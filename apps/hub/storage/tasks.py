"""任务与节点仓储。

表在 migrations.py 里早就建好了（tasks / task_nodes），缺的只是读写层。

`payload_json` 存整个 View，其余列是**查询投影**——一律从 View 派生，
不接受调用方单独传，否则两处会漂。`task_nodes.resolve_source` 单独成列，
因为「为什么用了这个 Agent」是要按任务列出来给用户看的（施工方案 §6.4 要求持久化）。
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from protocol.generated.python import TaskNodeView, TaskSummaryView

from core.errors import HubError
from storage.database import Database, Transaction


class TaskRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, task: TaskSummaryView) -> TaskSummaryView:
        with self.database.transaction() as transaction:
            self.save_in_transaction(transaction, task)
        return task

    @staticmethod
    def save_in_transaction(transaction: Transaction, task: TaskSummaryView) -> TaskSummaryView:
        payload = task.model_dump_json(by_alias=True, exclude_none=True)
        transaction.connection.execute(
            "INSERT INTO tasks(task_id,workspace_id,profile_id,objective,status,source,"
            "payload_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(task_id) DO UPDATE SET "
            "status=excluded.status, payload_json=excluded.payload_json, "
            "updated_at=excluded.updated_at",
            (
                task.id,
                task.workspace_id,
                task.profile_id,
                task.objective,
                str(task.status),
                str(task.source),
                payload,
                task.created_at,
                task.updated_at,
            ),
        )
        return task

    def get(self, task_id: str) -> TaskSummaryView:
        with self.database.locked_connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        if row is None:
            raise HubError("NOT_FOUND", f"任务不存在：{task_id}")
        return TaskSummaryView.model_validate_json(row[0])

    def list(self, query: dict[str, Any]) -> tuple[Sequence[TaskSummaryView], int]:
        clauses: list[str] = []
        params: list[Any] = []
        if query.get("status"):
            clauses.append("status=?")
            params.append(str(query["status"]))
        if query.get("workspaceId"):
            clauses.append("workspace_id=?")
            params.append(query["workspaceId"])
        if query.get("search"):
            clauses.append("objective LIKE ?")
            params.append(f"%{query['search']}%")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

        page = max(int(query.get("page") or 1), 1)
        page_size = min(max(int(query.get("pageSize") or 50), 1), 200)
        with self.database.locked_connection() as connection:
            total = int(
                connection.execute(f"SELECT COUNT(*) FROM tasks{where}", params).fetchone()[0]
            )
            rows = connection.execute(
                f"SELECT payload_json FROM tasks{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
        return [TaskSummaryView.model_validate_json(row[0]) for row in rows], total

    def save_node(self, node: TaskNodeView) -> TaskNodeView:
        with self.database.transaction() as transaction:
            self.save_node_in_transaction(transaction, node)
        return node

    @staticmethod
    def save_node_in_transaction(transaction: Transaction, node: TaskNodeView) -> TaskNodeView:
        payload = node.model_dump_json(by_alias=True, exclude_none=True)
        transaction.connection.execute(
            "INSERT INTO task_nodes(node_id,task_id,role_id,resolved_agent,resolve_source,"
            "status,payload_json) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(node_id) DO UPDATE SET "
            "resolved_agent=excluded.resolved_agent, resolve_source=excluded.resolve_source, "
            "status=excluded.status, payload_json=excluded.payload_json",
            (
                node.id,
                node.task_id,
                str(node.role_id),
                node.resolved_agent_id,
                str(node.resolve_source),
                str(node.status),
                payload,
            ),
        )
        return node

    def list_nodes(self, task_id: str) -> Sequence[TaskNodeView]:
        with self.database.locked_connection() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM task_nodes WHERE task_id=? ORDER BY rowid", (task_id,)
            ).fetchall()
        return [TaskNodeView.model_validate_json(row[0]) for row in rows]
