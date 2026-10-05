"""W3 所需仓储的 W1 侧实现。

W3 的 handoff 第 4 条：「W1 当前 core.ports 是 API Handler Port，没有面向 W3 的
事务化 Task/Session/Approval Repository Port。集成时需由 W1 在其路径提供薄适配器，
复用现有 Database/EventStore；**不要在 W3 再建 SQLite 或第二套事件表**。」

所以这里全部复用 storage/ 已有的 Database 和 EventStore，一张新表都不建——
表在 migrations.py 里早就有了（sessions / approvals / events），缺的只是读写层。
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from protocol.generated.python import AgentTaskSpec, ApprovalView, HubEvent, SessionView

from orchestrator.domain import AgentCandidate, RuntimeEventDraft
from storage.database import Database
from storage.events import EventDraft, EventStore
from storage.execution_state import ExecutionStateRepository


class EventSink:
    """RuntimeEventSink：把 W3 的事件草稿写进 W1 的事件表。

    RuntimeEventDraft 和 storage.EventDraft 字段一一对应，这里只做搬运。
    每次 append 开一个事务——W3 的调用点本来就是一个个独立的状态迁移，
    合并成大事务反而会让「事件已发但状态没落库」的窗口变长。
    """

    def __init__(self, database: Database, events: EventStore) -> None:
        self.database = database
        self.events = events

    async def append(self, draft: RuntimeEventDraft) -> HubEvent | None:
        with self.database.transaction() as transaction:
            event = self.append_in_transaction(transaction, draft)
        return event

    def append_in_transaction(self, transaction: Any, draft: RuntimeEventDraft) -> HubEvent:
        event, _created = self.events.append(
            transaction,
            EventDraft(
                aggregate_type=draft.aggregate_type,
                aggregate_id=draft.aggregate_id,
                type=draft.type,
                payload=draft.payload,
                task_id=draft.task_id,
                node_id=draft.node_id,
                role_id=draft.role_id,
                agent_instance_id=draft.agent_instance_id,
                adapter_id=draft.adapter_id,
            ),
        )
        return event

    async def load_task_events(self, task_id: str, after_seq: int = 0) -> Sequence[HubEvent]:
        # taskId 只存在 envelope_json 里，events 表没有这一列，所以用 json_extract。
        # 同时匹配 aggregate_id：任务自身的事件 aggregateType=task、aggregateId=taskId；
        # 而 session / approval 聚合的事件 aggregateId 不是 taskId，
        # 只能靠 envelope 里的 taskId 找回来。恢复要的是「这个任务的全部事件」，
        # 少一类就重建不出完整状态。
        #
        # 代价：json_extract 走不了索引。当前每个任务的事件量是有界的（节点数级别），
        # 可以接受；将来事件量上来要加一个真实的 task_id 列 + 索引，
        # 不要在这里堆查询技巧。
        with self.database.locked_connection() as connection:
            rows = connection.execute(
                "SELECT envelope_json FROM events "
                "WHERE seq>? AND (json_extract(envelope_json, '$.taskId')=? "
                "  OR (aggregate_type='task' AND aggregate_id=?)) "
                "ORDER BY seq",
                (after_seq, task_id, task_id),
            ).fetchall()
        return [HubEvent.model_validate_json(row[0]) for row in rows]


class SessionRepository:
    """SessionRepositoryPort：sessions 表的读写。

    payload_json 存整个 SessionView，另外把查询要用到的字段拆成列。
    拆出来的列是**查询投影**，不是第二份事实——写入时一律从 SessionView 派生，
    不接受调用方单独传。
    """

    def __init__(self, database: Database) -> None:
        self.database = database
        self.execution_state = ExecutionStateRepository(database)

    async def get(self, session_id: str) -> SessionView | None:
        with self.database.locked_connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
        return SessionView.model_validate_json(row[0]) if row else None

    async def save(self, session: SessionView) -> None:
        payload = session.model_dump_json(by_alias=True, exclude_none=True)
        with self.database.transaction() as transaction:
            transaction.connection.execute(
                "INSERT INTO sessions(session_id,task_id,node_id,workspace_id,role_id,"
                "agent_instance_id,external_session_id,purpose,parent_session_id,"
                "reuse_policy,status,payload_json,last_used_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(session_id) DO UPDATE SET "
                "task_id=excluded.task_id, node_id=excluded.node_id, "
                "external_session_id=excluded.external_session_id, "
                "status=excluded.status, payload_json=excluded.payload_json, "
                "last_used_at=excluded.last_used_at",
                (
                    session.id,
                    session.task_id or "",
                    session.node_id,
                    session.workspace_id,
                    str(session.role_id),
                    session.agent_instance_id,
                    session.external_session_id,
                    str(session.purpose),
                    session.parent_session_id,
                    str(session.reuse_policy),
                    str(session.status),
                    payload,
                    session.last_used_at,
                ),
            )

    async def list(self, query: dict[str, Any]) -> Sequence[SessionView]:
        clauses: list[str] = []
        params: list[Any] = []
        if query.get("status"):
            clauses.append("status=?")
            params.append(str(query["status"]))
        if query.get("workspaceId"):
            clauses.append("workspace_id=?")
            params.append(query["workspaceId"])
        if query.get("taskId"):
            clauses.append("(task_id=? OR session_id IN (SELECT json_extract(payload_json, '$.sessionId') FROM task_nodes WHERE task_id=?))")
            params.extend([query["taskId"], query["taskId"]])
        if query.get("agentInstanceId"):
            clauses.append("agent_instance_id=?")
            params.append(query["agentInstanceId"])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self.database.locked_connection() as connection:
            rows = connection.execute(
                f"SELECT payload_json FROM sessions{where} ORDER BY last_used_at DESC",
                params,
            ).fetchall()
        return [SessionView.model_validate_json(row[0]) for row in rows]

    async def save_spec(self, session_id: str, spec: AgentTaskSpec) -> None:
        self.execution_state.put(
            f"session_spec:{session_id}",
            spec.model_dump(mode="json", by_alias=True, exclude_none=True),
        )

    async def get_spec(self, session_id: str) -> AgentTaskSpec | None:
        value = self.execution_state.get(f"session_spec:{session_id}")
        return AgentTaskSpec.model_validate(value) if value else None


class ApprovalRepository:
    """ApprovalRepositoryPort：approvals 表的读写。

    expiresAt 归 Hub 独占（裁决 D19），Adapter 不参与——所以这里存什么就是什么，
    不做任何过期重算。过期判定只在 security/approvals.py 一处。
    """

    def __init__(self, database: Database) -> None:
        self.database = database

    async def get(self, approval_id: str) -> ApprovalView | None:
        with self.database.locked_connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM approvals WHERE approval_id=?", (approval_id,)
            ).fetchone()
        return ApprovalView.model_validate_json(row[0]) if row else None

    async def save(self, approval: ApprovalView) -> None:
        payload = approval.model_dump_json(by_alias=True, exclude_none=True)
        with self.database.transaction() as transaction:
            transaction.connection.execute(
                "INSERT INTO approvals(approval_id,task_id,node_id,action,payload_json,"
                "status,decided_at) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(approval_id) DO UPDATE SET "
                "status=excluded.status, payload_json=excluded.payload_json, "
                "decided_at=excluded.decided_at",
                (
                    approval.id,
                    approval.task_id,
                    approval.node_id,
                    str(approval.action),
                    payload,
                    str(approval.status),
                    approval.decided_at,
                ),
            )

    async def compare_and_set(
        self,
        approval: ApprovalView,
        *,
        expected_status: str,
    ) -> bool:
        payload = approval.model_dump_json(by_alias=True, exclude_none=True)
        with self.database.transaction() as transaction:
            cursor = transaction.connection.execute(
                "UPDATE approvals SET status=?,payload_json=?,decided_at=? "
                "WHERE approval_id=? AND status=?",
                (
                    str(approval.status),
                    payload,
                    approval.decided_at,
                    approval.id,
                    expected_status,
                ),
            )
        return int(cursor.rowcount) == 1

    async def list(self, query: dict[str, Any]) -> Sequence[ApprovalView]:
        clauses: list[str] = []
        params: list[Any] = []
        if query.get("status"):
            clauses.append("status=?")
            params.append(str(query["status"]))
        if query.get("taskId"):
            clauses.append("task_id=?")
            params.append(query["taskId"])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        def read():
            with self.database.locked_connection() as connection:
                return connection.execute(
                    f"SELECT payload_json FROM approvals{where} ORDER BY approval_id", params
                ).fetchall()
        rows = await self.database.read_async(read)
        return [ApprovalView.model_validate_json(row[0]) for row in rows]


class AdapterDirectory:
    """AdapterDirectoryPort：把 W2 的 AdapterManager 接到 W3 的编排上。

    W3 只按 Agent Instance ID 取 Adapter，永远不认厂商名——这是四层解耦的
    最后一道关口。`adapter_for` 里一旦出现 if claude / if codex，解耦就破了。
    """

    def __init__(self, manager: Any) -> None:
        self.manager = manager

    async def list_candidates(self) -> Sequence[AgentCandidate]:
        agents = await self.manager.list_agents()
        return [AgentCandidate.from_view(item) for item in agents]

    def adapter_for(self, agent_instance_id: str) -> Any:
        # 实例 ID 形如 local.<adapterId>.default，由 AdapterManager 生成。
        # 这里只做 ID 解析，不认识任何具体厂商。
        parts = agent_instance_id.split(".")
        adapter_id = parts[1] if len(parts) >= 2 else agent_instance_id
        adapter = self.manager.get(adapter_id)
        if adapter is None:
            raise LookupError(f"没有注册的 Adapter 能承接实例 {agent_instance_id}")
        return adapter
