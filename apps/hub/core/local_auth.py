"""Local browser sessions are separate from the legacy Hub bearer token."""
from __future__ import annotations

import hashlib
import secrets
import time
from http.cookies import SimpleCookie

from core.errors import HubError


COOKIE_NAME = "hqagent_local_session"


class LocalBrowserAuth:
    def __init__(self, *, code_ttl: float = 600, session_ttl: int = 86400) -> None:
        self.code_ttl = code_ttl
        self.session_ttl = session_ttl
        self._code_hash: str | None = None
        self._code_expiry = 0.0
        self._attempts = 0
        self._sessions: dict[str, float] = {}

    def issue_code(self, value: str | None = None) -> str:
        code = value or secrets.token_hex(6)
        self._code_hash = self._digest(code)
        self._code_expiry = time.monotonic() + self.code_ttl
        self._attempts = 0
        return code

    def exchange(self, code: str) -> str:
        if self._attempts >= 10:
            raise HubError("UNAUTHORIZED", "连接码尝试过多，请在本机重新生成连接码")
        self._attempts += 1
        if (
            self._code_hash is None
            or time.monotonic() >= self._code_expiry
            or not secrets.compare_digest(self._code_hash, self._digest(code.strip()))
        ):
            raise HubError("UNAUTHORIZED", "本地连接码无效、已使用或已过期")
        self._code_hash = None
        secret = secrets.token_urlsafe(32)
        now = time.monotonic()
        self._sessions = {k: v for k, v in self._sessions.items() if v > now}
        self._sessions[self._digest(secret)] = now + self.session_ttl
        return secret

    def valid(self, cookie: str | None) -> bool:
        return bool(cookie and self._sessions.get(self._digest(cookie), 0) > time.monotonic())

    def logout(self, cookie: str | None) -> None:
        if cookie:
            self._sessions.pop(self._digest(cookie), None)

    def cookie_from_headers(self, headers: dict[str, str]) -> str | None:
        parsed = SimpleCookie()
        try:
            parsed.load(headers.get("cookie", ""))
        except Exception:
            return None
        return parsed[COOKIE_NAME].value if COOKIE_NAME in parsed else None

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
