import base64
import copy

import pytest
from protocol.generated import python as dto

from server.common import digest, stamp
from test_pi_projection import Worker5, catalog, env, prepare


def seed_run(worker, local, run):
    event = worker.event('sync.run.state', syncGeneration=1, payload=dict(
        runId=run, conversationId=local, status='waiting_approval', observedAt=stamp(worker.env.clock())))
    assert worker.emit(event)['type'] == 'worker.events_ack'


def approval(worker, local, run, identifier='approval', status='pending', **changes):
    payload = dict(approvalId=identifier, resultRef=dict(runId=run), action='network',
                   targetSummary='safe summary', riskLevel='low', status=status,
                   requestedAt=stamp(worker.env.clock()), expiresAt=stamp(worker.env.clock()+120),
                   remoteApprovalAllowed=True, workerPolicyRevision=1)
    payload.update(changes)
    return worker.event('approval.state_changed', conversationId=local, payload=payload)


def cursor(browser):
    return browser.get('/events').json()['data']['nextServerCursor']


def page(browser, token, limit=100):
    return browser.get('/events?after='+token+'&limit='+str(limit))


@pytest.mark.parametrize('status', ['pending', 'approved', 'rejected', 'expired'])
@pytest.mark.parametrize('with_feature', [False, True])
def test_non_pi_approval_is_realtime_legacy_shape(env, status, with_feature):
    w = Worker5(env, env.pi)
    w.confirm()
    browser = env.pi if with_feature else env.alice
    with w.connect():
        normal, _ = prepare(w)
        seed_run(w, 'normal', 'normal-run')
        token = cursor(browser)
        event = approval(w, 'normal', 'normal-run', status=status)
        original = copy.deepcopy(event)
        assert w.emit(event)['position']['seq'] == event['seq']
        result = page(browser, token).json()['data']
        assert len(result['items']) == 1
        projected = result['items'][0]
        dto.RemoteBrowserLegacyApprovalEvent.model_validate(projected)
        dto.RemoteBrowserV2WorkerEvent.model_validate(projected)  # Frozen old browser branch.
        frame = projected['payload']
        assert frame['type'] == 'approval.state_changed' and frame['wireRevision'] == 2
        assert frame['conversationId'] == normal and frame['payload']['status'] == status
        assert frame['payload']['approvalId'] != 'approval' and frame['payload']['resultRef']['runId'] != 'normal-run'
        for key in ('eventId','workerId','workerStoreId','workerEpoch','seq','occurredAt'):
            assert frame[key] == event[key]
        assert event == original and event['wireRevision'] == 5
        with env.service.repo.transaction() as tx:
            owner = env.service.security.session(tx,env.alice.cookie)['owner']
            stored = tx.sync_entry(owner,w.worker,w.store,event_id=event['eventId'])
            assert stored['event_hash'] == digest(original) and stored['applied'] == 1
        view = browser.get('/approvals/'+frame['payload']['approvalId']).json()['data']
        assert view['status'] == status
        snapshot = browser.get('/conversations/'+normal+'/snapshot').json()['data']
        assert bool(snapshot['approvals']) == (status == 'pending')
        # Reconnect/retry with the same cursor replays facts, not newly forged IDs.
        assert page(browser, token).json()['data']['items'][0]['payload'] == frame


def test_mixed_pi_and_non_pi_approvals_no_hidden_hints_or_ids(env):
    w = Worker5(env, env.pi)
    w.confirm()
    with w.connect():
        normal, pi = prepare(w)
        seed_run(w,'normal','normal-run')
        seed_run(w,'pi-local','pi-run')
        old, new, other = cursor(env.alice), cursor(env.pi), cursor(env.bob)
        for n in range(4):
            assert w.emit(approval(w,'pi-local','pi-run',identifier='hidden-'+str(n),
                                   remoteApprovalAllowed=False,denialCode='PI_TOOL_CALL_BLOCKED'))['type']=='worker.events_ack'
        hidden = page(env.alice,old,1).json()['data']
        assert hidden['items']==[] and not hidden['hasMore']
        assert set(hidden)=={'items','hasMore','nextServerCursor'}
        assert hidden['nextServerCursor'] != old
        assert w.emit(approval(w,'normal','normal-run',identifier='visible'))['type']=='worker.events_ack'
        mixed = page(env.pi,new).json()['data']['items']
        assert len(mixed)==5
        for item in mixed[:4]:
            dto.RemoteBrowserPiApprovalEvent.model_validate(item)
            assert item['payload']['conversationId']==pi
            assert item['payload']['payload']['denialCode']=='PI_TOOL_CALL_BLOCKED'
        dto.RemoteBrowserLegacyApprovalEvent.model_validate(mixed[-1])
        old_page = page(env.alice,old,1).json()['data']
        assert len(old_page['items'])==1 and not old_page['hasMore']
        assert old_page['items'][0]['payload']['conversationId']==normal
        assert page(env.bob,other).json()['data']['items']==[]
        assert page(env.alice,new).json()['error']['code']=='REMOTE_CURSOR_INVALID'


def test_denial_projection_does_not_change_authoritative_reason(env):
    w = Worker5(env,env.pi)
    w.confirm()
    with w.connect():
        normal,_ = prepare(w)
        seed_run(w,'normal','run')
        token = cursor(env.alice)
        event = approval(w,'normal','run',remoteApprovalAllowed=False,denialCode='ATTACHMENT_NOT_READY')
        assert w.emit(event)['type']=='worker.events_ack'
        projected = page(env.alice,token).json()['data']['items'][0]['payload']['payload']
        assert projected['denialCode']=='REMOTE_APPROVAL_FORBIDDEN'
        assert projected['remoteApprovalAllowed'] is False
        identifier=projected['approvalId']
        assert env.alice.get('/approvals/'+identifier).json()['data']['denialCode']=='ATTACHMENT_NOT_READY'
        assert env.alice.get('/conversations/'+normal+'/snapshot').json()['data']['approvals'][0]['denialCode']=='ATTACHMENT_NOT_READY'
        assert env.alice.post('/approvals/'+identifier+'/decisions',dict(decision='approve')).status_code==403
        assert env.alice.post('/approvals/'+identifier+'/decisions',dict(decision='reject')).status_code==202
        assert w.receive()['payload']['approvalId']=='approval'


def test_inconsistent_approval_fact_rejected_without_ack_or_projection(env):
    w = Worker5(env,env.pi)
    w.confirm()
    with w.connect():
        normal,_ = prepare(w)
        seed_run(w,'normal','run')
        token = cursor(env.alice)
        invalid = approval(w,'normal','run',remoteApprovalAllowed=True,denialCode='REMOTE_APPROVAL_FORBIDDEN')
        assert w.emit(invalid)['error']['code']=='REMOTE_EVENT_CONFLICT'
        # Disconnect can legitimately publish busyFresh=false. It must not
        # publish the rejected approval or acknowledge its reliable slot.
        assert not any(item['type']=='worker.event' for item in page(env.alice,token).json()['data']['items'])
        with env.service.repo.transaction() as tx:
            owner=env.service.security.session(tx,env.alice.cookie)['owner']
            assert tx.sync_entry(owner,w.worker,w.store,event_id=invalid['eventId']) is None
        assert env.alice.get('/conversations/'+normal+'/snapshot').json()['data']['approvals']==[]


def test_snapshot_fallback_is_after_filter_and_recovers_at_applied_tail(env):
    w = Worker5(env,env.pi)
    w.confirm()
    with w.connect():
        normal,pi = prepare(w)
        seed_run(w,'normal','run')
        seed_run(w,'pi-local','pi-run')
        old,new = cursor(env.alice),cursor(env.pi)
        # A migrated/unrepresentable browser record is not a new Worker frame.
        with env.service.repo.transaction() as tx:
            owner=env.service.security.session(tx,env.alice.cookie)['owner']
            env.service.browser_events.emit(tx,owner,dict(workerId=w.worker,workerStoreId=w.store),{},pi=True,conversation=pi)
        assert page(env.alice,old).json()['data']['items']==[]
        assert page(env.pi,new).json()['error']['code']=='REMOTE_CURSOR_EXPIRED'
        event=approval(w,'normal','run')
        assert w.emit(event)['type']=='worker.events_ack'
        with env.service.repo.transaction() as tx:
            env.service.browser_events.emit(tx,owner,dict(workerId=w.worker,workerStoreId=w.store),{},conversation=normal)
        assert page(env.alice,old).status_code==410
        snapshot=env.alice.get('/conversations/'+normal+'/snapshot').json()['data']
        assert len(snapshot['approvals'])==1
        assert page(env.alice,snapshot['serverCursor']).json()['data']['items']==[]
        w.emit(approval(w,'normal','run',status='rejected'))
        result=page(env.alice,snapshot['serverCursor']).json()['data']['items']
        assert len(result)==1 and result[0]['payload']['payload']['status']=='rejected'


def test_progress_and_pi_only_catalog_busy_changes(env):
    w=Worker5(env,env.pi)
    w.confirm()
    with w.connect():
        normal,pi=prepare(w)
        seed_run(w,'normal','run')
        old,new=cursor(env.alice),cursor(env.pi)
        changed=catalog(w)
        changed['runtimes'][0]['guard']['checkedAt']=stamp(env.clock()+1)
        w.catalog(capabilityRevision=2,**changed)
        w.busy(['pi-local'])
        assert page(env.alice,old).json()['data']['items']==[]
        assert page(env.pi,new).json()['data']['items']
        token=cursor(env.alice)
        w.emit(w.event('run.progress',conversationId='normal',resultRef=dict(runId='run'),message='safe progress'))
        item=page(env.alice,token).json()['data']['items'][0]
        dto.RemoteBrowserV2WorkerEvent.model_validate(item)
        assert item['payload']['wireRevision']==2 and item['payload']['message']=='safe progress'


def test_server_cursor_has_no_plaintext_position_and_is_authenticated(env):
    first=cursor(env.alice)
    second=cursor(env.alice)
    assert first!=second and len(first)==len(second)
    version,nonce,payload,tag=first.split('.')
    assert version=='e1'
    ciphertext=base64.urlsafe_b64decode(payload+'='*(-len(payload)%4))
    assert len(ciphertext)==512 and b'position' not in ciphertext
    tampered='.'.join([version,nonce,payload,('0' if tag[0]!='0' else '1')+tag[1:]])
    assert page(env.alice,tampered).json()['error']['code']=='REMOTE_CURSOR_INVALID'
    assert page(env.bob,first).json()['error']['code']=='REMOTE_CURSOR_INVALID'
    assert page(env.pi,first).json()['error']['code']=='REMOTE_CURSOR_INVALID'


def test_hidden_deleted_and_mismatched_approval_references(env):
    w=Worker5(env,env.pi)
    w.confirm()
    with w.connect():
        normal,pi=prepare(w)
        seed_run(w,'normal','normal-run')
        seed_run(w,'pi-local','pi-run')
        old,new=cursor(env.alice),cursor(env.pi)
        w.upsert('normal',version=2,visibility='pc_only')
        assert w.emit(approval(w,'normal','normal-run'))['type']=='worker.events_ack'
        for browser,token in [(env.alice,old),(env.pi,new)]:
            records=page(browser,token).json()['data']['items']
            assert not any(r['type']=='worker.event' for r in records)
        w.upsert('normal',version=3)
        w.emit(approval(w,'normal','normal-run'))
        old=cursor(env.alice)
        mismatch=approval(w,'normal','pi-run',identifier='wrong-reference')
        assert w.emit(mismatch)['error']['code']=='REMOTE_TARGET_MISMATCH'
        assert not any(r['type']=='worker.event' for r in page(env.alice,old).json()['data']['items'])


def test_pending_and_terminals_replay_after_reconnect_and_public_id_approve(env):
    w=Worker5(env,env.pi)
    w.confirm()
    with w.connect():
        normal,_=prepare(w)
        seed_run(w,'normal','run')
        token=cursor(env.alice)
        w.emit(approval(w,'normal','run'))
        event=page(env.alice,token).json()['data']['items'][0]
        identifier=event['payload']['payload']['approvalId']
    with w.connect(w.hello(lastServerAck=dict(workerStoreId=w.store,seq=w.seq))):
        replay=page(env.alice,token).json()['data']['items']
        assert any(r.get('payload')==event['payload'] for r in replay)
        result=env.alice.post('/approvals/'+identifier+'/decisions',dict(decision='approve'))
        assert result.status_code==202
        command=w.receive()
        assert command['payload']['approvalId']=='approval' and command['wireRevision']==5
        token=cursor(env.alice)
        w.emit(approval(w,'normal','run',status='approved'))
        records=page(env.alice,token).json()['data']['items']
        assert records[0]['payload']['payload']['status']=='approved'


def test_unknown_runtime_binding_never_published_as_non_pi(env):
    w=Worker5(env,env.pi)
    w.confirm()
    with w.connect():
        w.catalog()  # No declared instance/type evidence for the scenario roles.
        conv=w.upsert('unknown')
        seed_run(w,'unknown','run')
        old,new=cursor(env.alice),cursor(env.pi)
        w.emit(approval(w,'unknown','run'))
        assert page(env.alice,old).json()['data']['items']==[]
        assert env.alice.get('/conversations/'+conv).status_code==404
        records=page(env.pi,new).json()['data']['items']
        assert len(records)==1 and records[0]['payload']['wireRevision']==5


@pytest.mark.parametrize('status', ['pending','approved','rejected','expired'])
def test_pi_approval_states_use_new_variant_only(env,status):
    w=Worker5(env,env.pi)
    w.confirm()
    with w.connect():
        _,pi=prepare(w)
        seed_run(w,'pi-local','run')
        old,new=cursor(env.alice),cursor(env.pi)
        w.emit(approval(w,'pi-local','run',status=status,remoteApprovalAllowed=False,denialCode='PI_TOOL_CALL_BLOCKED'))
        assert page(env.alice,old).json()['data']['items']==[]
        records=page(env.pi,new).json()['data']['items']
        assert len(records)==1
        dto.RemoteBrowserPiApprovalEvent.model_validate(records[0])
        assert records[0]['payload']['payload']['status']==status
        assert records[0]['payload']['payload']['denialCode']=='PI_TOOL_CALL_BLOCKED'


def test_deleted_conversation_cannot_replay_approval_body(env):
    w=Worker5(env,env.pi)
    w.confirm()
    with w.connect():
        normal,_=prepare(w)
        seed_run(w,'normal','run')
        token=cursor(env.alice)
        w.emit(approval(w,'normal','run',targetSummary='APPROVAL-ERASE-MARKER'))
        w.emit(w.event('sync.conversation.deleted',syncGeneration=1,conversationId='normal',deletedAt=stamp(env.clock())))
        response=page(env.alice,token)
        assert response.status_code==200 and 'APPROVAL-ERASE-MARKER' not in response.text
        assert not any(r['type']=='worker.event' for r in response.json()['data']['items'])
        assert env.alice.get('/conversations/'+normal+'/snapshot').status_code==404
