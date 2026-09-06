from __future__ import annotations

import pytest


def test_health_is_public_and_has_only_frozen_fields(client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert set(response.json()) == {"status", "appVersion", "protocolVersion", "pid", "startedAt"}


def test_http_requires_bearer_and_rejects_origin(client, auth_headers) -> None:
    # 裁决 D23：没带对 token 是 UNAUTHORIZED(401)，来源不对是 ORIGIN_NOT_ALLOWED(403)。
    # 两者必须能分开——否则排障时看不出是凭据问题还是 Origin 配错了。
    missing_token = client.get("/api/v1/bootstrap")
    assert missing_token.status_code == 401
    assert missing_token.json()["error"]["code"] == "UNAUTHORIZED"

    bad = dict(auth_headers)
    bad["Origin"] = "https://example.com"
    bad_origin = client.get("/api/v1/bootstrap", headers=bad)
    assert bad_origin.status_code == 403
    assert bad_origin.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"

    assert client.get("/api/v1/bootstrap", headers=auth_headers).status_code == 200


def test_protocol_version_comes_from_generated_package() -> None:
    """裁决 D24：协议版本只有一个事实源，不得在 Hub 侧硬编码。"""
    from protocol.generated.python import PROTOCOL_VERSION as generated

    from core.constants import PROTOCOL_VERSION as hub

    assert hub == generated


def test_ticket_is_single_use(client, auth_headers) -> None:
    response = client.post("/api/v1/auth/ws-ticket", headers=auth_headers, json={"purpose": "events"})
    ticket = response.json()["data"]["ticket"]
    with client.websocket_connect(
        f"/api/v1/events/stream?ticket={ticket}&after=0",
        headers={"Origin": "http://localhost:1420"},
    ):
        pass
    # 断言具体关闭码，不是「抛了个异常就算过」。
    # 老写法 except Exception: replay_rejected = True 太松——服务端把 close 发在
    # accept 之前时它照样绿，而那种写法下浏览器只会拿到 code 1006，
    # 4401/4403/4410 全部丢失（见 .hqagent/reviews/INT-ws-close-codes.md）。
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect(
        f"/api/v1/events/stream?ticket={ticket}&after=0",
        headers={"Origin": "http://localhost:1420"},
    ) as replayed:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            replayed.receive_text()
    assert excinfo.value.code == 4401
