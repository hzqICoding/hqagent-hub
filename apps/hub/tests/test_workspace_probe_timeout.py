import asyncio
import time

import pytest

from runtime import workspaces
from remote_support import System
from storage.workspaces import WorkspaceRecord, WorkspaceRepository


class HeldGit:
    def __init__(self):
        self.returncode = None
        self.killed = False

    async def communicate(self):
        await asyncio.Event().wait()

    def kill(self):
        self.killed = True
        self.returncode = -9

    async def wait(self):
        return self.returncode


def test_git_timeout_and_cancel_reap_owned_process(monkeypatch, tmp_path):
    async def scenario():
        calls = []
        processes = []
        async def launch(*args, **kwargs):
            calls.append(kwargs)
            process = HeldGit()
            processes.append(process)
            return process
        monkeypatch.setattr(workspaces.asyncio, 'create_subprocess_exec', launch)
        monkeypatch.setattr(workspaces, 'GIT_TIMEOUT_SECONDS', .02)
        assert await workspaces._git(tmp_path, 'status', '--porcelain') == (124, '')
        assert processes[0].killed and calls[0]['stdin'] == asyncio.subprocess.DEVNULL
        task = asyncio.create_task(workspaces._git(tmp_path, 'status', '--porcelain'))
        while len(processes) < 2:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert processes[1].killed
    asyncio.run(scenario())


def test_workspace_and_bootstrap_bound_all_slow_repositories_and_degrade(monkeypatch, tmp_path):
    async def scenario():
        system = System(tmp_path)
        spawned = []
        async def launch(*args, **kwargs):
            process = HeldGit()
            spawned.append(process)
            return process
        try:
            repo = WorkspaceRepository(system.db)
            system.ports.workspaces = workspaces.WorkspaceService(repo)
            for i in range(30):
                path = tmp_path / f'slow-{i:02}'
                path.mkdir()
                repo.save(WorkspaceRecord(f'slow-{i:02}', str(path), f'slow-{i:02}', 'git', None, None))
            monkeypatch.setattr(workspaces.asyncio, 'create_subprocess_exec', launch)
            monkeypatch.setattr(workspaces, 'GIT_TIMEOUT_SECONDS', .03)
            monkeypatch.setattr(workspaces, 'WORKSPACE_QUERY_SECONDS', .06)
            for endpoint in ('/api/v1/workspaces', '/api/v1/bootstrap'):
                start = time.monotonic()
                response = await system.local.get(endpoint)
                assert response.status_code == 200, response.text
                assert time.monotonic() - start < .8
                data = response.json()['data']
                rows = data if isinstance(data, list) else [data['currentWorkspace']]
                assert (len(data) if isinstance(data, list) else data['workspaceCount']) == 30
                for row in rows:
                    assert row['vcs'] == 'git'
                    assert 'isClean' not in row and 'branch' not in row
                    assert row['capabilities']['canRunWriteTasks'] is False
                    assert row['capabilities']['canInitGit'] is False
                    assert row['capabilities']['reason'] == workspaces.GIT_STATE_UNKNOWN_REASON
            assert spawned and all(p.killed for p in spawned)
            assert len(spawned) < 10  # Budget does not multiply by the 30 workspaces.
            assert all(r.vcs == 'git' for r in repo.list())
            # A later healthy read recovers capabilities; degraded facts are not stored.
            async def git(path, *args):
                return 0, 'true' if args[0] == 'rev-parse' else 'main' if args[0] == 'branch' else ''
            monkeypatch.setattr(workspaces, '_git', git)
            view = await system.ports.workspaces.get_workspace('slow-00')
            assert view.is_clean is True and view.capabilities.can_run_write_tasks
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('stage', ['rev-parse', 'branch', 'status'])
def test_each_timed_out_git_stage_is_unknown_not_non_git(monkeypatch, tmp_path, stage):
    async def scenario():
        async def git(path, *args):
            return (124, '') if args[0] == stage else (0, 'true' if args[0] == 'rev-parse' else 'main')
        monkeypatch.setattr(workspaces, '_git', git)
        service = workspaces.WorkspaceService(None)
        view = await service._to_view(WorkspaceRecord('workspace', str(tmp_path), 'workspace', 'git', None, None))
        assert view.vcs == 'git' and view.is_clean is None
        assert not view.capabilities.can_run_write_tasks and not view.capabilities.can_init_git
    asyncio.run(scenario())
