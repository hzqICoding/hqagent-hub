from __future__ import annotations

from storage.events import EventDraft


TASK = {"objective": "验证事务幂等", "workspaceId": "ws_test", "source": "desktop"}


def test_same_idempotency_key_creates_one_task_and_event(client, hub, auth_headers) -> None:
    headers = {**auth_headers, "Idempotency-Key": "idem-task-001"}
    responses = [client.post("/api/v1/tasks", headers=headers, json=TASK) for _ in range(3)]
    assert all(response.status_code == 200 for response in responses)
    ids = {response.json()["data"]["id"] for response in responses}
    assert len(ids) == 1
    with hub.database.locked_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM events WHERE type='task.created'").fetchone()[0] == 1


def test_idempotency_mismatch_is_conflict(client, auth_headers) -> None:
    headers = {**auth_headers, "Idempotency-Key": "idem-task-002"}
    assert client.post("/api/v1/tasks", headers=headers, json=TASK).status_code == 200
    changed = {**TASK, "objective": "不同请求"}
    response = client.post("/api/v1/tasks", headers=headers, json=changed)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_MISMATCH"


def test_event_cursor_expired_has_snapshot_recovery(client, hub, auth_headers) -> None:
    for index in range(3):
        with hub.database.transaction() as transaction:
            hub.events.append(
                transaction,
                EventDraft("system", "test", "agent.progress", {"index": index}),
            )
    hub.events.prune_before(3)
    response = client.get("/api/v1/events?after=0", headers=auth_headers)
    assert response.status_code == 410
    error = response.json()["error"]
    assert error["code"] == "EVENT_CURSOR_EXPIRED"
    assert error["detail"]["snapshotUrl"] == "/api/v1/bootstrap"
    snapshot = client.get("/api/v1/bootstrap", headers=auth_headers)
    assert snapshot.status_code == 200
    assert snapshot.json()["data"]["lastEventSeq"] >= 3


def test_websocket_reconnect_replays_without_duplicates(client, hub, auth_headers) -> None:
    with hub.database.transaction() as transaction:
        first, _ = hub.events.append(transaction, EventDraft("system", "test", "agent.progress", {"n": 1}))
    for number in (2, 3):
        with hub.database.transaction() as transaction:
            hub.events.append(transaction, EventDraft("system", "test", "agent.progress", {"n": number}))
    ticket = client.post("/api/v1/auth/ws-ticket", headers=auth_headers).json()["data"]["ticket"]
    received = []
    with client.websocket_connect(
        f"/api/v1/events/stream?ticket={ticket}&after={first.seq}",
        headers={"Origin": "http://localhost:1420"},
    ) as websocket:
        received.append(websocket.receive_json())
        received.append(websocket.receive_json())
    assert [item["payload"]["n"] for item in received] == [2, 3]
    assert len({item["seq"] for item in received}) == 2

