import pytest

from r15_support import Worker2
from server.common import stamp, uid
from test_r15_replica import database_text


@pytest.fixture
def env(r15_env):
    return r15_env


def test_reset_retains_dedup_without_text_and_never_regrants_old_intent(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); conv = w.upsert(); w.busy()
        key = uid(); body = dict(clientMessageId=uid(), text='private-granted-original-body', sessionMode='new')
        path = '/conversations/' + conv + '/messages'
        receipt = env.alice.post(path, body, key=key).json()['data']
        frame = w.receive(); w.received(frame); permission = w.receive()
        assert permission['type'] == 'command.delivery_granted'
        reset = w.event('sync.reset', syncGeneration=2)
        assert w.emit(reset)['type'] == 'worker.events_ack'
        assert body['text'] not in database_text(env)
        assert w.upsert(generation=3) == conv
        w.busy()
        assert env.alice.post(path, body, key=key).status_code == 404
        assert env.alice.post(path, body).status_code == 404
        with env.service.repo.transaction() as tx:
            owner = env.service.security.session(tx, env.alice.cookie)['owner']
            command = tx.get(owner, 'command', receipt['commandId'])
            assert command['_granted'] and command['_deleted']
            assert tx.get(owner, 'outbox', 'grant:' + frame['commandId'])['_frame'] == permission
            assert len(tx.list(owner, 'command', parent=conv)) == 1


def test_ungranted_reset_retires_order_slot_and_old_message_never_reappears(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); conv = w.upsert(); w.busy()
        receipt = w.send(conv, text='ungranted-private-body')
        frame = w.receive()
        assert w.emit(w.event('sync.reset', syncGeneration=2))['type'] == 'worker.events_ack'
        assert 'ungranted-private-body' not in database_text(env)
        w.upsert(generation=3); w.busy()
        skip = next(s for s in w.skips if s['commandId'] == receipt['commandId'])
        assert skip['conversationSeq'] == 1
        assert w.emit(w.event('conversation.skip_recorded', commandId=skip['commandId'], conversationId=conv, conversationSeq=1))['type'] == 'worker.events_ack'
        next_receipt = w.send(conv, text='new explicit request')
        next_frame = w.receive()
        assert next_receipt['conversationSeq'] == next_frame['conversationSeq'] == 2
        w.received(frame)
        with env.service.repo.transaction() as tx:
            owner = env.service.security.session(tx, env.alice.cookie)['owner']
            assert tx.get(owner, 'outbox', 'grant:' + frame['commandId']) is None


def test_deadline_expired_idempotency_key_reports_expiry_not_queued_again(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); conv = w.upsert(); w.busy()
        key = uid(); body = dict(clientMessageId=uid(), text='timeout', sessionMode='new')
        path = '/conversations/' + conv + '/messages'
        receipt = env.alice.post(path, body, key=key).json()['data']
        w.receive(); env.clock.advance(30)
        assert env.alice.get('/commands/' + receipt['commandId']).json()['data']['status'] == 'failed'
        assert env.alice.post(path, body, key=key).json()['error']['code'] == 'REMOTE_DELIVERY_EXPIRED'


def test_message_cursor_cannot_mix_generations_after_reset(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        conv = w.upsert()
        for n in (1, 2):
            w.emit(w.message('local', 'old-' + str(n), message=str(n), sequence=n))
        page = env.alice.get('/conversations/' + conv + '/messages?limit=1').json()['data']
        w.emit(w.event('sync.reset', syncGeneration=2))
        w.upsert(generation=3)
        w.emit(w.message('local', 'new', generation=3, message='1', sequence=1))
        result = env.alice.get('/conversations/' + conv + '/messages?before=' + page['before'])
        assert result.status_code == 410 and result.json()['error']['code'] == 'REMOTE_CURSOR_EXPIRED'
