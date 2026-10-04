import json
from pathlib import Path

import pytest
from protocol.generated import python as dto

from server import wire
from server.common import Fault, stamp, uid
from test_pi_projection import Worker5, env, catalog, prepare


@pytest.mark.parametrize('observed', [False, True])
def test_four_to_five_control_fence_preserves_uncertainty(env, observed):
    w=Worker5(env,env.pi);w.confirm()
    with w.connect(w.hello(wireRevision=4)):
        with env.service.repo.transaction() as tx:
            owner=env.service.security.session(tx,env.alice.cookie)['owner']
            tx.put(owner,'command','legacy-control',dict(_frame=dict(wireRevision=4),status='accepted',deliveryState='acknowledged' if observed else 'sent',controlResult=dict(outcome='unconfirmed',executionMayStillBeRunning=True,orphanProcessIds=['unresolved'])),worker=w.worker,store=w.store)
    with w.connect():
        if not observed:
            assert w.ack['error']['code']=='REMOTE_REVISION_REQUIRED'
        else:
            assert w.ack['type']=='worker.hello_ack' and w.ack['wireRevision']==5
            with env.service.repo.transaction() as tx:
                assert tx.get(owner,'command','legacy-control')['controlResult']['executionMayStillBeRunning']
                device=tx.get(owner,'device',w.worker)
                assert device['_upgradeAck']==device['_upgradeWorkerAck']==0


@pytest.mark.parametrize('revision',[1,2,3,4])
def test_old_codecs_reject_pi_error_and_native_enum(revision):
    fault=wire.encode(dict(type='worker.hello_rejected',error=Fault('PI_TOOL_CALL_BLOCKED').view()),revision)
    assert fault['error']['code']=='INTERNAL' and fault['supportedWireRevisions']==[1,2,3,4,5]
    root=Path(__file__).resolve().parents[3]/'packages/protocol/fixtures/contracts'
    pi=json.loads((root/'pi.RemoteV5NativeIndexUpserted.json').read_text(encoding='utf-8'))
    pi['wireRevision']=revision
    with pytest.raises(Fault):wire.decode(json.dumps(pi),revision)


def test_all_frozen_worker_fixtures_keep_generated_validation():
    root=Path(__file__).resolve().parents[3]/'packages/protocol/fixtures/contracts'
    checked={1:0,2:0,3:0,4:0}
    for path in root.glob('*.json'):
        frame=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(frame,dict) or frame.get('wireRevision') not in checked or 'type' not in frame:
            continue
        revision=frame['wireRevision']
        try:
            getattr(dto,wire.CODECS[revision][0]).model_validate(frame)
        except ValueError:
            continue  # The fixture may be a server frame or a non-frame aggregate.
        decoded=wire.decode(json.dumps(frame),revision)
        assert decoded['wireRevision']==revision and decoded['type']==frame['type']
        checked[revision]+=1
    assert all(count>5 for count in checked.values()), checked


def test_pi_admission_requires_five_after_downgrade(env):
    w=Worker5(env,env.pi);w.confirm()
    with w.connect():
        _,pi=prepare(w)
    with w.connect(w.hello(wireRevision=4,lastServerAck=dict(workerStoreId=w.store,seq=w.seq))):
        assert w.ack['type']=='worker.hello_ack'
        result=env.pi.post('/conversations/'+pi+'/messages',dict(clientMessageId=uid(),text='must not downgrade',sessionMode='new'))
        assert result.json()['error']['code']=='REMOTE_REVISION_REQUIRED'
        # A new old-line event cannot inject a PI message into a known PI copy.
        frame=w.message('pi-local','must not sync on four');frame['wireRevision']=4
        w.ws.send_json(frame)
        assert w.receive()['error']['code']=='REMOTE_REVISION_REQUIRED'


def test_pi_guard_failure_and_async_error_projection(env):
    w=Worker5(env,env.pi);w.confirm()
    with w.connect():
        _,pi=prepare(w)
        body=dict(clientMessageId=uid(),text='hello',sessionMode='new')
        pending=env.pi.post('/conversations/'+pi+'/messages',body)
        assert pending.status_code==202
        command=w.receive();assert command['wireRevision']==5
        w.received(command);assert w.receive()['type']=='command.delivery_granted'
        w.accepted(command)
        assert w.emit(w.event('command.failed',commandId=command['commandId'],conversationId=pi,resultStatus='failed',error=Fault('PI_TOOL_CALL_BLOCKED').view()))['type']=='worker.events_ack'
        view=env.pi.get('/commands/'+command['commandId']).json()['data']
        assert view['error']['code']=='PI_TOOL_CALL_BLOCKED'
        assert env.alice.get('/commands/'+command['commandId']).status_code==404
        changed=catalog(w);changed['runtimes'][0].pop('guard')
        assert w.catalog(capabilityRevision=2,**changed)['type']=='worker.events_ack'
        rejected=env.pi.post('/conversations/'+pi+'/messages',dict(body,clientMessageId=uid()))
        assert rejected.json()['error']['code']=='PI_GUARD_UNAVAILABLE'
