"""Team Profile 仓储。

表在 migrations.py 里早就建好了（`team_profiles`），一直没人写读写层——
W3 只做解析不做存储，W1 当时把 TeamProfilePort 留成了 UnavailablePort。

只用 `team_profiles` 一张表，`payload_json` 存整个 TeamProfileView。
不拆 `role_bindings`：绑定关系是 Profile 的内部结构，没有任何查询需要按
role 反查 profile；拆开只会带来两张表同步的问题，而 Profile 的写入是整体替换。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from protocol.generated.python import TeamProfileView

from core.errors import HubError
from storage.database import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class TeamProfileRepository:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.pi_instances = lambda: set()

    def list(self) -> list[TeamProfileView]:
        with self.database.locked_connection() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM team_profiles ORDER BY scope, name"
            ).fetchall()
        return [TeamProfileView.model_validate_json(row[0]) for row in rows]

    def get(self, profile_id: str) -> TeamProfileView:
        with self.database.locked_connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM team_profiles WHERE profile_id=?", (profile_id,)
            ).fetchone()
        if row is None:
            raise HubError("NOT_FOUND", f"Team Profile 不存在：{profile_id}")
        return TeamProfileView.model_validate_json(row[0])

    def save(self, value: TeamProfileView) -> TeamProfileView:
        from runtime.execution_selection import reject_pi_fallbacks
        reject_pi_fallbacks(value.model_dump(mode='json', by_alias=True), self.pi_instances())
        payload = value.model_dump_json(by_alias=True, exclude_none=True)
        with self.database.transaction() as transaction:
            transaction.connection.execute(
                "INSERT INTO team_profiles(profile_id,name,scope,payload_json,updated_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(profile_id) DO UPDATE SET "
                "name=excluded.name, scope=excluded.scope, "
                "payload_json=excluded.payload_json, updated_at=excluded.updated_at",
                (value.id, value.name, str(value.scope), payload, _now()),
            )
        return value

    def delete(self, profile_id: str) -> None:
        with self.database.transaction() as transaction:
            transaction.connection.execute(
                "DELETE FROM team_profiles WHERE profile_id=?", (profile_id,)
            )

    def default_global(self) -> TeamProfileView | None:
        for profile in self.list():
            if str(profile.scope) == "global" and profile.is_default:
                return profile
        return None
