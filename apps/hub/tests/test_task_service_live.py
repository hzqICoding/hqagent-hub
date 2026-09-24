from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from protocol.generated.python import AgentResult, CreateTaskInput, TaskActionInput, TeamProfileView

from orchestrator.catalog import BuiltinCatalog
from orchestrator.role_resolver import RoleResolver
from orchestrator.runtime import WorkflowRuntime
from orchestrator.sessions import SessionManager
from orchestrator.tests.fakes import FakeAdapter, FakeAdapterDirectory, agent
from runtime.repositories import EventSink, SessionRepository
from runtime.tasks import TaskService
from security.permissions import PermissionEngine
from storage.database import Database
from storage.events import EventStore
from storage.tasks import TaskRepository


class Profiles:
    def __init__(self) -> None:
        self.profile = TeamProfileView.model_validate(
            {
                "id": "profile_default",
                "name": "default",
                "scope": "global",
                "isDefault": True,
                "roleBindings": {},
                "updatedAt": "2026-09-24T00:00:00Z",
            }
        )

    async def get_profile(self, profile_id: str):
        assert profile_id == self.profile.id
        return self.profile

    async def list_profiles(self):
        return [self.profile]


class Workspaces:
    def __init__(self, path: Path, *, can_write: bool = False) -> None:
        self.item = SimpleNamespace(
            id="workspace",
            name="workspace",
            path=str(path),
            vcs="none" if not can_write else "git",
            capabilities=SimpleNamespace(
                can_run_write_tasks=can_write,
                reason=None if can_write else "read only workspace",
            ),
        )

    async def list_workspaces(self, search, limit):
        return [self.item]


def build_service(
    tmp_path: Path,
    *,
    result_status: str = "done",
    candidate_ids: tuple[str, ...] = ("agent",),
):
    database = Database(tmp_path / "hub.db")
    database.initialize()
    events = EventSink(database, EventStore(database))
    adapter = FakeAdapter()
    adapter.result = AgentResult.model_validate(
        {"status": result_status, "summary": result_status, "changedFiles": []}
    )
    directory = FakeAdapterDirectory(
        tuple(agent(item, capabilities=("structured_output",)) for item in candidate_ids),
        adapter,
    )
    catalog = BuiltinCatalog.load()
    sessions = SessionManager(SessionRepository(database), directory)
    runtime = WorkflowRuntime(
        RoleResolver(catalog),
        PermissionEngine(catalog),
        sessions,
        directory,
        events,
    )
    service = TaskService(
        TaskRepository(database),
        runtime,
        directory,
        Profiles(),
        events,
        Workspaces(tmp_path / "plain-directory"),
    )
    return service, adapter, database


async def settle(service: TaskService) -> None:
    while service._pumps:
        await asyncio.gather(*tuple(service._pumps.values()), return_exceptions=True)


def task_input(**overrides):
    raw = {
        "objective": "inspect code",
        "workspaceId": "workspace",
        "workflowRoles": ["analyst"],
        "roleOverrides": {"analyst": "agent"},
        "roleExecutions": {
            "analyst": {
                "modelId": "model-test",
                "reasoningEffort": "medium",
                "instructions": "read only",
            }
        },
    }
    raw.update(overrides)
    return CreateTaskInput.model_validate(raw)


def test_real_task_service_is_idempotent_and_read_only_uses_workspace(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, adapter, database = build_service(tmp_path)
        value = task_input()
        first = await service.create_task(value, "same-key")
        await settle(service)
        second = await service.create_task(value, "same-key")
        assert first.id == second.id
        assert len(adapter.started) == 1
        spec = adapter.started[0]
        assert spec.worktree_path == str(tmp_path / "plain-directory")
        assert spec.read_only is True
        assert spec.model_id_ == "model-test"
        assert spec.reasoning_effort == "medium"
        assert spec.role_instructions == "read only"
        with database.locked_connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM events WHERE type='task.created'").fetchone()[0] == 1
        database.close()

    asyncio.run(scenario())


def test_read_only_stages_receive_upstream_analysis(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, adapter, database = build_service(tmp_path)
        adapter.result = AgentResult(status="done", summary="UPSTREAM_PLAN_MARKER", changedFiles=[])
        value = task_input(workflowRoles=["planner", "analyst"])
        await service.create_task(value, "handoff-key")
        await settle(service)
        assert len(adapter.started) == 2
        assert "UPSTREAM_PLAN_MARKER" in adapter.started[1].objective
        database.close()
    asyncio.run(scenario())


def test_task_deduplication_survives_old_receipt_expiry(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, adapter, database = build_service(tmp_path)
        value = task_input()
        first = await service.create_task(value, "durable-key")
        await settle(service)
        with database.transaction() as tx:
            tx.connection.execute("UPDATE idempotency_records SET expires_at='2000-01-01T00:00:00Z' WHERE key='durable-key'")
        second = await service.create_task(value, "durable-key")
        assert first.id == second.id and len(adapter.started) == 1
        database.close()
    asyncio.run(scenario())


def test_role_override_wins_for_explicit_read_only_workflow(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, adapter, database = build_service(
            tmp_path,
            candidate_ids=("automatic", "chosen"),
        )
        value = task_input(workflowRoles=["analyst"], roleOverrides={"analyst": "chosen"})
        detail = await service.create_task(value, "override-key")
        await settle(service)
        detail = await service.get_task(detail.id)
        assert detail.nodes[0].role_id == "analyst"
        assert detail.nodes[0].resolved_agent_id == "chosen"
        assert len(adapter.started) == 1
        assert adapter.started[0].read_only is True
        database.close()

    asyncio.run(scenario())


def test_failed_agent_result_never_becomes_succeeded(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, _, database = build_service(tmp_path, result_status="failed")
        created = await service.create_task(task_input(), "failed-key")
        await settle(service)
        detail = await service.get_task(created.id)
        assert detail.status.value == "failed"
        assert detail.nodes[0].status.value == "failed"
        assert detail.result is not None and detail.result.status == "failed"
        database.close()

    asyncio.run(scenario())


def test_append_creates_child_and_resumes_with_persisted_spec(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, adapter, database = build_service(tmp_path)
        parent = await service.create_task(task_input(), "parent-key")
        await settle(service)
        child = await service.act(
            parent.id,
            TaskActionInput.model_validate(
                {"action": "append_instruction", "instruction": "continue analysis"}
            ),
            "append-key",
        )
        await settle(service)
        child = await service.get_task(child.id)
        assert child.parent_task_id == parent.id
        assert child.objective == "continue analysis"
        assert adapter.resumed
        assert adapter.resumed[-1].task_spec is not None
        assert adapter.resumed[-1].task_spec.model_id_ == "model-test"
        database.close()

    asyncio.run(scenario())


def test_recovery_marks_unknown_running_task_paused(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, adapter, database = build_service(tmp_path)
        gate = asyncio.Event()

        async def blocked_stream(session_id: str):
            await gate.wait()
            if False:
                yield None

        adapter.stream_events = blocked_stream
        created = await service.create_task(task_input(), "recover-key")
        assert (await service.get_task(created.id)).status.value == "running"
        for pump in tuple(service._pumps.values()):
            pump.cancel()
        await asyncio.gather(*tuple(service._pumps.values()), return_exceptions=True)
        replacement, _, _ = build_service_from_database(tmp_path, database)
        recovered = await replacement.recover_pending()
        detail = await replacement.get_task(created.id)
        assert recovered == (created.id,)
        assert detail.status.value == "paused"
        assert detail.failure_reason and "无法确认" in detail.failure_reason
        database.close()

    asyncio.run(scenario())


def build_service_from_database(tmp_path: Path, database: Database):
    events = EventSink(database, EventStore(database))
    adapter = FakeAdapter()
    directory = FakeAdapterDirectory((agent("agent", capabilities=("structured_output",)),), adapter)
    catalog = BuiltinCatalog.load()
    runtime = WorkflowRuntime(
        RoleResolver(catalog),
        PermissionEngine(catalog),
        SessionManager(SessionRepository(database), directory),
        directory,
        events,
    )
    service = TaskService(
        TaskRepository(database),
        runtime,
        directory,
        Profiles(),
        events,
        Workspaces(tmp_path / "plain-directory"),
    )
    return service, adapter, database
