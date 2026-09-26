from __future__ import annotations

import asyncio
import json

import pytest
from protocol.generated.python import RemoteLinkPairingInput, SaveLocalSceneInput
from core.errors import HubError
from runtime.remote.wire import decode, encode
from storage.local_chat import now
from remote_support import System, FakeRemoteServer, command_events, later, until


def test_offline_database_rollback_rotates_store_and_quarantines_old_queue(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server)
                command = system.command("offline-command")
                await system.bridge.receive(command)
                old_store = system.repo.get("identity")["store"]
                backup = system.db.backup(tmp_path / "old.db")
                # Execute without a Worker socket or the publisher loop. Task
                # persistence must advance the independent witness before start.
                await system.chat.start()
                await until(lambda: len(system.adapter.started) == 1)
                await until(lambda: system.chat.repository.run_record(system.repo.inbox("offline-command")["run_id"])["status"] == "succeeded")
                await system.chat.stop()
                system.db.restore_from_backup(backup)
                assert system.repo.check_continuity() is False
                assert system.repo.get("identity")["store"] != old_store
                assert system.repo.get("identity")["ack"] is None
                assert system.repo.get("link")["view"]["state"] == "frozen"
                assert system.chat.repository.run_record(system.repo.inbox("offline-command")["run_id"])["status"] == "paused"
                await system.chat.start()
                await asyncio.sleep(0.05)
                assert len(system.adapter.started) == 1
                with pytest.raises(HubError):
                    await system.bridge.receive(command)
                assert len(system.adapter.started) == 1
        finally:
            await system.close()
    asyncio.run(scenario())


def test_unlink_repair_does_not_transfer_old_conversation_or_outbox(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer() as old:
                await system.pair(old)
                original = system.command("old")
                await system.bridge.receive(original)
                old_store = system.repo.get("identity")["store"]
                await system.link.clear("unlink-old", unlink=True)
                old.secret = None
                old.claimed = False
                await system.link.pair(RemoteLinkPairingInput(serverOrigin=old.origin, deviceName="new"), "new-pair")
                old.claimed = True
                await system.link.poll()
                assert system.repo.get("identity")["store"] != old_store
                assert system.repo.get("identity")["ack"] is None
                assert system.repo.frames() == []
                # This fake reuses workerId; store identity still prevents transfer.
                with pytest.raises(HubError) as mismatch:
                    await system.bridge.receive(system.command("new", seq=2))
                assert mismatch.value.code == "REMOTE_TARGET_MISMATCH"
                same_id_new_binding = {**original, "expectedWorkerStoreId": system.repo.get("identity")["store"]}
                with pytest.raises(HubError) as replay:
                    await system.bridge.receive(same_id_new_binding)
                assert replay.value.code == "REMOTE_TARGET_MISMATCH"
                assert system.chat.repository.conversation(original["conversationId"]).authority == "remote"
        finally:
            await system.close()
    asyncio.run(scenario())


def test_withdraw_admitted_queued_run_confirms_actual_local_cancellation(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server)
                await system.bridge.receive(system.command("queued"))
                row = system.repo.inbox("queued")
                withdrawal = system.command("withdraw", kind="command.withdraw", payload={"targetCommandId": "queued", "targetConversationSeq": 1})
                await system.bridge.receive(withdrawal)
                assert system.chat.repository.run_record(row["run_id"])["status"] == "cancelled"
                events = [json.loads(f) for f in system.repo.frames()]
                result = next(e for e in events if e["type"] == "command.completed" and e.get("commandId") == "withdraw")
                assert result["resultStatus"] == "confirmed"
                assert result["controlResult"]["executionMayStillBeRunning"] is False
                assert result["resultRef"]["runId"] == row["run_id"]
                await system.chat.start()
                await asyncio.sleep(0.05)
                assert not system.adapter.started
        finally:
            await system.close()
    asyncio.run(scenario())


def test_ws_expired_submit_consumes_slot_and_does_not_cancel_accepted_work(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                expired = system.command("expired")
                expired["expiresAt"] = later(-1)
                await server.send(system.command("next", seq=2))
                await server.send(expired)
                await until(lambda: command_events(server, "next", "command.completed"))
                assert [s.objective for s in system.adapter.started] == ["next"]
                assert command_events(server, "expired", "command.rejected")[-1]["error"]["code"] == "REMOTE_COMMAND_EXPIRED"
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_ws_expected_store_mismatch_fences_execution(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                command = system.command("wrong-store")
                command["expectedWorkerStoreId"] = "previous-store"
                await server.send(command)
                await until(lambda: system.repo.get("link")["view"]["state"] == "frozen")
                assert system.repo.get("link")["view"]["lastErrorCode"] == "REMOTE_STORE_CHANGED"
                assert not system.adapter.started
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_ws_unknown_control_delivery_recovers_as_unconfirmed_without_reissue(tmp_path):
    async def scenario():
        system = System(tmp_path, hold=True)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                await server.send(system.command("run"))
                await until(lambda: len(system.adapter.started) == 1)
                row = system.repo.inbox("run")
                entered, release = asyncio.Event(), asyncio.Event()
                async def lost_reply(request):
                    system.adapter.cancels.append(request)
                    entered.set()
                    await release.wait()
                    return system.adapter.cancel_results[request.mode]
                system.adapter.cancel = lost_reply
                command = system.command("cancel-in-flight", kind="run.cancel", payload={"runId": row["run_id"]})
                await server.send(command)
                await entered.wait()
                await server.ws.close(code=1012)
                await until(lambda: command_events(server, "cancel-in-flight", "command.control_result"))
                event = command_events(server, "cancel-in-flight", "command.control_result")[-1]
                assert event["controlResult"]["outcome"] == "unconfirmed"
                assert event["controlResult"]["evidence"] == "delivery_unknown"
                await server.send(command)
                await asyncio.sleep(0.05)
                assert len(system.adapter.cancels) == 1
                assert not command_events(server, "cancel-in-flight", "command.completed")
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_scene_version_is_never_silently_replaced_and_catalog_is_bounded(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server)
                await system.worker.projector.catalog()
                first_revision = system.worker.projector.capability_revision()
                await system.worker.projector.catalog()
                assert system.worker.projector.capability_revision() == first_revision
                scene = system.chat.repository.scene("analyze")
                system.chat.repository.save_scene("analyze", SaveLocalSceneInput(roles=scene.roles, expectedVersion=1))
                await system.worker.projector.catalog()
                assert system.worker.projector.capability_revision() == first_revision + 1
                receipt, _ = await system.bridge.receive(system.command("old-scene"))
                assert receipt["type"] == "command.rejected" and receipt["error"]["code"] == "REMOTE_SCENE_VERSION_MISMATCH"
                assert not system.adapter.started
                system.ports.workspaces.items *= 1001
                existing_catalog_count = sum(json.loads(f)["type"] == "capability.changed" for f in system.repo.frames())
                with pytest.raises(HubError) as error:
                    await system.worker.projector.catalog()
                assert error.value.code == "REMOTE_FRAME_TOO_LARGE"
                assert sum(json.loads(f)["type"] == "capability.changed" for f in system.repo.frames()) == existing_catalog_count
        finally:
            await system.close()
    asyncio.run(scenario())


def test_wire_rejects_oversize_duplicate_keys_and_wrong_revision_without_echo():
    with pytest.raises(HubError) as oversized:
        decode(" " * (256 * 1024 + 1))
    assert oversized.value.code == "REMOTE_FRAME_TOO_LARGE"
    with pytest.raises(HubError):
        decode('{"type":"server.heartbeat","wireRevision":1,"wireRevision":2}')
    with pytest.raises(HubError) as rejected:
        decode('{"type":"worker.hello_rejected","wireRevision":2,"supportedWireRevisions":[2],"error":{"message":"private credential"}}')
    assert rejected.value.code == "REMOTE_PROTOCOL_UNSUPPORTED"
    assert "private credential" not in str(rejected.value)
