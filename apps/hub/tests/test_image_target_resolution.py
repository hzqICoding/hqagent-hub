import asyncio
from types import SimpleNamespace

import pytest
from protocol.generated import python as dto
from adapters.history import FileHistory
from orchestrator.domain import ProfileSnapshot, ResolutionRequest, ResolutionGap
from runtime.execution_selection import scene_execution, native_execution_candidate
from runtime.repositories import AdapterDirectory
from runtime.attachments.capabilities import REQUIRED_PROBES
from remote_support import System, until
from storage.local_chat import now
from core.errors import HubError
from test_r15_joint_server import RealPair, server_source


def view(identifier='local.codex.default', version='0.159.2', status='ready'):
    return dto.AgentView(id=identifier, adapterId='codex', displayName='synthetic', version=version,
        status=status, detectedAt=now(), capabilities=[dto.CapabilityItem(id=name, name=name,
            hard=True, source='detected', supported=True) for name in ('structured_output', 'tool_approval', 'session_resume', 'file_write')],
        assignedRoles=[], isPrimaryFor=[])


def configure(system, values):
    async def list_agents():
        return list(values)
    async def detect():
        return SimpleNamespace(detected_version=values[0].version)
    manager = SimpleNamespace(list_agents=list_agents, get=lambda kind: system.adapter)
    directory = AdapterDirectory(manager)
    system.ports.agents = manager
    system.tasks.directory = directory
    system.tasks.runtime.adapters = directory
    system.tasks.runtime.sessions.adapters = directory
    system.adapter.detect = detect
    system.adapter.handle = system.adapter.handle.model_copy(update={'adapter_id': 'codex'})
    return system.worker.attachments.capabilities


def verify(caps, version='0.159.2', model=None, identifier='local.codex.default'):
    from runtime.attachments.verification_target import target_for
    adapter = caps.worker.bridge.chat.ports.tasks.directory.adapter_for(identifier)
    target = target_for(identifier, 'codex', version, model, adapter)
    caps.store.record('codex', version, model, {name: True for name in REQUIRED_PROBES}, ['image/png'],
                      target=target, cleanup_confirmed=True)


def role(caps, scene='analyze'):
    return caps.values[scene][0]


def test_default_scenes_share_actual_execution_resolution(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            values = [view('local.codex.z'), view()]
            caps = configure(system, values)
            await caps.refresh()
            assert all(caps.values[s][0]['imageInput']['support'] == 'unknown' for s in ('analyze', 'plan', 'develop'))
            verify(caps)
            await caps.refresh()
            for scene_id in ('analyze', 'plan', 'develop'):
                scene = system.chat.repository.scene(scene_id)
                assert not next(r for r in scene.roles if r.enabled).agent_instance_id
                profile, overrides, options = scene_execution(scene, 'test-profile')
                resolution, _, _ = system.tasks.runtime.resolve_agent(ResolutionRequest(
                    role_id=scene.roles[0].role_id if scene_id != 'develop' else 'developer',
                    agents=tuple(await system.tasks.directory.list_candidates()),
                    global_profile=ProfileSnapshot.from_view(profile), requires_approval=None))
                assert not isinstance(resolution, ResolutionGap)
                selected = caps.values[scene_id][0]
                assert selected['agentId'] == resolution.agent.instance_id
                assert selected['agentId'] == 'local.codex.default'
                assert selected['imageInput']['support'] == 'supported'
            conversation = system.chat.repository.create_conversation(dto.CreateLocalConversationInput(
                title='default', workspaceId='workspace', sceneId='analyze'), 'create')
            caps.require(conversation.id, [{'kind': 'image', 'mimeType': 'image/png', 'sizeBytes': 1}])
            await system.chat.start()
            receipt = system.chat.send(conversation.id, dto.SendLocalMessageInput(
                clientMessageId='run', text='synthetic default selection', sessionMode='new'), 'run')
            await until(lambda: system.chat.repository.run_record(receipt.run_id)['status'] == 'succeeded')
            task = await system.tasks.get_task(system.chat.repository.run_record(receipt.run_id)['task_id'])
            assert task.nodes[0].resolved_agent_id == role(caps)['agentId']
            assert system.adapter.started[0].model_id_ is None
        finally:
            await system.close()
    asyncio.run(scenario())


def test_explicit_model_availability_and_version_use_matching_verification(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            values = [view()]
            caps = configure(system, values)
            verify(caps)
            scene = system.chat.repository.scene('analyze')
            system.chat.repository.save_scene('analyze', dto.SaveLocalSceneInput(expectedVersion=scene.version,
                roles=[r.model_copy(update={'agent_instance_id': values[0].id, 'model_id_': 'chosen-model'}) for r in scene.roles]))
            await caps.refresh()
            assert role(caps)['imageInput']['support'] == 'unknown'
            verify(caps, model='chosen-model')
            await caps.refresh()
            assert role(caps)['imageInput']['support'] == 'supported'
            values[0] = values[0].model_copy(update={'version': '0.159.3'})
            await caps.refresh()
            assert role(caps)['imageInput']['support'] == 'unknown'
            verify(caps, version='0.159.3', model='chosen-model')
            await caps.refresh()
            assert role(caps)['imageInput']['support'] == 'supported'
            values[0] = values[0].model_copy(update={'status': 'offline'})
            await caps.refresh()
            assert role(caps)['imageInput']['support'] == 'unknown' and role(caps)['imageInput']['reason']
        finally:
            await system.close()
    asyncio.run(scenario())


def test_unresolved_and_duplicate_instance_targets_remain_unknown(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            values = []
            caps = configure(system, values)
            await caps.refresh()
            assert role(caps)['imageInput']['support'] == 'unknown'
            assert role(caps)['imageInput']['reason']
            values.extend([view(), view()])
            verify(caps)
            await caps.refresh()
            assert role(caps)['imageInput']['support'] == 'unknown'
            assert '不唯一' in role(caps)['imageInput']['reason']
        finally:
            await system.close()
    asyncio.run(scenario())


def test_native_capability_uses_bound_runtime_not_other_same_type_instances(tmp_path, monkeypatch):
    async def scenario():
        system = System(tmp_path)
        try:
            values = [view(), view('local.codex.other', '0.159.3')]
            caps = configure(system, values)
            verify(caps)
            system.worker.native.plugins = [FileHistory('codex', tmp_path / 'history', runtime_id=values[0].id)]
            await caps.refresh()
            assert caps.native('codex')['imageInput']['support'] == 'supported'
            bound = native_execution_candidate(tuple(await system.tasks.directory.list_candidates()), values[0].id, system.tasks.runtime)
            assert bound.instance_id == values[0].id
            system.worker.native.plugins.append(FileHistory('codex', tmp_path / 'other', runtime_id=values[1].id))
            await caps.refresh()
            assert caps.native('codex')['imageInput']['support'] == 'unknown'
            monkeypatch.setattr(system.chat.repository, 'conversation', lambda _: SimpleNamespace(
                conversation_kind='native', agent_type='codex'))
            monkeypatch.setattr(system.worker.native, 'row', lambda *a, **kw: {'runtime_id': values[1].id})
            assert caps.target('bound-other').native.image_input.support == 'unknown'
            verify(caps, version='0.159.3', identifier=values[1].id)
            await caps.refresh()
            assert caps.target('bound-other').native.image_input.support == 'supported'
            values[1] = values[1].model_copy(update={'status': 'offline'})
            await caps.refresh()
            assert caps.target('bound-other').native.image_input.support == 'unknown'
            with pytest.raises(HubError):
                native_execution_candidate(tuple(await system.tasks.directory.list_candidates()), values[1].id, system.tasks.runtime)
        finally:
            await system.close()
    asyncio.run(scenario())


def test_catalog_revision_and_require_track_resolution_changes(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            values = [view()]
            caps = configure(system, values)
            with system.db.transaction() as tx:
                identity = system.repo.get('identity', tx)
                identity['wireRevision'] = 4
                system.repo.put('identity', identity, tx)
                system.repo.set_view(tx, dict(state='paired', workerId='worker-test', deviceName='synthetic',
                    serverOrigin='https://remote.invalid', connectionStatus='offline', lastConnectedAt=None))
                system.repo.seal(tx)
            conversation = system.chat.repository.create_conversation(dto.CreateLocalConversationInput(
                title='revision', workspaceId='workspace', sceneId='analyze'), 'create')
            image = [{'kind': 'image', 'mimeType': 'image/png', 'sizeBytes': 1}]
            await caps.refresh()
            initial = system.worker.projector.capability_revision()
            await caps.refresh()
            assert system.worker.projector.capability_revision() == initial
            with pytest.raises(HubError): caps.require(conversation.id, image)
            verify(caps)
            await caps.refresh()
            assert system.worker.projector.capability_revision() > initial
            caps.require(conversation.id, image)
            previous = system.worker.projector.capability_revision()
            for version in ('0.159.3', '0.159.4'):
                values[0] = values[0].model_copy(update={'version': version})
                await caps.refresh()
                assert system.worker.projector.capability_revision() > previous
                previous = system.worker.projector.capability_revision()
                with pytest.raises(HubError): caps.require(conversation.id, image)
            verify(caps, version='0.159.4')
            await caps.refresh()
            caps.require(conversation.id, image)
            scene = system.chat.repository.scene('analyze')
            system.chat.repository.save_scene('analyze', dto.SaveLocalSceneInput(expectedVersion=scene.version,
                roles=[r.model_copy(update={'model_id_': 'unverified-model'}) for r in scene.roles]))
            previous = system.worker.projector.capability_revision()
            await caps.refresh()
            assert system.worker.projector.capability_revision() > previous
            with pytest.raises(HubError): caps.require(conversation.id, image)
            assert 'unverified-model' not in '\n'.join(system.repo.frames())
        finally:
            await system.close()
    asyncio.run(scenario())


def test_agent_snapshot_expiry_refreshes_availability_for_execution_and_catalog(monkeypatch):
    from adapters.manager import AdapterManager
    async def scenario():
        clock = [10.0]
        current = [view()]
        calls = []
        manager = AdapterManager([SimpleNamespace(adapter_id='codex')], detect_ttl_seconds=60)
        async def discover_one(adapter):
            calls.append(adapter.adapter_id)
            return current[0], None
        monkeypatch.setattr(manager, '_discover_one', discover_one)
        monkeypatch.setattr('adapters.manager.time.monotonic', lambda: clock[0])
        directory = AdapterDirectory(manager)
        assert (await directory.list_candidates())[0].ready
        await manager.list_agents()
        assert calls == ['codex']
        current[0] = current[0].model_copy(update={'status': 'offline', 'version': '0.159.3'})
        clock[0] += 61
        assert not (await directory.list_candidates())[0].ready
        assert (await manager.list_agents())[0].version == '0.159.3'
        assert calls == ['codex', 'codex']
    asyncio.run(scenario())


def test_real_phone_image_uses_unbound_default_scene(tmp_path):
    import httpx
    from pathlib import Path
    from test_r16_attachments import upload_phone, send_phone
    from runtime.attachments.verification import synthetic_inputs
    async def scenario():
        async with RealPair(tmp_path, revision=4) as pair:
            caps = configure(pair.system, [view()])
            verify(caps)
            assert not pair.system.chat.repository.scene('analyze').roles[0].agent_instance_id
            await caps.refresh()
            await until(lambda: not pair.system.repo.frames())
            images = tmp_path / 'images'
            images.mkdir()
            png = synthetic_inputs(images)[0][0]
            conversation, item = await upload_phone(pair, Path(png.local_path).read_bytes())
            pair.system.worker.attachments.library.http_factory = lambda: httpx.AsyncClient(
                verify=pair.tls, follow_redirects=False, trust_env=False)
            command = await send_phone(pair, conversation, item)
            await until(lambda: pair.system.worker.delivery.row(command) and
                pair.system.worker.delivery.row(command)['state'] in {'completed', 'failed', 'rejected'})
            row = pair.system.worker.delivery.row(command)
            assert row['state'] == 'completed', row['result_json']
            await until(lambda: pair.system.chat.repository.run_record(row['run_id'])['status'] == 'succeeded')
            task = await pair.system.tasks.get_task(pair.system.chat.repository.run_record(row['run_id'])['task_id'])
            assert task.nodes[0].resolved_agent_id == role(caps)['agentId'] == 'local.codex.default'
            assert pair.system.adapter.started[0].input_attachments[0].attachment.kind == 'image'
    asyncio.run(scenario())
