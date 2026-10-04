import asyncio
import time
import os
import subprocess
import sys
from types import SimpleNamespace

from protocol.generated import python as dto

from adapters.manager import AdapterManager
from adapters.events import utc_timestamp
from api.app import create_application
from core.ports import HubPorts
from runtime.composition import build_ports, bind_ports
from runtime.paths import HubPaths
from runtime.repositories import AdapterDirectory
from runtime.workspaces import WorkspaceService
from storage.workspaces import WorkspaceRepository, WorkspaceRecord
from storage.team_profiles import TeamProfileRepository
from remote_support import System, until
from runtime.pi_visibility import HTTP_PROJECTION


class SlowRuntime:
    adapter_id = 'pi'
    display_name = 'Synthetic slow runtime'

    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0
        self.health_calls = 0
        self.version = '1.0.1'
        self.guard = dto.RuntimeGuardView(status='ready', isolation='hub_extension_only', checkedAt=utc_timestamp(), reasons=[])

    async def detect(self):
        assert HTTP_PROJECTION.get() is None  # Detached from the requesting client.
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        return dto.AdapterDescriptor(adapterId=self.adapter_id, displayName=self.display_name,
            integrationKind='cli_stream', authKind='local_login', supportedPlatforms=['windows'],
            installed=True, detectedVersion=self.version, minimumVersion='1.0.0', detectedAt=utc_timestamp(),
            capabilities=[{'id': 'structured_output', 'supported': True}])

    async def health(self):
        self.health_calls += 1
        return dto.AdapterHealth(status='ready', checkedAt=utc_timestamp())

    def verification_configuration(self):
        return ['synthetic']


def test_cached_snapshot_singleflight_refresh_and_explicit_discovery():
    async def scenario():
        runtime = SlowRuntime()
        manager = AdapterManager([runtime])
        try:
            rows = await manager.cached_agents()
            assert rows[0].id == 'local.pi.default' and rows[0].status == 'discovering'
            await runtime.entered.wait()
            for _ in range(20):
                assert (await manager.cached_agents())[0].status == 'discovering'
            # Explicit requests and direct detect share the ongoing real probe.
            explicit = asyncio.create_task(manager.discover())
            detected = asyncio.create_task(manager.detect('pi', refresh=True))
            await asyncio.sleep(.01)
            assert not explicit.done() and runtime.calls == 1
            runtime.release.set()
            assert (await explicit).discovered[0].status == 'ready'
            await detected
            assert runtime.calls == runtime.health_calls == 1
            assert (await manager.cached_agents())[0].version == '1.0.1'
            assert runtime.calls == 1
            runtime.release.clear()
            runtime.version = '1.0.2'
            manager._last_discovery = time.monotonic() - 61
            assert (await manager.cached_agents())[0].version == '1.0.1'
            await until(lambda: runtime.calls == 2)
            for _ in range(20):
                await manager.cached_agents()
            assert runtime.calls == 2
            runtime.release.set()
            await manager._discovery_job
            assert (await manager.cached_agents())[0].version == '1.0.2'
            # A fresh-cache explicit POST still performs new detection.
            await manager.discover()
            assert runtime.calls == runtime.health_calls == 3
        finally:
            await manager.close()
    asyncio.run(scenario())


def test_all_read_routes_stay_fast_with_blocked_detection_and_dependencies(tmp_path, monkeypatch):
    async def scenario():
        system = System(tmp_path)
        runtime = SlowRuntime()
        manager = AdapterManager([runtime])
        system.ports.agents = manager
        system.tasks.directory = AdapterDirectory(manager)
        system.tasks.runtime.adapters = system.tasks.directory
        repo = WorkspaceRepository(system.db)
        repo.save(WorkspaceRecord('workspace', str(tmp_path), 'synthetic', 'git', None, None))
        system.ports.workspaces = WorkspaceService(repo)
        bootstrap = system.application.app.state.local_bootstrap
        with system.db.transaction() as tx:
            identity = system.repo.get('identity', tx)
            identity['wireRevision'] = 5
            system.repo.put('identity', identity, tx)
            system.repo.set_view(tx, dict(state='paired', workerId='worker-test', deviceName='synthetic',
                serverOrigin='https://remote.invalid', connectionStatus='offline', lastConnectedAt=None))
            system.repo.seal(tx)
        entered = {'git': 0, 'update': 0, 'drain': 0}
        gate = asyncio.Event()
        async def git(*args):
            assert HTTP_PROJECTION.get() is None
            entered['git'] += 1
            await gate.wait()
            return 0, 'true'
        async def update_available():
            entered['update'] += 1
            await gate.wait()
            return False, 'Update Agent offline'
        async def active():
            entered['drain'] += 1
            await gate.wait()
            return ['active-task']
        monkeypatch.setattr('runtime.workspaces._git', git)
        bootstrap.update_proxy = SimpleNamespace(availability=update_available)
        system.ports.drain = SimpleNamespace(active_task_ids=active)
        durations = []
        try:
            # The middleware must not publish a catalog (which probes Git) in GET.
            async def no_catalog():
                raise AssertionError('request attempted catalog refresh')
            monkeypatch.setattr(system.worker.projector, 'catalog', no_catalog)
            for _ in range(3):
                for version in ('v1', 'v2'):
                    for endpoint in ('bootstrap', 'agents'):
                        start = time.monotonic()
                        response = await asyncio.wait_for(system.local.get(f'/api/{version}/{endpoint}',
                            headers={'X-HQ-Client-Features': 'pi-v1'}), .5)
                        elapsed = time.monotonic() - start
                        durations.append(elapsed)
                        assert response.status_code == 200, response.text
                        data = response.json()['data']
                        if endpoint == 'agents':
                            assert data[0]['status'] == 'discovering'
                        else:
                            assert data['workspaceCount'] == 1
                            assert not data['currentWorkspace']['capabilities']['canRunWriteTasks']
                            assert not data['features']['updates']['available']
            assert max(durations) < .5 and runtime.calls == 1
            await until(lambda: all(entered.values()))
            assert entered == {'git': 1, 'update': 1, 'drain': 1}
            post = asyncio.create_task(system.local.post('/api/v1/agents/discovery',
                headers={'X-HQ-Client-Features': 'pi-v1', 'Origin': 'http://127.0.0.1'}))
            await asyncio.sleep(.02)
            assert not post.done() and runtime.calls == 1
            runtime.release.set()
            response = await post
            assert response.status_code == 200 and response.json()['data']['discovered'][0]['status'] == 'ready'
            # The legacy client still cannot observe PI during or after discovery.
            old = await system.local.get('/api/v1/agents')
            assert old.json()['data'] == []
            print(f'blocked Runtime/Git/update/drain: {len(durations)} reads, max={max(durations)*1000:.1f}ms')
        finally:
            gate.set()
            await bootstrap.close()
            await manager.close()
            await system.close()
    asyncio.run(scenario())


def test_startup_discovers_in_background_without_blocking_ready_or_seeding_placeholders(tmp_path, monkeypatch):
    async def scenario():
        runtime = SlowRuntime()
        runtime.adapter_id = 'codex'
        manager = AdapterManager([runtime])
        monkeypatch.setattr('runtime.composition._build_agent_port', lambda: manager)
        ports = build_ports()
        application = create_application(paths=HubPaths.resolve(tmp_path), token='test', ports=ports)
        started = time.monotonic()
        await asyncio.wait_for(bind_ports(application, ports), .3)
        assert runtime.calls == 0 and not TeamProfileRepository(application.database).list()
        async with application.app.router.lifespan_context(application.app):
            assert time.monotonic() - started < .5
            await runtime.entered.wait()
            assert runtime.calls == 1  # Initial discovery does not need a GET.
            snapshot = await application.app.state.local_bootstrap.build()
            assert snapshot.agents.total == 1 and snapshot.agents.ready == 0
            runtime.release.set()
            await manager._discovery_job
            assert len(TeamProfileRepository(application.database).list()) == 1
    asyncio.run(scenario())


def test_failed_background_detector_keeps_known_instance_and_retries_only_when_due():
    async def scenario():
        runtime = SlowRuntime()
        async def failed():
            runtime.calls += 1
            raise RuntimeError('private failure text')
        runtime.detect = failed
        manager = AdapterManager([runtime])
        try:
            await manager.cached_agents()
            await manager._discovery_job
            for _ in range(10):
                row = (await manager.cached_agents())[0]
                assert row.status == 'error' and row.id == 'local.pi.default'
                assert 'private failure' not in row.model_dump_json()
            assert runtime.calls == 1
        finally:
            await manager.close()
    asyncio.run(scenario())


def test_update_proxy_pid_query_is_read_only():
    from api.update_proxy import UpdateAgentProxy
    # Use the actual interpreter, not the Windows venv redirector's wrapper PID.
    child = subprocess.Popen([getattr(sys, '_base_executable', sys.executable), '-B', '-c',
        'import time; time.sleep(10)'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        assert UpdateAgentProxy._pid_exists(child.pid)
        time.sleep(.05)
        assert child.poll() is None
    finally:
        child.terminate()
        child.wait(timeout=5)
    assert not UpdateAgentProxy._pid_exists(child.pid)


def test_shutdown_cancels_background_detection_without_restarting_it():
    async def scenario():
        runtime = SlowRuntime()
        manager = AdapterManager([runtime])
        manager.start()
        await runtime.entered.wait()
        await asyncio.wait_for(manager.close(), .5)
        assert manager._discovery_job.done()
        assert all(job.done() for job in manager._detect_jobs.values())
        await manager.cached_agents()
        assert runtime.calls == 1
    asyncio.run(scenario())
