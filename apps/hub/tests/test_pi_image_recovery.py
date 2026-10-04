import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from protocol.generated import python as dto

from adapters.pi_adapter import PiGuardError, PiModelError, denied
from adapters.image_support import image_model_support
from core.errors import HubError
from runtime.attachments.verification import synthetic_inputs
from runtime.attachments.verification_jobs import VerificationCoordinator
from runtime.attachments.verification_target import target_for
from runtime.attachments.verification_recovery import pi_processes_absent
from test_pi_adapter import adapter_fixture, cleanup
from test_pi_repair2 import integrated
from test_local_image_jobs import setup


TEXT = 'deepseek/deepseek-v4-pro'
VISION = 'deepseek/deepseek-v4-flash-vision-exp'
OTHER_VISION = 'synthetic/other-vision'


def catalog(adapter):
    adapter._models({'models': [
        {'provider': 'deepseek', 'id': 'deepseek-v4-pro', 'input': ['text']},
        {'provider': 'deepseek', 'id': 'deepseek-v4-flash-vision-exp', 'input': ['text', 'image']},
        {'provider': 'synthetic', 'id': 'other-vision', 'input': ['image']},
    ]}, {'model': {'provider': 'deepseek', 'id': 'deepseek-v4-pro'}})


@pytest.mark.parametrize('model', [None, TEXT])
def test_text_model_image_rejected_before_any_process_without_poisoning_guard(tmp_path, monkeypatch, model):
    adapter, spec = adapter_fixture(tmp_path, monkeypatch)
    catalog(adapter)
    spec = spec.model_copy(update={'model_id_': model, 'input_attachments': [synthetic_inputs(tmp_path)[0][0]]})
    before = adapter.guard.model_dump()
    calls = []
    async def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError('must not launch a process for known text-only input')
    monkeypatch.setattr(adapter.runner, 'run', forbidden)
    monkeypatch.setattr(adapter.runner, 'start', forbidden)
    result = asyncio.run(adapter.start(spec))
    assert result.code == 'AGENT_IMAGE_UNSUPPORTED'
    assert json.loads(result.raw)['cleanupConfirmed'] is True
    assert not calls and adapter.guard.model_dump() == before
    assert not adapter.registry.values() and not (adapter.root / 'sessions').exists()


@pytest.mark.parametrize('error,code,changed', [
    (PiModelError('model missing'), 'VALIDATION_FAILED', False),
    (RuntimeError('transport'), 'INTERNAL', False),
    (ValueError('bad input'), 'INTERNAL', False),
    (HubError('PATH_NOT_ALLOWED', 'invalid workspace'), 'PATH_NOT_ALLOWED', False),
    (PiGuardError('handshake'), 'PI_GUARD_UNAVAILABLE', True),
])
def test_only_explicit_guard_failures_change_guard(tmp_path, monkeypatch, error, code, changed):
    adapter, spec = adapter_fixture(tmp_path, monkeypatch)
    before = adapter.guard.model_dump()
    async def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(adapter, '_new_connection', fail)
    result = asyncio.run(adapter.start(spec))
    assert result.code == code
    assert (adapter.guard.model_dump() != before) is changed
    assert json.loads(result.raw)['cleanupConfirmed'] is True


def test_post_handshake_binding_failure_is_not_guard_failure_and_closes_process(tmp_path, monkeypatch):
    adapter, spec = adapter_fixture(tmp_path, monkeypatch)
    def fail_binding(*args):
        raise ValueError('invalid native identity')
    monkeypatch.setattr(adapter, '_bind', fail_binding)
    async def scenario():
        result = await adapter.start(spec)
        assert result.code == 'INTERNAL' and adapter.guard.status == 'ready'
        assert json.loads(result.raw)['cleanupConfirmed'] is True
        assert not adapter.failed_starts
        assert not list((adapter.root / 'sessions').iterdir())
    asyncio.run(scenario())


@pytest.mark.parametrize('metadata', [False, True])
def test_adapter_reports_unconfirmed_cleanup_and_retains_exact_owned_process(tmp_path, monkeypatch, metadata):
    from adapters.pi_rpc import PiRPC
    adapter, spec = adapter_fixture(tmp_path, monkeypatch)
    if metadata:
        spec = spec.model_copy(update={'model_id_': None})
    else:
        def bad_binding(*args):
            raise ValueError('binding failed')
        monkeypatch.setattr(adapter, '_bind', bad_binding)
    original = PiRPC.force_close
    async def refused(self):
        return False
    monkeypatch.setattr(PiRPC, 'force_close', refused)
    async def scenario():
        try:
            result = await adapter.start(spec)
            assert result.code == 'INTERNAL' and adapter.guard.status == 'ready'
            evidence = json.loads(result.raw)
            assert evidence['cleanupConfirmed'] is False and evidence['executionMayStillBeRunning'] is True
            state = adapter.failed_start_state(spec.session_id)
            assert state is not None and state.process.returncode is None
            assert evidence['orphanProcessIds'] == [state.process.pid]
            monkeypatch.setattr(PiRPC, 'force_close', original)
            cancelled = await adapter.cancel(dto.CancelRequest(sessionId=spec.session_id, mode='force'))
            assert cancelled.outcome == 'force_killed' and not cancelled.orphan_process_ids
            assert state.process.returncode is not None and not adapter.failed_starts
        finally:
            for state in list(adapter.failed_starts.values()):
                await original(state.connection)
                adapter._release(state)
    asyncio.run(scenario())


@pytest.mark.parametrize('uncertain', [False, True])
def test_failed_start_without_handle_has_failed_terminal_or_explicit_uncertainty(tmp_path, monkeypatch, uncertain):
    async def scenario():
        coordinator, adapter, request = setup(tmp_path, monkeypatch)
        calls = []
        async def fail(spec):
            calls.append(spec.session_id)
            result = dto.AdapterFailure(kind='capability_missing', code='AGENT_IMAGE_UNSUPPORTED', message='synthetic', retryable=False)
            return result.model_copy(update={'raw': json.dumps({'cleanupConfirmed': False,
                'executionMayStillBeRunning': True, 'orphanProcessIds': [12345]})}) if uncertain else result
        adapter.start = fail
        job = await coordinator.start(request(), 'first', 'req')
        await coordinator.tasks[job.job_id]
        view = coordinator.view(job.job_id)
        assert view.status == ('interrupted' if uncertain else 'failed')
        assert view.cleanup_state == ('unconfirmed' if uncertain else 'confirmed')
        assert view.slot_held is uncertain and view.execution_may_still_be_running is uncertain
        if uncertain:
            with pytest.raises(HubError):
                await coordinator.start(request(), 'second', 'req')
        else:
            second = await coordinator.start(request(), 'second', 'req')
            await coordinator.tasks[second.job_id]
            assert len(calls) == 2 and coordinator.view(second.job_id).status == 'failed'
    asyncio.run(scenario())


def test_real_guard_start_failure_releases_verification_slot_without_inference(tmp_path, monkeypatch):
    adapter, _ = adapter_fixture(tmp_path, monkeypatch, 'bad-handshake')
    # Keep the coordinator's target stable; only the synthetic adapter executes
    # the deliberately invalid guard handshake. No prompt/model is sent.
    async def resolve(identifier, model):
        return target_for(identifier, 'pi', '1.0.1', model, adapter), adapter, True
    async def scenario():
        coordinator = VerificationCoordinator(tmp_path / 'verification', resolve)
        target = (await resolve('local.pi.default', 'synthetic/family/model'))[0]
        raw = dict(agentId='local.pi.default', modelId='synthetic/family/model',
            expectedTargetRevision=target['targetRevision'], acknowledgeModelUsage=True)
        try:
            for key in ('first', 'retry'):
                job = await coordinator.start(raw, key, 'req')
                await coordinator.tasks[job.job_id]
                result = coordinator.view(job.job_id)
                assert result.status == 'failed' and result.cleanup_state == 'confirmed'
                assert not result.slot_held and not result.execution_may_still_be_running
                assert result.diagnostics.new_start.code == 'PI_GUARD_UNAVAILABLE'
                assert not result.result.passed
            assert not list((adapter.root / 'sessions').rglob('*.jsonl'))
        finally:
            await coordinator.close()
            await cleanup(adapter)
    asyncio.run(scenario())


@pytest.mark.parametrize('absence,handle,pid,orphan,pending,diagnostic', [
    (True, False, False, False, False, 'adapter_failure'),
    (False, False, False, False, False, 'adapter_failure'),
    (True, True, False, False, False, 'adapter_failure'),
    (True, False, True, False, False, 'adapter_failure'),
    (True, False, False, True, False, 'adapter_failure'),
    (True, False, False, False, True, 'adapter_failure'),
    (True, False, False, False, False, 'exception'),
])
def test_persisted_failure_recovery_requires_absent_processes_and_returned_failure(
        tmp_path, monkeypatch, absence, handle, pid, orphan, pending, diagnostic):
    async def scenario():
        coordinator, adapter, request = setup(tmp_path, monkeypatch)
        job = await coordinator.start(request(), 'paid-intent', 'req')
        await coordinator.cancel(job.job_id, 'cancel-before-start')
        await coordinator.tasks[job.job_id]
        saved = coordinator.job(job.job_id)
        saved['view']['target'].update(agentType='pi', transport='pi-rpc-images-v1')
        saved['view'].update(status='interrupted', cleanupState='unconfirmed', slotHeld=True,
            executionMayStillBeRunning=True, orphanProcessIds=[12345] if orphan else [])
        saved['resources'] = [dict(sessionId='old-image-probe', internal=True, handleKnown=handle, stopped=False,
                                    **({'processId': 12345} if pid else {}))]
        saved['diagnostics'] = {'new.start': {'result': diagnostic, 'kind': 'capability_missing', 'code': 'PI_GUARD_UNAVAILABLE'}}
        saved['outcomes'] = {'new': False}
        saved['launchPending'] = pending
        directory = Path(saved['directory'])
        directory.mkdir(exist_ok=True)
        (directory / 'synthetic.txt').write_text('test only')
        coordinator.save()
        restarted = VerificationCoordinator(tmp_path, coordinator.resolve)
        await restarted.recover_failed_starts(lambda root: absence)
        value = restarted.view(job.job_id)
        expected = absence and not (handle or pid or orphan or pending) and diagnostic == 'adapter_failure'
        assert value.status == ('failed' if expected else 'interrupted')
        assert value.slot_held is (not expected)
        assert value.cleanup_state == ('confirmed' if expected else 'unconfirmed')
        assert directory.exists() is (not expected)
        assert not adapter.started and not restarted.tasks
        assert restarted.data['keys']['paid-intent']['jobId'] == job.job_id
        if expected:
            assert not value.result.passed
            again = VerificationCoordinator(tmp_path, coordinator.resolve)
            assert not again.view(job.job_id).slot_held
    asyncio.run(scenario())


def test_pi_matrix_lists_image_models_hides_text_default_and_post_rejects_before_detection(tmp_path, monkeypatch):
    async def scenario():
        system, adapter = integrated(tmp_path, monkeypatch, '')
        catalog(adapter)
        coordinator = system.worker.attachments.verifications
        # Avoid stale scenario model from the general PI fixture.
        scene = system.chat.repository.scene('analyze')
        system.chat.repository.save_scene('analyze', dto.SaveLocalSceneInput(expectedVersion=scene.version,
            roles=[r.model_copy(update={'model_id_': TEXT}) for r in scene.roles]))
        counts = []
        async def detect():
            counts.append('detect')
            return SimpleNamespace(detected_version='1.0.1')
        async def forbidden(*args, **kwargs):
            raise AssertionError('known model metadata must not launch or reload')
        monkeypatch.setattr(adapter, 'detect', detect)
        monkeypatch.setattr(adapter, 'list_models', forbidden)
        monkeypatch.setattr(adapter.runner, 'run', forbidden)
        monkeypatch.setattr(adapter.runner, 'start', forbidden)
        try:
            page = await coordinator.matrix(agent_id='local.pi.default')
            assert {r.target.model_id_ for r in page.items} == {VISION, OTHER_VISION}
            assert all(r.status == 'unverified' for r in page.items)
            for model in (None, TEXT):
                before = list(counts)
                raw = dict(agentId='local.pi.default', expectedTargetRevision='cached-old-page', acknowledgeModelUsage=True)
                if model:
                    raw['modelId'] = model
                result = await system.local.post('/api/v1/agents/image-verification-jobs', json=raw,
                    headers={'X-HQ-Client-Features': 'pi-v1', 'Origin': 'http://127.0.0.1', 'Idempotency-Key': 'reject-' + str(model)})
                assert result.status_code == 422 and result.json()['error']['code'] == 'AGENT_IMAGE_UNSUPPORTED'
                assert counts == before
                assert not coordinator.data['jobs'] and not coordinator.data['keys']
            target = target_for('local.pi.default', 'pi', '1.0.1', None, adapter)
            coordinator.store.record('pi', '1.0.1', None, {'new': False}, [], target=target, completed=False)
            assert None not in {r.target.model_id_ for r in (await coordinator.matrix()).items}
            history = await coordinator.matrix(inactive=True)
            row = next(r for r in history.items if r.target.model_id_ is None)
            assert row.status == 'unavailable' and not row.last_record.passed
            adapter.default_model = VISION
            assert {r.target.model_id_ for r in (await coordinator.matrix()).items} == {None, VISION, OTHER_VISION}
            adapter.model_inputs = {}
            assert image_model_support(adapter, None) is None
            page = await coordinator.matrix()
            assert {r.target.model_id_ for r in page.items} == {None, TEXT}
        finally:
            await system.close()
            await cleanup(adapter)
    asyncio.run(scenario())


def test_hub_attachment_startup_recovers_persisted_text_default_failure(tmp_path, monkeypatch):
    async def scenario():
        system, adapter = integrated(tmp_path, monkeypatch, '')
        coordinator = system.worker.attachments.verifications
        catalog(adapter)
        async def resolve(identifier, model):
            return target_for(identifier, 'pi', '1.0.1', model, adapter), adapter, True
        # Seed a durable job without executing a model; then reproduce the exact
        # returned-failure/no-handle state written by the prior implementation.
        coordinator.resolve = resolve
        coordinator.preflight = None
        adapter.default_model = VISION
        target = (await resolve('local.pi.default', None))[0]
        job = await coordinator.start(dict(agentId='local.pi.default', expectedTargetRevision=target['targetRevision'],
            acknowledgeModelUsage=True), 'old-key', 'old-request')
        await coordinator.cancel(job.job_id, 'cancel-queued')
        await coordinator.tasks[job.job_id]
        saved = coordinator.job(job.job_id)
        saved['view'].update(status='interrupted', cleanupState='unconfirmed', slotHeld=True, executionMayStillBeRunning=True)
        saved['resources'] = [dict(sessionId='old-probe', internal=True, handleKnown=False, stopped=False)]
        saved['diagnostics'] = {'new.start': {'result': 'adapter_failure', 'code': 'PI_GUARD_UNAVAILABLE', 'kind': 'capability_missing'}}
        saved['outcomes'] = {'new': False}
        saved['launchPending'] = False
        coordinator.save()
        adapter.default_model = TEXT
        service = system.worker.attachments
        service.verifications = VerificationCoordinator.for_service(service)
        checks = []
        def absent(root):
            checks.append(root)
            return True
        monkeypatch.setattr('runtime.attachments.verification_recovery.pi_processes_absent', absent)
        try:
            await system.chat.start()
            view = service.verifications.view(job.job_id)
            assert checks and view.status == 'failed' and view.cleanup_state == 'confirmed'
            assert not view.slot_held and not view.execution_may_still_be_running
            assert view.result is not None and not view.result.passed
        finally:
            await system.close()
            await cleanup(adapter)
    asyncio.run(scenario())


def test_actual_process_absence_observer_does_not_spawn_helpers(tmp_path, monkeypatch):
    # Exercise OS enumeration, including another Node process with a private
    # PI session-dir marker, without running PI or any model.
    import shutil
    import subprocess
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node required for owned-process evidence fixture')
    directory = tmp_path / 'pi' / 'sessions'
    directory.mkdir(parents=True)
    child = subprocess.Popen([node, '-e', 'setTimeout(()=>{}, 15000)', '--', '--session-dir', str(directory / 'synthetic')],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert pi_processes_absent(tmp_path) is False
    finally:
        child.terminate()
        child.wait(timeout=5)
    # On inaccessible foreign runtimes the conservative answer may remain False;
    # it must never be True while the owned child above is alive.
    assert isinstance(pi_processes_absent(tmp_path), bool)
