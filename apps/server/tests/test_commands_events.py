import json

import pytest
from starlette.websockets import WebSocketDisconnect

from conftest import FakeWorker
from server.common import Fault, stamp, uid


def admit_run(worker, *, run_id="run", ref=True):
    receipt = worker.send(worker.conv)
    frame = worker.receive()
    assert frame["commandId"] == receipt["commandId"]
    fields = dict(commandId=receipt["commandId"], conversationId=worker.conv, receivedAt=stamp(worker.env.clock()), status="accepted")
    if ref:
        fields["resultRef"] = dict(runId=run_id, executionTaskId="task-" + run_id)
    assert worker.emit(worker.event("command.accepted", **fields))["type"] == "worker.events_ack"
    payload = dict(runId=run_id, executionTaskId="task-" + run_id, conversationId=worker.conv, status="running", observedAt=stamp(worker.env.clock()))
    assert worker.emit(worker.event("run.state_changed", commandId=receipt["commandId"], conversationId=worker.conv, payload=payload))["type"] == "worker.events_ack"
    return receipt


def test_withdraw_never_dispatched_skip_and_gap_replay(env, paired):
    first = paired.send(paired.conv)
    second = paired.send(paired.conv)
    result = env.alice.post("/commands/" + first["commandId"] + "/cancellations")
    assert result.status_code == 202
    assert result.json()["data"]["status"] == "rejected"
    assert result.json()["data"]["error"]["code"] == "REMOTE_COMMAND_WITHDRAWN"
    with paired.connect():
        skip, submit = paired.receive(), paired.receive()
        assert skip["type"] == "conversation.skip" and skip["conversationSeq"] == 1
        assert submit["type"] == "run.submit" and submit["conversationSeq"] == 2
        assert paired.emit(paired.event("conversation.skip_recorded", commandId=first["commandId"], conversationId=paired.conv, conversationSeq=1))["position"]["seq"] == 2
        paired.ws.send_json(dict(type="conversation.gap", wireRevision=1, workerId=paired.worker, workerStoreId=paired.store, workerEpoch=paired.epoch, conversationId=paired.conv, expectedSeq=1, receivedSeq=2))
        assert paired.receive() == skip
        assert paired.emit(paired.event("command.accepted", commandId=second["commandId"], conversationId=paired.conv, receivedAt=submit["createdAt"], status="accepted"))["position"]["seq"] == 3


def test_message_and_command_idempotency(env, paired):
    body = dict(clientMessageId=uid(), text="original", sessionMode="new")
    path = "/conversations/" + paired.conv + "/messages"
    key = uid()
    a = env.alice.post(path, body, key=key)
    assert env.alice.post(path, body, key=key).json()["data"] == a.json()["data"]
    assert env.alice.post(path, body).json()["data"] == a.json()["data"]
    assert env.alice.post(path, dict(body, text="changed"), key=key).status_code == 409
    assert env.alice.post(path, dict(body, text="changed")).status_code == 409
    assert len(env.alice.get("/conversations/" + paired.conv + "/messages").json()["data"]["items"]) == 1
    # Direct repository boundary also rejects a reused command ID with new content.
    with env.service.repo.transaction() as tx:
        owner = env.service.security.session(tx, env.alice.cookie)["owner"]
        conv = env.service.get(tx, owner, "conversation", paired.conv)
        command = env.service.get(tx, owner, "command", a.json()["data"]["commandId"])
        args = (tx, owner, conv, "run.submit", command["_frame"]["payload"], command["expiresAt"], command["conversationSeq"], command["commandId"])
        assert env.service.enqueue(*args) == a.json()["data"]
        with pytest.raises(Fault, match="IDEMPOTENCY_MISMATCH"):
            env.service.enqueue(*args[:4], dict(args[4], text="changed"), *args[5:])


def test_expiration_keeps_sequence_and_preserves_possible_execution(env, paired):
    first = paired.send(paired.conv, expiresAt=stamp(env.clock() + 1))
    env.clock.advance(2)
    second = paired.send(paired.conv)
    with paired.connect():
        skip, submit = paired.receive(), paired.receive()
        assert skip["reason"] == "expired_before_dispatch" and skip["conversationSeq"] == 1
        assert submit["conversationSeq"] == 2
    assert env.alice.get("/commands/" + first["commandId"]).json()["data"]["error"]["code"] == "REMOTE_COMMAND_EXPIRED"
    assert env.alice.get("/commands/" + second["commandId"]).json()["data"]["status"] == "queued"


def test_dispatched_expiry_reconciles_and_late_accept_is_preserved(env, paired):
    with paired.connect():
        receipt = paired.send(paired.conv, expiresAt=stamp(env.clock() + 1))
        original = paired.receive()
        env.clock.advance(2)
        view = env.alice.get("/commands/" + receipt["commandId"]).json()["data"]
        assert view["status"] == "queued" and view["deliveryState"] == "reconciliation_required"
        accepted = paired.event("command.accepted", commandId=receipt["commandId"], conversationId=paired.conv, receivedAt=original["createdAt"], status="accepted")
        assert paired.emit(accepted)["type"] == "worker.events_ack"
        assert env.alice.get("/commands/" + receipt["commandId"]).json()["data"]["status"] == "accepted"
    env.clock.advance(86400 - 10)
    assert env.alice.get("/commands/" + receipt["commandId"]).json()["data"]["status"] == "accepted"


def test_withdraw_after_dispatch_waits_for_worker_tombstone(env, paired):
    with paired.connect():
        receipt = paired.send(paired.conv)
        original = paired.receive()
        response = env.alice.post("/commands/" + receipt["commandId"] + "/cancellations")
        assert response.json()["data"]["withdrawalState"] == "requested"
        withdraw = paired.receive()
        assert withdraw["type"] == "command.withdraw" and "conversationSeq" not in withdraw
        assert withdraw["payload"]["targetConversationSeq"] == 1
        assert paired.emit(paired.event("command.accepted", commandId=withdraw["commandId"], conversationId=paired.conv, receivedAt=withdraw["createdAt"], status="accepted"))["type"] == "worker.events_ack"
        evidence = dict(outcome="confirmed", executionMayStillBeRunning=False, orphanProcessIds=[], reason="persisted", evidence="inbox_tombstone", observedAt=stamp(env.clock()))
        done = paired.event("command.completed", commandId=withdraw["commandId"], conversationId=paired.conv, resultStatus="withdrawn", controlResult=evidence)
        assert paired.emit(done)["type"] == "worker.events_ack"
        view = env.alice.get("/commands/" + original["commandId"]).json()["data"]
        assert view["status"] == "rejected" and view["withdrawalState"] == "confirmed"


def test_event_gaps_omissions_duplicates_and_conflicts(env, paired):
    tail = env.alice.get("/events").json()["data"]["nextServerCursor"]
    with paired.connect():
        event = paired.event("events.omitted", 4, firstSeq=3, reason="not_remote_visible")
        assert paired.emit(event)["position"]["seq"] == 1
        assert paired.emit(event)["position"]["seq"] == 1
        fill = paired.event("events.omitted", 2, firstSeq=2, reason="not_remote_visible")
        assert paired.emit(fill)["position"]["seq"] == 4
        assert paired.emit(event)["position"]["seq"] == 4
        assert env.alice.get("/events?after=" + tail).json()["data"]["items"] == []
        conflict = dict(event, firstSeq=2)
        assert paired.emit(conflict)["error"]["code"] == "REMOTE_EVENT_CONFLICT"


def test_visible_projection_waits_for_contiguous_commit(env, paired):
    with paired.connect():
        catalog = dict(workerId=paired.worker, workerStoreId=paired.store, capabilityRevision=2, observedAt=stamp(env.clock()), workspaces=[], scenes=[], remotelyBlockedActions=[])
        event = paired.event("capability.changed", 3, payload=catalog)
        assert paired.emit(event)["position"]["seq"] == 1
        assert env.alice.get("/devices/" + paired.worker + "/catalog").json()["data"]["capabilityRevision"] == 1
        assert paired.emit(paired.event("events.omitted", 2, firstSeq=2, reason="not_remote_visible"))["position"]["seq"] == 3
        assert env.alice.get("/devices/" + paired.worker + "/catalog").json()["data"]["capabilityRevision"] == 2


def test_new_store_freezes_old_pending_commands(env, paired):
    receipt = paired.send(paired.conv)
    old_store = paired.store
    paired.store = uid()
    with paired.connect():
        assert paired.ack["commandDelivery"] == "frozen"
        assert paired.ack["reason"]["code"] == "REMOTE_STORE_CHANGED"
        assert paired.ack["lastServerAck"]["seq"] == 0
        view = env.alice.get("/commands/" + receipt["commandId"]).json()["data"]
        assert view["deliveryState"] == "reconciliation_required" and view["status"] == "queued"
        paired.ws.send_json(dict(type="worker.heartbeat", wireRevision=1, connectionId=paired.ack["connectionId"], workerId=paired.worker, workerStoreId=paired.store, workerEpoch=paired.epoch, sentAt=stamp(env.clock()), lastServerAck=None))
        assert paired.receive()["type"] == "server.heartbeat"  # no command was delivered
    with paired.connect():
        assert paired.ack["commandDelivery"] == "frozen"
    paired.store = old_store
    with paired.connect():
        assert paired.ack["commandDelivery"] == "frozen"  # changing back never unfreezes


def test_old_connection_fenced_but_old_epoch_events_replay(env, paired):
    old_epoch = paired.epoch
    with paired.connect():
        old_socket = paired.ws
        paired.epoch = uid()
        with paired.connect():
            with pytest.raises(WebSocketDisconnect) as closed:
                old_socket.receive_json()
            assert closed.value.code == 4409
            event = paired.event("events.omitted", 2, firstSeq=2, reason="not_remote_visible", workerEpoch=old_epoch)
            assert paired.emit(event)["position"]["seq"] == 2
            paired.ws.send_json(dict(type="worker.heartbeat", wireRevision=1, connectionId=paired.ack["connectionId"], workerId=paired.worker, workerStoreId=paired.store, workerEpoch=old_epoch, sentAt=stamp(env.clock()), lastServerAck=None))
            assert paired.receive()["error"]["code"] == "REMOTE_EPOCH_STALE"


def test_ack_regression_and_cross_store_freeze(env, paired):
    with paired.connect(paired.hello(lastServerAck=dict(workerStoreId="foreign", seq=1))):
        assert paired.ack["commandDelivery"] == "frozen"
        assert paired.ack["reason"]["code"] == "REMOTE_ACK_CONFLICT"


def test_heartbeat_and_45_second_offline(env, paired):
    with paired.connect():
        assert paired.ack["heartbeatIntervalSeconds"] == 15 and paired.ack["offlineAfterSeconds"] == 45
        env.clock.advance(46)
        assert env.alice.get("/devices/" + paired.worker).json()["data"]["status"] == "offline"
        assert paired.receive()["error"]["code"] == "REMOTE_DEVICE_OFFLINE"


def test_browser_cursor_paging_scope_and_expiration(env, paired):
    env.settings.cursor_ttl = 5
    snapshot = env.alice.get("/conversations/" + paired.conv + "/snapshot").json()["data"]
    paired.send(paired.conv)
    paired.send(paired.conv)
    cursor = snapshot["serverCursor"]
    seen = []
    while True:
        page = env.alice.get("/events?after=" + cursor + "&limit=1").json()["data"]
        seen += page["items"]
        cursor = page["nextServerCursor"]
        if not page["hasMore"]:
            break
    assert len(seen) == 4
    assert env.bob.get("/events?after=" + cursor).json()["error"]["code"] == "REMOTE_CURSOR_INVALID"
    messages = env.alice.get("/conversations/" + paired.conv + "/messages?limit=1").json()["data"]
    assert messages["hasMore"]
    assert env.alice.get("/events?after=" + messages["nextCursor"]).json()["error"]["code"] == "REMOTE_CURSOR_INVALID"
    following = env.alice.get("/conversations/" + paired.conv + "/messages?cursor=" + messages["nextCursor"]).json()["data"]
    assert len(following["items"]) == 1 and not following["hasMore"]
    env.clock.advance(6)
    expired = env.alice.get("/events?after=" + cursor)
    assert expired.status_code == 410 and expired.json()["error"]["code"] == "REMOTE_CURSOR_EXPIRED"
    assert env.alice.get("/conversations/" + paired.conv + "/snapshot").status_code == 200


def test_visible_run_can_bind_after_accept_without_result_ref(env, paired):
    with paired.connect():
        receipt = admit_run(paired, ref=False)
        assert env.alice.get("/runs/run").json()["data"]["status"] == "running"
        assert env.bob.get("/runs/run").status_code == 404
        assert env.alice.post("/commands/" + receipt["commandId"] + "/cancellations").json()["error"]["code"] == "REMOTE_WITHDRAWAL_TOO_LATE"
