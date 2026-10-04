from __future__ import annotations

import asyncio
import json
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from protocol.generated.python import EventPage, HubEvent

from core.constants import PROTOCOL_VERSION
from core.errors import HubError
from storage.database import Database, Transaction


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class EventDraft:
    aggregate_type: str
    aggregate_id: str
    type: str
    payload: Any
    event_id: str | None = None
    occurred_at: str | None = None
    task_id: str | None = None
    node_id: str | None = None
    role_id: str | None = None
    agent_instance_id: str | None = None
    adapter_id: str | None = None


class EventBroker:
    def __init__(self) -> None:
        self._subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[HubEvent]]] = set()
        self._lock = threading.Lock()

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[HubEvent]]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[HubEvent] = asyncio.Queue()
        item = (loop, queue)
        with self._lock:
            self._subscribers.add(item)
        try:
            yield queue
        finally:
            with self._lock:
                self._subscribers.discard(item)

    def publish(self, event: HubEvent) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers)
        for loop, queue in subscribers:
            if loop.is_closed():
                continue
            loop.call_soon_threadsafe(queue.put_nowait, event)


class EventStore:
    def __init__(self, database: Database, broker: EventBroker | None = None) -> None:
        self.database = database
        self.broker = broker or EventBroker()

    def append(self, transaction: Transaction, draft: EventDraft) -> tuple[HubEvent, bool]:
        event_id = draft.event_id or f"evt_{uuid.uuid4().hex}"
        occurred_at = draft.occurred_at or _timestamp()
        payload_json = json.dumps(draft.payload, ensure_ascii=False, separators=(",", ":"))
        try:
            cursor = transaction.connection.execute(
                "INSERT INTO events(event_id, aggregate_type, aggregate_id, type, payload_json, envelope_json, occurred_at) "
                "VALUES(?,?,?,?,?,'{}',?)",
                (event_id, draft.aggregate_type, draft.aggregate_id, draft.type, payload_json, occurred_at),
            )
        except Exception as exc:
            if "UNIQUE constraint failed: events.event_id" not in str(exc):
                raise
            row = transaction.connection.execute(
                "SELECT envelope_json FROM events WHERE event_id=?", (event_id,)
            ).fetchone()
            return HubEvent.model_validate_json(row[0]), False

        raw = {
            "eventId": event_id,
            "seq": int(cursor.lastrowid),
            "occurredAt": occurred_at,
            "aggregateType": draft.aggregate_type,
            "aggregateId": draft.aggregate_id,
            "type": draft.type,
            "payload": draft.payload,
            "protocolVersion": PROTOCOL_VERSION,
            "taskId": draft.task_id,
            "nodeId": draft.node_id,
            "roleId": draft.role_id,
            "agentInstanceId": draft.agent_instance_id,
            "adapterId": draft.adapter_id,
        }
        event = HubEvent.model_validate({key: value for key, value in raw.items() if value is not None})
        envelope_json = event.model_dump_json(by_alias=True, exclude_none=True)
        transaction.connection.execute(
            "UPDATE events SET envelope_json=? WHERE seq=?", (envelope_json, event.seq)
        )
        transaction.after_commit(lambda: self.broker.publish(event))
        return event, True

    def latest_seq(self) -> int:
        with self.database.locked_connection() as connection:
            row = connection.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()
            return int(row[0])

    def oldest_seq(self) -> int | None:
        with self.database.locked_connection() as connection:
            row = connection.execute("SELECT MIN(seq) FROM events").fetchone()
            return int(row[0]) if row[0] is not None else None

    @staticmethod
    def _cursor_expired_detail(bounds, snapshot_url):
        return {
            "snapshotUrl": snapshot_url,
            "oldestAvailableSeq": int(bounds[0]) if bounds[0] is not None else None,
            "latestSeq": int(bounds[1]) if bounds[1] is not None else 0,
        }

    def cursor_expired_detail(self, snapshot_url="/api/v1/bootstrap") -> dict[str, Any]:
        """One consistent watermark observation for HTTP and WS recovery errors."""
        with self.database.locked_connection() as connection:
            bounds = connection.execute("SELECT MIN(seq), MAX(seq) FROM events").fetchone()
            return self._cursor_expired_detail(bounds, snapshot_url)

    def page(self, after: int, limit: int) -> EventPage:
        if after < 0:
            raise HubError("VALIDATION_FAILED", "after 必须大于等于 0")
        with self.database.locked_connection() as connection:
            oldest_row = connection.execute("SELECT MIN(seq), MAX(seq) FROM events").fetchone()
            oldest = int(oldest_row[0]) if oldest_row[0] is not None else None
            if oldest is not None and after < oldest - 1:
                raise HubError(
                    "EVENT_CURSOR_EXPIRED",
                    "事件游标已过期，请重新获取 bootstrap Snapshot",
                    detail=self._cursor_expired_detail(oldest_row, "/api/v1/bootstrap"),
                )
            rows = connection.execute(
                "SELECT envelope_json FROM events WHERE seq>? ORDER BY seq LIMIT ?",
                (after, limit + 1),
            ).fetchall()
        has_more = len(rows) > limit
        events = [HubEvent.model_validate_json(row[0]) for row in rows[:limit]]
        last_seq = events[-1].seq if events else after
        return EventPage.model_validate(
            {"events": events, "lastSeq": last_seq, "hasMore": has_more}
        )

    def prune_before(self, seq: int) -> int:
        with self.database.transaction() as transaction:
            cursor = transaction.connection.execute("DELETE FROM events WHERE seq<?", (seq,))
            return int(cursor.rowcount)
