from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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

    async def request(self, value: ApprovalRequest) -> ApprovalView:
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
            return existing
        details = dict(value.details or {})
        if value.external_request_id:
            details["externalRequestId"] = value.external_request_id
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
                "status": ApprovalStatus.PENDING.value,
                "requestedAt": timestamp(now),
                "expiresAt": timestamp(now + timedelta(minutes=self.timeout_minutes)),
                "details": details or None,
            }
        )
        await self.repository.save(approval)
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
        if approval.status != ApprovalStatus.PENDING:
            expected_status = (
                ApprovalStatus.APPROVED
                if value.decision == ApprovalDecision.APPROVE
                else ApprovalStatus.REJECTED
            )
            if approval.status == expected_status and approval.decision == value.decision:
                return approval
            code = (
                "APPROVAL_EXPIRED"
                if approval.status == ApprovalStatus.EXPIRED
                else "APPROVAL_ALREADY_DECIDED"
            )
            raise ApprovalError(code, "审批已失效或已处理", {"approvalId": approval_id})
        now = self.clock()
        if self._expired(approval, now):
            expired = approval.model_copy(update={"status": ApprovalStatus.EXPIRED})
            await self.repository.save(expired)
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
            }
        )
        details = approval.details or {}
        adapter = self.adapters.adapter_for(approval.request_agent_id)
        await self.repository.save(resolved)
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
        # The Hub decision is durable before talking to the Adapter. Adapter
        # transport failure must not turn a user decision back into "pending".
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
                    f"审批决定已保存，但 Adapter 拒绝消费：{dispatch_result.message}",
                    {"approvalId": approval.id, "adapterFailureKind": dispatch_result.kind.value},
                )
        except Exception:
            await self._append_task_failure(
                resolved,
                "用户审批决定已保存，但 Adapter 未能接收决定",
            )
            raise
        if value.decision == ApprovalDecision.REJECT:
            await self._append_task_failure(resolved, value.reason or "用户拒绝了危险动作")
        return resolved

    async def expire_due(self) -> tuple[str, ...]:
        now = self.clock()
        approvals = await self.repository.list({"status": ApprovalStatus.PENDING.value})
        expired_ids: list[str] = []
        for approval in approvals:
            if not self._expired(approval, now):
                continue
            expired = approval.model_copy(update={"status": ApprovalStatus.EXPIRED})
            await self.repository.save(expired)
            await self._append_task_failure(expired, "审批已超时，用户未在 Hub 时效内决定")
            expired_ids.append(expired.id)
        return tuple(expired_ids)

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
