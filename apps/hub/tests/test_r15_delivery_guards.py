from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from protocol.generated.python import SendLocalMessageInput
from core.errors import HubError
from runtime.remote.deadline import DeliveryClock
from remote_support import System, FakeRemoteServer, command_events, until, later
from test_remote_controls import pending_approval
from test_r15_worker import local_conversation, command, receive, grant


@pytest.mark.parametrize("discontinuity", ["wall-back", "wall-forward", "sleep", "restart"])
def test_delivery_clock_fails_closed_on_unprovable_time(discontinuity):
    mono, wall = [100.0], [1000.0]
    clock = DeliveryClock(monotonic=lambda: mono[0], wall=lambda: wall[0])
    stamp = lambda seconds: datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace("+00:00", "Z")
    clock.calibrate(stamp(1000), 98)
    frame = {"createdAt": stamp(1000), "deliverBy": stamp(1030), "expiresAt": stamp(1030)}
    assert clock.upper() == 1002  # Handshake RTT counts against the deadline.
    clock.check(frame)
    if discontinuity == "wall-back":
        wall[0] -= 10
    elif discontinuity == "wall-forward":
        wall[0] += 10
    elif discontinuity == "sleep":
        mono[0] += 60
        wall[0] += 60
    else:
        clock.invalidate()
    with pytest.raises(HubError) as error:
        clock.check(frame)
    assert error.value.code == "REMOTE_DELIVERY_EXPIRED"


def test_metadata_changes_between_received_and_grant_reject_without_partial_commit(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            conversation = await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                update = command(system, "stale", conversation.id, kind="conversation.update", payload={
                    "conversationId": conversation.id, "expectedVersion": 1, "title": "phone title"})
                receipt = await receive(server, update)
                changed = await system.local.patch("/api/v2/conversations/" + conversation.id,
                    json={"expectedVersion": 1, "title": "PC title"}, headers={"Idempotency-Key": "pc-title"})
                assert changed.status_code == 200
                await server.send(grant(update, receipt))
                await until(lambda: command_events(server, "stale", "command.rejected"))
                assert command_events(server, "stale", "command.rejected")[-1]["error"]["code"] == "CONFLICT"
                assert system.chat.repository.conversation(conversation.id).title == "PC title"
                assert system.chat.repository.conversation(conversation.id).version == 2
                assert not command_events(server, "stale", "command.accepted")
                # A bad target consumes its transport slot, with an immutable
                # rejection; the following valid submit executes on this socket.
                bad = command(system, "bad-target", conversation.id)
                bad["payload"]["workspaceId"] = "another-workspace"
                await server.send(bad)
                await until(lambda: command_events(server, "bad-target", "command.rejected"))
                rejection = command_events(server, "bad-target", "command.rejected")[-1]
                await until(lambda: system.repo.get("identity")["ack"] >= rejection["seq"])
                await server.send(bad)
                await until(lambda: len(command_events(server, "bad-target", "command.rejected")) == 2)
                assert command_events(server, "bad-target", "command.rejected")[-1] == rejection
                valid = command(system, "good", conversation.id, seq=2)
                accepted = await receive(server, valid)
                await server.send(grant(valid, accepted))
                await until(lambda: command_events(server, "good", "command.completed"))
                assert server.connections == 1 and not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("action", ["git_push", "deploy", "delete", "db_migrate", "shell", "network"])
def test_rev2_approval_rechecks_policy_after_receipt_and_reject_always_works(tmp_path, action):
    async def scenario():
        system = System(tmp_path, hold=True)
        try:
            conversation = await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                run = system.chat.send(conversation.id, SendLocalMessageInput(
                    clientMessageId="pc", text="approval run", sessionMode="new"), "pc")
                await until(lambda: system.chat.repository.run_record(run.run_id)["task_id"] is not None)
                approval = await pending_approval(system, {"run_id": run.run_id}, action=action)
                approve = command(system, "approve", conversation.id, kind="approval.decide", payload={
                    "runId": run.run_id, "approvalId": approval.id, "decision": "approve"})
                if action == "network":
                    receipt = await receive(server, approve)
                    assert system.adapter.approvals == []
                    with system.db.transaction() as tx:
                        system.repo.put("policy", {"revision": 2, "blockedActions": ["network"]}, tx)
                        system.repo.seal(tx)
                    await server.send(grant(approve, receipt))
                else:
                    await server.send(approve)
                await until(lambda: command_events(server, "approve", "command.rejected"))
                assert command_events(server, "approve", "command.rejected")[-1]["error"]["code"] == "REMOTE_APPROVAL_FORBIDDEN"
                assert system.adapter.approvals == []
                reject = command(system, "reject", conversation.id, kind="approval.decide", payload={
                    "runId": run.run_id, "approvalId": approval.id, "decision": "reject"})
                receipt = await receive(server, reject)
                assert system.adapter.approvals == []
                permission = grant(reject, receipt)
                await server.send(permission)
                await until(lambda: command_events(server, "reject", "command.completed"))
                await server.send(permission)
                await asyncio.sleep(0.1)
                assert len(system.adapter.approvals) == 1 and str(system.adapter.approvals[0].decision) == "reject"
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_busy_snapshot_chunks_are_one_immutable_complete_set(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            ids = set()
            for index in range(101):
                conversation = await local_conversation(system, "queued-" + str(index))
                system.chat.send(conversation.id, SendLocalMessageInput(
                    clientMessageId=str(index), text="queued", sessionMode="new"), str(index))
                ids.add(conversation.id)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server)
                server.workers.append(system.worker)
                await system.worker.start()  # Keep native supervisor stopped.
                await until(lambda: server.busy_ids == ids)
                parts = [f for f in server.frames if f["type"] == "sync.busy.snapshot"]
                assert len(parts) == 2 and parts[0]["snapshotId"] == parts[1]["snapshotId"]
                assert all(p["partCount"] == 2 and len(p["conversationIds"]) <= 100 for p in parts)
                assert {p["partIndex"] for p in parts} == {0, 1}
                assert not system.adapter.started and not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_grant_rechecks_real_approval_expiry_before_accepting(tmp_path):
    async def scenario():
        system = System(tmp_path, hold=True)
        try:
            conversation = await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                run = system.chat.send(conversation.id, SendLocalMessageInput(
                    clientMessageId="approval", text="approval", sessionMode="new"), "approval")
                await until(lambda: system.chat.repository.run_record(run.run_id)["task_id"] is not None)
                approval = await pending_approval(system, {"run_id": run.run_id}, action="network")
                decision = command(system, "expired-approval", conversation.id, kind="approval.decide", payload={
                    "runId": run.run_id, "approvalId": approval.id, "decision": "reject"})
                receipt = await receive(server, decision)
                await system.ports.approvals.repository.save(approval.model_copy(update={"expires_at": later(-1)}))
                await server.send(grant(decision, receipt))
                await until(lambda: command_events(server, "expired-approval", "command.rejected"))
                assert command_events(server, "expired-approval", "command.rejected")[-1]["error"]["code"] == "APPROVAL_EXPIRED"
                assert not command_events(server, "expired-approval", "command.accepted")
                assert not system.adapter.approvals and not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_initial_continue_starts_new_session_without_prior_execution(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            conversation = await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                frame = command(system, "no-prior-context", conversation.id)
                frame["payload"]["sessionMode"] = "continue"
                receipt = await receive(server, frame)
                await server.send(grant(frame, receipt))
                await until(lambda: command_events(server, "no-prior-context", "command.completed"))
                assert command_events(server, "no-prior-context", "command.completed")[-1]['resultStatus'] == 'succeeded'
                assert len(system.adapter.started) == 1 and not system.adapter.resumed and not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())
