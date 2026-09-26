from __future__ import annotations

import asyncio
import json

import pytest
from protocol.generated.python import CreateLocalConversationInput
from core.errors import HubError
from remote_support import FakeRemoteServer, System, command_events, until


@pytest.mark.parametrize("case,code", [
    ("worker", "REMOTE_TARGET_MISMATCH"),
    ("binding", "REMOTE_TARGET_MISMATCH"),
    ("authority", "CONVERSATION_AUTHORITY_MISMATCH"),
    ("slot", "REMOTE_EVENT_CONFLICT"),
    ("withdrawal", "REMOTE_TARGET_MISMATCH"),
    ("calendar", "VALIDATION_FAILED"),
])
def test_bad_command_replays_same_rejection_and_next_command_runs_on_same_ws(tmp_path, case, code):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                conversation, next_seq = "conversation-flow", 2
                if case in {"binding", "slot", "withdrawal"}:
                    await server.send(system.command("seed", conversation=conversation))
                    await until(lambda: command_events(server, "seed", "command.completed"))
                bad = system.command("bad", conversation=conversation)
                if case == "worker":
                    bad["targetWorkerId"] = "wrong-worker"
                elif case == "binding":
                    bad["conversationSeq"] = 2
                    bad["payload"]["workspaceId"] = "wrong-workspace"
                    next_seq = 3
                elif case == "authority":
                    local = system.chat.repository.create_conversation(CreateLocalConversationInput(
                        title="local", workspaceId="workspace", sceneId="analyze"), "local")
                    bad["conversationId"] = local.id
                    next_seq = 1
                elif case == "withdrawal":
                    bad = system.command("bad", conversation=conversation, kind="command.withdraw",
                        payload={"targetCommandId": "seed", "targetConversationSeq": 2})
                elif case == "calendar":
                    bad["createdAt"] = "2026-13-01T00:00:00Z"
                good = system.command("good", conversation=conversation, seq=next_seq)
                await server.send(bad)
                await server.send(good)
                await until(lambda: command_events(server, "bad", "command.rejected"))
                await until(lambda: command_events(server, "good", "command.completed"))
                first = command_events(server, "bad", "command.rejected")[0]
                assert first["error"]["code"] == code
                inbox = system.repo.inbox("bad")
                assert inbox["status"] == "rejected"
                assert json.loads(inbox["receipt_json"]) == first
                count = len(command_events(server, "bad", "command.rejected"))
                await server.send(bad)
                await until(lambda: len(command_events(server, "bad", "command.rejected")) > count)
                assert all(event == first for event in command_events(server, "bad", "command.rejected"))
                assert server.connections == 1 and not server.errors
                assert "bad" not in [s.objective for s in system.adapter.started]
                assert [s.objective for s in system.adapter.started][-1] == "good"
                if case == "authority":
                    assert system.chat.repository.conversation(local.id).authority == "local"
                    assert system.db.connection.execute("SELECT 1 FROM remote_conversations WHERE conversation_id=?", (local.id,)).fetchone() is None
                if case == "slot":
                    assert system.db.connection.execute("SELECT command_id FROM remote_slots WHERE conversation_id=? AND sequence=1", (conversation,)).fetchone()[0] == "seed"
                assert system.repo.get("link")["view"]["state"] == "paired"
        finally:
            await system.close()
    asyncio.run(scenario())


def test_failed_admission_rolls_back_before_rejection_commits_and_survives_ack(tmp_path, monkeypatch):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server)
                def fail_after_write(tx, frame):
                    tx.connection.execute("INSERT INTO remote_projections VALUES('must-rollback','partial')")
                    raise HubError("REMOTE_TARGET_MISMATCH", "injected command error")
                monkeypatch.setattr(system.bridge, "_bind_conversation", fail_after_write)
                trace = []
                system.db.connection.set_trace_callback(trace.append)
                bad = system.command("atomic-reject")
                receipt, _ = await system.bridge.receive(bad)
                system.db.connection.set_trace_callback(None)
                boundaries = [s for s in trace if s in {"BEGIN IMMEDIATE", "ROLLBACK", "COMMIT"}]
                assert boundaries == ["BEGIN IMMEDIATE", "ROLLBACK", "BEGIN IMMEDIATE", "COMMIT"]
                assert system.db.connection.execute("SELECT 1 FROM remote_projections WHERE key='must-rollback'").fetchone() is None
                assert system.repo.inbox("atomic-reject")["status"] == "rejected"
                assert not system.db.connection.execute("SELECT 1 FROM local_runs").fetchall()
                identity = system.repo.get("identity")
                system.repo.ack({"workerStoreId": identity["store"], "seq": identity["covered"]})
                system.repo.boot()
                replay, _ = await system.bridge.receive(bad)
                assert receipt == replay  # Same eventId, epoch, seq, time, error.
        finally:
            await system.close()
    asyncio.run(scenario())


def test_conflicting_id_has_stable_rejection_without_replacing_original_slot(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server)
                original = system.command("immutable")
                accepted, _ = await system.bridge.receive(original)
                conflict = {**original, "conversationSeq": 2, "payload": {**original["payload"], "text": "changed"}}
                rejection, _ = await system.bridge.receive(conflict)
                again, _ = await system.bridge.receive(conflict)
                assert rejection == again
                assert rejection["error"]["code"] == "IDEMPOTENCY_MISMATCH"
                assert json.loads(system.repo.inbox("immutable")["receipt_json"]) == accepted
                assert system.db.connection.execute("SELECT COUNT(*) FROM remote_slots").fetchone()[0] == 1
                good, _ = await system.bridge.receive(system.command("next", seq=2))
                assert good["type"] == "command.accepted"
        finally:
            await system.close()
    asyncio.run(scenario())
