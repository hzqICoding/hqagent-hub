from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from protocol.generated.python import CancelMode, CancelResult, SendLocalMessageInput, TaskActionInput

from remote_support import System, FakeRemoteServer, command_events, until
from runtime.remote.commands import control_result
from storage.local_chat import now
from test_r15_worker import local_conversation, command, receive, grant


async def running(system, conversation, key, mode="new"):
    receipt = system.chat.send(conversation, SendLocalMessageInput(
        clientMessageId=key, text=key, sessionMode=mode), key)
    await until(lambda: system.chat.repository.run_record(receipt.run_id)["task_id"] is not None)
    record = system.chat.repository.run_record(receipt.run_id)
    node = system.tasks.repository.list_nodes(record["task_id"])[0]
    session = await system.tasks.runtime.sessions.repository.get(node.session_id)
    return receipt.run_id, record["task_id"], session


async def next_finished(system, conversation, key, mode):
    system.adapter.release.set()
    receipt = system.chat.send(conversation, SendLocalMessageInput(
        clientMessageId=key, text=key, sessionMode=mode), key)
    await until(lambda: system.chat.repository.run_record(receipt.run_id)["status"] in {"succeeded", "failed"})
    return system.chat.repository.run_record(receipt.run_id)


@pytest.mark.parametrize("stop", ["stopped_gracefully", "force_killed"])
@pytest.mark.parametrize("next_mode", ["continue", "new"])
def test_confirmed_cancel_keeps_native_session_resumable_without_affecting_new(tmp_path, stop, next_mode):
    async def scenario():
        system = System(tmp_path, hold=True)
        try:
            conv = await local_conversation(system)
            await system.chat.start()
            run, task, original = await running(system, conv.id, "first")
            system.adapter.cancel_results[CancelMode.GRACEFUL] = CancelResult(
                outcome=stop, completedAt=now(), orphanProcessIds=[])
            before = system.tasks.control_observation(task)
            await system.chat.control(run, TaskActionInput(action="cancel"), "cancel-first")
            after = system.tasks.control_observation(task)
            result = control_result(before, after)
            assert result["outcome"] == "confirmed" and result["evidence"] == "adapter_confirmed"
            assert not result["executionMayStillBeRunning"] and not result["orphanProcessIds"]
            cancelled = await system.tasks.runtime.sessions.repository.get(original.id)
            assert str(cancelled.status) == "idle" and cancelled.is_valid
            assert cancelled.external_session_id == original.external_session_id
            assert cancelled.turn_count == original.turn_count == 1
            next_run = await next_finished(system, conv.id, "second", next_mode)
            assert next_run["status"] == "succeeded", next_run["error"]
            next_session_id = system.tasks.repository.list_nodes(next_run["task_id"])[0].session_id
            if next_mode == "continue":
                assert next_session_id == original.id and len(system.adapter.started) == 1
                assert len(system.adapter.resumed) == 1
                request = system.adapter.resumed[0]
                assert request.session_id == original.id
                assert request.external_session_id == original.external_session_id
                assert (await system.tasks.runtime.sessions.repository.get(original.id)).turn_count == 2
            else:
                assert next_session_id != original.id and len(system.adapter.started) == 2
                assert not system.adapter.resumed
                assert (await system.tasks.runtime.sessions.repository.get(next_session_id)).turn_count == 1
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("unsafe", ["orphans", "unresolved", "recovery", "missing-state", "unsupported", "no-external", "lost-external"])
def test_cancel_without_safe_resume_evidence_closes_session_and_continue_is_structurally_rejected(tmp_path, unsafe):
    async def scenario():
        system = System(tmp_path, hold=True)
        try:
            if unsafe in {"unsupported", "no-external"}:
                system.adapter.handle = system.adapter.handle.model_copy(update={
                    "supports_resume": False, **({"external_session_id": None} if unsafe == "no-external" else {})})
            conv = await local_conversation(system)
            await system.chat.start()
            run, task, original = await running(system, conv.id, "first")
            if unsafe == "orphans":
                system.adapter.cancel_results[CancelMode.GRACEFUL] = CancelResult(
                    outcome="force_killed", completedAt=now(), orphanProcessIds=[123])
            if unsafe in {"unresolved", "recovery"}:
                state = system.tasks.state.get("task_spec:" + task)
                state["unresolvedCancellation" if unsafe == "unresolved" else "recoveryRequired"] = (
                    {"kind": "cancellation", "cancellations": [{"outcome": "not_found", "orphanProcessIds": []}]}
                    if unsafe == "unresolved" else True)
                system.tasks.state.put("task_spec:" + task, state)
            repository = system.tasks.runtime.sessions.repository
            if unsafe == "lost-external":
                await repository.save(original.model_copy(update={"external_session_id": None}))
            saved_state = repository.execution_state
            if unsafe == "missing-state":
                repository.execution_state = SimpleNamespace(get=lambda _key: None)
            try:
                await system.chat.control(run, TaskActionInput(action="cancel"), "cancel-first")
            finally:
                repository.execution_state = saved_state
            assert str((await repository.get(original.id)).status) == "closed"
            if unsafe in {"orphans", "unresolved", "recovery"}:
                assert control_result({}, system.tasks.control_observation(task))["outcome"] == "unconfirmed"
            next_run = await next_finished(system, conv.id, "unsafe-continue", "continue")
            assert next_run["status"] == "failed"
            assert system.chat.repository.failure_code(next_run["run_id"]) == "SESSION_NOT_RESUMABLE"
            assert len(system.adapter.started) == 1 and not system.adapter.resumed
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("outcome,session_state,task_state", [
    ("already_finished", "idle", "running"),
    ("not_found", "invalid", "failed"),
    ("refused", "active", "failed"),
])
def test_other_cancel_outcomes_keep_their_original_semantics(tmp_path, outcome, session_state, task_state):
    async def scenario():
        system = System(tmp_path, hold=True)
        try:
            conv = await local_conversation(system)
            await system.chat.start()
            run, task, session = await running(system, conv.id, "first")
            system.adapter.cancel_results[CancelMode.GRACEFUL] = CancelResult(outcome=outcome, completedAt=now())
            await system.chat.control(run, TaskActionInput(action="cancel"), "cancel-first")
            assert str((await system.tasks.runtime.sessions.repository.get(session.id)).status) == session_state
            assert str(system.tasks.repository.get(task).status) == task_state
        finally:
            await system.close()
    asyncio.run(scenario())


def test_second_turn_cancel_checks_current_task_evidence_not_session_creation_task(tmp_path):
    async def scenario():
        system = System(tmp_path, hold=True)
        try:
            conv = await local_conversation(system)
            await system.chat.start()
            first, first_task, session = await running(system, conv.id, "first")
            await system.chat.control(first, TaskActionInput(action="cancel"), "cancel-first")
            second, second_task, reused = await running(system, conv.id, "second", "continue")
            assert reused.id == session.id and reused.turn_count == 2
            state = system.tasks.state.get("task_spec:" + second_task)
            state["unresolvedCancellation"] = {"kind": "cancellation", "cancellations": [{"outcome": "not_found", "orphanProcessIds": []}]}
            system.tasks.state.put("task_spec:" + second_task, state)
            assert not system.tasks.control_observation(first_task).get("unresolvedCancellation")
            await system.chat.control(second, TaskActionInput(action="cancel"), "cancel-second")
            assert str((await system.tasks.runtime.sessions.repository.get(session.id)).status) == "closed"
            third = await next_finished(system, conv.id, "third", "continue")
            assert system.chat.repository.failure_code(third["run_id"]) == "SESSION_NOT_RESUMABLE"
            assert len(system.adapter.resumed) == 1
        finally:
            await system.close()
    asyncio.run(scenario())


def test_revision_two_phone_cancel_then_continue_reuses_native_session(tmp_path):
    async def scenario():
        system = System(tmp_path, hold=True)
        try:
            conv = await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                first = command(system, "phone-first", conv.id)
                receipt = await receive(server, first)
                await server.send(grant(first, receipt))
                await until(lambda: system.worker.delivery.row("phone-first")["run_id"] is not None)
                run_id = system.worker.delivery.row("phone-first")["run_id"]
                await until(lambda: system.chat.repository.run_record(run_id)["task_id"] is not None)
                task_id = system.chat.repository.run_record(run_id)["task_id"]
                session_id = system.tasks.repository.list_nodes(task_id)[0].session_id
                original = await system.tasks.runtime.sessions.repository.get(session_id)
                cancel = command(system, "phone-cancel", conv.id, kind="run.cancel", payload={"runId": run_id})
                cancel_receipt = await receive(server, cancel)
                await server.send(grant(cancel, cancel_receipt))
                await until(lambda: command_events(server, "phone-cancel", "command.completed"))
                result = command_events(server, "phone-cancel", "command.completed")[-1]["controlResult"]
                assert result["outcome"] == "confirmed" and result["evidence"] == "adapter_confirmed"
                system.adapter.release.set()
                next_command = command(system, "phone-continue", conv.id, seq=2)
                next_command["payload"]["sessionMode"] = "continue"
                next_receipt = await receive(server, next_command)
                await server.send(grant(next_command, next_receipt))
                await until(lambda: command_events(server, "phone-continue", "command.completed") or
                            command_events(server, "phone-continue", "command.failed"))
                assert command_events(server, "phone-continue", "command.completed")
                assert len(system.adapter.started) == 1 and len(system.adapter.resumed) == 1
                request = system.adapter.resumed[0]
                assert request.session_id == session_id and request.external_session_id == original.external_session_id
                assert (await system.tasks.runtime.sessions.repository.get(session_id)).turn_count == 2
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())
