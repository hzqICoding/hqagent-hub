from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from protocol.generated.python import CreateTaskInput, PageResult, TaskDetailView

from api.app import HubApplication, create_application
from core.ports import HubPorts
from runtime.paths import HubPaths
from storage.database import Database, Transaction
from storage.events import EventDraft, EventStore
from storage.idempotency import IdempotencyRepository


TOKEN = "test_" + "x" * 43


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class TransactionalTaskPort:
    available = True
    unavailable_reason = None

    def __init__(self, database: Database, events: EventStore) -> None:
        self.database = database
        self.events = events
        self.idempotency = IdempotencyRepository(database)

    async def create_task(self, value: CreateTaskInput, idempotency_key: str | None) -> dict[str, Any]:
        raw = value.model_dump(mode="json", by_alias=True, exclude_none=True)

        def create(transaction: Transaction) -> dict[str, Any]:
            created_at = now()
            task_id = f"task_{uuid.uuid4().hex}"
            profile_id = value.profile_id or "profile_default"
            source = value.source.value if value.source else "desktop"
            event, _ = self.events.append(
                transaction,
                EventDraft(
                    aggregate_type="task",
                    aggregate_id=task_id,
                    type="task.created",
                    task_id=task_id,
                    payload={
                        "objective": value.objective,
                        "workspaceId": value.workspace_id,
                        "profileId": profile_id,
                        "source": source,
                    },
                ),
            )
            detail = TaskDetailView.model_validate(
                {
                    "id": task_id,
                    "objective": value.objective,
                    "workspaceId": value.workspace_id,
                    "workspaceName": value.workspace_id,
                    "profileId": profile_id,
                    "profileName": profile_id,
                    "status": "queued",
                    "source": source,
                    "createdAt": created_at,
                    "updatedAt": created_at,
                    "parentTaskId": value.parent_task_id,
                    "nodes": [],
                    "artifacts": [],
                    "events": [event],
                    "allowedPaths": value.allowed_paths,
                    "readFirst": value.read_first,
                    "acceptance": value.acceptance,
                    "requiresApproval": value.requires_approval,
                    "lastEventSeq": event.seq,
                }
            )
            response = detail.model_dump(mode="json", by_alias=True, exclude_none=True)
            transaction.connection.execute(
                "INSERT INTO tasks(task_id,workspace_id,profile_id,objective,status,source,payload_json,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    task_id,
                    value.workspace_id,
                    profile_id,
                    value.objective,
                    "queued",
                    source,
                    json.dumps(response, ensure_ascii=False),
                    created_at,
                    created_at,
                ),
            )
            return response

        return self.idempotency.execute(idempotency_key, "/api/v1/tasks", raw, create)

    async def list_tasks(self, query: dict[str, Any]) -> PageResult:
        with self.database.locked_connection() as connection:
            rows = connection.execute("SELECT payload_json FROM tasks ORDER BY created_at DESC").fetchall()
        items = [TaskDetailView.model_validate_json(row[0]) for row in rows]
        return PageResult.model_validate(
            {"items": items, "total": len(items), "page": 1, "pageSize": 50, "hasMore": False}
        )

    async def get_task(self, task_id: str) -> TaskDetailView:
        with self.database.locked_connection() as connection:
            row = connection.execute("SELECT payload_json FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return TaskDetailView.model_validate_json(row[0])

    async def act(self, task_id: str, value: Any, idempotency_key: str | None) -> Any:
        return await self.get_task(task_id)


@pytest.fixture
def hub(tmp_path: Path) -> HubApplication:
    paths = HubPaths.resolve(tmp_path / "HQAgent-Hub")
    class DeferredTaskPort:
        available = True
        unavailable_reason = None

        def bind(self, application: HubApplication) -> None:
            self.delegate = TransactionalTaskPort(application.database, application.events)

        async def list_tasks(self, query: dict[str, Any]) -> Any:
            return await self.delegate.list_tasks(query)

        async def create_task(self, value: Any, key: str | None) -> Any:
            return await self.delegate.create_task(value, key)

        async def get_task(self, task_id: str) -> Any:
            return await self.delegate.get_task(task_id)

        async def act(self, task_id: str, value: Any, key: str | None) -> Any:
            return await self.delegate.act(task_id, value, key)

    deferred = DeferredTaskPort()
    ports = replace(HubPorts.unavailable_defaults(), tasks=deferred)
    application = create_application(
        paths=paths,
        token=TOKEN,
        ports=ports,
        environment="test",
        allowed_origins={"http://localhost:1420"},
        allowed_hosts={"testserver", "127.0.0.1"},
        close_database_on_shutdown=False,
    )
    deferred.bind(application)
    yield application
    application.database.close()


@pytest.fixture
def client(hub: HubApplication):
    with TestClient(hub.app) as value:
        yield value


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}", "Origin": "http://localhost:1420"}
