import sqlite3

import pytest
from protocol.generated import python as dto

from r15_support import Worker2
from server import wire
from server.common import Fault, stamp, uid
from server.repository import UnitOfWork
from test_r15_replica import database_text


@pytest.fixture
def env(r15_env):
    return r15_env


def prepare_approval(w):
    conv = w.upsert()
    w.emit(w.event('sync.run.state', syncGeneration=1, payload=dict(runId='run', conversationId='local', status='waiting_approval', observedAt=stamp(w.env.clock()))))
    approval = dict(approvalId='approval', resultRef=dict(runId='run'), action='git_push', targetSummary='deployment target', riskLevel='high', status='pending', requestedAt=stamp(w.env.clock()), expiresAt=stamp(w.env.clock() + 300), remoteApprovalAllowed=False, workerPolicyRevision=1)
    w.emit(w.event('approval.state_changed', conversationId='local', payload=approval))
    snap = w.browser.get('/conversations/' + conv + '/snapshot').json()['data']
    return conv, snap['approvals'][0]['approvalId']


def test_high_risk_approve_forbidden_reject_requires_grant_and_maps_ids(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); conv, approval = prepare_approval(w)
        assert approval != 'approval'
        assert env.alice.post('/approvals/' + approval + '/decisions', dict(decision='approve')).json()['error']['code'] == 'REMOTE_APPROVAL_FORBIDDEN'
        assert env.bob.post('/approvals/' + approval + '/decisions', dict(decision='reject')).status_code == 404
        result = env.alice.post('/approvals/' + approval + '/decisions', dict(decision='reject'))
        assert result.status_code == 202  # no busy snapshot is required for rejection
        frame = w.receive()
        assert frame['payload']['approvalId'] == 'approval' and frame['payload']['runId'] == 'run'
        w.received(frame); assert w.receive()['type'] == 'command.delivery_granted'
        w.accept(frame)
        w.emit(w.event('command.completed', commandId=frame['commandId'], conversationId=conv, resultStatus='approval_consumed', resultRef=dict(runId='run')))
        assert env.alice.get('/conversations/' + conv + '/snapshot').json()['data']['approvals'] == []


def test_grant_survives_disconnect_and_deadline_and_is_replayed_unchanged(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); conv = w.upsert(); w.busy()
        receipt = w.send(conv); frame = w.receive()
        w.received(frame)
        grant = w.receive()
    env.clock.advance(31)
    assert env.alice.get('/commands/' + receipt['commandId']).json()['data']['deliveryState'] == 'granted'
    with w.connect():
        assert w.receive() == grant
        # The original delivery frame remains immutable if replayed as reconciliation.
        repeated = w.receive()
        assert repeated == frame
        assert w.accept(frame)['type'] == 'worker.events_ack'
        assert env.alice.get('/commands/' + receipt['commandId']).json()['data']['status'] == 'accepted'


def test_offline_all_new_write_kinds_fail_and_never_create_attempt(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); conv, approval = prepare_approval(w); w.busy()
        run = env.alice.get('/conversations/' + conv + '/runs').json()['data']['items'][0]['runId']
    requests = [('POST', '/conversations', dict(targetWorkerId=w.worker, workerStoreId=w.store, title='offline', workspaceId='ws', sceneId='scene', sceneVersion=1)),
                ('PATCH', '/conversations/' + conv, dict(expectedVersion=1, title='offline')),
                ('POST', '/conversations/' + conv + '/messages', dict(clientMessageId=uid(), text='offline', sessionMode='new')),
                ('POST', '/runs/' + run + '/commands', dict(action='cancel')),
                ('POST', '/approvals/' + approval + '/decisions', dict(decision='reject'))]
    for method, path, body in requests:
        result = env.alice.request(method, path, body)
        assert result.status_code == 409 and result.json()['error']['code'] == 'REMOTE_DEVICE_OFFLINE'
    assert env.alice.get('/conversations/' + conv + '/commands').json()['data']['items'] == []


def test_duplicate_message_intent_creates_one_delivery_attempt(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); conv = w.upsert(); w.busy()
        body = dict(clientMessageId=uid(), text='one attempt', sessionMode='new')
        key = uid(); path = '/conversations/' + conv + '/messages'
        first = env.alice.post(path, body, key=key)
        assert first.status_code == 202
        assert env.alice.post(path, body, key=key).json()['data'] == first.json()['data']
        assert env.alice.post(path, body).json()['data'] == first.json()['data']
        assert env.alice.post(path, dict(body, text='changed'), key=key).status_code == 409
        assert len(env.alice.get('/conversations/' + conv + '/commands').json()['data']['items']) == 1
        assert env.alice.get('/conversations/' + conv + '/messages').json()['data']['items'] == []


def test_pending_noncontent_display_text_erased_before_contiguous_ack(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        conv = w.upsert()
        missing = w.message('local', 'body awaiting proof')
        event = w.event('approval.state_changed', conversationId='local', payload=dict(approvalId='a', resultRef=dict(runId='r'), action='delete', targetSummary='NONCONTENT-DISPLAY-SECRET', riskLevel='high', status='pending', requestedAt=stamp(env.clock()), expiresAt=stamp(env.clock() + 100), remoteApprovalAllowed=False, workerPolicyRevision=1))
        assert w.emit(event)['position']['seq'] == 1
        deletion = w.event('sync.reset', syncGeneration=2)
        assert w.emit(deletion)['position']['seq'] == 1
        assert 'NONCONTENT-DISPLAY-SECRET' not in database_text(env)
        from server.common import digest
        proof = dict(type='sync.content.redaction', wireRevision=2, redactionId=uid(), workerId=w.worker, workerStoreId=w.store, workerEpoch=w.epoch, syncGeneration=2, deletionEventId=deletion['eventId'], deletionSeq=deletion['seq'], slots=[dict(seq=missing['seq'], eventId=missing['eventId'], eventSha256=digest(missing), originalType=missing['type'])])
        assert w.emit(proof)['position']['seq'] == deletion['seq']
        assert 'NONCONTENT-DISPLAY-SECRET' not in database_text(env)


def test_storage_resource_failure_rolls_back_and_keeps_retry_position(env, monkeypatch):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        conv = w.upsert()
        frame = w.message('local', 'retryable content')
        with monkeypatch.context() as patch:
            def full(*args, **kwargs):
                error = sqlite3.OperationalError('full')
                error.sqlite_errorcode = sqlite3.SQLITE_FULL
                raise error
            patch.setattr(UnitOfWork, 'sync_part', full)
            assert w.emit(frame)['error']['code'] == 'REMOTE_SYNC_RESOURCE_LIMIT'
        assert env.alice.get('/conversations/' + conv + '/messages').json()['data']['items'] == []
    with w.connect():
        assert w.ack['lastServerAck']['seq'] == 1
        assert w.emit(frame)['position']['seq'] == 2


def test_wire_one_error_domain_and_no_frame_rewriting():
    with pytest.raises(Fault, match='REMOTE_PROTOCOL_UNSUPPORTED'):
        wire.encode(dict(type='server.heartbeat', wireRevision=1, connectionId='c', receivedAt='2026-09-27T00:00:00Z'), 2)
    rejected = wire.encode(dict(type='worker.hello_rejected', error=Fault('REMOTE_SYNC_CONFLICT').view()), 1)
    dto.RemoteServerOutboundFrame.model_validate(rejected)
    assert rejected['error']['code'] == 'INTERNAL' and rejected['supportedWireRevisions'] == [1, 2, 3, 4, 5]


def test_late_received_without_a_prior_timer_transaction_cannot_get_grant(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); conv = w.upsert(); w.busy()
        receipt = w.send(conv); frame = w.receive()
        env.clock.advance(30)
        w.received(frame)
        with env.service.repo.transaction() as tx:
            owner = env.service.security.session(tx, env.alice.cookie)['owner']
            value = tx.get(owner, 'command', receipt['commandId'])
            assert value['status'] == 'failed' and not value['_granted']
            assert value['error']['code'] == 'REMOTE_DELIVERY_EXPIRED'
            assert tx.get(owner, 'outbox', 'grant:' + frame['commandId']) is None


def test_safe_integer_segment_count_does_not_allocate_unbounded_resources(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        conv = w.upsert()
        event = w.message('local', 'x', parts=2**53 - 1)
        assert w.emit(event)['error']['code'] == 'REMOTE_SYNC_RESOURCE_LIMIT'
        assert env.alice.get('/conversations/' + conv + '/messages').json()['data']['items'] == []
