from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from protocol.generated.python import ApprovalDecision, HubEvent, TaskStatus

from .domain import NodeRuntimeState, TaskRuntimeState
from .errors import InvalidTaskActionError
from .ports import RuntimeEventSink


def _payload(event: HubEvent) -> dict[str, Any]:
    if isinstance(event.payload, dict):
        return event.payload
    if hasattr(event.payload, "model_dump"):
        return event.payload.model_dump(mode="json", by_alias=True, exclude_none=True)
    return {}


class TaskEventReducer:
    """Rebuild task/node state solely from the persisted Hub event stream."""

    def apply(self, state: TaskRuntimeState, event: HubEvent) -> TaskRuntimeState:
        if event.event_id in state.seen_event_ids:
            return state
        if event.seq <= state.last_seq:
            raise InvalidTaskActionError(
                "事件序列倒退，无法安全恢复任务",
                taskId=state.task_id,
                lastSeq=state.last_seq,
                eventSeq=event.seq,
            )
        if event.task_id and event.task_id != state.task_id:
            raise InvalidTaskActionError(
                "事件不属于待恢复任务",
                taskId=state.task_id,
                eventTaskId=event.task_id,
            )

        payload = _payload(event)
        node = self._node(state, event)
        event_type = event.type

        if event_type == "task.created":
            state.status = TaskStatus.QUEUED.value
            state.objective = payload.get("objective")
            state.workspace_id = payload.get("workspaceId")
            state.profile_id = payload.get("profileId")
        elif event_type == "node.resolved" and node is not None:
            node.role_id = payload.get("roleId") or self._text(event.role_id)
            node.status = "resolving"
            node.resolved_agent_id = payload.get("resolvedAgentId")
            node.resolved_agent_name = payload.get("resolvedAgentName")
            node.resolve_source = payload.get("resolveSource")
            node.is_fallback = bool(payload.get("isFallback", False))
            node.fallback_reason = payload.get("fallbackReason")
            node.missing_capabilities = tuple(payload.get("missingCapabilities") or ())
        elif event_type == "agent.started" and node is not None:
            self._set_task_status(state, TaskStatus.RUNNING.value, event_type)
            node.status = "running"
            node.session_id = payload.get("sessionId")
            node.external_session_id = payload.get("externalSessionId")
        elif event_type == "approval.required":
            self._set_task_status(state, TaskStatus.WAITING_APPROVAL.value, event_type)
            state.pending_approval_id = payload.get("approvalId")
            if node is not None:
                node.status = "waiting_approval"
        elif event_type == "approval.resolved":
            decision = payload.get("decision")
            if decision == ApprovalDecision.APPROVE.value:
                self._set_task_status(state, TaskStatus.RUNNING.value, event_type)
                if node is not None:
                    node.status = "running"
            elif decision == ApprovalDecision.REJECT.value:
                self._set_task_status(state, TaskStatus.FAILED.value, event_type)
                state.failure_reason = payload.get("reason") or "用户拒绝审批"
                if node is not None:
                    node.status = "failed"
            state.pending_approval_id = None
        elif event_type == "agent.completed" and node is not None:
            node.status = "succeeded"
            result = payload.get("result") or {}
            node.changed_files = tuple(
                item.get("path") for item in result.get("changedFiles", []) if item.get("path")
            )
        elif event_type == "agent.failed" and node is not None:
            node.status = "failed"
            node.error = payload.get("message")
        elif event_type == "task.path_violation":
            self._set_task_status(state, TaskStatus.FAILED.value, event_type)
            violations = tuple(payload.get("violationPaths") or ())
            state.failure_reason = f"路径越界：{', '.join(violations)}"
            if node is not None:
                node.status = "failed"
                node.violation_paths = violations
        elif event_type in {"task.status_changed", "task.completed", "task.failed"}:
            target = payload.get("to")
            if target:
                self._set_task_status(state, target, event_type)
            state.failure_reason = payload.get("reason") if target == TaskStatus.FAILED.value else state.failure_reason

        state.seen_event_ids.add(event.event_id)
        state.last_seq = event.seq
        return state

    def rebuild(
        self,
        task_id: str,
        events: Iterable[HubEvent],
        initial: TaskRuntimeState | None = None,
    ) -> TaskRuntimeState:
        state = initial or TaskRuntimeState(task_id=task_id)
        for event in sorted(events, key=lambda item: item.seq):
            self.apply(state, event)
        return state

    @staticmethod
    def _node(state: TaskRuntimeState, event: HubEvent) -> NodeRuntimeState | None:
        if not event.node_id:
            return None
        return state.nodes.setdefault(event.node_id, NodeRuntimeState(node_id=event.node_id))

    @staticmethod
    def _text(value: object | None) -> str | None:
        if value is None:
            return None
        return value.value if hasattr(value, "value") else str(value)

    @staticmethod
    def _set_task_status(state: TaskRuntimeState, target: str, event_type: str) -> None:
        terminal = {
            TaskStatus.SUCCEEDED.value,
            TaskStatus.FAILED.value,
            TaskStatus.CANCELLED.value,
        }
        if state.status in terminal and target != state.status:
            raise InvalidTaskActionError(
                "终态任务不能再次迁移",
                current=state.status,
                target=target,
                eventType=event_type,
            )
        state.status = target


class TaskRecoveryService:
    def __init__(self, events: RuntimeEventSink, reducer: TaskEventReducer | None = None) -> None:
        self.events = events
        self.reducer = reducer or TaskEventReducer()

    async def recover(
        self,
        task_id: str,
        checkpoint: TaskRuntimeState | None = None,
    ) -> TaskRuntimeState:
        after = checkpoint.last_seq if checkpoint else 0
        events = await self.events.load_task_events(task_id, after)
        return self.reducer.rebuild(task_id, events, checkpoint)
