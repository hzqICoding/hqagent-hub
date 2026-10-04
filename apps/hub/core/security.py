from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from protocol.generated.python import WsTicket

from core.constants import WS_TICKET_TTL_SECONDS


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_startup_token() -> str:
    return secrets.token_urlsafe(32)


def token_matches(actual: str, expected: str) -> bool:
    return hmac.compare_digest(actual.encode("utf-8"), expected.encode("utf-8"))


@dataclass(slots=True)
class _TicketRecord:
    digest: bytes
    expires_at: datetime
    purpose: str
    features: bool = False
    cursor_owner: str | None = None


class WsTicketStore:
    def __init__(self) -> None:
        self._records: dict[bytes, _TicketRecord] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _digest(ticket: str) -> bytes:
        return hashlib.sha256(ticket.encode("utf-8")).digest()

    def issue(self, purpose: str = "events", *, features: bool = False, cursor_owner: str | None = None) -> WsTicket:
        now = utc_now()
        expires_at = now + timedelta(seconds=WS_TICKET_TTL_SECONDS)
        ticket = secrets.token_urlsafe(32)
        digest = self._digest(ticket)
        with self._lock:
            self._purge_locked(now)
            self._records[digest] = _TicketRecord(digest, expires_at, purpose, features, cursor_owner)
        return WsTicket.model_validate(
            {
                "ticket": ticket,
                "expiresAt": expires_at.isoformat().replace("+00:00", "Z"),
                "ttlSeconds": WS_TICKET_TTL_SECONDS,
            }
        )

    def consume(self, ticket: str, purpose: str = "events") -> bool:
        return self.consume_record(ticket, purpose) is not None

    def consume_record(self, ticket: str, purpose: str = "events") -> _TicketRecord | None:
        now = utc_now()
        digest = self._digest(ticket)
        with self._lock:
            self._purge_locked(now)
            record = self._records.pop(digest, None)
        return record if record and record.purpose == purpose and record.expires_at > now else None

    def _purge_locked(self, now: datetime) -> None:
        expired = [key for key, record in self._records.items() if record.expires_at <= now]
        for key in expired:
            self._records.pop(key, None)

