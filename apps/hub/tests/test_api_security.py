from __future__ import annotations


def test_health_is_public_and_has_only_frozen_fields(client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert set(response.json()) == {"status", "appVersion", "protocolVersion", "pid", "startedAt"}


def test_http_requires_bearer_and_rejects_origin(client, auth_headers) -> None:
    assert client.get("/api/v1/bootstrap").status_code == 401
    bad = dict(auth_headers)
    bad["Origin"] = "https://example.com"
    assert client.get("/api/v1/bootstrap", headers=bad).status_code == 401
    assert client.get("/api/v1/bootstrap", headers=auth_headers).status_code == 200


def test_ticket_is_single_use(client, auth_headers) -> None:
    response = client.post("/api/v1/auth/ws-ticket", headers=auth_headers, json={"purpose": "events"})
    ticket = response.json()["data"]["ticket"]
    with client.websocket_connect(
        f"/api/v1/events/stream?ticket={ticket}&after=0",
        headers={"Origin": "http://localhost:1420"},
    ):
        pass
    replay_rejected = False
    try:
        with client.websocket_connect(
            f"/api/v1/events/stream?ticket={ticket}&after=0",
            headers={"Origin": "http://localhost:1420"},
        ):
            pass
    except Exception:
        replay_rejected = True
    assert replay_rejected
