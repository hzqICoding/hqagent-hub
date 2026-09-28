from __future__ import annotations

import asyncio
import json

from protocol.generated.python import RemoteSyncSettingsInput
from runtime.remote.sync import CONTENT_TYPES, WINDOW_BYTES
from runtime.remote.wire import canonical
from storage.local_chat import now
from remote_support import System, FakeRemoteServer, until, TOKEN
from test_r15_worker import local_conversation, command, receive, grant


def seed_messages(system, conversation, count, text):
    with system.db.transaction() as tx:
        for index in range(count):
            tx.connection.execute("INSERT INTO local_messages VALUES(?,?,?,?,?,?,?)",
                (f"history-{index}", conversation, index + 1, "assistant", text + str(index), None, now()))


def settings(system, enabled, key):
    return system.worker.sync.set_settings(RemoteSyncSettingsInput(
        mirrorEnabled=enabled, expectedVersion=system.worker.sync.settings().version), key)


def test_history_backfill_is_bounded_and_full_utf8_segments_preserve_text(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            conversation = await local_conversation(system)
            text = "Unicode token prose\r\n\x00" + "中文😀\\\"\n" * 8000
            seed_messages(system, conversation.id, 12, text)
            async with FakeRemoteServer(revision=2, auto_ack=False) as server:
                await system.pair(server, start=True)
                await until(lambda: any(f["type"] == "sync.message.segment" for f in server.frames))
                await asyncio.sleep(0.5)
                events = [f for f in server.frames if "eventId" in f]
                assert len(events) <= 16
                assert sum(len(canonical(f).encode()) for f in events) <= WINDOW_BYTES
                assert not any(f.get("complete") for f in server.frames)
                assert system.repo.get("sync-work")["phase"] == "backfilling"
                # ACK resumes the persisted batch cursor, without waiting for a
                # retransmission timer and without granting any command.
                store = system.repo.get("identity")["store"]
                contiguous = 0
                for (item_store, end), start in sorted(server.coverage.items()):
                    if item_store == store and start <= contiguous + 1:
                        contiguous = max(contiguous, end)
                server.acks[store] = contiguous
                server.auto_ack = True
                await server.send({"type": "worker.events_ack", "wireRevision": 2,
                    "connectionId": server.connection_id, "workerId": "worker-test",
                    "position": {"workerStoreId": store, "seq": contiguous}})
                await until(lambda: system.repo.get("sync-work")["phase"] == "synced", timeout=20)
                assert len(server.replica_messages) == 12
                for index in range(12):
                    assert server.replica_messages[(store, f"history-{index}")]["text"] == text + str(index)
                segments = [f for f in server.frames if f["type"] == "sync.message.segment"]
                assert all(len(f["payload"]["text"]) <= 16000 and len(f["payload"]["text"].encode()) <= 64000 for f in segments)
                assert all(len(canonical(f).encode()) <= 256 * 1024 for f in server.frames)
                progress = [f for f in server.frames if f["type"] == "sync.backfill.progress"]
                assert len(progress) > 2 and progress[-1]["complete"]
                previous = 0
                for batch in progress:
                    content = [f for f in server.frames if f["type"] in CONTENT_TYPES and previous < f["seq"] < batch["seq"]]
                    assert len(content) == batch["batchEventCount"] <= 100
                    assert sum(len(canonical(f).encode()) for f in content) <= WINDOW_BYTES
                    previous = batch["seq"]
                # A post-watermark change uploads a new complete revision.
                with system.db.transaction() as tx:
                    tx.connection.execute("UPDATE local_messages SET text=? WHERE message_id='history-0'", (text + "edited",))
                await until(lambda: server.replica_messages[(store, "history-0")]["revision"] == 2)
                assert server.replica_messages[(store, "history-0")]["text"] == text + "edited"
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_reset_retires_unacked_content_with_original_hash_proofs_and_reenable(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            conversation = await local_conversation(system)
            seed_messages(system, conversation.id, 20, "old body " * 2000)
            async with FakeRemoteServer(revision=2, auto_ack=False) as server:
                await system.pair(server, start=True)
                await until(lambda: any(f["type"] == "sync.message.segment" for f in server.frames))
                with system.db.locked_connection() as db:
                    originals = {r["seq"]: dict(r) for r in db.execute("SELECT * FROM remote_outbox")
                        if json.loads(r["frame_json"]).get("type") in CONTENT_TYPES}
                assert originals
                changed = settings(system, False, "off")
                server.auto_ack = True
                await until(lambda: system.repo.get("sync-work")["phase"] == "disabled")
                reset = next(f for f in server.frames if f["type"] == "sync.reset")
                assert reset["syncGeneration"] == changed.sync_generation == 2
                proofs = [f for f in server.frames if f["type"] == "sync.content.redaction"]
                assert proofs and all(len(f["slots"]) <= 100 for f in proofs)
                covered = {s["seq"]: s for p in proofs for s in p["slots"]}
                assert set(originals) <= set(covered)
                for seq, original in originals.items():
                    assert covered[seq]["eventSha256"] == original["digest"]
                    assert covered[seq]["eventId"] == original["event_id"]
                reset_index = server.frames.index(reset)
                await asyncio.sleep(0.4)
                assert not [f for f in server.frames[reset_index + 1:] if f["type"] in CONTENT_TYPES]
                assert not server.replica_messages
                with system.db.locked_connection() as db:
                    assert db.execute("SELECT COUNT(*) FROM remote_sync_items").fetchone()[0] == 0
                    assert db.execute("SELECT COUNT(*) FROM local_messages").fetchone()[0] == 20
                    for seq in originals:
                        row = db.execute("SELECT payload_json FROM events WHERE seq=? AND aggregate_id='remote-worker'", (seq,)).fetchone()
                        assert row is None or row[0] == "{}"
                restored = settings(system, True, "on")
                assert restored.sync_generation == 3
                await until(lambda: system.repo.get("sync-work")["phase"] == "synced", timeout=20)
                assert len(server.replica_messages) == 20
                assert all(f["syncGeneration"] == 3 for f in server.frames[reset_index + len(proofs) + 1:] if f["type"] in CONTENT_TYPES)
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_reset_releases_provisional_and_keeps_admitted_dedup_without_body(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            conversation = await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                frame = command(system, "private-body", conversation.id)
                frame["payload"]["text"] = "unique body erased from remote ledger"
                receipt = await receive(server, frame)
                settings(system, False, "off")
                assert not system.worker.busy.ids()
                with system.db.locked_connection() as db:
                    assert db.execute("SELECT command_json FROM remote2_delivery WHERE command_id='private-body'").fetchone()[0] is None
                    assert db.execute("SELECT command_json FROM remote_inbox WHERE command_id='private-body'").fetchone()[0] == "{}"
                await server.send(grant(frame, receipt))
                await asyncio.sleep(0.3)
                assert not system.adapter.started
                assert system.worker.delivery.row("private-body")["state"] == "rejected"
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_revocation_discards_replayable_copies_and_releases_reservations(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            conversation = await local_conversation(system)
            async with FakeRemoteServer(revision=2, auto_ack=False) as server:
                await system.pair(server, start=True)
                frame = command(system, "revoked-pending", conversation.id)
                await receive(server, frame)
                await server.ws.close(code=4403)
                await until(lambda: system.repo.get("link")["view"]["state"] == "revoked")
                assert system.repo.get("sync-work")["phase"] == "revoked"
                assert not system.worker.busy.ids()
                with system.db.locked_connection() as db:
                    assert db.execute("SELECT COUNT(*) FROM remote_sync_items").fetchone()[0] == 0
                    assert db.execute("SELECT command_json FROM remote_inbox WHERE command_id='revoked-pending'").fetchone()[0] == "{}"
                    assert not any(json.loads(r[0]).get("type") in CONTENT_TYPES for r in db.execute("SELECT frame_json FROM remote_outbox"))
                assert not system.adapter.started and not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_sync_never_exposes_device_authorization_or_hub_credentials(tmp_path, caplog):
    async def scenario():
        system = System(tmp_path)
        try:
            conversation = await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                secret = system.link.vault.read()
                body = "public prose about a token\n" + secret + "\n" + TOKEN + "\nAuthorization: Bearer hidden-value"
                seed_messages(system, conversation.id, 1, body)
                await until(lambda: bool(server.replica_messages))
                text = next(iter(server.replica_messages.values()))["text"]
                assert "public prose about a token" in text
                responses = [(await system.local.get("/api/v1/remote/" + path)).text for path in ("link", "sync-settings")]
                captured = json.dumps(server.frames) + "".join(responses) + caplog.text
                for private in (secret, TOKEN, "hidden-value", "Authorization: Bearer"):
                    assert private not in captured
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())
