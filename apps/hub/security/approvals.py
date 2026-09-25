from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from collections.abc import AsyncIterator
from typing import Callable

from protocol.generated.python import (
    AdapterFailure,
    ApprovalDecision,
    ApprovalDispatch,
    ApprovalResponseInput,
    ApprovalStatus,
    ApprovalView,
    DangerousAction,
    RiskLevel,
    TaskStatus,
)

from orchestrator.domain import RuntimeEventDraft
from orchestrator.errors import ApprovalError
from orchestrator.ports import (
    AdapterDirectoryPort,
    ApprovalRepositoryPort,
    RuntimeEventSink,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    task_id: str
    task_objective: str
    node_id: str
    request_agent_id: str
    request_agent_name: str
    role_id: str
    action: DangerousAction
    target_resource: str
    risk_level: RiskLevel
    approval_id: str | None = None
    external_request_id: str | None = None
    details: dict[str, object] | None = None


class ApprovalCoordinator:
    def __init__(
        self,
        repository: ApprovalRepositoryPort,
        events: RuntimeEventSink,
        adapters: AdapterDirectoryPort,
        *,
        timeout_minutes: int = 30,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if timeout_minutes < 1:
            raise ValueError("timeout_minutes must be positive")
        self.repository = repository
        self.events = events
        self.adapters = adapters
        self.timeout_minutes = timeout_minutes
        self.clock = clock
        self._task_locks: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def task_guard(self, task_id: str) -> AsyncIterator[None]:
        lock = self._task_locks.setdefault(task_id, asyncio.Lock())
        async with lock:
            yield

    async def request(
        self,
        value: ApprovalRequest,
        *,
        active_check: Callable[[], bool] | None = None,
    ) -> ApprovalView:
        async with self.task_guard(value.task_id):
            return await self._request_locked(value, active_check=active_check)

    async def _request_locked(
        self,
        value: ApprovalRequest,
        *,
        active_check: Callable[[], bool] | None = None,
    ) -> ApprovalView:
        now = self.clock()
        approval_id = value.approval_id or f"approval_{uuid.uuid4().hex}"
        existing = await self.repository.get(approval_id)
        if existing is not None:
            existing_external = (existing.details or {}).get("externalRequestId")
            if (
                existing.task_id != value.task_id
                or existing.node_id != value.node_id
                or existing.request_agent_id != value.request_agent_id
                or existing.action != value.action
                or existing_external != value.external_request_id
            ):
                raise ApprovalError(
                    "CONFLICT",
                    "同一 approvalId 对应了不同的原生审批请求",
                    {"approvalId": approval_id},
                )
            if existing.status == ApprovalStatus.PENDING and active_check and not active_check():
                return await self._invalidate_one_locked(
                    existing,
                    reason="审批请求到达时任务已不再等待执行",
                    invalidated_by="task_state",
                )
            return existing
        details = dict(value.details or {})
        if value.external_request_id:
            details["externalRequestId"] = value.external_request_id
        active = active_check() if active_check else True
        approval = ApprovalView.model_validate(
            {
                "id": approval_id,
                "taskId": value.task_id,
                "taskObjective": value.task_objective,
                "nodeId": value.node_id,
                "requestAgentId": value.request_agent_id,
                "requestAgentName": value.request_agent_name,
                "roleId": value.role_id,
                "action": value.action.value,
                "targetResource": value.target_resource,
                "riskLevel": value.risk_level.value,
                "status": (
                    ApprovalStatus.PENDING.value if active else ApprovalStatus.EXPIRED.value
                ),
                "requestedAt": timestamp(now),
                "decidedAt": None if active else timestamp(now),
                "reason": None if active else "审批请求到达时任务已不再等待执行",
                "expiresAt": timestamp(now + timedelta(minutes=self.timeout_minutes)),
                "details": (
                    details
                    if active
                    else {
                        **details,
                        "invalidatedBy": "task_state",
                        "invalidatedAt": timestamp(now),
                    }
                ) or None,
            }
        )
        await self.repository.save(approval)
        if not active:
            return approval
        await self.events.append(
            RuntimeEventDraft(
                type="approval.required",
                aggregate_type="approval",
                aggregate_id=approval.id,
                task_id=approval.task_id,
                node_id=approval.node_id,
                role_id=value.role_id,
                agent_instance_id=approval.request_agent_id,
                payload={
                    "approvalId": approval.id,
                    "action": approval.action.value,
                    "targetResource": approval.target_resource,
                    "riskLevel": approval.risk_level.value,
                    "expiresAt": approval.expires_at,
                },
            )
        )
        return approval

    async def respond(
        self,
        approval_id: str,
        value: ApprovalResponseInput,
    ) -> ApprovalView:
        approval = await self.repository.get(approval_id)
        if approval is None:
            raise ApprovalError("NOT_FOUND", "审批不存在", {"approvalId": approval_id})
        async with self.task_guard(approval.task_id):
            return await self.respond_locked(approval_id, value)

    async def respond_locked(
        self,
        approval_id: str,
        value: ApprovalResponseInput,
    ) -> ApprovalView:
        approval = await self.repository.get(approval_id)
        if approval is None:
            raise ApprovalError("NOT_FOUND", "审批不存在", {"approvalId": approval_id})
        if approval.status != ApprovalStatus.PENDING:
            return self._existing_decision_or_raise(approval, value)
        now = self.clock()
        if self._expired(approval, now):
            expired = await self._invalidate_one_locked(
                approval,
                reason="审批已超时，用户未在 Hub 时效内决定",
                invalidated_by="hub_timeout",
            )
            await self._append_task_failure(expired, "审批已超时，用户未在 Hub 时效内决定")
            raise ApprovalError(
                "APPROVAL_EXPIRED",
                "审批已超时；该状态表示用户未及时决定，不是 Agent 侧超时",
                {"approvalId": approval_id},
            )

        decided_at = timestamp(now)
        status = (
            ApprovalStatus.APPROVED
            if value.decision == ApprovalDecision.APPROVE
            else ApprovalStatus.REJECTED
        )
        resolved = approval.model_copy(
            update={
                "status": status,
                "decision": value.decision,
                "reason": value.reason,
                "decided_at": decided_at,
                "details": {
                    **(approval.details or {}),
                    "deliveryStatus": "dispatching",
                },
            }
        )
        details = approval.details or {}
        adapter = self.adapters.adapter_for(approval.request_agent_id)
        if not await self._compare_and_set(approval, resolved):
            current = await self.repository.get(approval.id)
            if current is not None and current.status != ApprovalStatus.PENDING:
                return self._existing_decision_or_raise(current, value)
            raise ApprovalError(
                "CONFLICT",
                "审批状态在决定提交期间发生变化",
                {"approvalId": approval.id},
            )
        try:
            dispatch_result = await adapter.approve(
                ApprovalDispatch.model_validate(
                    {
                        "approvalId": approval.id,
                        "externalRequestId": details.get("externalRequestId"),
                        "decision": value.decision.value,
                        "reason": value.reason,
                        "decidedAt": decided_at,
                    }
                )
            )
            if isinstance(dispatch_result, AdapterFailure):
                raise ApprovalError(
                    "INTERNAL",
                    f"Adapter 拒绝消费审批决定：{dispatch_result.message}",
                    {"approvalId": approval.id, "adapterFailureKind": dispatch_result.kind.value},
                )
        except Exception as error:
            failure_kind = (
                error.detail.get("adapterFailureKind")
                if isinstance(error, ApprovalError) and isinstance(error.detail, dict)
                else type(error).__name__
            )
            failed = resolved.model_copy(
                update={
                    "reason": "用户决定已记录，但 Adapter 未确认消费",
                    "details": {
                        **(resolved.details or {}),
                        "deliveryStatus": "failed",
                        "deliveryFailureKind": str(failure_kind or "unknown")[:80],
                    },
                }
            )
            await self.repository.save(failed)
            await self._append_task_failure(
                failed,
                "用户审批决定已记录，但 Adapter 未确认消费",
            )
            if isinstance(error, ApprovalError):
                raise
            raise ApprovalError(
                "INTERNAL",
                "用户审批决定已记录，但 Adapter 未确认消费",
                {"approvalId": approval.id},
            ) from error
        consumed = resolved.model_copy(
            update={
                "details": {
                    **(resolved.details or {}),
                    "deliveryStatus": "consumed",
                }
            }
        )
        await self.repository.save(consumed)
        await self.events.append(
            RuntimeEventDraft(
                type="approval.resolved",
                aggregate_type="approval",
                aggregate_id=approval.id,
                task_id=approval.task_id,
                node_id=approval.node_id,
                role_id=str(approval.role_id) if approval.role_id else None,
                agent_instance_id=approval.request_agent_id,
                payload={
                    "approvalId": approval.id,
                    "decision": value.decision.value,
                    "reason": value.reason,
                    "decidedAt": decided_at,
                },
            )
        )
        if value.decision == ApprovalDecision.REJECT:
            await self._append_task_failure(consumed, value.reason or "用户拒绝了危险动作")
        return consumed

    async def invalidate_task_pending(
        self,
        task_id: str,
        *,
        reason: str,
        invalidated_by: str,
    ) -> tuple[ApprovalView, ...]:
        async with self.task_guard(task_id):
            return await self.invalidate_task_pending_locked(
                task_id,
                reason=reason,
                invalidated_by=invalidated_by,
            )

    async def invalidate_task_pending_locked(
        self,
        task_id: str,
        *,
        reason: str,
        invalidated_by: str,
    ) -> tuple[ApprovalView, ...]:
        approvals = await self.repository.list(
            {"status": ApprovalStatus.PENDING.value, "taskId": task_id}
        )
        invalidated: list[ApprovalView] = []
        for approval in approvals:
            updated = await self._invalidate_one_locked(
                approval,
                reason=reason,
                invalidated_by=invalidated_by,
            )
            if updated.status == ApprovalStatus.EXPIRED:
                invalidated.append(updated)
        return tuple(invalidated)

    async def expire_due(self) -> tuple[str, ...]:
        now = self.clock()
        approvals = await self.repository.list({"status": ApprovalStatus.PENDING.value})
        expired_ids: list[str] = []
        for approval in approvals:
            if not self._expired(approval, now):
                continue
            async with self.task_guard(approval.task_id):
                current = await self.repository.get(approval.id)
                if current is None or current.status != ApprovalStatus.PENDING:
                    continue
                expired = await self._invalidate_one_locked(
                    current,
                    reason="审批已超时，用户未在 Hub 时效内决定",
                    invalidated_by="hub_timeout",
                )
                if expired.status == ApprovalStatus.EXPIRED:
                    await self._append_task_failure(
                        expired, "审批已超时，用户未在 Hub 时效内决定"
                    )
                    expired_ids.append(expired.id)
        return tuple(expired_ids)

    def _existing_decision_or_raise(
        self,
        approval: ApprovalView,
        value: ApprovalResponseInput,
    ) -> ApprovalView:
        expected_status = (
            ApprovalStatus.APPROVED
            if value.decision == ApprovalDecision.APPROVE
            else ApprovalStatus.REJECTED
        )
        if approval.status == expected_status and approval.decision == value.decision:
            delivery_status = (approval.details or {}).get("deliveryStatus")
            if delivery_status in {"dispatching", "failed"}:
                raise ApprovalError(
                    "INTERNAL",
                    "用户决定已记录，但原生消费状态未确认；不会自动重复发送",
                    {"approvalId": approval.id, "deliveryStatus": delivery_status},
                )
            return approval
        code = (
            "APPROVAL_EXPIRED"
            if approval.status == ApprovalStatus.EXPIRED
            else "APPROVAL_ALREADY_DECIDED"
        )
        raise ApprovalError(code, "审批已失效或已处理", {"approvalId": approval.id})

    async def _invalidate_one_locked(
        self,
        approval: ApprovalView,
        *,
        reason: str,
        invalidated_by: str,
    ) -> ApprovalView:
        if approval.status != ApprovalStatus.PENDING:
            return approval
        now = timestamp(self.clock())
        details = {
            **(approval.details or {}),
            "invalidatedBy": invalidated_by,
            "invalidatedAt": now,
        }
        expired = approval.model_copy(
            update={
                "status": ApprovalStatus.EXPIRED,
                "decision": None,
                "reason": reason,
                "decided_at": now,
                "details": details,
            }
        )
        if await self._compare_and_set(approval, expired):
            return expired
        return await self.repository.get(approval.id) or approval

    async def _compare_and_set(
        self,
        current: ApprovalView,
        updated: ApprovalView,
    ) -> bool:
        compare = getattr(self.repository, "compare_and_set", None)
        if compare is not None:
            return bool(
                await compare(updated, expected_status=ApprovalStatus.PENDING.value)
            )
        latest = await self.repository.get(current.id)
        if latest is None or latest.status != ApprovalStatus.PENDING:
            return False
        await self.repository.save(updated)
        return True

    @staticmethod
    def _expired(approval: ApprovalView, now: datetime) -> bool:
        if not approval.expires_at:
            return False
        expires_at = datetime.fromisoformat(approval.expires_at.replace("Z", "+00:00"))
        return now >= expires_at

    async def _append_task_failure(self, approval: ApprovalView, reason: str) -> None:
        await self.events.append(
            RuntimeEventDraft(
                type="task.failed",
                aggregate_type="task",
                aggregate_id=approval.task_id,
                task_id=approval.task_id,
                node_id=approval.node_id,
                role_id=str(approval.role_id) if approval.role_id else None,
                agent_instance_id=approval.request_agent_id,
                payload={
                    "from": TaskStatus.WAITING_APPROVAL.value,
                    "to": TaskStatus.FAILED.value,
                    "reason": reason,
                },
            )
        )
