"""Local browser sessions are separate from the legacy Hub bearer token."""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time
from http.cookies import SimpleCookie
from pathlib import Path
from threading import RLock

from core.errors import HubError


COOKIE_NAME = "hqagent_local_session"


class LocalBrowserAuth:
    def __init__(self, *, code_ttl: float = 600, session_ttl: int = 30 * 86400,
                 storage_path: Path | None = None, renewal_interval: int = 3600,
                 max_sessions: int = 20) -> None:
        self.code_ttl = code_ttl
        self.session_ttl = session_ttl
        self._code_hash: str | None = None
        self._code_expiry = 0.0
        self._attempts = 0
        self.renewal_interval = min(renewal_interval, session_ttl)
        self.max_sessions = max_sessions
        self._lock = RLock()
        if storage_path is not None:
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            # Create with restrictive permissions before SQLite opens it. SQLite's
            # rollback journal inherits the database permissions on POSIX.
            fd = os.open(storage_path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
            if os.name != "nt":
                storage_path.chmod(0o600)
        self._database = sqlite3.connect(
            str(storage_path) if storage_path is not None else ":memory:",
            check_same_thread=False,
        )
        with self._database:
            self._database.execute("CREATE TABLE IF NOT EXISTS browser_sessions "
                                   "(digest TEXT PRIMARY KEY, expires_at REAL NOT NULL)")
            self._prune(time.time())

    def _prune(self, now: float) -> None:
        self._database.execute(
            "DELETE FROM browser_sessions WHERE expires_at <= ? OR expires_at > ?",
            (now, now + self.session_ttl),
        )

    def close(self) -> None:
        with self._lock:
            self._database.close()

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
        now = time.time()
        with self._lock, self._database:
            self._prune(now)
            self._database.execute("INSERT INTO browser_sessions VALUES (?, ?)",
                                   (self._digest(secret), now + self.session_ttl))
            # rowid preserves creation order even when an older session renews.
            self._database.execute(
                "DELETE FROM browser_sessions WHERE rowid NOT IN "
                "(SELECT rowid FROM browser_sessions ORDER BY rowid DESC LIMIT ?)",
                (self.max_sessions,),
            )
        return secret

    def expires_at(self, cookie: str | None) -> float | None:
        """Authenticate and renew at most once per interval, using durable wall time.

        Read the store each time so logout/revocation cannot resurrect a cached
        session, including when another local auth instance shares the store.
        """
        if not cookie:
            return None
        digest = self._digest(cookie)
        now = time.time()
        with self._lock, self._database:
            row = self._database.execute(
                "SELECT expires_at FROM browser_sessions WHERE digest = ?", (digest,)
            ).fetchone()
            if row is None:
                return None
            expiry = row[0]
            if not now < expiry <= now + self.session_ttl:
                self._database.execute("DELETE FROM browser_sessions WHERE digest = ?", (digest,))
                return None
            if now - (expiry - self.session_ttl) >= self.renewal_interval:
                expiry = now + self.session_ttl
                self._database.execute(
                    "UPDATE browser_sessions SET expires_at = ? WHERE digest = ?", (expiry, digest)
                )
            return expiry

    def valid(self, cookie: str | None) -> bool:
        return self.expires_at(cookie) is not None

    def logout(self, cookie: str | None) -> None:
        if cookie:
            with self._lock, self._database:
                self._database.execute("DELETE FROM browser_sessions WHERE digest = ?",
                                       (self._digest(cookie),))

    def revoke_sessions(self) -> None:
        with self._lock, self._database:
            self._database.execute("DELETE FROM browser_sessions")

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
