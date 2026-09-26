from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from protocol.generated.python import (
    CreateLocalConversationInput, SaveLocalSceneInput, SendLocalMessageInput,
    TaskActionInput, TaskDetailView, TaskStatus, UpdateLocalConversationInput,
)
from api.app import create_application
from core.errors import HubError
from core.local_auth import COOKIE_NAME, LocalBrowserAuth
from core.ports import HubPorts
from runtime.paths import HubPaths
from runtime.local_chat import LocalChatService
from storage.database import Database
from storage.local_chat import LocalChatRepository


@pytest.fixture
def chat_repo(tmp_path):
    db = Database(tmp_path / "chat.db")
    db.initialize()
    yield LocalChatRepository(db)
    db.close()


def conversation(repo):
    return repo.create_conversation(CreateLocalConversationInput(title="Q20", workspaceId="ws", sceneId="analyze"), "create-q20")


def test_message_atomic_deduplication_and_frozen_scene(chat_repo):
    conv = conversation(chat_repo)
    value = SendLocalMessageInput(clientMessageId="msg-1", text="梳理RTK", sessionMode="new")
    a = chat_repo.enqueue(conv.id, value, "msg-1")
    b = chat_repo.enqueue(conv.id, value, "msg-1")
    assert a.run_id == b.run_id and b.duplicate
    replay = chat_repo.enqueue(conv.id, value, "another-http-retry-key")
    assert replay.run_id == a.run_id and replay.duplicate
    assert len(chat_repo.messages(conv.id)) == 1
    scene = chat_repo.scene("analyze")
    changed = scene.roles[0].model_copy(update={"instructions": "新的职责"})
    chat_repo.save_scene("analyze", SaveLocalSceneInput(roles=[changed], expectedVersion=scene.version))
    assert chat_repo.scene("analyze").version == 2
    assert chat_repo.view(chat_repo.run_record(a.run_id)).scene_snapshot.version == 1
    with pytest.raises(HubError, match="不同内容"):
        chat_repo.enqueue(conv.id, value.model_copy(update={"text": "另一个任务"}), "msg-1")


def test_conversation_metadata_version_archive_and_idempotency(chat_repo):
    conv = conversation(chat_repo)
    assert conv.version == 1 and conv.archived is False
    renamed = chat_repo.update_conversation(
        conv.id, UpdateLocalConversationInput(expectedVersion=1, title="  RTK 项目  "), "rename-1"
    )
    replay = chat_repo.update_conversation(
        conv.id, UpdateLocalConversationInput(expectedVersion=1, title="  RTK 项目  "), "rename-1"
    )
    assert renamed.title == "RTK 项目" and renamed.version == 2
    assert replay.version == 2
    with pytest.raises(HubError) as mismatch:
        chat_repo.update_conversation(
            conv.id, UpdateLocalConversationInput(expectedVersion=1, archived=False), "rename-1"
        )
    assert mismatch.value.code == "IDEMPOTENCY_MISMATCH"
    with pytest.raises(HubError) as stale:
        chat_repo.update_conversation(
            conv.id, UpdateLocalConversationInput(expectedVersion=1, archived=True), "archive-stale"
        )
    assert stale.value.code == "CONFLICT"
    for value in (
        UpdateLocalConversationInput(expectedVersion=2),
        UpdateLocalConversationInput(expectedVersion=2, title=None),
        UpdateLocalConversationInput(expectedVersion=2, title="   "),
        UpdateLocalConversationInput(expectedVersion=2, archived=None),
    ):
        with pytest.raises(HubError) as invalid:
            chat_repo.update_conversation(conv.id, value, uid_for(value))
        assert invalid.value.code == "VALIDATION_FAILED"


def uid_for(value):
    return "invalid-" + str(abs(hash(repr(value.model_dump()))))


def test_archive_blocks_messages_until_restored_and_metadata_survives_reopen(tmp_path):
    path = tmp_path / "metadata.db"
    db = Database(path)
    db.initialize()
    repo = LocalChatRepository(db)
    conv = conversation(repo)
    archived = repo.update_conversation(
        conv.id, UpdateLocalConversationInput(expectedVersion=1, archived=True), "archive"
    )
    assert archived.archived is True and archived.version == 2
    with pytest.raises(HubError) as blocked:
        repo.enqueue(
            conv.id, SendLocalMessageInput(clientMessageId="blocked", text="不能执行", sessionMode="new"),
            "blocked",
        )
    assert blocked.value.code == "CONFLICT"
    restored = repo.update_conversation(
        conv.id, UpdateLocalConversationInput(expectedVersion=2, archived=False), "restore"
    )
    receipt = repo.enqueue(
        conv.id, SendLocalMessageInput(clientMessageId="allowed", text="恢复后执行", sessionMode="new"),
        "allowed",
    )
    assert restored.version == 3 and receipt.status == "queued"
    assert repo.conversation(conv.id).version == 3  # enqueue is not a metadata edit
    with db.locked_connection() as connection:
        payload = json.loads(connection.execute(
            "SELECT payload_json FROM local_conversations WHERE conversation_id=?", (conv.id,)
        ).fetchone()[0])
    assert "lastRunStatus" not in payload
    db.close()
    reopened = Database(path)
    reopened.initialize()
    restored_repo = LocalChatRepository(reopened)
    value = restored_repo.conversation(conv.id)
    assert value.version == 3 and value.archived is False
    assert value.last_run_status == TaskStatus.QUEUED
    reopened.close()


def test_legacy_conversation_defaults_and_list_has_no_200_item_cutoff(chat_repo):
    conv = conversation(chat_repo)
    with chat_repo.database.transaction() as tx:
        raw = json.loads(tx.connection.execute(
            "SELECT payload_json FROM local_conversations WHERE conversation_id=?", (conv.id,)
        ).fetchone()[0])
        raw.pop("version", None)
        raw.pop("archived", None)
        tx.connection.execute(
            "UPDATE local_conversations SET payload_json=? WHERE conversation_id=?",
            (json.dumps(raw), conv.id),
        )
    assert chat_repo.conversation(conv.id).version == 1
    assert chat_repo.conversation(conv.id).archived is False
    for index in range(201):
        chat_repo.create_conversation(
            CreateLocalConversationInput(title=f"conversation-{index}", workspaceId="ws", sceneId="analyze"),
            f"bulk-{index}",
        )
    assert len(chat_repo.conversations()) == 202


def test_archive_and_enqueue_are_one_atomic_decision(chat_repo):
    conv = conversation(chat_repo)
    gate = threading.Barrier(2)

    def archive():
        gate.wait()
        return chat_repo.update_conversation(
            conv.id, UpdateLocalConversationInput(expectedVersion=1, archived=True), "archive-race"
        )

    def enqueue():
        gate.wait()
        return chat_repo.enqueue(
            conv.id, SendLocalMessageInput(clientMessageId="message-race", text="race", sessionMode="new"),
            "message-race",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(archive), pool.submit(enqueue)]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(("ok", future.result()))
            except HubError as error:
                outcomes.append((error.code, None))
    assert [kind for kind, _ in outcomes].count("ok") == 1
    assert [kind for kind, _ in outcomes].count("CONFLICT") == 1
    current = chat_repo.conversation(conv.id)
    assert bool(current.archived) != bool(chat_repo.messages(conv.id))


def test_archive_and_last_status_use_actual_task_projection(chat_repo):
    conv = conversation(chat_repo)
    receipt = chat_repo.enqueue(
        conv.id, SendLocalMessageInput(clientMessageId="actual", text="actual", sessionMode="new"),
        "actual",
    )
    stamp = "2026-09-26T00:00:00Z"
    with chat_repo.database.transaction() as tx:
        tx.connection.execute(
            "INSERT INTO tasks(task_id,workspace_id,profile_id,objective,status,source,payload_json,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            ("task-actual", "ws", None, "actual", "running", "desktop", "{}", stamp, stamp),
        )
        tx.connection.execute(
            "UPDATE local_runs SET task_id=?,status='failed' WHERE run_id=?",
            ("task-actual", receipt.run_id),
        )
    assert chat_repo.conversation(conv.id).last_run_status == TaskStatus.RUNNING
    with pytest.raises(HubError) as active:
        chat_repo.update_conversation(
            conv.id, UpdateLocalConversationInput(expectedVersion=1, archived=True), "actual-active"
        )
    assert active.value.code == "CONFLICT"
    with chat_repo.database.transaction() as tx:
        tx.connection.execute("UPDATE tasks SET status='succeeded' WHERE task_id='task-actual'")
    archived = chat_repo.update_conversation(
        conv.id, UpdateLocalConversationInput(expectedVersion=1, archived=True), "actual-terminal"
    )
    assert archived.archived is True
    assert archived.last_run_status == TaskStatus.SUCCEEDED


def test_scene_conflict_and_invalid_role_are_rejected(chat_repo):
    scene = chat_repo.scene("analyze")
    value = SaveLocalSceneInput(roles=scene.roles, expectedVersion=1)
    chat_repo.save_scene("analyze", value)
    with pytest.raises(HubError, match="刷新"):
        chat_repo.save_scene("analyze", value)
    with pytest.raises(HubError, match="角色"):
        chat_repo.save_scene("analyze", SaveLocalSceneInput(roles=[scene.roles[0].model_copy(update={"role_id": "developer"})], expectedVersion=2))


def test_auth_code_single_use_expiry_and_logout():
    auth = LocalBrowserAuth()
    code = auth.issue_code("test-local-code")
    cookie = auth.exchange(code)
    assert auth.valid(cookie)
    with pytest.raises(HubError):
        auth.exchange(code)
    auth.logout(cookie)
    assert not auth.valid(cookie)
    expired = LocalBrowserAuth(code_ttl=-1)
    code = expired.issue_code()
    with pytest.raises(HubError):
        expired.exchange(code)


class Workspaces:
    async def list_workspaces(self, *_args):
        return [SimpleNamespace(id="ws")]


class Profiles:
    available = True
    def __init__(self):
        self.values = {}
    async def save_profile(self, profile_id, value):
        self.values[profile_id] = value
        return value


class Tasks:
    available = True
    def __init__(self):
        self.started = []
        self.items = {}
    async def create_task(self, value, key):
        self.started.append((value, key))
        identifier = f"task-{len(self.started)}"
        task = TaskDetailView.model_validate({"id": identifier, "objective": value.objective,
            "workspaceId": "ws", "workspaceName": "Q20", "profileId": value.profile_id,
            "profileName": "分析", "status": "succeeded", "source": "desktop",
            "createdAt": "2026-09-24T00:00:00Z", "updatedAt": "2026-09-24T00:00:00Z",
            "nodes": [], "events": [], "artifacts": [], "result": {"status": "done", "summary": "RTK分析结果"}})
        self.items[identifier] = task
        return task
    async def get_task(self, task_id):
        return self.items[task_id]


def test_local_cookie_api_to_queue_and_result(tmp_path):
    tasks, profiles = Tasks(), Profiles()
    ports = replace(HubPorts.unavailable_defaults(), tasks=tasks, workspaces=Workspaces(), team_profiles=profiles)
    hub = create_application(paths=HubPaths.resolve(tmp_path), token="private-hub-token", ports=ports,
        allowed_hosts={"testserver"}, allowed_origins={"http://testserver"}, environment="test")
    code = hub.local_auth.issue_code("local-123456")
    with TestClient(hub.app) as client:
        assert client.get("/api/v2/scenes").status_code == 401
        bad = client.post("/api/v2/auth/local-session", json={"code": code}, headers={"Origin": "https://evil.example"})
        assert bad.status_code == 403
        response = client.post("/api/v2/auth/local-session", json={"code": code}, headers={"Origin": "http://testserver"})
        assert response.status_code == 200 and COOKIE_NAME in client.cookies
        assert "private-hub-token" not in response.text
        assert "httponly" in response.headers["set-cookie"].lower()
        assert client.get("/api/v1/tasks").status_code == 401  # cookie grants only local v2
        headers = {"Origin": "http://testserver", "Idempotency-Key": "conv-key"}
        response = client.post("/api/v2/conversations", json={"title": "Q20", "workspaceId": "ws", "sceneId": "analyze"}, headers=headers)
        assert response.status_code == 201, response.text
        conv_id = response.json()["data"]["id"]
        metadata_headers = {"Origin": "http://testserver", "Idempotency-Key": "metadata-key"}
        patch = client.patch(
            f"/api/v2/conversations/{conv_id}",
            json={"expectedVersion": 1, "title": "  Q20 renamed  "}, headers=metadata_headers,
        )
        replay = client.patch(
            f"/api/v2/conversations/{conv_id}",
            json={"expectedVersion": 1, "title": "  Q20 renamed  "}, headers=metadata_headers,
        )
        assert patch.status_code == 200 and patch.json()["data"]["version"] == 2
        assert patch.json()["data"]["title"] == "Q20 renamed"
        assert replay.json()["data"]["version"] == 2
        stale = client.patch(
            f"/api/v2/conversations/{conv_id}", json={"expectedVersion": 1, "archived": True},
            headers={"Origin": "http://testserver", "Idempotency-Key": "stale-key"},
        )
        assert stale.status_code == 409 and stale.json()["error"]["code"] == "CONFLICT"
        archived = client.patch(
            f"/api/v2/conversations/{conv_id}", json={"expectedVersion": 2, "archived": True},
            headers={"Origin": "http://testserver", "Idempotency-Key": "archive-key"},
        )
        assert archived.status_code == 200 and archived.json()["data"]["archived"] is True
        blocked = client.post(
            f"/api/v2/conversations/{conv_id}/messages",
            json={"clientMessageId": "blocked", "text": "blocked", "sessionMode": "new"},
            headers={"Origin": "http://testserver", "Idempotency-Key": "blocked"},
        )
        assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "CONFLICT"
        restored = client.patch(
            f"/api/v2/conversations/{conv_id}", json={"expectedVersion": 3, "archived": False},
            headers={"Origin": "http://testserver", "Idempotency-Key": "restore-key"},
        )
        assert restored.status_code == 200 and restored.json()["data"]["version"] == 4
        headers["Idempotency-Key"] = "message-key"
        body = {"clientMessageId": "message-key", "text": "分析RTK", "sessionMode": "new"}
        first = client.post(f"/api/v2/conversations/{conv_id}/messages", json=body, headers=headers)
        again = client.post(f"/api/v2/conversations/{conv_id}/messages", json=body, headers=headers)
        assert first.status_code == 202, first.text
        assert again.json()["data"]["duplicate"]
        run_id = first.json()["data"]["runId"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            messages = client.get(f"/api/v2/conversations/{conv_id}/messages").json()["data"]
            if any(m["role"] == "assistant" for m in messages):
                break
            time.sleep(0.02)
        assert len(tasks.started) == 1
        assert tasks.started[0][0].workflow_roles == ["analyst"]
        assert messages[-1]["text"] == "RTK分析结果"
        run = client.get(f"/api/v2/runs/{run_id}").json()["data"]
        assert run["status"] == "succeeded" and run["task"]["id"] == "task-1"
        assert client.post("/api/v2/auth/logout", headers={"Origin": "http://testserver"}).status_code == 200
        assert client.get("/api/v2/scenes").status_code == 401


def test_persisted_queue_survives_repository_reopen(tmp_path):
    path = tmp_path / "state.db"
    db = Database(path)
    db.initialize()
    repo = LocalChatRepository(db)
    conv = conversation(repo)
    receipt = repo.enqueue(conv.id, SendLocalMessageInput(clientMessageId="m1", text="继续", sessionMode="new"), "m1")
    db.close()
    db = Database(path)
    db.initialize()
    restored = LocalChatRepository(db)
    assert restored.next_run(conv.id)["run_id"] == receipt.run_id
    assert restored.messages(conv.id)[0].text == "继续"
    db.close()


def test_terminal_state_and_reply_rollback_together(chat_repo):
    conv = conversation(chat_repo)
    item = chat_repo.enqueue(conv.id, SendLocalMessageInput(clientMessageId="atomic", text="read", sessionMode="new"), "atomic")
    with chat_repo.database.transaction() as tx:
        tx.connection.execute("CREATE TEMP TRIGGER break_reply BEFORE INSERT ON local_messages WHEN NEW.role='assistant' BEGIN SELECT RAISE(ABORT, 'simulated disk failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        chat_repo.complete_run(item.run_id, "succeeded", "result")
    assert chat_repo.run_record(item.run_id)["status"] == "queued"
    assert len(chat_repo.messages(conv.id)) == 1
    with chat_repo.database.transaction() as tx:
        tx.connection.execute("DROP TRIGGER break_reply")
    chat_repo.complete_run(item.run_id, "succeeded", "result")
    assert chat_repo.messages(conv.id)[-1].text == "result"


def test_cancel_intent_during_dispatch_is_consumed(chat_repo):
    async def scenario():
        class DelayedTasks(Tasks):
            def __init__(self):
                super().__init__()
                self.entered, self.release = asyncio.Event(), asyncio.Event()
                self.cancelled = 0
            async def create_task(self, value, key):
                self.entered.set()
                await self.release.wait()
                task = await super().create_task(value, key)
                task = task.model_copy(update={"status": TaskStatus.RUNNING})
                self.items[task.id] = task
                return task
            async def act(self, task_id, value, key):
                assert str(value.action) == "cancel"
                self.cancelled += 1
                task = self.items[task_id].model_copy(update={"status": TaskStatus.CANCELLED})
                self.items[task_id] = task
                return task
        tasks = DelayedTasks()
        ports = replace(HubPorts.unavailable_defaults(), tasks=tasks, team_profiles=Profiles(), workspaces=Workspaces())
        service = LocalChatService(chat_repo, ports, poll_seconds=0.01)
        conv = conversation(chat_repo)
        receipt = service.send(conv.id, SendLocalMessageInput(clientMessageId="race", text="read", sessionMode="new"), "race")
        await service.start()
        try:
            await asyncio.wait_for(tasks.entered.wait(), 2)
            from protocol.generated.python import TaskActionInput
            result = await service.control(receipt.run_id, TaskActionInput(action="cancel"), "cancel-race")
            assert str(result.status) == "running"  # not falsely cancelled
            tasks.release.set()
            for _ in range(100):
                if chat_repo.run_record(receipt.run_id)["status"] == "cancelled":
                    break
                await asyncio.sleep(0.01)
            assert tasks.cancelled == 1
            assert chat_repo.messages(conv.id)[-1].role == "assistant"
        finally:
            await service.stop()
    asyncio.run(scenario())


def test_archived_conversation_rejects_retry_before_task_port_action(chat_repo):
    async def scenario():
        class RetryTasks(Tasks):
            def __init__(self):
                super().__init__()
                self.actions = 0

            async def act(self, task_id, value, key):
                self.actions += 1
                raise AssertionError("archived retry reached TaskPort")

        tasks = RetryTasks()
        old_task = await tasks.create_task(SimpleNamespace(objective="old", profile_id="profile"), "old")
        ports = replace(HubPorts.unavailable_defaults(), tasks=tasks, team_profiles=Profiles(), workspaces=Workspaces())
        service = LocalChatService(chat_repo, ports)
        conv = conversation(chat_repo)
        receipt = chat_repo.enqueue(
            conv.id, SendLocalMessageInput(clientMessageId="old", text="old", sessionMode="new"), "old"
        )
        chat_repo.update_run(receipt.run_id, "succeeded", task_id=old_task.id)
        await service.update_conversation(
            conv.id, UpdateLocalConversationInput(expectedVersion=1, archived=True), "archive-old"
        )
        with pytest.raises(HubError) as blocked:
            await service.control(receipt.run_id, TaskActionInput(action="retry"), "retry-archived")
        assert blocked.value.code == "CONFLICT"
        assert tasks.actions == 0

    asyncio.run(scenario())


def test_archive_refresh_commits_terminal_reply_before_metadata(chat_repo):
    async def scenario():
        tasks = Tasks()
        task = await tasks.create_task(SimpleNamespace(objective="done", profile_id="profile"), "done")
        ports = replace(HubPorts.unavailable_defaults(), tasks=tasks, team_profiles=Profiles(), workspaces=Workspaces())
        service = LocalChatService(chat_repo, ports)
        conv = conversation(chat_repo)
        receipt = chat_repo.enqueue(
            conv.id, SendLocalMessageInput(clientMessageId="done", text="done", sessionMode="new"), "done"
        )
        chat_repo.update_run(receipt.run_id, "running", task_id=task.id)
        archived = await service.update_conversation(
            conv.id, UpdateLocalConversationInput(expectedVersion=1, archived=True), "archive-done"
        )
        assert archived.archived is True
        assert chat_repo.run_record(receipt.run_id)["status"] == "succeeded"
        assert chat_repo.messages(conv.id)[-1].text == "RTK分析结果"

    asyncio.run(scenario())


def test_archive_waits_for_retry_action_and_then_observes_new_run(chat_repo):
    async def scenario():
        class DelayedRetryTasks(Tasks):
            def __init__(self):
                super().__init__()
                self.entered, self.release = asyncio.Event(), asyncio.Event()

            async def act(self, task_id, value, key):
                assert str(value.action) == "retry"
                self.entered.set()
                await self.release.wait()
                retried = self.items[task_id].model_copy(
                    update={"id": "task-retry", "status": TaskStatus.QUEUED}
                )
                self.items[retried.id] = retried
                return retried

        tasks = DelayedRetryTasks()
        old_task = await tasks.create_task(SimpleNamespace(objective="old", profile_id="profile"), "old")
        ports = replace(HubPorts.unavailable_defaults(), tasks=tasks, team_profiles=Profiles(), workspaces=Workspaces())
        service = LocalChatService(chat_repo, ports)
        conv = conversation(chat_repo)
        receipt = chat_repo.enqueue(
            conv.id, SendLocalMessageInput(clientMessageId="old-race", text="old", sessionMode="new"),
            "old-race",
        )
        chat_repo.update_run(receipt.run_id, "succeeded", task_id=old_task.id)
        retry = asyncio.create_task(
            service.control(receipt.run_id, TaskActionInput(action="retry"), "retry-race")
        )
        await asyncio.wait_for(tasks.entered.wait(), 2)
        archive = asyncio.create_task(service.update_conversation(
            conv.id, UpdateLocalConversationInput(expectedVersion=1, archived=True), "archive-race-after-retry"
        ))
        await asyncio.sleep(0)
        assert not archive.done()
        tasks.release.set()
        retried = await retry
        assert str(retried.status) == "queued"
        with pytest.raises(HubError) as blocked:
            await archive
        assert blocked.value.code == "CONFLICT"
        assert chat_repo.conversation(conv.id).archived is False

    asyncio.run(scenario())


def test_real_composition_three_chat_turns_reuse_one_session(tmp_path, monkeypatch):
    """Only the vendor boundary is simulated; TaskService and SQL are real."""
    from protocol.generated.python import AgentView
    from orchestrator.tests.fakes import FakeAdapter
    from runtime import composition
    adapter = FakeAdapter()
    view = AgentView.model_validate({"id": "local.test-adapter.default", "adapterId": "test-adapter",
        "displayName": "Contract runtime", "version": "1.0", "status": "ready",
        "detectedAt": "2026-09-24T00:00:00Z", "assignedRoles": [], "isPrimaryFor": [],
        "capabilities": [{"id": k, "name": k, "hard": True, "source": "detected", "supported": True}
                         for k in ["structured_output", "session_resume"]]})
    class Manager:
        available = True
        unavailable_reason = None
        async def list_agents(self):
            return [view]
        def get(self, identifier):
            return adapter if identifier == "test-adapter" else None
    monkeypatch.setattr(composition, "_build_agent_port", lambda: Manager())
    ports = composition.build_ports()
    hub = create_application(paths=HubPaths.resolve(tmp_path / "data"), token="test-token", ports=ports,
        allowed_hosts={"testserver"}, allowed_origins={"http://testserver"}, environment="test")
    asyncio.run(composition.bind_ports(hub, ports))
    code = hub.local_auth.issue_code("test-full-composition")
    workspace = tmp_path / "source"
    workspace.mkdir()
    with TestClient(hub.app) as client:
        common = {"Origin": "http://testserver"}
        assert client.post("/api/v2/auth/local-session", json={"code": code}, headers=common).status_code == 200
        ws = client.post("/api/v2/workspaces", json={"path": str(workspace)}, headers=common).json()["data"]
        response = client.post("/api/v2/conversations", json={"title": "Local", "workspaceId": ws["id"], "sceneId": "analyze"},
            headers={**common, "Idempotency-Key": "full-conv"})
        assert response.status_code == 201, response.text
        conversation_id = response.json()["data"]["id"]
        for turn in range(3):
            key = f"full-message-{turn}"
            receipt = client.post(f"/api/v2/conversations/{conversation_id}/messages",
                json={"clientMessageId": key, "text": f"read-{turn}", "sessionMode": "new" if turn == 0 else "continue"},
                headers={**common, "Idempotency-Key": key})
            assert receipt.status_code == 202, receipt.text
            run_id = receipt.json()["data"]["runId"]
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                run = client.get(f"/api/v2/runs/{run_id}").json()["data"]
                messages = client.get(f"/api/v2/conversations/{conversation_id}/messages").json()["data"]
                if len([m for m in messages if m["role"] == "assistant"]) == turn + 1:
                    break
                time.sleep(0.01)
            assert run["status"] == "succeeded", run
        assert len(adapter.started) == 1
        assert len(adapter.resumed) == 2
        assert all(r.task_spec is not None for r in adapter.resumed)
