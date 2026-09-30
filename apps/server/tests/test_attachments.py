import hashlib
import io
from urllib.parse import quote

import pytest
from protocol.generated import python as dto

from conftest import check_http
from r3_support import Worker3
from server.common import digest,stamp,uid


class Worker4(Worker3):
    def hello(self,**changes):return super().hello(**(dict(wireRevision=4)|changes))
    def event(self,kind,seq=None,**fields):
        self.seq=self.seq+1 if seq is None else seq
        value=dict(type=kind,wireRevision=4,workerId=self.worker,workerStoreId=self.store,workerEpoch=self.epoch,eventId=uid(),seq=self.seq,occurredAt=stamp(self.env.clock()),**fields)
        dto.RemoteV4WorkerOutboundFrame.model_validate(value);return value
    def receive(self):
        value=self.ws.receive_json();getattr(dto,{1:'RemoteServerOutboundFrame',2:'RemoteV2ServerOutboundFrame',3:'RemoteV3ServerOutboundFrame',4:'RemoteV4ServerOutboundFrame'}[value['wireRevision']]).model_validate(value);return value


@pytest.fixture
def env(r15_env):
    with r15_env.service.repo.transaction() as tx:r15_env.owner=r15_env.service.security.session(tx,r15_env.alice.cookie)['owner']
    return r15_env


@pytest.fixture
def attachment_worker(env):
    w=Worker4(env,env.alice);w.confirm()
    with w.connect():
        w.catalog();w.conv=w.upsert();w.busy()
        yield w


def upload(env,conv,data=b'hello file',name='safe.txt',key=None,headers=None,browser=None):
    b=browser or env.alice
    h={'Cookie':'__Host-hqremote='+b.cookie,'Origin':env.settings.origin,'X-CSRF-Token':b.csrf,'Idempotency-Key':key or uid(),
       'Content-Type':'application/octet-stream','Content-Length':str(len(data)),'X-File-Name':quote(name),'X-Content-Sha256':hashlib.sha256(data).hexdigest()}
    h.update(headers or {})
    result=env.client.post('/api/v2/conversations/'+conv+'/attachments',content=data,headers=h)
    check_http(result,'POST','/api/v2/conversations/'+conv+'/attachments');return result


def content(env,identifier,**headers):
    return env.client.get('/api/v2/attachments/'+identifier+'/content',headers={'Cookie':'__Host-hqremote='+env.alice.cookie,**headers})


def test_stream_upload_replay_shared_hash_and_true_delete(env,attachment_worker):
    w=attachment_worker;data=b'UNIQUE-ATTACHMENT-BODY';key=uid()
    first=upload(env,w.conv,data,key=key);assert first.status_code==201,first.text
    one=first.json()['data']['attachment'];identifier=one['attachmentId']
    assert upload(env,w.conv,data,key=key).json()['data']==first.json()['data']
    assert upload(env,w.conv,b'other',key=key).status_code==409
    two=upload(env,w.conv,data).json()['data']['attachment']
    limits=env.alice.get('/attachments/limits').json()['data']
    assert limits['usedBytes']==len(data)*2 and limits['reservedBytes']==0
    got=content(env,identifier)
    assert got.content==data and got.headers['content-length']==str(len(data))
    assert got.headers['content-disposition'].startswith('attachment') and got.headers['x-content-type-options']=='nosniff' and got.headers['cache-control']=='no-store' and got.headers['x-request-id']
    assert content(env,identifier,Range='bytes=0-1').status_code==400
    assert env.bob.get('/attachments/'+identifier).status_code==404
    store=env.service.attachments.store
    assert env.alice.request('DELETE','/attachments/'+identifier).status_code==200
    assert upload(env,w.conv,data,key=key).status_code==404
    assert store.exists(one['sha256']) and content(env,identifier).status_code==404
    assert env.alice.request('DELETE','/attachments/'+two['attachmentId']).status_code==200
    assert not store.exists(one['sha256'])
    with pytest.raises(FileNotFoundError):store.open_read(one['sha256'])
    with env.service.repo.transaction() as tx:
        for kind in ('attachment','blob-ref','upload','upload-intent'):assert tx.list(env.owner,kind)==[]
    assert list(store.temp.iterdir())==[]


@pytest.mark.parametrize('data,name,code',[(b'MZ'+b'1'*64,'fake.txt','ATTACHMENT_TYPE_UNSUPPORTED'),(b'<svg>bad</svg>','fake.txt','ATTACHMENT_TYPE_UNSUPPORTED'),(b'<!DOCTYPE html><html>','fake.md','ATTACHMENT_TYPE_UNSUPPORTED'),(b'a\0b','fake.txt','ATTACHMENT_TYPE_UNSUPPORTED'),(b'ok','fake.exe','ATTACHMENT_TYPE_UNSUPPORTED'),(b'','empty.txt','VALIDATION_FAILED')])
def test_type_spoof_cleanup(env,attachment_worker,data,name,code):
    result=upload(env,attachment_worker.conv,data,name)
    assert result.json()['error']['code']==code
    assert list(env.service.attachments.store.temp.iterdir())==[]
    assert env.alice.get('/attachments/limits').json()['data']['reservedBytes']==0


@pytest.mark.parametrize('length',[2,200])
def test_content_length_lies_cleanup(env,attachment_worker,length):
    result=upload(env,attachment_worker.conv,b'12345',headers={'Content-Length':str(length)})
    assert result.json()['error']['code']=='ATTACHMENT_HASH_MISMATCH'
    assert list(env.service.attachments.store.temp.iterdir())==[]


def test_send_manifest_grant_and_pin_expiration(env,attachment_worker):
    w=attachment_worker
    a=upload(env,w.conv).json()['data']['attachment']
    sent=w.send(w.conv,attachmentIds=[a['attachmentId']]);frame=w.receive()
    assert frame['wireRevision']==4 and frame['payload']['attachments']==[{k:a[k] for k in ('attachmentId','fileName','kind','mimeType','sizeBytes','sha256')}]
    assert env.alice.get('/attachments/'+a['attachmentId']).json()['data']['state']=='reserved'
    assert env.alice.request('DELETE','/attachments/'+a['attachmentId']).json()['error']['code']=='ATTACHMENT_IN_USE'
    worker_headers={'Cookie':'','Authorization':'Bearer '+w.secret}
    path='/api/v2/worker/attachments/'+a['attachmentId']+'/content?commandId='+sent['commandId']
    assert env.client.get(path,headers=worker_headers).status_code==404
    w.received(frame);w.receive();w.accepted(frame)
    assert env.client.get(path,headers=worker_headers).content==b'hello file'
    env.clock.advance(601);env.service.attachments.maintain()
    assert env.alice.get('/attachments/'+a['attachmentId']).json()['data']['state']=='uploaded'


def test_expiry_restart_recovery_and_orphans(env,attachment_worker):
    w=attachment_worker;a=upload(env,w.conv).json()['data']['attachment']
    store=env.service.attachments.store
    orphan=store.cas/('b'*64);orphan.write_bytes(b'orphan');temp=store.temp/'abandoned';temp.write_bytes(b'partial')
    env.clock.advance(86400)
    from conftest import Browser
    env.alice=Browser(env,'alice')
    assert content(env,a['attachmentId']).status_code==404
    from server.attachments import Attachments
    recovered=Attachments(env.service)
    assert not recovered.store.exists(a['sha256']) and not orphan.exists() and not temp.exists()
    assert env.alice.get('/attachments/limits').json()['data']['usedBytes']==0


def test_image_thumbnail_and_capability_fail_closed(env,attachment_worker):
    from PIL import Image
    stream=io.BytesIO();Image.new('RGB',(800,400),'blue').save(stream,format='PNG',pnginfo=None)
    w=attachment_worker;result=upload(env,w.conv,stream.getvalue(),'wrong.exe')
    assert result.status_code==201,result.text
    a=result.json()['data']['attachment'];assert a['fileName'].endswith('.png') and a['kind']=='image'
    assert a['thumbnailStatus']=='ready'
    thumb=env.client.get('/api/v2/attachments/'+a['attachmentId']+'/thumbnail',headers={'Cookie':'__Host-hqremote='+env.alice.cookie})
    assert thumb.status_code==200 and thumb.headers['content-type']=='image/png'
    with Image.open(io.BytesIO(thumb.content)) as image:assert max(image.size)==512 and image.info=={}
    rejected=env.alice.post('/conversations/'+w.conv+'/messages',dict(clientMessageId=uid(),text='image',sessionMode='new',attachmentIds=[a['attachmentId']]))
    assert rejected.json()['error']['code']=='AGENT_IMAGE_UNSUPPORTED'
    with env.service.repo.transaction() as tx:value=tx.get(env.owner,'attachment',a['attachmentId']);thumb_hash=value['_thumbnail']
    env.alice.request('DELETE','/attachments/'+a['attachmentId'])
    assert not env.service.attachments.store.exists(thumb_hash)


@pytest.mark.parametrize('action',['conversation','reset','device'])
def test_scoped_erasure_of_files_metadata_replay_and_read_handles(env,attachment_worker,action):
    w=attachment_worker;a=upload(env,w.conv,b'ERASE-ATTACHMENT-MARKER').json()['data']['attachment']
    store=env.service.attachments.store
    handle=store.open_read(a['sha256']);env.service.attachments.readers[(env.owner,a['attachmentId'])]={handle}
    if action=='conversation':w.emit(w.event('sync.conversation.deleted',syncGeneration=1,conversationId='local',deletedAt=stamp(env.clock())))
    elif action=='reset':w.emit(w.event('sync.reset',syncGeneration=2))
    else:env.alice.request('DELETE','/devices/'+w.worker)
    assert handle.closed and not store.exists(a['sha256']) and content(env,a['attachmentId']).status_code==404
    with env.service.repo.transaction() as tx:
        for kind in ('attachment','blob-ref','upload','upload-intent'):assert tx.list(env.owner,kind)==[]
    assert list(store.temp.iterdir())==[]


def test_worker_pending_upload_and_suspension_matrix(env,attachment_worker):
    w=attachment_worker;data=b'local user bytes'
    item=dict(localAttachmentId='local-attachment',fileName='local.txt',kind='file',mimeType='text/plain',sizeBytes=len(data),sha256=hashlib.sha256(data).hexdigest(),availability='pending_upload')
    event=w.message('local','user message',message='local-message',role='user',attachments=[item])
    assert w.emit(event)['type']=='worker.events_ack'
    snap=env.alice.get('/conversations/'+w.conv+'/snapshot').json()['data'];identifier=snap['messages'][0]['attachments'][0]['attachmentId']
    env.alice.request('PATCH','/devices/'+w.worker,dict(expectedVersion=1,remoteAccess='suspended'))
    assert upload(env,w.conv).json()['error']['code']=='REMOTE_DEVICE_SUSPENDED'
    h={'Cookie':'','Authorization':'Bearer '+w.secret,'Content-Type':'application/octet-stream','Content-Length':str(len(data)),'X-File-Name':'local.txt','X-Content-Sha256':item['sha256'],'Idempotency-Key':uid(),
       'X-Worker-Store-Id':w.store,'X-Sync-Generation':'1','X-Local-Conversation-Id':'local','X-Local-Message-Id':'local-message','X-Local-Attachment-Id':'local-attachment'}
    response=env.client.post('/api/v2/worker/attachments',content=data,headers=h)
    assert response.status_code==201,response.text
    assert response.json()['data']['attachment']['attachmentId']==identifier
    assert env.client.post('/api/v2/worker/attachments',content=data,headers=h).status_code==201
    assert w.emit(w.message('local','user message',message='local-message',revision=2,role='user',attachments=[dict(item,availability='available')]))['type']=='worker.events_ack'
    assert w.emit(w.message('local','second user message',message='second-local-message',sequence=2,role='user',attachments=[dict(item,availability='available')]))['type']=='worker.events_ack'
    assert env.alice.get('/attachments/limits').json()['data']['usedBytes']==len(data)
    with env.service.repo.transaction() as tx:
        assert len(tx.get(env.owner,'attachment',identifier)['_messages'])==2
    assert content(env,identifier).content==data
    assert env.client.get('/api/v2/worker/attachments/'+identifier+'/content',headers={'Cookie':'','Authorization':'Bearer '+w.secret}).content==data
    w.upsert(version=2,visibility='pc_only')
    assert content(env,identifier).status_code==404
