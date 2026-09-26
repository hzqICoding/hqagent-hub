import asyncio
import json
import logging
from pathlib import Path
import secrets

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse
from protocol.generated import python as dto

from conftest import FakeWorker
from server.app import create_app
from server.common import MAX_SEQ, stamp, uid
from server.config import Settings
from server.repository import Repository
from test_commands_events import admit_run


def test_wss_auth_rate_limit_has_registered_error_and_retry_after(env, paired):
    env.clock.advance(61)
    env.settings.rate_limit = 1
    with paired.connect():
        assert paired.ack["type"] == "worker.hello_ack"
    with pytest.raises(WebSocketDenialResponse) as denied:
        with paired.connect():
            pass
    assert denied.value.status_code == 429
    assert int(denied.value.headers["retry-after"]) > 0
    dto.ApiEnvelope.model_validate(denied.value.json())
    assert denied.value.json()["error"]["code"] == "REMOTE_RATE_LIMITED"


def test_worker_cannot_reference_other_owner_conversation(env, paired):
    other = FakeWorker(env, env.bob)
    other.confirm()
    with other.connect():
        other.catalog()
    foreign = other.conversation()
    with paired.connect():
        event = paired.event("message.appended", conversationId=foreign, payload=dict(messageId=uid(), conversationId=foreign, role="assistant", text="should never appear", createdAt=stamp(env.clock())))
        assert paired.emit(event)["error"]["code"] == "NOT_FOUND"
    assert env.bob.get("/conversations/" + foreign + "/messages").json()["data"]["items"] == []


def test_new_event_id_same_seq_and_omitted_overlap_rejected(env, paired):
    with paired.connect():
        conflict = paired.event("events.omitted", 2, firstSeq=1, reason="not_remote_visible")
        assert paired.emit(conflict)["error"]["code"] == "REMOTE_EVENT_CONFLICT"
    with paired.connect():
        one = paired.event("events.omitted", 2, firstSeq=2, reason="not_remote_visible")
        assert paired.emit(one)["position"]["seq"] == 2
        assert paired.emit(dict(one, eventId=uid()))["error"]["code"] == "REMOTE_EVENT_CONFLICT"


def test_ack_ahead_and_reported_ack_regression(env, paired):
    with paired.connect(paired.hello(lastServerAck=dict(workerStoreId=paired.store, seq=1))):
        assert paired.ack["commandDelivery"] == "ready"
    with paired.connect(paired.hello(lastServerAck=None)):
        assert paired.ack["commandDelivery"] == "frozen"
        assert paired.ack["reason"]["code"] == "REMOTE_ACK_CONFLICT"
    other = FakeWorker(env, env.bob)
    other.confirm()
    with other.connect(other.hello(lastServerAck=dict(workerStoreId=other.store, seq=999))):
        assert other.ack["commandDelivery"] == "frozen"


def test_expiry_limits_and_safe_sequence_exhaustion(env, paired):
    path = "/conversations/" + paired.conv + "/messages"
    for expires in (env.clock() - 1, env.clock() + 7 * 86400 + 1):
        response = env.alice.post(path, dict(clientMessageId=uid(), text="x", sessionMode="new", expiresAt=stamp(expires)))
        assert response.status_code == 410
    with env.service.repo.transaction() as tx:
        owner = env.service.security.session(tx, env.alice.cookie)["owner"]
        conv = tx.get(owner, "conversation", paired.conv)
        conv["_nextSeq"] = MAX_SEQ + 1
        env.service.save(tx, owner, "conversation", paired.conv, conv)
    assert env.alice.post(path, dict(clientMessageId=uid(), text="x", sessionMode="new")).json()["error"]["code"] == "REMOTE_STORE_CHANGED"


def test_revoke_undispatched_retains_immutable_skip(env, paired):
    receipt = paired.send(paired.conv)
    env.alice.post("/devices/" + paired.worker + "/revocations")
    with env.service.repo.transaction() as tx:
        owner = env.service.security.session(tx, env.alice.cookie)["owner"]
        command = tx.get(owner, "command", receipt["commandId"])
        assert command["status"] == "rejected" and not command["_dispatch"]
        box = tx.get(owner, "outbox", "skip:" + receipt["commandId"])
        dto.RemoteConversationSkip.model_validate(box["_frame"])
        assert box["_frame"]["conversationSeq"] == 1


def test_catalog_updates_device_projection_without_stale_overwrite(env, paired):
    with paired.connect():
        assert paired.catalog(capabilityRevision=2)["type"] == "worker.events_ack"
        assert env.alice.get("/devices/" + paired.worker).json()["data"]["capabilityRevision"] == 2


def test_authority_marker_enforced(env, paired):
    with env.service.repo.transaction() as tx:
        owner = env.service.security.session(tx, env.alice.cookie)["owner"]
        conv = tx.get(owner, "conversation", paired.conv)
        conv["authority"] = "local"
        env.service.save(tx, owner, "conversation", paired.conv, conv)
    result = env.alice.post("/conversations/" + paired.conv + "/messages", dict(clientMessageId=uid(), text="x", sessionMode="new"))
    assert result.json()["error"]["code"] == "CONVERSATION_AUTHORITY_MISMATCH"


def test_optional_static_mount_and_api_priority(tmp_path):
    static = tmp_path / "h5"
    static.mkdir()
    (static / "index.html").write_text("<h1>H5 build</h1>", encoding="utf-8")
    settings = Settings(tmp_path / "static.sqlite3", secrets.token_bytes(32), origin="https://testserver", static_dir=static)
    with TestClient(create_app(settings), base_url=settings.origin) as client:
        assert client.get("/").text == "<h1>H5 build</h1>"
        assert client.get("/api/v2/auth/session").json()["data"] == dict(authenticated=False)
    settings = Settings(tmp_path / "no-static.sqlite3", secrets.token_bytes(32), origin="https://testserver")
    with TestClient(create_app(settings), base_url=settings.origin) as client:
        assert client.get("/").status_code == 404


def test_no_sqlite_dialect_in_business_code():
    root = Path(__file__).resolve().parents[1] / "server"
    for path in root.glob("*.py"):
        if path.name == "repository.py":
            continue
        code = path.read_text(encoding="utf-8")
        assert "import sqlite3" not in code
        assert "PRAGMA " not in code


def test_control_uses_worker_reference_without_inventing_run_state(env, paired):
    with paired.connect():
        receipt = paired.send(paired.conv)
        paired.receive()
        accepted = paired.event("command.accepted", commandId=receipt["commandId"], conversationId=paired.conv,
                                receivedAt=stamp(env.clock()), status="accepted", resultRef=dict(runId="bound", executionTaskId="bound-task"))
        assert paired.emit(accepted)["type"] == "worker.events_ack"
        assert env.alice.get("/runs/bound").status_code == 404
        assert env.bob.post("/runs/bound/commands", dict(action="cancel")).status_code == 404
        assert env.alice.post("/runs/bound/commands", dict(action="cancel")).status_code == 202
        assert paired.receive()["type"] == "run.cancel"


def test_delivery_batches_keep_conversation_order(env, paired):
    for _ in range(33):
        paired.send(paired.conv)
    with paired.connect():
        assert [paired.receive()["conversationSeq"] for _ in range(33)] == list(range(1, 34))


def test_wall_clock_jump_does_not_change_liveness(env, paired):
    env.settings.monotonic = lambda: 100.0
    with paired.connect():
        env.clock.advance(100)
        assert env.alice.get("/devices/" + paired.worker).json()["data"]["status"] == "online"
