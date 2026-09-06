from __future__ import annotations

import uuid

import asyncio
from dataclasses import dataclass

from protocol.generated.python import (
    AdapterFailure,
    AdapterFailureKind,
    AdapterStreamEnd,
    AgentResult,
    AgentTaskSpec,
    CancelMode,
    CancelOutcome,
    CancelRequest,
    CancelResult,
    ErrorCode,
    FileChange,
    ResolveSource,
    RoleBindingView,
    SessionPurpose,
    SessionReusePolicy,
    SessionStatus,
    SessionView,
    TaskStatus,
)

from security.paths import PathScope
from security.permissions import PermissionEngine, RolePolicy

from .domain import (
    AgentCandidate,
    ProfileSnapshot,
    ResolutionDecision,
    ResolutionGap,
    ResolutionRequest,
    RuntimeEventDraft,
)
from .errors import InvalidTaskActionError, PathNotAllowedError
from .ports import AdapterDirectoryPort, RuntimeEventSink
from .role_resolver import RoleResolver
from .sessions import SessionManager, SessionPlan


@dataclass(frozen=True, slots=True)
class NodeDispatchRequest:
    task_id: str
    node_id: str
    workspace_id: str
    workspace_name: str
    role_id: str
    objective: str
    agents: tuple[AgentCandidate, ...]
    allowed_paths: tuple[str, ...] | None = None
    read_first: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()
    requires_approval: tuple[str, ...] | None = None
    task_override_agent_id: str | None = None
    workspace_profile: ProfileSnapshot | None = None
    global_profile: ProfileSnapshot | None = None
    manual_agent_id: str | None = None
    required_capabilities: frozenset[str] = frozenset()
    excluded_agent_ids: frozenset[str] = frozenset()
    permission_binding: RoleBindingView | None = None
    session_purpose: SessionPurpose = SessionPurpose.ADHOC
    reuse_policy: SessionReusePolicy = SessionReusePolicy.NEW_SESSION
    resume_session_id: str | None = None
    implementation_agent_id: str | None = None
    review_context_paths: tuple[str, ...] = ()
    worktree_path: str | None = None
    branch: str | None = None
    base_commit: str | None = None
    handoff_documents: tuple[str, ...] = ()
    timeout_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class DispatchOutcome:
    task_id: str
    node_id: str
    role_id: str
    worktree_path: str | None
    resolution: ResolutionDecision
    session: SessionView
    session_plan: SessionPlan
    path_scope: PathScope
    role_policy: RolePolicy
    requires_approval: tuple[str, ...]
    task_spec: AgentTaskSpec | None


@dataclass(frozen=True, slots=True)
class CompletionOutcome:
    result: AgentResult
    session: SessionView
    violation_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CancellationOutcome:
    result: CancelResult
    task_status: TaskStatus
    session_status: SessionStatus


class WorkflowRuntime:
    def __init__(
        self,
        resolver: RoleResolver,
        permissions: PermissionEngine,
        sessions: SessionManager,
        adapters: AdapterDirectoryPort,
        events: RuntimeEventSink,
    ) -> None:
        self.resolver = resolver
        self.permissions = permissions
        self.sessions = sessions
        self.adapters = adapters
        self.events = events

    async def dispatch(
        self,
        request: NodeDispatchRequest,
    ) -> DispatchOutcome | ResolutionGap:
        policy = self.permissions.role_policy(request.role_id, request.permission_binding)
        requires_approval = self.permissions.effective_requires_approval(
            policy,
            request.requires_approval,
        )
        resolution = self.resolver.resolve(
            ResolutionRequest(
                role_id=request.role_id,
                agents=request.agents,
                task_override_agent_id=request.task_override_agent_id,
                workspace_profile=request.workspace_profile,
                global_profile=request.global_profile,
                manual_agent_id=request.manual_agent_id,
                required_capabilities=request.required_capabilities,
                requires_approval=requires_approval,
                excluded_agent_ids=request.excluded_agent_ids,
            )
        )
        if isinstance(resolution, ResolutionGap):
            return resolution

        await self.events.append(
            RuntimeEventDraft(
                type="node.resolved",
                aggregate_type="task",
                aggregate_id=request.task_id,
                task_id=request.task_id,
                node_id=request.node_id,
                role_id=request.role_id,
                agent_instance_id=resolution.agent.instance_id,
                adapter_id=resolution.agent.adapter_id,
                payload=resolution.to_payload().model_dump(
                    mode="json", by_alias=True, exclude_none=True
                ),
            )
        )

        task_paths = (
            policy.writable_paths if request.allowed_paths is None else request.allowed_paths
        )
        scope = self.permissions.path_scope(policy, task_paths)
        if not policy.read_only and task_paths and not scope.adapter_patterns:
            raise PathNotAllowedError(tuple(task_paths), policy.writable_paths)

        plan = await self.sessions.plan(
            reuse_policy=request.reuse_policy,
            resume_session_id=request.resume_session_id,
            agent_instance_id=resolution.agent.instance_id,
            role_id=request.role_id,
            implementation_agent_id=request.implementation_agent_id,
        )
        read_first = list(request.read_first)
        if plan.forced_isolation:
            if not request.review_context_paths:
                raise InvalidTaskActionError(
                    "同一 Agent 承担实现与审核时，必须提供独立审核要读取的 diff/handoff 路径",
                    nodeId=request.node_id,
                )
            for path in request.review_context_paths:
                if path not in read_first:
                    read_first.append(path)

        if plan.resume_session is not None:
            session = await self.sessions.resume(
                plan.resume_session,
                request.objective,
                list(request.acceptance) or None,
            )
            task_spec = None
        else:
            # 裁决 D25：sessionId 由 Hub 生成后传给 Adapter，不能反过来。
            # 原来本地 Session ID 取自 handle.session_id，等于把会话身份的所有权
            # 交给了 Adapter——而 D7 要求「同一 Agent 承担实现与复核时必须是两个
            # 不同会话」，Adapter 并不知道自己这次是在实现还是在复核，只有 Hub 知道。
            hub_session_id = f"session_{uuid.uuid4().hex}"
            task_spec = AgentTaskSpec.model_validate(
                {
                    "sessionId": hub_session_id,
                    "taskId": request.task_id,
                    "nodeId": request.node_id,
                    "workspaceId": request.workspace_id,
                    "roleId": request.role_id,
                    "objective": request.objective,
                    "worktreePath": request.worktree_path,
                    "branch": request.branch,
                    "baseCommit": request.base_commit,
                    "allowedPaths": list(scope.adapter_patterns),
                    "readFirst": read_first or None,
                    "acceptance": list(request.acceptance) or None,
                    "requiresApproval": list(requires_approval) or None,
                    "sessionPurpose": request.session_purpose.value,
                    "reusePolicy": SessionReusePolicy.NEW_SESSION.value,
                    "handoffDocuments": list(request.handoff_documents) or None,
                    "timeoutSeconds": request.timeout_seconds,
                }
            )
            adapter = self.adapters.adapter_for(resolution.agent.instance_id)
            handle = await adapter.start(task_spec)
            if handle.session_id != hub_session_id:
                raise InvalidTaskActionError(
                    "Adapter 必须原样返回 Hub 传入的 sessionId（裁决 D25），不得自行生成",
                    expected=hub_session_id,
                    actual=handle.session_id,
                )
            if handle.adapter_id != resolution.agent.adapter_id:
                raise InvalidTaskActionError(
                    "Adapter 返回的 adapterId 与解析结果不一致",
                    expected=resolution.agent.adapter_id,
                    actual=handle.adapter_id,
                )
            if handle.supports_resume and not handle.external_session_id:
                raise InvalidTaskActionError(
                    "声明 supportsResume 的会话必须返回明确 externalSessionId",
                    nodeId=request.node_id,
                )
            session = await self.sessions.create_active(
                handle=handle,
                workspace_id=request.workspace_id,
                workspace_name=request.workspace_name,
                role_id=request.role_id,
                agent_instance_id=resolution.agent.instance_id,
                agent_display_name=resolution.agent.display_name,
                purpose=request.session_purpose,
                reuse_policy=SessionReusePolicy.NEW_SESSION,
                task_id=request.task_id,
                node_id=request.node_id,
            )

        await self.events.append(
            RuntimeEventDraft(
                type="agent.started",
                aggregate_type="task",
                aggregate_id=request.task_id,
                task_id=request.task_id,
                node_id=request.node_id,
                role_id=request.role_id,
                agent_instance_id=resolution.agent.instance_id,
                adapter_id=resolution.agent.adapter_id,
                payload={
                    "sessionId": session.id,
                    "externalSessionId": session.external_session_id or None,
                    "purpose": session.purpose.value,
                    "reusePolicy": plan.reuse_policy.value,
                    "worktreePath": request.worktree_path,
                    "branch": request.branch,
                },
            )
        )
        return DispatchOutcome(
            task_id=request.task_id,
            node_id=request.node_id,
            role_id=request.role_id,
            worktree_path=request.worktree_path,
            resolution=resolution,
            session=session,
            session_plan=plan,
            path_scope=scope,
            role_policy=policy,
            requires_approval=requires_approval,
            task_spec=task_spec,
        )

    async def collect_result(
        self,
        outcome: DispatchOutcome,
        *,
        complete_task: bool = True,
    ) -> CompletionOutcome:
        adapter = self.adapters.adapter_for(outcome.resolution.agent.instance_id)
        result = await adapter.collect_result(outcome.session.id)
        changed_files = tuple(
            item.path for item in (result.changed_files or []) if isinstance(item, FileChange)
        )
        validation = outcome.path_scope.validate(changed_files)
        if validation.violation_paths:
            await self.events.append(
                RuntimeEventDraft(
                    type="task.path_violation",
                    aggregate_type="task",
                    aggregate_id=outcome.task_id,
                    task_id=outcome.task_id,
                    node_id=outcome.node_id,
                    role_id=outcome.role_id,
                    agent_instance_id=outcome.session.agent_instance_id,
                    adapter_id=outcome.session.adapter_id,
                    payload={
                        "violationPaths": list(validation.violation_paths),
                        "allowedPaths": list(outcome.path_scope.adapter_patterns),
                        "worktreePath": outcome.worktree_path,
                    },
                )
            )
            await self._task_status_event(
                outcome,
                TaskStatus.RUNNING,
                TaskStatus.FAILED,
                "Agent 修改了角色或任务白名单之外的路径，已保留现场",
                event_type="task.failed",
            )
            session = await self.sessions.close(outcome.session.id)
            return CompletionOutcome(result, session, validation.violation_paths)

        if result.status == "done":
            await self.events.append(
                RuntimeEventDraft(
                    type="agent.completed",
                    aggregate_type="task",
                    aggregate_id=outcome.task_id,
                    task_id=outcome.task_id,
                    node_id=outcome.node_id,
                    role_id=outcome.role_id,
                    agent_instance_id=outcome.session.agent_instance_id,
                    adapter_id=outcome.session.adapter_id,
                    payload={
                        "result": result.model_dump(mode="json", by_alias=True, exclude_none=True)
                    },
                )
            )
            if complete_task:
                await self._task_status_event(
                    outcome,
                    TaskStatus.RUNNING,
                    TaskStatus.SUCCEEDED,
                    None,
                    event_type="task.completed",
                )
        else:
            capability_gap = any(
                blocker.kind == "capability_gap" for blocker in (result.blockers or [])
            )
            error_code = ErrorCode.CAPABILITY_MISSING if capability_gap else ErrorCode.INTERNAL
            await self.events.append(
                RuntimeEventDraft(
                    type="agent.failed",
                    aggregate_type="task",
                    aggregate_id=outcome.task_id,
                    task_id=outcome.task_id,
                    node_id=outcome.node_id,
                    role_id=outcome.role_id,
                    agent_instance_id=outcome.session.agent_instance_id,
                    adapter_id=outcome.session.adapter_id,
                    payload={
                        "errorCode": error_code.value,
                        "message": result.summary,
                        "blockers": [
                            item.model_dump(mode="json", by_alias=True, exclude_none=True)
                            for item in (result.blockers or [])
                        ],
                    },
                )
            )
            if complete_task:
                await self._task_status_event(
                    outcome,
                    TaskStatus.RUNNING,
                    TaskStatus.FAILED,
                    result.summary,
                    event_type="task.failed",
                )
        session = (
            await self.sessions.finish(outcome.session.id)
            if result.status == "done"
            else await self.sessions.close(outcome.session.id)
        )
        return CompletionOutcome(result, session)

    async def handle_stream_end(
        self,
        outcome: DispatchOutcome,
        stream_end: AdapterStreamEnd,
    ) -> SessionView:
        session = await self.sessions.apply_stream_end(outcome.session.id, stream_end)
        if session.status == SessionStatus.INVALID:
            await self.events.append(
                RuntimeEventDraft(
                    type="agent.failed",
                    aggregate_type="task",
                    aggregate_id=outcome.task_id,
                    task_id=outcome.task_id,
                    node_id=outcome.node_id,
                    role_id=outcome.role_id,
                    agent_instance_id=session.agent_instance_id,
                    adapter_id=session.adapter_id,
                    payload={
                        "errorCode": ErrorCode.INTERNAL.value,
                        "message": stream_end.detail or "Agent 已退出，Session 失效",
                    },
                )
            )
        return session

    async def record_adapter_failure(
        self,
        outcome: DispatchOutcome,
        failure: AdapterFailure,
        *,
        previous_status: TaskStatus = TaskStatus.RUNNING,
    ) -> None:
        code_by_kind = {
            AdapterFailureKind.NOT_INSTALLED: ErrorCode.AGENT_NOT_FOUND,
            AdapterFailureKind.NOT_LOGGED_IN: ErrorCode.AGENT_NOT_LOGGED_IN,
            AdapterFailureKind.VERSION_INCOMPATIBLE: ErrorCode.AGENT_INCOMPATIBLE,
            AdapterFailureKind.CAPABILITY_MISSING: ErrorCode.CAPABILITY_MISSING,
            AdapterFailureKind.PATH_VIOLATION: ErrorCode.PATH_NOT_ALLOWED,
            AdapterFailureKind.CANCELLED: ErrorCode.TASK_NOT_CANCELLABLE,
        }
        error_code = failure.code or code_by_kind.get(failure.kind, ErrorCode.INTERNAL)
        blockers = []
        if failure.kind == AdapterFailureKind.CAPABILITY_MISSING:
            blockers.append(
                {
                    "kind": "capability_gap",
                    "message": failure.message,
                    "detail": {
                        "missingCapabilities": [
                            item.value for item in (failure.missing_capabilities or [])
                        ]
                    },
                }
            )
        elif failure.kind == AdapterFailureKind.AGENT_ERROR:
            blockers.append(
                {
                    "kind": "external_failure",
                    "message": failure.message,
                    "detail": {
                        "adapterFailureKind": failure.kind.value,
                        "agentSideTimeout": "超时" in failure.message or "timeout" in failure.message.lower(),
                    },
                }
            )
        await self.events.append(
            RuntimeEventDraft(
                type="agent.failed",
                aggregate_type="task",
                aggregate_id=outcome.task_id,
                task_id=outcome.task_id,
                node_id=outcome.node_id,
                role_id=outcome.role_id,
                agent_instance_id=outcome.session.agent_instance_id,
                adapter_id=outcome.session.adapter_id,
                payload={
                    "errorCode": error_code.value,
                    "message": failure.message,
                    "blockers": blockers or None,
                },
            )
        )

        if failure.kind == AdapterFailureKind.PATH_VIOLATION:
            await self.events.append(
                RuntimeEventDraft(
                    type="task.path_violation",
                    aggregate_type="task",
                    aggregate_id=outcome.task_id,
                    task_id=outcome.task_id,
                    node_id=outcome.node_id,
                    role_id=outcome.role_id,
                    agent_instance_id=outcome.session.agent_instance_id,
                    adapter_id=outcome.session.adapter_id,
                    payload={
                        "violationPaths": failure.violation_paths or [],
                        "allowedPaths": list(outcome.path_scope.adapter_patterns),
                        "worktreePath": outcome.worktree_path,
                    },
                )
            )
        # Agent-side tool timeout is an agent_error and remains a task failure;
        # it never mutates ApprovalStatus to expired. Approval expiry is owned by
        # ApprovalCoordinator's Hub clock.
        await self._task_status_event(
            outcome,
            previous_status,
            TaskStatus.FAILED,
            failure.message,
            event_type="task.failed",
        )

    async def cancel(
        self,
        outcome: DispatchOutcome,
        *,
        reason: str,
        grace_seconds: int = 10,
    ) -> CancellationOutcome:
        adapter = self.adapters.adapter_for(outcome.resolution.agent.instance_id)
        graceful = CancelRequest.model_validate(
            {
                "sessionId": outcome.session.id,
                "mode": CancelMode.GRACEFUL.value,
                "reason": reason,
                "graceSeconds": grace_seconds,
            }
        )
        try:
            result = await asyncio.wait_for(
                adapter.cancel(graceful),
                timeout=max(float(grace_seconds), 0.001),
            )
        except TimeoutError:
            result = await adapter.cancel(
                CancelRequest.model_validate(
                    {
                        "sessionId": outcome.session.id,
                        "mode": CancelMode.FORCE.value,
                        "reason": f"graceful 超时：{reason}",
                    }
                )
            )

        if result.outcome == CancelOutcome.REFUSED:
            await self.events.append(
                RuntimeEventDraft(
                    type="agent.failed",
                    aggregate_type="task",
                    aggregate_id=outcome.task_id,
                    task_id=outcome.task_id,
                    node_id=outcome.node_id,
                    role_id=outcome.role_id,
                    agent_instance_id=outcome.session.agent_instance_id,
                    adapter_id=outcome.session.adapter_id,
                    payload={
                        "errorCode": ErrorCode.TASK_NOT_CANCELLABLE.value,
                        "message": result.detail or "Adapter 拒绝取消，Agent 可能仍在运行",
                    },
                )
            )
            await self._task_status_event(
                outcome,
                TaskStatus.RUNNING,
                TaskStatus.FAILED,
                result.detail or "取消失败，Agent 可能仍在运行",
                event_type="task.failed",
            )
            return CancellationOutcome(result, TaskStatus.FAILED, outcome.session.status)

        if result.outcome == CancelOutcome.NOT_FOUND:
            invalid = outcome.session.model_copy(
                update={"status": SessionStatus.INVALID, "is_valid": False}
            )
            await self.sessions.repository.save(invalid)
            await self._task_status_event(
                outcome,
                TaskStatus.RUNNING,
                TaskStatus.FAILED,
                result.detail or "Adapter 找不到待取消 Session",
                event_type="task.failed",
            )
            return CancellationOutcome(result, TaskStatus.FAILED, SessionStatus.INVALID)

        if result.outcome == CancelOutcome.ALREADY_FINISHED:
            session = await self.sessions.finish(outcome.session.id)
            return CancellationOutcome(result, TaskStatus.RUNNING, session.status)

        session = await self.sessions.close(outcome.session.id)
        await self._task_status_event(
            outcome,
            TaskStatus.RUNNING,
            TaskStatus.CANCELLED,
            reason,
            event_type="task.status_changed",
        )
        return CancellationOutcome(result, TaskStatus.CANCELLED, session.status)

    async def _task_status_event(
        self,
        outcome: DispatchOutcome,
        previous: TaskStatus,
        target: TaskStatus,
        reason: str | None,
        *,
        event_type: str,
    ) -> None:
        await self.events.append(
            RuntimeEventDraft(
                type=event_type,
                aggregate_type="task",
                aggregate_id=outcome.task_id,
                task_id=outcome.task_id,
                node_id=outcome.node_id,
                role_id=outcome.role_id,
                agent_instance_id=outcome.session.agent_instance_id,
                adapter_id=outcome.session.adapter_id,
                payload={
                    "from": previous.value,
                    "to": target.value,
                    "reason": reason,
                },
            )
        )
