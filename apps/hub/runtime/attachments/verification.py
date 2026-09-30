"""Explicit operator image probe. Importing this module never calls a model."""
import asyncio
import hashlib
import json
from pathlib import Path
import secrets
import tempfile
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

async def probe(adapter, inputs, colors, nonce, model, workspace, *, diagnostics=None):
    """Exercise the actual start/resume transport, never a help-only claim."""
    outcomes = {name: False for name in REQUIRED_PROBES}
    diagnostics = diagnostics if diagnostics is not None else {}

    async def observed(stage, operation):
        started = time.monotonic()
        try:
            result = await operation
        except BaseException as error:
            diagnostics[stage] = {'result': 'exception', 'exceptionType': type(error).__name__,
                                  'elapsedMs': int((time.monotonic() - started) * 1000)}
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
        return result
    session_id = uid('image-probe')
    spec = AgentTaskSpec(sessionId=session_id, taskId=uid('probe-task'), nodeId=uid('probe-node'), workspaceId='image-verification', roleId='analyst', objective='Describe the four quadrant colors in row-major order, using English color names.', worktreePath=str(workspace), allowedPaths=[], readOnly=True, sessionPurpose='adhoc', reusePolicy='new_session', modelId=model, inputAttachments=[inputs[0]])

    async def finished(identifier, stage, expected_nonce=None):
        async with asyncio.timeout(180):
            async for _ in adapter.stream_events(identifier):
                pass
            result = await observed(stage + '.collect', adapter.collect_result(identifier))
        recognized = not isinstance(result, AdapterFailure) and recognizes(result.summary, colors if expected_nonce else colors[:4], expected_nonce)
        diagnostics[stage + '.recognition'] = {'matched': recognized}
        return recognized
    handles = []
    try:
        handle = await observed('new.start', adapter.start(spec))
        if isinstance(handle, AdapterFailure):
            return outcomes
        handles.append(handle)
        outcomes['new'] = await finished(handle.session_id, 'new')
        resume = ResumeRequest(sessionId=handle.session_id, externalSessionId=handle.external_session_id, message='Describe the current image quadrant colors in row-major order using English color names.', taskSpec=spec)
        result = await observed('resume.start', adapter.resume(resume))
        if not isinstance(result, AdapterFailure):
            outcomes['resume'] = await finished(handle.session_id, 'resume')
        mixed = spec.model_copy(update={'input_attachments': inputs})
        result = await observed('mixed-five.start', adapter.resume(resume.model_copy(update={'task_spec': mixed, 'message': 'For EACH attached image in attachment order, report its four quadrant colors in row-major order using English color names (sixteen colors in total). Then read the attached text file and include its exact marker.'})))
        if not isinstance(result, AdapterFailure):
            outcomes['mixed-five'] = await finished(handle.session_id, 'mixed-five', nonce)
        invalid = inputs[0].model_copy(update={'attachment': inputs[0].attachment.model_copy(update={'sha256': '0' * 64})})
        try:
            checked_inputs([invalid])
        except HubError as error:
            outcomes['error'] = error.code == 'ATTACHMENT_HASH_MISMATCH'
        cancel_spec = spec.model_copy(update={'session_id': uid('image-probe'), 'objective': 'Describe the image and then provide a long detailed visual analysis.'})
        cancel_handle = await observed('cancel.start', adapter.start(cancel_spec))
        if not isinstance(cancel_handle, AdapterFailure):
            handles.append(cancel_handle)
            result = await observed('cancel.stop', adapter.cancel(CancelRequest(sessionId=cancel_handle.session_id, mode='force')))
            outcomes['cancel'] = str(result.outcome) in {'stopped_gracefully', 'force_killed', 'already_finished'} and (not result.orphan_process_ids)
    finally:
        for handle in handles:
            try:
                await adapter.cancel(CancelRequest(sessionId=handle.session_id, mode='force'))
            except Exception:
                pass
    return outcomes

async def verify_images(root, agent, model=None, *, adapter=None):
    from adapters.claude_adapter import ClaudeAdapter
    from adapters.codex_adapter import CodexAdapter
    adapter = adapter or (ClaudeAdapter() if agent == 'claude' else CodexAdapter())
    descriptor = await adapter.detect()
    if isinstance(descriptor, AdapterFailure):
        raise RuntimeError('Runtime unavailable for image verification')
    directory = Path(root) / 'image-verification'
    directory.mkdir(parents=True, exist_ok=True)
    outcomes = {name: False for name in REQUIRED_PROBES}
    diagnostics = {}
    with tempfile.TemporaryDirectory(prefix='probe-', dir=directory) as temporary:
        inputs, colors, nonce = synthetic_inputs(Path(temporary))
        workspace = Path(temporary) / 'workspace'
        workspace.mkdir()
        try:
            outcomes = await probe(adapter, inputs, colors, nonce, model, workspace, diagnostics=diagnostics)
        finally:
            record = VerificationStore(root).record(agent, descriptor.detected_version, model, outcomes, [v.attachment.mime_type for v in inputs if v.attachment.kind == 'image'], diagnostics=diagnostics)
    return record
