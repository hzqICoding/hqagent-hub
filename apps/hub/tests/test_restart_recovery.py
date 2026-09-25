from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from protocol.generated.python import (
    CreateLocalConversationInput,
    SendLocalMessageInput,
    SessionView,
    TaskNodeView,
    TaskSummaryView,
)

from api.app import create_application
from core.ports import HubPorts
from runtime.paths import HubPaths
from runtime.repositories import EventSink, SessionRepository
from runtime.tasks import TaskService
from storage.database import Database
from storage.events import EventStore
from storage.execution_state import ExecutionStateRepository
from storage.local_chat import LocalChatRepository
from storage.tasks import TaskRepository


def stamp(offset: int = 0) -> str:
    value = datetime(2026, 9, 25, tzinfo=timezone.utc) + timedelta(seconds=offset)
    return value.isoformat().replace("+00:00", "Z")


class RecoveryApprovals:
    def __init__(self, pending_task_ids: set[str] | None = None) -> None:
        self.pending_task_ids = pending_task_ids or set()
        self.invalidated: list[tuple[str, str, str]] = []

    async def invalidate_task_pending(
        self,
        task_id: str,
        *,
        reason: str,
        invalidated_by: str,
    ) -> None:
        if task_id not in self.pending_task_ids:
            return
        self.pending_task_ids.remove(task_id)
        self.invalidated.append((task_id, reason, invalidated_by))


class ReceiptWindowTasks:
    available = True
    unavailable_reason = None

    def __init__(self, delegate: TaskService, recovered_task_id: str) -> None:
        self.delegate = delegate
        self.recovered_task_id = recovered_task_id
        self.create_calls: list[str | None] = []

    async def recover_pending(self):
        return await self.delegate.recover_pending()

    async def shutdown(self):
        return await self.delegate.shutdown()

    async def get_task(self, task_id: str):
        return await self.delegate.get_task(task_id)

    async def create_task(self, _value, idempotency_key: str | None):
        self.create_calls.append(idempotency_key)
        return await self.delegate.get_task(self.recovered_task_id)


class ProfileSink:
    available = True
    unavailable_reason = None

    async def save_profile(self, _profile_id, value):
        return value


def build_recovery_service(
    database,
    *,
    pending_approval_tasks: set[str] | None = None,
) -> tuple[TaskService, RecoveryApprovals]:
    sessions = SessionRepository(database)
    runtime = SimpleNamespace(sessions=SimpleNamespace(repository=sessions))
    events = EventSink(database, EventStore(database))
    approvals = RecoveryApprovals(pending_approval_tasks)
    return (
        TaskService(
            TaskRepository(database),
            runtime,
            directory=SimpleNamespace(),
            profiles=SimpleNamespace(),
            events=events,
            workspaces=SimpleNamespace(),
            approval_coordinator=approvals,
        ),
        approvals,
    )


def save_task(database, index: int, status: str, node_status: str = "pending") -> str:
    task_id = f"task_restart_{index:03d}"
    node_id = f"node_restart_{index:03d}"
    created_at = stamp(index)
    TaskRepository(database).save(
        TaskSummaryView.model_validate(
            {
                "id": task_id,
                "objective": f"restart recovery {index}",
                "workspaceId": "workspace_restart",
                "workspaceName": "restart fixture",
                "profileId": "profile_restart",
                "profileName": "restart fixture",
                "status": status,
                "source": "desktop",
                "createdAt": created_at,
                "updatedAt": created_at,
            }
        )
    )
    session_id = f"session_restart_{index:03d}" if node_status != "pending" else None
    TaskRepository(database).save_node(
        TaskNodeView.model_validate(
            {
                "id": node_id,
                "taskId": task_id,
                "roleId": "analyst",
                "resolvedAgentId": "agent_restart",
                "resolvedAgentName": "Restart Fixture",
                "resolveSource": "manual",
                "status": node_status,
                "sessionId": session_id,
            }
        )
    )
    ExecutionStateRepository(database).put(
        f"task_spec:{task_id}",
        {
            "request": {},
            "profile": {},
            "workspace": {},
            "worktrees": {},
        },
    )
    return task_id


async def save_session(
    database,
    session_id: str,
    task_id: str,
    node_id: str,
    status: str,
) -> None:
    await SessionRepository(database).save(
        SessionView.model_validate(
            {
                "id": session_id,
                "status": status,
                "workspaceId": "workspace_restart",
                "workspaceName": "restart fixture",
                "roleId": "analyst",
                "agentInstanceId": "agent_restart",
                "agentDisplayName": "Restart Fixture",
                "adapterId": "codex",
                "externalSessionId": f"native_{session_id}",
                "purpose": "adhoc",
                "reusePolicy": "new_session",
                "taskId": task_id,
                "nodeId": node_id,
                "createdAt": stamp(),
                "lastUsedAt": stamp(),
                "isValid": status in {"active", "idle"},
            }
        )
    )


def test_restart_recovers_all_pages_without_replaying_and_preserves_session_history(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        paths = HubPaths.resolve(tmp_path / "restart-data")
        first_ports = HubPorts.unavailable_defaults()
        first = create_application(paths=paths, token="restart-token-1", ports=first_ports)
        database = first.database

        task_ids = [save_task(database, index, "queued") for index in range(205)]
        running_id = save_task(database, 205, "running", "running")
        approval_id = save_task(database, 206, "waiting_approval", "waiting_approval")
        approval_task = TaskRepository(database).get(approval_id)
        TaskRepository(database).save(
            approval_task.model_copy(update={"pending_approval_id": "approval_restart_206"})
        )
        blocked_id = save_task(database, 207, "queued")
        blocked_spec = ExecutionStateRepository(database).get(f"task_spec:{blocked_id}")
        assert blocked_spec is not None
        blocked_spec["blockedByParent"] = "task_parent"
        ExecutionStateRepository(database).put(f"task_spec:{blocked_id}", blocked_spec)

        await save_session(
            database,
            "session_restart_205",
            running_id,
            "node_restart_205",
            "active",
        )
        await save_session(
            database,
            "session_dispatch_window",
            task_ids[-1],
            f"node_restart_{204:03d}",
            "active",
        )
        await save_session(
            database,
            "session_restart_206",
            approval_id,
            "node_restart_206",
            "active",
        )
        await save_session(database, "session_idle", "task_history", "node_history", "idle")
        await save_session(database, "session_closed", "task_history", "node_history", "closed")

        local_chat = LocalChatRepository(database)
        conversation = local_chat.create_conversation(
            CreateLocalConversationInput.model_validate(
                {
                    "title": "restart projection",
                    "workspaceId": "workspace_restart",
                    "sceneId": "analyze",
                }
            ),
            "conversation-restart",
        )
        receipt = local_chat.enqueue(
            conversation.id,
            SendLocalMessageInput.model_validate(
                {
                    "clientMessageId": "message-restart",
                    "text": "do not replay this task",
                    "sessionMode": "new",
                }
            ),
            "message-restart",
        )
        local_chat.update_run(receipt.run_id, "running", task_id=running_id)
        receipt_window_conversation = local_chat.create_conversation(
            CreateLocalConversationInput.model_validate(
                {
                    "title": "task receipt window",
                    "workspaceId": "workspace_restart",
                    "sceneId": "analyze",
                }
            ),
            "conversation-receipt-window",
        )
        receipt_window = local_chat.enqueue(
            receipt_window_conversation.id,
            SendLocalMessageInput.model_validate(
                {
                    "clientMessageId": "message-receipt-window",
                    "text": "recover the durable task receipt",
                    "sessionMode": "new",
                }
            ),
            "message-receipt-window",
        )
        local_chat.update_run(receipt_window.run_id, "running")
        database.close()

        second_ports = HubPorts.unavailable_defaults()
        second = create_application(paths=paths, token="restart-token-2", ports=second_ports)
        recovery, approvals = build_recovery_service(
            second.database,
            pending_approval_tasks={approval_id},
        )
        receipt_tasks = ReceiptWindowTasks(recovery, task_ids[-2])
        second_ports.tasks = receipt_tasks
        second_ports.team_profiles = ProfileSink()

        async with second.app.router.lifespan_context(second.app):
            for _ in range(50):
                records = LocalChatRepository(second.database)
                if (
                    records.run_record(receipt.run_id)["status"] == "paused"
                    and records.run_record(receipt_window.run_id)["status"] == "paused"
                ):
                    break
                await asyncio.sleep(0.02)

            repository = TaskRepository(second.database)
            assert repository.get(task_ids[0]).status.value == "paused"
            assert repository.get(task_ids[-1]).status.value == "paused"
            assert repository.get(running_id).status.value == "paused"
            assert repository.get(approval_id).status.value == "paused"
            assert repository.get(approval_id).pending_approval_id is None
            assert repository.get(blocked_id).status.value == "queued"
            assert LocalChatRepository(second.database).run_record(receipt.run_id)["status"] == "paused"
            receipt_window_record = LocalChatRepository(second.database).run_record(
                receipt_window.run_id
            )
            assert receipt_window_record["status"] == "paused"
            assert receipt_window_record["task_id"] == task_ids[-2]
            assert receipt_tasks.create_calls == [f"local-run:{receipt_window.run_id}"]

            running_node = repository.list_nodes(running_id)[0]
            approval_node = repository.list_nodes(approval_id)[0]
            assert running_node.status.value == "failed"
            assert approval_node.status.value == "failed"
            assert "无法确认" in (running_node.error or "")

            sessions = SessionRepository(second.database)
            assert (await sessions.get("session_restart_205")).status.value == "invalid"
            assert (await sessions.get("session_restart_206")).status.value == "invalid"
            assert (await sessions.get("session_dispatch_window")).status.value == "invalid"
            assert (await sessions.get("session_idle")).status.value == "idle"
            assert (await sessions.get("session_closed")).status.value == "closed"
            assert len(approvals.invalidated) == 1
            invalidated_task_id, invalidated_reason, invalidated_by = approvals.invalidated[0]
            assert invalidated_task_id == approval_id
            assert "无法确认" in invalidated_reason
            assert invalidated_by == "restart_recovery"

            with second.database.locked_connection() as connection:
                assert connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 208
                assert connection.execute(
                    "SELECT COUNT(*) FROM events WHERE type='task.status_changed'"
                ).fetchone()[0] == 207

    asyncio.run(scenario())


def test_restart_finishes_legacy_paused_recovery_residue_only_once(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = Database(tmp_path / "legacy-paused" / "hub.db")
        database.initialize()
        task_id = save_task(database, 1, "paused", "waiting_approval")
        task = TaskRepository(database).get(task_id)
        TaskRepository(database).save(
            task.model_copy(update={"pending_approval_id": "approval_legacy"})
        )
        spec = ExecutionStateRepository(database).get(f"task_spec:{task_id}")
        assert spec is not None
        spec["recoveryRequired"] = True
        spec["failureReason"] = "旧版本 shutdown 仅暂停 Task"
        ExecutionStateRepository(database).put(f"task_spec:{task_id}", spec)
        await save_session(
            database,
            "session_legacy_active",
            task_id,
            "node_restart_001",
            "active",
        )
        service, approvals = build_recovery_service(
            database,
            pending_approval_tasks={task_id},
        )

        first = await service.recover_pending()
        settled = TaskRepository(database).get(task_id)
        first_updated_at = settled.updated_at
        second = await service.recover_pending()

        assert first == (task_id,)
        assert second == ()
        assert TaskRepository(database).get(task_id).updated_at == first_updated_at
        assert TaskRepository(database).get(task_id).pending_approval_id is None
        assert TaskRepository(database).list_nodes(task_id)[0].status.value == "failed"
        session = await SessionRepository(database).get("session_legacy_active")
        assert session is not None and session.status.value == "invalid"
        assert len(approvals.invalidated) == 1
        with database.locked_connection() as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM events WHERE type='task.status_changed'"
            ).fetchone()[0] == 1
        database.close()

    asyncio.run(scenario())


def test_shutdown_quarantines_persisted_queued_work_without_an_in_memory_pump(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        database = Database(tmp_path / "shutdown" / "hub.db")
        database.initialize()
        task_id = save_task(database, 1, "queued")
        await save_session(
            database,
            "session_shutdown_window",
            task_id,
            "node_restart_001",
            "active",
        )
        service, _ = build_recovery_service(database)

        assert not service._pumps
        assert not service._outcomes
        await service.shutdown()

        assert TaskRepository(database).get(task_id).status.value == "paused"
        session = await SessionRepository(database).get("session_shutdown_window")
        assert session is not None and session.status.value == "invalid"
        database.close()

    asyncio.run(scenario())
