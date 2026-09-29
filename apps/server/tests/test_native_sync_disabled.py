from concurrent.futures import ThreadPoolExecutor

import pytest

from r3_support import Worker3, native_page
from test_r15_replica import database_text


@pytest.fixture
def env(r15_env):
    with r15_env.service.repo.transaction() as tx:
        r15_env.owner = r15_env.service.security.session(tx, r15_env.alice.cookie)['owner']
    return r15_env


def routes(worker, identifier):
    return [f'/devices/{worker.worker}/native-sessions',
            f'/native-sessions/{identifier}', f'/native-sessions/{identifier}/messages']


def assert_disabled(env, paths):
    for path in paths:
        response = env.alice.get(path)
        assert response.status_code == 409
        assert response.json()['error'] == dict(code='REMOTE_SYNC_DISABLED', message='这台电脑已关闭同步', retryable=False)
        assert response.headers['x-request-id'] == response.json()['requestId']
        assert response.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('suspended', [False, True])
def test_sync_disabled_three_reads_offline_paused_and_backfill_restoration(env, suspended):
    worker = Worker3(env, env.alice)
    worker.confirm()
    with worker.connect():
        worker.catalog()
        index, original = worker.index(title='index-title-erased-by-reset')
        paths = routes(worker, index['nativeSessionId'])
        worker.emit(worker.event('sync.reset', syncGeneration=2))
        if suspended:
            assert env.alice.request('PATCH', f'/devices/{worker.worker}', dict(expectedVersion=1, remoteAccess='suspended')).status_code == 200
        assert_disabled(env, paths)
        assert 'index-title-erased-by-reset' not in database_text(env)
        with env.service.repo.transaction() as tx:
            assert tx.list(env.owner, 'native-index', worker=worker.worker) == []
            assert tx.sync_reverse(env.owner, 'native-index', index['nativeSessionId']) is not None
        # Owner and authentication always precede sync state; unknown IDs cannot
        # borrow the known device's disabled state even within the same account.
        for path in paths:
            assert env.bob.get(path).status_code == 404
            unauthenticated = env.client.get('/api/v2' + path, headers={'Cookie': ''})
            assert unauthenticated.status_code == 401
        for suffix in ('', '/messages'):
            assert env.alice.get('/native-sessions/unknown-native' + suffix).status_code == 404
        assert env.alice.get('/devices/unknown-worker/native-sessions').status_code == 404
    # Sync-disabled has priority over online query admission.
    assert_disabled(env, paths)
    with worker.connect(worker.hello(lastServerAck=dict(workerStoreId=worker.store, seq=worker.seq))):
        # A new enabled generation with an empty backfill is a real empty page;
        # the retained ID mapping alone must not recreate an index.
        marker = worker.event('sync.backfill.progress', syncGeneration=3, backfillId='reenabled', batchIndex=0,
                              batchEventCount=0, snapshotHighWater=worker.seq, complete=True)
        assert worker.emit(marker)['type'] == 'worker.events_ack'
        assert env.alice.get(paths[0]).json()['data'] == dict(items=[], hasMore=False)
        for path in paths[1:]:
            assert env.alice.get(path).status_code == 404
        assert worker.emit(worker.event('native.index.upserted', syncGeneration=3, payload=original['payload']))['type'] == 'worker.events_ack'
        restored = env.alice.get(paths[0]).json()['data']['items']
        assert restored[0]['nativeSessionId'] == index['nativeSessionId']
        assert env.alice.get(paths[1]).status_code == 200
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(env.alice.get, paths[2])
            query = worker.receive()
            worker.answer(query, native_page())
            assert pending.result(timeout=3).status_code == 200


def test_enabled_no_sessions_is_empty_and_unknown_ids_are_not_found(env):
    worker = Worker3(env, env.alice)
    worker.confirm()
    with worker.connect():
        worker.catalog()
        assert env.alice.get(f'/devices/{worker.worker}/native-sessions').json()['data'] == dict(items=[], hasMore=False)
        for suffix in ('', '/messages'):
            assert env.alice.get('/native-sessions/unknown-native' + suffix).status_code == 404


@pytest.mark.parametrize('remove', ['delete', 'missing'])
def test_deleted_or_missing_device_is_not_found_before_disabled(env, remove):
    worker = Worker3(env, env.alice)
    worker.confirm()
    with worker.connect():
        worker.catalog()
        index, _ = worker.index()
        worker.emit(worker.event('sync.reset', syncGeneration=2))
    if remove == 'delete':
        assert env.alice.request('DELETE', f'/devices/{worker.worker}').status_code == 200
    else:
        # Simulate a missing resource while its minimal identity mapping survives.
        with env.service.repo.transaction() as tx:
            tx.remove_record(env.owner, 'device', worker.worker)
    for path in routes(worker, index['nativeSessionId']):
        response = env.alice.get(path)
        assert response.status_code == 404 and response.json()['error']['code'] == 'NOT_FOUND'
