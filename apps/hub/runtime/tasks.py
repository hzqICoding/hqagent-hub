"""Durable task application service for the real Hub composition."""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from protocol.generated.python import (
    AdapterStreamEnd,
    ApprovalDecision,
    ApprovalResponseInput,
    ApprovalStatus,
    CreateTaskInput,
    DangerousAction,
    NodeStatus,
    PageResult,
    RiskLevel,
    SessionPurpose,
    SessionReusePolicy,
    SessionStatus,
    TaskActionInput,
    TaskDetailView,
    TaskNodeView,
    TaskStatus,
    TaskSummaryView,
    TeamProfileView,
)

from core.errors import HubError
from orchestrator.domain import ProfileSnapshot, ResolutionGap, RuntimeEventDraft
from orchestrator.errors import AdapterStartFailedError, ApprovalError, OrchestrationError
from orchestrator.runtime import NodeDispatchRequest
from security.approvals import ApprovalRequest
from security.worktrees import WorktreeSpec
from storage.execution_state import ExecutionStateRepository
from storage.idempotency import IdempotencyRepository
from runtime.review_evidence import acceptance_prompt, freeze_evidence, verify_evidence


# Keep legacy v1 defaults; local v2 scenes always supply an explicit workflow.
DEFAULT_WORKFLOW_ROLES = ("general_implementer", "reviewer")
TERMINAL_TASK_STATES = {
    TaskStatus.SUCCEEDED.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED.value,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _failure_text(failure: Any, fallback: object) -> str:
    kind = _text(getattr(failure, "kind", "agent_error"))
    message = getattr(failure, "message", None) or str(fallback)
    text = f"{kind}: {message}"
    paths = getattr(failure, "violation_paths", None)
    if paths:
        text += "；越界路径：" + ", ".join(str(path) for path in paths[:5])
    missing = getattr(failure, "missing_capabilities", None)
    if missing:
        text += "；缺少能力：" + ", ".join(_text(item) for item in missing)
    return text


def _purpose(role_id: str) -> SessionPurpose:
    return {
        "architect": SessionPurpose.ARCHITECT,
        "planner": SessionPurpose.ARCHITECT,
        "general_implementer": SessionPurpose.IMPLEMENT,
        "frontend_implementer": SessionPurpose.IMPLEMENT,
        "developer": SessionPurpose.IMPLEMENT,
        "reviewer": SessionPurpose.REVIEW,
        "tester": SessionPurpose.TEST,
        "deployer": SessionPurpose.DEPLOY,
        "integrator": SessionPurpose.INTEGRATE,
    }.get(role_id, SessionPurpose.ADHOC)


class TaskService:
    @staticmethod
    def _current_inputs():
        from runtime.attachments.service import CURRENT_INPUTS
        return [v.model_dump(mode='json', by_alias=True) for v in CURRENT_INPUTS.get()]

    available = True
    unavailable_reason = None

    def __init__(
        self,
        repository: Any,
        runtime: Any,
        directory: Any,
        profiles: Any,
        events: Any,
        workspaces: Any,
        worktrees: Any = None,
        approval_coordinator: Any = None,
    ) -> None:
        self.repository = repository
        self.runtime = runtime
        self.directory = directory
        self.profiles = profiles
        self.events = events
        self.workspaces = workspaces
        self.worktrees = worktrees
        self.approval_coordinator = approval_coordinator
        database = getattr(repository, "database", None)
        if database is None:
            raise ValueError("TaskService requires a persistent TaskRepository")
        self.database = database
        self.state = ExecutionStateRepository(database)
        self.idempotency = IdempotencyRepository(database, ttl_hours=None)
        self._pumps: dict[str, asyncio.Task[None]] = {}
        self._outcomes: dict[str, Any] = {}
        self._dispatching: set[str] = set()
        self._task_locks: dict[str, asyncio.Lock] = {}
        self.execution_commit_observer = None

    async def list_tasks(self, query: dict[str, Any]) -> PageResult:
        items, total = self.repository.list(query)
        page = max(int(query.get("page") or 1), 1)
        page_size = min(max(int(query.get("pageSize") or 50), 1), 200)
        return PageResult.model_validate(
            {
                "items": [item.model_dump(mode="json", by_alias=True, exclude_none=True) for item in items],
                "total": total,
                "page": page,
                "pageSize": page_size,
                "hasMore": page * page_size < total,
            }
        )

    async def get_task(self, task_id: str) -> TaskDetailView:
        summary = self.repository.get(task_id)
        nodes = list(self.repository.list_nodes(task_id))
        events = await self.events.load_task_events(task_id)
        spec = self._task_spec(task_id)
        raw = summary.model_dump(mode="json", by_alias=True, exclude_none=True)
        raw.update(
            {
                "nodes": [node.model_dump(mode="json", by_alias=True, exclude_none=True) for node in nodes],
                "artifacts": [],
                "events": [event.model_dump(mode="json", by_alias=True, exclude_none=True) for event in events],
                "lastEventSeq": events[-1].seq if events else 0,
                "allowedPaths": spec["request"].get("allowedPaths"),
                "readFirst": spec["request"].get("readFirst"),
                "acceptance": spec["request"].get("acceptance"),
                "requiresApproval": spec["request"].get("requiresApproval"),
                "failureReason": spec.get("failureReason"),
                "result": spec.get("result"),
            }
        )
        last_worktree = next((node for node in reversed(nodes) if node.worktree_path and node.id in (spec.get('worktrees') or {})), None)
        last_worktree = last_worktree or next((node for node in reversed(nodes) if node.worktree_path), None)
        if last_worktree:
            raw["worktreePath"] = last_worktree.worktree_path
            raw["branch"] = last_worktree.branch
        return TaskDetailView.model_validate(raw)

    async def create_task(
        self,
        value: CreateTaskInput,
        idempotency_key: str | None,
    ) -> TaskDetailView:
        profile = await self._profile_for(value)
        workspace = await self._workspace_for(value.workspace_id)
        workflow = self._workflow(value)
        self._assert_workflow_supported(workflow, workspace)
        request_raw = value.model_dump(mode="json", by_alias=True, exclude_none=True)

        def persist(transaction: Any) -> dict[str, str]:
            task_id = f"task_{uuid.uuid4().hex[:12]}"
            self._persist_new_task(transaction, task_id, value, profile, workspace, workflow)
            return {"taskId": task_id}

        receipt = self.idempotency.execute(
            idempotency_key,
            "/api/v1/tasks",
            request_raw,
            persist,
        )
        task_id = str(receipt["taskId"])
        async with self._lock(task_id):
            task = self.repository.get(task_id)
            state = self._task_spec(task_id)
            if _text(task.status) == TaskStatus.QUEUED.value and not state.get("blockedByParent"):
                await self._advance(task_id)
        return await self.get_task(task_id)

    async def act(
        self,
        task_id: str,
        value: TaskActionInput,
        idempotency_key: str | None,
    ) -> TaskDetailView:
        self.repository.get(task_id)
        request_raw = value.model_dump(mode="json", by_alias=True, exclude_none=True)

        def persist(transaction: Any) -> dict[str, str]:
            action_id = f"action_{uuid.uuid4().hex}"
            self.state.put(
                f"task_action:{action_id}",
                {
                    "actionId": action_id,
                    "taskId": task_id,
                    "request": request_raw,
                    "status": "pending",
                    "createdAt": _now(),
                },
                transaction,
            )
            return {"taskId": task_id, "actionId": action_id}

        receipt = self.idempotency.execute(
            idempotency_key,
            f"/api/v1/tasks/{task_id}/actions",
            request_raw,
            persist,
        )
        action_id = str(receipt["actionId"])
        async with self._lock(task_id):
            action_state = self.state.get(f"task_action:{action_id}") or {}
            if action_state.get("status") == "completed":
                return await self.get_task(str(action_state.get("resultTaskId") or task_id))
            if action_state.get("status") == "failed":
                raise HubError(
                    "TASK_ACTION_INVALID",
                    str(action_state.get("error") or "任务动作此前执行失败"),
                    detail={"actionId": action_id},
                )
            if action_state.get("status") == "executing":
                raise HubError(
                    "TASK_ACTION_INVALID",
                    "上次动作在完成回执前中断，结果未知；请先核对任务状态再发起新动作",
                    detail={"actionId": action_id, "recoveryRequired": True},
                )
            action_state["status"] = "executing"
            self.state.put(f"task_action:{action_id}", action_state)
            try:
                result_task_id = await self._execute_action(task_id, value, action_id)
            except Exception as error:
                action_state.update({"status": "failed", "error": str(error), "completedAt": _now()})
                self.state.put(f"task_action:{action_id}", action_state)
                raise
            action_state.update(
                {"status": "completed", "resultTaskId": result_task_id, "completedAt": _now()}
            )
            self.state.put(f"task_action:{action_id}", action_state)
        return await self.get_task(result_task_id)

    async def recover_pending(self) -> tuple[str, ...]:
        """Make interrupted work explicit; never replay unknown side effects."""
        return await self._quarantine_nonterminal_tasks(
            "Hub 重启后无法确认先前执行是否仍有副作用，请人工继续或重试",
            invalidated_by="restart_recovery",
        )

    async def _quarantine_nonterminal_tasks(
        self,
        reason: str,
        *,
        invalidated_by: str,
    ) -> tuple[str, ...]:
        recovered: list[str] = []
        page = 1
        page_size = 200
        while True:
            items, total = self.repository.list({"page": page, "pageSize": page_size})
            for task in items:
                status = _text(task.status)
                active_status = status in {
                    TaskStatus.QUEUED.value,
                    TaskStatus.RUNNING.value,
                    TaskStatus.WAITING_APPROVAL.value,
                }
                if not active_status and status != TaskStatus.PAUSED.value:
                    continue
                spec = self._task_spec(task.id)
                if status == TaskStatus.PAUSED.value and not spec.get("recoveryRequired"):
                    continue
                if status == TaskStatus.QUEUED.value and spec.get("blockedByParent"):
                    continue
                nodes = list(self.repository.list_nodes(task.id))
                interrupted_nodes = [
                    node
                    for node in nodes
                    if _text(node.status) in {
                        NodeStatus.RUNNING.value,
                        NodeStatus.WAITING_APPROVAL.value,
                        NodeStatus.RESOLVING.value,
                    }
                ]
                invalidated_sessions = await self._invalidate_interrupted_sessions(task.id)
                invalidate = None
                should_invalidate_approvals = (
                    status in {TaskStatus.WAITING_APPROVAL.value, TaskStatus.PAUSED.value}
                    or task.pending_approval_id is not None
                )
                if self.approval_coordinator is not None and should_invalidate_approvals:
                    invalidate = getattr(
                        self.approval_coordinator,
                        "invalidate_task_pending",
                        None,
                    )
                    if invalidate is not None:
                        await invalidate(
                            task.id,
                            reason=reason,
                            invalidated_by=invalidated_by,
                        )
                has_legacy_residue = bool(
                    interrupted_nodes or invalidated_sessions or task.pending_approval_id
                )
                if status == TaskStatus.PAUSED.value and not has_legacy_residue:
                    continue
                for node in interrupted_nodes:
                    self.repository.save_node(
                        node.model_copy(
                            update={
                                "status": NodeStatus.FAILED,
                                "error": reason,
                                "completed_at": _now(),
                            }
                        )
                    )
                self.repository.save(
                    task.model_copy(
                        update={
                            "status": TaskStatus.PAUSED,
                            "pending_approval_id": None,
                            "updated_at": _now(),
                        }
                    )
                )
                spec.update({"recoveryRequired": True, "failureReason": reason})
                self.state.put(f"task_spec:{task.id}", spec)
                await self._emit(
                    task.id,
                    "task.status_changed",
                    {"taskId": task.id, "to": "paused", "reason": reason},
                )
                recovered.append(task.id)
            if page * page_size >= total:
                break
            page += 1
        return tuple(recovered)

    async def _invalidate_interrupted_sessions(self, task_id: str) -> int:
        sessions = getattr(self.runtime, "sessions", None)
        repository = getattr(sessions, "repository", None)
        if repository is None:
            return 0
        invalidated = 0
        for session in await repository.list({"taskId": task_id}):
            if _text(session.status) != SessionStatus.ACTIVE.value:
                continue
            await repository.save(
                session.model_copy(
                    update={
                        "status": SessionStatus.INVALID,
                        "is_valid": False,
                        "last_used_at": _now(),
                    }
                )
            )
            invalidated += 1
        return invalidated

    async def shutdown(self) -> None:
        pumps = tuple(self._pumps.values())
        for pump in pumps:
            pump.cancel()
        if pumps:
            await asyncio.gather(*pumps, return_exceptions=True)
        await self._quarantine_nonterminal_tasks(
            "Hub 已停止；原生执行结果未确认，任务需要恢复核对",
            invalidated_by="hub_shutdown",
        )

    async def expire_approvals(self) -> None:
        if self.approval_coordinator is None:
            return
        for approval_id in await self.approval_coordinator.expire_due():
            approval = await self.approval_coordinator.repository.get(approval_id)
            if approval is None:
                continue
            async with self._lock(approval.task_id):
                task = self.repository.get(approval.task_id)
                if _text(task.status) in TERMINAL_TASK_STATES:
                    continue
                await self._cancel(task.id)
                current = self.repository.get(task.id)
                reason = "工具审批已过期，本轮停止；不会自动放行"
                if _text(current.status) == TaskStatus.CANCELLED.value:
                    await self._fail_node(task.id, self._node(task.id, approval.node_id), reason)
                else:
                    spec = self._task_spec(task.id)
                    spec.update({"recoveryRequired": True, "failureReason": reason + "；原生执行停止状态待核实"})
                    self.state.put(f"task_spec:{task.id}", spec)
                    self.repository.save(current.model_copy(update={"status": TaskStatus.PAUSED, "updated_at": _now()}))

    async def _execute_action(
        self,
        task_id: str,
        value: TaskActionInput,
        action_id: str,
    ) -> str:
        task = self.repository.get(task_id)
        action = _text(value.action)
        status = _text(task.status)
        if action == "cancel":
            await self._cancel(task_id)
            return task_id
        if action == "pause":
            spec = self._task_spec(task_id)
            running = any(
                _text(node.status) in {NodeStatus.RUNNING.value, NodeStatus.WAITING_APPROVAL.value}
                for node in self.repository.list_nodes(task_id)
            )
            if running:
                spec["pauseRequested"] = True
                spec["controlEvidence"] = {"kind": "pause_requested", "observedAt": _now()}
                self.state.put(f"task_spec:{task_id}", spec)
                await self._emit(
                    task_id,
                    "task.status_changed",
                    {"taskId": task_id, "to": status, "reason": "pause_requested；将在节点边界暂停"},
                )
            else:
                self._record_control_evidence(task_id, "node_boundary_paused")
                self.repository.save(task.model_copy(update={"status": TaskStatus.PAUSED, "updated_at": _now()}))
                await self._emit(task_id, "task.status_changed", {"taskId": task_id, "to": "paused"})
            return task_id
        if action == "resume":
            if status != TaskStatus.PAUSED.value:
                raise HubError("TASK_ACTION_INVALID", "只有 paused 任务可以继续")
            spec = self._task_spec(task_id)
            spec.update({"pauseRequested": False, "recoveryRequired": False, "failureReason": None})
            self.state.put(f"task_spec:{task_id}", spec)
            for node in self.repository.list_nodes(task_id):
                if _text(node.status) == NodeStatus.FAILED.value:
                    self.repository.save_node(self._reset_node(node))
            self.repository.save(task.model_copy(update={"status": TaskStatus.QUEUED, "updated_at": _now()}))
            await self._emit(task_id, "task.status_changed", {"taskId": task_id, "to": "queued"})
            await self._advance(task_id)
            self._record_control_evidence(task_id, "supervisor_resumed")
            return task_id
        if action == "append_instruction":
            if not value.instruction:
                raise HubError("VALIDATION_FAILED", "append_instruction 必须带 instruction")
            child = await self._create_child(
                task_id,
                objective=value.instruction,
                idempotency_key=f"internal:{action_id}",
                blocked=status not in TERMINAL_TASK_STATES,
            )
            return child.id
        if action == "retry":
            if status in TERMINAL_TASK_STATES:
                child = await self._create_child(
                    task_id,
                    objective=task.objective,
                    idempotency_key=f"internal:{action_id}",
                    blocked=False,
                )
                return child.id
            failed = [node for node in self.repository.list_nodes(task_id) if _text(node.status) == NodeStatus.FAILED.value]
            if value.node_id:
                failed = [node for node in failed if node.id == value.node_id]
            if not failed:
                raise HubError("TASK_ACTION_INVALID", "没有可重试的失败节点")
            for node in failed:
                self.repository.save_node(self._reset_node(node))
            self.repository.save(task.model_copy(update={"status": TaskStatus.QUEUED, "updated_at": _now()}))
            await self._advance(task_id)
            return task_id
        raise HubError("TASK_ACTION_INVALID", f"不支持的动作：{action}")

    async def _create_child(
        self,
        parent_task_id: str,
        *,
        objective: str,
        idempotency_key: str,
        blocked: bool,
    ) -> TaskDetailView:
        parent_spec = self._task_spec(parent_task_id)
        raw = dict(parent_spec["request"])
        raw.update({"objective": objective, "parentTaskId": parent_task_id})
        resume_sessions: dict[str, str] = {}
        for node in self.repository.list_nodes(parent_task_id):
            if node.session_id and _text(node.status) == NodeStatus.SUCCEEDED.value:
                resume_sessions[_text(node.role_id)] = node.session_id
        native = getattr(self.repository.database, "native_service", None)
        if native is not None:
            for role_id, session_id in (parent_spec["request"].get("resumeSessions") or {}).items():
                try:
                    native.row(session_id, session=True)
                except HubError as error:
                    if error.code != "NOT_FOUND":
                        raise
                else:
                    # Native retry must retain its exact imported binding, even
                    # when the preceding node was cancelled rather than succeeded.
                    resume_sessions[role_id] = session_id
        raw["resumeSessions"] = resume_sessions or None
        child_value = CreateTaskInput.model_validate(raw)
        profile = TeamProfileView.model_validate(parent_spec["profile"])
        workspace = dict(parent_spec["workspace"])
        workflow = self._workflow(child_value)
        request_raw = child_value.model_dump(mode="json", by_alias=True, exclude_none=True)

        def persist(transaction: Any) -> dict[str, str]:
            child_id = f"task_{uuid.uuid4().hex[:12]}"
            self._persist_new_task(
                transaction,
                child_id,
                child_value,
                profile,
                workspace,
                workflow,
                blocked_by_parent=parent_task_id if blocked else None,
            )
            child_spec = self.state.get(f'task_spec:{child_id}')
            child_spec['inputAttachments'] = parent_spec.get('inputAttachments', [])
            self.state.put(f'task_spec:{child_id}', child_spec, transaction)
            return {"taskId": child_id}

        receipt = self.idempotency.execute(
            idempotency_key,
            f"/internal/tasks/{parent_task_id}/child",
            request_raw,
            persist,
        )
        child_id = str(receipt["taskId"])
        if not blocked:
            async with self._lock(child_id):
                await self._advance(child_id)
        return await self.get_task(child_id)

    def _persist_new_task(
        self,
        transaction: Any,
        task_id: str,
        value: CreateTaskInput,
        profile: Any,
        workspace: dict[str, Any],
        workflow: tuple[tuple[str, tuple[str, ...]], ...],
        *,
        blocked_by_parent: str | None = None,
    ) -> None:
        now = _now()
        task = TaskSummaryView.model_validate(
            {
                "id": task_id,
                "objective": value.objective,
                "workspaceId": value.workspace_id,
                "workspaceName": workspace["name"],
                "profileId": profile.id,
                "profileName": profile.name,
                "status": TaskStatus.QUEUED.value,
                "source": _text(value.source) if value.source else "desktop",
                "createdAt": now,
                "updatedAt": now,
                "parentTaskId": value.parent_task_id,
            }
        )
        self.repository.save_in_transaction(transaction, task)
        workflow_rows: list[dict[str, Any]] = []
        role_to_node = {role_id: f"node_{uuid.uuid4().hex[:12]}" for role_id, _ in workflow}
        for role_id, deps in workflow:
            node_id = role_to_node[role_id]
            original_acceptance = role_id == "reviewer" and str(value.review_mode) == "original_planner"
            execution_role = "planner" if original_acceptance else role_id
            node = TaskNodeView.model_validate(
                {
                    "id": node_id,
                    "taskId": task_id,
                    "roleId": execution_role,
                    "phase": "acceptance" if role_id == "reviewer" else "execution",
                    "reviewSourceNodeId": role_to_node.get("planner") if original_acceptance else None,
                    "resolvedAgentId": "",
                    "resolvedAgentName": "",
                    "resolveSource": "manual",
                    "status": NodeStatus.PENDING.value,
                }
            )
            self.repository.save_node_in_transaction(transaction, node)
            workflow_rows.append(
                {"nodeId": node_id, "roleId": execution_role,
                 "phase": "acceptance" if role_id == "reviewer" else "execution",
                 "dependsOn": [role_to_node[item] for item in deps]}
            )
        self.state.put(
            f"task_spec:{task_id}",
            {
                "request": value.model_dump(mode="json", by_alias=True, exclude_none=True),
                "profile": profile.model_dump(mode="json", by_alias=True, exclude_none=True),
                "workspace": workspace,
                "workflow": workflow_rows,
                "pauseRequested": False,
                "blockedByParent": blocked_by_parent,
                "worktrees": {},
                "nodeResults": {},
                "createdAt": now,
                "inputAttachments": self._current_inputs(),
            },
            transaction,
        )
        self.events.append_in_transaction(
            transaction,
            RuntimeEventDraft(
                type="task.created",
                aggregate_type="task",
                aggregate_id=task_id,
                task_id=task_id,
                payload={
                    "taskId": task_id,
                    "objective": value.objective,
                    "workspaceId": value.workspace_id,
                    "profileId": profile.id,
                    "parentTaskId": value.parent_task_id,
                },
            ),
        )
        if self.execution_commit_observer is not None:
            # Optional persistence observer; no execution policy or state change.
            # It seals the remote recovery witness before a new Task can dispatch.
            self.execution_commit_observer(transaction)

    async def _advance(self, task_id: str) -> None:
        task = self.repository.get(task_id)
        if _text(task.status) in {TaskStatus.PAUSED.value, *TERMINAL_TASK_STATES}:
            return
        spec = self._task_spec(task_id)
        if spec.get("pauseRequested"):
            self._record_control_evidence(task_id, "node_boundary_paused")
            self.repository.save(task.model_copy(update={"status": TaskStatus.PAUSED, "updated_at": _now()}))
            return
        nodes = {node.id: node for node in self.repository.list_nodes(task_id)}
        for item in spec["workflow"]:
            node = nodes[item["nodeId"]]
            if _text(node.status) != NodeStatus.PENDING.value:
                continue
            if not all(_text(nodes[dep].status) == NodeStatus.SUCCEEDED.value for dep in item["dependsOn"]):
                continue
            try:
                self._dispatching.add(task_id)
                await self._dispatch_node(task_id, node, item["roleId"], spec)
            except (HubError, OrchestrationError) as error:
                # Preparation failures belong to this node, not its completed predecessor.
                await self._fail_node(task_id, self._node(task_id, node.id), str(error))
            finally:
                self._dispatching.discard(task_id)
            return
        if nodes and all(_text(node.status) == NodeStatus.SUCCEEDED.value for node in nodes.values()):
            self.repository.save(task.model_copy(update={"status": TaskStatus.SUCCEEDED, "updated_at": _now()}))
            await self._emit(task_id, "task.completed", {"taskId": task_id, "to": "succeeded"})

    async def _dispatch_node(
        self,
        task_id: str,
        node: TaskNodeView,
        role_id: str,
        spec: dict[str, Any],
    ) -> None:
        value = CreateTaskInput.model_validate(spec["request"])
        profile = TeamProfileView.model_validate(spec["profile"])
        workspace = dict(spec["workspace"])
        self._assert_can_write(role_id, workspace)
        original_acceptance = str(node.phase) == "acceptance" and role_id == "planner" and str(value.review_mode) == "original_planner"
        original_agent_id = None
        objective = self._node_objective(task_id, value.objective)
        native = getattr(self.repository.database, "native_service", None)
        native_session_id = (value.resume_sessions or {}).get(role_id)
        if native is not None and native_session_id:
            await native.prepare_session(native_session_id, task_id, node.id, objective)
        if original_acceptance:
            execution_path, resume_session_id, original_agent_id, objective = await self._planner_acceptance_inputs(task_id, node, spec, value)
        else:
            execution_path = await self._prepare_execution_path(task_id, node, role_id, workspace, spec)
            resume_session_id = (value.resume_sessions or {}).get(role_id)
        implementation_agent_id, review_context_paths = self._review_context(task_id, role_id)
        candidates = await self.directory.list_candidates()
        if original_agent_id:
            candidates = [candidate for candidate in candidates if candidate.instance_id == original_agent_id]
        snapshot = ProfileSnapshot.from_view(profile)
        role_options = (value.role_executions or {}).get(role_id)
        role_policy = self.runtime.permissions.role_policy(role_id)
        continued_allowed_paths = (
            tuple(execution_path["allowed_paths"])
            if execution_path and "allowed_paths" in execution_path
            else None
        )
        requested_approvals = tuple(_text(item) for item in (value.requires_approval or ()))
        effective_approvals = tuple(
            dict.fromkeys([*role_policy.default_requires_approval, *requested_approvals])
        )
        request = NodeDispatchRequest(
            task_id=task_id,
            node_id=node.id,
            workspace_id=value.workspace_id,
            workspace_name=workspace["name"],
            role_id=role_id,
            objective=objective,
            agents=tuple(candidates),
            allowed_paths=continued_allowed_paths
            if continued_allowed_paths is not None
            else (tuple(value.allowed_paths) if value.allowed_paths else None),
            read_first=tuple(value.read_first or ()),
            acceptance=tuple(value.acceptance or ()),
            requires_approval=effective_approvals,
            task_override_agent_id=original_agent_id or (value.role_overrides or {}).get(role_id),
            global_profile=snapshot if profile.scope == "global" else None,
            workspace_profile=snapshot if profile.scope == "workspace" else None,
            session_purpose=_purpose(role_id),
            reuse_policy=SessionReusePolicy.RESUME_EXPLICIT if resume_session_id else SessionReusePolicy.NEW_SESSION,
            resume_session_id=resume_session_id,
            worktree_path=execution_path["path"] if execution_path else None,
            branch=(execution_path.get("branch") or None) if execution_path else None,
            base_commit=(execution_path.get("base_commit") or None) if execution_path else None,
            implementation_agent_id=implementation_agent_id,
            review_context_paths=review_context_paths,
            model_id=role_options.model_id_ if role_options else None,
            reasoning_effort=role_options.reasoning_effort if role_options else None,
            role_instructions=role_options.instructions if role_options else None,
            input_attachments=tuple(spec.get('inputAttachments', ())),
        )
        try:
            outcome = await self.runtime.dispatch(request)
        except AdapterStartFailedError as error:
            await self._fail_node(task_id, node, _failure_text(error.failure, error))
            return
        except OrchestrationError as error:
            await self._fail_node(task_id, node, str(error))
            return
        if isinstance(outcome, ResolutionGap):
            await self._fail_node(task_id, node, outcome.reason)
            return
        node = self._node(task_id, node.id)  # evidence metadata was persisted during preparation
        self.repository.save_node(
            node.model_copy(
                update={
                    "status": NodeStatus.RUNNING,
                    "resolved_agent_id": outcome.resolution.agent.instance_id,
                    "resolved_agent_name": outcome.resolution.agent.display_name,
                    "resolve_source": outcome.resolution.source,
                    "is_fallback": outcome.resolution.is_fallback,
                    "fallback_reason": outcome.resolution.fallback_reason,
                    "session_id": outcome.session.id,
                    "external_session_id": outcome.session.external_session_id,
                    "worktree_path": outcome.worktree_path,
                    "branch": request.branch,
                    "started_at": _now(),
                }
            )
        )
        task = self.repository.get(task_id)
        self.repository.save(
            task.model_copy(
                update={
                    "status": TaskStatus.RUNNING,
                    "current_role": role_id,
                    "current_agent": outcome.resolution.agent.display_name,
                    "updated_at": _now(),
                }
            )
        )
        self._start_pump(task_id, node.id, outcome)

    async def _planner_acceptance_inputs(self, task_id: str, node: TaskNodeView,
                                         state: dict, value: CreateTaskInput):
        nodes = list(self.repository.list_nodes(task_id))
        planner = next((n for n in nodes if n.id == node.review_source_node_id), None)
        developer = next((n for n in reversed(nodes) if str(n.role_id) == "developer"), None)
        if (planner is None or str(planner.role_id) != "planner" or str(planner.phase) == "acceptance"
                or str(planner.status) != "succeeded" or not planner.session_id
                or developer is None or str(developer.status) != "succeeded"):
            raise HubError("SESSION_NOT_RESUMABLE", "原规划会话验收缺少成功的规划或实施节点")
        if planner.session_id == developer.session_id:
            raise HubError("SESSION_NOT_RESUMABLE", "验收不能复用实施者会话")
        repository = self.runtime.sessions.repository
        session = await repository.get(planner.session_id)
        if (session is None or session.agent_instance_id != planner.resolved_agent_id
                or session.external_session_id != planner.external_session_id):
            raise HubError("SESSION_NOT_RESUMABLE", "原规划会话身份与本轮规划节点不一致")
        continued = {**state, "request": {**state['request'],
                     "resumeSessions": {**(value.resume_sessions or {}), "planner": planner.session_id}}}
        execution_path = await self._continued_execution_path(task_id, node, "planner", state['workspace'], continued, read_only=True)
        worktree = (state.get('worktrees') or {}).get(developer.id)
        developer_spec = await repository.get_spec(developer.session_id)
        developer_session = await repository.get(developer.session_id)
        if (not worktree or developer_spec is None or developer_session is None
                or developer_spec.session_id != developer.session_id
                or developer_session.id != developer.session_id
                or str(developer_session.status) not in {'idle', 'closed'}
                or str(developer_spec.role_id) != 'developer'
                or str(developer_session.role_id) != 'developer'
                or developer_spec.read_only
                or developer_session.agent_instance_id != developer.resolved_agent_id
                or not developer.external_session_id
                or developer_session.external_session_id != developer.external_session_id
                or developer_session.workspace_id != value.workspace_id
                or developer_spec.task_id != developer_session.task_id
                or developer_spec.node_id != developer_session.node_id
                or (developer_session.task_id != task_id and (value.resume_sessions or {}).get('developer') != developer.session_id)
                or Path(worktree['repositoryPath']).resolve() != Path(state['workspace']['path']).resolve()
                or Path(worktree['worktreePath']).resolve() != Path(developer.worktree_path or '').resolve()
                or Path(developer_spec.worktree_path or '').resolve() != Path(worktree['worktreePath']).resolve()
                or developer_spec.workspace_id != value.workspace_id
                or developer_spec.base_commit != worktree['baseCommit']
                or developer_spec.branch != worktree['branch']):
            raise HubError("PATH_NOT_ALLOWED", "实施证据来源与实际工作树或Session规格不一致")
        packet = (state.get('acceptanceEvidence') or {}).get(node.id)
        try:
            if packet is None:
                events = list(await self.events.load_task_events(task_id))
                packet = await asyncio.to_thread(freeze_evidence, worktree, task_id, developer, planner,
                    (state.get('nodeResults') or {}).get(developer.id, {}), events, value.objective)
                state.setdefault('acceptanceEvidence', {})[node.id] = packet
                self.state.put(f'task_spec:{task_id}', state)
            else:
                await asyncio.to_thread(verify_evidence, packet)
        except (OSError, ValueError) as error:
            raise HubError('VALIDATION_FAILED', '无法完整读取实现源码作为验收证据') from error
        self.repository.save_node(node.model_copy(update={'review_evidence_id': packet['id']}))
        review_options = (value.role_executions or {}).get('reviewer')
        instructions = review_options.instructions if review_options and review_options.instructions else '按原方案检查实现和测试证据，说明结论与不足。'
        return execution_path, planner.session_id, planner.resolved_agent_id, acceptance_prompt(packet, instructions)

    async def _prepare_execution_path(
        self,
        task_id: str,
        node: TaskNodeView,
        role_id: str,
        workspace: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any] | None:
        path = workspace.get("path")
        if not path:
            return None
        policy = self.runtime.permissions.role_policy(role_id)
        continued = await self._continued_execution_path(
            task_id,
            node,
            role_id,
            workspace,
            state,
            read_only=policy.read_only,
        )
        if continued is not None:
            return continued
        if policy.read_only:
            inherited = self._inherit_worktree(task_id)
            return inherited or {"path": str(path), "branch": "", "base_commit": ""}
        if self.worktrees is None:
            raise HubError("FEATURE_UNAVAILABLE", "写任务需要 WorktreeManager")
        existing = (state.get("worktrees") or {}).get(node.id)
        if existing and Path(existing["worktreePath"]).is_dir():
            return {
                "path": existing["worktreePath"],
                "branch": existing["branch"],
                "base_commit": existing["baseCommit"],
            }
        repository = Path(path)
        base_commit = await self._head_commit(repository)
        branch = f"hq/{task_id}/{role_id}"
        worktree_path = self.worktrees.worktree_root / f"{task_id}-{role_id}"
        worktree = WorktreeSpec(repository, worktree_path, branch, base_commit)
        created = await asyncio.to_thread(self.worktrees.create, worktree)
        state.setdefault("worktrees", {})[node.id] = {
            "repositoryPath": str(repository),
            "worktreePath": str(created),
            "branch": branch,
            "baseCommit": base_commit,
        }
        self.state.put(f"task_spec:{task_id}", state)
        return {"path": str(created), "branch": branch, "base_commit": base_commit}

    async def _continued_execution_path(
        self,
        task_id: str,
        node: TaskNodeView,
        role_id: str,
        workspace: dict[str, Any],
        state: dict[str, Any],
        *,
        read_only: bool,
    ) -> dict[str, Any] | None:
        request = state.get("request") or {}
        resume_session_id = (request.get("resumeSessions") or {}).get(role_id)
        if not resume_session_id:
            return None
        sessions = getattr(getattr(self.runtime, "sessions", None), "repository", None)
        if sessions is None or not hasattr(sessions, "get_spec"):
            raise HubError(
                "SESSION_NOT_RESUMABLE",
                "恢复会话缺少持久 Session/AgentTaskSpec 仓储",
                detail={"sessionId": resume_session_id, "roleId": role_id},
            )
        session = await sessions.get(resume_session_id)
        original_spec = await sessions.get_spec(resume_session_id)
        workspace_id = request.get("workspaceId")
        if session is None or original_spec is None:
            raise HubError(
                "SESSION_NOT_RESUMABLE",
                "恢复会话或其持久执行规格不存在",
                detail={"sessionId": resume_session_id, "roleId": role_id},
            )
        if (
            _text(session.status) != "idle"
            or not session.is_valid
            or not session.external_session_id
        ):
            raise HubError(
                "SESSION_NOT_RESUMABLE",
                "恢复会话不是可用的 idle 原生会话",
                detail={"sessionId": resume_session_id, "roleId": role_id},
            )
        if (
            session.workspace_id != workspace_id
            or original_spec.workspace_id != workspace_id
        ):
            raise HubError(
                "SESSION_NOT_RESUMABLE",
                "恢复会话与当前 workspace 不一致",
                detail={"sessionId": resume_session_id, "roleId": role_id},
            )
        if (
            _text(session.role_id) != role_id
            or _text(original_spec.role_id) != role_id
            or original_spec.session_id != resume_session_id
        ):
            raise HubError(
                "SESSION_NOT_RESUMABLE",
                "恢复会话与当前角色或 Hub Session 不一致",
                detail={"sessionId": resume_session_id, "roleId": role_id},
            )
        if bool(original_spec.read_only) != read_only:
            raise HubError(
                "SESSION_NOT_RESUMABLE",
                "恢复会话的只读权限与当前角色不一致",
                detail={"sessionId": resume_session_id, "roleId": role_id},
            )
        if (
            "allowedPaths" in request
            and tuple(request.get("allowedPaths") or ()) != tuple(original_spec.allowed_paths)
        ):
            raise HubError(
                "SESSION_NOT_RESUMABLE",
                "当前任务显式 allowedPaths 与原会话权限范围不一致，请使用 New 会话",
                detail={"sessionId": resume_session_id, "roleId": role_id},
            )
        if not original_spec.worktree_path:
            raise HubError(
                "SESSION_NOT_RESUMABLE",
                "恢复会话缺少原执行路径",
                detail={"sessionId": resume_session_id, "roleId": role_id},
            )
        actual_path = Path(original_spec.worktree_path).resolve()
        if not actual_path.is_dir():
            raise HubError(
                "SESSION_NOT_RESUMABLE",
                "恢复会话的原执行路径已不存在",
                detail={"sessionId": resume_session_id, "roleId": role_id},
            )
        result: dict[str, Any] = {
            "path": str(actual_path),
            "branch": original_spec.branch or "",
            "base_commit": original_spec.base_commit or "",
            "allowed_paths": list(original_spec.allowed_paths),
        }
        if read_only:
            return result
        if self.worktrees is None:
            raise HubError("FEATURE_UNAVAILABLE", "写任务需要 WorktreeManager")
        try:
            actual_path.relative_to(self.worktrees.worktree_root.resolve())
        except ValueError as exc:
            raise HubError(
                "SESSION_NOT_RESUMABLE",
                "写会话的原执行路径不在受控 worktree 根目录",
                detail={"sessionId": resume_session_id, "roleId": role_id},
            ) from exc
        if not original_spec.branch or not original_spec.base_commit:
            raise HubError(
                "SESSION_NOT_RESUMABLE",
                "写会话缺少原 branch/baseCommit，不能安全验证累计改动",
                detail={"sessionId": resume_session_id, "roleId": role_id},
            )
        repository = Path(str(workspace["path"])).resolve()
        state.setdefault("worktrees", {})[node.id] = {
            "repositoryPath": str(repository),
            "worktreePath": str(actual_path),
            "branch": original_spec.branch,
            "baseCommit": original_spec.base_commit,
            "continuedFromSessionId": resume_session_id,
        }
        self.state.put(f"task_spec:{task_id}", state)
        return result

    def _start_pump(self, task_id: str, node_id: str, outcome: Any) -> None:
        self._outcomes[node_id] = outcome

        async def pump() -> None:
            adapter = self.directory.adapter_for(outcome.resolution.agent.instance_id)
            try:
                async for item in adapter.stream_events(outcome.session.id):
                    if isinstance(item, AdapterStreamEnd):
                        await self.runtime.handle_stream_end(outcome, item)
                        break
                    await self._forward(outcome, item)
                await self._complete_node(task_id, node_id)
            except asyncio.CancelledError:
                raise
            except AdapterStartFailedError as error:
                await self._fail_node(task_id, self._node(task_id, node_id), _failure_text(error.failure, error))
            except Exception as error:  # noqa: BLE001
                await self._fail_node(task_id, self._node(task_id, node_id), str(error))
            finally:
                self._pumps.pop(node_id, None)
                self._outcomes.pop(node_id, None)

        self._pumps[node_id] = asyncio.create_task(pump())

    async def _forward(self, outcome: Any, event: Any) -> None:
        event_type = str(getattr(event, "unified_type", getattr(event, "type", "agent.progress")))
        payload = event.payload
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump(mode="json", by_alias=True, exclude_none=True)
        if event_type == "approval.required":
            if self.approval_coordinator is None:
                raise HubError("FEATURE_UNAVAILABLE", "审批 Broker 尚未接入 TaskService")
            approval_id = str(payload.get("approvalId") or "")
            if not approval_id:
                raise HubError("VALIDATION_FAILED", "Adapter 审批事件缺少 approvalId")
            task = self.repository.get(outcome.task_id)
            def approval_active() -> bool:
                current_task = self.repository.get(outcome.task_id)
                current_node = self._node(outcome.task_id, outcome.node_id)
                return bool(
                    _text(current_task.status)
                    in {TaskStatus.RUNNING.value, TaskStatus.WAITING_APPROVAL.value}
                    and current_node is not None
                    and _text(current_node.status)
                    in {NodeStatus.RUNNING.value, NodeStatus.WAITING_APPROVAL.value}
                    and current_task.pending_approval_id in {None, approval_id}
                )

            approval = await self.approval_coordinator.request(
                ApprovalRequest(
                    approval_id=approval_id,
                    task_id=outcome.task_id,
                    task_objective=task.objective,
                    node_id=outcome.node_id,
                    request_agent_id=outcome.resolution.agent.instance_id,
                    request_agent_name=outcome.resolution.agent.display_name,
                    role_id=outcome.role_id,
                    action=DangerousAction(str(payload["action"])),
                    target_resource=str(payload.get("targetResource") or ""),
                    risk_level=RiskLevel(str(payload.get("riskLevel") or "high")),
                    external_request_id=getattr(event, "external_request_id", None)
                    or payload.get("externalRequestId"),
                ),
                active_check=approval_active,
            )
            if _text(approval.status) != "pending":
                return
            node = self._node(outcome.task_id, outcome.node_id)
            if node:
                self.repository.save_node(node.model_copy(update={"status": NodeStatus.WAITING_APPROVAL}))
            self.repository.save(
                task.model_copy(
                    update={
                        "status": TaskStatus.WAITING_APPROVAL,
                        "pending_approval_id": approval.id,
                        "updated_at": _now(),
                    }
                )
            )
            return
        await self.events.append(
            RuntimeEventDraft(
                type=event_type,
                aggregate_type="task",
                aggregate_id=outcome.task_id,
                payload=payload,
                task_id=outcome.task_id,
                node_id=outcome.node_id,
                role_id=outcome.role_id,
                agent_instance_id=outcome.resolution.agent.instance_id,
                adapter_id=outcome.resolution.agent.adapter_id,
            )
        )

    async def _complete_node(self, task_id: str, node_id: str) -> None:
        async with self._lock(task_id):
            node = self._node(task_id, node_id)
            outcome = self._outcomes.get(node_id)
            if node is None or outcome is None:
                return
            completion = await self.runtime.collect_result(outcome, complete_task=False,
                **({'keep_session_on_report': True} if str(node.phase) == 'acceptance' else {}))
            result = completion.result
            violations = tuple(completion.violation_paths or ())
            spec = self._task_spec(task_id)
            packet = (spec.get('acceptanceEvidence') or {}).get(node_id)
            if packet is not None:
                try:
                    await asyncio.to_thread(verify_evidence, packet)
                except HubError as error:
                    self.repository.save_node(node.model_copy(update={'review_verdict': 'insufficient_evidence'}))
                    await self._fail_node(task_id, self._node(task_id, node_id), str(error))
                    return
            worktree_raw = (spec.get("worktrees") or {}).get(node_id)
            if worktree_raw and self.worktrees is not None:
                validation = await asyncio.to_thread(
                    self.worktrees.validate,
                    WorktreeSpec(
                        Path(worktree_raw["repositoryPath"]),
                        Path(worktree_raw["worktreePath"]),
                        worktree_raw["branch"],
                        worktree_raw["baseCommit"],
                    ),
                    outcome.path_scope,
                )
                violations = tuple(dict.fromkeys([*violations, *validation.violation_paths]))
            succeeded = result.status == "done" and not violations
            changed_files = [item.path for item in (result.changed_files or [])]
            self.repository.save_node(
                node.model_copy(
                    update={
                        "status": NodeStatus.SUCCEEDED if succeeded else NodeStatus.FAILED,
                        "output_summary": result.summary,
                        "error": None if succeeded else result.summary,
                        "changed_files": changed_files,
                        "violation_paths": list(violations),
                        "completed_at": _now(),
                        "review_verdict": ({'done': 'passed', 'failed': 'changes_requested', 'blocked': 'insufficient_evidence'}.get(str(result.status))
                                           if str(node.phase) == 'acceptance' and not violations else None),
                    }
                )
            )
            result_raw = result.model_dump(mode="json", by_alias=True, exclude_none=True)
            spec.setdefault("nodeResults", {})[node_id] = result_raw
            spec["result"] = result_raw
            self.state.put(f"task_spec:{task_id}", spec)
            task = self.repository.get(task_id)
            if not succeeded:
                reason = (
                    "Agent 修改了授权范围之外的路径：" + ", ".join(violations)
                    if violations
                    else result.summary
                )
                spec["failureReason"] = reason
                self.state.put(f"task_spec:{task_id}", spec)
                self.repository.save(task.model_copy(update={"status": TaskStatus.FAILED, "updated_at": _now()}))
                await self._emit(task_id, "task.failed", {"taskId": task_id, "to": "failed", "reason": reason})
                await self._release_children(task_id)
                return
            if spec.get("pauseRequested"):
                spec["controlEvidence"] = {"kind": "node_boundary_paused", "observedAt": _now()}
                self.state.put(f"task_spec:{task_id}", spec)
                self.repository.save(task.model_copy(update={"status": TaskStatus.PAUSED, "updated_at": _now()}))
                await self._emit(task_id, "task.status_changed", {"taskId": task_id, "to": "paused"})
                return
            await self._advance(task_id)
            if _text(self.repository.get(task_id).status) == TaskStatus.SUCCEEDED.value:
                await self._release_children(task_id)

    async def _cancel(self, task_id: str) -> None:
        if self.approval_coordinator is None:
            await self._cancel_locked(task_id)
            return
        async with self.approval_coordinator.task_guard(task_id):
            await self.approval_coordinator.invalidate_task_pending_locked(
                task_id,
                reason="任务已取消，未决审批已由系统撤回",
                invalidated_by="task_cancelled",
            )
            await self._cancel_locked(task_id)

    async def _cancel_locked(self, task_id: str) -> None:
        current_task = self.repository.get(task_id)
        if _text(current_task.status) in TERMINAL_TASK_STATES:
            # Cancel is idempotent for an already-cancelled task and must never
            # rewrite a completed success/failure into cancelled.
            evidence = self.control_observation(task_id).get("controlEvidence") or {}
            if evidence.get("kind") not in {"cancellation", "adapter_confirmed"}:
                # A terminal label by itself isn't an Adapter stop receipt.
                # ALREADY_FINISHED is confirmed through CancellationOutcome;
                # previously confirmed cancellations retain that exact evidence.
                self._record_control_evidence(task_id, "terminal_unverified")
            return
        # Keep recovery flags, but do not mix receipts from separate attempts.
        self._record_control_evidence(task_id, "cancel_requested")
        running = [
            node
            for node in self.repository.list_nodes(task_id)
            if _text(node.status) in {NodeStatus.RUNNING.value, NodeStatus.WAITING_APPROVAL.value}
        ]
        if not running:
            self._record_control_evidence(task_id, "adapter_confirmed", cancellations=[])
            task = self.repository.get(task_id)
            self.repository.save(task.model_copy(update={
                "status": TaskStatus.CANCELLED, "pending_approval_id": None, "updated_at": _now()}))
            await self._emit(task_id, "task.status_changed", {"taskId": task_id, "to": "cancelled"})
            await self._release_children(task_id)
            return
        for node in running:
            outcome = self._outcomes.get(node.id)
            if outcome is None:
                self._record_control_evidence(task_id, "missing_execution_handle")
                reason = "缺少当前进程内执行句柄，无法确认原生执行已停止"
                self.repository.save_node(
                    node.model_copy(update={"status": NodeStatus.FAILED, "error": reason, "completed_at": _now()})
                )
                task = self.repository.get(task_id)
                self.repository.save(task.model_copy(update={
                    "status": TaskStatus.PAUSED, "pending_approval_id": None, "updated_at": _now()}))
                spec = self._task_spec(task_id)
                spec.update({"recoveryRequired": True, "failureReason": reason})
                self.state.put(f"task_spec:{task_id}", spec)
                return
            cancellation = await self.runtime.cancel(outcome, reason="用户取消任务")
            prior = self.control_observation(task_id).get("controlEvidence") or {}
            results = list(prior.get("cancellations", []))
            # Detail is display-only and can contain native provider output.
            # Persist only the structured cancellation facts for the bridge.
            result = getattr(cancellation, "result", None)
            if result is not None and hasattr(result, "model_dump"):
                results.append(result.model_dump(mode="json", by_alias=True, exclude_none=True,
                                                  exclude={"detail"}))
                self._record_control_evidence(task_id, "cancellation", cancellations=results,
                                              expectedHandles=len(running))
            else:
                self._record_control_evidence(task_id, "receipt_unavailable")
            if cancellation.task_status != TaskStatus.CANCELLED:
                task = self.repository.get(task_id)
                self.repository.save(task.model_copy(update={
                    "status": cancellation.task_status, "pending_approval_id": None, "updated_at": _now()}))
                return
            pump = self._pumps.pop(node.id, None)
            if pump:
                pump.cancel()
            self.repository.save_node(
                node.model_copy(update={"status": NodeStatus.CANCELLED, "completed_at": _now()})
            )
        task = self.repository.get(task_id)
        self.repository.save(task.model_copy(update={
            "status": TaskStatus.CANCELLED, "pending_approval_id": None, "updated_at": _now()}))
        await self._release_children(task_id)

    async def _release_children(self, parent_task_id: str) -> None:
        for key, child_spec in self.state.list_prefix("task_spec:").items():
            if child_spec.get("blockedByParent") != parent_task_id:
                continue
            child_id = key.split(":", 1)[1]
            child_spec["blockedByParent"] = None
            self.state.put(key, child_spec)
            async with self._lock(child_id):
                await self._advance(child_id)

    async def _fail_node(self, task_id: str, node: TaskNodeView | None, reason: str) -> None:
        if node is None:
            return
        self.repository.save_node(
            node.model_copy(update={"status": NodeStatus.FAILED, "error": reason, "completed_at": _now()})
        )
        task = self.repository.get(task_id)
        self.repository.save(task.model_copy(update={"status": TaskStatus.FAILED, "updated_at": _now()}))
        spec = self._task_spec(task_id)
        spec["failureReason"] = reason
        self.state.put(f"task_spec:{task_id}", spec)
        await self._emit(task_id, "task.failed", {"taskId": task_id, "to": "failed", "reason": reason})
        await self._release_children(task_id)

    async def _emit(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        await self.events.append(
            RuntimeEventDraft(
                type=event_type,
                aggregate_type="task",
                aggregate_id=task_id,
                payload=payload,
                task_id=task_id,
            )
        )

    async def _profile_for(self, value: CreateTaskInput) -> Any:
        if value.profile_id:
            return await self.profiles.get_profile(value.profile_id)
        for profile in await self.profiles.list_profiles():
            if profile.is_default:
                return profile
        raise HubError("VALIDATION_FAILED", "没有可用的 Team Profile，请先创建角色配置")

    async def _workspace_for(self, workspace_id: str) -> dict[str, Any]:
        for item in await self.workspaces.list_workspaces(None, None):
            if getattr(item, "id", None) != workspace_id:
                continue
            capabilities = getattr(item, "capabilities", None)
            return {
                "name": getattr(item, "name", workspace_id),
                "path": getattr(item, "path", None),
                "vcs": _text(getattr(item, "vcs", "none")),
                "can_write": bool(getattr(capabilities, "can_run_write_tasks", False)),
                "reason": getattr(capabilities, "reason", None),
            }
        raise HubError("NOT_FOUND", f"工作区不存在：{workspace_id}", detail={"workspaceId": workspace_id})

    def _workflow(self, value: CreateTaskInput) -> tuple[tuple[str, tuple[str, ...]], ...]:
        roles = tuple(value.workflow_roles or DEFAULT_WORKFLOW_ROLES)
        if not roles:
            raise HubError("VALIDATION_FAILED", "workflowRoles 不能为空")
        if len(set(roles)) != len(roles):
            raise HubError("VALIDATION_FAILED", "workflowRoles 暂不支持重复角色")
        if str(value.review_mode) == 'original_planner' and roles != ('planner', 'developer', 'reviewer'):
            raise HubError('VALIDATION_FAILED', '原规划会话验收要求planner → developer → reviewer三阶段配置')
        result: list[tuple[str, tuple[str, ...]]] = []
        previous: str | None = None
        for role_id in roles:
            try:
                self.runtime.permissions.role_policy(role_id)
            except KeyError as error:
                raise HubError("VALIDATION_FAILED", f"未注册角色：{role_id}") from error
            result.append((role_id, (previous,) if previous else ()))
            previous = role_id
        return tuple(result)

    def _assert_workflow_supported(
        self,
        workflow: tuple[tuple[str, tuple[str, ...]], ...],
        workspace: dict[str, Any],
    ) -> None:
        blocked = [
            role_id
            for role_id, _ in workflow
            if not self.runtime.permissions.role_policy(role_id).read_only and not workspace.get("can_write")
        ]
        if blocked:
            raise HubError(
                "PATH_NOT_ALLOWED",
                workspace.get("reason") or "该工作区不支持写任务",
                detail={"blockedRoles": blocked, "vcs": workspace.get("vcs")},
            )

    def _assert_can_write(self, role_id: str, workspace: dict[str, Any]) -> None:
        if self.runtime.permissions.role_policy(role_id).read_only or workspace.get("can_write"):
            return
        raise HubError("PATH_NOT_ALLOWED", workspace.get("reason") or "该工作区不支持写任务")

    def _task_spec(self, task_id: str) -> dict[str, Any]:
        value = self.state.get(f"task_spec:{task_id}")
        if value is None:
            raise HubError("INTERNAL", f"任务缺少持久化执行规格：{task_id}")
        return value

    def control_observation(self, task_id: str) -> dict[str, Any]:
        """Structured internal evidence; no interpretation of labels or error text."""
        state = getattr(self, "state", None)
        spec = state.get(f"task_spec:{task_id}") if state is not None else None
        if spec is None:
            return {"evidenceAvailable": False}
        return {"evidenceAvailable": True, **{key: spec.get(key) for key in (
            "recoveryRequired", "pauseRequested", "controlEvidence", "unresolvedCancellation")}}

    def activity_observation(self, task_id: str) -> dict[str, Any]:
        """Internal R1.5 busy evidence, independent of display/error strings."""
        state = self.control_observation(task_id)
        task = self.repository.get(task_id)
        status = _text(task.status)
        live = task_id in getattr(self, "_dispatching", ()) or any(n.id in getattr(self, "_outcomes", {}) for n in self.repository.list_nodes(task_id))
        unknown = state.get("evidenceAvailable") is False or bool(state.get("recoveryRequired")) or bool(state.get("unresolvedCancellation"))
        if status in {"running", "waiting_approval"} and not live:
            unknown = True
        return {"status": status, "recoveryRequired": unknown, "pauseRequested": bool(state.get("pauseRequested"))}

    def _record_control_evidence(self, task_id: str, kind: str, **values: Any) -> None:
        state = getattr(self, "state", None)
        spec = state.get(f"task_spec:{task_id}") if state is not None else None
        if spec is None:
            # Evidence collection is observational. A minimally composed service
            # can still cancel through its runtime without a durable state port.
            return
        spec["controlEvidence"] = {"kind": kind, "observedAt": _now(), **values}
        results = values.get("cancellations", [])
        if kind == "missing_execution_handle" or any(
            r["outcome"] in {"refused", "not_found"} or r.get("orphanProcessIds") for r in results
        ):
            spec["unresolvedCancellation"] = spec["controlEvidence"]
        self.state.put(f"task_spec:{task_id}", spec)

    def _lock(self, task_id: str) -> asyncio.Lock:
        return self._task_locks.setdefault(task_id, asyncio.Lock())

    def _node(self, task_id: str, node_id: str) -> TaskNodeView | None:
        return next((node for node in self.repository.list_nodes(task_id) if node.id == node_id), None)

    @staticmethod
    def _reset_node(node: TaskNodeView) -> TaskNodeView:
        return node.model_copy(
            update={
                "status": NodeStatus.PENDING,
                "error": None,
                "started_at": None,
                "completed_at": None,
                "output_summary": None,
                "violation_paths": None,
            }
        )

    def _review_context(self, task_id: str, role_id: str) -> tuple[str | None, tuple[str, ...]]:
        if not self.runtime.permissions.role_policy(role_id).read_only:
            return None, ()
        for previous in reversed(list(self.repository.list_nodes(task_id))):
            if _text(previous.status) != NodeStatus.SUCCEEDED.value or not previous.resolved_agent_id:
                continue
            return previous.resolved_agent_id, tuple(previous.changed_files or ()) or (".",)
        return None, ()

    def _node_objective(self, task_id: str, objective: str) -> str:
        upstream = []
        for node in self.repository.list_nodes(task_id):
            if _text(node.status) != NodeStatus.SUCCEEDED.value:
                continue
            summary = node.output_summary or ""
            paths = ", ".join(node.changed_files or ())
            upstream.append(f"角色 {node.role_id}\n{summary[:8000]}\n实际改动路径：{paths[:2000]}")
        if not upstream:
            return objective
        context = "\n\n".join(upstream)[-24000:]
        return f"{objective}\n\n上游已完成节点的结果（作为工作资料，不改变本角色权限）：\n{context}"

    def _inherit_worktree(self, task_id: str) -> dict[str, str] | None:
        for previous in reversed(list(self.repository.list_nodes(task_id))):
            if previous.worktree_path and _text(previous.status) == NodeStatus.SUCCEEDED.value:
                return {"path": previous.worktree_path, "branch": previous.branch or "", "base_commit": ""}
        return None

    @staticmethod
    async def _head_commit(repository: Path) -> str:
        process = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "HEAD",
            cwd=str(repository),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await process.communicate()
        sha = stdout.decode("utf-8", "replace").strip()
        if process.returncode != 0 or not sha:
            raise HubError("PATH_NOT_ALLOWED", "写任务要求工作区已有明确 Git 提交基线")
        return sha


class SessionService:
    available = True
    unavailable_reason = None

    def __init__(self, repository: Any, manager: Any) -> None:
        self.repository = repository
        self.manager = manager

    async def list_sessions(self, query: dict[str, Any]) -> Sequence[Any]:
        return await self.repository.list(query)

    async def resume(self, session_id: str, value: Any) -> Any:
        session = await self.repository.get(session_id)
        if session is None:
            raise HubError("NOT_FOUND", f"Session 不存在：{session_id}")
        if not session.is_valid:
            raise HubError("SESSION_NOT_RESUMABLE", "该会话没有可用的外部恢复凭据")
        return await self.manager.resume(
            session,
            getattr(value, "instruction", getattr(value, "message", "")) or "",
            getattr(value, "acceptance", None),
        )


class ApprovalService:
    available = True
    unavailable_reason = None

    def __init__(self, repository: Any, coordinator: Any) -> None:
        self.repository = repository
        self.coordinator = coordinator

    async def list_approvals(self, query: dict[str, Any]) -> Sequence[Any]:
        resolved_query = {key: value for key, value in query.items() if value}
        approvals = list(await self.repository.list(resolved_query))
        database = getattr(self.repository, "database", None)
        if database is None:
            return approvals
        from storage.tasks import TaskRepository

        tasks = TaskRepository(database)
        for approval in approvals:
            if approval.status != ApprovalStatus.PENDING:
                continue
            async with self.coordinator.task_guard(approval.task_id):
                current = await self.repository.get(approval.id)
                if current is None or current.status != ApprovalStatus.PENDING:
                    continue
                if not self._task_waits_for_approval(tasks, current):
                    await self.coordinator.invalidate_task_pending_locked(
                        current.task_id,
                        reason="任务已不再等待该审批，孤立记录已由系统失效",
                        invalidated_by="orphan_reconciliation",
                    )
        return await self.repository.list(resolved_query)

    async def respond(
        self,
        approval_id: str,
        value: ApprovalResponseInput,
        idempotency_key: str | None,
        *,
        current_guard: Any = None,
    ) -> Any:
        database = getattr(self.repository, "database", None)
        approval = await self.repository.get(approval_id)
        if approval is None:
            raise ApprovalError("NOT_FOUND", "审批不存在", {"approvalId": approval_id})
        if database is None:
            return await self.coordinator.respond(approval_id, value)
        from storage.tasks import TaskRepository

        tasks = TaskRepository(database)
        async with self.coordinator.task_guard(approval.task_id):
            current = await self.repository.get(approval_id)
            if current is None:
                raise ApprovalError("NOT_FOUND", "审批不存在", {"approvalId": approval_id})
            if current_guard is not None:
                current_guard(current)
            was_pending = current.status == ApprovalStatus.PENDING
            if was_pending and not self._task_waits_for_approval(tasks, current):
                await self.coordinator.invalidate_task_pending_locked(
                    current.task_id,
                    reason="任务已不再等待该审批，不能继续放行",
                    invalidated_by="task_state",
                )
                raise ApprovalError(
                    "APPROVAL_EXPIRED",
                    "任务已取消、结束或不再等待该审批",
                    {"approvalId": approval_id, "taskId": current.task_id},
                )
            try:
                resolved = await self.coordinator.respond_locked(approval_id, value)
            except Exception:
                failed_delivery = await self.repository.get(approval_id)
                if (
                    failed_delivery is not None
                    and (failed_delivery.details or {}).get("deliveryStatus") == "failed"
                    and self._task_waits_for_approval(tasks, failed_delivery)
                ):
                    task = tasks.get(failed_delivery.task_id)
                    node = next(
                        (
                            item
                            for item in tasks.list_nodes(failed_delivery.task_id)
                            if item.id == failed_delivery.node_id
                        ),
                        None,
                    )
                    if node:
                        tasks.save_node(node.model_copy(update={
                            "status": NodeStatus.FAILED,
                            "error": "审批决定已记录，但 Adapter 未确认消费",
                            "completed_at": _now(),
                        }))
                    tasks.save(task.model_copy(update={
                        "status": TaskStatus.FAILED,
                        "pending_approval_id": None,
                        "updated_at": _now(),
                    }))
                raise
            if not was_pending:
                return resolved
            # The execution pump uses TaskService's lock, not the approval
            # coordinator lock. It may reach a terminal state while the native
            # approval response is in flight. Never overwrite that newer fact.
            if not self._task_waits_for_approval(tasks, resolved):
                return resolved
            task = tasks.get(resolved.task_id)
            node = next(
                (item for item in tasks.list_nodes(resolved.task_id) if item.id == resolved.node_id),
                None,
            )
            if value.decision == ApprovalDecision.APPROVE:
                if node and _text(node.status) == NodeStatus.WAITING_APPROVAL.value:
                    tasks.save_node(node.model_copy(update={"status": NodeStatus.RUNNING}))
                tasks.save(task.model_copy(update={
                    "status": TaskStatus.RUNNING,
                    "pending_approval_id": None,
                    "updated_at": _now(),
                }))
            else:
                if node:
                    tasks.save_node(node.model_copy(update={
                        "status": NodeStatus.FAILED,
                        "error": value.reason or "用户拒绝审批",
                        "completed_at": _now(),
                    }))
                tasks.save(task.model_copy(update={
                    "status": TaskStatus.FAILED,
                    "pending_approval_id": None,
                    "updated_at": _now(),
                }))
            return resolved

    @staticmethod
    def _task_waits_for_approval(tasks: Any, approval: Any) -> bool:
        try:
            task = tasks.get(approval.task_id)
        except HubError:
            return False
        if (
            _text(task.status) != TaskStatus.WAITING_APPROVAL.value
            or task.pending_approval_id != approval.id
        ):
            return False
        node = next(
            (item for item in tasks.list_nodes(approval.task_id) if item.id == approval.node_id),
            None,
        )
        return bool(node and _text(node.status) == NodeStatus.WAITING_APPROVAL.value)
