import asyncio
import json
import logging
from pathlib import Path
import sys
import time

import pytest
from fastapi import Request

from api.envelopes import success_response, error_response
from core.diagnostics import configure_logging, emit, Redactor, remote_command, transport_logger
from core.errors import HubError
from runtime.loop_monitor import LoopMonitor
from runtime.paths import HubPaths
from adapters.process import ProcessRunner
from remote_support import System, TOKEN


def records(log):
    log.flush()
    return [json.loads(line) for line in log.path.read_text('utf-8').splitlines()] if log.path.exists() else []


def test_log_defaults_utf8_rotation_and_metadata_whitelist(tmp_path, monkeypatch):
    monkeypatch.delenv('HQAGENT_LOG_LEVEL', raising=False)
    log = configure_logging(tmp_path, max_bytes=700, backups=2)
    try:
        assert log.level == logging.INFO and log.path == tmp_path / 'logs/hub.log'
        for n in range(30):
            emit('verification.state', jobId=f'job-{n}', status='failed', cleanupState='confirmed', slotHeld=False,
                 prompt='PROMPT_PRIVATE', body='BODY_PRIVATE', message='中文正文禁止记录', token='TOKEN_PRIVATE')
        rows = records(log)
        files = list(log.path.parent.glob('hub.log*'))
        assert len(files) == 3 and log.path.with_name('hub.log.2').exists()
        whole = ''.join(p.read_text('utf-8') for p in files)
        assert all(value not in whole for value in ('PROMPT_PRIVATE', 'BODY_PRIVATE', '正文禁止记录', 'TOKEN_PRIVATE'))
        assert rows[-1]['jobId'] == 'job-29'
        assert set(rows[-1]) == {'ts', 'level', 'logger', 'event', 'jobId', 'status', 'cleanupState', 'slotHeld'}
        emit('hub.starting', dataRoot='合成数据目录', port=1234, appVersion='0.1.0', protocolVersion='0.11.1',
             environment='test', desktop=True)
        assert records(log)[-1]['dataRoot'] == '合成数据目录'
    finally:
        log.close()


def test_central_redaction_and_existing_legacy_loggers_never_copy_messages(tmp_path, monkeypatch):
    monkeypatch.setenv('SYNTHETIC_API_KEY', 'env-private-api-value')
    log = configure_logging(tmp_path, secrets=('known-private-credential',), level='DEBUG')
    values = ['Bearer AUTH_PRIVATE', 'ticket=TICKET_PRIVATE', 'Cookie: localSession=COOKIE_PRIVATE',
              'sk-PRIVATE_KEY_123', 'api_key=KEY_PRIVATE', 'known-private-credential', 'env-private-api-value']
    try:
        for text in values:
            emit('verification.state', jobId=text, status='failed')
        # These foreign payload-bearing libraries are deliberately never copied.
        for name in ('websockets.client', 'httpx', 'httpcore.connection', 'uvicorn.access'):
            logger = logging.getLogger(name)
            before = logger.level
            logger.setLevel(logging.DEBUG)
            logger.error('FOREIGN_BODY_PRIVATE %s', 'Bearer HEADER_PRIVATE')
            logger.setLevel(before)
        try:
            private_local = 'LOCAL_PRIVATE'
            raise RuntimeError('EXCEPTION_BODY_PRIVATE Cookie: EXCEPTION_COOKIE_PRIVATE')
        except RuntimeError:
            logging.getLogger('runtime.local_chat').error('MESSAGE_PRIVATE %s', private_local, exc_info=True)
            transport = transport_logger()
            transport.debug('WS_FRAME_PRIVATE')
            transport.error('WS_ERROR_BODY_PRIVATE Bearer WS_CREDENTIAL_PRIVATE', exc_info=True)
        rows = records(log)
        text = log.path.read_text('utf-8')
        for secret in ['AUTH_PRIVATE', 'TICKET_PRIVATE', 'COOKIE_PRIVATE', 'PRIVATE_KEY_123', 'KEY_PRIVATE',
                       'known-private-credential', 'env-private-api-value', 'FOREIGN_BODY_PRIVATE', 'HEADER_PRIVATE',
                       'LOCAL_PRIVATE', 'EXCEPTION_BODY_PRIVATE', 'EXCEPTION_COOKIE_PRIVATE', 'MESSAGE_PRIVATE',
                       'WS_FRAME_PRIVATE', 'WS_ERROR_BODY_PRIVATE', 'WS_CREDENTIAL_PRIVATE']:
            assert secret not in text
        legacy = next(r for r in rows if r['event'] == 'legacy.error')
        assert legacy['exceptionType'] == 'RuntimeError' and legacy['stack']
        assert all(set(f) == {'file', 'line', 'function'} for f in legacy['stack'])
        assert any(r['event'] == 'remote.transport' and r['exceptionType'] == 'RuntimeError' for r in rows)
        assert Redactor().text('ticket=abc Cookie: session=def') == '[redacted] [redacted]'
    finally:
        log.close()


def test_http_metadata_routes_ids_auth_errors_and_no_bodies_or_secrets(tmp_path):
    async def scenario():
        log = configure_logging(tmp_path / 'logs-root', secrets=(TOKEN,), level='DEBUG')
        system = System(tmp_path / 'system')
        app = system.application.app
        private = ['HUB_TOKEN_PRIVATE', 'WS_TICKET_PRIVATE', 'COOKIE_PRIVATE', 'DEVICE_PRIVATE',
                   'PAIRCODE_PRIVATE', 'PAT_PRIVATE', 'APIKEY_PRIVATE', 'REQUEST_BODY_PRIVATE',
                   'RESPONSE_BODY_PRIVATE', 'PROMPT_PRIVATE', 'MODEL_OUTPUT_PRIVATE', 'ATTACHMENT_PRIVATE']
        @app.post('/api/v1/diagnostic-probe/{identifier}')
        async def echo(identifier: str, request: Request):
            await request.body()
            return success_response({'text': private})
        @app.get('/api/v1/diagnostic-error')
        async def error():
            return error_response(HubError('INTERNAL', 'EXCEPTION_BODY_PRIVATE'))
        @app.get('/api/v1/diagnostic-crash')
        async def crash():
            private_variable = 'LOCAL_CONTENT_PRIVATE'
            raise RuntimeError(private_variable)
        try:
            reply = await system.local.post('/api/v1/diagnostic-probe/HUB_TOKEN_PRIVATE?ticket=WS_TICKET_PRIVATE&body=QUERY_PRIVATE',
                headers={'Cookie': 'localSession=COOKIE_PRIVATE'}, json=dict(zip(private, private)))
            assert reply.status_code == 200 and 'x-request-id' not in reply.headers
            failure = await system.local.get('/api/v1/diagnostic-error')
            assert failure.status_code == 500
            with pytest.raises(RuntimeError):
                await system.local.get('/api/v1/diagnostic-crash?secret=QUERY_PRIVATE')
            await system.local.get('/healthz', headers={'Authorization': '', 'Cookie': ''})
            await system.local.get('/healthz', headers={'Authorization': '', 'Cookie': 'localSession=COOKIE_PRIVATE'})
            # Issued response-only secrets must not be captured either.
            ticket = await system.local.post('/api/v1/auth/ws-ticket')
            ticket_value = ticket.json()['data']['ticket']
            # Existing maintenance request-ID mapping stays byte-for-byte authoritative.
            existing = await system.local.get('/api/v1/agents/image-verifications', headers={'X-Request-Id': 'request-original'})
            assert existing.headers['x-request-id'] == existing.json()['requestId'] == 'request-original'
            rows = records(log)
            text = log.path.read_text('utf-8')
            assert all(value not in text for value in [*private, TOKEN, ticket_value, 'QUERY_PRIVATE', 'LOCAL_CONTENT_PRIVATE', 'EXCEPTION_BODY_PRIVATE'])
            access = next(r for r in rows if r.get('route') == '/api/v1/diagnostic-probe/{identifier}')
            assert access['requestId'] == reply.json()['requestId'] and access['auth'] == 'bearer'
            assert access['method'] == 'POST' and access['status'] == 200 and access['elapsedMs'] >= 0
            assert next(r for r in rows if r['event'] == 'http.access' and r.get('status') == 500)['errorCode'] == 'INTERNAL'
            assert any(r['event'] == 'http.exception' and r['stack'] for r in rows)
            health = [r for r in rows if r.get('route') == '/healthz']
            assert {r['auth'] for r in health} == {'none', 'cookie'}
            assert all(r['level'] == 'DEBUG' for r in health)
            assert any(r.get('requestId') == 'request-original' for r in rows)
        finally:
            await system.close()
            log.close()
    asyncio.run(scenario())


def test_health_success_is_silent_at_default_level(tmp_path):
    async def scenario():
        log = configure_logging(tmp_path / 'logs-root')
        system = System(tmp_path / 'system')
        try:
            response = await system.local.get('/healthz')
            assert response.status_code == 200
            assert not any(r.get('route') == '/healthz' for r in records(log))
        finally:
            await system.close()
            log.close()
    asyncio.run(scenario())


def test_log_failure_is_one_safe_warning_and_does_not_block_data_root(tmp_path, capsys):
    (tmp_path / 'logs').write_text('not a directory')
    paths = HubPaths.resolve(tmp_path)
    paths.create()
    log = configure_logging(tmp_path)
    try:
        for _ in range(3):
            emit('hub.starting', dataRoot=str(tmp_path))
            log.disable_file()
        assert log.file is None
        assert paths.data.is_dir() and paths.runtime.is_dir()
        assert capsys.readouterr().err.count('Hub file logging unavailable') == 1
    finally:
        log.close()


def test_loop_blocked_stack_from_independent_thread_is_bounded_and_once(tmp_path):
    async def scenario():
        log = configure_logging(tmp_path)
        monitor = LoopMonitor(interval=.03, threshold=.02, stack_after=.08)
        try:
            monitor.start()
            private_local = 'FRAME_LOCAL_PRIVATE'
            time.sleep(.45)  # Intentionally blocks the monitored loop.
            await asyncio.sleep(.07)
            rows = records(log)
            blocked = [r for r in rows if r['event'] == 'loop.blocked']
            assert len(blocked) == 1 and blocked[0]['lagMs'] >= 80
            assert 0 < len(blocked[0]['stack']) <= 32
            assert any(f['function'] == 'scenario' for f in blocked[0]['stack'])
            assert any(r['event'] == 'loop.lag' for r in rows)
            assert private_local not in log.path.read_text('utf-8')
            assert all(set(frame) == {'file', 'line', 'function'} for frame in blocked[0]['stack'])
            time.sleep(.2)
            await asyncio.sleep(.04)
            assert len([r for r in records(log) if r['event'] == 'loop.blocked']) == 2
        finally:
            await monitor.close()
            log.close()
    asyncio.run(scenario())


def test_monitor_environment_switch_is_off(tmp_path, monkeypatch):
    monkeypatch.setenv('HQAGENT_LOOP_MONITOR', '0')
    async def scenario():
        log = configure_logging(tmp_path)
        monitor = LoopMonitor(interval=.01, threshold=.01, stack_after=.02)
        try:
            monitor.start()
            time.sleep(.06)
            await asyncio.sleep(.03)
            assert monitor.thread is None and monitor.task is None
            assert not any(r['event'].startswith('loop.') for r in records(log))
        finally:
            await monitor.close()
            log.close()
    asyncio.run(scenario())


def test_default_monitor_captures_a_one_second_block_before_loop_recovers(tmp_path):
    async def scenario():
        log = configure_logging(tmp_path)
        monitor = LoopMonitor()
        try:
            assert (monitor.interval, monitor.threshold, monitor.stack_after) == (.5, .3, 1.0)
            monitor.start()
            time.sleep(1.2)
            # Reading the file here still runs before the monitor coroutine:
            # only the watchdog + log writer threads could produce this record.
            rows = records(log)
            assert len([r for r in rows if r['event'] == 'loop.blocked']) == 1
        finally:
            await monitor.close()
            log.close()
    asyncio.run(scenario())


def test_process_logs_omit_command_arguments_environment_and_output(tmp_path):
    async def scenario():
        log = configure_logging(tmp_path)
        try:
            result = await ProcessRunner().run([sys.executable, '-B', '-c',
                'print("PROCESS_OUTPUT_PRIVATE")', 'PROCESS_ARG_PRIVATE'], timeout=5)
            assert result.returncode == 0
            await asyncio.sleep(.02)
            rows = records(log)
            assert any(r['event'] == 'process.started' and r['pid'] > 0 for r in rows)
            assert any(r['event'] == 'process.exited' and r['exitCode'] == 0 for r in rows)
            text = log.path.read_text('utf-8')
            assert 'PROCESS_OUTPUT_PRIVATE' not in text and 'PROCESS_ARG_PRIVATE' not in text
        finally:
            log.close()
    asyncio.run(scenario())


def test_remote_command_logging_is_metadata_only(tmp_path):
    log = configure_logging(tmp_path)
    try:
        remote_command({'type': 'command.failed', 'commandId': 'command-test',
            'payload': {'text': 'REMOTE_BODY_PRIVATE'}, 'error': {'code': 'INTERNAL', 'message': 'REMOTE_ERROR_PRIVATE'},
            'deviceSecret': 'DEVICE_PRIVATE'}, 'received')
        row = records(log)[-1]
        assert row['kind'] == 'command.failed' and row['commandId'] == 'command-test' and row['errorCode'] == 'INTERNAL'
        assert 'PRIVATE' not in log.path.read_text('utf-8')
    finally:
        log.close()


def test_runtime_device_secret_is_redacted_even_when_echoed_as_command_id(tmp_path):
    from runtime.remote.security import CredentialVault
    secret = 'synthetic-device-credential-unprefixed'
    vault = CredentialVault(tmp_path / 'remote')
    vault.posix = None  # Never store a synthetic test credential in a real keyring.
    vault.save(secret)
    log = configure_logging(tmp_path)
    try:
        assert vault.read() == secret
        remote_command({'type': 'run.submit', 'commandId': secret, 'payload': {'text': 'PRIVATE'}}, 'received')
        row = records(log)[-1]
        assert row['commandId'] == '[redacted]'
        assert secret not in log.path.read_text('utf-8')
    finally:
        log.close()


def test_real_remote_transport_logs_state_and_commands_without_pairing_secrets(tmp_path):
    from remote_support import FakeRemoteServer, until, command_events
    async def scenario():
        log = configure_logging(tmp_path / 'logs-root', secrets=(TOKEN,))
        system = System(tmp_path / 'system')
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                secret = system.link.vault.read()
                frame = system.command('log-command')
                frame['payload']['text'] = 'REMOTE_PROMPT_PRIVATE'
                await server.send(frame)
                await until(lambda: command_events(server, 'log-command', 'command.completed'))
                rows = records(log)
                command_rows = [r for r in rows if r['event'] == 'remote.command' and r['commandId'] == 'log-command']
                assert {'received', 'queued', 'sent'} <= {r['direction'] for r in command_rows}
                assert any(r['event'] == 'remote.state' and r.get('connectionStatus') == 'online' for r in rows)
                text = log.path.read_text('utf-8')
                assert all(v not in text for v in (secret, TOKEN, 'ABCD2345', 'REMOTE_PROMPT_PRIVATE', 'remote result'))
        finally:
            await system.close()
            log.close()
    asyncio.run(scenario())


def test_metadata_events_cover_discovery_models_guard_jobs_deletion_and_preparation(tmp_path, monkeypatch):
    from protocol.generated import python as dto
    from adapters.manager import AdapterManager
    from adapters.pi_adapter import PiAdapter, denied
    from adapters.failures import failure
    from core.diagnostics import catalog_logged
    from test_bootstrap_cached_discovery import SlowRuntime
    from test_local_image_jobs import setup
    from test_r16_attachments import headers
    from remote_support import until
    async def scenario():
        log = configure_logging(tmp_path / 'logs-root', secrets=(TOKEN,))
        system = System(tmp_path / 'system')
        runtime = SlowRuntime()
        runtime.release.set()
        manager = AdapterManager([runtime])
        coordinator, adapter, request = setup(tmp_path / 'verification', monkeypatch)
        class Catalog:
            @catalog_logged('pi')
            async def list_models(self, identifier):
                return dto.LocalAgentModelsView(agentInstanceId=identifier, models=[], verified=False,
                    reason='MODEL_CATALOG_CONTENT_PRIVATE')
        try:
            await manager.discover()
            await Catalog().list_models('local.pi.default')
            pi = PiAdapter(storage_dir=tmp_path / 'pi')
            pi._guard_view('blocked', 'guard_not_loaded')
            denied('AGENT_IMAGE_UNSUPPORTED', message='ADAPTER_MESSAGE_PRIVATE')
            failure(dto.AdapterFailureKind.AGENT_ERROR, 'MODEL_OUTPUT_PRIVATE', retryable=False, raw='RAW_PRIVATE')
            job = await coordinator.start(request(), 'key', 'req')
            await coordinator.tasks[job.job_id]
            conv = await system.local.post('/api/v2/conversations', json={'title': 'TITLE_PRIVATE',
                'workspaceId': 'workspace', 'sceneId': 'analyze'}, headers={'Idempotency-Key': 'create'})
            cid = conv.json()['data']['id']
            body = b'FILE_CONTENT_PRIVATE'
            uploaded = await system.local.post(f'/api/v2/conversations/{cid}/attachments', content=body,
                headers=headers(body, name='FILE_NAME_PRIVATE.txt'))
            assert uploaded.status_code == 201
            attachment = uploaded.json()['data']['attachment']['attachmentId']
            await system.chat.start()
            sent = await system.local.post(f'/api/v2/conversations/{cid}/messages', json={'clientMessageId': 'message',
                'text': 'USER_MESSAGE_PRIVATE', 'sessionMode': 'new', 'attachmentIds': [attachment]},
                headers={'Idempotency-Key': 'send'})
            assert sent.status_code == 202
            run = sent.json()['data']['runId']
            await until(lambda: system.chat.repository.run_record(run)['status'] == 'succeeded')
            empty = system.chat.repository.create_conversation(dto.CreateLocalConversationInput(
                title='DELETE_TITLE_PRIVATE', workspaceId='workspace', sceneId='analyze'), 'delete')
            await system.chat.delete_conversation(empty.id, 1, 'delete')
            with system.db.transaction() as tx:
                system.repo.set_view(tx, {'state': 'unpaired', 'lastErrorCode': 'REMOTE_SERVER_UNREACHABLE'})
                system.repo.put('sync-work', {'phase': 'resetting'}, tx)
            rows = records(log)
            assert {'agent.discovery', 'agent.models', 'agent.guard', 'agent.failure', 'verification.state',
                    'conversation.deletion', 'attachment.preparation', 'remote.state', 'remote.sync'} <= {r['event'] for r in rows}
            assert {'pending', 'preparing', 'ready', 'starting', 'started'} <= {r['status'] for r in rows if r['event'] == 'attachment.preparation'}
            assert {'cleaning', 'completed'} <= {r['status'] for r in rows if r['event'] == 'conversation.deletion'}
            assert 'PRIVATE' not in log.path.read_text('utf-8')
        finally:
            await coordinator.close()
            await manager.close()
            await system.close()
            log.close()
    asyncio.run(scenario())


def test_log_queue_is_bounded_and_slow_disk_does_not_block_emit(tmp_path, monkeypatch):
    import threading
    log = configure_logging(tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = log.file.handle
    def slow(record):
        entered.set()
        release.wait(3)
        original(record)
    monkeypatch.setattr(log.file, 'handle', slow)
    try:
        emit('process.started', pid=123, mode='probe')
        assert entered.wait(1)
        start = time.monotonic()
        for n in range(2200):
            emit('process.started', pid=n + 1, mode='probe')
        assert time.monotonic() - start < 1
        assert log.queue.qsize() <= 2048 and log.dropped > 0
    finally:
        release.set()
        log.close()


def test_file_write_failure_disables_logging_without_escaping_to_caller(tmp_path, capsys, monkeypatch):
    log = configure_logging(tmp_path)
    def failed(record):
        raise OSError('DISK_PRIVATE_ERROR')
    monkeypatch.setattr(log.file, 'handle', failed)
    try:
        emit('process.started', pid=123, mode='probe')
        log.flush()
        emit('process.started', pid=124, mode='probe')
        assert log.file is None
        message = capsys.readouterr().err
        assert message.count('Hub file logging unavailable') == 1
        assert 'DISK_PRIVATE_ERROR' not in message
    finally:
        log.close()


def test_log_level_environment_controls_file_threshold(tmp_path, monkeypatch):
    monkeypatch.setenv('HQAGENT_LOG_LEVEL', 'warning')
    log = configure_logging(tmp_path)
    try:
        emit('process.started', pid=123, mode='probe')
        emit('loop.lag', level=logging.WARNING, lagMs=345)
        assert [r['event'] for r in records(log)] == ['loop.lag']
    finally:
        log.close()
