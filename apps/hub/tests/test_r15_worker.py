from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from protocol.generated.python import (RemoteV2ServerOutboundFrame,
    LocalConversationView, SendLocalMessageInput, TaskActionInput)
from core.errors import HubError
from storage.local_chat import now
from remote_support import System, FakeRemoteServer, command_events, until, dump


async def local_conversation(system, name="desktop"):
    response = await system.local.post("/api/v2/conversations", json={"title": name,
        "workspaceId": "workspace", "sceneId": "analyze"}, headers={"Idempotency-Key": "create-" + name})
    assert response.status_code == 201, response.text
    return LocalConversationView.model_validate(response.json()["data"])


def command(system, identifier, local_id, *, public="public-route", kind="run.submit", seq=1,
            seconds=20, payload=None):
    stamp = now()
    deadline = (datetime.fromisoformat(stamp.replace("Z", "+00:00")) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")
    frame = {"type": kind, "wireRevision": 2, "commandId": identifier, "conversationId": public,
        "localConversationId": local_id, "targetWorkerId": "worker-test",
        "expectedWorkerStoreId": system.repo.get("identity")["store"], "createdAt": stamp,
        "expiresAt": deadline, "deliverBy": deadline, "payload": payload or {"clientMessageId": identifier,
            "text": identifier, "workspaceId": "workspace", "sceneId": "analyze", "sceneVersion": 1, "sessionMode": "new"}}
    if kind == "run.submit":
        frame["conversationSeq"] = seq
    return dump(RemoteV2ServerOutboundFrame.model_validate(frame))


def grant(frame, receipt, **overrides):
    value = {"type": "command.delivery_granted", "wireRevision": 2,
        **{k: frame[k] for k in ("commandId", "conversationId", "targetWorkerId", "expectedWorkerStoreId", "deliverBy")},
        "commandDigest": receipt["commandDigest"], "receivedEventId": receipt["eventId"], "grantedAt": now()}
    value.update(overrides)
    return dump(RemoteV2ServerOutboundFrame.model_validate(value))


async def receive(server, frame):
    await server.send(frame)
    await until(lambda: command_events(server, frame["commandId"], "command.received"))
    return command_events(server, frame["commandId"], "command.received")[-1]


def test_rev2_grant_not_ack_authorizes_once_and_reuses_desktop_session(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            conversation = await local_conversation(system)
            await system.chat.start()
            local = system.chat.send(conversation.id, SendLocalMessageInput(clientMessageId="pc-first", text="remember-context", sessionMode="new"), "pc-first")
            await until(lambda: system.chat.repository.run_record(local.run_id)["status"] == "succeeded")
            original_session = system.tasks.repository.list_nodes(system.chat.repository.run_record(local.run_id)["task_id"])[0].session_id
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                assert server.hellos[-1]["wireRevision"] == 2
                frame = command(system, "mobile-continue", conversation.id)
                frame["payload"]["sessionMode"] = "continue"
                receipt = await receive(server, frame)
                await until(lambda: (system.repo.get("identity")["ack"] or 0) >= receipt["seq"])
                assert len(system.adapter.started) == 1 and system.adapter.resumed == []
                await server.send(frame)
                await asyncio.sleep(0.1)
                assert system.adapter.resumed == []
                permission = grant(frame, receipt)
                await server.send(permission)
                await until(lambda: command_events(server, frame["commandId"], "command.completed"))
                assert len(system.adapter.started) == 1 and len(system.adapter.resumed) == 1
                assert system.adapter.resumed[0].session_id == original_session
                await server.send(permission)
                await server.send(frame)
                await asyncio.sleep(0.1)
                assert len(system.adapter.resumed) == 1
                assert len(system.chat.repository.conversations(include_hidden=True)) == 1
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_phone_create_and_metadata_cas_then_computer_continues(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                create = command(system, "create-phone", "local-phone", kind="conversation.create", payload={
                    "targetWorkerId": "worker-test", "workerStoreId": system.repo.get("identity")["store"],
                    "workspaceId": "workspace", "sceneId": "analyze", "sceneVersion": 1, "title": "Phone"})
                receipt = await receive(server, create)
                assert not system.chat.repository.conversations()
                await server.send(grant(create, receipt))
                await until(lambda: command_events(server, "create-phone", "command.completed"))
                result = command_events(server, "create-phone", "command.completed")[-1]
                assert result["controlResult"]["evidence"] == "metadata_committed" and "resultRef" not in result
                update = command(system, "update-phone", "local-phone", kind="conversation.update",
                    payload={"conversationId": "local-phone", "expectedVersion": 1, "visibility": "mobile_only"})
                received = await receive(server, update)
                await server.send(grant(update, received))
                await until(lambda: command_events(server, "update-phone", "command.completed"))
                assert system.chat.repository.conversations() == []
                assert system.chat.repository.conversations(include_hidden=True)[0].visibility == "mobile_only"
                response = await system.local.post("/api/v2/conversations/local-phone/messages",
                    json={"clientMessageId": "pc", "text": "pc can write", "sessionMode": "new"}, headers={"Idempotency-Key": "pc"})
                assert response.status_code == 202, response.text
                run_id = response.json()["data"]["runId"]
                await until(lambda: system.chat.repository.run_record(run_id)["status"] == "succeeded")
                assert system.chat.repository.conversation("local-phone").authority == "remote"
                assert len(system.adapter.started) == 1 and not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["expired", "bad-digest", "bad-receipt", "no-grant", "late-grant", "cancelled"])
def test_delivery_failures_release_reservation_and_never_execute(tmp_path, failure):
    async def scenario():
        system = System(tmp_path)
        try:
            conversation = await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                frame = command(system, "held", conversation.id, seconds=2 if failure in {"no-grant", "late-grant"} else 20)
                if failure == "expired":
                    for field in ("createdAt", "deliverBy", "expiresAt"):
                        frame[field] = (datetime.fromisoformat(frame[field].replace("Z", "+00:00")) - timedelta(seconds=21)).isoformat().replace("+00:00", "Z")
                await server.send(frame)
                if failure != "expired":
                    await until(lambda: command_events(server, "held", "command.received"))
                    receipt = command_events(server, "held", "command.received")[-1]
                    row = system.worker.delivery.row("held")
                    assert row["state"] == "provisional" and conversation.id in system.worker.busy.ids()
                    if failure == "bad-digest":
                        await server.send(grant(frame, receipt, commandDigest="0" * 64))
                    elif failure == "bad-receipt":
                        await server.send(grant(frame, receipt, receivedEventId="unknown-receipt"))
                    elif failure == "cancelled":
                        await system.chat.control(row["run_id"], TaskActionInput(action="cancel"), "local-cancel")
                        await server.send(grant(frame, receipt))
                    elif failure == "late-grant":
                        permission = grant(frame, receipt)
                        await asyncio.sleep(2.1)
                        await server.send(permission)
                await until(lambda: command_events(server, "held", "command.rejected"))
                assert system.worker.busy.ids() == [] and not system.adapter.started
                assert not command_events(server, "held", "command.accepted")
                # The rejected slot must not strand sequence 2.
                next_frame = command(system, "next", conversation.id, seq=2)
                next_receipt = await receive(server, next_frame)
                await server.send(grant(next_frame, next_receipt))
                await until(lambda: command_events(server, "next", "command.completed"))
                assert [s.objective for s in system.adapter.started] == ["next"]
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_busy_first_arrival_wins_both_directions_and_cancel_is_never_gated(tmp_path):
    async def scenario():
        system = System(tmp_path, hold=True)
        try:
            conversation = await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                frame = command(system, "first", conversation.id)
                receipt = await receive(server, frame)
                with pytest.raises(HubError) as busy:
                    system.chat.send(conversation.id, SendLocalMessageInput(clientMessageId="loser", text="retained input", sessionMode="new"), "loser")
                assert busy.value.code == "REMOTE_CONVERSATION_BUSY"
                await server.send(grant(frame, receipt))
                await until(lambda: len(system.adapter.started) == 1)
                run_id = system.worker.delivery.row("first")["run_id"]
                cancel = command(system, "cancel", conversation.id, kind="run.cancel", payload={"runId": run_id})
                cancel_receipt = await receive(server, cancel)
                assert conversation.id in system.worker.busy.ids()
                await server.send(grant(cancel, cancel_receipt))
                await until(lambda: command_events(server, "cancel", "command.completed"))
                await until(lambda: system.worker.busy.ids() == [])
                local = system.chat.send(conversation.id, SendLocalMessageInput(clientMessageId="pc-wins", text="pc-wins", sessionMode="new"), "pc-wins")
                loser = command(system, "phone-loses", conversation.id, seq=2)
                await server.send(loser)
                await until(lambda: command_events(server, "phone-loses", "command.rejected"))
                assert command_events(server, "phone-loses", "command.rejected")[-1]["error"]["code"] == "REMOTE_CONVERSATION_BUSY"
                assert system.chat.repository.run_record(local.run_id)["status"] in {"queued", "running"}
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_slow_granted_cancel_does_not_hold_admission_lock(tmp_path):
    async def scenario():
        system = System(tmp_path, hold=True)
        entered, release = asyncio.Event(), asyncio.Event()
        try:
            first = await local_conversation(system, "first")
            second = await local_conversation(system, "second")
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                running = system.chat.send(first.id, SendLocalMessageInput(clientMessageId="pc", text="pc", sessionMode="new"), "pc")
                await until(lambda: system.chat.repository.run_record(running.run_id)["task_id"] is not None)
                original_cancel = system.adapter.cancel
                async def slow_cancel(*args, **kwargs):
                    entered.set()
                    await release.wait()
                    return await original_cancel(*args, **kwargs)
                system.adapter.cancel = slow_cancel
                cancel = command(system, "slow-cancel", first.id, kind="run.cancel", payload={"runId": running.run_id})
                received = await receive(server, cancel)
                await server.send(grant(cancel, received))
                await asyncio.wait_for(entered.wait(), 3)
                independent = command(system, "independent", second.id, public="second-route")
                async with asyncio.timeout(2):
                    receipt = await receive(server, independent)
                    await server.send(grant(independent, receipt))
                    await until(lambda: command_events(server, "independent", "command.accepted"))
                assert not release.is_set() and not command_events(server, "slow-cancel", "command.completed")
                release.set()
                await until(lambda: command_events(server, "slow-cancel", "command.completed"))
                assert server.connections == 1 and not server.errors
        finally:
            release.set()
            await system.close()
    asyncio.run(scenario())
