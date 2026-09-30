import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from protocol.generated import python as dto

from conftest import FakeWorker, check_http
from r15_support import Worker2
from server import wire
from server.common import Fault, digest, stamp, uid
from server.security import COOKIE
from test_r15_policy import prepare_approval
from test_r15_replica import database_text


@pytest.fixture
def env(r15_env):
    with r15_env.service.repo.transaction() as tx:
        r15_env.owner = r15_env.service.security.session(tx, r15_env.alice.cookie)['owner']
    return r15_env


def issue(env, scopes=None, **fields):
    result = env.alice.post('/api-tokens', dict(name='automation', scopes=scopes or ['devices:read'], **fields))
    assert result.status_code == 201, result.text
    return result.json()['data']


def pat(env, secret, method='GET', path='/devices', body=None, **headers):
    auth = {'Cookie': '', 'Authorization': 'Bearer ' + secret, 'Idempotency-Key': uid(), **headers}
    result = env.client.request(method, '/api/v2' + path, json=body, headers=auth)
    check_http(result, method, '/api/v2' + path)
    return result


def patch(env, worker, version=1, key=None, **changes):
    return env.alice.request('PATCH', '/devices/' + worker.worker, dict(expectedVersion=version, **changes), key=key)


def owner(env):
    return env.owner


def test_device_filters_cursor_scope_stable_order_and_defaults(env):
    workers = [Worker2(env, env.alice) for _ in range(4)]
    for w in workers:
        assert w.confirm().json()['data']['version'] == 1
    patch(env, workers[1], remoteAccess='suspended')
    env.alice.post('/devices/' + workers[2].worker + '/revocations')
    with workers[0].connect():
        all_devices = env.alice.get('/devices').json()['data']['items']
        assert [v['workerId'] for v in all_devices] == [workers[i].worker for i in (0, 1, 3)]
        assert all(v['remoteAccess'] in {'enabled', 'suspended'} for v in all_devices)
        assert env.alice.get('/devices?online=true').json()['data']['items'][0]['workerId'] == workers[0].worker
        assert len(env.alice.get('/devices?online=false').json()['data']['items']) == 2
        assert len(env.alice.get('/devices?remoteAccess=suspended').json()['data']['items']) == 1
        assert len(env.alice.get('/devices?includeRevoked=true').json()['data']['items']) == 4
        first = env.alice.get('/devices?limit=1').json()['data']
        cursor = first['nextCursor']
        patch(env, workers[0], displayName='renamed')
        next_page = env.alice.get('/devices?includeRevoked=false&limit=3&cursor=' + cursor).json()['data']
        assert [v['workerId'] for v in next_page['items']] == [workers[1].worker, workers[3].worker]
        for actor, query in [(env.bob, ''), (env.alice, '&online=true'), (env.alice, '&includeRevoked=true')]:
            assert actor.get('/devices?cursor=' + cursor + query).json()['error']['code'] == 'REMOTE_CURSOR_INVALID'
        token = issue(env)['secret']
        assert pat(env, token, path='/devices?cursor=' + cursor).json()['error']['code'] == 'REMOTE_CURSOR_INVALID'
    assert env.alice.get('/devices?online=1').status_code == 422
    with env.service.repo.transaction() as tx:
        old = env.service.cursor(tx, owner(env), 'page:device:', 1)
    assert env.alice.get('/devices?cursor=' + old).json()['error']['code'] == 'REMOTE_CURSOR_EXPIRED'


def test_device_cas_idempotency_alias_lifecycle_and_stale_observation(env):
    w = Worker2(env, env.alice); w.confirm(); key = uid()
    with env.service.repo.transaction() as tx:
        stale = env.service.get(tx, owner(env), 'device', w.worker)
    first = patch(env, w, key=key, displayName='  desk  ', remoteAccess='suspended')
    assert first.status_code == 200
    view = first.json()['data']
    assert view['version'] == 2 and view['displayName'] == 'desk' and 'suspendedAt' in view
    assert patch(env, w, key=key, displayName='  desk  ', remoteAccess='suspended').json()['data'] == view
    assert patch(env, w, key=key, displayName='other').json()['error']['code'] == 'IDEMPOTENCY_MISMATCH'
    conflict = patch(env, w, displayName='new').json()['error']
    assert conflict['code'] == 'CONFLICT' and conflict['detail'] == dict(fields=['expectedVersion'], currentVersion=2)
    with env.service.repo.transaction() as tx:
        env.service.save(tx, owner(env), 'device', w.worker, stale)
    with w.connect():
        w.catalog(); w.busy()
        assert env.alice.get('/devices/' + w.worker).json()['data']['remoteAccess'] == 'suspended'
        assert patch(env, w, 2, displayName='desk').json()['data']['version'] == 2
        cleared = patch(env, w, 2, displayName='  ', remoteAccess='enabled').json()['data']
        assert cleared['version'] == 3 and 'displayName' not in cleared and 'suspendedAt' not in cleared
        assert cleared['deviceName'] == 'private-computer'
    assert env.bob.request('PATCH', '/devices/' + w.worker, dict(expectedVersion=3, displayName='x')).status_code == 404
    env.alice.post('/devices/' + w.worker + '/revocations')
    assert env.alice.get('/devices/' + w.worker).json()['data']['version'] == 4
    assert patch(env, w, key=key, displayName='  desk  ', remoteAccess='suspended').json()['error']['code'] == 'REMOTE_DEVICE_REVOKED'


def test_suspension_admission_exemptions_sync_and_resume(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); conv, approval = prepare_approval(w)
        run = env.alice.get('/conversations/' + conv + '/runs').json()['data']['items'][0]['runId']
        assert patch(env, w, remoteAccess='suspended').status_code == 200
        cases = [('POST', '/conversations', dict(targetWorkerId=w.worker, workerStoreId=w.store, title='x', workspaceId='ws', sceneId='scene', sceneVersion=1)),
                 ('PATCH', '/conversations/' + conv, dict(expectedVersion=1, title='x')),
                 ('POST', '/conversations/' + conv + '/messages', dict(clientMessageId=uid(), text='x', sessionMode='new')),
                 ('POST', '/approvals/' + approval + '/decisions', dict(decision='approve'))]
        cases += [('POST', '/runs/' + run + '/commands', dict(action=action)) for action in ('pause', 'resume', 'retry')]
        for method, path, body in cases:
            result = env.alice.request(method, path, body)
            assert result.status_code == 409 and result.json()['error']['code'] == 'REMOTE_DEVICE_SUSPENDED'
        # Freshness was never established; cancel/reject still flow through all gates.
        for path, body in [('/runs/' + run + '/commands', dict(action='cancel')), ('/approvals/' + approval + '/decisions', dict(decision='reject'))]:
            result = env.alice.post(path, body)
            assert result.status_code == 202, result.text
            frame = w.receive(); w.received(frame)
            assert w.receive()['type'] == 'command.delivery_granted'
            w.accept(frame)
        w.upsert(version=2, title='local still writes')
        assert w.emit(w.message('local', 'synchronization continues'))['type'] == 'worker.events_ack'
        w.busy()
        assert env.alice.get('/devices/' + w.worker).json()['data']['version'] == 2
        patch(env, w, 2, remoteAccess='enabled')
        assert w.send(conv)['status'] == 'queued'


@pytest.mark.parametrize('grant_first', [True, False])
def test_pause_grant_transaction_order_and_late_receipt(env, grant_first):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); conv = w.upsert(); w.busy()
        receipt = w.send(conv); frame = w.receive()
        if grant_first:
            w.received(frame); assert w.receive()['type'] == 'command.delivery_granted'
        assert patch(env, w, remoteAccess='suspended').status_code == 200
        if not grant_first:
            w.received(frame)
        current = env.alice.get('/commands/' + receipt['commandId']).json()['data']
        assert current['deliveryState'] == ('granted' if grant_first else 'acknowledged')
        if not grant_first:
            assert current['status'] == 'failed' and current['error']['code'] == 'REMOTE_DEVICE_SUSPENDED'
        with env.service.repo.transaction() as tx:
            grant = tx.get(owner(env), 'outbox', 'grant:' + receipt['commandId'])
            assert bool(grant) == grant_first
        patch(env, w, 2, remoteAccess='enabled')
        if not grant_first:
            assert env.alice.get('/commands/' + receipt['commandId']).json()['data']['status'] == 'failed'


def test_delete_erases_all_stores_bodies_staging_alias_and_credentials(env):
    w = Worker2(env, env.alice); w.confirm()
    marker = 'DELETE-ALL-CONTENT-7c21'
    with w.connect():
        w.catalog(); conv = w.upsert(title=marker); w.busy()
        patch(env, w, displayName=marker)
        w.emit(w.message('local', marker))
        w.emit(w.message('local', marker, sequence=2, parts=2))
        receipt = w.send(conv, marker); frame = w.receive()
        w.received(frame); w.receive()
        tail = env.alice.get('/events').json()['data']['nextServerCursor']
        with env.service.repo.transaction() as tx:
            tx.put(owner(env), 'message', 'historical-store', dict(text=marker), worker=w.worker, store='old-store', parent='old-conv')
        key = uid()
        deleted = env.alice.request('DELETE', '/devices/' + w.worker, key=key)
        assert deleted.status_code == 200 and deleted.json()['data']['executionMayStillBeRunning'] is True
        assert w.ws.receive()['code'] == 4403
    assert marker not in database_text(env)
    assert w.request_body['deviceName'] not in database_text(env)
    assert env.alice.get('/devices?includeRevoked=true').json()['data']['items'] == []
    for path in ['/devices/' + w.worker, '/devices/' + w.worker + '/catalog', '/conversations/' + conv,
                 '/conversations/' + conv + '/snapshot', '/commands/' + receipt['commandId'], '/conversations?workerId=' + w.worker]:
        assert env.alice.get(path).status_code == 404
    assert env.alice.request('DELETE', '/devices/' + w.worker, key=key).status_code == 404
    assert env.alice.request('DELETE', '/devices/' + w.worker).status_code == 404
    events = env.alice.get('/events?after=' + tail)
    assert events.status_code == 410 or events.json()['data']['items'] == []
    from starlette.testclient import WebSocketDenialResponse
    with pytest.raises(WebSocketDenialResponse) as error:
        with w.connect():
            pass
    assert error.value.status_code == 403
    assert w.register().json()['error']['code'] == 'REMOTE_PAIRING_CONFLICT'
    with env.service.repo.transaction() as tx:
        tombstone = tx.get(owner(env), 'command-tombstone', receipt['commandId'])
        assert tombstone['_granted'] is True
        assert tx.list(owner(env), 'sync-state', worker=w.worker) == []
        assert tx.list(owner(env), 'sync-stage', worker=w.worker) == []


def test_pat_issue_once_expiry_replay_metadata_and_no_plaintext(env, caplog):
    caplog.set_level('INFO', logger='hqremote')
    key = uid(); body = dict(name=' ops ', scopes=['devices:read', 'devices:manage'])
    first = env.alice.post('/api-tokens', body, key=key)
    secret = first.json()['data']['secret']; token = first.json()['data']['token']
    assert re.fullmatch(r'hqr_pat_[0-9a-f]{24}_[A-Za-z0-9_-]{43}', secret)
    assert token['name'] == 'ops' and token['status'] == 'active'
    assert 'lastUsedAt' not in token
    assert token['expiresAt'] == stamp(env.clock() + 90 * 86400)
    replay = env.alice.post('/api-tokens', body, key=key)
    assert replay.status_code == 200 and replay.json()['data'] == dict(token=token, secretAvailable=False)
    assert env.alice.post('/api-tokens', dict(body, name='different'), key=key).status_code == 409
    assert secret not in database_text(env) and secret not in caplog.text
    assert len(env.alice.get('/api-tokens').json()['data']['items']) == 1
    env.clock.advance(90 * 86400)
    assert pat(env, secret).json()['error']['code'] == 'REMOTE_API_TOKEN_EXPIRED'
    # New session, same owner; replay keeps the first expiry and never issues again.
    from conftest import Browser
    env.alice = Browser(env, 'alice')
    assert env.alice.post('/api-tokens', body, key=key).json()['data']['token']['status'] == 'expired'
    revoked = env.alice.request('DELETE', '/api-tokens/' + token['tokenId']).json()['data']
    assert revoked['status'] == 'revoked'
    assert pat(env, secret).json()['error']['code'] == 'REMOTE_API_TOKEN_INVALID'
    assert env.alice.request('DELETE', '/api-tokens/' + token['tokenId']).json()['data'] == revoked


@pytest.mark.parametrize('changes', [dict(name=' '), dict(scopes=['devices:read','devices:read']),
                                    dict(scopes=['devices:*']), dict(expiresAt='2020-01-01T00:00:00Z'),
                                    dict(expiresAt='2099-01-01T00:00:00Z')])
def test_pat_creation_constraints(env, changes):
    assert env.alice.post('/api-tokens', dict(name='valid', scopes=['devices:read'], **{} ) | changes).status_code == 422


def test_pat_scopes_authentication_revoke_and_idempotency_namespace(env):
    w = Worker2(env, env.alice); w.confirm()
    read = issue(env); manage = issue(env, ['devices:manage']); delete = issue(env, ['devices:delete'])
    assert pat(env, read['secret']).status_code == 200
    assert pat(env, manage['secret']).status_code == 403  # No scope inheritance.
    path = '/devices/' + w.worker
    assert pat(env, read['secret'], 'PATCH', path, dict(expectedVersion=1, displayName='x')).status_code == 403
    key = uid()
    body = dict(expectedVersion=1, displayName='managed')
    changed = pat(env, manage['secret'], 'PATCH', path, body, **{'Idempotency-Key': key, 'Origin': 'https://untrusted.invalid'})
    assert changed.status_code == 200  # No Cookie and no CSRF.
    assert pat(env, manage['secret'], 'PATCH', path, body, **{'Idempotency-Key': key}).json()['data'] == changed.json()['data']
    assert pat(env, manage['secret'], 'PATCH', path, body, **{'Idempotency-Key': ''}).status_code == 422
    other = issue(env, ['devices:manage'])
    assert pat(env, other['secret'], 'PATCH', path, body, **{'Idempotency-Key': key}).json()['error']['code'] == 'CONFLICT'
    assert env.bob.request('DELETE', '/api-tokens/' + read['token']['tokenId']).status_code == 404
    revoked = env.alice.request('DELETE', '/api-tokens/' + manage['token']['tokenId'])
    assert revoked.status_code == 200
    assert pat(env, manage['secret'], 'PATCH', path, body, **{'Idempotency-Key': key}).status_code == 401
    for method, route in [('GET','/api-tokens'), ('POST','/api-tokens'), ('DELETE','/api-tokens/' + read['token']['tokenId']),
                          ('GET','/auth/session'), ('POST','/auth/login'), ('GET','/conversations'), ('GET','/events'), ('GET','/openapi.json')]:
        assert pat(env, read['secret'], method, route).json()['error']['code'] == 'REMOTE_API_TOKEN_SCOPE_INSUFFICIENT'
    assert pat(env, delete['secret'], 'DELETE', path).status_code == 200
    assert pat(env, read['secret'], path=path).status_code == 404
    assert 'lastUsedAt' in env.alice.get('/api-tokens?includeRevoked=true').json()['data']['items'][0]


def test_ambiguous_identity_and_cookie_delete_csrf(env):
    w = Worker2(env, env.alice); w.confirm(); token = issue(env)['secret']
    for path in ['/devices', '/api-tokens', '/auth/session', '/openapi.json']:
        result = env.alice.request('GET', path, headers={'Authorization': 'Bearer ' + token})
        assert result.json()['error']['code'] == 'REMOTE_AUTH_AMBIGUOUS'
    for headers in [[('Authorization','Bearer '+token)] * 2,
                    [('Cookie', f'{COOKIE}={env.alice.cookie}; {COOKIE}={env.alice.cookie}')]]:
        assert env.client.get('/api/v2/devices', headers=headers).json()['error']['code'] == 'REMOTE_AUTH_AMBIGUOUS'
    for headers in [{'X-CSRF-Token':''}, {'Origin':'https://other.invalid'}]:
        assert env.alice.request('DELETE','/devices/'+w.worker,headers=headers).json()['error']['code'] == 'REMOTE_CSRF_REJECTED'
    result = env.client.post('/api/v2/worker/pairing-requests', json=w.request_body,
                            headers={'Cookie':'', 'Authorization':'Bearer '+token,'Idempotency-Key':uid()})
    assert result.json()['error']['code'] == 'REMOTE_DEVICE_AUTH_FAILED'


def test_request_ids_completion_logs_errors_and_openapi(env, caplog, monkeypatch):
    caplog.set_level('INFO', logger='hqremote')
    client_id = '12345678-1234-4234-9234-123456789abc'
    secret = issue(env)['secret']
    calls = [lambda: env.alice.get('/devices'),
             lambda: env.client.get('/api/v2/devices', headers={'Cookie':''}),
             lambda: env.alice.get('/devices?unknown=DO-NOT-LOG-THIS'),
             lambda: env.alice.get('/missing-path'),
             lambda: pat(env, secret, path='/api-tokens'),
             lambda: env.alice.request('GET','/devices',headers={'X-Client-Request-Id':'BAD-CLIENT-SECRET'}),
             lambda: env.alice.request('GET','/devices',headers={'X-Client-Request-Id':client_id,'X-Request-Id':'untrusted'}),
             lambda: env.client.get('/api/v2/openapi.json', headers={'Cookie':''})]
    for call in calls:
        caplog.clear(); result = call()
        identifier = result.headers['x-request-id']
        if 'requestId' in result.json():
            assert result.json()['requestId'] == identifier
        logs = [json.loads(r.message) for r in caplog.records if r.name == 'hqremote']
        assert len(logs) == 1 and logs[0]['requestId'] == identifier
        assert logs[0]['status'] == result.status_code and logs[0]['elapsedMs'] >= 0
        assert logs[0]['operation'] != 'devices'
        for private in [secret, env.alice.cookie, 'BAD-CLIENT-SECRET', 'DO-NOT-LOG-THIS']:
            assert private not in caplog.text
    root = Path(__file__).resolve().parents[3]
    assert result.json() == json.loads((root/'packages/protocol/openapi/remote-hub.v2.bundle.json').read_text(encoding='utf-8'))
    monkeypatch.setattr(env.service, 'devices', lambda *args: (_ for _ in ()).throw(RuntimeError('DO-NOT-LOG-THIS')))
    error = env.alice.get('/devices')
    assert error.status_code == 500 and error.headers['x-request-id'] == error.json()['requestId']
    assert 'DO-NOT-LOG-THIS' not in error.text + caplog.text


@pytest.mark.parametrize('revision', [1, 2])
def test_new_http_codes_cannot_enter_worker_error_domain(revision):
    frame = wire.encode(dict(type='worker.hello_rejected', error=Fault('REMOTE_DEVICE_SUSPENDED').view()), revision)
    assert frame['error']['code'] == 'INTERNAL'
    getattr(dto, 'RemoteServerOutboundFrame' if revision == 1 else 'RemoteV2ServerOutboundFrame').model_validate(frame)


def test_real_concurrent_pause_and_grant_have_one_transaction_order(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); conv = w.upsert(); w.busy()
        receipt = w.send(conv); frame = w.receive()
        event = w.event('command.received', commandId=frame['commandId'], conversationId=conv,
                        commandDigest=digest(frame), deliverBy=frame['deliverBy'], receivedAt=stamp(env.clock()))
        barrier = threading.Barrier(2)
        def grant():
            barrier.wait(timeout=3)
            with env.service.repo.transaction() as tx:
                env.service.received(tx, owner(env), event)
        def suspend():
            barrier.wait(timeout=3)
            with env.service.repo.transaction() as tx:
                return env.service.patch_device(tx, owner(env), w.worker, dict(expectedVersion=1, remoteAccess='suspended'))
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(grant), pool.submit(suspend)]
            for future in futures:
                future.result(timeout=5)
        with env.service.repo.transaction() as tx:
            value = tx.get(owner(env), 'command', receipt['commandId'])
            permission = tx.get(owner(env), 'outbox', 'grant:' + receipt['commandId'])
            assert bool(permission) == value['_granted']
            assert value['status'] == ('queued' if permission else 'failed')
            if not permission:
                assert value['error']['code'] == 'REMOTE_DEVICE_SUSPENDED'


def test_pause_closes_existing_safe_windows_but_new_reject_can_be_granted(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); conv, approval = prepare_approval(w)
        run = env.alice.get('/conversations/' + conv + '/runs').json()['data']['items'][0]['runId']
        cancel = env.alice.post('/runs/' + run + '/commands', dict(action='cancel')).json()['data']
        w.receive()
        key = uid(); path = '/approvals/' + approval + '/decisions'
        reject = env.alice.post(path, dict(decision='reject'), key=key).json()['data']
        old = w.receive()
        patch(env, w, remoteAccess='suspended')
        for command in [cancel, reject]:
            value = env.alice.get('/commands/' + command['commandId']).json()['data']
            assert value['status'] == 'failed' and value['error']['code'] == 'REMOTE_DEVICE_SUSPENDED'
        w.received(old)
        assert w.emit(w.event('command.rejected', commandId=old['commandId'], conversationId=conv,
                             receivedAt=stamp(env.clock()), status='rejected',
                             error=Fault('REMOTE_DELIVERY_EXPIRED').view()))['type'] == 'worker.events_ack'
        assert env.alice.post(path, dict(decision='reject'), key=key).json()['data']['commandId'] == reject['commandId']
        new = env.alice.post(path, dict(decision='reject')).json()['data']
        assert new['commandId'] != reject['commandId']
        frame = w.receive(); w.received(frame)
        assert w.receive()['type'] == 'command.delivery_granted'


def test_revoked_delete_cannot_resurrect_and_keeps_other_device(env):
    w = Worker2(env, env.alice); w.confirm()
    other = Worker2(env, env.alice); other.confirm()
    with env.service.repo.transaction() as tx:
        stale = env.service.get(tx, owner(env), 'device', w.worker)
    env.alice.post('/devices/' + w.worker + '/revocations')
    assert env.alice.request('DELETE', '/devices/' + w.worker).status_code == 200
    with env.service.repo.transaction() as tx:
        env.service.save(tx, owner(env), 'device', w.worker, stale)
    assert env.alice.get('/devices/' + w.worker).status_code == 404
    assert [v['workerId'] for v in env.alice.get('/devices').json()['data']['items']] == [other.worker]
    with other.connect():
        assert other.ack['type'] == 'worker.hello_ack'


def test_suspended_precedes_offline_freshness_and_revision_and_is_durable(env):
    w = FakeWorker(env, env.alice); w.confirm()
    body = dict(targetWorkerId=w.worker, workerStoreId=w.store, title='x', workspaceId='ws', sceneId='scene', sceneVersion=1)
    patch(env, w, remoteAccess='suspended')
    assert env.alice.post('/conversations', body).json()['error']['code'] == 'REMOTE_DEVICE_SUSPENDED'
    with w.connect():
        assert env.alice.post('/conversations', body).json()['error']['code'] == 'REMOTE_DEVICE_SUSPENDED'
    from server.repository import Repository
    from server.service_sync import SyncService
    reopened = Repository(env.settings.database)
    try:
        replacement = SyncService(reopened, env.settings, env.service.security)
        with reopened.transaction() as tx:
            device = replacement.get(tx, owner(env), 'device', w.worker)
            assert device['remoteAccess'] == 'suspended' and device['version'] == 2
            with pytest.raises(Fault, match='REMOTE_DEVICE_SUSPENDED'):
                replacement.ready(tx, owner(env), w.worker, w.store)
    finally:
        reopened.close()


def test_pat_list_pagination_filter_last_used_and_owner_isolation(env):
    issued = [issue(env) for _ in range(3)]
    env.alice.request('DELETE', '/api-tokens/' + issued[1]['token']['tokenId'])
    page = env.alice.get('/api-tokens?limit=1').json()['data']
    cursor = page['nextCursor']
    assert len(env.alice.get('/api-tokens?includeRevoked=true').json()['data']['items']) == 3
    assert env.alice.get('/api-tokens?includeRevoked=false&cursor=' + cursor).json()['data']['items'][0]['tokenId'] == issued[2]['token']['tokenId']
    for actor, suffix in [(env.bob, ''), (env.alice, '&includeRevoked=true')]:
        assert actor.get('/api-tokens?cursor=' + cursor + suffix).json()['error']['code'] == 'REMOTE_CURSOR_INVALID'
    assert env.bob.get('/api-tokens').json()['data']['items'] == []
    assert pat(env, issued[0]['secret'], path='/devices/unknown').status_code == 404
    used = env.alice.get('/api-tokens').json()['data']['items'][0]
    assert used['lastUsedAt'] == stamp(env.clock())  # Passed scope, business failed.
    token = issued[2]['secret']
    assert pat(env, token, 'PATCH', '/devices/unknown', dict(expectedVersion=1, displayName='x')).status_code == 403
    assert 'lastUsedAt' not in env.alice.get('/api-tokens').json()['data']['items'][1]


def test_pat_failed_auth_uses_source_bucket_and_request_id(env, caplog):
    caplog.set_level('INFO', logger='hqremote')
    env.settings.rate_limit = 2
    for _ in range(2):
        assert pat(env, 'hqr_pat_invalid_' + uid()).status_code == 401
    result = pat(env, 'hqr_pat_invalid_' + uid())
    assert result.status_code == 429
    assert result.headers['Retry-After'] == str(env.settings.rate_window)
    assert result.headers['x-request-id'] == result.json()['requestId']
    logs = [json.loads(r.message) for r in caplog.records if r.name == 'hqremote']
    assert logs[-1]['errorCode'] == 'REMOTE_RATE_LIMITED'


def test_validation_never_echoes_unknown_names_inputs_or_raw_exceptions(env):
    secret = 'PRIVATE-UNKNOWN-INPUT'
    result = env.alice.post('/api-tokens', dict(name='x', scopes=['devices:read'], **{secret: secret}))
    assert result.status_code == 422 and secret not in result.text
    for invalid in ['ABCDEF12-1234-4234-9234-123456789abc', '12345678-1234-1234-9234-123456789abc', secret]:
        response = env.alice.request('GET', '/devices', headers={'X-Client-Request-Id': invalid})
        assert response.status_code == 400 and response.json()['error']['code'] == 'BAD_REQUEST'
        assert invalid not in response.text


def test_packaged_error_mapping_matches_registry_and_guidance():
    import yaml
    from server.public_contract import HTTP_ERRORS
    root = Path(__file__).resolve().parents[3] / 'packages/protocol'
    errors = yaml.safe_load((root/'registry/error-codes.yaml').read_text(encoding='utf-8'))['errors']
    guidance = yaml.safe_load((root/'remote/http-error-guidance.yaml').read_text(encoding='utf-8'))['errors']
    assert set(HTTP_ERRORS) == {e['code'] for e in errors}
    for error in errors:
        fault = Fault(error['code'])
        assert fault.status == error['http'] and fault.retryable == error['retryable']
        assert fault.http_view()['message'] == guidance[error['code']]['message']


def test_publication_runs_from_standalone_package_without_checkout(tmp_path):
    import os
    import subprocess
    import sys
    import zipfile
    server_root = Path(__file__).resolve().parents[1]
    archive = tmp_path / 'server-release.zip'
    with zipfile.ZipFile(archive, 'w') as release:
        for path in (server_root/'server').rglob('*'):
            if path.suffix in {'.py', '.json'}:
                release.write(path, path.relative_to(server_root).as_posix())
    program = """import sys
sys.path.insert(0, sys.argv[1])
from server.public_contract import OPENAPI, HTTP_ERRORS
from server.app import ROUTES
assert OPENAPI['info']['version'] == '0.9.2'
assert len(ROUTES) == 39 and len(HTTP_ERRORS) == 81
print('standalone package publication: PASS')
"""
    env = dict(os.environ, PYTHONPATH='', PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, '-B', '-c', program, str(archive)], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'standalone package publication: PASS'


def test_pat_catalog_legacy_revocation_cross_owner_and_maximum_lifetime(env):
    w = Worker2(env, env.alice); w.confirm()
    token = issue(env, ['devices:read', 'devices:delete'], expiresAt=stamp(env.clock() + 365 * 86400))
    with w.connect():
        w.catalog()
        assert pat(env, token['secret'], path='/devices/' + w.worker + '/catalog').status_code == 200
    bob = Worker2(env, env.bob); bob.confirm()
    assert pat(env, token['secret'], path='/devices/' + bob.worker).status_code == 404
    assert pat(env, token['secret'], 'POST', '/devices/' + bob.worker + '/revocations', {}).status_code == 404
    revoked = pat(env, token['secret'], 'POST', '/devices/' + w.worker + '/revocations', {})
    assert revoked.status_code == 200
    assert pat(env, token['secret'], path='/devices/' + w.worker).json()['data']['status'] == 'revoked'
    assert pat(env, token['secret'], 'DELETE', '/devices/' + w.worker).status_code == 200


@pytest.mark.parametrize('revision', [1, 2])
def test_delete_dispatched_command_respects_wire_grant_semantics(env, revision):
    from server.service import Service
    w = (FakeWorker if revision == 1 else Worker2)(env, env.alice); w.confirm()
    with w.connect():
        w.catalog()
        if revision == 1:
            # Seed an authentic historical R1 delivery, not a new HTTP policy.
            with env.service.repo.transaction() as tx:
                conv = Service.create_conversation(env.service, tx, owner(env), dict(targetWorkerId=w.worker,
                    workerStoreId=w.store, title='legacy', workspaceId='ws', sceneId='scene', sceneVersion=1))
                receipt = Service.enqueue(env.service, tx, owner(env), conv, 'run.submit', dict(clientMessageId=uid(),
                    text='old in-flight body', sessionMode='new', workspaceId='ws', sceneId='scene', sceneVersion=1), stamp(env.clock() + 60), sequence=1)
        else:
            conv = w.upsert(); w.busy(); receipt = w.send(conv)
        frame = w.receive()
        assert frame['type'] == 'run.submit'
        assert env.alice.request('DELETE', '/devices/' + w.worker).status_code == 200
        with env.service.repo.transaction() as tx:
            value = tx.get(owner(env), 'command-tombstone', receipt['commandId'])
            if revision == 1:
                assert value['status'] == 'queued' and value['deliveryState'] == 'reconciliation_required'
                assert value['_dispatch'] and '_granted' not in value
            else:
                assert not value['_granted'] and value['status'] in {'failed', 'rejected'}
            assert tx.pending_outbox(owner(env), w.worker, w.store) == []
