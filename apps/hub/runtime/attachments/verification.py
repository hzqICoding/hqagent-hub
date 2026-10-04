"""Explicit operator image probe. Importing this module never calls a model."""
import asyncio
import hashlib
import json
from pathlib import Path
import secrets
import time
from core.errors import HubError
from protocol.generated.python import AgentInputAttachment, AgentTaskSpec, AdapterFailure, CancelRequest, ResumeRequest
from adapters.attachment_input import checked_inputs
from runtime.attachments.capabilities import VerificationStore, REQUIRED_PROBES
from storage.local_chat import uid

def synthetic_inputs(directory):
    from PIL import Image
    directory = Path(directory)
    colors = [('red', (255, 0, 0)), ('green', (0, 255, 0)), ('blue', (0, 0, 255)), ('yellow', (255, 255, 0))]
    values = []
    expected, arrangements = [], set()
    for extension, format_, mime in [('png', 'PNG', 'image/png'), ('jpg', 'JPEG', 'image/jpeg'), ('webp', 'WEBP', 'image/webp'), ('gif', 'GIF', 'image/gif')]:
        while True:
            secrets.SystemRandom().shuffle(colors)
            order = tuple(c[0] for c in colors)
            if order not in arrangements:
                arrangements.add(order)
                break
        expected.extend(order)
        image = Image.new('RGB', (512, 512), (255, 255, 255))
        for i, (_, color) in enumerate(colors):
            x, y = i % 2 * 256, i // 2 * 256
            image.paste(color, (x + 16, y + 16, x + 240, y + 240))
        path = directory / (uid('image') + '.' + extension)
        image.save(path, format=format_)
        body = path.read_bytes()
        values.append(AgentInputAttachment(attachment={'attachmentId': uid('probe'), 'fileName': 'probe.' + extension, 'kind': 'image', 'mimeType': mime, 'sizeBytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}, localPath=str(path)))
    nonce = secrets.token_hex(8)
    path = directory / (uid('input') + '.txt')
    path.write_text(nonce, encoding='utf-8')
    values.append(AgentInputAttachment(attachment={'attachmentId': uid('probe'), 'fileName': 'probe.txt', 'kind': 'file', 'mimeType': 'text/plain', 'sizeBytes': len(nonce), 'sha256': hashlib.sha256(nonce.encode()).hexdigest()}, localPath=str(path)))
    return (values, expected, nonce)

def recognizes(summary, colors, nonce=None):
    text = summary.lower()
    last = -1
    for color in colors:
        position = text.find(color, last + 1)
        if position <= last:
            return False
        last = position
    return nonce is None or nonce in summary

async def probe(adapter, inputs, colors, nonce, model, workspace, *, diagnostics=None, stage_hook=None, progress_hook=None):
    """Exercise the actual start/resume transport, never a help-only claim."""
    outcomes = {name: False for name in REQUIRED_PROBES}
    diagnostics = diagnostics if diagnostics is not None else {}

    async def stage(name, detail=None):
        if detail is not None:
            diagnostics[name] = detail
        if stage_hook:
            await stage_hook(name, detail)

    async def outcome(name, passed):
        outcomes[name] = passed
        if progress_hook:
            await progress_hook(name, passed)

    async def observed(stage, operation):
        started = time.monotonic()
        try:
            if stage_hook:
                try:
                    await stage_hook(stage, None)
                except BaseException:
                    operation.close()
                    raise
            result = await operation
        except BaseException as error:
            diagnostics[stage] = {'result': 'exception', 'exceptionType': type(error).__name__,
                                  'elapsedMs': int((time.monotonic() - started) * 1000)}
            if stage_hook:
                await stage_hook(stage, diagnostics[stage])
            raise
        detail = {'result': 'ok', 'elapsedMs': int((time.monotonic() - started) * 1000)}
        if isinstance(result, AdapterFailure):
            detail.update(result='adapter_failure', kind=str(result.kind), code=str(result.code), retryable=result.retryable)
            try:
                native = json.loads(result.raw or '{}')
                if isinstance(native, dict) and native.get('startupStage') in {
                    'process.start', 'initialize', 'model/list', 'thread/start', 'thread/resume', 'turn/start'}:
                    detail['startupStage'] = native['startupStage']
                    for field in ('osError', 'winError'):
                        if isinstance(native.get(field), int):
                            detail[field] = native[field]
            except (ValueError, TypeError):
                pass
        elif hasattr(result, 'outcome'):
            detail.update(outcome=str(result.outcome), orphanProcessIds=result.orphan_process_ids or [])
        diagnostics[stage] = detail
        if stage_hook:
            await stage_hook(stage, detail)
        return result
    session_id = uid('image-probe')
    spec = AgentTaskSpec(sessionId=session_id, taskId=uid('probe-task'), nodeId=uid('probe-node'), workspaceId='image-verification', roleId='analyst', objective='Describe the four quadrant colors in row-major order, using English color names.', worktreePath=str(workspace), allowedPaths=[], readOnly=True, sessionPurpose='adhoc', reusePolicy='new_session', modelId=model, inputAttachments=[inputs[0]])

    async def finished(identifier, stage, expected_nonce=None):
        async with asyncio.timeout(180):
            async for _ in adapter.stream_events(identifier):
                pass
            result = await observed(stage + '.collect', adapter.collect_result(identifier))
        recognized = not isinstance(result, AdapterFailure) and recognizes(result.summary, colors if expected_nonce else colors[:4], expected_nonce)
        if stage_hook:
            await stage_hook(stage + '.recognition', {'matched': recognized})
        diagnostics[stage + '.recognition'] = {'matched': recognized}
        return recognized
    handles = []
    try:
        handle = await observed('new.start', adapter.start(spec))
        if isinstance(handle, AdapterFailure):
            await outcome('new', False)
            return outcomes
        handles.append(handle)
        await outcome('new', await finished(handle.session_id, 'new'))
        resume = ResumeRequest(sessionId=handle.session_id, externalSessionId=handle.external_session_id, message='Describe the current image quadrant colors in row-major order using English color names.', taskSpec=spec)
        result = await observed('resume.start', adapter.resume(resume))
        if not isinstance(result, AdapterFailure):
            await outcome('resume', await finished(handle.session_id, 'resume'))
        else:
            await outcome('resume', False)
        mixed = spec.model_copy(update={'input_attachments': inputs})
        result = await observed('mixed-five.start', adapter.resume(resume.model_copy(update={'task_spec': mixed, 'message': 'For EACH attached image in attachment order, report its four quadrant colors in row-major order using English color names (sixteen colors in total). Then read the attached text file and include its exact marker.'})))
        if not isinstance(result, AdapterFailure):
            await outcome('mixed-five', await finished(handle.session_id, 'mixed-five', nonce))
        else:
            await outcome('mixed-five', False)
        invalid = inputs[0].model_copy(update={'attachment': inputs[0].attachment.model_copy(update={'sha256': '0' * 64})})
        await stage('error.check')
        try:
            checked_inputs([invalid])
        except HubError as error:
            await outcome('error', error.code == 'ATTACHMENT_HASH_MISMATCH')
        await stage('error.check', {'matched': outcomes['error']})
        cancel_spec = spec.model_copy(update={'session_id': uid('image-probe'), 'objective': 'Describe the image and then provide a long detailed visual analysis.'})
        cancel_handle = await observed('cancel.start', adapter.start(cancel_spec))
        if not isinstance(cancel_handle, AdapterFailure):
            handles.append(cancel_handle)
            result = await observed('cancel.stop', adapter.cancel(CancelRequest(sessionId=cancel_handle.session_id, mode='force')))
            await outcome('cancel', str(result.outcome) in {'stopped_gracefully', 'force_killed', 'already_finished'} and (not result.orphan_process_ids))
        else:
            await outcome('cancel', False)
    finally:
        # The coordinator owns bounded cleanup and publication. A probe must not
        # swallow failed cancellation and thereby certify cleanup as successful.
        pass
    return outcomes

async def verify_images(root, agent, model=None, *, adapter=None):
    """Injected-adapter harness. Operators use CLI -> HTTP -> running Hub owner."""
    if adapter is None:
        raise HubError('CONFLICT', '请通过运行中Hub的agents verify-image入口验证', detail={'reason': 'agent_unavailable'})
    from runtime.attachments.verification_jobs import VerificationCoordinator
    from runtime.attachments.verification_target import target_for
    identifier = 'local.' + agent + '.default'
    async def resolve(agent_id, selected):
        if agent == 'pi':
            await adapter.list_models(agent_id)
        descriptor = await adapter.detect()
        return target_for(agent_id, agent, getattr(descriptor, 'detected_version', None), selected, adapter), adapter, not isinstance(descriptor, AdapterFailure)
    coordinator = VerificationCoordinator(root, resolve)
    target, _, _ = await resolve(identifier, model)
    value = dict(agentId=identifier, expectedTargetRevision=target['targetRevision'], acknowledgeModelUsage=True)
    if model is not None:
        value['modelId'] = model
    job = await coordinator.start(value, uid('test-verification'), uid('request'))
    await coordinator.tasks[job.job_id]
    return coordinator.store.latest(identifier, agent, model)
