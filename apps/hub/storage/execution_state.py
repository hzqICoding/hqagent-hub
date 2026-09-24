from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from storage.database import Database, Transaction


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ExecutionStateRepository:
    """Durable execution documents backed by the existing ``hub_state`` table."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self, key: str) -> dict[str, Any] | None:
        with self.database.locked_connection() as connection:
            row = connection.execute(
                "SELECT value_json FROM hub_state WHERE key=?", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def put(
        self,
        key: str,
        value: dict[str, Any],
        transaction: Transaction | None = None,
    ) -> None:
        if transaction is not None:
            self._put(transaction, key, value)
            return
        with self.database.transaction() as current:
            self._put(current, key, value)

    def delete(self, key: str, transaction: Transaction | None = None) -> None:
        if transaction is not None:
            transaction.connection.execute("DELETE FROM hub_state WHERE key=?", (key,))
            return
        with self.database.transaction() as current:
            current.connection.execute("DELETE FROM hub_state WHERE key=?", (key,))

    def list_prefix(self, prefix: str) -> dict[str, dict[str, Any]]:
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self.database.locked_connection() as connection:
            rows = connection.execute(
                "SELECT key,value_json FROM hub_state WHERE key LIKE ? ESCAPE '\\' ORDER BY key",
                (f"{escaped}%",),
            ).fetchall()
        return {str(row[0]): json.loads(row[1]) for row in rows}

    @staticmethod
    def _put(transaction: Transaction, key: str, value: dict[str, Any]) -> None:
        transaction.connection.execute(
            "INSERT INTO hub_state(key,value_json,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, "
            "updated_at=excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False, separators=(",", ":")), _now()),
        )
