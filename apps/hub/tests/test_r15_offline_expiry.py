from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager

import pytest
from protocol.generated.python import LocalConversationView, RemoteV2WorkerOutboundFrame
from runtime.remote.deadline import DeliveryClock, instant
from runtime.remote.worker import NoRedirectConnect
from storage.local_chat import now
from remote_support import System, FakeRemoteServer, command_events, until
from test_r15_worker import local_conversation, command, receive, grant
from test_r15_recovery import crash
from test_r15_sync import settings
from test_remote_cookie_routes import login, ORIGIN


class Unreachable:
    """Hold the connection attempt open: neither publish nor reconnect runs."""
    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    @asynccontextmanager
    async def __call__(self, *_args, **_kwargs):
        self.entered.set()
        await self.release.wait()
        raise ConnectionRefusedError("test server unavailable")
        yield  # Make this an async context manager; it never yields a socket.


async def disconnect_without_reconnecting(system):
    unavailable = Unreachable()
    system.worker.connector = unavailable
    await system.worker.disconnect()
    await asyncio.wait_for(unavailable.entered.wait(), 3)
    assert system.worker.socket is None
    return unavailable


async def conversation_view(system, identifier):
    response = await system.local.get("/api/v2/conversations")
    assert response.status_code == 200, response.text
    return next(LocalConversationView.model_validate(v) for v in response.json()["data"] if v["id"] == identifier)


def rejected(system, identifier):
    with system.db.locked_connection() as db:
        row = db.execute("SELECT state,result_json FROM remote2_delivery WHERE command_id=?", (identifier,)).fetchone()
    return json.loads(row[1]) if row and row[0] == "rejected" else None


def test_disconnected_reservation_expires_without_user_write_and_computer_stays_usable(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            conversation = await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                frame = command(system, "offline-held", conversation.id, seconds=2)
                await receive(server, frame)
                await login(system)
                assert (await conversation_view(system, conversation.id)).busy is True
                await disconnect_without_reconnecting(system)
                # No GET, archive or enqueue can trigger this durable release.
                await until(lambda: rejected(system, "offline-held"), timeout=5)
                assert time.time() <= instant(frame["deliverBy"]) + 5
                await asyncio.sleep(max(0, instant(frame["deliverBy"]) - time.time()))
                assert (await conversation_view(system, conversation.id)).busy is False
                archived = await system.local.patch("/api/v2/conversations/" + conversation.id,
                    json={"archived": True, "expectedVersion": 1},
                    headers={"Origin": ORIGIN, "Idempotency-Key": "archive-offline"})
                assert archived.status_code == 200, archived.text
                assert LocalConversationView.model_validate(archived.json()["data"]).archived
                restored = await system.local.patch("/api/v2/conversations/" + conversation.id,
                    json={"archived": False, "expectedVersion": 2},
                    headers={"Origin": ORIGIN, "Idempotency-Key": "restore-offline"})
                assert restored.status_code == 200, restored.text
                sent = await system.local.post(f"/api/v2/conversations/{conversation.id}/messages",
                    json={"clientMessageId": "pc-offline", "text": "computer still works", "sessionMode": "new"},
                    headers={"Origin": ORIGIN, "Idempotency-Key": "pc-offline"})
                assert sent.status_code == 202, sent.text
                await until(lambda: system.chat.repository.run_record(sent.json()["data"]["runId"])["status"] == "succeeded")
                assert [s.objective for s in system.adapter.started] == ["computer still works"]
                assert rejected(system, "offline-held")["error"]["code"] == "REMOTE_DELIVERY_EXPIRED"
                assert server.connections == 1 and not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("pending_state", ["waiting", "provisional"])
def test_startup_rejects_precrash_receipt_before_server_is_reachable_and_reports_it_later(tmp_path, pending_state):
    async def scenario():
        system = System(tmp_path)
        try:
            conversation = await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                frame = command(system, "precrash", conversation.id, seq=2 if pending_state == "waiting" else 1)
                received = None
                if pending_state == "provisional":
                    received = await receive(server, frame)
                else:
                    await server.send(frame)
                    await until(lambda: system.worker.delivery.row("precrash") is not None)
                async with system.worker.delivery.lock:
                    assert system.worker.delivery.row("precrash")["state"] == pending_state
                    server.workers.remove(system.worker)
                    await crash(system)
                system = System(tmp_path)
                unavailable = Unreachable()
                system.worker.connector = unavailable
                server.workers.append(system.worker)
                # Exercise the real Hub lifespan startup sequence, not the
                # connected test helper that used to hide this defect.
                async with system.application.app.router.lifespan_context(system.application.app):
                    result = rejected(system, "precrash")
                    assert result and result["error"]["code"] == "REMOTE_DELIVERY_EXPIRED"
                    RemoteV2WorkerOutboundFrame.model_validate(result)
                    assert (await conversation_view(system, conversation.id)).busy is False
                    assert not system.adapter.started
                    await asyncio.wait_for(unavailable.entered.wait(), 3)
                    assert server.connections == 1
                    system.worker.connector = lambda uri, **kw: NoRedirectConnect(uri, ssl=server.client_tls, **kw)
                    unavailable.release.set()
                    await until(lambda: command_events(server, "precrash", "command.rejected"))
                    assert command_events(server, "precrash", "command.rejected")[-1] == result
                    await server.send(grant(frame, received) if received else frame)
                    await asyncio.sleep(0.2)
                    assert not command_events(server, "precrash", "command.accepted")
                    assert not system.adapter.started and not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["deadline", "wall-back", "wall-forward", "sleep", "restart"])
def test_offline_busy_reads_are_write_free_and_expiry_does_not_wait_for_local_input(tmp_path, change):
    async def scenario():
        system = System(tmp_path)
        try:
            conversation = await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                await receive(server, command(system, "clock-held", conversation.id))
                # Hold only the admission/cleanup lock to inspect the read path
                # before the periodic writer has had a chance to reject it.
                async with system.worker.delivery.lock:
                    await disconnect_without_reconnecting(system)
                    mono, wall = [100.0], [1000.0]
                    clock = DeliveryClock(monotonic=lambda: mono[0], wall=lambda: wall[0])
                    clock.calibrate(now(), 100.0)
                    system.worker.delivery.clock = clock
                    assert (await conversation_view(system, conversation.id)).busy is True
                    if change == "wall-back":
                        wall[0] -= 10
                    elif change == "wall-forward":
                        wall[0] += 10
                    elif change in {"sleep", "deadline"}:
                        delta = 60 if change == "sleep" else 31
                        mono[0] += delta
                        wall[0] += delta
                    else:
                        clock.invalidate()
                    before = system.db.connection.total_changes
                    for _ in range(3):
                        assert (await conversation_view(system, conversation.id)).busy is False
                        assert system.worker.busy.ids() == []
                    assert system.db.connection.total_changes == before
                    assert system.worker.delivery.row("clock-held")["state"] == "provisional"
                    assert not system.worker.busy.observe(system.chat.repository.run_record(
                        system.worker.delivery.row("clock-held")["run_id"]))["reservationLive"]
                    # The archive transaction uses ids(tx), and must not need a
                    # send action or a GET write to get past the expired gate.
                    archive = await system.local.patch("/api/v2/conversations/" + conversation.id,
                        json={"archived": True, "expectedVersion": 1}, headers={"Idempotency-Key": "archive"})
                    assert archive.status_code == 200, archive.text
                    assert system.worker.delivery.row("clock-held")["state"] == "provisional"
                await until(lambda: rejected(system, "clock-held"), timeout=5)
                assert rejected(system, "clock-held")["error"]["code"] == "REMOTE_DELIVERY_EXPIRED"
                assert not system.adapter.started and server.connections == 1 and not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_offline_expiry_never_rejects_or_cancels_granted_running_execution(tmp_path):
    async def scenario():
        system = System(tmp_path, hold=True)
        try:
            conversation = await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                frame = command(system, "granted", conversation.id, seconds=2)
                received = await receive(server, frame)
                await server.send(grant(frame, received))
                await until(lambda: bool(system.adapter.started))
                await disconnect_without_reconnecting(system)
                await asyncio.sleep(2.1)  # Deadline and at least two cleanup cycles.
                row = system.worker.delivery.row("granted")
                assert row["state"] == "accepted" and row["grant_json"] is not None
                assert system.chat.repository.run_record(row["run_id"])["status"] == "running"
                assert (await conversation_view(system, conversation.id)).busy is True
                assert rejected(system, "granted") is None
                assert not system.adapter.cancels
                assert server.connections == 1 and not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["unlink", "revoke", "reset", "freeze"])
def test_expiry_task_is_reused_across_link_and_sync_state_changes_and_stops_cleanly(tmp_path, operation):
    async def scenario():
        system = System(tmp_path)
        try:
            conversation = await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                await receive(server, command(system, "lifecycle", conversation.id))
                cleanup = system.worker.expiry_job
                async with system.worker.delivery.lock:
                    await disconnect_without_reconnecting(system)
                    if operation == "unlink":
                        await system.link.clear("unlink", unlink=True)
                    elif operation == "revoke":
                        system.worker.state("offline", revoked=True, code="REMOTE_DEVICE_REVOKED")
                    elif operation == "reset":
                        settings(system, False, "off")
                    else:
                        system.worker.state("offline", frozen=True, code="REMOTE_PROTOCOL_UNSUPPORTED")
                await until(lambda: rejected(system, "lifecycle"), timeout=5)
                await asyncio.sleep(1.1)
                assert not cleanup.done() and system.worker.expiry_job is cleanup
                assert (await conversation_view(system, conversation.id)).busy is False
                assert not system.adapter.started
                await system.worker.stop()
                assert cleanup.done() and system.worker.expiry_job is None
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())
