import asyncio

import pytest
from protocol.generated import python as dto
from test_pi_repair2 import integrated
from test_pi_adapter import cleanup
from remote_support import until


@pytest.mark.parametrize('report', ['runtime-error', 'missing-end', 'business-failure'])
def test_only_confirmed_completed_replies_retain_sessions(tmp_path, monkeypatch, report):
    async def scenario():
        system, adapter = integrated(tmp_path, monkeypatch, 'recall')
        try:
            conversation = system.chat.repository.create_conversation(dto.CreateLocalConversationInput(
                title='completion proof', workspaceId='workspace', sceneId='analyze'), 'create')
            await system.chat.start()
            async def send(key, text):
                receipt = system.chat.send(conversation.id, dto.SendLocalMessageInput(
                    clientMessageId=key, text=text, sessionMode='continue'), key)
                await until(lambda: system.chat.repository.run_record(receipt.run_id)['status'] in {'failed', 'succeeded'}, timeout=12)
                return system.chat.repository.run_record(receipt.run_id)
            first = await send('first', 'remember SYNTHETIC_CONTEXT_58')
            assert first['status'] == 'succeeded'
            original = (await system.tasks.runtime.sessions.repository.list({'taskId': first['task_id']}))[0]
            monkeypatch.setenv('PI_FAKE_TOOL', 'read')
            monkeypatch.setenv('PI_FAKE_ARGS', '{"path":"../outside"}')
            monkeypatch.setenv('PI_FAKE_FINAL_REPORT', report)
            failed = await send('failed', 'synthetic blocked tool followed by failure')
            assert failed['status'] == 'failed'
            state = adapter.registry.get(original.id)
            current = await system.tasks.runtime.sessions.repository.get(original.id)
            if report == 'business-failure':
                assert state.result.status == 'failed'
                assert any(b.kind == 'external_failure' for b in state.result.blockers)
                assert current.status == 'idle' and current.is_valid
            else:
                assert state.failure is not None
                assert current.status == 'invalid' and not current.is_valid
                assert not adapter.can_resume_completed_turn(original.id)
            monkeypatch.delenv('PI_FAKE_TOOL')
            monkeypatch.delenv('PI_FAKE_FINAL_REPORT')
            following = await send('following', 'recall context')
            assert following['status'] == ('succeeded' if report == 'business-failure' else 'failed')
            if report == 'business-failure':
                assert 'SYNTHETIC_CONTEXT_58' in system.chat.repository.messages(conversation.id)[-1].text
        finally:
            await system.close()
            await cleanup(adapter)
    asyncio.run(scenario())


def test_safety_refusal_does_not_manufacture_review_acceptance(tmp_path, monkeypatch):
    from test_pi_adapter import adapter_fixture
    adapter, spec = adapter_fixture(tmp_path, monkeypatch)
    spec = spec.model_copy(update={'session_purpose': dto.SessionPurpose.REVIEW, 'role_id': 'reviewer'})
    monkeypatch.setenv('PI_FAKE_TOOL', 'read')
    monkeypatch.setenv('PI_FAKE_ARGS', '{"path":"../outside"}')
    monkeypatch.setenv('PI_FAKE_BLOCKED_REPORT', '1')
    async def scenario():
        try:
            handle = await adapter.start(spec)
            assert not isinstance(handle, dto.AdapterFailure)
            result = await adapter.collect_result(handle.session_id)
            assert result.status == 'blocked'
            assert result.blockers[-1].detail['errorCode'] == 'PI_TOOL_CALL_BLOCKED'
            assert adapter.can_resume_completed_turn(handle.session_id)
        finally:
            await cleanup(adapter)
    asyncio.run(scenario())
