import asyncio
import json
from types import SimpleNamespace

from protocol.generated import python as dto
from remote_support import System, FakeRemoteServer, until
from storage.local_chat import now
from storage.events import EventDraft
from test_image_target_resolution import configure, view
from test_r15_joint_server import RealPair, server_source

PI_HEADERS = {'X-HQ-Client-Features': 'pi-v1', 'Origin': 'http://127.0.0.1'}


def configure_pi(system):
    pi = view('local.pi.default', version='1.0.1').model_copy(update={'adapter_id': 'pi'})
    normal = view()
    caps = configure(system, [normal, pi])
    system.adapter.verification_configuration = lambda: ['synthetic-provider-model']
    system.adapter.guard = dto.RuntimeGuardView(status='ready', isolation='hub_extension_only',
        checkedAt=now(), reasons=[])
    scene = system.chat.repository.scene('analyze')
    system.chat.repository.save_scene('analyze', dto.SaveLocalSceneInput(expectedVersion=scene.version,
        roles=[r.model_copy(update={'agent_instance_id': pi.id, 'model_id_': 'synthetic/family/model'}) for r in scene.roles]))
    return caps


def test_http_feature_projection_resources_and_cursor_scope(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            configure_pi(system)
            agents = await system.local.get('/api/v2/agents')
            assert [v['adapterId'] for v in agents.json()['data']] == ['codex']
            modern = await system.local.get('/api/v2/agents', headers=PI_HEADERS)
            assert {v['adapterId'] for v in modern.json()['data']} == {'codex', 'pi'}
            old_scenes = (await system.local.get('/api/v2/scenes')).json()['data']
            assert all(s['id'] != 'analyze' for s in old_scenes)
            assert (await system.local.get('/api/v2/scenes/analyze')).status_code == 404
            created = await system.local.post('/api/v2/conversations', headers={**PI_HEADERS, 'Idempotency-Key': 'pi-create'},
                json={'workspaceId': 'workspace', 'sceneId': 'analyze', 'title': 'PI synthetic'})
            assert created.status_code == 201, created.text
            identifier = created.json()['data']['id']
            assert (await system.local.get('/api/v2/conversations/' + identifier + '/messages')).status_code == 404
            assert (await system.local.get('/api/v2/conversations/' + identifier + '/messages', headers=PI_HEADERS)).status_code == 200
            assert (await system.local.get('/api/v2/conversations')).json()['data'] == []
            blocked = await system.local.post('/api/v2/conversations', headers={'Idempotency-Key': 'old-create'},
                json={'workspaceId': 'workspace', 'sceneId': 'analyze', 'title': 'not allowed'})
            assert blocked.status_code == 404
            with system.db.transaction() as tx:
                system.events.append(tx, EventDraft(aggregate_type='agent', aggregate_id='local.pi.default',
                    type='agent.progress', payload={'message': 'PI-private'}, adapter_id='pi'))
                system.events.append(tx, EventDraft(aggregate_type='agent', aggregate_id='local.codex.default',
                    type='agent.progress', payload={'message': 'ordinary'}))
            events = await system.local.get('/api/v2/events?after=0')
            assert 'PI-private' not in events.text and 'ordinary' in events.text
            cursor = events.json()['data']['nextSeq']
            switched = await system.local.get(f'/api/v2/events?after={cursor}', headers=PI_HEADERS)
            assert switched.status_code == 410 and switched.json()['error']['code'] == 'EVENT_CURSOR_EXPIRED'
            modern_events = await system.local.get('/api/v2/events?after=0', headers=PI_HEADERS)
            assert 'PI-private' in modern_events.text
            assert modern_events.json()['data']['nextSeq'] == cursor
        finally:
            await system.close()
    asyncio.run(scenario())


def test_revision4_defers_pi_and_revision5_replays_full_metadata(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            configure_pi(system)
            async with FakeRemoteServer(revision=4) as server:
                await system.pair(server, start=True)
                await until(lambda: system.repo.get('identity')['wireRevision'] == 4)
                assert system.repo.get('link')['view']['lastErrorCode'] == 'REMOTE_REVISION_REQUIRED'
                conversation = system.chat.repository.create_conversation(dto.CreateLocalConversationInput(
                    workspaceId='workspace', sceneId='analyze', title='deferred PI'), 'deferred')
                await until(lambda: (system.repo.get('pi-deferred') or {}).get('pending'))
                assert not any(f['type'] == 'sync.conversation.upserted' and f['payload']['conversationId'] == conversation.id for f in server.frames)
                await until(lambda: any(f['type'] == 'capability.changed' for f in server.frames))
                catalogs = [f for f in server.frames if f['type'] == 'capability.changed']
                assert catalogs and all(s['sceneId'] != 'analyze' for s in catalogs[-1]['payload']['scenes'])
                server.revision = 5
                system.worker.next_revision2_probe = 0
                await until(lambda: system.repo.get('identity')['wireRevision'] == 5)
                await until(lambda: any(f['type'] == 'sync.conversation.upserted' and f['payload']['conversationId'] == conversation.id for f in server.frames))
                await until(lambda: any(f['type'] == 'capability.changed' and f['wireRevision'] == 5 for f in server.frames))
                catalog = next(f['payload'] for f in reversed(server.frames) if f['type'] == 'capability.changed' and f['wireRevision'] == 5)
                runtime = next(r for r in catalog['runtimes'] if r['agentType'] == 'pi')
                assert runtime['guard']['status'] == 'ready' and runtime['nativeSessionsSupported'] is False
                scene = next(s for s in catalog['scenes'] if s['sceneId'] == 'analyze')
                assert scene['roleImageCapabilities'][0]['agentType'] == 'pi'
                assert scene['roleImageCapabilities'][0]['modelId'] == 'synthetic/family/model'
                assert scene['roleImageCapabilities'][0]['imageInput']['support'] != 'supported'
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_pi_busy_snapshot_is_not_truncated_on_old_wire(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            configure_pi(system)
            await system.worker.pi.refresh()
            conversation = system.chat.repository.create_conversation(dto.CreateLocalConversationInput(
                workspaceId='workspace', sceneId='analyze', title='busy PI'), 'busy-pi')
            system.chat.repository.enqueue(conversation.id, dto.SendLocalMessageInput(
                clientMessageId='hold', text='hold', sessionMode='new'), 'hold')
            with system.db.transaction() as tx:
                identity = system.repo.get('identity', tx)
                identity['wireRevision'] = 4
                system.repo.put('identity', identity, tx)
                system.repo.set_view(tx, dict(state='paired', workerId='worker-test', deviceName='test',
                    serverOrigin='https://example.test', connectionStatus='offline', lastConnectedAt=None))
                system.repo.seal(tx)
            system.worker.busy.connection_id = 'test-connection'
            system.worker.busy.snapshot(force=True)
            assert not any(json.loads(f)['type'] == 'sync.busy.snapshot' for f in system.repo.frames())
            assert system.repo.get('pi-deferred')['pending'] is True
        finally:
            await system.close()
    asyncio.run(scenario())


def test_ws_projection_uses_ticket_features_not_handshake_headers(client, hub, auth_headers):
    for ticket_pi in (False, True):
        headers = dict(auth_headers)
        if ticket_pi:
            headers['X-HQ-Client-Features'] = 'pi-v1'
        ticket = client.post('/api/v1/auth/ws-ticket', headers=headers).json()['data']['ticket']
        with hub.database.transaction() as tx:
            hub.events.append(tx, EventDraft('agent', 'synthetic-pi', 'agent.progress',
                {'message': 'PI-only'}, adapter_id='pi'))
            hub.events.append(tx, EventDraft('system', 'ordinary', 'agent.progress',
                {'message': 'visible-end'}))
        # Contrary feature headers on WS cannot alter the issued ticket claims.
        ws_headers = {'Origin': auth_headers['Origin']}
        if not ticket_pi:
            ws_headers['X-HQ-Client-Features'] = 'pi-v1'
        with client.websocket_connect('/api/v1/events/stream?after=0&ticket=' + ticket,
                                      headers=ws_headers) as ws:
            messages = []
            while True:
                event = ws.receive_json()
                messages.append(event.get('payload', {}).get('message'))
                if messages[-1] == 'visible-end':
                    break
        assert ('PI-only' in messages) is ticket_pi


def test_ws_feature_change_expires_previous_event_cursor(client, hub, auth_headers):
    with hub.database.transaction() as tx:
        event, _ = hub.events.append(tx, EventDraft('system', 'ordinary', 'agent.progress', {'message': 'visible'}))
    client.get('/api/v1/events?after=0', headers=auth_headers)
    ticket = client.post('/api/v1/auth/ws-ticket', headers={**auth_headers,
        'X-HQ-Client-Features': 'pi-v1'}).json()['data']['ticket']
    with client.websocket_connect(f'/api/v1/events/stream?after={event.seq}&ticket={ticket}',
                                  headers={'Origin': auth_headers['Origin']}) as ws:
        error = ws.receive_json()['error']
        assert error['code'] == 'EVENT_CURSOR_EXPIRED'
        assert error['detail'] == hub.events.cursor_expired_detail('/api/v1/bootstrap')


def test_real_server_revision4_inflight_fence_then_pi_catalog(tmp_path, monkeypatch, server_source):
    from test_r3_upgrade_history import phone_submit, drained
    async def scenario():
        from server import wire
        codecs = dict(wire.CODECS)
        assert 5 in codecs
        from server.events_sync import SyncEvents
        import traceback
        faults = []
        accept = SyncEvents.accept
        def traced_accept(instance, tx, owner, event, *args, **kwargs):
            try:
                return accept(instance, tx, owner, event, *args, **kwargs)
            except Exception as error:
                faults.append({'type': event['type'], 'seq': event['seq'],
                    'stack': [(v.name, v.lineno) for v in traceback.extract_tb(error.__traceback__)]})
                raise
        monkeypatch.setattr(SyncEvents, 'accept', traced_accept)
        async with RealPair(tmp_path, revision=4) as pair:
            await drained(pair)
            pair.system.adapter.release.clear()
            identifier = await phone_submit(pair, 'revision4-in-flight')
            delivery = pair.system.worker.delivery
            await until(lambda: bool(pair.system.adapter.started) and delivery.row(identifier)['state'] == 'accepted')
            from runtime.pi_visibility import task_revision_allowed
            row = delivery.row(identifier)
            task_id = pair.system.chat.repository.run_record(row['run_id'])['task_id']
            assert not task_revision_allowed(pair.system.db, task_id)
            with pair.system.db.locked_connection() as db:
                db.execute('SAVEPOINT before_handle')
                try:
                    db.execute('UPDATE local_runs SET task_id=NULL WHERE run_id=?', (row['run_id'],))
                    assert not task_revision_allowed(pair.system.db, task_id)
                finally:
                    db.execute('ROLLBACK TO before_handle')
                    db.execute('RELEASE before_handle')
            # Restore through the fixture that lowered the revision. An outer
            # monkeypatch would later roll back to v4 and poison the next test.
            pair.wire_patch.setattr(wire, 'CODECS', codecs)
            pair.system.worker.next_revision2_probe = 0
            assert not pair.system.worker.can_upgrade()
            await asyncio.sleep(.5)
            assert pair.system.repo.get('identity')['wireRevision'] == 4
            pair.system.adapter.release.set()
            await until(lambda: delivery.row(identifier)['state'] == 'completed')
            await until(lambda: pair.system.chat.repository.run_record(delivery.row(identifier)['run_id'])['status'] == 'succeeded')
            await until(lambda: pair.system.repo.get('identity')['wireRevision'] == 5, timeout=15)
            assert json.loads(delivery.row(identifier)['result_json'])['wireRevision'] == 4
            assert len(pair.system.adapter.started) == 1
            before_version = pair.system.chat.repository.conversation(pair.legacy_ids[0]).version
            configure_pi(pair.system)
            assert pair.system.chat.repository.conversation(pair.legacy_ids[0]).version == before_version + 1
            await pair.system.worker.pi.refresh()
            try:
                await until(lambda: any(f['type'] == 'capability.changed' and any(
                    r.get('agentType') == 'pi' for r in f['payload'].get('runtimes', [])) for f in pair.sent))
            except TimeoutError:
                raise AssertionError({'link': pair.system.repo.get('link')['view'],
                    'errors': [f.get('error', {}).get('code') for f in pair.received if f['type'] == 'worker.hello_rejected'],
                    'outbox': [json.loads(f)['type'] for f in pair.system.repo.frames()], 'faults': faults}) from None
            await drained(pair)
            with pair.service.repo.transaction() as tx:
                catalog = tx.get(pair.owner, 'catalog', pair.worker_id)
                assert next(r for r in catalog['runtimes'] if r['agentType'] == 'pi')['guard']['status'] == 'ready'
                scene = next(s for s in catalog['scenes'] if s['sceneId'] == 'analyze')
                from server.client_features import ClientProjection
                assert ClientProjection.pi_scene(catalog, scene)
        assert wire.CODECS == codecs
    asyncio.run(scenario())
