import hashlib
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from api.app import create_application
from core.local_auth import COOKIE_NAME, LocalBrowserAuth
from runtime import pair
from runtime.paths import HubPaths


@pytest.fixture
def wall_clock(monkeypatch):
    clock = [2_000_000_000.0]
    monkeypatch.setattr('core.local_auth.time.time', lambda: clock[0])
    return clock


def exchange(auth):
    return auth.exchange(auth.issue_code())


def rows(path):
    with sqlite3.connect(path) as database:
        return database.execute('SELECT digest, expires_at FROM browser_sessions').fetchall()


def test_restart_digest_only_and_expired_startup_cleanup(tmp_path, wall_clock):
    path = tmp_path / 'sessions.db'
    auth = LocalBrowserAuth(storage_path=path)
    secret = exchange(auth)
    assert rows(path) == [(hashlib.sha256(secret.encode()).hexdigest(), wall_clock[0] + 30 * 86400)]
    assert secret.encode() not in path.read_bytes()
    if os.name != 'nt':
        assert path.stat().st_mode & 0o777 == 0o600
    auth.close()
    restored = LocalBrowserAuth(storage_path=path)
    assert restored.valid(secret)
    restored.close()
    wall_clock[0] += 30 * 86400
    expired = LocalBrowserAuth(storage_path=path)
    assert not expired.valid(secret)
    assert rows(path) == []
    expired.close()


def test_renewal_is_durable_and_throttled(tmp_path, wall_clock):
    path = tmp_path / 'sessions.db'
    auth = LocalBrowserAuth(storage_path=path)
    secret = exchange(auth)
    original = rows(path)
    changes = auth._database.total_changes
    for _ in range(100):
        wall_clock[0] += 30
        assert auth.valid(secret)
    assert rows(path) == original
    assert auth._database.total_changes == changes
    wall_clock[0] += 600
    assert auth.valid(secret)
    assert auth._database.total_changes == changes + 1
    assert rows(path)[0][1] == wall_clock[0] + 30 * 86400
    auth.close()
    wall_clock[0] = original[0][1] + 1
    restored = LocalBrowserAuth(storage_path=path)
    assert restored.valid(secret)  # Survives original expiry after durable renewal.
    restored.close()


def test_logout_and_revoke_all_are_persistent_across_instances(tmp_path, wall_clock):
    path = tmp_path / 'sessions.db'
    first = LocalBrowserAuth(storage_path=path)
    one, two = exchange(first), exchange(first)
    second = LocalBrowserAuth(storage_path=path)
    second.logout(one)
    assert not first.valid(one)
    assert first.valid(two)
    second.revoke_sessions()
    assert not first.valid(two)
    assert rows(path) == []
    first.close()
    second.close()


@pytest.mark.parametrize('restart', [False, True])
def test_clock_rollback_invalidates_instead_of_extending(tmp_path, wall_clock, restart):
    path = tmp_path / 'sessions.db'
    auth = LocalBrowserAuth(storage_path=path)
    secret = exchange(auth)
    wall_clock[0] -= 60
    if restart:
        auth.close()
        auth = LocalBrowserAuth(storage_path=path)
    assert not auth.valid(secret)
    assert rows(path) == []
    auth.close()


def test_twenty_session_cap_evicts_oldest_even_if_renewed(tmp_path, wall_clock):
    path = tmp_path / 'sessions.db'
    auth = LocalBrowserAuth(storage_path=path)
    secrets = [exchange(auth) for _ in range(20)]
    wall_clock[0] += 3600
    assert auth.valid(secrets[0])
    newest = exchange(auth)
    assert not auth.valid(secrets[0])
    assert all(auth.valid(secret) for secret in secrets[1:] + [newest])
    assert len(rows(path)) == 20
    auth.close()


def make_hub(path):
    return create_application(paths=HubPaths.resolve(path), token='operator-private',
                              allowed_hosts={'testserver'}, allowed_origins={'https://testserver'},
                              environment='test')


def test_http_restart_renewal_logout_and_operator_revocation(tmp_path, wall_clock):
    origin = {'Origin': 'https://testserver'}
    hub = make_hub(tmp_path)
    with TestClient(hub.app, base_url='https://testserver') as client:
        login = client.post('/api/v2/auth/local-session',
                            json={'code': hub.local_auth.issue_code()}, headers=origin)
        cookie_header = login.headers['set-cookie']
        assert 'Max-Age=2592000' in cookie_header
        assert all(attribute in cookie_header for attribute in ['HttpOnly', 'SameSite=strict', 'Secure', 'Path=/'])
        secret = client.cookies.get(COOKIE_NAME)
    hub = make_hub(tmp_path)
    with TestClient(hub.app, base_url='https://testserver') as client:
        client.cookies.set(COOKIE_NAME, secret)
        assert client.get('/api/v2/auth/status').json()['data']['authenticated']
        wall_clock[0] += 3600
        renewed = client.get('/api/v2/conversations')
        assert renewed.status_code == 200
        assert 'Max-Age=2592000' in renewed.headers['set-cookie']
        assert renewed.headers['cache-control'] == 'no-store'
        assert secret not in renewed.text and 'operator-private' not in renewed.text
        endpoint = '/internal/auth/revoke-sessions'
        assert client.post(endpoint, headers=origin).status_code == 401
        revoked = client.post(endpoint, headers={'Authorization': 'Bearer operator-private'})
        assert revoked.status_code == 200
        assert not client.get('/api/v2/auth/status').json()['data']['authenticated']
        assert client.get('/api/v2/conversations').status_code == 401
        client.cookies.clear()
        client.post('/api/v2/auth/local-session', json={'code': hub.local_auth.issue_code()}, headers=origin)
        logout = client.post('/api/v2/auth/logout', headers=origin)
        assert logout.status_code == 200
        assert 'Max-Age=0' in logout.headers['set-cookie']
        assert not client.get('/api/v2/auth/status').json()['data']['authenticated']
    assert rows(tmp_path / 'data' / 'browser-sessions.db') == []


def test_revoke_cli_uses_operator_endpoint_without_terminal_secrets(monkeypatch, capsys, tmp_path):
    calls = []
    monkeypatch.setattr(pair, '_operator_request',
                        lambda data_dir, endpoint: (calls.append((data_dir, endpoint)) or ('unused', {'revoked': True})))
    monkeypatch.setattr('sys.argv', ['pair', '--data-dir', str(tmp_path), '--revoke-sessions'])
    monkeypatch.setattr(pair.sys.stdout, 'isatty', lambda: False)
    pair.main()
    assert calls == [(tmp_path, '/internal/auth/revoke-sessions')]
    assert '已撤销' in capsys.readouterr().out
