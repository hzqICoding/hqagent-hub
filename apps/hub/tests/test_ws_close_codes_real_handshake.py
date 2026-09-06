"""WS 关闭码必须能真正到达客户端——这一条只有真握手才测得出来。

Starlette 的 TestClient 在进程内自实现 WebSocket，不走 HTTP 握手，
close code 被直接交给调用方。所以下面这些断言在 TestClient 上恒真，
即使服务端把 close 发在 accept 之前（那种写法会被 ASGI 服务器翻译成
HTTP 403 握手拒绝，浏览器只能拿到 code 1006，4401/4403/4410 全部丢失）。

同类盲区上一轮已经吃过一次：裸 uvicorn 缺 websockets 实现时
/events/stream 完全不可用，而整套 TestClient 测试是绿的
（见 .hqagent/reviews/INT-smoke-W1xW5.md）。所以这个文件必须起真 uvicorn。
"""
from __future__ import annotations

import asyncio
import socket
import threading

import pytest
import uvicorn
import websockets

from conftest import TOKEN


ORIGIN = "http://localhost:1420"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _LiveServer:
    def __init__(self, app) -> None:
        self.port = _free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="error")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> "_LiveServer":
        self.thread.start()
        for _ in range(200):
            if self.server.started:
                return self
            threading.Event().wait(0.05)
        raise RuntimeError("uvicorn 没能在 10 秒内启动")

    def __exit__(self, *_exc) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)

    def ws_url(self, query: str) -> str:
        return f"ws://127.0.0.1:{self.port}/api/v1/events/stream?{query}"


async def _close_code(url: str, origin: str) -> int:
    """连上去、等对端关闭，返回客户端实际观察到的关闭码。"""
    async with websockets.connect(url, additional_headers={"Origin": origin}) as ws:
        try:
            while True:
                await ws.recv()
        except websockets.ConnectionClosed as exc:
            return int(exc.code)
    raise AssertionError("连接没有被服务端关闭")


@pytest.fixture
def live(hub):
    with _LiveServer(hub.app) as server:
        yield server


def test_bad_ticket_closes_with_4401_not_a_handshake_rejection(live) -> None:
    """裁决 D23：票不对是 4401。必须是关闭码，不能退化成 HTTP 403 握手拒绝。"""
    code = asyncio.run(_close_code(live.ws_url("ticket=bogus&after=0"), ORIGIN))
    assert code == 4401


def test_bad_origin_closes_with_4403_and_is_distinguishable_from_bad_ticket(live) -> None:
    """来源不对是 4403。和 4401 分得开，才谈得上「排障时看得出是哪种」。"""
    code = asyncio.run(_close_code(live.ws_url("ticket=bogus&after=0"), "https://evil.example.com"))
    assert code == 4403


def test_expired_cursor_closes_with_4410_and_sends_snapshot_url_first(live, hub) -> None:
    """游标过期要给 4410，且必须先发一帧带 snapshotUrl 的错误。

    光给关闭码不够用：前端拿不到 snapshotUrl 就不知道去哪重取 Snapshot，
    只能带着同一个过期游标无限退避重连（§22.3 明列的验收项）。
    """
    from storage.events import EventDraft

    with hub.database.transaction() as transaction:
        for index in range(3):
            hub.events.append(
                transaction,
                EventDraft(
                    aggregate_type="task",
                    aggregate_id="task_cursor_probe",
                    type="task.status_changed",
                    payload={"n": index},
                ),
            )
    hub.events.prune_before(hub.events.latest_seq())

    async def scenario() -> tuple[int, dict]:
        import httpx

        base = f"http://127.0.0.1:{live.port}"
        headers = {"Authorization": f"Bearer {TOKEN}", "Origin": ORIGIN}
        async with httpx.AsyncClient(base_url=base, headers=headers) as client:
            response = await client.post("/api/v1/auth/ws-ticket", json={"purpose": "events"})
            ticket = response.json()["data"]["ticket"]

        import json as jsonlib

        frame: dict = {}
        async with websockets.connect(
            live.ws_url(f"ticket={ticket}&after=0"),
            additional_headers={"Origin": ORIGIN},
        ) as ws:
            try:
                while True:
                    message = await ws.recv()
                    parsed = jsonlib.loads(message)
                    if isinstance(parsed, dict) and "error" in parsed:
                        frame = parsed
            except websockets.ConnectionClosed as exc:
                return int(exc.code), frame
        raise AssertionError("连接没有被服务端关闭")

    code, frame = asyncio.run(scenario())
    assert code == 4410
    assert frame["error"]["code"] == "EVENT_CURSOR_EXPIRED"
    assert frame["error"]["detail"]["snapshotUrl"] == "/api/v1/bootstrap"
    assert "oldestAvailableSeq" in frame["error"]["detail"]


def test_valid_ticket_still_connects(live, hub) -> None:
    """修 accept 时机不能把正常连接弄坏。"""

    async def scenario() -> bool:
        import httpx

        base = f"http://127.0.0.1:{live.port}"
        headers = {"Authorization": f"Bearer {TOKEN}", "Origin": ORIGIN}
        async with httpx.AsyncClient(base_url=base, headers=headers) as client:
            response = await client.post("/api/v1/auth/ws-ticket", json={"purpose": "events"})
            ticket = response.json()["data"]["ticket"]
        async with websockets.connect(
            live.ws_url(f"ticket={ticket}&after=0"),
            additional_headers={"Origin": ORIGIN},
        ):
            return True

    assert asyncio.run(scenario()) is True
