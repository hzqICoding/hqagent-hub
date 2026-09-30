from __future__ import annotations

import asyncio

import pytest
from protocol.generated.python import SendLocalMessageInput, TaskActionInput
from runtime.remote.worker import NoRedirectConnect
from storage.local_chat import now
from remote_support import System, FakeRemoteServer, command_events, until
from test_r15_worker import local_conversation, command, receive, grant


async def crash(system):
    # Drop in-memory drivers/handles without graceful TaskService.shutdown or
    # cancel actions, exactly retaining the active durable state after a crash.
    await system.worker.stop()
    await system.chat.stop()
    pumps = tuple(system.tasks._pumps.values())
    for pump in pumps:
        pump.cancel()
    await asyncio.gather(*pumps, return_exceptions=True)
    await system.local.aclose()
    system.db.close()


async def restart(system, server):
    await system.tasks.recover_pending()
    system.worker.connector = lambda uri, **kwargs: NoRedirectConnect(uri, ssl=server.client_tls, **kwargs)
    server.workers.append(system.worker)
    await system.chat.start()
    await system.worker.start()
    await until(lambda: system.repo.get("link")["view"].get("connectionStatus") == "online")


@pytest.mark.parametrize("granted", [True, False])
def test_crash_recovery_replaces_busy_and_never_executes_unconfirmed_reservation(tmp_path, granted):
    async def scenario():
        system = System(tmp_path, hold=True)
        try:
            conversation = await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                frame = command(system, "interrupted", conversation.id)
                received = await receive(server, frame)
                if granted:
                    await server.send(grant(frame, received))
                    await until(lambda: len(system.adapter.started) == 1)
                await until(lambda: server.busy_ids == {conversation.id})
                old_epoch = system.repo.get("identity")["epoch"]
                run_id = system.worker.delivery.row("interrupted")["run_id"]
                server.workers.remove(system.worker)
                await crash(system)
                system = System(tmp_path)
                assert system.chat.repository.run_record(run_id)["status"] in {"queued", "running"}
                await restart(system, server)
                await until(lambda: server.busy_ids == set())
                assert system.repo.get("identity")["epoch"] != old_epoch
                assert system.worker.busy.ids() == []
                record = system.chat.repository.run_record(run_id)
                if granted:
                    assert record["status"] == "paused"
                    assert system.worker.busy.observe(record)["recoveryRequired"] is True
                    await until(lambda: any(f["type"] == "sync.run.state" and f["payload"]["runId"] == run_id
                        and f["payload"].get("recoveryRequired") for f in server.frames))
                    continuation = system.chat.send(conversation.id, SendLocalMessageInput(
                        clientMessageId="unsafe-continue", text="continue interrupted", sessionMode="continue"), "unsafe-continue")
                    await until(lambda: system.chat.repository.run_record(continuation.run_id)["status"] == "failed")
                    assert not system.adapter.started and not system.adapter.resumed
                else:
                    assert record["status"] == "cancelled"
                    await server.send(grant(frame, received))
                    await until(lambda: command_events(server, "interrupted", "command.rejected"))
                assert not system.adapter.started
                # A recovery warning is not a lock, and does not strand newer
                # explicitly-new local work behind the old paused row.
                local = system.chat.send(conversation.id, SendLocalMessageInput(
                    clientMessageId="after-crash", text="new explicit context", sessionMode="new"), "after-crash")
                await until(lambda: system.chat.repository.run_record(local.run_id)["status"] == "succeeded")
                assert len(system.adapter.started) == 1
                if granted:
                    # Only an explicit local recovery action may restart the
                    # interrupted Task. Its original LocalRun must be observed
                    # by the supervisor again, so the final reply is not lost.
                    await system.chat.control(run_id, TaskActionInput(action="resume"), "explicit-local-recovery")
                    await until(lambda: system.chat.repository.run_record(run_id)["status"] == "succeeded")
                    assert len(system.adapter.started) == 2
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_reconnect_busy_is_complete_replacement_and_cancel_during_disconnect_clears_it(tmp_path):
    async def scenario():
        system = System(tmp_path, hold=True)
        try:
            conversation = await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                sent = system.chat.send(conversation.id, SendLocalMessageInput(
                    clientMessageId="running", text="running", sessionMode="new"), "running")
                await until(lambda: server.busy_ids == {conversation.id})
                await until(lambda: bool(system.adapter.started))
                await system.worker.stop()
                await system.chat.control(sent.run_id, TaskActionInput(action="cancel"), "offline-local-cancel")
                await system.worker.start()
                await until(lambda: server.connections >= 2 and server.busy_ids == set())
                fresh = [f for f in server.frames if f["type"] == "sync.busy.snapshot" and f["connectionId"] == server.connection_id]
                assert fresh and fresh[-1]["conversationIds"] == [] and fresh[-1]["partCount"] == 1
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_rev1_only_server_falls_back_reports_no_sync_and_executes_original_protocol(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer(revision=1) as server:
                await system.pair(server, start=True)
                assert server.requested_revisions[:2] == [4, 1]
                assert server.hellos[-1]["wireRevision"] == 1
                assert system.repo.get("link")["view"]["lastErrorCode"] == "REMOTE_REVISION_REQUIRED"
                assert system.repo.get("identity").get("wireRevision", 1) == 1
                await server.send(system.command("legacy"))
                await until(lambda: command_events(server, "legacy", "command.completed"))
                assert len(system.adapter.started) == 1
                assert all(f["wireRevision"] == 1 for f in server.frames)
                assert not any(f["type"].startswith("sync.") for f in server.frames)
                settings = await system.local.put("/api/v1/remote/sync-settings", json={
                    "mirrorEnabled": False, "expectedVersion": 1}, headers={"Idempotency-Key": "legacy-sync"})
                assert settings.status_code == 409 and settings.json()["error"]["code"] == "REMOTE_REVISION_REQUIRED"
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_revision_upgrade_fence_drains_original_events_and_never_downgrades_rev2(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer(revision=1, auto_ack=False) as server:
                await system.pair(server, start=True)
                await server.send(system.command("old"))
                await until(lambda: command_events(server, "old", "command.completed"))
                assert system.worker.can_upgrade() is False
                original = dict(server.event_bytes)
                await system.worker.stop()
                server.auto_ack = True
                await system.worker.start()
                await until(lambda: system.worker.can_upgrade())
                for key, value in original.items():
                    assert server.event_bytes[key] == value  # Original epoch/hash retained.
                await system.worker.stop()
                server.revision = 2
                await system.worker.start()
                await until(lambda: system.repo.get("identity").get("wireRevision") == 2)
                assert system.repo.get("identity")["upgradeFence"]["server"] is not None
                await system.worker.stop()
                server.revision = 1
                await system.worker.start()
                await until(lambda: system.repo.get("link")["view"]["state"] == "frozen")
                assert system.repo.get("identity")["wireRevision"] == 2
                assert system.repo.get("link")["view"]["lastErrorCode"] == "REMOTE_PROTOCOL_UNSUPPORTED"
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_rev2_gap_skip_and_late_replay_cannot_resurrect_skipped_command(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            conversation = await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                second = command(system, "second", conversation.id, seq=2)
                await server.send(second)
                await until(lambda: any(f["type"] == "conversation.gap" for f in server.frames))
                assert not system.adapter.started and not command_events(server, "second", "command.received")
                skip = {"type": "conversation.skip", "wireRevision": 2, "commandId": "skipped",
                    "conversationId": second["conversationId"], "conversationSeq": 1,
                    "targetWorkerId": second["targetWorkerId"], "expectedWorkerStoreId": second["expectedWorkerStoreId"],
                    "reason": "expired_before_dispatch", "recordedAt": now()}
                await server.send(skip)
                await until(lambda: command_events(server, "second", "command.received"))
                receipt = command_events(server, "second", "command.received")[-1]
                await server.send(grant(second, receipt))
                await until(lambda: command_events(server, "second", "command.completed"))
                await server.send(command(system, "skipped", conversation.id))
                await until(lambda: command_events(server, "skipped", "command.rejected"))
                assert command_events(server, "skipped", "command.rejected")[-1]["error"]["code"] == "REMOTE_COMMAND_WITHDRAWN"
                assert [s.objective for s in system.adapter.started] == ["second"]
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_server_upgrade_fence_can_clear_without_restarting_worker(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            system.worker.revision_probe_seconds = 0.5
            async with FakeRemoteServer(revision=2) as server:
                server.upgrade_pending = True
                await system.pair(server, start=True)
                assert server.requested_revisions[:3] == [4, 2, 1]
                assert system.repo.get("identity").get("wireRevision", 1) == 1
                assert system.repo.get("link")["view"]["lastErrorCode"] == "REMOTE_STATE_NOT_READY"
                epoch = system.repo.get("identity")["epoch"]
                server.upgrade_pending = False
                await until(lambda: system.repo.get("identity").get("wireRevision") == 2)
                await until(lambda: any(f["type"] == "sync.busy.snapshot" for f in server.frames))
                assert system.repo.get("identity")["epoch"] == epoch
                assert server.hellos[-1]["wireRevision"] == 2 and not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())
