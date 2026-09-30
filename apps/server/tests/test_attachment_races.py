import asyncio
import hashlib
import io

import pytest
from starlette.requests import Request

from test_attachments import env,attachment_worker,upload,content,Worker4
from server.common import Fault,stamp,uid
from test_r15_replica import database_text


def request(env,conv,data,receive,key=None):
    headers={'cookie':'__Host-hqremote='+env.alice.cookie,'origin':env.settings.origin,'x-csrf-token':env.alice.csrf,
             'idempotency-key':key or uid(),'content-type':'application/octet-stream','content-length':str(len(data)),
             'x-file-name':'race.txt','x-content-sha256':hashlib.sha256(data).hexdigest()}
    return Request(dict(type='http',method='POST',path='/upload',scheme='https',query_string=b'',headers=[(k.encode(),v.encode()) for k,v in headers.items()],path_params={'conversationId':conv}),receive)


@pytest.mark.parametrize('mode',['quota','concurrency','duplicate','delete'])
def test_upload_reservation_and_deletion_races(env,attachment_worker,mode):
    w=attachment_worker; data=b'abcdef'; attachments=env.service.attachments
    async def scenario():
        release=asyncio.Event(); started=asyncio.Event(); first=True
        async def receive():
            nonlocal first
            if first:
                first=False;started.set();return dict(type='http.request',body=data[:3],more_body=True)
            await release.wait();return dict(type='http.request',body=data[3:],more_body=False)
        key=uid();task=asyncio.create_task(attachments.upload(request(env,w.conv,data,receive,key),False))
        await started.wait(); second_task=None
        try:
            with env.service.repo.transaction() as tx:
                assert tx.attachment_usage(env.owner)==(0,len(data))
            if mode=='delete':
                with env.service.repo.transaction() as tx:
                    env.service.erase_replica(tx,env.owner,w.worker,w.store,'local',permanent=True)
                release.set()
                with pytest.raises(Fault):await task
                assert not list(attachments.store.cas.iterdir()) and not list(attachments.store.temp.iterdir())
                return
            if mode=='quota':attachments.quota=10
            if mode=='concurrency':
                async def second_receive():return await receive()
                second_task=asyncio.create_task(attachments.upload(request(env,w.conv,data,second_receive),False))
                await asyncio.sleep(.02)
            async def complete():return dict(type='http.request',body=data,more_body=False)
            code={'quota':'ATTACHMENT_QUOTA_EXCEEDED','concurrency':'REMOTE_RATE_LIMITED','duplicate':'CONFLICT'}[mode]
            with pytest.raises(Fault,match=code):await attachments.upload(request(env,w.conv,data,complete,key if mode=='duplicate' else None),False)
        finally:
            release.set()
            if not task.done():await task
            if second_task:
                # Its body intentionally supplies only a suffix: cleanup must
                # release quota even on an independently failed writer.
                try:await second_task
                except Fault:pass
        with env.service.repo.transaction() as tx:assert tx.attachment_usage(env.owner)[1]==0
    env.client.portal.call(scenario)


def test_shared_blob_across_accounts_and_crash_before_db_commit(env,attachment_worker,monkeypatch):
    a=attachment_worker;b=Worker4(env,env.bob);b.confirm();data=b'SHARED-CONTENT'
    with b.connect():
        b.catalog();conv=b.upsert()
        one=upload(env,a.conv,data).json()['data']['attachment']
        two=upload(env,conv,data,browser=env.bob).json()['data']['attachment']
        env.alice.request('DELETE','/devices/'+a.worker)
        assert env.service.attachments.store.exists(one['sha256'])
        assert env.bob.get('/attachments/'+two['attachmentId']).status_code==200
        assert env.alice.get('/attachments/'+two['attachmentId']).status_code==404
        env.bob.request('DELETE','/attachments/'+two['attachmentId'])
        assert not env.service.attachments.store.exists(one['sha256'])
        original=env.service.attachments.save
        def fail(*args):raise RuntimeError('do not log failure input')
        with monkeypatch.context() as patch:
            patch.setattr(env.service.attachments,'save',fail)
            assert upload(env,conv,b'orphan bytes',browser=env.bob).status_code==500
        assert not list(env.service.attachments.store.cas.iterdir()) and not list(env.service.attachments.store.temp.iterdir())


def test_uploaded_files_offline_explicit_count_and_bad_hash(env,attachment_worker):
    w=attachment_worker
    assert upload(env,w.conv,headers={'X-Content-Sha256':'0'*64}).json()['error']['code']=='ATTACHMENT_HASH_MISMATCH'
    result=env.alice.post('/conversations/'+w.conv+'/messages',dict(clientMessageId=uid(),text='x',sessionMode='new',attachmentIds=[str(n) for n in range(6)]))
    assert result.json()['error']['code']=='ATTACHMENT_COUNT_EXCEEDED'
    result=upload(env,w.conv,headers={'Content-Length':'20000001'})
    assert result.json()['error']['code']=='ATTACHMENT_TOO_LARGE'
    # A device need not be online for a browser to stage a visible attachment.
    connection=env.service.connections[(env.owner,w.worker)]
    connection.last_seen=env.clock()-46
    assert upload(env,w.conv).status_code==201


def test_browser_origin_binds_to_granted_message_and_survives_pin(env,attachment_worker):
    w=attachment_worker;a=upload(env,w.conv).json()['data']['attachment']
    w.send(w.conv,attachmentIds=[a['attachmentId']]);frame=w.receive();w.received(frame);w.receive()
    assert w.emit(w.event('command.accepted',commandId=frame['commandId'],conversationId=w.conv,receivedAt=stamp(env.clock()),status='accepted',resultRef=dict(runId='run-local')))['type']=='worker.events_ack'
    item=dict(localAttachmentId='bound',originAttachmentId=a['attachmentId'],availability='available',**{k:a[k] for k in ('fileName','kind','mimeType','sizeBytes','sha256')})
    event=w.message('local','user text',message='bound-message',role='user',runId='run-local',sourceCommandId=frame['commandId'],attachments=[item])
    assert w.emit(event)['type']=='worker.events_ack'
    assert env.alice.get('/attachments/'+a['attachmentId']).json()['data']['state']=='attached'
    env.clock.advance(601);env.service.attachments.maintain()
    assert content(env,a['attachmentId']).content==b'hello file'


def test_image_all_role_capabilities_and_failed_thumbnail_no_fallback(env,attachment_worker):
    from PIL import Image
    w=attachment_worker;buf=io.BytesIO();Image.new('RGB',(5,5)).save(buf,format='PNG')
    a=upload(env,w.conv,buf.getvalue(),'one.png').json()['data']['attachment']
    cap=dict(support='supported',cliEntry='supported',runtimeImplemented=True,verified=True,mimeTypes=['image/png'],maxBytes=10000000)
    scene=dict(sceneId='scene',name='scene',version=1,readOnly=False,roleImageCapabilities=[dict(roleId='planner',agentId='a',imageInput=cap),dict(roleId='executor',agentId='b',imageInput=cap)])
    assert w.catalog(capabilityRevision=2,scenes=[scene])['type']=='worker.events_ack'
    w.send(w.conv,attachmentIds=[a['attachmentId']]);frame=w.receive()
    assert frame['payload']['attachmentCapabilityRevision']==2
    invalid=upload(env,w.conv,b'\x89PNG\r\n\x1a\ninvalid','bad.png')
    assert invalid.status_code==201
    value=invalid.json()['data']['attachment'];assert value['thumbnailStatus']=='unavailable'
    response=env.alice.get('/attachments/'+value['attachmentId']+'/thumbnail')
    assert response.json()['error']['code']=='ATTACHMENT_THUMBNAIL_UNAVAILABLE'


def test_attachment_content_and_name_never_logged(env,attachment_worker,caplog):
    caplog.set_level('INFO',logger='hqremote')
    result=upload(env,attachment_worker.conv,b'PRIVATE-CONTENT-MARKER','PRIVATE-FILE-MARKER.txt')
    assert result.status_code==201
    assert 'PRIVATE-CONTENT-MARKER' not in caplog.text and 'PRIVATE-FILE-MARKER' not in caplog.text
    assert env.alice.cookie not in caplog.text and attachment_worker.secret not in caplog.text


def test_retained_deletion_journal_prevents_old_snapshot_blob_resurrection(env,attachment_worker):
    from server.attachments import Attachments
    w=attachment_worker;data=b'backup restore bytes'
    item=upload(env,w.conv,data).json()['data']['attachment'];identifier=item['attachmentId']
    with env.service.repo.transaction() as tx:snapshot=tx.get(env.owner,'attachment',identifier)
    assert env.alice.request('DELETE','/attachments/'+identifier).status_code==200
    # An offline restore must retain/merge the latest external deletion journal.
    with env.service.repo.transaction() as tx:
        env.service.attachments.save(tx,env.owner,snapshot)
        tx.put(env.owner,'blob-ref',identifier+':original',dict(hash=item['sha256']))
    env.service.attachments.store.path(item['sha256']).write_bytes(data)
    recovered=Attachments(env.service)
    assert not recovered.store.exists(item['sha256'])
    with env.service.repo.transaction() as tx:
        assert tx.get(env.owner,'attachment',identifier) is None
        assert not tx.blob_referenced(item['sha256'])


def test_replay_still_verifies_bytes_and_filename_is_not_a_path(env,attachment_worker):
    w=attachment_worker;key=uid();first=upload(env,w.conv,b'first','C:/folder/CON.txt',key=key)
    assert first.status_code==201 and first.json()['data']['attachment']['fileName']=='attachment.txt'
    response=upload(env,w.conv,b'other','C:/folder/CON.txt',key=key,headers={'X-Content-Sha256':hashlib.sha256(b'first').hexdigest()})
    assert response.json()['error']['code']=='ATTACHMENT_HASH_MISMATCH'
    assert content(env,first.json()['data']['attachment']['attachmentId']).content==b'first'
