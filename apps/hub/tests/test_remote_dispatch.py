from __future__ import annotations

import asyncio
import pytest

from remote_support import FakeRemoteServer, System, command_events, until, wait_budget


def test_wait_budget_defaults_to_one_and_scales_only_synchronization(monkeypatch):
    monkeypatch.delenv('HQAGENT_TEST_TIMEOUT_SCALE', raising=False)
    assert wait_budget(8) == 8
    monkeypatch.setenv('HQAGENT_TEST_TIMEOUT_SCALE', '3')
    assert wait_budget(8) == 24
    assert wait_budget(2) == 6
    budgets, intervals = [], []
    original = asyncio.timeout
    def observed_timeout(seconds):
        budgets.append(seconds)
        return original(seconds)
    async def sleep(seconds):
        intervals.append(seconds)
    monkeypatch.setattr(asyncio, 'timeout', observed_timeout)
    monkeypatch.setattr(asyncio, 'sleep', sleep)
    async def scenario():
        samples = iter((False, True))
        await until(lambda: next(samples))
        await until(lambda: True, timeout=12)
        await until(lambda: True, timeout=2, scale_timeout=False)
    asyncio.run(scenario())
    assert budgets == [24, 36, 2]
    assert intervals == [0.01]


@pytest.mark.parametrize('value', ['0', '-1', 'nan', 'inf', 'bad', ''])
def test_invalid_wait_scale_never_disables_timeout(monkeypatch, value):
    monkeypatch.setenv('HQAGENT_TEST_TIMEOUT_SCALE', value)
    with pytest.raises(ValueError):
        wait_budget(8)


def test_slow_cancel_does_not_block_admission_or_another_run_and_same_run_is_serial(tmp_path):
    async def scenario():
        system = System(tmp_path, hold=True)
        release = asyncio.Event()
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                await server.send(system.command("run-a", conversation="conversation-a"))
                await server.send(system.command("run-b", conversation="conversation-b"))
                await until(lambda: len(system.adapter.started) == 2)
                a, b = system.repo.inbox("run-a"), system.repo.inbox("run-b")
                task_a = system.chat.repository.run_record(a["run_id"])["task_id"]
                session_a = system.tasks.repository.list_nodes(task_a)[0].session_id
                entered = asyncio.Event()
                original_cancel = system.adapter.cancel
                async def slow_cancel(request):
                    if request.session_id == session_a:
                        entered.set()
                        await release.wait()
                    return await original_cancel(request)
                system.adapter.cancel = slow_cancel
                await server.send(system.command("cancel-a", conversation="conversation-a", kind="run.cancel", payload={"runId": a["run_id"]}))
                await asyncio.wait_for(entered.wait(), wait_budget(2))
                await server.send(system.command("resume-a", conversation="conversation-a", kind="run.resume", payload={"runId": a["run_id"]}))
                await server.send(system.command("cancel-b", conversation="conversation-b", kind="run.cancel", payload={"runId": b["run_id"]}))
                await server.send(system.command("run-c", conversation="conversation-c"))
                # These three ceilings assert nonblocking admission/control,
                # not merely readiness; slow CI must not relax this behavior.
                await until(lambda: command_events(server, "run-c", "command.accepted"), timeout=2, scale_timeout=False)
                await until(lambda: command_events(server, "resume-a", "command.accepted"), timeout=2, scale_timeout=False)
                await until(lambda: command_events(server, "cancel-b", "command.completed"), timeout=2, scale_timeout=False)
                assert not release.is_set()
                assert system.repo.inbox("cancel-a")["status"] == "executing"
                assert system.repo.inbox("resume-a")["status"] == "admitted"
                assert system.repo.inbox("run-c")["status"] == "accepted"
                # Keep the native cancellation blocked for real wall-clock seconds.
                await asyncio.sleep(2)
                assert not command_events(server, "cancel-a", "command.completed")
                assert not command_events(server, "resume-a", "command.control_result")
                release.set()
                await until(lambda: command_events(server, "cancel-a", "command.completed"))
                await until(lambda: command_events(server, "resume-a", "command.failed"))
                assert command_events(server, "resume-a", "command.failed")[-1]["controlResult"]["evidence"] == "worker_policy"
                assert len(system.adapter.cancels) == 2
                assert server.connections == 1 and not server.errors
        finally:
            release.set()
            await system.close()
    asyncio.run(scenario())


def test_duplicate_admission_and_recover_do_not_launch_a_second_live_control(tmp_path):
    async def scenario():
        system = System(tmp_path, hold=True)
        release, entered = asyncio.Event(), asyncio.Event()
        calls = []
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                await server.send(system.command("run"))
                await until(lambda: len(system.adapter.started) == 1)
                row = system.repo.inbox("run")
                original = system.adapter.cancel
                async def slow(request):
                    calls.append(request.session_id)
                    entered.set()
                    await release.wait()
                    return await original(request)
                system.adapter.cancel = slow
                command = system.command("cancel", kind="run.cancel", payload={"runId": row["run_id"]})
                await server.send(command)
                await asyncio.wait_for(entered.wait(), wait_budget(2))
                await until(lambda: command_events(server, "cancel", "command.accepted"))
                count = len(command_events(server, "cancel", "command.accepted"))
                await server.send(command)
                await until(lambda: len(command_events(server, "cancel", "command.accepted")) > count)
                await system.bridge.recover()
                assert len(calls) == 1
                assert len(system.bridge._executions) == 1
                assert system.repo.inbox("cancel")["status"] == "executing"
                release.set()
                await until(lambda: command_events(server, "cancel", "command.completed"))
                await until(lambda: not system.bridge._executions)
                assert system.bridge._run_locks == {} and system.bridge._run_pending == {}
                assert len(calls) == 1 and not server.errors
        finally:
            release.set()
            await system.close()
    asyncio.run(scenario())


def test_reconnect_reports_inflight_control_unknown_and_does_not_resume_its_effects(tmp_path):
    async def scenario():
        system = System(tmp_path, hold=True)
        entered = asyncio.Event()
        calls = []
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                await server.send(system.command("run"))
                await until(lambda: len(system.adapter.started) == 1)
                row = system.repo.inbox("run")
                async def unknown_cancel(request):
                    calls.append(request.session_id)
                    entered.set()
                    await asyncio.Event().wait()
                system.adapter.cancel = unknown_cancel
                await server.send(system.command("cancel", kind="run.cancel", payload={"runId": row["run_id"]}))
                await asyncio.wait_for(entered.wait(), wait_budget(2))
                await server.send(system.command("resume", kind="run.resume", payload={"runId": row["run_id"]}))
                await until(lambda: command_events(server, "resume", "command.accepted"))
                assert system.repo.inbox("resume")["status"] == "admitted"
                await server.ws.close(code=1012)
                await until(lambda: command_events(server, "cancel", "command.control_result"))
                await until(lambda: command_events(server, "resume", "command.control_result"))
                for name in ("cancel", "resume"):
                    result = command_events(server, name, "command.control_result")[-1]["controlResult"]
                    assert result["outcome"] == "unconfirmed"
                    assert result["evidence"] == "delivery_unknown"
                    assert result["executionMayStillBeRunning"] is True
                    assert not command_events(server, name, "command.completed")
                assert len(calls) == 1 and server.connections == 2 and not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_ws_queue_backpressure_does_not_disconnect_when_more_than_200_commands_arrive(tmp_path, monkeypatch):
    async def scenario():
        system = System(tmp_path)
        release, entered = asyncio.Event(), asyncio.Event()
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                original = system.bridge.receive
                async def blocked_admission(frame):
                    entered.set()
                    await release.wait()
                    return await original(frame)
                monkeypatch.setattr(system.bridge, "receive", blocked_admission)
                for index in range(205):
                    command = system.command(f"bad-{index}", conversation="burst", seq=index + 1)
                    command["targetWorkerId"] = "wrong-worker"
                    await server.send(command)
                    if index == 0:
                        await asyncio.wait_for(entered.wait(), wait_budget(2))
                await server.send(system.command("after-burst", conversation="independent"))
                await asyncio.sleep(0.1)
                assert server.connections == 1
                assert system.repo.get("link")["view"]["connectionStatus"] == "online"
                release.set()
                await until(lambda: command_events(server, "after-burst", "command.completed"), timeout=20)
                assert system.db.connection.execute("SELECT COUNT(*) FROM remote_inbox WHERE status='rejected'").fetchone()[0] == 205
                assert [s.objective for s in system.adapter.started] == ["after-burst"]
                assert server.connections == 1 and not server.errors
        finally:
            release.set()
            await system.close()
    asyncio.run(scenario())
