"""Local-only validated attachment encoding. Never include this in wire events."""
import base64
import hashlib
import json
from pathlib import Path
from core.errors import HubError
from protocol.generated.python import AgentInputAttachment

def checked_inputs(values):
    result = []
    if len(values or []) > 5:
        raise HubError('ATTACHMENT_COUNT_EXCEEDED', '每轮最多五个附件')
    for raw in values or []:
        value = raw if isinstance(raw, AgentInputAttachment) else AgentInputAttachment.model_validate(raw)
        if value.attachment.size_bytes > (10000000 if value.attachment.kind == 'image' else 20000000):
            raise HubError('ATTACHMENT_TOO_LARGE', '附件超过单项大小上限')
        path = Path(value.local_path)
        if not path.is_absolute() or path.is_symlink() or (not path.is_file()):
            raise HubError('ATTACHMENT_NOT_READY', '附件受控文件不可读')
        sha, length = (hashlib.sha256(), 0)
        with path.open('rb') as stream:
            while (chunk := stream.read(65536)):
                length += len(chunk)
                if length > value.attachment.size_bytes:
                    raise HubError('ATTACHMENT_HASH_MISMATCH', '附件完整性校验失败')
                sha.update(chunk)
        if length != value.attachment.size_bytes or sha.hexdigest() != value.attachment.sha256:
            raise HubError('ATTACHMENT_HASH_MISMATCH', '附件完整性校验失败')
        result.append(value)
    return result

def file_prompt(message, values):
    from adapters.prompt import attachment_read_scope
    scope = attachment_read_scope([value for value in values if value.attachment.kind == 'file'])
    return message + ('\n' + scope if scope and scope not in message else '')

def claude_input(message, values):
    values = checked_inputs(values)
    content = [{'type': 'text', 'text': file_prompt(message, values)}]
    for value in values:
        if value.attachment.kind == 'image':
            with Path(value.local_path).open('rb') as stream:
                image = stream.read(value.attachment.size_bytes + 1)
            if len(image) != value.attachment.size_bytes or hashlib.sha256(image).hexdigest() != value.attachment.sha256:
                raise HubError('ATTACHMENT_HASH_MISMATCH', '附件完整性校验失败')
            content.append({'type': 'image', 'source': {'type': 'base64', 'media_type': value.attachment.mime_type, 'data': base64.b64encode(image).decode('ascii')}})
    return (json.dumps({'type': 'user', 'message': {'role': 'user', 'content': content}}, ensure_ascii=False) + '\n').encode()

def claude_session_args(session_id, *, resume, has_attachments):
    return (['--input-format', 'stream-json'] if has_attachments else []) + ['--resume' if resume else '--session-id', session_id]

def codex_input(message, values):
    values = checked_inputs(values)
    return [{'type': 'text', 'text': file_prompt(message, values)}] + [{'type': 'localImage', 'path': v.local_path} for v in values if v.attachment.kind == 'image']

def codex_exec_args(executable, message, values, *, resume_id=None):
    values = checked_inputs(values)
    args = [executable, 'exec'] + (['resume', resume_id] if resume_id else [])
    for value in values:
        if value.attachment.kind == 'image':
            args.extend(['--image', value.local_path])
    return args + [file_prompt(message, values)]
