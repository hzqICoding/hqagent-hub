import asyncio
import json
from dataclasses import replace

import pytest
from protocol.generated import python as dto
from core.errors import HubError
from orchestrator.catalog import BuiltinCatalog
from orchestrator.domain import AgentCandidate, ProfileSnapshot, ResolutionRequest, ResolutionGap
from orchestrator.role_resolver import RoleResolver
from orchestrator.team_resolver import TeamResolver
from runtime.services import TeamProfileService, seed_default_profile
from storage.team_profiles import TeamProfileRepository
from remote_support import System, until
from test_image_target_resolution import configure, view
from test_pi_projection_wire import configure_pi, PI_HEADERS
from test_remote_cookie_routes import login


def profile(primary='normal', fallbacks=()):
    return dto.SaveTeamProfileInput(id='primary-policy', name='synthetic', scope='global',
        isDefault=False, roleBindings={'analyst': {'roleId': 'analyst', 'roleName': '分析',
            'primaryAgentId': primary, 'fallbackAgentIds': list(fallbacks)}})


def candidates(pi_status='ready'):
    return tuple(AgentCandidate.from_view(v) for v in (
        view('normal'), view('opaque-runtime', version='1.0.1', status=pi_status).model_copy(update={'adapter_id': 'pi'})))


@pytest.mark.parametrize('mode', ['fallback', 'automatic', 'primary', 'offline-primary'])
def test_primary_rule_shared_by_role_selection(mode):
    resolver = RoleResolver(BuiltinCatalog.load())
    values = candidates('offline' if mode == 'offline-primary' else 'ready')
    value = profile('opaque-runtime' if 'primary' in mode else 'normal',
                    ['opaque-runtime'] if mode == 'fallback' else [])
    if mode == 'automatic':
        values = (replace(values[0], status='offline'), values[1])
    result = resolver.resolve(ResolutionRequest(role_id='analyst', agents=values,
        global_profile=ProfileSnapshot.from_view(value)))
    if mode == 'primary':
        assert result.agent.instance_id == 'opaque-runtime' and not result.is_fallback
    else:
        assert isinstance(result, ResolutionGap)
        if mode == 'fallback':
            assert result.reason == 'PI 暂不支持作为后备 Agent'


def test_profile_save_import_and_historical_resolution_do_not_rewrite(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            values = [view('normal'), view('opaque-runtime').model_copy(update={'adapter_id': 'pi'})]
            configure(system, values)
            repository = TeamProfileRepository(system.db)
            service = TeamProfileService(repository, TeamResolver(BuiltinCatalog.load(),
                RoleResolver(BuiltinCatalog.load())), system.ports.agents)
            value = profile(fallbacks=['opaque-runtime'])
            with pytest.raises(HubError, match='PI 暂不支持作为后备 Agent'):
                await service.save_profile(value.id, value)
            historical = dto.TeamProfileView.model_validate({**value.model_dump(by_alias=True),
                'updatedAt': '2026-10-04T00:00:00Z'})
            with pytest.raises(HubError, match='PI 暂不支持作为后备 Agent'):
                repository.save(historical)
            # A genuine historical row predates validation. Loading/resolution
            # reports gaps, never silently deleting the user's fallback setting.
            raw = historical.model_dump_json(by_alias=True)
            with system.db.transaction() as tx:
                tx.connection.execute('INSERT INTO team_profiles VALUES(?,?,?,?,?)',
                    (value.id, value.name, 'global', raw, historical.updated_at))
            resolved = await service.resolve(dto.ResolveTeamProfileInput(profileId=value.id))
            assert resolved.has_gaps and any(g.reason == 'PI 暂不支持作为后备 Agent' for g in resolved.gaps)
            assert (await service.get_profile(value.id)).role_bindings['analyst'].fallback_agent_ids == ['opaque-runtime']
            with system.db.locked_connection() as db:
                assert db.execute('SELECT payload_json FROM team_profiles WHERE profile_id=?', (value.id,)).fetchone()[0] == raw
            repository.delete(value.id)
            seeded = seed_default_profile(repository, values)
            assert all('opaque-runtime' not in r.fallback_agent_ids for r in seeded.role_bindings.values())
            assert all(r.primary_agent_id == 'normal' for r in seeded.role_bindings.values())
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('cookie', [False, True])
def test_configuration_http_entries_reject_pi_fallbacks_before_writes(tmp_path, cookie):
    async def scenario():
        system = System(tmp_path)
        try:
            configure_pi(system)
            if cookie:
                await login(system)
            scene = system.chat.repository.scene('analyze')
            roles = [r.model_dump(mode='json', by_alias=True, exclude_none=True) for r in scene.roles]
            roles[0]['fallbackAgentIds'] = ['local.pi.default']
            calls = [
                ('PUT', '/api/v2/scenes/analyze', {'expectedVersion': scene.version, 'roles': roles}),
                ('POST', '/api/v2/scenes', {'name': 'bad import', 'roles': roles}),
                ('POST', '/api/v2/role-templates', {'name': 'bad template', 'baseRoleId': 'analyst',
                    'instructions': '', 'fallbackAgentIds': ['local.pi.default']}),
            ]
            if not cookie:
                calls.append(('PUT', '/api/v1/team-profiles/primary-policy',
                    profile('local.codex.default', ['local.pi.default']).model_dump(mode='json', by_alias=True)))
            for index, (method, path, body) in enumerate(calls):
                response = await system.local.request(method, path, json=body,
                    headers={**PI_HEADERS, 'Idempotency-Key': 'deny-fallback-' + str(index)})
                assert response.status_code == 422, response.text
                assert response.json()['error']['code'] == 'VALIDATION_FAILED'
                assert response.json()['error']['message'] == 'PI 暂不支持作为后备 Agent'
            assert system.chat.repository.scene('analyze').version == scene.version
        finally:
            await system.close()
    asyncio.run(scenario())


def test_offline_pi_primary_remains_exact_catalog_target_and_cannot_fall_back(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            configure_pi(system)
            values = [view(), view('local.pi.default', version='1.0.1', status='offline').model_copy(update={'adapter_id': 'pi'})]
            configure(system, values)
            await system.worker.pi.refresh()
            role = system.worker.attachments.capabilities.values['analyze'][0]
            assert role['agentId'] == 'local.pi.default' and role['agentType'] == 'pi'
            assert role['imageInput']['support'] == 'unknown' and role['imageInput']['reason']
            from server.client_features import ClientProjection
            assert ClientProjection.pi_scene({'runtimes': []}, {'roleImageCapabilities': [role]})
            assert (await system.local.get('/api/v2/scenes/analyze')).status_code == 404
            conversation = system.chat.repository.create_conversation(dto.CreateLocalConversationInput(
                workspaceId='workspace', sceneId='analyze', title='offline primary'), 'offline-primary')
            await system.chat.start()
            receipt = system.chat.send(conversation.id, dto.SendLocalMessageInput(clientMessageId='first',
                text='synthetic', sessionMode='new'), 'offline-first')
            await until(lambda: system.chat.repository.run_record(receipt.run_id)['status'] == 'failed')
            assert not system.adapter.started
        finally:
            await system.close()
    asyncio.run(scenario())


# True P1 TLS application + the actual Worker projection. Agent execution is a
# synthetic stream; no provider, credentials or model invocation is involved.
from test_r15_joint_server import RealPair, server_source


@pytest.mark.parametrize('terminal', ['approved', 'rejected', 'expired'])
def test_real_device_mixed_approval_projection_and_primary_catalog(tmp_path, server_source, terminal):
    from adapters.events import AdapterEvent
    from test_r3_upgrade_history import drained
    async def scenario():
        async with RealPair(tmp_path, revision=5) as pair:
            system = pair.system
            configure_pi(system)
            await system.worker.pi.refresh()
            gate, finish = asyncio.Event(), asyncio.Event()
            start = system.adapter.start
            async def synthetic_start(spec):
                kind = 'pi' if spec.model_id_ == 'synthetic/family/model' else 'codex'
                system.adapter.handle = system.adapter.handle.model_copy(update={'adapter_id': kind})
                return await start(spec)
            async def stream(identifier):
                await gate.wait()
                yield AdapterEvent.create('synthetic', 'approval.required', dto.ApprovalRequiredPayload(
                    approvalId='approval-' + identifier, action='network', targetResource='synthetic target', riskLevel='low'),
                    external_request_id='synthetic-' + identifier)
                await finish.wait()
            system.adapter.start = synthetic_start
            system.adapter.stream_events = stream
            runs = []
            for scene in ('analyze', 'plan'):
                conversation = system.chat.repository.create_conversation(dto.CreateLocalConversationInput(
                    workspaceId='workspace', sceneId=scene, title='mixed ' + scene), 'mixed-' + scene)
                receipt = system.chat.send(conversation.id, dto.SendLocalMessageInput(clientMessageId='mixed-' + scene,
                    text='synthetic', sessionMode='new'), 'mixed-' + scene)
                runs.append((conversation.id, receipt.run_id))
            await until(lambda: len(system.adapter.started) == 2)
            # Stabilize the existing run-state projection before watching only
            # approval deltas (run-state deltas legitimately require snapshots).
            for _, run in runs:
                await until(lambda: bool(system.chat.repository.run_record(run)['task_id']))
                task = system.tasks.repository.get(system.chat.repository.run_record(run)['task_id'])
                node = system.tasks.repository.list_nodes(task.id)[0]
                system.tasks.repository.save_node(node.model_copy(update={'status': dto.NodeStatus.WAITING_APPROVAL}))
                system.tasks.repository.save(task.model_copy(update={'status': dto.TaskStatus.WAITING_APPROVAL}))
            await until(lambda: all(system.chat.repository.run_record(r)['status'] == 'waiting_approval' for _, r in runs))
            await drained(pair)
            with system.db.locked_connection() as db:
                high = db.execute('SELECT COALESCE(MAX(sequence),0) FROM remote_sync_changes').fetchone()[0]
            await until(lambda: system.repo.get('sync-work')['cursor'] >= high and not system.repo.frames())
            catalog_path = '/devices/' + pair.worker_id + '/catalog'
            legacy_catalog = (await pair.browser.get(catalog_path)).json()['data']
            modern_catalog = (await pair.browser.get(catalog_path, headers={'X-HQ-Client-Features': 'pi-v1'})).json()['data']
            dto.RemoteV4CatalogView.model_validate(legacy_catalog)
            dto.RemoteV5CatalogView.model_validate(modern_catalog)
            assert 'analyze' not in {s['sceneId'] for s in legacy_catalog['scenes']}
            assert 'plan' in {s['sceneId'] for s in legacy_catalog['scenes']}
            assert next(s for s in modern_catalog['scenes'] if s['sceneId'] == 'analyze')['roleImageCapabilities'][0]['agentType'] == 'pi'
            old_cursor = (await pair.browser.get('/events')).json()['data']['nextServerCursor']
            modern_cursor = (await pair.browser.get('/events', headers={'X-HQ-Client-Features': 'pi-v1'})).json()['data']['nextServerCursor']
            gate.set()
            await until(lambda: len([f for f in pair.sent if f['type'] == 'approval.state_changed' and f['payload']['status'] == 'pending']) >= 2)
            await until(lambda: not system.repo.frames())
            old = await pair.browser.get('/events', params={'after': old_cursor})
            modern = await pair.browser.get('/events', params={'after': modern_cursor}, headers={'X-HQ-Client-Features': 'pi-v1'})
            assert old.status_code == modern.status_code == 200, (old.text, modern.text)
            old_items, new_items = old.json()['data']['items'], modern.json()['data']['items']
            old_approvals = [v for v in old_items if v['type'] == 'worker.event']
            new_approvals = [v for v in new_items if v['type'] == 'worker.event']
            assert len(old_approvals) == 1 and len(new_approvals) == 2
            dto.RemoteBrowserLegacyApprovalEvent.model_validate(old_approvals[0])
            pi_event = next(v for v in new_approvals if v['payload']['wireRevision'] == 5)
            dto.RemoteBrowserPiApprovalEvent.model_validate(pi_event)
            assert pi_event['payload']['conversationId'] not in old.text
            assert pi_event['payload']['payload']['approvalId'] not in old.text
            assert len(old_items) == 1  # No alternate refresh hint leaks PI.
            legacy_id = old_approvals[0]['payload']['payload']['approvalId']
            assert legacy_id in modern.text
            # Terminals are projection facts, saved through the same repository
            # as the approval broker, while the fake tool stream remains held.
            statuses = (terminal,)
            approvals = await system.coordinator.repository.list({'status': 'pending'})
            assert len(approvals) == 2
            for status in statuses:
                old_cursor = old.json()['data']['nextServerCursor']
                modern_cursor = modern.json()['data']['nextServerCursor']
                before = len(pair.sent)
                for approval in approvals:
                    await system.coordinator.repository.save(approval.model_copy(update={'status': dto.ApprovalStatus(status)}))
                await until(lambda: len([f for f in pair.sent[before:] if f['type'] == 'approval.state_changed' and f['payload']['status'] == status]) >= 2)
                await until(lambda: not system.repo.frames())
                old = await pair.browser.get('/events', params={'after': old_cursor})
                modern = await pair.browser.get('/events', params={'after': modern_cursor}, headers={'X-HQ-Client-Features': 'pi-v1'})
                assert old.status_code == modern.status_code == 200, (old.text, modern.text)
                assert len(old.json()['data']['items']) == 1
                assert len(modern.json()['data']['items']) == 2
                assert all(v['payload']['payload']['status'] == status for v in modern.json()['data']['items'])
                assert pi_event['payload']['payload']['approvalId'] not in old.text
            assert system.repo.get('link')['view']['state'] == 'paired'
    asyncio.run(scenario())
