#!/usr/bin/env python3
"""Localhost Cargo sparse-registry bridge for Schannel-restricted sandboxes.

Python's OpenSSL HTTPS path fetches crates.io while Cargo only talks plain HTTP
to 127.0.0.1. This helper is for local verification and is not part of the app.
"""

from __future__ import annotations

import argparse
import http.server
import json
from pathlib import Path
import urllib.error
import urllib.request


class RegistryBridge(http.server.ThreadingHTTPServer):
    def __init__(self, cache: Path) -> None:
        super().__init__(("127.0.0.1", 0), Handler)
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/index/config.json":
            port = self.server.server_address[1]
            body = json.dumps(
                {
                    "dl": f"http://127.0.0.1:{port}/api/v1/crates",
                    "api": "https://crates.io",
                },
                separators=(",", ":"),
            ).encode()
            self._send(200, body, "application/json")
            return

        if self.path.startswith("/index/"):
            relative = self.path.removeprefix("/index/")
            self._proxy(
                f"https://index.crates.io/{relative}",
                self.server.cache / "index" / relative,
                "text/plain",
            )
            return

        prefix = "/api/v1/crates/"
        if self.path.startswith(prefix) and self.path.endswith("/download"):
            parts = self.path.removeprefix(prefix).split("/")
            if len(parts) == 3 and parts[2] == "download":
                crate, version, _ = parts
                self._proxy(
                    f"https://static.crates.io/crates/{crate}/{crate}-{version}.crate",
                    self.server.cache / "crates" / crate / f"{crate}-{version}.crate",
                    "application/gzip",
                )
                return
        self._send(404, b"not found", "text/plain")

    def _proxy(self, url: str, cache_path: Path, content_type: str) -> None:
        try:
            if cache_path.is_file():
                body = cache_path.read_bytes()
            else:
                request = urllib.request.Request(url, headers={"User-Agent": "hqagent-cargo-bridge/1"})
                with urllib.request.urlopen(request, timeout=90) as response:
                    body = response.read()
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
                temporary.write_bytes(body)
                temporary.replace(cache_path)
            self._send(200, body, content_type)
        except urllib.error.HTTPError as error:
            self._send(error.code, str(error).encode(), "text/plain")
        except Exception as error:  # local diagnostic bridge
            self._send(502, str(error).encode(), "text/plain")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    args = parser.parse_args()
    server = RegistryBridge(args.cache)
    args.ready_file.write_text(str(server.server_address[1]), encoding="ascii")
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
