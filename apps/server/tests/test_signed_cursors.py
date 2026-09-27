import base64
import json

import pytest

from server.common import Fault, canonical


def test_stateless_poll_and_page_cursors_do_not_accumulate_records(env, paired):
    paired.send(paired.conv)
    paired.send(paired.conv)
    cursor = env.alice.get('/events').json()['data']['nextServerCursor']
    for _ in range(40):
        cursor = env.alice.get('/events?after=' + cursor).json()['data']['nextServerCursor']
        page = env.alice.get('/conversations/' + paired.conv + '/messages?limit=1').json()['data']
        assert page['hasMore']
        assert env.alice.get('/conversations/' + paired.conv + '/messages?cursor=' + page['nextCursor']).status_code == 200
    with env.service.repo.transaction() as tx:
        owner = env.service.security.session(tx, env.alice.cookie)['owner']
        assert tx.list(owner, 'cursor') == []


@pytest.mark.parametrize('field,value', [('position', 100), ('expiresAt', 9999999999999), ('scope', 'page:device:')])
def test_tampered_cursor_rejected(env, field, value):
    cursor = env.alice.get('/events').json()['data']['nextServerCursor']
    version, payload, signature = cursor.split('.')
    claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    claims[field] = value
    payload = base64.urlsafe_b64encode(canonical(claims).encode()).decode().rstrip('=')
    result = env.alice.get('/events?after=' + '.'.join([version, payload, signature]))
    assert result.json()['error']['code'] == 'REMOTE_CURSOR_INVALID'


def test_cursor_owner_scope_expiry_and_no_repository_dependency(env):
    with env.service.repo.transaction() as tx:
        owner = env.service.security.session(tx, env.alice.cookie)['owner']
    # No repository methods are required to issue or authenticate a cursor.
    token = env.service.cursor(None, owner, 'events', 123)
    assert env.service.position(None, owner, 'events', token) == 123
    for candidate_owner, scope in [('other-owner', 'events'), (owner, 'page:device:')]:
        with pytest.raises(Fault, match='REMOTE_CURSOR_INVALID'):
            env.service.position(None, candidate_owner, scope, token)
    assert env.bob.get('/events?after=' + token).json()['error']['code'] == 'REMOTE_CURSOR_INVALID'
    env.clock.advance(env.settings.cursor_ttl + 1)
    with pytest.raises(Fault, match='REMOTE_CURSOR_EXPIRED'):
        env.service.position(None, owner, 'events', token)
    for malformed in ['legacy-random-cursor', 'c1.bad.bad', 'c1.' + 'x' * 2100]:
        with pytest.raises(Fault, match='REMOTE_CURSOR_INVALID'):
            env.service.position(None, owner, 'events', malformed)
