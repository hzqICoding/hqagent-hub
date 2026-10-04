from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from adapters.process import ProcessRunner, terminate_process_tree
from core.errors import HubError
from runtime import descriptor, review_evidence
from runtime.directory_picker import LocalDirectoryPicker
from runtime.tasks import TaskService
from security.worktrees import SubprocessGitRunner


def test_probe_process_receives_eof_without_reading_parent_stdin(tmp_path):
    async def scenario():
        result = await ProcessRunner().run(
            [sys.executable, '-B', '-c', 'import sys; print(repr(sys.stdin.buffer.read()))'],
            cwd=tmp_path, timeout=2,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "b''"

    asyncio.run(scenario())


def test_interactive_process_receives_its_own_input_pipe(tmp_path):
    async def scenario():
        process = await ProcessRunner().start(
            [sys.executable, '-B', '-c', 'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())'],
            cwd=tmp_path,
        )
        output, _ = await asyncio.wait_for(process.communicate(b'owned input'), 2)
        assert process.returncode == 0
        assert output == b'owned input'

    asyncio.run(scenario())


@pytest.mark.parametrize('cancel', [False, True])
def test_probe_timeout_or_cancellation_cleans_up_process(monkeypatch, cancel):
    entered = asyncio.Event()

    async def communicate():
        entered.set()
        await asyncio.Event().wait()

    child = SimpleNamespace(communicate=communicate)
    launch = AsyncMock(return_value=child)
    cleanup = AsyncMock(return_value=True)
    monkeypatch.setattr('adapters.process.asyncio.create_subprocess_exec', launch)
    monkeypatch.setattr('adapters.process.terminate_process_tree', cleanup)

    async def scenario():
        pending = asyncio.create_task(ProcessRunner().run(['fake-probe'], timeout=.01))
        await entered.wait()
        if cancel:
            pending.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
            await pending

    asyncio.run(scenario())
    assert launch.call_args.kwargs['stdin'] == subprocess.DEVNULL
    cleanup.assert_awaited_once_with(child)


@pytest.mark.skipif(os.name != 'nt', reason='Windows process tree helper')
def test_taskkill_timeout_has_bounded_cleanup_and_private_stdin(monkeypatch):
    class Target(asyncio.subprocess.Process):
        def __init__(self):
            self.pid = 12345

        @property
        def returncode(self):
            return None

    class Killer:
        killed = False

        async def wait(self):
            await asyncio.Event().wait()

        def kill(self):
            self.killed = True

    killer = Killer()
    launch = AsyncMock(return_value=killer)
    monkeypatch.setattr('adapters.process.asyncio.create_subprocess_exec', launch)

    async def scenario():
        assert await asyncio.wait_for(terminate_process_tree(Target(), timeout=.01), .5) is False

    asyncio.run(scenario())
    assert killer.killed
    assert launch.call_args.args[0] == 'taskkill.exe'
    assert launch.call_args.kwargs['stdin'] == subprocess.DEVNULL


def test_directory_picker_timeout_does_not_wait_forever_after_kill(monkeypatch):
    class Child:
        returncode = None
        killed = False

        async def communicate(self):
            await asyncio.Event().wait()

        async def wait(self):
            await asyncio.Event().wait()

        def kill(self):
            self.killed = True

    child = Child()
    monkeypatch.setattr('runtime.directory_picker.asyncio.create_subprocess_exec', AsyncMock(return_value=child))
    native_wait_for = asyncio.wait_for
    budgets = []

    async def fast_wait_for(awaitable, timeout):
        budgets.append(timeout)
        return await native_wait_for(awaitable, min(timeout, .01))

    monkeypatch.setattr('runtime.directory_picker.asyncio.wait_for', fast_wait_for)
    with pytest.raises(TimeoutError):
        asyncio.run(LocalDirectoryPicker(timeout=.01)._launch(''))
    assert child.killed
    assert budgets == [.01, 3]


def test_git_worktree_commands_are_noninteractive_and_bounded(tmp_path, monkeypatch):
    def run(args, **kwargs):
        assert kwargs['stdin'] == subprocess.DEVNULL
        assert kwargs['timeout'] == 30
        raise subprocess.TimeoutExpired(args, kwargs['timeout'])

    monkeypatch.setattr('security.worktrees.subprocess.run', run)
    with pytest.raises(subprocess.TimeoutExpired):
        SubprocessGitRunner().run(['status'], cwd=tmp_path)


def test_evidence_timeout_becomes_a_feature_error(tmp_path, monkeypatch):
    def run(args, **kwargs):
        assert kwargs['stdin'] == subprocess.DEVNULL
        assert kwargs['timeout'] == 15
        raise subprocess.TimeoutExpired(args, kwargs['timeout'])

    monkeypatch.setattr(review_evidence.subprocess, 'run', run)
    with pytest.raises(HubError) as caught:
        review_evidence._git(tmp_path, 'status')
    assert caught.value.code == 'FEATURE_UNAVAILABLE'


@pytest.mark.skipif(os.name != 'nt', reason='Windows runtime descriptor ACL helpers')
def test_descriptor_helpers_are_noninteractive_and_bounded(tmp_path, monkeypatch):
    commands = []

    def run(args, **kwargs):
        assert kwargs['stdin'] == subprocess.DEVNULL
        assert kwargs['timeout'] == 5
        commands.append(args[0])
        return SimpleNamespace(stdout='"user","S-1-5-21-123"')

    path = tmp_path / 'descriptor'
    path.write_text('private', encoding='utf-8')
    monkeypatch.setattr(descriptor.subprocess, 'run', run)
    descriptor.secure_current_user_only(path)
    assert commands == ['whoami', 'icacls']


@pytest.mark.parametrize('failure', [TimeoutError(), FileNotFoundError()])
def test_task_git_baseline_failure_is_bounded_and_reported(tmp_path, monkeypatch, failure):
    probe = AsyncMock(side_effect=failure)
    monkeypatch.setattr(ProcessRunner, 'run', probe)
    with pytest.raises(HubError) as caught:
        asyncio.run(TaskService._head_commit(tmp_path))
    assert caught.value.code == 'PATH_NOT_ALLOWED'
    assert probe.call_args.kwargs['timeout'] == 5


def test_task_git_baseline_retains_success(tmp_path, monkeypatch):
    probe = AsyncMock(return_value=SimpleNamespace(returncode=0, stdout='abc123\n'))
    monkeypatch.setattr(ProcessRunner, 'run', probe)
    assert asyncio.run(TaskService._head_commit(tmp_path)) == 'abc123'
