import asyncio
import json
from pathlib import Path
import shutil

import pytest
from protocol.generated.python import AgentTaskSpec, AdapterFailure, ResumeRequest, CancelRequest
from adapters.pi_adapter import PiAdapter, prompt_input
from adapters.pi_guard import selector, unique_object
from adapters.process import ProcessRunner


def adapter_fixture(tmp_path, monkeypatch, mode=''):
    node = shutil.which('node')
    if not node:
        pytest.skip('synthetic PI RPC requires Node')
    package = tmp_path / 'package'
    package.mkdir()
    entry = package / 'cli.mjs'
    entry.write_bytes((Path(__file__).parent / 'fixtures/pi/cli.mjs').read_bytes())
    (package / 'package.json').write_text(json.dumps({'type': 'module', 'name': '@earendil-works/pi-coding-agent', 'version': '1.0.1', 'bin': {'pi': 'cli.mjs'}}))
    monkeypatch.setenv('HQAGENT_PI_PATH', str(entry))
    monkeypatch.setenv('PI_FAKE_MODE', mode)
    adapter = PiAdapter(storage_dir=tmp_path / 'hub-data/pi', guard_timeout=1, approval_timeout=0.1)
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    spec = AgentTaskSpec(sessionId='session-test', taskId='task-test', nodeId='node-test', workspaceId='workspace',
        roleId='analyst', objective='synthetic', worktreePath=str(workspace), allowedPaths=[], readOnly=True,
        reusePolicy='new_session', sessionPurpose='adhoc', modelId='synthetic/family/model', timeoutSeconds=3)
    return adapter, spec


async def cleanup(adapter):
    for state in adapter.registry.values():
        await state.connection.force_close()
        adapter._release(state)


async def denial_evidence(adapter, identifier):
    state = adapter.registry.get(identifier)
    assert state.tool_blocks and all(d.decision == 'block' for d in state.tool_blocks)
    assert state.failure is None and state.settled.is_set() and state.process.returncode is not None
    events = [event async for event in adapter.stream_events(identifier)]
    assert not any(getattr(event, 'unified_type', None) == 'agent.failed' for event in events)
    assert any(getattr(event, 'unified_type', None) == 'agent.tool_call' and event.payload.failed
               for event in events)
    denied = [b for b in state.result.blockers or [] if b.kind == 'permission_denied'
              and (b.detail or {}).get('errorCode') == 'PI_TOOL_CALL_BLOCKED']
    assert denied and all(b.detail['evidence'] == 'guard_decision' for b in denied)
    assert adapter.can_resume_completed_turn(identifier)
    return denied


def test_rpc_guard_start_final_and_exact_resume(tmp_path, monkeypatch):
    adapter, spec = adapter_fixture(tmp_path, monkeypatch)
    async def scenario():
        try:
            descriptor = await adapter.detect()
            assert descriptor.detected_version == '1.0.1'
            handle = await adapter.start(spec)
            assert not isinstance(handle, AdapterFailure), handle
            state = adapter.registry.get(spec.session_id)
            assert state.context['readOnly'] and state.handshakes == 1
            result = await adapter.collect_result(handle.session_id)
            assert result.summary == 'synthetic final'
            failure = await adapter.resume(ResumeRequest(sessionId=handle.session_id,
                externalSessionId=handle.external_session_id, message='continue', taskSpec=spec))
            assert failure is None, failure
            next_state = adapter.registry.get(spec.session_id)
            assert next_state.external_session_id == handle.external_session_id
            assert next_state.handshakes == 2
            assert (await adapter.collect_result(handle.session_id)).summary == 'synthetic final'
        finally:
            await cleanup(adapter)
    asyncio.run(scenario())


@pytest.mark.parametrize('mode', ['bad-handshake', 'no-handshake', 'unsafe-shell'])
def test_missing_guard_never_prompts(tmp_path, monkeypatch, mode):
    adapter, spec = adapter_fixture(tmp_path, monkeypatch, mode)
    async def scenario():
        result = await adapter.start(spec)
        assert isinstance(result, AdapterFailure) and result.code == 'PI_GUARD_UNAVAILABLE'
        assert not list((tmp_path / 'hub-data/pi/sessions').rglob('*.jsonl'))
    asyncio.run(scenario())


@pytest.mark.parametrize('mode,outcome', [('hold', 'stopped_gracefully'), ('no-settle', 'force_killed')])
def test_abort_ack_and_agent_end_are_not_stopping_evidence(tmp_path, monkeypatch, mode, outcome):
    adapter, spec = adapter_fixture(tmp_path, monkeypatch, mode)
    async def stop_synthetic_process(process):
        # The fixture never spawns tools/children. Exercise the Adapter's tree
        # termination outcome without relying on sandbox taskkill permissions.
        process.kill()
        await process.wait()
        return True
    monkeypatch.setattr('adapters.pi_rpc.terminate_process_tree', stop_synthetic_process)
    async def scenario():
        try:
            handle = await adapter.start(spec)
            assert not isinstance(handle, AdapterFailure), handle
            result = await adapter.cancel(CancelRequest(sessionId=spec.session_id, mode='graceful', graceSeconds=1))
            assert result.outcome == outcome and result.orphan_process_ids == []
        finally:
            await cleanup(adapter)
    asyncio.run(scenario())


def test_selector_and_strict_arguments():
    assert selector('provider/family/model') == ('provider', 'family/model')
    for value in ('model', '/model', 'provider/', 'a/../b', 'https://x/y', 'a/b c'):
        with pytest.raises(ValueError):
            selector(value)
    for value in ('[]', '{"x":1,"x":2}', '{"x":NaN}', '{"x":1e9999}'):
        with pytest.raises(ValueError):
            unique_object(value)

@pytest.mark.parametrize('tool,arguments,allowed', [
    ('read', {'path': 'safe.txt'}, True),
    ('read', {'path': '../outside'}, False),
    ('find', {'pattern': '*', 'path': '../outside'}, False),
    ('bash', {'command': 'cat safe.txt | cat'}, False),
    ('read', {'path': 'wild*.txt'}, False),
    ('write', {'path': 'safe.txt', 'content': 'x'}, False),
])
def test_guard_paths_and_read_only_tools(tmp_path, monkeypatch, tool, arguments, allowed):
    adapter, spec = adapter_fixture(tmp_path, monkeypatch)
    monkeypatch.setenv('PI_FAKE_TOOL', tool)
    monkeypatch.setenv('PI_FAKE_ARGS', json.dumps(arguments))
    async def scenario():
        try:
            handle = await adapter.start(spec)
            assert not isinstance(handle, AdapterFailure), handle
            result = await adapter.collect_result(spec.session_id)
            if allowed:
                assert result.summary == 'synthetic final'
            else:
                assert not isinstance(result, AdapterFailure)
                await denial_evidence(adapter, spec.session_id)
        finally:
            await cleanup(adapter)
    asyncio.run(scenario())


def test_guard_source_and_inventory_cannot_be_bypassed(tmp_path, monkeypatch):
    from adapters.pi_guard import GUARD_PATH
    adapter, spec = adapter_fixture(tmp_path, monkeypatch)
    monkeypatch.setenv('PI_FAKE_TOOL', 'read')
    monkeypatch.setenv('PI_FAKE_ARGS', json.dumps({'path': str(GUARD_PATH)}))
    async def scenario():
        try:
            handle = await adapter.start(spec)
            assert not isinstance(handle, AdapterFailure), handle
            result = await adapter.collect_result(spec.session_id)
            assert result.summary == 'blocked'
            evidence = await denial_evidence(adapter, spec.session_id)
            assert 'path_outside_scope' in evidence[0].detail['guardReasons']
            assert '拦截' in evidence[0].message
        finally:
            await cleanup(adapter)
    asyncio.run(scenario())


def test_dynamic_tool_inventory_fails_closed(tmp_path, monkeypatch):
    adapter, spec = adapter_fixture(tmp_path, monkeypatch, 'dynamic-tool')
    monkeypatch.setenv('PI_FAKE_TOOL', 'read')
    monkeypatch.setenv('PI_FAKE_ARGS', '{"path":"safe.txt"}')
    async def scenario():
        try:
            handle = await adapter.start(spec)
            assert not isinstance(handle, AdapterFailure), handle
            result = await adapter.collect_result(spec.session_id)
            assert isinstance(result, AdapterFailure)
            assert adapter.guard.status == 'blocked' and 'tool_inventory_changed' in adapter.guard.reasons
        finally:
            await cleanup(adapter)
    asyncio.run(scenario())

@pytest.mark.parametrize('decision', ['approve', 'reject', 'timeout', 'policy-change'])
def test_guard_approval_binding_expiry_and_current_policy(tmp_path, monkeypatch, decision):
    from protocol.generated.python import ApprovalDispatch
    from remote_support import until
    adapter, spec = adapter_fixture(tmp_path, monkeypatch)
    adapter.approval_timeout = 0.15 if decision == 'timeout' else 2
    policy = [1]
    adapter.policy_state = lambda _spec: policy[0]
    expired = []
    async def expire(task):
        expired.append(task)
    adapter.expire_approval = expire
    spec = spec.model_copy(update={'read_only': False, 'allowed_paths': ['**']})
    monkeypatch.setenv('PI_FAKE_TOOL', 'bash')
    monkeypatch.setenv('PI_FAKE_ARGS', '{"command":"cat safe.txt"}')
    async def scenario():
        try:
            handle = await adapter.start(spec)
            assert not isinstance(handle, AdapterFailure), handle
            state = adapter.registry.get(spec.session_id)
            await until(lambda: bool(state.pending_checks))
            identifier, (external, _) = next(iter(state.pending_checks.items()))
            if decision != 'timeout':
                if decision == 'policy-change':
                    policy[0] += 1
                result = await adapter.approve(ApprovalDispatch(approvalId=identifier,
                    decidedAt='2026-10-03T00:00:00Z', externalRequestId=external, decision='reject' if decision == 'reject' else 'approve'))
                assert result is None
            result = await adapter.collect_result(spec.session_id)
            if decision == 'approve':
                assert result.summary == 'synthetic final'
            else:
                assert result.summary == 'blocked'
                await denial_evidence(adapter, spec.session_id)
            if decision == 'timeout':
                assert expired == [spec.task_id]
            repeated = await adapter.approve(ApprovalDispatch(approvalId=identifier, decidedAt='2026-10-03T00:00:00Z', externalRequestId=external, decision='approve'))
            assert isinstance(repeated, AdapterFailure)
        finally:
            await cleanup(adapter)
    asyncio.run(scenario())


def test_same_native_binding_is_locked_and_unsettled_restart_cannot_resume(tmp_path, monkeypatch):
    adapter, spec = adapter_fixture(tmp_path, monkeypatch, 'hold')
    async def stop(process):
        process.kill()
        await process.wait()
        return True
    monkeypatch.setattr('adapters.pi_rpc.terminate_process_tree', stop)
    async def scenario():
        second = PiAdapter(storage_dir=adapter.root, guard_timeout=1)
        try:
            handle = await adapter.start(spec)
            assert not isinstance(handle, AdapterFailure), handle
            continued = spec.model_copy(update={'session_id': 'parallel-session', 'resume_session_id': handle.external_session_id})
            rejected = await second.start(continued)
            assert isinstance(rejected, AdapterFailure)
            state = adapter.registry.get(spec.session_id)
            await state.connection.force_close()
            adapter._release(state)  # Emulate owner death, without a settled record.
            rejected = await second.start(continued)
            assert isinstance(rejected, AdapterFailure) and rejected.code == 'SESSION_NOT_RESUMABLE'
        finally:
            await cleanup(adapter)
            await cleanup(second)
    asyncio.run(scenario())


def test_selector_requires_available_model_and_rechecks_switch_model(tmp_path, monkeypatch):
    adapter, spec = adapter_fixture(tmp_path, monkeypatch, 'switch-model')
    async def scenario():
        try:
            models = await adapter.list_models('local.pi.default')
            assert models.verified and [v.id for v in models.models] == ['synthetic/family/model', 'synthetic/other']
            assert all(v.efforts == [] for v in models.models)
            rejected = await adapter.start(spec.model_copy(update={'model_id_': 'synthetic/absent'}))
            assert isinstance(rejected, AdapterFailure)
            assert not list((adapter.root / 'sessions').rglob('*.jsonl'))
            handle = await adapter.start(spec)
            assert not isinstance(handle, AdapterFailure), handle
            assert (await adapter.collect_result(spec.session_id)).status == 'done'
            failed = await adapter.resume(ResumeRequest(sessionId=handle.session_id,
                externalSessionId=handle.external_session_id, message='resume', taskSpec=spec))
            assert isinstance(failed, AdapterFailure) and failed.code == 'SESSION_NOT_RESUMABLE'
        finally:
            await cleanup(adapter)
    asyncio.run(scenario())


def test_pi_images_and_five_probe_record_are_instance_model_bound(tmp_path, monkeypatch):
    import base64
    from runtime.attachments import verification
    from runtime.attachments.verification_target import target_for
    adapter, _ = adapter_fixture(tmp_path, monkeypatch, 'probe')
    make_inputs = verification.synthetic_inputs
    def synthetic(directory):
        inputs, colors, nonce = make_inputs(directory)
        monkeypatch.setenv('PI_FAKE_ANSWERS', json.dumps([' '.join(colors[:4]), ' '.join(colors[:4]), ' '.join(colors) + ' ' + nonce]))
        encoded = prompt_input('synthetic', inputs)
        assert len(encoded['images']) == 4
        assert encoded['images'][0]['type'] == 'image'
        assert encoded['images'][0]['mimeType'] == 'image/png'
        assert base64.b64decode(encoded['images'][0]['data']) == Path(inputs[0].local_path).read_bytes()
        assert str(inputs[-1].local_path) in encoded['message']
        return inputs, colors, nonce
    monkeypatch.setattr(verification, 'synthetic_inputs', synthetic)
    async def stop(process):
        process.kill()
        await process.wait()
        return True
    monkeypatch.setattr('adapters.pi_rpc.terminate_process_tree', stop)
    async def scenario():
        try:
            record = await verification.verify_images(tmp_path / 'verification', 'pi', 'synthetic/family/model', adapter=adapter)
            assert record['passed'] and record['cleanupConfirmed'], record.get('diagnostics')
            assert all(record['probes'].values()) and set(record['probes']) == {'new', 'resume', 'mixed-five', 'cancel', 'error'}
            assert record['transport'] == 'pi-rpc-images-v1'
            assert not list((adapter.root / 'sessions').rglob('*.jsonl'))
            assert not list((adapter.root / 'bindings').glob('*.json'))
            from runtime.attachments.capabilities import VerificationStore
            store = VerificationStore(tmp_path / 'verification')
            target = target_for('local.pi.default', 'pi', '1.0.1', 'synthetic/family/model', adapter)
            assert store.capability('pi', '1.0.1', 'synthetic/family/model', target=target).verified
            changed = target_for('local.pi.default', 'pi', '1.0.2', 'synthetic/family/model', adapter)
            assert not store.capability('pi', '1.0.2', 'synthetic/family/model', target=changed).verified
            default_before = target_for('local.pi.default', 'pi', '1.0.1', None, adapter)
            monkeypatch.setenv('PI_FAKE_DEFAULT', 'other')
            await adapter.list_models('local.pi.default')
            default_after = target_for('local.pi.default', 'pi', '1.0.1', None, adapter)
            assert default_before['targetRevision'] != default_after['targetRevision']
        finally:
            await cleanup(adapter)
    asyncio.run(scenario())


@pytest.mark.parametrize('mode', ['tamper-arguments', 'nested-call'])
def test_guard_rechecks_parameters_and_nested_calls(tmp_path, monkeypatch, mode):
    adapter, spec = adapter_fixture(tmp_path, monkeypatch, mode)
    monkeypatch.setenv('PI_FAKE_TOOL', 'read')
    monkeypatch.setenv('PI_FAKE_ARGS', '{"path":"safe.txt"}')
    async def scenario():
        try:
            handle = await adapter.start(spec)
            assert not isinstance(handle, AdapterFailure)
            result = await adapter.collect_result(handle.session_id)
            if mode == 'tamper-arguments':
                # The real extension rejects changed arguments even though the
                # host had authorized the original exact arguments.
                assert result.summary == 'blocked'
            else:
                assert result.summary == 'synthetic final'
                await denial_evidence(adapter, spec.session_id)
                assert adapter.registry.get(spec.session_id).tool_blocks[0].tool_call_id == 'nested-call'
        finally:
            await cleanup(adapter)
    asyncio.run(scenario())


def test_unverified_cli_version_never_launches_task(tmp_path, monkeypatch):
    adapter, spec = adapter_fixture(tmp_path, monkeypatch)
    package = tmp_path / 'package/package.json'
    value = json.loads(package.read_text())
    value['version'] = '1.0.2'
    package.write_text(json.dumps(value))
    result = asyncio.run(adapter.start(spec))
    assert isinstance(result, AdapterFailure) and result.code == 'PI_UNCONTROLLED_EXTENSIONS'
    assert not (adapter.root / 'sessions').exists()


@pytest.mark.parametrize('target,allowed', [('file', True), ('parent', False), ('other', False)])
def test_pi_guard_only_reads_exact_verified_attachment(tmp_path, monkeypatch, target, allowed):
    import hashlib
    from protocol.generated.python import AgentInputAttachment
    adapter, spec = adapter_fixture(tmp_path, monkeypatch)
    file = tmp_path / 'attachment.txt'
    file.write_bytes(b'synthetic attachment')
    attachment = AgentInputAttachment(localPath=str(file), attachment=dict(attachmentId='fixture',
        fileName='attachment.txt', kind='file', mimeType='text/plain', sizeBytes=file.stat().st_size,
        sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
    spec = spec.model_copy(update={'input_attachments': [attachment]})
    selected = file if target == 'file' else file.parent if target == 'parent' else file.parent / 'other.txt'
    monkeypatch.setenv('PI_FAKE_TOOL', 'read')
    monkeypatch.setenv('PI_FAKE_ARGS', json.dumps({'path': str(selected)}))
    async def scenario():
        try:
            handle = await adapter.start(spec)
            assert not isinstance(handle, AdapterFailure), handle
            result = await adapter.collect_result(handle.session_id)
            assert not isinstance(result, AdapterFailure)
            if allowed:
                assert result.summary == 'synthetic final'
            else:
                assert result.summary == 'blocked'
                await denial_evidence(adapter, spec.session_id)
        finally:
            await cleanup(adapter)
    asyncio.run(scenario())


def test_model_catalog_waits_for_current_availability_snapshot(tmp_path, monkeypatch):
    adapter, _ = adapter_fixture(tmp_path, monkeypatch, 'catalog-lazy')
    result = asyncio.run(adapter.list_models('local.pi.default'))
    assert result.verified and [m.id for m in result.models] == ['synthetic/family/model', 'synthetic/other']


def test_empty_model_catalog_is_not_a_verified_selection(tmp_path, monkeypatch):
    adapter, _ = adapter_fixture(tmp_path, monkeypatch, 'empty-catalog')
    result = asyncio.run(adapter.list_models('local.pi.default'))
    assert not result.verified and result.models == [] and result.reason


def test_replacement_resume_preserves_context_after_tool_block(tmp_path, monkeypatch):
    adapter, spec = adapter_fixture(tmp_path, monkeypatch, 'recall')
    spec = spec.model_copy(update={'objective': 'remember SYNTHETIC_CONTEXT_58'})
    async def scenario():
        try:
            handle = await adapter.start(spec)
            assert not isinstance(handle, AdapterFailure)
            assert (await adapter.collect_result(handle.session_id)).summary == 'SYNTHETIC_CONTEXT_58'
            monkeypatch.setenv('PI_FAKE_TOOL', 'read')
            monkeypatch.setenv('PI_FAKE_ARGS', '{"path":"../outside"}')
            request = ResumeRequest(sessionId=handle.session_id, externalSessionId=handle.external_session_id,
                message='attempt read', taskSpec=spec)
            assert await adapter.resume(request) is None
            assert (await adapter.collect_result(handle.session_id)).summary == 'blocked'
            await denial_evidence(adapter, handle.session_id)
            monkeypatch.delenv('PI_FAKE_TOOL')
            assert await adapter.resume(request.model_copy(update={'message': 'recall'})) is None
            assert (await adapter.collect_result(handle.session_id)).summary == 'SYNTHETIC_CONTEXT_58'
            assert adapter.registry.get(handle.session_id).external_session_id == handle.external_session_id
        finally:
            await cleanup(adapter)
    asyncio.run(scenario())


def test_restart_can_resume_only_a_durably_stopped_binding(tmp_path, monkeypatch):
    adapter, spec = adapter_fixture(tmp_path, monkeypatch, 'recall')
    spec = spec.model_copy(update={'objective': 'remember SYNTHETIC_CONTEXT_58'})
    async def scenario():
        restarted = PiAdapter(storage_dir=adapter.root, guard_timeout=1)
        try:
            handle = await adapter.start(spec)
            assert not isinstance(handle, AdapterFailure)
            await adapter.collect_result(handle.session_id)
            result = await restarted.resume(ResumeRequest(sessionId=handle.session_id,
                externalSessionId=handle.external_session_id, message='recall', taskSpec=spec))
            assert result is None, result
            assert (await restarted.collect_result(handle.session_id)).summary == 'SYNTHETIC_CONTEXT_58'
        finally:
            await cleanup(adapter)
            await cleanup(restarted)
    asyncio.run(scenario())
