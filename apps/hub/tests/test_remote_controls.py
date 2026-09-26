from __future__ import annotations

import asyncio
import json

import pytest
from protocol.generated.python import (CancelMode, CancelResult, DangerousAction,
    NodeStatus, RiskLevel, TaskStatus)
from core.errors import HubError
from security.approvals import ApprovalRequest
from storage.events import EventDraft
from storage.local_chat import now
from remote_support import System, FakeRemoteServer, command_events, later, until


@pytest.mark.parametrize("mode,outcome,evidence", [
    ("stopped_gracefully", "confirmed", "adapter_confirmed"),
    ("refused", "rejected", "adapter_refused"),
    ("missing", "unconfirmed", "recovery_flag"),
    ("orphans", "unconfirmed", "recovery_flag"),
    ("already_finished", "confirmed", "adapter_confirmed"),
    ("not_found", "unconfirmed", "missing_execution_handle"),
])
def test_ws_cancel_uses_real_task_runtime_structured_evidence(tmp_path, mode, outcome, evidence):
    async def scenario():
        system = System(tmp_path, hold=True)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                await server.send(system.command("running"))
                await until(lambda: len(system.adapter.started) == 1)
                row = system.repo.inbox("running")
                await until(lambda: system.chat.repository.run_record(row["run_id"])["task_id"] is not None)
                task_id = system.chat.repository.run_record(row["run_id"])["task_id"]
                if mode == "missing":
                    system.tasks._outcomes.clear()
                else:
                    system.adapter.cancel_results[CancelMode.GRACEFUL] = CancelResult(
                        outcome="force_killed" if mode == "orphans" else mode,
                        completedAt=now(), orphanProcessIds=[321] if mode == "orphans" else [])
                await server.send(system.command("cancel", kind="run.cancel", payload={"runId": row["run_id"]}))
                await until(lambda: command_events(server, "cancel", "command.control_result"))
                event = command_events(server, "cancel", "command.control_result")[-1]
                result = event["controlResult"]
                assert result["outcome"] == outcome and result["evidence"] == evidence
                assert result["executionMayStillBeRunning"] is (outcome != "confirmed")
                assert result["orphanProcessIds"] == ([321] if mode == "orphans" else [])
                assert event["resultRef"] == {"runId": row["run_id"], "executionTaskId": task_id}
                if outcome == "confirmed":
                    await until(lambda: command_events(server, "cancel", "command.completed"))
                elif outcome == "rejected":
                    await until(lambda: command_events(server, "cancel", "command.failed"))
                    assert (await system.tasks.get_task(task_id)).status == TaskStatus.FAILED
                else:
                    assert not command_events(server, "cancel", "command.completed")
                    assert not command_events(server, "cancel", "command.failed")
                if mode == "missing":
                    assert system.tasks.control_observation(task_id)["recoveryRequired"] is True
                    for action in ("resume", "retry"):
                        await server.send(system.command(action, kind="run." + action, payload={"runId": row["run_id"]}))
                        await until(lambda: command_events(server, action, "command.control_result"))
                        assert command_events(server, action, "command.control_result")[-1]["controlResult"]["outcome"] == "unconfirmed"
                        assert not command_events(server, action, "command.completed")
                    assert len(system.adapter.started) == 1
                    assert system.tasks.control_observation(task_id)["recoveryRequired"] is True
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


async def pending_approval(system, row, *, action="git_push", identifier="approval-live"):
    record = system.chat.repository.run_record(row["run_id"])
    task_id = record["task_id"]
    node = system.tasks.repository.list_nodes(task_id)[0]
    approval = await system.coordinator.request(ApprovalRequest(task_id=task_id, task_objective="test",
        node_id=node.id, request_agent_id="agent", request_agent_name="agent", role_id="analyst",
        action=DangerousAction(action), target_resource="registered target", risk_level=RiskLevel.LOW,
        approval_id=identifier, external_request_id="native-" + identifier))
    system.tasks.repository.save_node(node.model_copy(update={"status": NodeStatus.WAITING_APPROVAL}))
    task = system.tasks.repository.get(task_id)
    system.tasks.repository.save(task.model_copy(update={"status": TaskStatus.WAITING_APPROVAL,
        "pending_approval_id": approval.id}))
    return approval


@pytest.mark.parametrize("action", ["git_push", "deploy", "delete", "db_migrate", "shell"])
def test_ws_high_risk_approval_rejected_but_rejection_consumed_once(tmp_path, action):
    async def scenario():
        system = System(tmp_path, hold=True)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                await server.send(system.command("run"))
                await until(lambda: len(system.adapter.started) == 1)
                row = system.repo.inbox("run")
                approval = await pending_approval(system, row, action=action)
                approve = system.command("approve", kind="approval.decide", payload={
                    "runId": row["run_id"], "approvalId": approval.id, "decision": "approve"})
                await server.send(approve)
                await until(lambda: command_events(server, "approve", "command.failed"))
                assert command_events(server, "approve", "command.failed")[-1]["error"]["code"] == "REMOTE_APPROVAL_FORBIDDEN"
                assert system.adapter.approvals == []
                reject = system.command("reject", kind="approval.decide", payload={
                    "runId": row["run_id"], "approvalId": approval.id, "decision": "reject"})
                await server.send(reject)
                await until(lambda: command_events(server, "reject", "command.completed"))
                assert command_events(server, "reject", "command.completed")[-1]["resultStatus"] == "approval_consumed"
                await server.send(reject)
                await asyncio.sleep(0.05)
                assert len(system.adapter.approvals) == 1
                assert str(system.adapter.approvals[0].decision) == "reject"
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_ws_approval_uses_current_policy_and_unknown_consumption_is_not_completed(tmp_path):
    async def scenario():
        system = System(tmp_path, hold=True)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                await server.send(system.command("run"))
                await until(lambda: len(system.adapter.started) == 1)
                row = system.repo.inbox("run")
                approval = await pending_approval(system, row, action="network")
                await until(lambda: any(f["type"] == "approval.state_changed" and f["payload"]["remoteApprovalAllowed"] for f in server.frames))
                with system.db.transaction() as tx:
                    system.repo.put("policy", {"revision": 2, "blockedActions": ["network"]}, tx)
                    system.repo.seal(tx)
                await server.send(system.command("policy-changed", kind="approval.decide", payload={
                    "runId": row["run_id"], "approvalId": approval.id, "decision": "approve"}))
                await until(lambda: command_events(server, "policy-changed", "command.failed"))
                assert command_events(server, "policy-changed", "command.failed")[-1]["error"]["code"] == "REMOTE_APPROVAL_FORBIDDEN"
                assert system.adapter.approvals == []
                async def failure(dispatch):
                    system.adapter.approvals.append(dispatch)
                    raise RuntimeError("simulated lost native receipt")
                system.adapter.approve = failure
                reject = system.command("unknown", kind="approval.decide", payload={
                    "runId": row["run_id"], "approvalId": approval.id, "decision": "reject"})
                await server.send(reject)
                await until(lambda: command_events(server, "unknown", "command.control_result"))
                assert command_events(server, "unknown", "command.control_result")[-1]["controlResult"]["outcome"] == "unconfirmed"
                assert not command_events(server, "unknown", "command.completed")
                await server.send(reject)
                await asyncio.sleep(0.05)
                assert len(system.adapter.approvals) == 1
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_ws_pause_confirms_at_boundary_resume_and_retry_keep_kernel_identity(tmp_path):
    async def scenario():
        system = System(tmp_path, hold=True)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                await server.send(system.command("run"))
                await until(lambda: len(system.adapter.started) == 1)
                row = system.repo.inbox("run")
                await server.send(system.command("pause", kind="run.pause", payload={"runId": row["run_id"]}))
                await until(lambda: command_events(server, "pause", "command.accepted"))
                assert not command_events(server, "pause", "command.completed")
                system.adapter.release.set()
                await until(lambda: command_events(server, "pause", "command.completed"))
                pause = command_events(server, "pause", "command.completed")[-1]
                assert pause["controlResult"]["evidence"] == "node_boundary_paused"
                await server.send(system.command("resume", kind="run.resume", payload={"runId": row["run_id"]}))
                await until(lambda: command_events(server, "resume", "command.completed"))
                assert command_events(server, "resume", "command.completed")[-1]["controlResult"]["evidence"] == "supervisor_resumed"
                await until(lambda: command_events(server, "run", "command.completed"))
                parent_id = system.chat.repository.run_record(row["run_id"])["task_id"]
                await server.send(system.command("retry", kind="run.retry", payload={"runId": row["run_id"]}))
                await until(lambda: command_events(server, "retry", "command.completed"))
                retry = command_events(server, "retry", "command.completed")[-1]
                assert retry["resultStatus"] == "retry_enqueued"
                assert retry["resultRef"]["runId"] != row["run_id"]
                assert retry["resultRef"]["executionTaskId"] != parent_id
                assert retry["resultRef"]["parentExecutionTaskId"] == parent_id
                assert "retryOfRunId" not in json.dumps(server.frames)
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("case", ["regression", "ahead", "store", "middle"])
def test_ws_ack_conflict_freezes_and_preserves_outbox(tmp_path, case):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer(auto_ack=False) as server:
                await system.pair(server, start=True)
                await until(lambda: len(server.frames) >= 2)
                identity = system.repo.get("identity")
                if case == "regression":
                    position = {"workerStoreId": identity["store"], "seq": identity["covered"]}
                    system.repo.ack(position)
                    bad = {**position, "seq": 0}
                elif case == "ahead":
                    bad = {"workerStoreId": identity["store"], "seq": identity["high"] + 100}
                elif case == "store":
                    bad = {"workerStoreId": "old-store", "seq": 0}
                else:
                    with system.db.transaction() as tx:
                        for index in range(3):
                            system.events.append(tx, EventDraft(aggregate_type="system", aggregate_id="private", type="private.test", payload={"secretLocalText": index}))
                        system.repo.cover_private(tx)
                        system.repo.seal(tx)
                    omitted = [json.loads(f) for f in system.repo.frames() if json.loads(f)["type"] == "events.omitted"][-1]
                    bad = {"workerStoreId": identity["store"], "seq": omitted["firstSeq"]}
                before = system.db.connection.execute("SELECT COUNT(*) FROM remote_outbox").fetchone()[0]
                await server.send({"type": "worker.events_ack", "wireRevision": 1, "connectionId": server.connection_id,
                    "workerId": "worker-test", "position": bad})
                await until(lambda: system.repo.get("link")["view"]["state"] == "frozen")
                assert system.repo.get("link")["view"]["lastErrorCode"] == "REMOTE_ACK_CONFLICT"
                assert system.db.connection.execute("SELECT COUNT(*) FROM remote_outbox").fetchone()[0] >= before
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_private_events_omit_content_remote_events_do_not_and_heartbeat_is_real(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            with system.db.transaction() as tx:
                system.events.append(tx, EventDraft(aggregate_type="system", aggregate_id="private", type="private.test", payload={"text": "LOCAL_ONLY_MARKER"}))
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                await server.send(system.command("remote"))
                await until(lambda: command_events(server, "remote", "command.completed"))
                assert any(f["type"] == "events.omitted" for f in server.frames)
                assert "LOCAL_ONLY_MARKER" not in json.dumps(server.frames)
                assert "ABCD2345" not in json.dumps(server.frames)
                assert any(f["type"] == "run.state_changed" for f in server.frames)
                await until(lambda: any(f["type"] == "worker.heartbeat" for f in server.frames), timeout=18)
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_store_target_mismatch_and_server_freeze_never_execute(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer(frozen=True) as server:
                await system.pair(server, start=True)
                assert system.repo.get("link")["view"]["state"] == "frozen"
                assert system.repo.get("link")["view"]["connectionStatus"] == "online"
                await server.send(system.command("must-not-run"))
                await until(lambda: system.repo.get("link")["view"]["connectionStatus"] == "offline")
                assert system.adapter.started == []
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())
