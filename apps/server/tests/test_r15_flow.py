import pytest

from r15_support import Worker2
from server.common import stamp, uid


@pytest.fixture
def env(r15_env):
    return r15_env


def test_copy_upsert_message_and_offline_failure(env):
    w = Worker2(env, env.alice); w.confirm()
    tail = env.alice.get('/events').json()['data']['nextServerCursor']
    with w.connect():
        assert w.ack['wireRevision'] == 2 and w.ack['commandDelivery'] == 'ready'
        w.catalog()
        conv = w.upsert()
        w.busy()
        assert w.emit(w.message('local', 'whole computer answer'))['type'] == 'worker.events_ack'
        data = env.alice.get('/conversations/' + conv + '/messages').json()['data']
        assert data['items'][0]['text'] == 'whole computer answer'
        assert env.alice.get('/conversations/' + conv).json()['data']['busyFresh'] is True
    failed = env.alice.post('/conversations/' + conv + '/messages', dict(clientMessageId=uid(), text='never queued', sessionMode='continue'))
    assert failed.status_code == 409 and failed.json()['error']['code'] == 'REMOTE_DEVICE_OFFLINE'
    assert env.alice.get('/conversations/' + conv + '/commands').json()['data']['items'] == []
    events = env.alice.get('/events?after=' + tail).json()['data']['items']
    assert any(e['type'] == 'conversation.updated' and e['payload']['conversationId'] == conv for e in events)


def test_create_by_grant_then_sync_and_update_by_grant(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); w.busy()
        body = dict(targetWorkerId=w.worker, workerStoreId=w.store, title='new title', workspaceId='ws', sceneId='scene', sceneVersion=1)
        receipt = env.alice.post('/conversations', body)
        assert receipt.status_code == 202
        conv = receipt.json()['data']['conversationId']
        assert env.alice.get('/conversations/' + conv).status_code == 404
        frame = w.receive(); assert frame['type'] == 'conversation.create'
        w.received(frame)
        grant = w.receive(); assert grant['type'] == 'command.delivery_granted'
        assert w.accept(frame)['type'] == 'worker.events_ack'
        assert w.upsert(frame['localConversationId'], title='new title') == conv
        control = dict(outcome='confirmed', executionMayStillBeRunning=False, orphanProcessIds=[], reason='committed', evidence='metadata_committed', observedAt=stamp(env.clock()))
        assert w.emit(w.event('command.completed', commandId=frame['commandId'], conversationId=conv, resultStatus='confirmed', controlResult=control))['type'] == 'worker.events_ack'
        result = env.alice.request('PATCH', '/conversations/' + conv, dict(expectedVersion=1, title='changed'))
        assert result.status_code == 202
        assert env.alice.get('/conversations/' + conv).json()['data']['title'] == 'new title'
        update = w.receive(); assert update['payload']['conversationId'] == frame['localConversationId']
        w.received(update); assert w.receive()['type'] == 'command.delivery_granted'
        w.accept(update)
        w.upsert(frame['localConversationId'], version=2, title='changed')
        assert env.alice.get('/conversations/' + conv).json()['data']['title'] == 'changed'


@pytest.mark.parametrize('grant_first', [True, False])
def test_delivery_deadline_transaction_race(env, grant_first):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); conv = w.upsert(); w.busy()
        receipt = w.send(conv)
        frame = w.receive()
        if grant_first:
            w.received(frame)
            assert w.receive()['type'] == 'command.delivery_granted'
        env.clock.advance(30)
        view = env.alice.get('/commands/' + receipt['commandId']).json()['data']
        if grant_first:
            assert view['status'] == 'queued' and view['deliveryState'] == 'granted'
            assert w.accept(frame)['type'] == 'worker.events_ack'
            assert env.alice.get('/commands/' + receipt['commandId']).json()['data']['status'] == 'accepted'
        else:
            assert view['status'] == 'failed' and view['error']['code'] == 'REMOTE_DELIVERY_EXPIRED'
            w.received(frame)
            with env.service.repo.transaction() as tx:
                owner = env.service.security.session(tx, env.alice.cookie)['owner']
                assert tx.get(owner, 'outbox', 'grant:' + frame['commandId']) is None


def test_busy_snapshot_freshness_and_empty_replacement(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); conv = w.upsert()
        body = dict(clientMessageId=uid(), text='wait', sessionMode='new')
        assert env.alice.post('/conversations/' + conv + '/messages', body).json()['error']['code'] == 'REMOTE_STATE_NOT_READY'
        w.busy(['local'])
        assert env.alice.post('/conversations/' + conv + '/messages', body).json()['error']['code'] == 'REMOTE_CONVERSATION_BUSY'
        w.busy([])
        assert env.alice.get('/conversations/' + conv).json()['data']['busy'] is False
    with w.connect():
        assert env.alice.get('/conversations/' + conv).json()['data']['busyFresh'] is False
        snapshot = uid()
        w.busy(['local'], snapshotId=snapshot, partCount=2)
        assert env.alice.get('/conversations/' + conv).json()['data']['busyFresh'] is False
        w.busy([], snapshotId=snapshot, partCount=2, partIndex=1)
        assert env.alice.get('/conversations/' + conv).json()['data']['busyFresh'] is True
