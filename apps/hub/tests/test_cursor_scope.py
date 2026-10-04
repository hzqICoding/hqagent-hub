import hashlib

import pytest
from protocol.generated.python import CreateLocalConversationInput

from api.pi_projection import CURSOR_SCOPE_CAPACITY, cursor_scope
from core.errors import HubError
from storage.events import EventDraft
from storage.local_chat import now


def features(headers, enabled):
    return {**headers, **({'X-HQ-Client-Features': 'pi-v1'} if enabled else {})}


def owner(headers):
    return hashlib.sha256(headers['Authorization'].encode()).hexdigest()


def seed_events(hub, count=3):
    with hub.database.transaction() as tx:
        return [hub.events.append(tx, EventDraft('system', 'cursor-test', 'agent.progress', {'index': n}))[0]
                for n in range(count)]


def test_message_after_is_not_an_event_cursor_or_a_scope_registration(client, hub, auth_headers):
    conversation = hub.local_chat.repository.create_conversation(CreateLocalConversationInput(
        title='message sequence', workspaceId='workspace', sceneId='analyze'), 'create')
    with hub.database.transaction() as tx:
        for sequence in (1, 2):
            tx.connection.execute('INSERT INTO local_messages VALUES(?,?,?,?,?,?,?)',
                (f'message-{sequence}', conversation.id, sequence, 'user', 'synthetic', None, now()))
    scopes = hub.app.state.remote_worker.pi.cursor_scopes
    modern = features(auth_headers, True)
    response = client.get(f'/api/v2/conversations/{conversation.id}/messages?after=1', headers=modern)
    assert response.status_code == 200, response.text
    assert [m['sequence'] for m in response.json()['data']] == [2]
    assert not scopes
    events = seed_events(hub)
    assert client.get('/api/v2/events?after=0', headers=auth_headers).status_code == 200
    before = list(scopes.items())
    assert client.get(f'/api/v2/conversations/{conversation.id}/messages?after=1', headers=modern).status_code == 200
    assert list(scopes.items()) == before
    # Ignoring message sequences must not reset a known event capability switch.
    changed = client.get(f'/api/v2/events?after={events[-1].seq}', headers=modern)
    assert changed.status_code == 410


@pytest.mark.parametrize('version', ['v1', 'v2'])
@pytest.mark.parametrize('enabled', [False, True])
def test_first_positive_event_cursor_registers_unknown_owner(client, hub, auth_headers, version, enabled):
    events = seed_events(hub)
    response = client.get(f'/api/{version}/events?after={events[0].seq}', headers=features(auth_headers, enabled))
    assert response.status_code == 200, response.text
    assert [item['seq'] for item in response.json()['data']['events']] == [e.seq for e in events[1:]]
    assert hub.app.state.remote_worker.pi.cursor_scopes[owner(auth_headers)] is enabled


@pytest.mark.parametrize('version', ['v1', 'v2'])
@pytest.mark.parametrize('previous', [False, True])
def test_known_feature_switch_expires_with_recovery_watermarks(client, hub, auth_headers, version, previous):
    events = seed_events(hub)
    initial, changed = features(auth_headers, previous), features(auth_headers, not previous)
    assert client.get(f'/api/{version}/events?after=0', headers=initial).status_code == 200
    path = f'/api/{version}/events?after={events[0].seq}'
    for _ in range(2):
        response = client.get(path, headers=changed)
        assert response.status_code == 410
        error = response.json()['error']
        assert error['code'] == 'EVENT_CURSOR_EXPIRED'
        assert error['detail'] == hub.events.cursor_expired_detail(f'/api/{version}/bootstrap')
        assert error['detail']['latestSeq'] == events[-1].seq
        assert error['detail']['oldestAvailableSeq'] == events[0].seq
        assert hub.app.state.remote_worker.pi.cursor_scopes[owner(auth_headers)] is previous
    # Snapshot query extras do not turn bootstrap into a cursor-consumption request.
    assert client.get(f'/api/{version}/bootstrap?after=999', headers=changed).status_code == 200
    resumed = client.get(f'/api/{version}/events?after={events[-1].seq}', headers=changed)
    assert resumed.status_code == 200


def test_scope_lru_evicts_one_oldest_and_touches_active_owners(hub):
    visibility = hub.app.state.remote_worker.pi
    for index in range(CURSOR_SCOPE_CAPACITY):
        cursor_scope(visibility, f'owner-{index}', False, 1)
    cursor_scope(visibility, 'owner-0', False, 1)
    cursor_scope(visibility, 'new-owner', True, 1)
    assert len(visibility.cursor_scopes) == CURSOR_SCOPE_CAPACITY
    assert 'owner-1' not in visibility.cursor_scopes and 'owner-2' in visibility.cursor_scopes
    assert visibility.cursor_scopes['owner-0'] is False
    for index in range(600):
        cursor_scope(visibility, 'owner-0', False, 2)
        cursor_scope(visibility, f'new-{index}', True, 1)
    assert len(visibility.cursor_scopes) == CURSOR_SCOPE_CAPACITY
    assert visibility.cursor_scopes['owner-0'] is False
    with pytest.raises(HubError) as failure:
        cursor_scope(visibility, 'owner-0', True, 2)
    assert failure.value.code == 'EVENT_CURSOR_EXPIRED'
    assert set(failure.value.detail) == {'snapshotUrl', 'latestSeq', 'oldestAvailableSeq'}
    assert list(visibility.cursor_scopes)[-1] == 'owner-0'
    # Eviction is not a downgrade: the forgotten client establishes a new scope.
    cursor_scope(visibility, 'owner-1', True, 2)
    assert visibility.cursor_scopes['owner-1'] is True


def test_pagination_and_other_after_parameters_do_not_use_scope_capacity(client, hub, auth_headers):
    seed_events(hub)
    assert client.get('/api/v1/events?after=0', headers=features(auth_headers, True)).status_code == 200
    scopes = hub.app.state.remote_worker.pi.cursor_scopes
    before = list(scopes.items())
    for page in (1, 2, 3):
        assert client.get(f'/api/v1/tasks?page={page}&after=2', headers=auth_headers).status_code == 200
        assert client.get(f'/api/v2/conversations?page={page}&after=2', headers=auth_headers).status_code == 200
        assert list(scopes.items()) == before
    assert client.get('/api/v2/unknown/bootstrap?after=2', headers=auth_headers).status_code == 404
    assert list(scopes.items()) == before
    client.head('/api/v2/events?after=0', headers=auth_headers)
    assert list(scopes.items()) == before


def test_scope_check_matches_event_endpoint_query_parsing(client, hub, auth_headers):
    events = seed_events(hub)
    assert client.get('/api/v2/events?after=0', headers=features(auth_headers, True)).status_code == 200
    for params in ({'after': ''}, [('after', '0'), ('after', '')], {'after': '-1'}, {'after': 'bad'}):
        response = client.get('/api/v2/events', params=params, headers=auth_headers)
        assert response.status_code == 422
        assert hub.app.state.remote_worker.pi.cursor_scopes[owner(auth_headers)] is True
    for after in (f'+{events[0].seq}', f' {events[0].seq} ', f'{events[0].seq}.0'):
        response = client.get('/api/v2/events', params={'after': after}, headers=auth_headers)
        assert response.status_code == 410
    response = client.get('/api/v2/events', params=[('after', '0'), ('after', str(events[0].seq))], headers=auth_headers)
    assert response.status_code == 410
    response = client.get('/api/v2/events', params=[('after', str(events[0].seq)), ('after', '0')], headers=auth_headers)
    assert response.status_code == 200


def test_empty_event_store_still_serializes_both_recovery_keys(client, hub, auth_headers):
    assert hub.events.latest_seq() == 0
    assert client.get('/api/v2/events?after=0', headers=features(auth_headers, True)).status_code == 200
    response = client.get('/api/v2/events?after=1', headers=auth_headers)
    assert response.status_code == 410
    assert response.json()['error']['detail'] == {
        'snapshotUrl': '/api/v2/bootstrap', 'latestSeq': 0, 'oldestAvailableSeq': None}


@pytest.mark.parametrize('version', ['v1', 'v2'])
def test_real_pruning_watermarks_remain_authoritative(client, hub, auth_headers, version):
    events = seed_events(hub)
    hub.events.prune_before(events[-1].seq)
    response = client.get(f'/api/{version}/events?after={events[0].seq}', headers=features(auth_headers, True))
    assert response.status_code == 410
    assert response.json()['error']['detail']['oldestAvailableSeq'] == events[-1].seq
    assert response.json()['error']['detail']['latestSeq'] == events[-1].seq


def test_ws_unknown_positive_cursor_uses_ticket_scope_and_registers(client, hub, auth_headers):
    events = seed_events(hub)
    ticket = client.post('/api/v1/auth/ws-ticket', headers=features(auth_headers, True)).json()['data']['ticket']
    assert not hub.app.state.remote_worker.pi.cursor_scopes
    with client.websocket_connect(f'/api/v1/events/stream?after={events[0].seq}&ticket={ticket}',
                                  headers={'Origin': auth_headers['Origin']}) as ws:
        frame = ws.receive_json()
        assert frame['seq'] == events[1].seq and 'error' not in frame
    assert hub.app.state.remote_worker.pi.cursor_scopes[owner(auth_headers)] is True


def test_ws_known_downgrade_has_same_watermarks_as_http(client, hub, auth_headers):
    events = seed_events(hub)
    assert client.get('/api/v2/events?after=0', headers=features(auth_headers, True)).status_code == 200
    ticket = client.post('/api/v1/auth/ws-ticket', headers=auth_headers).json()['data']['ticket']
    with client.websocket_connect(f'/api/v1/events/stream?after={events[0].seq}&ticket={ticket}',
                                  headers={'Origin': auth_headers['Origin'], 'X-HQ-Client-Features': 'pi-v1'}) as ws:
        error = ws.receive_json()['error']
        assert error['code'] == 'EVENT_CURSOR_EXPIRED'
        assert error['detail'] == hub.events.cursor_expired_detail('/api/v1/bootstrap')
        assert ws.receive()['code'] == 4410
