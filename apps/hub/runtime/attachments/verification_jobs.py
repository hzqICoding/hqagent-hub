"""Single-owner paid verification coordinator. CLI enters through Hub HTTP too."""
import asyncio
import json
from pathlib import Path
import shutil
import time

from protocol.generated.python import (AdapterFailure, CancelRequest, ERROR_CATALOG,
    LocalImageProbeDiagnostic, LocalImageVerificationJobView, LocalImageVerificationPage,
    LocalImageVerificationRecord, StartLocalImageVerificationInput)
from core.errors import HubError
from adapters.versions import cli_version
from runtime.remote.security import CredentialVault
from runtime.attachments.capabilities import VerificationStore, REQUIRED_PROBES
from runtime.attachments.verification_target import target_for
from storage.idempotency import request_hash
from storage.local_chat import now, uid

STAGES = {f'{p}.{s}': p.replace('mixed-five', 'mixedFive') + s.title()
          for p in ('new', 'resume', 'mixed-five') for s in ('start', 'collect', 'recognition')}
STAGES.update({'cancel.start': 'cancelStart', 'cancel.stop': 'cancelStop', 'error.check': 'errorCheck'})
SAFE_EXCEPTIONS = {'TimeoutError', 'CancelledError', 'OSError', 'ValueError', 'TypeError',
                   'RuntimeError', 'HubError', 'ConnectionError', 'BrokenPipeError'}
STOPPED = {'stopped_gracefully', 'force_killed', 'already_finished'}
TERMINAL = {'succeeded', 'failed', 'cancelled', 'interrupted'}


def conflict(reason, **detail):
    raise HubError('CONFLICT', '本机维护操作暂不可执行', detail={'reason': reason, **detail})


def diagnostics_view(raw):
    result = {}
    fields = {'result', 'elapsedMs', 'matched', 'kind', 'code', 'retryable', 'exceptionType',
              'startupStage', 'osError', 'winError', 'outcome', 'orphanProcessIds'}
    for stage, detail in raw.items():
        if stage not in STAGES or not isinstance(detail, dict):
            continue
        item = {k: v for k, v in detail.items() if k in fields}
        if item.get('code') not in ERROR_CATALOG:
            item.pop('code', None)
        if 'exceptionType' in item and item['exceptionType'] not in SAFE_EXCEPTIONS:
            item['exceptionType'] = 'UnknownError'
        # Validate each scalar independently: an unsafe vendor field must not
        # cause the complete response to fail or smuggle a free-form string.
        safe = {}
        for key, value in item.items():
            try:
                safe.update(LocalImageProbeDiagnostic.model_validate({key: value}).model_dump(
                    by_alias=True, mode='json', exclude_none=True))
            except ValueError:
                pass
        result[STAGES[stage]] = safe
    return result


def record_view(record, target):
    historical = record.get('target')
    if not historical:
        historical = {**target, 'targetRevision': 'legacy_unbound'}
        historical.pop('cliVersion', None)
        version = cli_version(record.get('version'))
        if version is not None:
            historical['cliVersion'] = version
    value = dict(recordId=record.get('recordId', 'legacy-' + request_hash(record)[:32]),
        target=historical, passed=bool(record['passed']),
        probes={k.replace('mixed-five', 'mixedFive'): bool(record['probes'].get(k, False)) for k in REQUIRED_PROBES},
        diagnostics=diagnostics_view(record.get('diagnostics', {})), mimeTypes=record['mimeTypes'],
        observedAt=record['observedAt'])
    if record.get('jobId'):
        value['jobId'] = record['jobId']
    return LocalImageVerificationRecord.model_validate(value).model_dump(by_alias=True, mode='json', exclude_none=True)


class VerificationCoordinator:
    def __init__(self, root, resolve, *, capabilities=None, budget=900, cleanup_budget=60):
        self.store = VerificationStore(root)
        self.root = self.store.root
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink() or (hasattr(self.root, 'is_junction') and self.root.is_junction()):
            conflict('agent_unavailable')
        self.path = self.root / 'jobs.json'
        self.resolve = resolve
        self.capabilities = capabilities
        self.budget, self.cleanup_budget = budget, cleanup_budget
        self.lock = asyncio.Lock()
        self.tasks, self.adapters = {}, {}
        try:
            self.data = json.loads(self.path.read_text('utf-8'))
        except FileNotFoundError:
            self.data = {'jobs': {}, 'keys': {}, 'cancelKeys': {}}
        # Never replay paid work after a restart. Empty ownership proves that a
        # queued job did not cross the launch boundary; missing PID proves nothing.
        for job in self.data['jobs'].values():
            if job['view']['status'] not in TERMINAL:
                job['view'].update(status='interrupted', finishedAt=now(), appliedToCurrentTarget=False)
                stopped = all(r.get('stopped') for r in job['resources']) and not job.get('launchPending')
                if stopped:
                    directory = Path(job['directory'])
                    try:
                        if directory.parent.resolve() != self.root.resolve() or directory.is_symlink():
                            raise OSError('invalid internal directory')
                        if directory.exists():
                            shutil.rmtree(directory)
                    except OSError:
                        stopped = False
                self.cleanup_state(job, stopped)
                for progress in job['view']['probes'].values():
                    if progress['state'] == 'running':
                        progress.update(state='failed', finishedAt=now())
                target = job['view']['target']
                record = self.store.record(target['agentType'], target.get('cliVersion'), target.get('modelId'),
                    {k: bool(job['outcomes'].get(k, False)) for k in REQUIRED_PROBES}, job.get('mimeTypes', []),
                    diagnostics=job['diagnostics'], target=target, job_id=job['view']['jobId'], completed=False)
                job['view']['result'] = record_view(record, target)
        self.save()

    @classmethod
    def for_service(cls, service):
        async def resolve(identifier, model):
            agents = await service.chat.ports.agents.list_agents()
            view = next((a for a in agents if a.id == identifier), None)
            if view is None:
                raise HubError('NOT_FOUND', 'Agent不存在')
            try:
                adapter = service.chat.ports.tasks.directory.adapter_for(identifier)
            except (LookupError, AttributeError):
                conflict('agent_unavailable')
            if str(view.adapter_id) == 'pi':
                models = await adapter.list_models(identifier)
                if model is not None and model not in {m.id for m in models.models}:
                    raise HubError('VALIDATION_FAILED', '模型选择器不在本机可用列表')
            descriptor = await adapter.detect()
            version = getattr(descriptor, 'detected_version', None)
            target = target_for(identifier, str(view.adapter_id), version, model, adapter)
            available = str(view.status) == 'ready' and not isinstance(descriptor, AdapterFailure)
            return target, adapter, available
        return cls(service.worker.repo.witness.parent.parent, resolve, capabilities=service.capabilities)

    def save(self):
        CredentialVault.atomic_write(self.path, json.dumps(self.data, ensure_ascii=False).encode())

    def persist(self, job):
        job['view']['updatedAt'] = now()
        self.save()

    def job(self, identifier):
        job = self.data['jobs'].get(identifier)
        if job is None:
            raise HubError('NOT_FOUND', '验证作业不存在')
        return job

    def view(self, identifier):
        return LocalImageVerificationJobView.model_validate(self.job(identifier)['view'])

    async def get(self, identifier):
        job = self.job(identifier)
        if job['view']['appliedToCurrentTarget']:
            try:
                current, _, available = await self.resolve(job['view']['target']['agentId'], job['view']['target'].get('modelId'))
                if not available or current != job['view']['target']:
                    job['view']['appliedToCurrentTarget'] = False
                    self.persist(job)
            except HubError:
                job['view']['appliedToCurrentTarget'] = False
                self.persist(job)
        return self.view(identifier)

    @staticmethod
    def slot(target):
        return target['agentId'], target.get('modelId')

    async def start(self, value, key, request_id):
        # Explicit strict bool check also protects non-HTTP callers and old DTOs.
        raw = value.model_dump(by_alias=True, mode='json', exclude_none=True) if hasattr(value, 'model_dump') else value
        if raw.get('acknowledgeModelUsage') is not True:
            raise HubError('VALIDATION_FAILED', '必须明确确认本次模型用量')
        value = StartLocalImageVerificationInput.model_validate(raw)
        if not key or len(key) > 200:
            raise HubError('VALIDATION_FAILED', '必须提供Idempotency-Key')
        digest = request_hash(raw)
        async with self.lock:
            prior = self.data['keys'].get(key)
            if prior:
                if prior['digest'] != digest:
                    raise HubError('IDEMPOTENCY_MISMATCH', '幂等键已用于不同验证意图')
                return self.view(prior['jobId'])
            target, adapter, available = await self.resolve(raw['agentId'], raw.get('modelId'))
            if not available or 'cliVersion' not in target or 'transport' not in target:
                conflict('agent_unavailable')
            if target['targetRevision'] != raw['expectedTargetRevision']:
                conflict('target_changed')
            for job in self.data['jobs'].values():
                if (job['view']['slotHeld'] or job['view']['status'] not in TERMINAL) and self.slot(job['view']['target']) == self.slot(target):
                    conflict('verification_in_progress', activeJobId=job['view']['jobId'])
            identifier, stamp = uid('verification-job'), now()
            view = dict(jobId=identifier, target=target, status='queued', acknowledgeModelUsage=True,
                acknowledgedAt=stamp, requestId=request_id, createdAt=stamp, updatedAt=stamp,
                probes={k.replace('mixed-five', 'mixedFive'): {'state': 'not_run'} for k in REQUIRED_PROBES},
                diagnostics={}, appliedToCurrentTarget=False, cleanupState='not_started',
                executionMayStillBeRunning=False, orphanProcessIds=[], slotHeld=True)
            job = {'view': view, 'resources': [], 'diagnostics': {}, 'outcomes': {}, 'internal': True,
                   'directory': str(self.root / identifier), 'createdEpoch': time.time()}
            self.data['jobs'][identifier] = job
            # No TTL. Retain digest/job identity even if an operator prunes results.
            self.data['keys'][key] = {'digest': digest, 'jobId': identifier}
            self.persist(job)
            self.adapters[identifier] = adapter
            self.tasks[identifier] = asyncio.create_task(self.run(identifier))
            return LocalImageVerificationJobView.model_validate(view.copy())

    async def current(self, job):
        target, _, available = await self.resolve(job['view']['target']['agentId'], job['view']['target'].get('modelId'))
        if not available or target != job['view']['target']:
            conflict('target_changed')

    async def stage(self, job, stage, detail):
        if detail is None:
            await self.current(job)
            if job['view']['status'] == 'cancel_requested':
                raise asyncio.CancelledError()
            name = stage.split('.')[0].replace('mixed-five', 'mixedFive')
            progress = job['view']['probes'][name]
            if progress['state'] == 'not_run':
                progress.update(state='running', startedAt=now())
        else:
            job['diagnostics'][stage] = detail
            job['view']['diagnostics'] = diagnostics_view(job['diagnostics'])
        self.persist(job)

    async def progress(self, job, name, passed):
        job['outcomes'][name] = passed
        job['view']['probes'][name.replace('mixed-five', 'mixedFive')].update(
            state='passed' if passed else 'failed', finishedAt=now())
        self.persist(job)

    @staticmethod
    def cleanup_state(job, stopped):
        job['view'].update(cleanupState='confirmed' if stopped else 'unconfirmed',
                           executionMayStillBeRunning=not stopped,
                           slotHeld=not stopped or job['view']['status'] not in TERMINAL)

    async def cleanup(self, job, adapter, *, deadline=None):
        job['view']['cleanupState'] = 'pending'
        self.persist(job)
        orphans = set(job['view']['orphanProcessIds'])
        try:
            remaining = self.cleanup_budget if deadline is None else max(0, deadline - asyncio.get_running_loop().time())
            async with asyncio.timeout(remaining):
                for resource in job['resources']:
                    if resource.get('stopped'):
                        continue
                    # After restart an adapter's empty registry is not evidence.
                    if adapter is not None:
                        self.observe_resource(job, adapter, resource)
                    if not resource.get('handleKnown') or adapter is None:
                        continue
                    result = await adapter.cancel(CancelRequest(sessionId=resource['sessionId'], mode='force'))
                    orphans.update(result.orphan_process_ids or [])
                    if str(result.outcome) in STOPPED and not result.orphan_process_ids:
                        resource['stopped'] = True
                        self.persist(job)
        except (Exception, asyncio.CancelledError):
            pass
        stopped = all(r.get('stopped') for r in job['resources']) and not job.get('launchPending')
        if stopped:
            try:
                release = getattr(adapter, 'release_temporary_session', None)
                if release is not None:
                    for resource in job['resources']:
                        if not await release(resource['sessionId']):
                            raise OSError('temporary session cleanup not confirmed')
                directory = Path(job['directory'])
                if directory.parent.resolve() != self.root.resolve() or directory.is_symlink():
                    raise OSError('invalid internal directory')
                if directory.exists():
                    shutil.rmtree(directory)
            except OSError:
                stopped = False
        job['view']['orphanProcessIds'] = sorted(orphans)[:64] if not stopped else []
        self.cleanup_state(job, stopped)
        self.persist(job)
        return stopped

    def observe_resource(self, job, adapter, resource):
        registry = getattr(adapter, 'registry', None)
        state = registry.get(resource['sessionId']) if registry is not None else None
        if state is None:
            return
        # Registration is exact to the write-ahead session ID, never a global
        # process-name search or a shared Runtime cancellation.
        observed = {'handleKnown': True}
        for key, value in (('externalSessionId', state.external_session_id),
                           ('turnId', state.active_turn_id),
                           ('processId', getattr(state.process, 'pid', None))):
            if value:
                observed[key] = value
        if any(resource.get(k) != v for k, v in observed.items()):
            resource.update(observed)
            self.persist(job)

    async def run(self, identifier):
        from runtime.attachments.verification import synthetic_inputs, probe
        job = self.job(identifier)
        adapter = self.adapters[identifier]
        status, mime_types = 'failed', []
        try:
            async with asyncio.timeout(max(0, min(self.budget, self.budget - (time.time() - job['createdEpoch'])))):
                await self.current(job)
                if job['view']['status'] == 'cancel_requested':
                    raise asyncio.CancelledError()
                job['view'].update(status='running', startedAt=now())
                self.persist(job)
                directory = Path(job['directory'])
                directory.mkdir()
                workspace = directory / 'workspace'
                workspace.mkdir()
                inputs, colors, nonce = synthetic_inputs(directory)
                mime_types = [i.attachment.mime_type for i in inputs if i.attachment.kind == 'image']
                job['mimeTypes'] = mime_types
                self.persist(job)
                await probe(OwnedAdapter(self, job, adapter), inputs, colors, nonce,
                    job['view']['target'].get('modelId'), workspace, diagnostics=job['diagnostics'],
                    stage_hook=lambda s, d: self.stage(job, s, d),
                    progress_hook=lambda n, p: self.progress(job, n, p))
                await self.current(job)
                status = 'succeeded' if all(job['outcomes'].get(k, False) for k in REQUIRED_PROBES) else 'failed'
        except asyncio.CancelledError:
            status = 'cancelled' if job['view']['status'] == 'cancel_requested' else 'interrupted'
        except HubError as error:
            job['failureReason'] = (error.detail or {}).get('reason', 'agent_unavailable')
            status = 'interrupted'
        except Exception:
            status = 'interrupted'
        finally:
            cleanup_deadline = asyncio.get_running_loop().time() + self.cleanup_budget
            stopped = await self.cleanup(job, adapter, deadline=cleanup_deadline)
            if job['view']['status'] == 'cancel_requested':
                status = 'cancelled'
            if not stopped:
                status = 'interrupted'
            try:
                async with asyncio.timeout(max(0, cleanup_deadline - asyncio.get_running_loop().time())):
                    await self.current(job)
                current = True
            except (Exception, asyncio.CancelledError) as error:
                current = False
                job['failureReason'] = 'target_changed'
                if isinstance(error, asyncio.CancelledError):
                    status = 'cancelled' if job['view']['status'] == 'cancel_requested' else 'interrupted'
            target = job['view']['target']
            for progress in job['view']['probes'].values():
                if progress['state'] == 'running':
                    progress.update(state='failed', finishedAt=now())
            outcomes = {k: bool(job['outcomes'].get(k, False)) for k in REQUIRED_PROBES}
            record = self.store.record(target['agentType'], target.get('cliVersion'), target.get('modelId'),
                outcomes, mime_types, diagnostics=job['diagnostics'], target=target,
                job_id=identifier, cleanup_confirmed=stopped and current and status == 'succeeded',
                completed=status == 'succeeded')
            job['view'].update(status=status, finishedAt=now(), result=record_view(record, target),
                appliedToCurrentTarget=stopped and current and record['passed'] and status == 'succeeded')
            self.cleanup_state(job, stopped)
            self.persist(job)
            try:
                if self.capabilities:
                    await self.capabilities.refresh()
            finally:
                self.tasks.pop(identifier, None)

    async def cancel(self, identifier, key):
        if not key or len(key) > 200:
            raise HubError('VALIDATION_FAILED', '必须提供Idempotency-Key')
        async with self.lock:
            job = self.job(identifier)
            digest = request_hash([identifier, {}])
            prior = self.data['cancelKeys'].get(key)
            if prior and prior != digest:
                raise HubError('IDEMPOTENCY_MISMATCH', '幂等键已用于其它取消操作')
            self.data['cancelKeys'][key] = digest
            if job['view']['status'] in TERMINAL and job['view']['cleanupState'] == 'confirmed':
                self.save()
                return await self.get(identifier), 200
            task = self.tasks.get(identifier)
            if task:
                queued = job['view']['status'] == 'queued'
                already_requested = job['view']['status'] == 'cancel_requested'
                job['view']['status'] = 'cancel_requested'
                self.persist(job)
                if not queued and not already_requested:
                    task.cancel()
            else:
                # Retrying only cleanup never starts inference. A restarted Hub
                # retains uncertainty unless an owned live handle is available.
                await self.cleanup(job, self.adapters.get(identifier))
                job['view']['status'] = 'interrupted'
                self.persist(job)
            return self.view(identifier), 202

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def matrix(self, agent_id=None, model=None, inactive=False, cursor=None, limit=50):
        if model is not None and not agent_id:
            raise HubError('VALIDATION_FAILED', '查询型号必须指定Agent')
        if not self.capabilities:
            raise HubError('NOT_FOUND', '验证矩阵不可用')
        await self.capabilities.refresh()
        usages = getattr(self.capabilities, 'usages', {})
        selectors = {(identifier, None) for identifier in self.capabilities.agents}
        selectors.update(usages)
        if inactive:
            for path in self.root.glob('*.json'):
                if path.name == 'jobs.json':
                    continue
                try:
                    record = json.loads(path.read_text('utf-8'))
                    if record.get('target'):
                        selectors.add(self.slot(record['target']))
                    else:
                        # Legacy observations remain discoverable as history even
                        # after their model stops appearing in active scenes.
                        selectors.update((identifier, record.get('model'))
                            for identifier, agent in self.capabilities.agents.items()
                            if str(getattr(agent, 'adapter_id', '')) == record.get('agent'))
                except (OSError, ValueError):
                    continue
        if model is not None:
            selectors = {(agent_id, model)}
        rows = []
        for identifier, selected in sorted(selectors, key=lambda x: (x[0], x[1] is not None, x[1] or '')):
            if agent_id and identifier != agent_id:
                continue
            try:
                target, _, available = await self.resolve(identifier, selected)
            except HubError:
                continue
            available = available and 'cliVersion' in target and 'transport' in target
            history = self.store.latest(identifier, target['agentType'], selected)
            reasons = []
            if history:
                old = history.get('target')
                if not old:
                    reasons.append('legacy_unbound')
                elif old != target:
                    reasons.append('cli_version_changed' if old.get('cliVersion') != target.get('cliVersion')
                                   else 'runtime_changed' if old.get('transport') != target.get('transport')
                                   else 'configuration_changed')
            if not available or 'cliVersion' not in target:
                reasons.append('target_unavailable')
            used = usages.get((identifier, selected), [])
            passed = bool(history and not reasons and history['passed'] and history.get('cleanupConfirmed'))
            row = dict(target=target, inUse=selected is None or bool(used), usages=used[:100],
                usagesTruncated=len(used) > 100, status='passed' if passed else 'stale' if reasons
                    else 'failed' if history else 'unverified', passed=passed,
                invalidated=bool(reasons), invalidationReasons=reasons)
            if not available:
                row['status'] = 'unavailable'
            if history:
                row['lastRecord'] = record_view(history, target)
            for job in self.data['jobs'].values():
                if self.slot(job['view']['target']) == (identifier, selected):
                    row['lastJobId'] = job['view']['jobId']
                    if job['view']['slotHeld'] or job['view']['status'] not in TERMINAL:
                        row['activeJobId'] = job['view']['jobId']
            rows.append(row)
        from runtime.pi_visibility import CLIENT_PI
        fingerprint = request_hash([bool(CLIENT_PI.get()), agent_id, model, inactive, limit, rows])
        offset = 0
        if cursor:
            try:
                prefix, position = cursor.split(':')
                offset = int(position)
                if prefix != fingerprint or offset < 0 or offset > len(rows):
                    raise ValueError()
            except ValueError:
                raise HubError('VALIDATION_FAILED', '游标筛选或快照已变化') from None
        more = offset + limit < len(rows)
        result = dict(items=rows[offset:offset + limit], hasMore=more)
        if more:
            result['nextCursor'] = fingerprint + ':' + str(offset + limit)
        return LocalImageVerificationPage.model_validate(result)


class OwnedAdapter:
    """Write-ahead ownership precedes every call that could launch a model."""
    def __init__(self, coordinator, job, adapter):
        self.coordinator, self.job, self.adapter = coordinator, job, adapter

    async def launch(self, operation):
        self.job['launchPending'] = True
        self.coordinator.persist(self.job)
        task = asyncio.create_task(operation)
        try:
            while not task.done():
                for resource in self.job['resources']:
                    self.coordinator.observe_resource(self.job, self.adapter, resource)
                await asyncio.wait({task}, timeout=0.01)
            return task.result()
        finally:
            if not task.done():
                task.cancel()
                await asyncio.wait({task}, timeout=0.1)
            for resource in self.job['resources']:
                self.coordinator.observe_resource(self.job, self.adapter, resource)
            if task.done():
                if not task.cancelled() and task.exception() is None:
                    handle = task.result()
                    if hasattr(handle, 'session_id') and hasattr(handle, 'external_session_id'):
                        for resource in self.job['resources']:
                            if resource['sessionId'] == handle.session_id:
                                resource.update(handleKnown=True, externalSessionId=handle.external_session_id)
                self.job['launchPending'] = False
                self.coordinator.persist(self.job)
            else:
                def completed(finished):
                    if not finished.cancelled():
                        finished.exception()
                    self.job['launchPending'] = False
                    for resource in self.job['resources']:
                        # An operation that outlived cancellation may have opened
                        # a turn after the previous stop proof. Reconcile again.
                        resource['stopped'] = False
                        if not finished.cancelled() and finished.exception() is None:
                            handle = finished.result()
                            if getattr(handle, 'session_id', None) == resource['sessionId']:
                                resource.update(handleKnown=True, externalSessionId=handle.external_session_id)
                        self.coordinator.observe_resource(self.job, self.adapter, resource)
                    self.coordinator.persist(self.job)
                task.add_done_callback(completed)

    async def start(self, spec):
        resource = dict(sessionId=spec.session_id, stopped=False, handleKnown=False,
                        workspace=spec.worktree_path, internal=True)
        self.job['resources'].append(resource)
        self.coordinator.persist(self.job)
        result = await self.launch(self.adapter.start(spec))
        if not isinstance(result, AdapterFailure):
            if result.session_id != spec.session_id:
                conflict('agent_unavailable')
            resource.update(externalSessionId=result.external_session_id, handleKnown=True)
        # A failed start can have launched an unobservable process. Preserve intent.
        self.coordinator.persist(self.job)
        return result

    async def resume(self, request):
        if not any(r['sessionId'] == request.session_id and r.get('externalSessionId') == request.external_session_id
                   for r in self.job['resources']):
            conflict('agent_unavailable')
        for resource in self.job['resources']:
            if resource['sessionId'] == request.session_id:
                resource['stopped'] = False
        self.coordinator.persist(self.job)
        return await self.launch(self.adapter.resume(request))

    def stream_events(self, identifier):
        return self.adapter.stream_events(identifier)

    async def collect_result(self, identifier):
        result = await self.adapter.collect_result(identifier)
        if not isinstance(result, AdapterFailure):
            for resource in self.job['resources']:
                if resource['sessionId'] == identifier:
                    resource['resultCollected'] = True
            self.coordinator.persist(self.job)
        return result

    async def cancel(self, request):
        result = await self.adapter.cancel(request)
        for resource in self.job['resources']:
            if resource['sessionId'] == request.session_id:
                resource['stopped'] = str(result.outcome) in STOPPED and not result.orphan_process_ids
        self.job['view']['orphanProcessIds'] = list(result.orphan_process_ids or [])[:64]
        self.coordinator.persist(self.job)
        return result
