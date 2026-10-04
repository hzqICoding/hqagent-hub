import asyncio
import json
from types import SimpleNamespace

import pytest
from protocol.generated import python as dto
from runtime.repositories import AdapterDirectory
from remote_support import System, Workspaces, until
from test_pi_adapter import adapter_fixture, cleanup
from test_image_target_resolution import view


def integrated(tmp_path, monkeypatch, mode):
    adapter, spec = adapter_fixture(tmp_path, monkeypatch, mode)
    system = System(tmp_path / 'system')
    system.ports.workspaces = Workspaces(spec.worktree_path)
    pi = view('local.pi.default', version='1.0.1').model_copy(update={'adapter_id': 'pi'})
    async def agents():
        return [pi]
    system.ports.agents = SimpleNamespace(list_agents=agents, get=lambda kind: adapter if kind == 'pi' else None)
    directory = AdapterDirectory(system.ports.agents)
    system.tasks.directory = system.tasks.runtime.adapters = system.tasks.runtime.sessions.adapters = directory
    system.coordinator.adapters = directory
    scene = system.chat.repository.scene('analyze')
    system.chat.repository.save_scene('analyze', dto.SaveLocalSceneInput(expectedVersion=scene.version,
        roles=[r.model_copy(update={'agent_instance_id': pi.id, 'model_id_': 'synthetic/family/model'}) for r in scene.roles]))
    return system, adapter


@pytest.mark.parametrize('blocked_report', [False, True, 'failed', 'plain', 'self-refusal'])
def test_local_continue_uses_same_session_after_policy_block(tmp_path, monkeypatch, blocked_report):
    async def scenario():
        system, adapter = integrated(tmp_path, monkeypatch, 'recall')
        try:
            conversation = system.chat.repository.create_conversation(dto.CreateLocalConversationInput(
                title='synthetic', workspaceId='workspace', sceneId='analyze'), 'create')
            await system.chat.start()
            async def send(key, text, mode='continue'):
                receipt = system.chat.send(conversation.id, dto.SendLocalMessageInput(
                    clientMessageId=key, text=text, sessionMode=mode), key)
                await until(lambda: system.chat.repository.run_record(receipt.run_id)['status'] in {'failed', 'succeeded'}, timeout=12)
                return system.chat.repository.run_record(receipt.run_id)
            first = await send('first', 'remember SYNTHETIC_CONTEXT_58', 'new')
            assert first['status'] == 'succeeded', first['error']
            sessions = await system.tasks.runtime.sessions.repository.list({'taskId': first['task_id']})
            assert len(sessions) == 1
            original = sessions[0]
            assert original.turn_count == 1 and original.status == 'idle'
            monkeypatch.setenv('PI_FAKE_TOOL', 'read')
            monkeypatch.setenv('PI_FAKE_ARGS', '{"path":"../outside"}')
            if blocked_report is True:
                monkeypatch.setenv('PI_FAKE_BLOCKED_REPORT', '1')
            elif isinstance(blocked_report, str):
                monkeypatch.setenv('PI_FAKE_FINAL_REPORT', blocked_report)
                if blocked_report == 'self-refusal':
                    monkeypatch.delenv('PI_FAKE_TOOL')
            blocked = await send('blocked', 'try reading outside')
            assert blocked['status'] == 'succeeded', blocked['error']
            current = await system.tasks.runtime.sessions.repository.get(original.id)
            assert current.status == 'idle' and current.is_valid and current.turn_count == 2
            events = system.events.page(0, 1000).events
            failures = [e.payload for e in events if e.type == 'agent.failed' and e.payload.get('errorCode') == 'PI_TOOL_CALL_BLOCKED']
            assert failures
            if blocked_report == 'self-refusal':
                assert failures[0]['blockers'][0]['detail']['evidence'] == 'model_report'
            else:
                assert failures[0]['blockers'][0]['detail']['guardReason'] == 'path_outside_scope'
            monkeypatch.delenv('PI_FAKE_TOOL', raising=False)
            monkeypatch.delenv('PI_FAKE_FINAL_REPORT', raising=False)
            third = await send('third', 'recall context')
            assert third['status'] == 'succeeded', third['error']
            current = await system.tasks.runtime.sessions.repository.get(original.id)
            assert current.turn_count == 3 and current.external_session_id == original.external_session_id
            messages = system.chat.repository.messages(conversation.id)
            assert 'SYNTHETIC_CONTEXT_58' in messages[-1].text
        finally:
            await system.close()
            await cleanup(adapter)
    asyncio.run(scenario())


def test_model_api_and_scene_save_share_verified_catalog(tmp_path, monkeypatch):
    async def scenario():
        system, adapter = integrated(tmp_path, monkeypatch, 'catalog-lazy')
        headers = {'X-HQ-Client-Features': 'pi-v1', 'Origin': 'http://127.0.0.1'}
        rows = [{'provider': 'synthetic', 'id': name, 'input': ['text']} for name in
                ('family/model', 'other', 'deepseek/one', 'deepseek/two', 'deepseek/three', 'deepseek/four')]
        monkeypatch.setenv('PI_FAKE_CATALOG', json.dumps(rows))
        try:
            response = await system.local.get('/api/v2/agents/local.pi.default/models', headers=headers)
            assert response.status_code == 200, response.text
            catalog = dto.LocalAgentModelsView.model_validate(response.json()['data'])
            assert catalog.verified and len(catalog.models) == 6
            scene = system.chat.repository.scene('analyze')
            async def save(model):
                current = system.chat.repository.scene('analyze')
                roles = [r.model_copy(update={'model_id_': model}).model_dump(mode='json', by_alias=True) for r in current.roles]
                return await system.local.put('/api/v2/scenes/analyze', json={'roles': roles, 'expectedVersion': current.version}, headers=headers)
            bad = await save('synthetic/not-available')
            assert bad.status_code == 422 and bad.json()['error']['code'] == 'VALIDATION_FAILED'
            assert system.chat.repository.scene('analyze').version == scene.version
            assert (await save('synthetic/deepseek/one')).status_code == 200
            monkeypatch.setenv('PI_FAKE_MODE', 'empty-catalog')
            empty = await system.local.get('/api/v2/agents/local.pi.default/models', headers=headers)
            assert not empty.json()['data']['verified'] and empty.json()['data']['models'] == []
            assert empty.json()['data']['reason']
            assert (await save('synthetic/deepseek/one')).status_code == 422
            assert not adapter.registry.values()  # Catalog operations never prompt.
        finally:
            await system.close()
            await cleanup(adapter)
    asyncio.run(scenario())
