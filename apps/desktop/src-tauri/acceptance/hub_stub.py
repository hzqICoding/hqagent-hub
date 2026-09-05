#!/usr/bin/env python3
"""Minimal loopback-only Hub stub for W5 security acceptance.

This is deliberately not production Hub code. It exercises the frozen runtime
descriptor, Bearer, Origin, and one-time WebSocket ticket contract without
modifying apps/hub/.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import threading
import time
from urllib.parse import parse_qs, urlparse
import uuid


ALLOWED_ORIGINS = {"http://tauri.localhost", "http://localhost:5173"}
TOKEN = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")


class TicketStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tickets: dict[str, float] = {}

    def issue(self) -> tuple[str, float]:
        ticket = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
        expires_at = time.time() + 30
        with self._lock:
            self._tickets[ticket] = expires_at
        return ticket, expires_at

    def consume(self, ticket: str) -> bool:
        now = time.time()
        with self._lock:
            expires_at = self._tickets.pop(ticket, None)
            for value, expiry in list(self._tickets.items()):
                if expiry <= now:
                    self._tickets.pop(value, None)
        return expires_at is not None and expires_at > now


TICKETS = TicketStore()


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "HQAgentW5Stub/0.1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send(self, status: int, body: bytes = b"", content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _bearer_valid(self) -> bool:
        return secrets.compare_digest(self.headers.get("Authorization", ""), f"Bearer {TOKEN}")

    def _origin_valid(self) -> bool:
        return self.headers.get("Origin") in ALLOWED_ORIGINS

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            body = json.dumps(self.server.health, separators=(",", ":")).encode()
            self._send(200, body)
            return
        if parsed.path == "/api/v1/bootstrap":
            if not self._bearer_valid():
                self._send(401, b'{"code":"UNAUTHORIZED"}')
                return
            if not self._origin_valid():
                self._send(403, b'{"code":"ORIGIN_REJECTED"}')
                return
            body = json.dumps(
                {
                    "success": True,
                    "data": {
                        "maintenance": False,
                        "instanceId": self.server.instance_id,
                    },
                },
                separators=(",", ":"),
            ).encode()
            self._send(200, body)
            return
        if parsed.path == "/api/v1/events/stream":
            self._handle_websocket(parsed)
            return
        self._send(404, b'{"code":"NOT_FOUND"}')

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/v1/auth/ws-ticket":
            self._send(404, b'{"code":"NOT_FOUND"}')
            return
        if not self._bearer_valid():
            self._send(401, b'{"code":"UNAUTHORIZED"}')
            return
        if not self._origin_valid():
            self._send(403, b'{"code":"ORIGIN_REJECTED"}')
            return
        ticket, expires_at = TICKETS.issue()
        expires = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expires_at))
        body = json.dumps(
            {"ticket": ticket, "expiresAt": expires, "ttlSeconds": 30},
            separators=(",", ":"),
        ).encode()
        self._send(200, body)

    def _handle_websocket(self, parsed) -> None:
        ticket = parse_qs(parsed.query).get("ticket", [""])[0]
        if self.headers.get("Origin") not in ALLOWED_ORIGINS:
            self._send(403, b'{"code":"ORIGIN_REJECTED"}')
            return
        if self.headers.get("Upgrade", "").lower() != "websocket":
            self._send(400, b'{"code":"BAD_REQUEST"}')
            return
        if not TICKETS.consume(ticket):
            self._send(401, b'{"code":"UNAUTHORIZED"}')
            return
        key = self.headers.get("Sec-WebSocket-Key", "")
        accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
        ).decode()
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        self.close_connection = True


class StubServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = False

    def __init__(self, instance_id: str, started_at: str) -> None:
        super().__init__(("127.0.0.1", 0), Handler)
        self.instance_id = instance_id
        self.health = {
            "status": "ok",
            "appVersion": "0.1.0",
            "protocolVersion": "0.1.0",
            "pid": os.getpid(),
            "startedAt": started_at,
        }


def atomic_descriptor(path: Path, descriptor: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(descriptor, stream, separators=(",", ":"))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    identity = subprocess.check_output(["whoami.exe"], text=True).strip()
    result = subprocess.run(
        [
            "icacls.exe",
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"{identity}:(F)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"icacls failed: {result.stdout} {result.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    args = parser.parse_args()

    instance_id = os.environ.get("HQAGENT_INSTANCE_ID") or str(uuid.uuid4())
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    server = StubServer(instance_id, started_at)
    port = server.server_address[1]
    descriptor_path = args.runtime_dir / "hub.json"
    descriptor = {
        "schemaVersion": 1,
        "instanceId": instance_id,
        "port": port,
        "token": TOKEN,
        "pid": os.getpid(),
        "baseUrl": f"http://127.0.0.1:{port}",
        "appVersion": "0.1.0",
        "protocolVersion": "0.1.0",
        "startedAt": started_at,
    }
    atomic_descriptor(descriptor_path, descriptor)
    args.ready_file.write_text(
        json.dumps({"port": port, "token": TOKEN, "pid": os.getpid()}),
        encoding="utf-8",
    )

    stop = threading.Event()

    def request_stop(_signum, _frame) -> None:
        stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
        descriptor_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

