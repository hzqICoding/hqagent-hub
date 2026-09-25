from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from protocol.generated.python import (
    ApprovalResponseInput,
    ApprovalStatus,
    ApprovalView,
    DangerousAction,
    NodeStatus,
    RiskLevel,
    TaskNodeView,
    TaskStatus,
    TaskSummaryView,
)

from orchestrator.errors import ApprovalError
from orchestrator.tests.fakes import FakeAdapterDirectory, agent
from runtime.repositories import ApprovalRepository, EventSink
from runtime.tasks import ApprovalService, TaskService
from security.approvals import ApprovalCoordinator, ApprovalRequest
from storage.database import Database
from storage.events import EventStore
from storage.tasks import TaskRepository


def timestamp() -> str:
    return "2026-09-25T04:00:00Z"


def save_waiting_task(
    repository: TaskRepository,
    *,
    task_id: str = "task",
    node_id: str = "node",
    approval_id: str | None = None,
    task_status: TaskStatus = TaskStatus.WAITING_APPROVAL,
    node_status: NodeStatus = NodeStatus.WAITING_APPROVAL,
) -> None:
    repository.save(
        TaskSummaryView.model_validate(
            {
                "id": task_id,
                "objective": "dangerous action",
                "workspaceId": "workspace",
                "workspaceName": "workspace",
                "profileId": "profile",
                "profileName": "profile",
                "status": task_status.value,
                "source": "desktop",
                "createdAt": timestamp(),
                "updatedAt": timestamp(),
                "pendingApprovalId": approval_id,
            }
        )
    )
    repository.save_node(
        TaskNodeView.model_validate(
            {
                "id": node_id,
                "taskId": task_id,
                "roleId": "developer",
                "resolvedAgentId": "agent",
                "resolvedAgentName": "agent",
                "resolveSource": "task_override",
                "status": node_status.value,
            }
        )
    )


async def request_approval(
    coordinator: ApprovalCoordinator,
    approval_id: str = "approval",
) -> ApprovalView:
    return await coordinator.request(
        ApprovalRequest(
            approval_id=approval_id,
            task_id="task",
            task_objective="dangerous action",
            node_id="node",
            request_agent_id="agent",
            request_agent_name="agent",
            role_id="developer",
            action=DangerousAction.SHELL,
            target_resource="node --test",
            risk_level=RiskLevel.HIGH,
            external_request_id="native-request",
        )
    )


def setup(tmp_path: Path):
    database = Database(tmp_path / "hub.db")
    database.initialize()
    event_sink = EventSink(database, EventStore(database))
    directory = FakeAdapterDirectory(
        (agent("agent", capabilities=("tool_approval",)),)
    )
    approvals = ApprovalRepository(database)
    coordinator = ApprovalCoordinator(approvals, event_sink, directory)
    tasks = TaskRepository(database)
    return database, event_sink, directory, approvals, coordinator, tasks


def task_service_for(
    tasks: TaskRepository,
    events: EventSink,
    coordinator: ApprovalCoordinator,
    runtime,
) -> TaskService:
    service = object.__new__(TaskService)
    service.repository = tasks
    service.events = events
    service.approval_coordinator = coordinator
    service.runtime = runtime
    service._outcomes = {"node": object()}
    service._pumps = {}

    async def release_children(_task_id: str) -> None:
        return None

    service._release_children = release_children
    return service


def test_cancel_invalidates_pending_and_late_approval_cannot_reach_adapter(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, events, directory, approvals, coordinator, tasks = setup(tmp_path)
        try:
            approval = await request_approval(coordinator)
            save_waiting_task(tasks, approval_id=approval.id)

            class Runtime:
                async def cancel(self, _outcome, *, reason):
                    return SimpleNamespace(task_status=TaskStatus.CANCELLED)

            task_service = task_service_for(tasks, events, coordinator, Runtime())
            await task_service._cancel("task")

            stored = await approvals.get(approval.id)
            assert stored.status == ApprovalStatus.EXPIRED
            assert stored.decision is None
            assert stored.details["invalidatedBy"] == "task_cancelled"
            assert "系统撤回" in stored.reason
            assert tasks.get("task").status == TaskStatus.CANCELLED
            assert tasks.get("task").pending_approval_id is None

            service = ApprovalService(approvals, coordinator)
            with pytest.raises(ApprovalError) as error:
                await service.respond(
                    approval.id,
                    ApprovalResponseInput.model_validate({"decision": "approve"}),
                    "late-approval",
                )
            assert error.value.code == "APPROVAL_EXPIRED"
            assert directory.adapter.approvals == []
        finally:
            database.close()

    asyncio.run(scenario())


def test_cancel_wins_race_before_approval_dispatch(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, events, directory, approvals, coordinator, tasks = setup(tmp_path)
        entered = asyncio.Event()
        release = asyncio.Event()
        try:
            approval = await request_approval(coordinator)
            save_waiting_task(tasks, approval_id=approval.id)

            class Runtime:
                async def cancel(self, _outcome, *, reason):
                    entered.set()
                    await release.wait()
                    return SimpleNamespace(task_status=TaskStatus.CANCELLED)

            task_service = task_service_for(tasks, events, coordinator, Runtime())
            approval_service = ApprovalService(approvals, coordinator)
            cancel_task = asyncio.create_task(task_service._cancel("task"))
            await asyncio.wait_for(entered.wait(), timeout=1)
            response_task = asyncio.create_task(
                approval_service.respond(
                    approval.id,
                    ApprovalResponseInput.model_validate({"decision": "approve"}),
                    "racing-approval",
                )
            )
            await asyncio.sleep(0)
            release.set()
            await cancel_task
            with pytest.raises(ApprovalError) as error:
                await response_task
            assert error.value.code == "APPROVAL_EXPIRED"
            assert (await approvals.get(approval.id)).status == ApprovalStatus.EXPIRED
            assert directory.adapter.approvals == []
        finally:
            database.close()

    asyncio.run(scenario())


def test_orphan_pending_is_expired_when_approvals_are_listed(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, _, _, approvals, coordinator, tasks = setup(tmp_path)
        try:
            save_waiting_task(
                tasks,
                task_status=TaskStatus.CANCELLED,
                node_status=NodeStatus.CANCELLED,
            )
            approval = await request_approval(coordinator, "orphan")
            service = ApprovalService(approvals, coordinator)
            listed = await service.list_approvals({})
            stored = next(item for item in listed if item.id == approval.id)
            assert stored.status == ApprovalStatus.EXPIRED
            assert stored.decision is None
            assert stored.details["invalidatedBy"] == "orphan_reconciliation"
        finally:
            database.close()

    asyncio.run(scenario())


def test_consumed_and_failed_delivery_have_distinct_idempotency(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, _, directory, approvals, coordinator, tasks = setup(tmp_path)
        try:
            approval = await request_approval(coordinator, "consumed")
            save_waiting_task(tasks, approval_id=approval.id)
            service = ApprovalService(approvals, coordinator)
            value = ApprovalResponseInput.model_validate({"decision": "approve"})
            first = await service.respond(approval.id, value, "approve-once")
            second = await service.respond(approval.id, value, "approve-again")
            assert first.status == second.status == ApprovalStatus.APPROVED
            assert first.details["deliveryStatus"] == "consumed"
            assert len(directory.adapter.approvals) == 1

            failed = await request_approval(coordinator, "failed-delivery")
            save_waiting_task(tasks, approval_id=failed.id)

            async def fail_approval(_dispatch):
                from protocol.generated.python import AdapterFailure

                return AdapterFailure.model_validate(
                    {"kind": "agent_error", "message": "gone", "retryable": False}
                )

            directory.adapter.approve = fail_approval
            with pytest.raises(ApprovalError):
                await service.respond(failed.id, value, "failed-once")
            stored = await approvals.get(failed.id)
            assert stored.status == ApprovalStatus.APPROVED
            assert stored.details["deliveryStatus"] == "failed"
            assert tasks.get("task").status == TaskStatus.FAILED
            with pytest.raises(ApprovalError) as repeated:
                await service.respond(failed.id, value, "failed-repeat")
            assert repeated.value.code == "INTERNAL"
        finally:
            database.close()

    asyncio.run(scenario())


def test_old_approved_history_remains_idempotent_after_task_cancel(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, _, directory, approvals, coordinator, tasks = setup(tmp_path)
        try:
            save_waiting_task(
                tasks,
                task_status=TaskStatus.CANCELLED,
                node_status=NodeStatus.CANCELLED,
            )
            historical = ApprovalView.model_validate(
                {
                    "id": "historical",
                    "taskId": "task",
                    "taskObjective": "old",
                    "nodeId": "node",
                    "requestAgentId": "agent",
                    "requestAgentName": "agent",
                    "roleId": "developer",
                    "action": "shell",
                    "targetResource": "old command",
                    "riskLevel": "high",
                    "status": "approved",
                    "requestedAt": timestamp(),
                    "decidedAt": timestamp(),
                    "decision": "approve",
                }
            )
            await approvals.save(historical)
            service = ApprovalService(approvals, coordinator)
            returned = await service.respond(
                historical.id,
                ApprovalResponseInput.model_validate({"decision": "approve"}),
                "historical-repeat",
            )
            assert returned.id == historical.id
            assert directory.adapter.approvals == []
        finally:
            database.close()

    asyncio.run(scenario())


def test_completion_during_native_approval_dispatch_is_not_overwritten(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, _, directory, approvals, coordinator, tasks = setup(tmp_path)
        entered = asyncio.Event()
        release = asyncio.Event()
        try:
            approval = await request_approval(coordinator, "completion-race")
            save_waiting_task(tasks, approval_id=approval.id)

            async def delayed_approval(dispatch):
                directory.adapter.approvals.append(dispatch)
                entered.set()
                await release.wait()
                return None

            directory.adapter.approve = delayed_approval
            service = ApprovalService(approvals, coordinator)
            response = asyncio.create_task(
                service.respond(
                    approval.id,
                    ApprovalResponseInput.model_validate({"decision": "approve"}),
                    "completion-race-key",
                )
            )
            await asyncio.wait_for(entered.wait(), timeout=1)

            terminal_task = tasks.get("task").model_copy(
                update={
                    "status": TaskStatus.SUCCEEDED,
                    "pending_approval_id": None,
                    "updated_at": timestamp(),
                }
            )
            terminal_node = tasks.list_nodes("task")[0].model_copy(
                update={"status": NodeStatus.SUCCEEDED, "completed_at": timestamp()}
            )
            tasks.save(terminal_task)
            tasks.save_node(terminal_node)
            release.set()

            resolved = await response
            assert resolved.status == ApprovalStatus.APPROVED
            assert resolved.details["deliveryStatus"] == "consumed"
            assert tasks.get("task").status == TaskStatus.SUCCEEDED
            assert tasks.get("task").pending_approval_id is None
            assert tasks.list_nodes("task")[0].status == NodeStatus.SUCCEEDED
        finally:
            database.close()

    asyncio.run(scenario())


def test_approve_first_then_cancel_serializes_without_replay_or_running_overwrite(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        database, events, directory, approvals, coordinator, tasks = setup(tmp_path)
        entered = asyncio.Event()
        release = asyncio.Event()
        try:
            approval = await request_approval(coordinator, "approve-first")
            save_waiting_task(tasks, approval_id=approval.id)

            async def delayed_approval(dispatch):
                directory.adapter.approvals.append(dispatch)
                entered.set()
                await release.wait()
                return None

            directory.adapter.approve = delayed_approval

            class Runtime:
                async def cancel(self, _outcome, *, reason):
                    return SimpleNamespace(task_status=TaskStatus.CANCELLED)

            approval_service = ApprovalService(approvals, coordinator)
            task_service = task_service_for(tasks, events, coordinator, Runtime())
            response = asyncio.create_task(
                approval_service.respond(
                    approval.id,
                    ApprovalResponseInput.model_validate({"decision": "approve"}),
                    "approve-first-key",
                )
            )
            await asyncio.wait_for(entered.wait(), timeout=1)
            cancel = asyncio.create_task(task_service._cancel("task"))
            await asyncio.sleep(0)
            assert cancel.done() is False

            release.set()
            resolved = await response
            await cancel

            assert resolved.status == ApprovalStatus.APPROVED
            assert resolved.details["deliveryStatus"] == "consumed"
            assert len(directory.adapter.approvals) == 1
            assert tasks.get("task").status == TaskStatus.CANCELLED
            assert tasks.get("task").pending_approval_id is None
            assert tasks.list_nodes("task")[0].status == NodeStatus.CANCELLED
        finally:
            database.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("terminal", [TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED])
def test_late_cancel_preserves_existing_terminal_task(tmp_path: Path, terminal: TaskStatus) -> None:
    async def scenario() -> None:
        database, events, _, approvals, coordinator, tasks = setup(tmp_path)
        try:
            approval = await request_approval(coordinator, f"late-{terminal.value}")
            node_status = (
                NodeStatus.SUCCEEDED
                if terminal == TaskStatus.SUCCEEDED
                else NodeStatus.FAILED
                if terminal == TaskStatus.FAILED
                else NodeStatus.CANCELLED
            )
            save_waiting_task(
                tasks,
                approval_id=approval.id,
                task_status=terminal,
                node_status=node_status,
            )

            class Runtime:
                async def cancel(self, _outcome, *, reason):
                    raise AssertionError("terminal task must not call adapter cancel")

            service = task_service_for(tasks, events, coordinator, Runtime())
            await service._cancel("task")
            assert tasks.get("task").status == terminal
            assert (await approvals.get(approval.id)).status == ApprovalStatus.EXPIRED

            await service._cancel("task")
            assert tasks.get("task").status == terminal
        finally:
            database.close()

    asyncio.run(scenario())
