"""Bounded local metadata logging. No payloads, command lines or exception text."""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import queue
import re
import sys
import threading
import time
from functools import wraps

from protocol.generated.python import ERROR_CATALOG


REQUEST_LOG = ContextVar('hub_request_log', default=None)
_active = None
_events = {
    'hub.starting': {'appVersion', 'protocolVersion', 'environment', 'port', 'dataRoot', 'desktop'},
    'hub.ready': {'appVersion', 'protocolVersion', 'environment', 'port', 'dataRoot', 'desktop', 'elapsedMs'},
    'hub.stopped': {'appVersion', 'protocolVersion', 'environment', 'port', 'dataRoot', 'desktop', 'elapsedMs'},
    'hub.failure': {'exceptionType', 'stack'},
    'http.access': {'method', 'route', 'status', 'elapsedMs', 'requestId', 'auth', 'errorCode'},
    'http.exception': {'method', 'route', 'requestId', 'exceptionType', 'stack'},
    'loop.lag': {'lagMs'},
    'loop.blocked': {'lagMs', 'threadId', 'stack', 'ownerThreadId', 'ownerIsLoopThread', 'ownerHoldMs', 'ownerStack'},
    'db.lock.slow': {'holdMs', 'threadId', 'isLoopThread', 'stack'},
    'db.lock.wait': {'waitMs', 'threadId', 'stack', 'ownerThreadId', 'ownerIsLoopThread', 'ownerHoldMs', 'ownerStack'},
    'loop.exception': {'exceptionType', 'stack'},
    'agent.discovery': {'agentId', 'agentType', 'version', 'status', 'errorCode', 'elapsedMs'},
    'agent.models': {'agentId', 'agentType', 'count', 'verified'},
    'agent.guard': {'agentType', 'status', 'reason'},
    'agent.failure': {'agentType', 'sessionId', 'errorCode', 'kind'},
    'process.started': {'pid', 'mode'},
    'process.exited': {'pid', 'mode', 'exitCode'},
    'remote.state': {'state', 'connectionStatus', 'errorCode'},
    'remote.retry': {'delayMs', 'errorCode'},
    'remote.sync': {'state'},
    'remote.command': {'direction', 'kind', 'commandId', 'result', 'errorCode'},
    'remote.admission': {'stage', 'elapsedMs', 'errorCode'},
    'remote.transport': {'exceptionType', 'stack'},
    'verification.state': {'jobId', 'status', 'cleanupState', 'slotHeld'},
    'conversation.deletion': {'conversationId', 'status', 'remoteCleanup', 'errorCode'},
    'attachment.preparation': {'runId', 'status', 'errorCode'},
    'legacy.error': {'exceptionType', 'stack'},
}
_legacy = {'runtime.local_chat', 'runtime.conversation_deletion', 'runtime.remote.worker',
           'runtime.remote.resources', 'runtime.remote.keychain', 'uvicorn.error', 'asyncio'}
_safe_exceptions = {'RuntimeError', 'ValueError', 'TypeError', 'OSError', 'PermissionError',
    'FileNotFoundError', 'TimeoutError', 'CancelledError', 'HubError', 'ConnectionError',
    'BrokenPipeError', 'AssertionError', 'KeyError', 'IndexError', 'HTTPException'}
_number_fields = {'port', 'pid', 'exitCode', 'threadId', 'ownerThreadId', 'status', 'count', 'elapsedMs', 'lagMs', 'delayMs', 'holdMs', 'waitMs', 'ownerHoldMs'}
_patterns = (
    re.compile(r'(?i)\bBearer\s+[^\s\"\'<>;,]+'),
    re.compile(r'(?i)\b(?:authorization|cookie|set-cookie)\s*[:=][^\r\n]*'),
    re.compile(r'(?i)\b(?:ticket|token|api[_-]?key|secret|password|pair[_-]?code|pat)\s*[=:]\s*[^\s\"\'&;,<>]+'),
    re.compile(r'\bsk-[A-Za-z0-9_-]+'),
    re.compile(r'(?i)https?://[^\s\"\']+'),
)


class Redactor:
    """Defense in depth for whitelisted string values, not a payload scrubber."""
    def __init__(self, secrets=()):
        self._secrets = tuple(sorted({s for s in secrets if isinstance(s, str) and s}, key=len, reverse=True))
        self._lock = threading.Lock()

    def remember(self, value):
        if isinstance(value, str) and value and value not in self._secrets:
            with self._lock:
                self._secrets = tuple(sorted({*self._secrets, value}, key=len, reverse=True))

    def text(self, value):
        text = str(value)
        if len(text) > 1024:
            return '[oversized]'
        for secret in self._secrets:
            text = text.replace(secret, '[redacted]')
        for pattern in _patterns:
            text = pattern.sub('[redacted]', text)
        text = re.sub(r'[\x00-\x1f\x7f]', ' ', text)
        return text[:1024]


def frame_stack(frame, limit=32):
    """No traceback formatting/linecache: those copy source lines and values."""
    frames = []
    while frame is not None and len(frames) < limit:
        frames.append({'file': Path(frame.f_code.co_filename).name,
                       'line': frame.f_lineno, 'function': frame.f_code.co_name})
        frame = frame.f_back
    return list(reversed(frames))


def exception_fields(error):
    frames, tb = [], error.__traceback__
    while tb is not None and len(frames) < 32:
        frames.append({'file': Path(tb.tb_frame.f_code.co_filename).name,
                       'line': tb.tb_lineno, 'function': tb.tb_frame.f_code.co_name})
        tb = tb.tb_next
    name = type(error).__name__
    return {'exceptionType': name if name in _safe_exceptions else 'UnknownError', 'stack': frames}


def note_response(request_id, error_code=None):
    context = REQUEST_LOG.get()
    if context is not None:
        context['requestId'] = request_id
        if error_code in ERROR_CATALOG:
            context['errorCode'] = error_code


class MetadataFilter(logging.Filter):
    def __init__(self, redactor):
        super().__init__()
        self.redactor = redactor

    def filter(self, record):
        event = getattr(record, 'hub_event', None)
        if not isinstance(event, str) or event not in _events:
            if record.name not in _legacy or record.levelno < logging.WARNING:
                return False
            event, fields = 'legacy.error', {}
            if record.exc_info and isinstance(record.exc_info[1], BaseException):
                fields = exception_fields(record.exc_info[1])
        else:
            fields = getattr(record, 'hub_fields', {})
            if not isinstance(fields, dict):
                return False
        context = REQUEST_LOG.get() or {}
        local_redactor = Redactor(context.get('_secrets', ()))
        clean = lambda value: self.redactor.text(local_redactor.text(value))
        row = {'ts': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
               'level': record.levelname, 'logger': record.name if record.name in _legacy else 'hub.' + event.split('.')[0],
               'event': event}
        for key in _events[event]:
            value = fields.get(key)
            if value is None:
                continue
            if key in {'stack', 'ownerStack'}:
                if isinstance(value, list):
                    row[key] = [{k: clean(f[k]) if k != 'line' else f[k]
                                 for k in ('file', 'line', 'function') if k in f and
                                 (isinstance(f[k], str) if k != 'line' else type(f[k]) is int)}
                                for f in value[-32:] if isinstance(f, dict)]
            elif key == 'errorCode':
                if isinstance(value, str) and value in ERROR_CATALOG:
                    row[key] = value
            elif key == 'exceptionType':
                row[key] = value if isinstance(value, str) and value in _safe_exceptions else 'UnknownError'
            elif type(value) is bool:
                row[key] = value
            elif key in _number_fields and isinstance(value, (int, float)) and math.isfinite(value):
                row[key] = round(value, 2) if isinstance(value, float) else value
            elif isinstance(value, str):
                row[key] = clean(value.split('?', 1)[0] if key == 'route' else value)
        # Never queue LogRecord: it can retain exc_info, body-bearing args or locals.
        record.hub_safe_row = row
        return True


class _QueueHandler(logging.Handler):
    def __init__(self, sink):
        super().__init__(sink.level)
        self.sink = sink
        self.addFilter(MetadataFilter(sink.redactor))

    def emit(self, record):
        if self.sink.file is None or self.sink.closed:
            return
        try:
            self.sink.queue.put_nowait(record.hub_safe_row)
        except queue.Full:
            self.sink.dropped += 1  # Bounded memory; never block the event loop.


class _FileHandler(RotatingFileHandler):
    def handleError(self, record):
        self.owner.disable_file()


class LocalLog:
    def __init__(self, root, *, secrets=(), max_bytes=5_000_000, backups=5, level=None):
        self.path = Path(root) / 'logs' / 'hub.log'
        configured = (level or os.environ.get('HQAGENT_LOG_LEVEL', 'INFO')).upper()
        self.level = getattr(logging, configured, logging.INFO)
        if self.level not in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL):
            self.level = logging.INFO
        env_secrets = [v for k, v in os.environ.items() if v and any(s in k.upper() for s in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY'))]
        self.redactor = Redactor([*secrets, *env_secrets])
        self.queue = queue.Queue(maxsize=2048)
        self.dropped = 0
        self.file = None
        self.thread = None
        self.closed = False
        self.warned = False
        try:
            if self.path.parent.is_symlink() or self.path.is_symlink():
                raise OSError('unsafe log location')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.file = _FileHandler(self.path, maxBytes=max_bytes, backupCount=backups, encoding='utf-8')
            self.file.owner = self
            self.file.setFormatter(logging.Formatter('%(message)s'))
            if os.name != 'nt':
                self.path.chmod(0o600)
        except OSError:
            self.disable_file()
        self.handler = _QueueHandler(self)
        logging.getLogger('hqhub').setLevel(logging.DEBUG)
        logging.getLogger('hqhub').propagate = False
        logging.getLogger('hqhub').addHandler(self.handler)
        logging.getLogger().addHandler(self.handler)
        if self.file is not None:
            self.thread = threading.Thread(target=self._write, name='hub-log-writer', daemon=True)
            try:
                self.thread.start()
            except (OSError, RuntimeError):
                self.thread = None
                self.disable_file()

    def disable_file(self):
        if not self.warned:
            self.warned = True
            try:
                sys.stderr.write('Hub file logging unavailable; continuing without file logs.\n')
            except (OSError, AttributeError):
                pass
        if self.file is not None:
            try:
                self.file.close()
            except OSError:
                pass
        self.file = None

    def _write(self):
        while True:
            value = self.queue.get()
            try:
                if value is None:
                    return
                if self.file is not None:
                    record = logging.LogRecord('hub', logging.INFO, '', 0,
                        json.dumps(value, ensure_ascii=False, separators=(',', ':')), (), None)
                    self.file.handle(record)
            except Exception:
                self.disable_file()
            finally:
                self.queue.task_done()

    def flush(self, timeout=2):
        deadline = time.monotonic() + timeout
        while self.thread is not None and self.queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(.005)

    def close(self):
        global _active
        if self.closed:
            return
        self.closed = True
        logging.getLogger('hqhub').removeHandler(self.handler)
        logging.getLogger().removeHandler(self.handler)
        if _active is self:
            _active = None
        if self.thread is not None:
            self.flush()
            try:
                self.queue.put_nowait(None)
            except queue.Full:
                pass
            self.thread.join(timeout=1)
        if self.thread is None or not self.thread.is_alive():
            if self.file is not None:
                self.file.close()


def configure_logging(root, *, secrets=(), **options):
    global _active
    if _active is not None:
        _active.close()
    _active = LocalLog(root, secrets=secrets, **options)
    return _active


def emit(event, *, level=logging.INFO, **fields):
    if _active is None or _active.closed or event not in _events:
        return
    try:
        logging.getLogger('hqhub').log(level, '', extra={'hub_event': event, 'hub_fields': fields})
    except Exception:
        # Diagnostics never becomes an execution/admission failure. In
        # particular, do not format the rejected values into an error log.
        pass


def is_enabled():
    return _active is not None and not _active.closed


def remember_secret(value):
    # Only credential owners register exact runtime values. Never read auth
    # stores from a log callback or write the credential into a LogRecord.
    if is_enabled():
        _active.redactor.remember(value)


def catalog_logged(kind):
    def decorate(function):
        @wraps(function)
        async def call(self, agent_instance_id, *args, **kwargs):
            try:
                result = await function(self, agent_instance_id, *args, **kwargs)
            except Exception:
                emit('agent.models', level=logging.WARNING, agentId=agent_instance_id, agentType=kind, count=0, verified=False)
                raise
            emit('agent.models', agentId=agent_instance_id, agentType=kind, count=len(result.models), verified=bool(result.verified))
            return result
        return call
    return decorate


def track_process(process, mode):
    if not is_enabled():
        return
    import asyncio
    pid = getattr(process, 'pid', None)
    emit('process.started', pid=pid, mode=mode)
    async def exited():
        try:
            code = await process.wait()
            emit('process.exited', pid=pid, mode=mode, exitCode=code)
        except (OSError, asyncio.CancelledError):
            pass
    task = asyncio.create_task(exited())
    # Keep the observer alive until process exit, without changing Adapter ownership.
    _process_observers.add(task)
    task.add_done_callback(_process_observers.discard)


_process_observers = set()


def remote_command(frame, direction):
    if not isinstance(frame, dict) or not isinstance(frame.get('commandId'), str):
        return
    kind = frame.get('type', '')
    if not isinstance(kind, str) or not re.fullmatch(r'[a-z_]+(?:\.[a-z_]+)+', kind):
        return
    error = frame.get('error')
    emit('remote.command', direction=direction, kind=kind, commandId=frame['commandId'],
         result=kind.split('.')[-1], errorCode=error.get('code') if isinstance(error, dict) else None)


def transport_logger():
    """Replace the transport's NullHandler with a metadata-only error bridge.

    Never enable protocol DEBUG/INFO, even with HQAGENT_LOG_LEVEL=DEBUG: the
    websockets logger includes headers and complete application frames there.
    """
    class TransportHandler(logging.Handler):
        def emit(self, record):
            fields = {}
            if record.exc_info and isinstance(record.exc_info[1], BaseException):
                fields = exception_fields(record.exc_info[1])
            emit('remote.transport', level=record.levelno, **fields)
    logger = logging.Logger('remote.transport.metadata', level=logging.WARNING)
    logger.addHandler(TransportHandler())
    logger.propagate = False
    return logger
