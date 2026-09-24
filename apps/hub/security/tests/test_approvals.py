from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from protocol.generated.python import (
    AdapterFailure,
    ApprovalResponseInput,
    ApprovalStatus,
    DangerousAction,
    RiskLevel,
)

from orchestrator.errors import ApprovalError
from orchestrator.tests.fakes import (
    FakeAdapterDirectory,
    FakeApprovalRepository,
    FakeEventSink,
    agent,
    async_test,
)
from security.approvals import ApprovalCoordinator, ApprovalRequest


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value


def build_coordinator():
    clock = MutableClock()
    repository = FakeApprovalRepository()
    events = FakeEventSink()
    directory = FakeAdapterDirectory((agent("agent", capabilities=("tool_approval",)),))
    coordinator = ApprovalCoordinator(
        repository,
        events,
        directory,
        timeout_minutes=5,
        clock=clock,
    )
    return coordinator, clock, repository, events, directory.adapter


def request_value() -> ApprovalRequest:
    return ApprovalRequest(
        task_id="task",
        task_objective="push changes",
        node_id="node",
        request_agent_id="agent",
        request_agent_name="agent",
        role_id="general_implementer",
        action=DangerousAction.GIT_PUSH,
        target_resource="origin/work/w3",
        risk_level=RiskLevel.HIGH,
        external_request_id="vendor-request",
    )


@async_test
async def test_hub_sets_expiry_and_dispatches_user_decision() -> None:
    coordinator, _, repository, events, adapter = build_coordinator()
    approval = await coordinator.request(request_value())
    resolved = await coordinator.respond(
        approval.id,
        ApprovalResponseInput.model_validate({"decision": "approve", "reason": "checked"}),
    )

    assert resolved.status == ApprovalStatus.APPROVED
    assert repository.items[approval.id].status == ApprovalStatus.APPROVED
    assert adapter.approvals[0].external_request_id == "vendor-request"
    assert [event.type for event in events.events] == ["approval.required", "approval.resolved"]


@async_test
async def test_expired_user_decision_never_reaches_adapter() -> None:
    coordinator, clock, repository, events, adapter = build_coordinator()
    approval = await coordinator.request(request_value())
    clock.value += timedelta(minutes=6)

    with pytest.raises(ApprovalError) as error:
        await coordinator.respond(
            approval.id,
            ApprovalResponseInput.model_validate({"decision": "approve"}),
        )

    assert error.value.code == "APPROVAL_EXPIRED"
    assert "不是 Agent 侧超时" in error.value.message
    assert repository.items[approval.id].status == ApprovalStatus.EXPIRED
    assert adapter.approvals == []
    assert events.events[-1].type == "task.failed"


@async_test
async def test_agent_side_timeout_does_not_expire_hub_approval() -> None:
    coordinator, clock, repository, _, _ = build_coordinator()
    approval = await coordinator.request(request_value())

    # An AdapterFailure(kind=agent_error) is handled by WorkflowRuntime. The
    # approval clock has not elapsed, so the Hub-owned approval remains pending.
    clock.value += timedelta(minutes=1)
    expired = await coordinator.expire_due()

    assert expired == ()
    assert repository.items[approval.id].status == ApprovalStatus.PENDING


@async_test
async def test_adapter_approval_id_is_preserved_and_duplicate_event_is_idempotent() -> None:
    coordinator, _, repository, events, _ = build_coordinator()
    request = replace(request_value(), approval_id="approval_from_adapter")

    first = await coordinator.request(request)
    second = await coordinator.request(request)

    assert first.id == "approval_from_adapter"
    assert second.id == first.id
    assert list(repository.items) == ["approval_from_adapter"]
    assert [event.type for event in events.events] == ["approval.required"]


@async_test
async def test_adapter_failure_is_not_treated_as_consumed_approval() -> None:
    coordinator, _, _, events, adapter = build_coordinator()
    approval = await coordinator.request(replace(request_value(), approval_id="approval_failure"))

    async def fail_approval(dispatch):
        return AdapterFailure.model_validate(
            {
                "kind": "agent_error",
                "message": "native request disappeared",
                "retryable": False,
            }
        )

    adapter.approve = fail_approval
    with pytest.raises(ApprovalError) as error:
        await coordinator.respond(
            approval.id,
            ApprovalResponseInput.model_validate({"decision": "approve"}),
        )

    assert error.value.code == "INTERNAL"
    assert events.events[-1].type == "task.failed"
