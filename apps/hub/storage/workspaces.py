"""工作区仓储。

表在 migrations.py 里早就有了（workspaces），migration 2 补了 last_opened_at。

**只存持久事实**：id / path / name / vcs / defaultProfileId / lastOpenedAt。
`branch`、`isClean`、`memoryDirPresent`、`capabilities` 一律不存——它们是文件系统的
当前状态，存下来立刻就过期（用户在 VS Code 里切个分支，库里的值就错了）。
这几个由 WorkspaceService 读时现算。
"""
from __future__ import annotations

from collections.abc import Sequence

from core.errors import HubError
from storage.database import Database


class WorkspaceRecord:
    """库里的一行。刻意不是 WorkspaceView——View 里有一半字段是现算的。"""

    __slots__ = ("id", "path", "name", "vcs", "default_profile_id", "last_opened_at")

    def __init__(
        self,
        id: str,
        path: str,
        name: str,
        vcs: str,
        default_profile_id: str | None,
        last_opened_at: str | None,
    ) -> None:
        self.id = id
        self.path = path
        self.name = name
        self.vcs = vcs
        self.default_profile_id = default_profile_id
        self.last_opened_at = last_opened_at


_COLUMNS = "workspace_id, path, name, vcs, default_profile_id, last_opened_at"


def _row(values: tuple) -> WorkspaceRecord:
    return WorkspaceRecord(*values)


class WorkspaceRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list(self, search: str | None = None, limit: int | None = None) -> Sequence[WorkspaceRecord]:
        params: list[object] = []
        where = ""
        if search:
            where = " WHERE (name LIKE ? OR path LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        sql = f"SELECT {_COLUMNS} FROM workspaces{where} ORDER BY name"
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self.database.locked_connection() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [_row(tuple(r)) for r in rows]

    def get(self, workspace_id: str) -> WorkspaceRecord:
        with self.database.locked_connection() as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM workspaces WHERE workspace_id=?", (workspace_id,)
            ).fetchone()
        if row is None:
            raise HubError("NOT_FOUND", f"工作区不存在：{workspace_id}")
        return _row(tuple(row))

    def find_by_path(self, path: str) -> WorkspaceRecord | None:
        with self.database.locked_connection() as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM workspaces WHERE path=?", (path,)
            ).fetchone()
        return _row(tuple(row)) if row else None

    def save(self, record: WorkspaceRecord) -> WorkspaceRecord:
        with self.database.transaction() as transaction:
            transaction.connection.execute(
                "INSERT INTO workspaces(workspace_id,path,name,vcs,default_profile_id,last_opened_at) "
                "VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(workspace_id) DO UPDATE SET "
                "path=excluded.path, name=excluded.name, vcs=excluded.vcs, "
                "default_profile_id=excluded.default_profile_id, "
                "last_opened_at=excluded.last_opened_at",
                (
                    record.id,
                    record.path,
                    record.name,
                    record.vcs,
                    record.default_profile_id,
                    record.last_opened_at,
                ),
            )
        return record

    def delete(self, workspace_id: str) -> None:
        with self.database.transaction() as transaction:
            transaction.connection.execute(
                "DELETE FROM workspaces WHERE workspace_id=?", (workspace_id,)
            )
