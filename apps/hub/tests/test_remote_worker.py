from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3

import httpx
import pytest
from protocol.generated.python import (ApiEnvelope, CreateLocalConversationInput,
    LocalConversationView, RemoteLinkView, RemoteLinkPairingInput, RemoteWorkerOutboundFrame,
    SaveLocalSceneInput, SendLocalMessageInput)
from core.errors import HubError
from runtime.remote.commands import control_result
from runtime.remote.link import PairingHTTP
from runtime.remote.security import CredentialVault, normalize_origin
from runtime.tasks import TaskService
from storage.database import Database
from storage.events import EventDraft
from storage.local_chat import LocalChatRepository, now
from storage.migrations import LATEST_SCHEMA_VERSION
from remote_support import System, FakeRemoteServer, TOKEN, command_events, dump, later, until


def run(coroutine):
    return asyncio.run(coroutine)


def test_remote_migration_preserves_v5_data_and_defaults_authority(tmp_path):
    path = tmp_path / "migration.db"
    old = Database(path)
    old.initialize(target_version=5)
    repo = LocalChatRepository(old)
    conv = repo.create_conversation(CreateLocalConversationInput(title="legacy", workspaceId="workspace", sceneId="analyze"), "create")
    receipt = repo.enqueue(conv.id, SendLocalMessageInput(clientMessageId="old-message", text="preserved", sessionMode="new"), "old")
    with old.transaction() as tx:
        raw = json.loads(tx.connection.execute("SELECT payload_json FROM local_conversations WHERE conversation_id=?", (conv.id,)).fetchone()[0])
        raw.pop("authority", None)
        tx.connection.execute("UPDATE local_conversations SET payload_json=? WHERE conversation_id=?", (json.dumps(raw), conv.id))
    old.close()
    upgraded = Database(path)
    try:
        upgraded.initialize()
        assert upgraded.schema_version == LATEST_SCHEMA_VERSION and upgraded.schema_version >= 6
        repo = LocalChatRepository(upgraded)
        assert repo.conversation(conv.id).authority == "local"
        assert repo.conversation(conv.id).title == "legacy"
        assert repo.messages(conv.id)[0].text == "preserved"
        assert repo.run_record(receipt.run_id)["status"] == "queued"
        with upgraded.transaction() as tx:
            for table in ("remote_state", "remote_inbox", "remote_slots", "remote_conversations", "remote_outbox", "remote_operations", "remote_projections"):
                assert tx.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            tx.connection.execute("INSERT INTO remote_state VALUES('usable', '{}')")
        assert upgraded.connection.execute("SELECT value_json FROM remote_state WHERE key='usable'").fetchone()[0] == "{}"
    finally:
        upgraded.close()


@pytest.mark.parametrize("value", ["https://user:pass@example.com", "https://example.com/a", "https://example.com?",
    "https://example.com#", "https://example.com:65536", "https://example.com:0", "https://bad..host",
    "https://-bad.test", "https://127.1", "https://example.com\\evil", "http://localhost", "ftp://localhost"])
def test_invalid_origin_is_structured_and_does_not_echo(value):
    with pytest.raises(HubError) as error:
        normalize_origin(value)
    assert error.value.code == "REMOTE_SERVER_ORIGIN_INVALID"
    assert value not in str(error.value)


def test_origin_normalization_and_explicit_worker_development_exception():
    assert normalize_origin("HTTPS://Example.COM:443/") == "https://example.com"
    assert normalize_origin("https://[::1]:8443/") == "https://[::1]:8443"
    assert normalize_origin("http://LOCALHOST:80/", development=True) == "http://localhost"
    with pytest.raises(HubError):
        normalize_origin("http://192.168.1.2", development=True)


def test_device_vault_protection_and_deletion(tmp_path):
    vault = CredentialVault(tmp_path / "vault")
    vault.create()
    secret = vault.read()
    assert len(secret) >= 43
    if os.name == "nt":
        assert secret.encode() not in vault.path.read_bytes()
    else:
        assert vault.path.stat().st_mode & 0o777 == 0o600
        assert vault.directory.stat().st_mode & 0o777 == 0o700
    vault.delete()
    assert not vault.path.exists()


def test_minimal_task_service_has_unavailable_evidence_not_a_stop_claim():
    service = object.__new__(TaskService)
    service._record_control_evidence("task", "already_terminal")
    observation = service.control_observation("task")
    result = control_result(observation, observation)
    assert observation == {"evidenceAvailable": False}
    assert result["outcome"] == "unconfirmed"
    assert result["executionMayStillBeRunning"] is True


def test_tls_pairing_api_lifecycle_and_secret_redaction(tmp_path, caplog):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer() as server:
                caplog.set_level(logging.DEBUG)
                unauthorized = await system.local.get("/api/v1/remote/link", headers={"Authorization": ""})
                assert unauthorized.status_code == 401
                denied = await system.local.get("/api/v1/remote/link", headers={"Origin": "https://evil.invalid"})
                assert denied.status_code == 403
                system.link.http = PairingHTTP(system.link.vault, transport=httpx.AsyncHTTPTransport(verify=server.client_tls))
                body = {"serverOrigin": server.origin, "deviceName": "test device"}
                initial = await system.local.post("/api/v1/remote/pairing", json=body, headers={"Idempotency-Key": "pair"})
                assert initial.status_code == 200, initial.text
                pairing = RemoteLinkView.model_validate(initial.json()["data"])
                assert dump(pairing)["state"] == "pairing"
                seq = system.events.latest_seq()
                replay = await system.local.post("/api/v1/remote/pairing", json=body, headers={"Idempotency-Key": "pair"})
                assert initial.json()["data"] == replay.json()["data"]
                assert system.events.latest_seq() == seq and server.pair_calls == 1
                server.claimed = True
                await system.link.poll()
                paired = await system.local.get("/api/v1/remote/link")
                assert paired.json()["data"]["lastConnectedAt"] is None
                assert paired.json()["data"]["connectionStatus"] == "offline"
                cancel = await system.local.delete("/api/v1/remote/pairing", headers={"Idempotency-Key": "cancel-paired"})
                assert cancel.status_code == 409 and cancel.json()["error"]["code"] == "REMOTE_PAIRING_CONFLICT"
                secret = system.link.vault.read()
                assert secret == server.secret
                unlink = await system.local.post("/api/v1/remote/unlink", headers={"Idempotency-Key": "unlink"})
                assert unlink.json()["data"]["state"] == "unpaired"
                assert unlink.json()["data"]["lastErrorCode"] == "REMOTE_AUTH_REQUIRED"
                assert not system.link.vault.path.exists()
                count = system.events.latest_seq()
                again = await system.local.post("/api/v1/remote/unlink", headers={"Idempotency-Key": "unlink"})
                assert system.events.latest_seq() == count
                for response in (initial, replay, paired, unlink, again):
                    ApiEnvelope.model_validate(response.json())
                    RemoteLinkView.model_validate(response.json()["data"])
                    assert response.headers["cache-control"] == "no-store"
                events = system.events.page(0, 200).events
                for event in events:
                    RemoteLinkView.model_validate(event.payload)
                public = json.dumps([initial.json(), replay.json(), paired.json(), unlink.json(), [dump(e) for e in events]]) + caplog.text
                assert secret not in public and TOKEN not in public
                assert "Bearer " + secret not in public
                assert len(server.requests) == 1  # No invented device-revoke request.
        finally:
            await system.close()
    run(scenario())


def test_cancel_late_pair_response_and_expiry_do_not_resurrect(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer() as server:
                system.link.http = PairingHTTP(system.link.vault, transport=httpx.AsyncHTTPTransport(verify=server.client_tls))
                server.challenge_gate = asyncio.Event()
                request = RemoteLinkPairingInput(serverOrigin=server.origin, deviceName="late")
                pending = asyncio.create_task(system.link.pair(request, "late"))
                await server.challenge_entered.wait()
                assert dump(await system.link.clear("cancel"))["state"] == "unpaired"
                server.claimed = True
                server.challenge_gate.set()
                assert dump(await pending)["state"] == "unpaired"
                assert not system.link.vault.path.exists()
                count = server.pair_calls
                assert dump(await system.link.pair(request, "late"))["state"] == "unpaired"
                assert count == server.pair_calls
                server.secret = None
                server.claimed = False
                await system.link.pair(request, "new-pair")
                with system.db.transaction() as tx:
                    view = system.repo.get("link", tx)["view"]
                    view["expiresAt"] = later(-1)
                    system.repo.set_view(tx, view)
                    system.repo.seal(tx)
                assert dump(await system.link.view())["state"] == "unpaired"
                assert not system.link.vault.path.exists()
                assert "pairCode" not in dump(await system.link.view())
        finally:
            await system.close()
    run(scenario())


def test_credential_delete_failure_does_not_commit_successful_replay(tmp_path, monkeypatch):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server)
                original = system.link.vault.delete
                def fail():
                    raise HubError("INTERNAL", "injected delete failure")
                monkeypatch.setattr(system.link.vault, "delete", fail)
                with pytest.raises(HubError):
                    await system.link.clear("delete-fails", unlink=True)
                assert system.repo.get("link")["view"]["state"] == "paired"
                monkeypatch.setattr(system.link.vault, "delete", original)
                assert dump(await system.link.clear("delete-fails", unlink=True))["state"] == "unpaired"
                assert not system.link.vault.path.exists()
        finally:
            await system.close()
    run(scenario())


def test_pairing_redirect_never_forwards_authorization(tmp_path):
    async def scenario():
        vault = CredentialVault(tmp_path)
        vault.create()
        seen = []
        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(307, headers={"Location": "https://other.invalid/steal"})
        http = PairingHTTP(vault, transport=httpx.MockTransport(handler))
        with pytest.raises(HubError) as error:
            await http.request("https://original.invalid", "POST", "/api/v2/worker/pairing-requests", value={}, key="redirect")
        assert error.value.code == "REMOTE_SERVER_UNREACHABLE"
        assert seen == ["https://original.invalid/api/v2/worker/pairing-requests"]
        assert vault.read() not in str(error.value)
    run(scenario())


def test_real_ws_executes_in_order_skip_and_withdrawal_fill_gaps(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                one, two = system.command("one"), system.command("two", seq=2)
                await server.send(two)
                await until(lambda: any(f["type"] == "conversation.gap" for f in server.frames))
                assert system.adapter.started == []
                await server.send(one)
                await until(lambda: len(system.adapter.started) == 2)
                skip = {"type": "conversation.skip", "wireRevision": 1, "commandId": "skip-three", "conversationId": one["conversationId"],
                    "conversationSeq": 3, "targetWorkerId": one["targetWorkerId"], "expectedWorkerStoreId": one["expectedWorkerStoreId"],
                    "reason": "expired_before_dispatch", "recordedAt": now()}
                await server.send(system.command("four", seq=4))
                await server.send(skip)
                await until(lambda: len(system.adapter.started) == 3)
                withdraw = system.command("withdraw-five", kind="command.withdraw", payload={"targetCommandId": "five", "targetConversationSeq": 5})
                await server.send(withdraw)
                await server.send(system.command("six", seq=6))
                await server.send(system.command("five", seq=5))
                await until(lambda: len(system.adapter.started) == 4)
                await until(lambda: command_events(server, "six", "command.completed"))
                assert [s.objective for s in system.adapter.started] == ["one", "two", "four", "six"]
                assert command_events(server, "five", "command.rejected")[-1]["error"]["code"] == "REMOTE_COMMAND_WITHDRAWN"
                assert command_events(server, "withdraw-five", "command.completed")[-1]["controlResult"]["evidence"] == "inbox_tombstone"
                assert any(f["type"] == "conversation.skip_recorded" for f in server.frames)
                assert server.errors == []
        finally:
            await system.close()
    run(scenario())


def test_ws_reconnect_and_epoch_replay_preserve_identity_and_execute_once(tmp_path, caplog):
    async def scenario():
        system = System(tmp_path)
        caplog.set_level(logging.DEBUG)
        try:
            async with FakeRemoteServer(auto_ack=False) as server:
                await system.pair(server, start=True)
                command = system.command("exactly-once")
                await server.send(command)
                await until(lambda: command_events(server, "exactly-once", "command.completed"))
                receipt = command_events(server, "exactly-once", "command.accepted")[0]
                original_store, original_epoch = receipt["workerStoreId"], receipt["workerEpoch"]
                await server.ws.close(code=1012)
                await until(lambda: server.connections >= 2 and system.repo.get("link")["view"].get("connectionStatus") == "online")
                await server.send(command)
                await until(lambda: len(command_events(server, "exactly-once", "command.accepted")) >= 2)
                assert len(system.adapter.started) == 1
                conflict = {**command, "payload": {**command["payload"], "text": "changed content"}}
                await server.send(conflict)
                await until(lambda: command_events(server, "exactly-once", "command.rejected"))
                assert command_events(server, "exactly-once", "command.rejected")[-1]["error"]["code"] == "IDEMPOTENCY_MISMATCH"
                await system.worker.stop()
                await system.worker.start()
                await until(lambda: len(server.hellos) >= 3)
                assert server.hellos[-1]["workerEpoch"] != original_epoch
                assert server.hellos[-1]["workerStoreId"] == original_store
                await until(lambda: sum(f.get("eventId") == receipt["eventId"] for f in server.frames) >= 3)
                assert all(f == receipt for f in server.frames if f.get("eventId") == receipt["eventId"])
                assert len(system.adapter.started) == 1 and not server.errors
                assert system.link.vault.read() not in caplog.text
                assert TOKEN not in caplog.text
        finally:
            await system.close()
    run(scenario())


def test_admission_transaction_rolls_back_inbox_slot_run_and_outbox(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server)
                command = system.command("atomic")
                with system.db.transaction() as tx:
                    tx.connection.execute("CREATE TEMP TRIGGER reject_outbox BEFORE INSERT ON remote_outbox BEGIN SELECT RAISE(ABORT,'disk fault'); END")
                with pytest.raises(sqlite3.IntegrityError):
                    await system.bridge.receive(command)
                for table in ("remote_inbox", "remote_slots", "local_runs", "remote_outbox"):
                    assert system.db.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
                assert not system.adapter.started
                with system.db.transaction() as tx:
                    tx.connection.execute("DROP TRIGGER reject_outbox")
                def assert_committed(spec):
                    row = system.repo.inbox("atomic")
                    assert row["run_id"] and row["receipt_json"]
                    assert not system.db.connection.in_transaction
                    assert system.db.connection.execute("SELECT COUNT(*) FROM remote_outbox").fetchone()[0] > 0
                system.adapter.before_start = assert_committed
                await system.bridge.receive(command)
                await system.chat.start()
                await until(lambda: len(system.adapter.started) == 1)
        finally:
            await system.close()
    run(scenario())


def test_remote_authority_is_persistent_but_local_execution_writes_are_allowed(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                await server.send(system.command("remote-owner"))
                await until(lambda: command_events(server, "remote-owner", "command.completed"))
                row = system.repo.inbox("remote-owner")
                record = system.chat.repository.run_record(row["run_id"])
                conversation = record["conversation_id"]
                for action in ("pause", "resume", "retry", "cancel", "append_instruction"):
                    response = await system.local.post(f"/api/v2/runs/{row['run_id']}/commands", json={"action": action, "instruction": "x"}, headers={"Idempotency-Key": action})
                    assert response.status_code == 202, response.text
                    if action in {"resume", "retry", "append_instruction"}:
                        await until(lambda: system.chat.repository.run_record(response.json()["data"]["id"])["status"] == "succeeded")
                direct = await system.local.post(f"/api/v1/tasks/{record['task_id']}/actions", json={"action": "retry"}, headers={"Idempotency-Key": "direct"})
                assert direct.status_code == 200, direct.text
                await until(lambda: str(system.tasks.repository.get(direct.json()["data"]["id"]).status) == "succeeded")
                sessions = await system.ports.sessions.list_sessions({"taskId": record["task_id"]})
                resumed = await system.local.post(f"/api/v1/sessions/{sessions[0].id}/resume", json={"instruction": "x"})
                assert resumed.status_code == 200, resumed.text
                assert system.adapter.resumed[-1].session_id == sessions[0].id
                await system.link.clear("unlink-authority", unlink=True)
                assert system.chat.repository.conversation(conversation).authority == "remote"
                message = await system.local.post(f"/api/v2/conversations/{conversation}/messages", json={"clientMessageId": "bad", "text": "x", "sessionMode": "new"}, headers={"Idempotency-Key": "bad"})
                assert message.status_code == 202, message.text
                local = await system.local.post("/api/v2/conversations", json={"title": "local", "workspaceId": "workspace", "sceneId": "analyze"}, headers={"Idempotency-Key": "local"})
                local_view = LocalConversationView.model_validate(local.json()["data"])
                assert local_view.authority == "local"
                sent = await system.local.post(f"/api/v2/conversations/{local_view.id}/messages", json={"clientMessageId": "local-msg", "text": "local", "sessionMode": "new"}, headers={"Idempotency-Key": "local-msg"})
                assert sent.status_code == 202
        finally:
            await system.close()
    run(scenario())


def test_unsupported_wire_revision_freezes_without_reconnect_storm(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer(reject_revisions=[5]) as server:
                await system.pair(server, start=True)
                await until(lambda: system.repo.get("link")["view"]["state"] == "frozen")
                await asyncio.sleep(0.2)
                view = dump(await system.link.view())
                assert view["lastErrorCode"] == "REMOTE_PROTOCOL_UNSUPPORTED"
                assert view["connectionStatus"] == "offline" and view["lastConnectedAt"] is None
                assert server.connections == 1 and not server.errors
        finally:
            await system.close()
    run(scenario())
