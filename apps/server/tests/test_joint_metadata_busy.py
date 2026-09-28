import pytest

from r15_support import Worker2
from server.common import stamp, uid


@pytest.fixture
def env(r15_env):
    return r15_env


def owner(env):
    with env.service.repo.transaction() as tx:
        return env.service.security.session(tx, env.alice.cookie)['owner']


def test_activity_timestamp_advances_without_changing_metadata_cas_and_cannot_regress(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        conv = w.upsert(); original = env.alice.get('/conversations/' + conv).json()['data']
        created = original['createdAt']
        env.clock.advance(1)
        w.upsert(createdAt=created)
        advanced = env.alice.get('/conversations/' + conv).json()['data']
        assert advanced['metadataVersion'] == original['metadataVersion'] == 1
        assert advanced['updatedAt'] > original['updatedAt']
        w.upsert(createdAt=created, updatedAt=original['updatedAt'])
        assert env.alice.get('/conversations/' + conv).json()['data']['updatedAt'] == advanced['updatedAt']
        w.upsert(version=2, title='real metadata edit', createdAt=created)
        value = env.alice.get('/conversations/' + conv).json()['data']
        assert value['metadataVersion'] == 2 and value['title'] == 'real metadata edit'


@pytest.mark.parametrize('field,value', [('title', 'bad'), ('visibility', 'mobile_only'),
    ('archived', True), ('workspaceId', 'other'), ('sceneId', 'other'), ('authority', 'remote')])
def test_same_metadata_version_still_rejects_real_metadata_changes(env, field, value):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        conv = w.upsert()
        original = env.alice.get('/conversations/' + conv).json()['data']
        payload = {k: original[k] for k in ('workspaceId', 'sceneId', 'sceneVersion', 'title',
            'createdAt', 'updatedAt', 'archived', 'visibility', 'metadataVersion', 'authority')}
        env.clock.advance(1)
        payload.update(conversationId='local', updatedAt=stamp(env.clock()))
        payload[field] = value
        error = w.emit(w.event('sync.conversation.upserted', syncGeneration=1, payload=payload))
        assert error['error']['code'] == 'REMOTE_SYNC_CONFLICT'
        assert env.alice.get('/conversations/' + conv).json()['data'][field] == original[field]


def views(env, conv):
    return [env.alice.get('/conversations/' + conv).json()['data'],
            env.alice.get('/conversations').json()['data']['items'][0],
            env.alice.get('/conversations/' + conv + '/snapshot').json()['data']['conversation']]


@pytest.mark.parametrize('loss', ['disconnect', 'timeout', 'freeze', 'partial'])
def test_stale_busy_is_false_in_views_and_event_replay(env, loss):
    w = Worker2(env, env.alice); w.confirm()
    cursor = env.alice.get('/events').json()['data']['nextServerCursor']
    with w.connect():
        conv = w.upsert(); w.busy(['local'])
        assert all(v['busy'] and v['busyFresh'] for v in views(env, conv))
        fresh_events = env.alice.get('/events?after=' + cursor).json()['data']['items']
        assert any(e['type'] == 'conversation.updated' and e['payload'].get('busy') for e in fresh_events)
        if loss == 'timeout':
            env.clock.advance(46)
        elif loss == 'freeze':
            account = owner(env)
            with env.service.repo.transaction() as tx:
                device = env.service.get(tx, account, 'device', w.worker)
                env.service.freeze(tx, account, device, 'REMOTE_STORE_CHANGED')
        elif loss == 'partial':
            w.busy(['local'], snapshotId=uid(), partCount=2)
        if loss != 'disconnect':
            assert all(not v['busy'] and not v['busyFresh'] for v in views(env, conv))
    assert all(not v['busy'] and not v['busyFresh'] for v in views(env, conv))
    events = env.alice.get('/events?after=' + cursor).json()['data']['items']
    changed = [e['payload'] for e in events if e['type'] == 'conversation.updated']
    assert changed and all(not v['busy'] and not v['busyFresh'] for v in changed)
    assert env.alice.get('/devices/' + w.worker).json()['data']['busySnapshotFresh'] is False


def test_disconnect_emits_busy_invalidation_after_previously_consumed_cursor(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        conv = w.upsert(); w.busy(['local'])
        cursor = env.alice.get('/events').json()['data']['nextServerCursor']
    result = env.alice.get('/events?after=' + cursor).json()['data']
    assert any(e['type'] == 'conversation.updated' and e['payload']['conversationId'] == conv
               and e['payload']['busy'] is False and e['payload']['busyFresh'] is False for e in result['items'])
