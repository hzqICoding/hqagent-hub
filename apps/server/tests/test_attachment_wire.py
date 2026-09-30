import pytest

from test_attachments import env,attachment_worker,upload,Worker4
from server.common import stamp,uid
from r3_support import Worker3


@pytest.mark.parametrize('acknowledged',[False,True])
@pytest.mark.parametrize('command_revision',[2,3])
def test_v3_to_v4_unconfirmed_control_fence(env,acknowledged,command_revision):
    w=Worker4(env,env.alice);w.confirm()
    with w.connect(w.hello(wireRevision=3)):
        with env.service.repo.transaction() as tx:
            tx.put(env.owner,'command','control',dict(commandId='control',_frame=dict(wireRevision=command_revision),status='accepted',deliveryState='acknowledged' if acknowledged else 'sent',controlResult=dict(outcome='unconfirmed',executionMayStillBeRunning=True,orphanProcessIds=['opaque'])),worker=w.worker,store=w.store)
    with w.connect():
        if acknowledged:
            assert w.ack['type']=='worker.hello_ack'
            with env.service.repo.transaction() as tx:assert tx.get(env.owner,'command','control')['controlResult']['executionMayStillBeRunning'] is True
        else:assert w.ack['error']['code']=='REMOTE_REVISION_REQUIRED'


def test_worker_cannot_upload_before_pending_or_after_reset(env,attachment_worker):
    import hashlib
    w=attachment_worker;data=b'local data';hash_=hashlib.sha256(data).hexdigest()
    h={'Cookie':'','Authorization':'Bearer '+w.secret,'Idempotency-Key':uid(),'Content-Type':'application/octet-stream','Content-Length':str(len(data)),
       'X-File-Name':'local.txt','X-Content-Sha256':hash_,'X-Worker-Store-Id':w.store,'X-Sync-Generation':'1','X-Local-Conversation-Id':'local','X-Local-Message-Id':'message','X-Local-Attachment-Id':'a'}
    assert env.client.post('/api/v2/worker/attachments',content=data,headers=h).json()['error']['code']=='ATTACHMENT_NOT_READY'
    w.emit(w.event('sync.reset',syncGeneration=2))
    assert env.client.post('/api/v2/worker/attachments',content=data,headers=h).json()['error']['code']=='REMOTE_SYNC_DISABLED'
    assert not list(env.service.attachments.store.cas.iterdir())


def test_cancel_preparation_evidence_is_projected_without_old_wire_event(env,attachment_worker):
    w=attachment_worker;w.send(w.conv);submit=w.receive();w.received(submit);w.receive()
    w.emit(w.event('command.accepted',commandId=submit['commandId'],conversationId=w.conv,receivedAt=stamp(env.clock()),status='accepted',resultRef=dict(runId='run',executionTaskId='task')))
    snapshot=env.alice.get('/conversations/'+w.conv+'/snapshot').json()['data']
    # run-ref is established by acceptance without fabricating a running task.
    with env.service.repo.transaction() as tx:run=tx.sync_lookup(env.owner,w.worker,w.store,'run','run')['public']
    tail=env.alice.get('/events').json()['data']['nextServerCursor']
    result=env.alice.post('/runs/'+run+'/commands',dict(action='cancel'));assert result.status_code==202,result.text
    cancel=w.receive();w.received(cancel);w.receive();w.accepted(cancel)
    control=dict(outcome='confirmed',executionMayStillBeRunning=False,orphanProcessIds=[],reason='preparation stopped',evidence='input_preparation_cancelled',observedAt=stamp(env.clock()))
    assert w.emit(w.event('command.completed',commandId=cancel['commandId'],conversationId=w.conv,resultStatus='confirmed',resultRef=dict(runId='run',executionTaskId='task'),controlResult=control))['type']=='worker.events_ack'
    view=env.alice.get('/commands/'+cancel['commandId']).json()['data'];assert view['controlResult']==control
    events=env.alice.get('/events?after='+tail).json()['data']['items']
    assert any(v['type']=='command.updated' and v['payload'].get('controlResult')==control for v in events)
    assert not any(v['type']=='worker.event' for v in events)
