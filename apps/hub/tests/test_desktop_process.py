import asyncio
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import threading
from http.client import HTTPConnection

import pytest
from fastapi.testclient import TestClient
from protocol.generated.python import HubRuntimeDescriptor, SendLocalMessageInput, CreateLocalConversationInput
from runtime.parent_process import ParentProcess, serve_with_parent, watch_parent
from runtime.paths import HubPaths
from api.app import create_application
from remote_support import System, until


def test_parent_environment_is_opt_in_and_validated(tmp_path):
    assert ParentProcess.from_env({}) == ParentProcess()
    actual = ParentProcess.from_env({'HQAGENT_RUNTIME_DIR': str(tmp_path),
                                    'HQAGENT_INSTANCE_ID': 'desktop-launch-123',
                                    'HQAGENT_PARENT_CONTROL': 'stdio-v1'})
    assert actual.stdio and actual.instance_id == 'desktop-launch-123' and actual.runtime_dir == tmp_path.resolve()
    for env in ({'HQAGENT_RUNTIME_DIR': 'relative'}, {'HQAGENT_INSTANCE_ID': 'short'},
                {'HQAGENT_PARENT_CONTROL': 'unknown'}):
        with pytest.raises(ValueError):
            ParentProcess.from_env(env)


@pytest.mark.parametrize('text', ['shutdown\n', '', 'ignored\r\nshutdown\r\n', 'x' * 5000 + '\nshutdown\n'])
def test_bounded_parent_reader_shutdown_and_eof(text):
    async def scenario():
        event = asyncio.Event()
        thread = watch_parent(io.StringIO(text), asyncio.get_running_loop(), event)
        await asyncio.wait_for(event.wait(), 2)
        assert thread.daemon
    asyncio.run(scenario())


def test_tauri_bearer_origins_and_cookie_boundary_remain_exact(tmp_path):
    hub = create_application(paths=HubPaths.resolve(tmp_path), token='test-operator',
                             allowed_hosts={'testserver'})
    with TestClient(hub.app) as client:
        for origin in ('http://tauri.localhost', 'https://tauri.localhost'):
            preflight = client.options('/api/v1/bootstrap', headers={
                'Origin': origin, 'Access-Control-Request-Method': 'GET',
                'Access-Control-Request-Headers': 'authorization'})
            assert preflight.status_code == 204
            assert preflight.headers['access-control-allow-origin'] == origin
            assert client.get('/api/v1/bootstrap', headers={'Origin': origin}).status_code == 401
            result = client.get('/api/v1/remote/link', headers={'Origin': origin, 'Authorization': 'Bearer test-operator'})
            assert result.status_code == 200
            assert result.headers['access-control-allow-origin'] == origin
            assert 'test-operator' not in result.text
        for origin in ('https://evil.example', 'https://tauri.localhost.evil.example', 'http://tauri.localhost:8888'):
            assert client.get('/api/v1/remote/link', headers={'Origin': origin, 'Authorization': 'Bearer test-operator'}).status_code == 403
        code = hub.local_auth.issue_code()
        assert client.post('/api/v2/auth/local-session', json={'code': code}).status_code == 403
        assert client.post('/api/v2/auth/local-session', json={'code': code}, headers={'Origin': 'http://testserver'}).status_code == 200
        assert client.get('/api/v2/conversations').status_code == 200
        assert client.post('/api/v2/conversations', json={}).status_code == 403
        assert client.get('/api/v2/conversations', headers={'Origin': 'https://evil.example'}).status_code == 403
        hub.app.state.shutting_down = True
        result = client.post('/api/v2/conversations', json={}, headers={'Origin': 'http://testserver'})
        assert result.status_code == 503 and result.json()['error']['code'] == 'HUB_MAINTENANCE'


def test_parent_shutdown_preserves_inflight_recovery_state(tmp_path):
    async def scenario():
        system = System(tmp_path, hold=True)
        class Server:
            should_exit = False
            async def serve(self, *, sockets):
                async with system.application.app.router.lifespan_context(system.application.app):
                    conv = await system.chat.create_conversation(CreateLocalConversationInput(
                        workspaceId='workspace', sceneId='analyze', title='shutdown fixture'), 'create')
                    receipt = system.chat.send(conv.id, SendLocalMessageInput(clientMessageId='message', text='hold', sessionMode='new'), 'send')
                    await until(lambda: system.chat.repository.run_record(receipt.run_id)['task_id'] is not None)
                    self.task_id = system.chat.repository.run_record(receipt.run_id)['task_id']
                    release.set()
                    await until(lambda: self.should_exit)
        release = threading.Event()
        class Input:
            def readline(self, _limit):
                release.wait(5)
                return 'shutdown\n'
        server = Server()
        try:
            await serve_with_parent(server, None, system.application, Input())
            assert system.chat._quiescing
            assert system.tasks.state.get('task_spec:' + server.task_id)['recoveryRequired'] is True
            assert str(system.tasks.repository.get(server.task_id).status) == 'paused'
            assert system.worker.socket is None
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('control', ['shutdown', 'eof'])
def test_real_source_process_desktop_lifetime(tmp_path, control):
    env = dict(os.environ)
    for key in ('HQAGENT_HUB_DATA_DIR', 'HQAGENT_PARENT_CONTROL', 'HQAGENT_RUNTIME_DIR', 'HQAGENT_INSTANCE_ID'):
        env.pop(key, None)
    runtime = tmp_path / 'shell-runtime'
    env.update(HQAGENT_PARENT_CONTROL='stdio-v1', HQAGENT_RUNTIME_DIR=str(runtime),
               HQAGENT_INSTANCE_ID='test-desktop-launch', PYTHONDONTWRITEBYTECODE='1',
               LOCALAPPDATA=str(tmp_path / 'app-data'), HOME=str(tmp_path), USERPROFILE=str(tmp_path),
               HQAGENT_CODEX_PATH=str(tmp_path / 'missing'), HQAGENT_CLAUDE_PATH=str(tmp_path / 'missing'))
    data = tmp_path / 'data-root'
    child = subprocess.Popen([sys.executable, '-B', '-m', 'runtime.main', '--data-dir', str(data)],
                             cwd=Path(__file__).resolve().parents[1], env=env, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 25
        descriptor = None
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise AssertionError(f'Hub exited before ready: {child.returncode}: {child.stderr.read().decode(errors="replace")}')
            path = runtime / 'hub.json'
            if path.exists():
                descriptor = HubRuntimeDescriptor.model_validate_json(path.read_text(encoding='utf-8'))
                connection = HTTPConnection('127.0.0.1', descriptor.port, timeout=0.5)
                try:
                    connection.request('GET', '/healthz')
                    if connection.getresponse().status == 200:
                        break
                except OSError:
                    pass
                finally:
                    connection.close()
            time.sleep(0.1)
        else:
            pytest.fail('Hub health timeout')
        assert descriptor.instance_id == 'test-desktop-launch'
        # Windows venv python.exe is a redirector with a separate interpreter PID.
        assert descriptor.pid > 0 and descriptor.port >= 1024
        assert not (data / 'runtime' / 'hub.json').exists()
        if control == 'shutdown':
            # Descriptor placement must not allow two Hubs to own one database.
            duplicate_env = {**env, 'HQAGENT_RUNTIME_DIR': str(tmp_path / 'other-runtime'),
                             'HQAGENT_INSTANCE_ID': 'other-launch-123'}
            duplicate = subprocess.run(
                [sys.executable, '-B', '-m', 'runtime.main', '--data-dir', str(data)],
                cwd=Path(__file__).resolve().parents[1], env=duplicate_env,
                input=b'', capture_output=True, timeout=15,
            )
            assert duplicate.returncode == 2
            assert (runtime / 'hub.json').exists()
            assert not (tmp_path / 'other-runtime' / 'hub.json').exists()
        start = time.monotonic()
        if control == 'shutdown':
            child.stdin.write(b'shutdown\n')
            child.stdin.flush()
        else:
            child.stdin.close()
            child.stdin = None
        assert child.wait(timeout=15) == 0
        assert time.monotonic() - start < 15
        output, errors = child.communicate()
        assert descriptor.token.encode() not in output + errors
        assert not (runtime / 'hub.json').exists()
        assert not (data / 'runtime' / 'hub.lock').exists()
    finally:
        if child.stdin is not None:
            child.stdin.close()
            child.stdin = None
        if child.poll() is None:
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


def test_unmanaged_run_ignores_stdin_and_uses_legacy_paths(tmp_path, monkeypatch):
    from runtime import main
    for name in ('HQAGENT_PARENT_CONTROL', 'HQAGENT_RUNTIME_DIR', 'HQAGENT_INSTANCE_ID'):
        monkeypatch.delenv(name, raising=False)
    class Input:
        def readline(self, *_):
            raise AssertionError('unmanaged Hub must not watch stdin')
    class Server:
        started = False
        def __init__(self, config):
            self.config = config
        async def serve(self, *, sockets):
            raw = json.loads((tmp_path / 'runtime' / 'hub.json').read_text(encoding='utf-8'))
            assert raw['instanceId'].startswith('hub_')
            assert raw['baseUrl'].startswith('http://127.0.0.1:')
    async def bind(*_):
        pass
    monkeypatch.setattr(main.sys, 'stdin', Input())
    monkeypatch.setattr(main.uvicorn, 'Server', Server)
    monkeypatch.setattr(main, 'bind_ports', bind)
    asyncio.run(main.run(tmp_path))
    assert not (tmp_path / 'runtime' / 'hub.json').exists()
    assert not (tmp_path / 'runtime' / 'hub.lock').exists()


def test_parent_eof_before_health_exits_without_orphan(tmp_path):
    env = {**os.environ, 'HQAGENT_PARENT_CONTROL': 'stdio-v1',
           'HQAGENT_RUNTIME_DIR': str(tmp_path / 'runtime'),
           'HQAGENT_INSTANCE_ID': 'early-eof-launch',
           'HQAGENT_CODEX_PATH': str(tmp_path / 'missing'),
           'HQAGENT_CLAUDE_PATH': str(tmp_path / 'missing')}
    result = subprocess.run([sys.executable, '-B', '-m', 'runtime.main', '--data-dir', str(tmp_path)],
                            cwd=Path(__file__).resolve().parents[1], env=env,
                            input=b'', capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    assert not (tmp_path / 'runtime' / 'hub.json').exists()
    assert not (tmp_path / 'runtime' / 'hub.lock').exists()
