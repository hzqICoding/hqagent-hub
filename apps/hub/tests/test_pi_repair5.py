import asyncio

import pytest
from protocol.generated import python as dto
from orchestrator.errors import AdapterStartFailedError
from remote_support import until
from test_pi_adapter import adapter_fixture, cleanup
from test_pi_repair2 import integrated


@pytest.mark.parametrize('report,success,healthy', [
    ('plain-refusal', True, True), ('plain-answer', True, True),
    ('bad-json', False, True), ('bad-array', False, True), ('bad-fence', False, True),
    ('length', False, True), ('runtime-error', False, False), ('aborted', False, False),
    ('exit-error', False, False),
])
def test_format_outcome_is_separate_from_native_session_health(tmp_path, monkeypatch, report, success, healthy):
    async def scenario():
        system, adapter = integrated(tmp_path, monkeypatch, 'recall')
        try:
            conversation = system.chat.repository.create_conversation(dto.CreateLocalConversationInput(
                title='plain reply', workspaceId='workspace', sceneId='analyze'), 'create')
            await system.chat.start()
            async def send(key, text):
                receipt = system.chat.send(conversation.id, dto.SendLocalMessageInput(
                    clientMessageId=key, text=text, sessionMode='continue'), key)
                await until(lambda: system.chat.repository.run_record(receipt.run_id)['status'] in {'failed', 'succeeded'}, timeout=12)
                return system.chat.repository.run_record(receipt.run_id)
            first = await send('first', 'remember SYNTHETIC_CONTEXT_58')
            assert first['status'] == 'succeeded'
            original = (await system.tasks.runtime.sessions.repository.list({'taskId': first['task_id']}))[0]
            monkeypatch.setenv('PI_FAKE_FINAL_REPORT', report)
            current_run = await send('reply', 'respond without calling a tool')
            assert current_run['status'] == ('succeeded' if success else 'failed')
            state = adapter.registry.get(original.id)
            assert state.tool_blocks == []
            session = await system.tasks.runtime.sessions.repository.get(original.id)
            assert session.status == ('idle' if healthy else 'invalid')
            assert session.is_valid is healthy
            assert adapter.can_resume_completed_turn(original.id) is healthy
            if success:
                expected = ('请求的文件位于授权根目录之外，我无法读取。' if report == 'plain-refusal' else 'ordinary synthetic answer')
                assert state.result.summary == expected and state.result.changed_files == []
                assert not state.result.blockers  # No fabricated refusal audit from prose.
                events = [e for e in system.events.page(0, 1000).events if e.task_id == current_run['task_id']]
                assert not any(e.type == 'agent.failed' for e in events)
            elif healthy:
                assert state.result_failure is not None and state.failure is None
            monkeypatch.delenv('PI_FAKE_FINAL_REPORT')
            followup = await send('continue', 'recall context')
            assert followup['status'] == ('succeeded' if healthy else 'failed')
            if healthy:
                session = await system.tasks.runtime.sessions.repository.get(original.id)
                assert session.turn_count == 3 and session.external_session_id == original.external_session_id
                assert 'SYNTHETIC_CONTEXT_58' in system.chat.repository.messages(conversation.id)[-1].text
        finally:
            await system.close()
            await cleanup(adapter)
    asyncio.run(scenario())


@pytest.mark.parametrize('role,purpose', [('general_implementer', 'implement'), ('reviewer', 'review')])
def test_write_and_review_require_json_but_healthy_format_failure_keeps_session(tmp_path, monkeypatch, role, purpose):
    from orchestrator.tests.test_runtime import build_runtime, request
    from orchestrator.tests.fakes import agent
    adapter, spec = adapter_fixture(tmp_path, monkeypatch, 'recall')
    candidate = agent('pi-primary', adapter_id='pi', capabilities=('file_write', 'structured_output', 'tool_approval', 'session_resume'))
    runtime, _, _ = build_runtime((candidate,), adapter)
    monkeypatch.setenv('PI_FAKE_FINAL_REPORT', 'plain-answer')
    async def scenario():
        try:
            outcome = await runtime.dispatch(request((candidate,), role_id=role,
                task_override_agent_id='pi-primary', session_purpose=dto.SessionPurpose(purpose),
                objective='remember SYNTHETIC_CONTEXT_58', worktree_path=spec.worktree_path,
                allowed_paths=('**',), model_id='synthetic/family/model'))
            result = await adapter.collect_result(outcome.session.id)
            assert isinstance(result, dto.AdapterFailure)
            # Even callers collecting without first consuming stream_end must
            # preserve the session based on the Adapter's structured proof.
            with pytest.raises(AdapterStartFailedError):
                await runtime.collect_result(outcome)
            saved = await runtime.sessions.repository.get(outcome.session.id)
            assert saved.status == 'idle' and saved.is_valid
            monkeypatch.delenv('PI_FAKE_FINAL_REPORT')
            resumed = await runtime.sessions.resume(saved, 'recall context', None)
            assert resumed.id == saved.id and resumed.turn_count == 2
            result = await adapter.collect_result(saved.id)
            assert result.summary == 'SYNTHETIC_CONTEXT_58'
        finally:
            await cleanup(adapter)
    asyncio.run(scenario())
