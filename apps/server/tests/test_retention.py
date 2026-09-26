import json
import secrets
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.common import stamp
from server.config import Settings
from server.repository import MIGRATIONS, Repository, SCHEMA_VERSION


def owner_of(env, browser):
    with env.service.repo.transaction() as tx:
        return env.service.security.session(tx, browser.cookie)['owner']


def test_retention_expires_old_boundary_and_empty_tail_snapshot_recovers(env, paired):
    env.settings.browser_retention_seconds = 5
    owner = owner_of(env, env.alice)
    command = paired.send(paired.conv)
    old = env.alice.get('/conversations/' + paired.conv + '/snapshot').json()['data']['serverCursor']
    with env.service.repo.transaction() as tx:
        tail_before = tx.browser_tail(owner)
        inbox_before = tx.db.execute('SELECT COUNT(*) FROM inbox WHERE owner=?', (owner,)).fetchone()[0]
    env.clock.advance(6)
    # No request-path pruning: still usable until low-frequency maintenance commits.
    assert env.alice.get('/events?after=' + old).status_code == 200
    env.service.maintain()
    assert env.alice.get('/events?after=' + old).json()['error']['code'] == 'REMOTE_CURSOR_EXPIRED'
    snapshot = env.alice.get('/conversations/' + paired.conv + '/snapshot').json()['data']
    fresh = snapshot['serverCursor']
    assert env.alice.get('/events?after=' + fresh).status_code == 200
    assert snapshot['commands'][0]['commandId'] == command['commandId']
    assert len(snapshot['messages']) == 1
    with env.service.repo.transaction() as tx:
        assert tx.browser_after(owner, 0, 100) == []
        assert tx.browser_tail(owner) == tail_before  # never resets to zero
        assert tx.db.execute('SELECT COUNT(*) FROM inbox WHERE owner=?', (owner,)).fetchone()[0] == inbox_before
        assert tx.get(owner, 'outbox', 'command:' + command['commandId']) is not None
    paired.send(paired.conv, text='after cleanup')
    assert len(env.alice.get('/events?after=' + fresh).json()['data']['items']) == 2


def test_partial_retention_and_owner_isolation(env, paired):
    env.settings.browser_retention_seconds = 5
    old = env.alice.get('/events').json()['data']['nextServerCursor']
    env.clock.advance(4)
    paired.send(paired.conv)
    page = env.alice.get('/events?after=' + old + '&limit=1').json()['data']
    retained = page['nextServerCursor']
    bob_cursor = env.bob.get('/events').json()['data']['nextServerCursor']
    env.clock.advance(2)
    env.service.maintain()
    assert env.alice.get('/events?after=' + old).status_code == 410
    assert env.alice.get('/events?after=' + retained).json()['data']['hasMore'] is False
    assert len(env.alice.get('/events?after=' + retained).json()['data']['items']) == 1
    assert env.bob.get('/events?after=' + bob_cursor).status_code == 200
    assert env.bob.get('/events?after=' + retained).json()['error']['code'] == 'REMOTE_CURSOR_INVALID'


def test_cleanup_sessions_rates_legacy_cursors_preserves_dedup_and_accounts(env, paired):
    owner = owner_of(env, env.alice)
    now = env.clock()
    with env.service.repo.transaction() as tx:
        tx.auth_put('session:expired', dict(expires=now - 1), owner)
        tx.auth_put('session:live', dict(expires=now + 100), owner)
        tx.auth_put('rate:expired', dict(until=now - 1))
        tx.auth_put('rate:live', dict(until=now + 100))
        tx.put(owner, 'cursor', 'legacy', dict(expires=now + 99999))
        tx.put(owner, 'message-intent', 'preserve', dict(content='dedup', receipt={}))
    env.service.maintain()
    with env.service.repo.transaction() as tx:
        assert tx.auth_get('session:expired') is None and tx.auth_get('rate:expired') is None
        assert tx.auth_get('session:live') is not None and tx.auth_get('rate:live') is not None
        assert tx.get(owner, 'cursor', 'legacy') is None
        assert tx.get(owner, 'message-intent', 'preserve') is not None
        assert len(tx.auth_list('account:')) == 2
    assert env.alice.get('/auth/session').json()['data']['authenticated']


def test_auth_replay_after_cleaned_session_remains_generic(env):
    browser = env.alice
    login = browser.post('/auth/login', dict(loginName='alice', password='test-only-password-very-long'), key='retention-login')
    assert login.status_code == 200
    env.clock.advance(env.settings.session_ttl + 1)
    env.service.maintain()
    result = browser.post('/auth/login', dict(loginName='alice', password='test-only-password-very-long'), key='retention-login')
    assert result.status_code == 401 and result.json()['error']['code'] == 'REMOTE_AUTH_REQUIRED'


def test_migrations_backfill_indexes_and_retention_without_rewriting_business_data(tmp_path):
    path = tmp_path / 'legacy.sqlite3'
    body = dict(status='queued', expiresAt=stamp(100))
    event = dict(eventId='event', workerId='worker', workerStoreId='store', seq=1)
    with sqlite3.connect(path) as db:
        db.executescript(MIGRATIONS[1] + '\nPRAGMA user_version=1;')
        db.execute('INSERT INTO auth VALUES(?,?,?)', ('session:expired', 'owner', json.dumps(dict(expires=100))))
        for kind, identifier, record in [('command', 'cmd', body), ('outbox', 'done', dict(done=True)), ('cursor', 'legacy', {})]:
            db.execute('INSERT INTO records(owner,kind,id,worker,store,parent,body) VALUES(?,?,?,?,?,?,?)', ('owner', kind, identifier, 'worker', 'store', 'conv', json.dumps(record)))
        db.execute('INSERT INTO inbox(owner,worker,store,event_id,first_seq,last_seq,body) VALUES(?,?,?,?,?,?,?)', ('owner', 'worker', 'store', 'event', 1, 1, json.dumps(event)))
        db.execute('INSERT INTO browser_outbox(owner,body) VALUES(?,?)', ('owner', json.dumps(dict(recordedAt=stamp(100)))))
    repo = Repository(path)
    try:
        repo.migrate()  # idempotent on current schema
        with repo.transaction() as tx:
            assert tx.db.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION
            assert tx.queued_due('owner', 'worker', 101) == [body]
            assert tx.pending_outbox('owner', 'worker', 'store') == []
            tx.cleanup_auth(101)
            tx.cleanup_owner('owner', 101)
            assert tx.auth_get('session:expired') is None
            assert tx.list('owner', 'cursor') == []
            assert tx.browser_tail('owner') == 1
            assert tx.browser_retention('owner')['generation'] == 1
            assert tx.event_id('owner', 'event') == event
            assert tx.get('owner', 'command', 'cmd') == body
            assert tx.get('owner', 'outbox', 'done') == dict(done=True)
    finally:
        repo.close()


def test_periodic_cleanup_runs_without_http_requests(tmp_path, monkeypatch):
    monkeypatch.setattr('server.app.MAINTENANCE_INTERVAL', 0.05)
    settings = Settings(tmp_path / 'periodic.sqlite3', secrets.token_bytes(32), browser_retention_seconds=5)
    app = create_app(settings)
    service = app.state.service
    with service.repo.transaction() as tx:
        tx.auth_put('account:test', dict(owner='owner'), 'owner')
        tx.put('owner', 'cursor', 'old', {})
        tx.browser_add('owner', dict(recordedAt=stamp(settings.clock() - 10)))
    with TestClient(app):
        deadline = time.monotonic() + 2
        while True:
            with service.repo.transaction() as tx:
                cleaned = tx.get('owner', 'cursor', 'old') is None and not tx.browser_after('owner', 0, 10)
            if cleaned:
                break
            assert time.monotonic() < deadline
            time.sleep(0.02)


def test_retention_configuration_default_and_override(tmp_path, monkeypatch):
    assert Settings(tmp_path / 'db', b'x' * 32).browser_retention_seconds == 7 * 86400
    monkeypatch.setenv('HQREMOTE_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HQREMOTE_BROWSER_RETENTION_SECONDS', '120')
    assert Settings.from_env().browser_retention_seconds == 120
    with pytest.raises(ValueError):
        Settings(tmp_path / 'db', b'x' * 32, browser_retention_seconds=0)
