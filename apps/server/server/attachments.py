"""Attachment transactions, quota reservations, scoped readers and physical GC."""
import asyncio
import hashlib
import hmac
import re
import sys
import subprocess
import os
import importlib.util
import time
from pathlib import Path
from urllib.parse import quote

from starlette.responses import Response, StreamingResponse

from .attachment_types import Detector, LIMITS, filename
from .blobstore import BLOCK, LocalBlobStore
from .common import Fault, canonical, digest, require, seconds, stamp, uid, validated
from .security import COOKIE

MANIFEST=('attachmentId','fileName','kind','mimeType','sizeBytes','sha256')


class DeadlineStreamResponse(StreamingResponse):
    async def stream_response(self,send):
        start=time.monotonic()
        async def bounded(message):
            remaining=120-(time.monotonic()-start)
            require(remaining>0,'ATTACHMENT_DOWNLOAD_FAILED')
            await asyncio.wait_for(send(message),min(30,remaining))
        try:await super().stream_response(bounded)
        finally:
            close=getattr(self.body_iterator,'aclose',None)
            if close:await close()


class Attachments:
    def __init__(self, service):
        self.s=service; self.store=LocalBlobStore(service.settings.database.parent/'blobs')
        self.active={}; self.readers={}; self.thumbnail_jobs={}; self.decoder=asyncio.Semaphore(1)
        self.quota=LIMITS['accountQuotaBytes']
        self.maintain(startup=True)

    def save(self,tx,owner,value):
        self.s.save(tx,owner,'attachment',value['attachmentId'],value)

    def view(self,value):
        message={k:value[k] for k in (*MANIFEST,'availability','thumbnailStatus','errorCode') if k in value}
        result=dict(attachment=message,conversationId=value['conversationId'],state=value['state'],createdAt=value['createdAt'])
        if value['state']!='attached': result['expiresAt']=value['expiresAt']
        return validated('RemoteAttachmentView',result)

    def get(self,tx,owner,identifier,*,browser=True):
        value=tx.get(owner,'attachment',identifier)
        require(value is not None,'NOT_FOUND')
        device=self.s.get(tx,owner,'device',value['_worker'])
        require(device['workerStoreId']==value['_store'],'NOT_FOUND')
        conv=self.s.browser_get(tx,owner,'conversation',value['conversationId']) if browser else self.s.get(tx,owner,'conversation',value['conversationId'])
        require(conv.get('_generation',0)==value['_generation'],'NOT_FOUND')
        require(value['state']=='attached' or seconds(value['expiresAt'])>self.s.settings.clock() or (value['state']=='reserved' and value.get('_pin',0)>self.s.settings.clock()),'NOT_FOUND')
        return value

    def quota_view(self,tx,owner):
        used,reserved=tx.attachment_usage(owner)
        return dict(limits=LIMITS,usedBytes=used,reservedBytes=reserved,observedAt=self.s.now())

    def prepare_send(self,tx,owner,conv,body):
        ids=body.get('attachmentIds',[])
        require(len(ids)<=5,'ATTACHMENT_COUNT_EXCEEDED');require(len(ids)==len(set(ids)))
        if not ids:return {}
        require(self.s.connections[(owner,conv['targetWorkerId'])].revision==4,'REMOTE_REVISION_REQUIRED')
        values=[self.get(tx,owner,i) for i in ids]
        for value in values:
            require(value['conversationId']==conv['conversationId'],'NOT_FOUND')
            require(value['state']=='uploaded','ATTACHMENT_IN_USE')
            require(value['availability']=='available' and self.store.exists(value.get('_blob','0'*64)),'ATTACHMENT_NOT_READY')
        result=dict(attachments=[{k:v[k] for k in MANIFEST} for v in values])
        images=[v for v in values if v['kind']=='image']
        if images:
            catalog=self.s.get(tx,owner,'catalog',conv['targetWorkerId'])
            if conv.get('conversationKind')=='native':
                caps=[c['imageInput'] for c in catalog.get('nativeImageCapabilities',[]) if c['agentType']==conv['agentType']]
            else:
                scene=next((c for c in catalog['scenes'] if c['sceneId']==conv['sceneId'] and c['version']==conv['sceneVersion']),{})
                caps=[r['imageInput'] for r in scene.get('roleImageCapabilities',[])]
            require(bool(caps),'AGENT_IMAGE_UNSUPPORTED')
            for cap in caps:
                require(cap['support']=='supported' and cap['cliEntry']=='supported' and cap['runtimeImplemented'] and cap['verified'] and all(v['mimeType'] in cap['mimeTypes'] and v['sizeBytes']<=cap['maxBytes'] for v in images),'AGENT_IMAGE_UNSUPPORTED')
            result['attachmentCapabilityRevision']=catalog['capabilityRevision']
        return result

    def reserve_send(self,tx,owner,receipt,ids):
        for identifier in ids:
            value=self.get(tx,owner,identifier)
            value.update(state='reserved',_command=receipt['commandId'],_pin=seconds(receipt['expiresAt']))
            self.save(tx,owner,value)

    def grant(self,tx,owner,command):
        for item in command['_frame'].get('payload',{}).get('attachments',[]):
            value=tx.get(owner,'attachment',item['attachmentId'])
            if value and value.get('_command')==command['commandId']:
                value['_pin']=self.s.settings.clock()+600;self.save(tx,owner,value)

    def release_failed(self,tx,owner,command):
        if command['status'] not in {'failed','rejected'}:return
        for value in tx.list(owner,'attachment',worker=command['targetWorkerId']):
            if value['state']=='reserved' and value.get('_command')==command['commandId']:
                value.update(state='uploaded');value.pop('_command',None);value.pop('_pin',None)
                if seconds(value['expiresAt'])<=self.s.settings.clock():self.remove(tx,owner,value)
                else:self.save(tx,owner,value)

    def sync_message(self,tx,owner,event,value):
        p=event['payload'];items=p.get('attachments',[])
        require(not items or (event['wireRevision']==4 and p['role']=='user'),'REMOTE_SYNC_CONFLICT')
        require(len(items)<=5 and len({a['localAttachmentId'] for a in items})==len(items),'REMOTE_SYNC_CONFLICT')
        result=[]
        for item in items:
            binding_key=digest([event['workerId'],event['workerStoreId'],event['syncGeneration'],p['messageId'],item['localAttachmentId']])
            prior=tx.get(owner,'attachment-binding',binding_key);origin=item.get('originAttachmentId')
            local_key=digest([event['workerId'],event['workerStoreId'],event['syncGeneration'],value['conversationId'],item['localAttachmentId']])
            local_binding=tx.get(owner,'attachment-local',local_key)
            if origin:
                require('sourceCommandId' in p and 'runId' in p,'REMOTE_TARGET_MISMATCH')
                command=self.s.get(tx,owner,'command',p['sourceCommandId'])
                run=tx.sync_lookup(owner,event['workerId'],event['workerStoreId'],'run',p['runId'])
                require(command.get('_granted') and command['targetWorkerId']==event['workerId'] and command['_frame']['expectedWorkerStoreId']==event['workerStoreId'] and command.get('conversationId')==value['conversationId'] and run and command.get('resultRef',{}).get('runId')==run['public'],'REMOTE_TARGET_MISMATCH')
                source=next((m for m in command['_frame'].get('payload',{}).get('attachments',[]) if m['attachmentId']==origin),None)
                require(source is not None and all(source[k]==item[k] for k in MANIFEST if k!='attachmentId'),'REMOTE_TARGET_MISMATCH')
                identifier=origin
            elif prior:identifier=prior['attachmentId']
            elif local_binding:identifier=local_binding['attachmentId']
            else:identifier=uid()
            attachment=tx.get(owner,'attachment',identifier)
            if attachment is None and (origin or prior):
                result.append(dict(attachmentId=identifier,**{k:item[k] for k in MANIFEST if k!='attachmentId'},availability='unavailable',thumbnailStatus='unavailable' if item['kind']=='image' else 'not_applicable',errorCode='NOT_FOUND'))
                continue
            if attachment is None:
                require(item['availability']!='available','ATTACHMENT_NOT_READY')
                attachment=dict(attachmentId=identifier,conversationId=value['conversationId'],state='attached',createdAt=self.s.now(),expiresAt=stamp(self.s.settings.clock()+86400),_worker=event['workerId'],_store=event['workerStoreId'],_generation=event['syncGeneration'],_messages=[],**{k:item[k] for k in MANIFEST if k!='attachmentId'},availability=item['availability'],thumbnailStatus='pending' if item['kind']=='image' else 'not_applicable')
                attachment['fileName']=filename(quote(item['fileName']))
            require(attachment['conversationId']==value['conversationId'] and all(attachment[k]==item[k] for k in ('kind','mimeType','sizeBytes','sha256')),'REMOTE_SYNC_CONFLICT')
            if attachment.get('_command'):require(attachment['_command']==p.get('sourceCommandId'),'ATTACHMENT_IN_USE')
            attachment['state']='attached';attachment['_messages']=sorted(set(attachment.get('_messages',[]))|{value['messageId']})
            if item['availability']=='available':require(attachment.get('_blob') and self.store.exists(attachment['_blob']),'ATTACHMENT_NOT_READY')
            attachment['availability']=item['availability']
            if item.get('errorCode'):attachment['errorCode']=item['errorCode']
            self.save(tx,owner,attachment)
            tx.put(owner,'attachment-binding',binding_key,dict(id=binding_key,attachmentId=identifier,conversationId=value['conversationId']),worker=event['workerId'],store=event['workerStoreId'],parent=value['conversationId'])
            tx.put(owner,'attachment-local',local_key,dict(id=local_key,attachmentId=identifier,conversationId=value['conversationId']),worker=event['workerId'],store=event['workerStoreId'],parent=value['conversationId'])
            result.append(self.view(attachment)['attachment'])
        return result

    def collect(self,hash_):
        with self.s.repo.transaction() as tx:
            if not tx.blob_referenced(hash_): self.store.delete(hash_)

    def cancel_scope(self,owner,ids,uploads):
        for identifier in ids:
            for handle in list(self.readers.pop((owner,identifier),set())): handle.close()
        for identifier in uploads:
            stage=self.active.get((owner,identifier))
            if stage:
                job=self.thumbnail_jobs.get(stage.path.name)
                if job:
                    process,destination=job
                    if process.poll() is None:process.kill();process.wait(timeout=2)
                    destination.unlink(missing_ok=True)
                self.store.abort(stage)

    def remove(self,tx,owner,value):
        identifier=value['attachmentId']
        tx.put(owner,'attachment-deletion',identifier,dict(attachmentId=identifier))
        tx.after_commit(('attachment-deletion',owner,identifier),lambda:self.store.remember_deletion(owner,identifier))
        tx.after_commit(('close-attachment',owner,identifier),lambda:self.cancel_scope(owner,[identifier],[]))
        tx.remove_record(owner,'attachment',identifier)
        tx.erase_attachment_intents(owner,{identifier})
        for variant,field in [('original','_blob'),('thumbnail','_thumbnail')]:
            tx.remove_record(owner,'blob-ref',identifier+':'+variant)
            if value.get(field):
                hash_=value[field]
                tx.after_commit(('blob-gc',hash_),lambda h=hash_:self.collect(h))

    def erase(self,tx,owner,worker,store,conversation=None):
        convs={v['conversationId'] for v in tx.list(owner,'conversation',worker=worker,store=store) if conversation is None or v.get('_localId',v['conversationId'])==conversation}
        for value in tx.list(owner,'attachment',worker=worker,store=store):
            if conversation is None or value['conversationId'] in convs: self.remove(tx,owner,value)
        uploads=[]
        for up in tx.list(owner,'upload',worker=worker,store=store):
            if conversation is None or up['conversationId'] in convs:
                tx.put(owner,'upload-retired',up['intent'],dict(content=up['content']))
                uploads.append(up['id']);tx.remove_record(owner,'upload',up['id'])
        for kind in ('attachment-binding','attachment-local'):
            for binding in tx.list(owner,kind,worker=worker,store=store):
                if conversation is None or binding['conversationId'] in convs: tx.remove_record(owner,kind,binding['id'])
        tx.after_commit(('close-uploads',owner,worker,store,conversation),lambda:self.cancel_scope(owner,[],uploads))

    def maintain(self,startup=False):
        now=self.s.settings.clock()
        with self.s.repo.transaction() as tx:
            if startup:
                for deletion in self.store.deletions():
                    owner,identifier=deletion['owner'],deletion['attachmentId']
                    value=tx.get(owner,'attachment',identifier)
                    if value:self.remove(tx,owner,value)
                    tx.scrub_attachment_replays(owner,identifier)
                # A crash after SQLite commit but before the journal callback
                # is completed from the durable, body-free deletion intent.
                for owner in tx.attachment_deletion_owners():
                    for deletion in tx.list(owner,'attachment-deletion'):
                        identifier=deletion['attachmentId']
                        tx.after_commit(('attachment-deletion',owner,identifier),lambda o=owner,i=identifier:self.store.remember_deletion(o,i))
            for owner in tx.attachment_owners():
                for upload in tx.list(owner,'upload'):
                    if startup or upload['deadline']<=now:
                        tx.remove_record(owner,'upload',upload['id'])
                        tx.after_commit(('abort',owner,upload['id']),lambda o=owner,i=upload['id']:self.cancel_scope(o,[],[i]))
                for value in tx.list(owner,'attachment'):
                    if value['state']=='reserved':
                        command=tx.get(owner,'command',value['_command'])
                        release=not command or command['status'] in {'failed','rejected'} or (not command.get('_granted') and seconds(command['expiresAt'])<=now) or (command.get('_granted') and value.get('_pin',0)<=now)
                        if release:
                            value['state']='uploaded';value.pop('_command',None);value.pop('_pin',None);self.save(tx,owner,value)
                    if value['state']=='uploaded' and seconds(value['expiresAt'])<=now:self.remove(tx,owner,value)
            if startup:
                for path in self.store.temp.iterdir():path.unlink(missing_ok=True)
            for path in self.store.cas.iterdir():
                if not tx.blob_referenced(path.name):
                    tx.after_commit(('blob-gc',path.name),lambda h=path.name:self.collect(h))

    def credential(self,tx,request,worker_mode,write):
        if worker_mode:
            require(not request.cookies.get(COOKIE),'REMOTE_AUTH_AMBIGUOUS')
            _,verifier=self.s.security.bearer(request.headers.get('authorization'))
            owner,device=self.s.security.device_identity(tx,verifier)
            return owner,device
        session=self.s.security.session(tx,request.cookies.get(COOKIE))
        require(session is not None,'REMOTE_AUTH_REQUIRED')
        if write:
            require(request.headers.get('origin')==self.s.settings.origin,'REMOTE_CSRF_REJECTED')
            require(hmac.compare_digest(request.headers.get('x-csrf-token',''),self.s.security.csrf(session['id'])),'REMOTE_CSRF_REJECTED')
        return session['owner'],None

    def upload_target(self,tx,owner,device,request):
        if device is None:
            conv=self.s.browser_get(tx,owner,'conversation',request.path_params['conversationId'])
            worker=self.s.get(tx,owner,'device',conv['targetWorkerId'])
            require(worker['status']!='revoked','REMOTE_DEVICE_REVOKED')
            require(worker.get('remoteAccess','enabled')!='suspended','REMOTE_DEVICE_SUSPENDED')
            require(worker['workerStoreId']==conv['workerStoreId'],'REMOTE_STORE_CHANGED')
            return conv,None
        headers=request.headers
        store=headers.get('x-worker-store-id'); generation=int(headers.get('x-sync-generation','0'))
        require(device['workerStoreId']==store,'REMOTE_STORE_CHANGED')
        state=self.s.replica.state(tx,owner,device['workerId'],store)
        require(state['enabled'] and state['generation']==generation,'REMOTE_SYNC_DISABLED')
        mapping=tx.sync_lookup(owner,device['workerId'],store,'conversation',headers.get('x-local-conversation-id',''))
        require(mapping and not mapping['deleted'],'ATTACHMENT_NOT_READY')
        conv=self.s.get(tx,owner,'conversation',mapping['public'])
        binding_key=digest([device['workerId'],store,generation,headers.get('x-local-message-id'),headers.get('x-local-attachment-id')])
        binding=tx.get(owner,'attachment-binding',binding_key)
        require(binding is not None and binding['conversationId']==conv['conversationId'],'ATTACHMENT_NOT_READY')
        value=self.get(tx,owner,binding['attachmentId'],browser=False)
        require(value['state']=='attached','ATTACHMENT_NOT_READY')
        return conv,value

    async def thumbnail(self,stage):
        destination=self.store.temp/uid()
        async with self.decoder:
            if not stage.path.exists():return None
            # Bypass the Windows venv launcher: kill/wait must target the actual
            # decoder, not a launcher whose child could survive its termination.
            pillow_site=str(Path(importlib.util.find_spec('PIL').origin).parent.parent)
            child_env=dict(os.environ,PYTHONPATH=pillow_site,PYTHONDONTWRITEBYTECODE='1')
            process=subprocess.Popen([getattr(sys,'_base_executable',sys.executable),'-B',str(Path(__file__).with_name('thumbnail_child.py')),str(stage.path),str(destination)],env=child_env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.thumbnail_jobs[stage.path.name]=(process,destination)
            try: await asyncio.to_thread(process.wait,timeout=8)
            except BaseException:
                if process.poll() is None:process.kill();process.wait(timeout=2)
                destination.unlink(missing_ok=True);return None
            finally:self.thumbnail_jobs.pop(stage.path.name,None)
        if process.returncode==0 and destination.exists() and destination.stat().st_size<=524288:
            hash_=hashlib.sha256(destination.read_bytes()).hexdigest()
            with destination.open('rb') as stream: thumb=self.store.stage_write(stream,524288,hash_)
            destination.unlink(missing_ok=True);return thumb
        destination.unlink(missing_ok=True);return None

    async def upload(self,request,worker_mode):
        headers=request.headers; key=headers.get('idempotency-key','')
        require(1<=len(key)<=200)
        require(headers.get('content-type','').split(';')[0]=='application/octet-stream','BAD_REQUEST')
        require(len(headers.getlist('content-length'))==1 and re.fullmatch(r'[0-9]+',headers['content-length']) is not None,'BAD_REQUEST')
        length=int(headers['content-length']); require(length>0);require(length<=20000000,'ATTACHMENT_TOO_LARGE')
        expected=headers.get('x-content-sha256','');require(re.fullmatch('[0-9a-f]{64}',expected) is not None,'BAD_REQUEST')
        name=filename(headers.get('x-file-name','')); detector=Detector(name)
        stage=None;thumb=None;upload_id=None;owner=None
        try:
            with self.s.repo.transaction() as tx:
                owner,device=self.credential(tx,request,worker_mode,True)
                conv,target=self.upload_target(tx,owner,device,request)
                if target:require(target['sha256']==expected and target['sizeBytes']==length,'ATTACHMENT_HASH_MISMATCH')
                scope=[conv['conversationId'],target['attachmentId'] if target else None,key]
                intent=self.s.security.mac('upload-key',canonical(scope))
                content=self.s.security.mac('upload-content',canonical([name,length,expected]))
                retired=tx.get(owner,'upload-retired',intent)
                if retired:
                    require(retired['content']==content,'IDEMPOTENCY_MISMATCH')
                    raise Fault('NOT_FOUND')
                prior=tx.get(owner,'upload-intent',intent)
                if prior:
                    require(prior['content']==content,'IDEMPOTENCY_MISMATCH')
                    self.get(tx,owner,prior['attachmentId'],browser=not worker_mode)
                identifier=prior['attachmentId'] if prior else target['attachmentId'] if target else uid()
                require(not any(u['intent']==intent or u['attachmentId']==identifier for u in tx.list(owner,'upload')),'CONFLICT')
                require(len(tx.list(owner,'upload'))<2,'REMOTE_RATE_LIMITED')
                reserved=0 if prior or (target and target.get('_blob')) else length
                used,pending=tx.attachment_usage(owner);require(used+pending+reserved<=self.quota,'ATTACHMENT_QUOTA_EXCEEDED')
                upload_id=uid();stage=self.store.stage_write(None,length,expected)
                up=dict(id=upload_id,intent=intent,content=content,attachmentId=identifier,reserved=reserved,deadline=self.s.settings.clock()+120,conversationId=conv['conversationId'],_worker=conv['targetWorkerId'],_store=conv['workerStoreId'],generation=conv.get('_generation',0))
                self.s.save(tx,owner,'upload',upload_id,up)
                self.active[(owner,upload_id)]=stage
            start=time.monotonic(); iterator=request.stream().__aiter__()
            while True:
                try: chunk=await asyncio.wait_for(anext(iterator),min(30,max(.001,120-(time.monotonic()-start))))
                except StopAsyncIteration:break
                require(time.monotonic()-start<120,'ATTACHMENT_PREPARATION_INTERRUPTED')
                require(stage.size+len(chunk)<=length,'ATTACHMENT_HASH_MISMATCH')
                for offset in range(0,len(chunk),BLOCK):
                    part=memoryview(chunk)[offset:offset+BLOCK]
                    detector.feed(bytes(part));require(detector.kind!='image' or length<=10000000,'ATTACHMENT_TOO_LARGE')
                    stage.write(part)
            require(stage.size==length,'ATTACHMENT_HASH_MISMATCH');detector.feed(b'',final=True);stage.finish()
            if detector.kind=='image':thumb=await asyncio.wait_for(self.thumbnail(stage),max(.001,120-(time.monotonic()-start)))
            with self.s.repo.transaction() as tx:
                current_owner,device=self.credential(tx,request,worker_mode,True);require(owner==current_owner,'NOT_FOUND')
                require(tx.get(owner,'upload',upload_id) is not None,'NOT_FOUND')
                current,target=self.upload_target(tx,owner,device,request)
                require(current.get('_generation',0)==up['generation'] and current['workerStoreId']==up['_store'],'NOT_FOUND')
                if prior:
                    value=self.get(tx,owner,identifier,browser=not worker_mode)
                else:
                    value=target or dict(attachmentId=identifier,conversationId=current['conversationId'],state='uploaded',createdAt=self.s.now(),expiresAt=stamp(self.s.settings.clock()+86400),_worker=up['_worker'],_store=up['_store'],_generation=up['generation'])
                    if target:require(target['kind']==detector.kind and target['mimeType']==detector.mime,'ATTACHMENT_TYPE_UNSUPPORTED')
                    self.store.commit(stage,expected)
                    value.update(fileName=detector.normalized_name(),kind=detector.kind,mimeType=detector.mime,sizeBytes=length,sha256=expected,availability='available',thumbnailStatus='unavailable' if detector.kind=='image' else 'not_applicable',_blob=expected)
                    tx.put(owner,'blob-ref',identifier+':original',dict(hash=expected),worker=up['_worker'],store=up['_store'],parent=current['conversationId'])
                    if thumb:
                        hash_=thumb.hash.hexdigest();self.store.commit(thumb,hash_);value.update(_thumbnail=hash_,thumbnailStatus='ready')
                        tx.put(owner,'blob-ref',identifier+':thumbnail',dict(hash=hash_),worker=up['_worker'],store=up['_store'],parent=current['conversationId'])
                    self.save(tx,owner,value)
                    tx.put(owner,'upload-intent',intent,dict(content=content,attachmentId=identifier),worker=up['_worker'],store=up['_store'],parent=current['conversationId'])
                tx.remove_record(owner,'upload',upload_id)
                return self.view(value)
        except (asyncio.TimeoutError,ConnectionError):raise Fault('ATTACHMENT_PREPARATION_INTERRUPTED') from None
        finally:
            if stage:self.store.abort(stage)
            if thumb:self.store.abort(thumb)
            if owner and upload_id:
                self.active.pop((owner,upload_id),None)
                with self.s.repo.transaction() as tx:tx.remove_record(owner,'upload',upload_id)
                self.collect(expected)
                if thumb:self.collect(thumb.hash.hexdigest())

    def download(self,tx,owner,value,thumbnail):
        require(value['availability']=='available' and value.get('_blob'),'ATTACHMENT_NOT_READY')
        if thumbnail:
            require(value['thumbnailStatus']!='pending','ATTACHMENT_NOT_READY')
            require(value['thumbnailStatus']=='ready' and value.get('_thumbnail'),'ATTACHMENT_THUMBNAIL_UNAVAILABLE')
        hash_=value['_thumbnail'] if thumbnail else value['_blob']
        require(self.store.exists(hash_),'ATTACHMENT_NOT_READY')
        handle=self.store.open_read(hash_);reader_key=(owner,value['attachmentId'])
        self.readers.setdefault(reader_key,set()).add(handle)
        size=self.store.path(hash_).stat().st_size
        async def stream():
            start=time.monotonic()
            try:
                while not handle.closed:
                    require(time.monotonic()-start<120,'ATTACHMENT_DOWNLOAD_FAILED')
                    with self.s.repo.transaction() as check:
                        self.get(check,owner,value['attachmentId'])
                        chunk=handle.read(BLOCK) if not handle.closed else b''
                    if not chunk:break
                    yield chunk
                    await asyncio.sleep(0)
            finally:
                handle.close()
                handles=self.readers.get(reader_key)
                if handles is not None:
                    handles.discard(handle)
                    if not handles:self.readers.pop(reader_key,None)
        return DeadlineStreamResponse(stream(),media_type='image/png' if thumbnail else 'application/octet-stream',headers={'Content-Length':str(size),'Content-Disposition':"attachment; filename*=UTF-8''"+quote('thumbnail.png' if thumbnail else value['fileName']),'X-Content-Type-Options':'nosniff','Cache-Control':'no-store'})

    async def http(self,request,operation):
        from .http import response
        worker_mode=operation.startswith('worker_attachment');write=request.method in {'POST','DELETE'}
        self.s.security.rate('attachment:'+ (request.client.host if request.client else 'unknown'))
        with self.s.repo.transaction() as tx:self.credential(tx,request,worker_mode,write)
        allowed={'commandId','variant'} if operation=='worker_attachment_content' else set()
        require(set(request.query_params)<=allowed)
        if operation in {'attachment_upload','worker_attachment_upload'}:
            return response(await self.upload(request,worker_mode),model='RemoteAttachmentView',status=201)
        with self.s.repo.transaction() as tx:
            owner,device=self.credential(tx,request,worker_mode,write)
            if operation=='attachment_limits':return response(self.quota_view(tx,owner),model='RemoteAttachmentLimitsView')
            value=self.get(tx,owner,request.path_params['attachmentId'])
            if worker_mode:
                require(value['_worker']==device['workerId'] and value['_store']==device['workerStoreId'],'NOT_FOUND')
                command_id=request.query_params.get('commandId')
                if command_id:
                    command=tx.get(owner,'command',command_id)
                    require(command and command.get('_granted') and command['status'] in {'accepted','completed','failed'} and command['targetWorkerId']==device['workerId'] and command.get('conversationId')==value['conversationId'] and any(a['attachmentId']==value['attachmentId'] for a in command['_frame'].get('payload',{}).get('attachments',[])),'NOT_FOUND')
                else:require(value['state']=='attached' and value.get('_messages'),'NOT_FOUND')
            if operation=='attachment_metadata':return response(self.view(value),model='RemoteAttachmentView')
            if operation=='attachment_delete':
                require(1<=len(request.headers.get('idempotency-key',''))<=200)
                require(value['state']=='uploaded' and not value.get('_messages'),'ATTACHMENT_IN_USE')
                self.remove(tx,owner,value)
                return response(dict(attachmentId=value['attachmentId'],deleted=True),model='AttachmentDeletedView')
            require('range' not in request.headers,'BAD_REQUEST')
            allowed={'commandId','variant'} if worker_mode else set(); require(set(request.query_params)<=allowed)
            variant=request.query_params.get('variant','original');require(variant in {'original','thumbnail'})
            return self.download(tx,owner,value,operation=='attachment_thumbnail' or variant=='thumbnail')
