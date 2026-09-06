from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from core.errors import HubError
from storage.database import Database, Transaction


def request_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class IdempotencyRepository:
    def __init__(self, database: Database, ttl_hours: int = 24) -> None:
        self.database = database
        self.ttl_hours = ttl_hours

    def execute(
        self,
        key: str | None,
        route: str,
        request_value: Any,
        operation: Callable[[Transaction], Any],
    ) -> Any:
        if not key:
            with self.database.transaction() as transaction:
                return operation(transaction)
        digest = request_hash(request_value)
        now = datetime.now(timezone.utc)
        with self.database.transaction() as transaction:
            row = transaction.connection.execute(
                "SELECT request_hash,response_json,expires_at FROM idempotency_records WHERE key=? AND route=?",
                (key, route),
            ).fetchone()
            if row and datetime.fromisoformat(row[2].replace("Z", "+00:00")) > now:
                if row[0] != digest:
                    raise HubError(
                        "IDEMPOTENCY_MISMATCH",
                        "相同 Idempotency-Key 不能用于不同请求体",
                        detail={"route": route},
                    )
                return json.loads(row[1])
            if row:
                transaction.connection.execute(
                    "DELETE FROM idempotency_records WHERE key=? AND route=?", (key, route)
                )
            result = operation(transaction)
            response_json = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
            expires_at = (now + timedelta(hours=self.ttl_hours)).isoformat().replace("+00:00", "Z")
            transaction.connection.execute(
                "INSERT INTO idempotency_records(key,route,request_hash,response_json,expires_at) VALUES(?,?,?,?,?)",
                (key, route, digest, response_json, expires_at),
            )
            return result

