import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest
from protocol.generated import python as dto
from core.errors import HubError
from orchestrator.tests.fakes import FakeAdapter
from remote_support import System, until
from runtime.attachments import verification
from runtime.attachments.capabilities import REQUIRED_PROBES
from runtime.attachments.verification_jobs import VerificationCoordinator, diagnostics_view
from runtime.attachments.verification_target import target_for


class ProbeAdapter(FakeAdapter):
    def __init__(self):
        super().__init__()
        self.version = '1.2.3'
        self.verification_configuration = {'model': 'model-a'}
        self.hold = False
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.stop = 'force_killed'

    async def detect(self):
        return SimpleNamespace(detected_version=self.version)

    async def stream_events(self, identifier):
        self.entered.set()
        if self.hold:
            await self.release.wait()
        if False:
            yield

    async def cancel(self, value):
        self.cancels.append(value)
        return dto.CancelResult(outcome=self.stop, completedAt='2026-10-01T00:00:00Z')


def setup(tmp_path, monkeypatch, *, budget=900):
    adapter = ProbeAdapter()
    original = verification.synthetic_inputs
    def inputs(path):
        values, colors, nonce = original(path)
        adapter.result = adapter.result.model_copy(update={'summary': ' '.join(colors) + ' ' + nonce})
        return values, colors, nonce
    monkeypatch.setattr(verification, 'synthetic_inputs', inputs)
    async def resolve(identifier, model):
        return target_for(identifier, 'claude', adapter.version, model, adapter), adapter, True
    coordinator = VerificationCoordinator(tmp_path, resolve, budget=budget, cleanup_budget=0.2)
    def request(model=None):
        target = target_for('agent', 'claude', adapter.version, model, adapter)
        return dict(agentId='agent', expectedTargetRevision=target['targetRevision'], acknowledgeModelUsage=True,
                    **({'modelId': model} if model is not None else {}))
    return coordinator, adapter, request


@pytest.mark.parametrize('confirmation', [None, False, 'true', 1])
def test_confirmation_is_strict_before_any_paid_intent(tmp_path, monkeypatch, confirmation):
    async def scenario():
        coordinator, adapter, request = setup(tmp_path, monkeypatch)
        value = request()
        if confirmation is None:
            value.pop('acknowledgeModelUsage')
        else:
            value['acknowledgeModelUsage'] = confirmation
        with pytest.raises(HubError) as error:
            await coordinator.start(value, 'key', 'request')
        assert error.value.code == 'VALIDATION_FAILED'
        assert not adapter.started and not coordinator.data['keys']
    asyncio.run(scenario())


def test_same_intent_single_slot_tombstone_and_exact_selector(tmp_path, monkeypatch):
    async def scenario():
        coordinator, adapter, request = setup(tmp_path, monkeypatch)
        adapter.hold = True
        job = await coordinator.start(request(), 'key', 'req-1')
        assert (await coordinator.start(request(), 'key', 'req-2')).job_id == job.job_id
        await adapter.entered.wait()
        with pytest.raises(HubError) as error:
            await coordinator.start(request(), 'other-key', 'req-3')
        assert error.value.detail == {'reason': 'verification_in_progress', 'activeJobId': job.job_id}
        with pytest.raises(HubError) as error:
            await coordinator.start(request('another-model'), 'key', 'req-4')
        assert error.value.code == 'IDEMPOTENCY_MISMATCH'
        assert len(adapter.started) == 1
        await coordinator.cancel(job.job_id, 'cancel')
        await until(lambda: not coordinator.tasks)
        coordinator.data['jobs'].pop(job.job_id)
        coordinator.save()
        with pytest.raises(HubError) as error:
            await coordinator.start(request(), 'key', 'req-5')
        assert error.value.code == 'NOT_FOUND' and len(adapter.started) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('stop', ['force_killed', 'refused'])
def test_cancel_only_owned_handles_keeps_unconfirmed_slot(tmp_path, monkeypatch, stop):
    async def scenario():
        coordinator, adapter, request = setup(tmp_path, monkeypatch)
        adapter.hold, adapter.stop = True, stop
        job = await coordinator.start(request(), 'key', 'req')
        await adapter.entered.wait()
        view, status = await coordinator.cancel(job.job_id, 'cancel')
        assert status == 202 and view.status == 'cancel_requested'
        await until(lambda: not coordinator.tasks)
        view = coordinator.view(job.job_id)
        assert view.status == ('cancelled' if stop == 'force_killed' else 'interrupted')
        assert view.cleanup_state == ('confirmed' if stop == 'force_killed' else 'unconfirmed')
        assert view.slot_held is (stop == 'refused')
        assert view.execution_may_still_be_running is (stop == 'refused')
        assert len(adapter.started) == 1 and not adapter.resumed
        assert all(c.session_id == adapter.started[0].session_id for c in adapter.cancels)
        assert not view.applied_to_current_target
        adapter.stop = 'force_killed'
        await coordinator.cancel(job.job_id, 'cancel-again')
        assert not coordinator.view(job.job_id).slot_held
    asyncio.run(scenario())


def test_all_five_and_confirmed_cleanup_required_for_bound_capability(tmp_path, monkeypatch):
    async def scenario():
        coordinator, adapter, request = setup(tmp_path, monkeypatch)
        job = await coordinator.start(request(), 'key', 'req')
        await coordinator.tasks[job.job_id]
        view = coordinator.view(job.job_id)
        assert view.status == 'succeeded' and view.cleanup_state == 'confirmed'
        assert all(p.state == 'passed' for p in view.probes.__dict__.values())
        target = view.target.model_dump(by_alias=True, mode='json', exclude_none=True)
        assert coordinator.store.capability('claude', adapter.version, target=target).verified
        assert not coordinator.store.capability('claude', adapter.version).verified
        assert not coordinator.store.capability('claude', adapter.version, target={**target, 'agentId': 'other'}).verified
        assert not __import__('pathlib').Path(coordinator.job(job.job_id)['directory']).exists()
        assert all(r['internal'] and r['stopped'] for r in coordinator.job(job.job_id)['resources'])
    asyncio.run(scenario())


def test_target_change_interrupts_following_probes_and_prevents_publish(tmp_path, monkeypatch):
    async def scenario():
        coordinator, adapter, request = setup(tmp_path, monkeypatch)
        old = request()
        adapter.version = '1.2.4'
        with pytest.raises(HubError) as error:
            await coordinator.start(old, 'before-start', 'req')
        assert error.value.detail['reason'] == 'target_changed'
        adapter.hold = True
        job = await coordinator.start(request(), 'key', 'req')
        await adapter.entered.wait()
        adapter.verification_configuration = {'model': 'model-b'}
        adapter.release.set()
        await coordinator.tasks[job.job_id]
        assert coordinator.view(job.job_id).status == 'interrupted'
        assert not coordinator.view(job.job_id).applied_to_current_target
        assert coordinator.job(job.job_id)['failureReason'] == 'target_changed'
        assert not adapter.resumed and len(adapter.started) == 1
    asyncio.run(scenario())


def test_five_results_do_not_substitute_for_confirmed_owned_cleanup(tmp_path, monkeypatch):
    async def scenario():
        coordinator, adapter, request = setup(tmp_path, monkeypatch)
        original = adapter.cancel
        refuse = [True]
        async def cancel(value):
            if refuse[0] and value.session_id == adapter.started[0].session_id:
                adapter.cancels.append(value)
                return dto.CancelResult(outcome='refused', completedAt='2026-10-01T00:00:00Z')
            return await original(value)
        adapter.cancel = cancel
        job = await coordinator.start(request(), 'key', 'req')
        await coordinator.tasks[job.job_id]
        view = coordinator.view(job.job_id)
        assert all(coordinator.job(job.job_id)['outcomes'].values())
        assert view.status == 'interrupted' and view.cleanup_state == 'unconfirmed'
        assert view.execution_may_still_be_running and view.slot_held
        assert not view.result.passed and not view.applied_to_current_target
        assert len({c.session_id for c in adapter.cancels}) == 2
        refuse[0] = False
        await coordinator.cancel(job.job_id, 'reconcile')
        assert not coordinator.view(job.job_id).slot_held
        assert not coordinator.view(job.job_id).applied_to_current_target
        assert len(adapter.started) == 2  # Reconciliation never repeats a probe.
    asyncio.run(scenario())


def test_restart_interrupted_does_not_replay_and_retains_uncertainty(tmp_path, monkeypatch):
    async def scenario():
        coordinator, adapter, request = setup(tmp_path, monkeypatch)
        adapter.hold = True
        job = await coordinator.start(request(), 'key', 'req')
        await adapter.entered.wait()
        recovered = VerificationCoordinator(tmp_path, coordinator.resolve)
        view = recovered.view(job.job_id)
        assert view.status == 'interrupted' and view.cleanup_state == 'unconfirmed' and view.slot_held
        assert view.result is not None and not view.result.passed
        assert not recovered.tasks and len(adapter.started) == 1
        await recovered.cancel(job.job_id, 'check')
        assert recovered.view(job.job_id).slot_held  # Empty new registry proves nothing.
        await coordinator.close()
    asyncio.run(scenario())


def test_deadline_cleans_without_retry_and_queued_cancel_starts_nothing(tmp_path, monkeypatch):
    async def scenario():
        coordinator, adapter, request = setup(tmp_path, monkeypatch, budget=0.5)
        adapter.hold = True
        job = await coordinator.start(request(), 'key', 'req')
        await coordinator.tasks[job.job_id]
        assert coordinator.view(job.job_id).status == 'interrupted'
        assert not coordinator.view(job.job_id).slot_held
        job = await coordinator.start(request(), 'next', 'req')
        before = len(adapter.started)
        await coordinator.cancel(job.job_id, 'queued-cancel')
        await until(lambda: not coordinator.tasks)
        assert len(adapter.started) == before and coordinator.view(job.job_id).status == 'cancelled'
    asyncio.run(scenario())


def test_diagnostics_are_closed_camelcase_safe_values():
    value = diagnostics_view({'new.start': {'result': 'exception', 'exceptionType': 'SecretVendorClass',
        'message': '/secret', 'raw': 'token', 'code': 'None', 'elapsedMs': 5, 'kind': 'arbitrary-output'},
        'mixed-five.recognition': {'matched': True}, 'untrusted': {'code': 'INTERNAL'},
        'cancel.stop': {'orphanProcessIds': [123], 'outcome': 'refused'}})
    assert value == {'newStart': {'result': 'exception', 'exceptionType': 'UnknownError', 'elapsedMs': 5},
                     'mixedFiveRecognition': {'matched': True},
                     'cancelStop': {'orphanProcessIds': [123], 'outcome': 'refused'}}


def test_adapter_cannot_transfer_verification_ownership_to_user_session(tmp_path, monkeypatch):
    async def scenario():
        coordinator, adapter, request = setup(tmp_path, monkeypatch)
        original = adapter.start
        async def wrong(spec):
            handle = await original(spec)
            return handle.model_copy(update={'session_id': 'unrelated-user-session'})
        adapter.start = wrong
        job = await coordinator.start(request(), 'key', 'req')
        await coordinator.tasks[job.job_id]
        assert coordinator.view(job.job_id).status == 'interrupted'
        assert coordinator.view(job.job_id).slot_held
        assert not adapter.cancels and not adapter.resumed
        assert all(r['sessionId'] != 'unrelated-user-session' for r in coordinator.job(job.job_id)['resources'])
    asyncio.run(scenario())


def test_final_target_check_holds_slot_and_repeated_cancel_still_commits_terminal(tmp_path, monkeypatch):
    async def scenario():
        coordinator, adapter, request = setup(tmp_path, monkeypatch)
        entered = asyncio.Event()
        original = coordinator.current
        async def current(job):
            if job['view']['cleanupState'] == 'confirmed':
                entered.set()
                await asyncio.Event().wait()
            return await original(job)
        coordinator.current = current
        job = await coordinator.start(request(), 'key', 'req')
        await entered.wait()
        assert coordinator.view(job.job_id).slot_held
        with pytest.raises(HubError) as error:
            await coordinator.start(request(), 'another-key', 'req2')
        assert error.value.detail['reason'] == 'verification_in_progress'
        await asyncio.gather(*(coordinator.cancel(job.job_id, 'cancel') for _ in range(10)))
        await until(lambda: not coordinator.tasks)
        view = coordinator.view(job.job_id)
        assert view.status == 'cancelled' and view.cleanup_state == 'confirmed'
        assert not view.applied_to_current_target and not view.result.passed and not view.slot_held
    asyncio.run(scenario())


def test_http_auth_cross_version_idempotency_progress_request_id(tmp_path):
    async def scenario():
        system = System(tmp_path, hold=True)
        try:
            system.local.headers['Origin'] = 'http://127.0.0.1'
            async def agents():
                return [dto.AgentView(id='agent', adapterId='claude', version='1.2.3', displayName='fake',
                    status='ready', detectedAt='2026-10-01T00:00:00Z', capabilities=[], assignedRoles=[], isPrimaryFor=[])]
            async def detect():
                return SimpleNamespace(detected_version='1.2.3')
            system.ports.agents = SimpleNamespace(list_agents=agents)
            system.adapter.detect = detect
            system.tasks.directory.candidates = tuple(replace(a, adapter_id='claude') for a in system.tasks.directory.candidates)
            path = '/agents/image-verification-jobs'
            denied = await system.local.get('/api/v2/agents/image-verifications', headers={'X-Request-Id': 'auth-test'})
            assert denied.status_code == 401 and denied.headers['cache-control'] == 'no-store'
            assert denied.headers['x-request-id'] == denied.json()['requestId'] == 'auth-test'
            from core.local_auth import COOKIE_NAME
            auth = system.application.local_auth
            system.local.cookies.set(COOKIE_NAME, auth.exchange(auth.issue_code()))
            page = await system.local.get('/api/v2/agents/image-verifications')
            assert page.status_code == 200, page.text
            target = page.json()['data']['items'][0]['target']
            value = dict(agentId='agent', expectedTargetRevision=target['targetRevision'], acknowledgeModelUsage=True)
            for confirm in [None, False, 'true', 1]:
                body = {**value, 'acknowledgeModelUsage': confirm}
                if confirm is None:
                    body.pop('acknowledgeModelUsage')
                rejected = await system.local.post('/api/v2' + path, json=body, headers={'Idempotency-Key': 'paid'})
                assert rejected.status_code == 422 and rejected.headers['cache-control'] == 'no-store'
            first = await system.local.post('/api/v1' + path, json=value,
                headers={'Idempotency-Key': 'paid', 'X-Request-Id': 'paid-request'})
            assert first.status_code == 202, first.text
            identifier = first.json()['data']['jobId']
            replay = await system.local.post('/api/v2' + path, json=value, headers={'Idempotency-Key': 'paid'})
            assert replay.status_code == 202 and replay.json()['data']['jobId'] == identifier
            assert first.json()['data']['requestId'] == first.json()['requestId'] == first.headers['x-request-id'] == 'paid-request'
            invalid = await system.local.post('/api/v2' + path + '/' + identifier + '/cancellations',
                json={'force': True}, headers={'Idempotency-Key': 'cancel'})
            assert invalid.status_code == 422
            cancelled = await system.local.post('/api/v2' + path + '/' + identifier + '/cancellations',
                json={}, headers={'Idempotency-Key': 'cancel'})
            assert cancelled.status_code in (200, 202), cancelled.text
            await system.worker.attachments.verifications.close()
        finally:
            await system.close()
    asyncio.run(scenario())


def test_matrix_snapshot_cursor_history_and_real_scene_selectors(tmp_path, monkeypatch):
    async def scenario():
        coordinator, adapter, request = setup(tmp_path, monkeypatch)
        class Capabilities:
            agents = {'agent': SimpleNamespace(adapter_id='claude'), 'agent-b': SimpleNamespace(adapter_id='claude')}
            usages = {('agent', 'model-scene'): [{'sceneId': 'scene', 'roleId': 'planner'}]}
            async def refresh(self):
                pass
        coordinator.capabilities = Capabilities()
        coordinator.store.record('claude', adapter.version, None, {k: True for k in REQUIRED_PROBES}, ['image/png'])
        page = await coordinator.matrix(limit=1)
        assert page.has_more and page.next_cursor
        row = page.items[0]
        assert not row.passed and row.last_record.passed
        assert row.invalidation_reasons == ['legacy_unbound']
        page2 = await coordinator.matrix(limit=1, cursor=page.next_cursor)
        assert page2.items[0].target.model_id_ == 'model-scene' and page2.items[0].in_use
        with pytest.raises(HubError):
            await coordinator.matrix(agent_id='agent', limit=1, cursor=page.next_cursor)
        explicit = await coordinator.matrix(agent_id='agent', model='extra-model')
        assert not explicit.items[0].in_use and explicit.items[0].status == 'unverified'
        with pytest.raises(HubError):
            await coordinator.matrix(model='extra-model')
        job = await coordinator.start(request('retired-model'), 'retired', 'req')
        await coordinator.tasks[job.job_id]
        normal = await coordinator.matrix()
        history = await coordinator.matrix(inactive=True)
        assert 'retired-model' not in [r.target.model_id_ for r in normal.items]
        assert 'retired-model' in [r.target.model_id_ for r in history.items]
        coordinator.store.record('claude', adapter.version, 'retired-legacy', {k: True for k in REQUIRED_PROBES}, ['image/png'])
        legacy = await coordinator.matrix(inactive=True)
        legacy = [r for r in legacy.items if r.target.model_id_ == 'retired-legacy']
        assert len(legacy) == 2
        assert all(r.last_record.passed and not r.passed and r.invalidation_reasons == ['legacy_unbound'] for r in legacy)
        adapter.version = '1.2.4'
        stale = await coordinator.matrix(agent_id='agent', model='retired-model')
        assert stale.items[0].last_record.passed and not stale.items[0].passed
        assert stale.items[0].invalidation_reasons == ['cli_version_changed']
    asyncio.run(scenario())


def test_configuration_snapshot_ignores_tokens_and_tracks_default_model(tmp_path, monkeypatch):
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path))
    config = tmp_path / 'settings.json'
    config.write_text(json.dumps({'model': 'a', 'theme': 'dark', 'env': {'ANTHROPIC_API_KEY': 'secret-a'}}))
    adapter = object()
    before = target_for('a', 'claude', '1.2.3', None, adapter)
    config.write_text(json.dumps({'model': 'a', 'theme': 'light', 'env': {'ANTHROPIC_API_KEY': 'secret-b'}}))
    assert target_for('a', 'claude', '1.2.3', None, adapter) == before
    config.write_text(json.dumps({'model': 'b'}))
    after = target_for('a', 'claude', '1.2.3', None, adapter)
    assert after['targetRevision'] != before['targetRevision'] and str(tmp_path) not in json.dumps(after)


def test_internal_verification_workspace_is_never_native_indexed_or_synced(tmp_path):
    from test_r3_native import fixture_history, setup_native
    async def scenario():
        system = System(tmp_path)
        try:
            root = system.worker.attachments.verifications.root
            workspace = root / 'verification-owned' / 'workspace'
            workspace.mkdir(parents=True)
            history = tmp_path / 'native-history'
            fixture_history(history, workspace, text='INTERNAL_PROBE_PRIVATE')
            native = setup_native(system, history)
            await native.scan()
            page = await native.listing()
            assert not page.items
            with system.db.locked_connection() as db:
                assert not db.execute('SELECT * FROM native_sources').fetchall()
                assert not db.execute('SELECT * FROM local_conversations').fetchall()
            assert 'INTERNAL_PROBE_PRIVATE' not in json.dumps(system.repo.frames())
        finally:
            await system.close()
    asyncio.run(scenario())


def test_cli_uses_paid_http_coordinator_and_explicit_confirmation(monkeypatch):
    from io import StringIO
    from runtime.cli import parser, execute, CLIError
    class Client:
        def __init__(self):
            self.calls = []
        def request(self, method, path, value=None):
            self.calls.append((method, path, value))
            if path == '/agents/discovery':
                return {'discovered': [{'id': 'instance', 'adapterId': 'claude'}]}
            if path.startswith('/agents/image-verifications?'):
                return {'items': [{'target': {'agentId': 'instance', 'targetRevision': 'snapshot'}}]}
            if method == 'POST':
                return {'jobId': 'job', 'status': 'queued'}
            return {'jobId': 'job', 'status': 'succeeded'}
    monkeypatch.setattr('runtime.cli.time.sleep', lambda _: None)
    client = Client()
    args = parser().parse_args(['agents', 'verify-image', '--agent', 'claude'])
    with pytest.raises(CLIError):
        execute(args, client, StringIO())
    assert not any(path == '/agents/image-verification-jobs' for _, path, _ in client.calls)
    args.acknowledge_model_usage = True
    output = StringIO()
    execute(args, client, output)
    body = next(v for m, p, v in client.calls if p == '/agents/image-verification-jobs')
    assert body == {'agentId': 'instance', 'expectedTargetRevision': 'snapshot', 'acknowledgeModelUsage': True}
    assert json.loads(output.getvalue())['status'] == 'succeeded'
