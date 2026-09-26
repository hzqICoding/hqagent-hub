from __future__ import annotations

import asyncio
import json
import time
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from protocol.generated.python import (
    AgentView,
    CreateLocalConversationInput,
    CreateLocalRoleTemplateInput,
    CreateLocalSceneInput,
    LocalBaseRoleId,
    LocalRoleConfig,
    SaveLocalSceneInput,
    SendLocalMessageInput,
    UpdateLocalRoleTemplateInput,
)

from api.app import create_application
from core.errors import HubError
from core.ports import HubPorts
from orchestrator.tests.fakes import FakeAdapter
from runtime.paths import HubPaths
from storage.database import Database
from storage.local_chat import LocalChatRepository


def role(role_id: str, *, enabled: bool = True, agent: str = "",
         instructions: str | None = None, role_name: str | None = None,
         template_id: str | None = None, template_version: int | None = None,
         model_id: str | None = None, effort: str | None = None) -> LocalRoleConfig:
    return LocalRoleConfig.model_validate({
        "roleId": role_id,
        "agentInstanceId": agent,
        "instructions": instructions if instructions is not None else f"{role_id} instructions",
        "enabled": enabled,
        "roleName": role_name,
        "roleTemplateId": template_id,
        "roleTemplateVersion": template_version,
        "modelId": model_id,
        "reasoningEffort": effort,
    })


@pytest.fixture
def repository(tmp_path: Path):
    database = Database(tmp_path / "custom-scenes.db")
    database.initialize()
    yield LocalChatRepository(database)
    database.close()


def test_role_template_crud_idempotency_conflict_and_persistence(tmp_path: Path) -> None:
    path = tmp_path / "templates.db"
    database = Database(path)
    database.initialize()
    repository = LocalChatRepository(database).role_templates
    with pytest.raises(HubError, match="不能为null"):
        repository.create(
            CreateLocalRoleTemplateInput.model_construct(
                name=None, base_role_id=LocalBaseRoleId.ANALYST, instructions=""
            ),
            "template-null-name",
        )
    value = CreateLocalRoleTemplateInput(
        name="  安全审查  ", baseRoleId="reviewer", instructions=""
    )
    created = repository.create(value, "template-create")
    replay = repository.create(value, "template-create")
    assert created.id.startswith("role_template_")
    assert created.name == "安全审查" and created.instructions == "" and created.version == 1
    assert replay.id == created.id and replay.version == 1
    with pytest.raises(HubError) as mismatch:
        repository.create(
            value.model_copy(update={"instructions": "different"}), "template-create"
        )
    assert mismatch.value.code == "IDEMPOTENCY_MISMATCH"
    updated_value = UpdateLocalRoleTemplateInput(
        expectedVersion=1, name="  严格审查  ", instructions="检查权限边界"
    )
    updated = repository.update(created.id, updated_value, "template-update")
    updated_replay = repository.update(created.id, updated_value, "template-update")
    assert updated.name == "严格审查" and updated.version == 2
    assert updated.base_role_id == created.base_role_id
    assert updated_replay.version == 2
    with pytest.raises(HubError, match="不能为null"):
        repository.update(
            created.id,
            UpdateLocalRoleTemplateInput.model_construct(
                expected_version=2, name="valid", instructions=None
            ),
            "template-null-instructions",
        )
    with pytest.raises(HubError) as stale:
        repository.update(
            created.id,
            UpdateLocalRoleTemplateInput(expectedVersion=1, name="stale", instructions=""),
            "template-stale",
        )
    assert stale.value.code == "CONFLICT"
    database.close()

    reopened = Database(path)
    reopened.initialize()
    templates = LocalChatRepository(reopened).role_templates.templates()
    assert [(item.id, item.version, item.instructions) for item in templates] == [
        (created.id, 2, "检查权限边界")
    ]
    reopened.close()


def test_migration_v5_preserves_v4_chat_data(tmp_path: Path) -> None:
    path = tmp_path / "migration.db"
    database = Database(path)
    database.initialize(target_version=4)
    repository = LocalChatRepository(database)
    conversation = repository.create_conversation(
        CreateLocalConversationInput(title="legacy", workspaceId="ws", sceneId="analyze"),
        "legacy-conversation",
    )
    database.close()

    upgraded = Database(path)
    upgraded.initialize()
    upgraded_repository = LocalChatRepository(upgraded)
    assert upgraded.schema_version == 5
    assert upgraded_repository.conversation(conversation.id).title == "legacy"
    template = upgraded_repository.role_templates.create(
        CreateLocalRoleTemplateInput(name="迁移后模板", baseRoleId="analyst", instructions="read"),
        "migration-template",
    )
    upgraded.close()

    reopened = Database(path)
    reopened.initialize()
    assert LocalChatRepository(reopened).role_templates.template(template.id).name == "迁移后模板"
    reopened.close()


def test_custom_scene_validation_readonly_templates_and_builtin_rules(repository) -> None:
    template = repository.role_templates.create(
        CreateLocalRoleTemplateInput(
            name="分析模板", baseRoleId="analyst", instructions="template source"
        ),
        "analyst-template",
    )
    scene_input = CreateLocalSceneInput(
        name="  自定义分析  ",
        description="只读场景",
        roles=[role(
            "analyst", role_name="安全分析员", instructions="scene copy",
            template_id=template.id, template_version=1,
        )],
    )
    created = repository.create_scene(scene_input, "scene-create")
    replay = repository.create_scene(scene_input, "scene-create")
    assert created.id.startswith("custom_scene_") and replay.id == created.id
    assert created.name == "自定义分析" and created.read_only is True
    assert created.is_builtin is False and created.roles[0].instructions == "scene copy"
    with pytest.raises(HubError, match="描述不能为null"):
        repository.create_scene(
            CreateLocalSceneInput.model_construct(
                name="null-description", description=None, roles=[role("analyst")]
            ),
            "null-description",
        )

    writable = repository.create_scene(
        CreateLocalSceneInput(name="实现", roles=[role("developer")]), "scene-developer"
    )
    assert writable.read_only is False

    invalid_roles = [
        [role("analyst"), role("analyst")],
        [role("unknown")],
        [role("analyst", enabled=False)],
    ]
    for index, roles in enumerate(invalid_roles):
        with pytest.raises(HubError) as invalid:
            repository.create_scene(
                CreateLocalSceneInput(name=f"invalid-{index}", roles=roles), f"invalid-{index}"
            )
        assert invalid.value.code == "VALIDATION_FAILED"

    with pytest.raises(HubError, match="基础角色"):
        repository.create_scene(
            CreateLocalSceneInput(name="bad-template-role", roles=[role(
                "reviewer", template_id=template.id, template_version=1
            )]),
            "bad-template-role",
        )
    with pytest.raises(HubError, match="不能高于"):
        repository.create_scene(
            CreateLocalSceneInput(name="future-template", roles=[role(
                "analyst", template_id=template.id, template_version=2
            )]),
            "future-template",
        )
    with pytest.raises(HubError, match="同时提供"):
        repository.create_scene(
            CreateLocalSceneInput(name="partial-template", roles=[role(
                "analyst", template_id=template.id
            )]),
            "partial-template",
        )

    analyze = repository.scene("analyze")
    with pytest.raises(HubError, match="名称不能为null"):
        repository.save_scene(
            "analyze",
            SaveLocalSceneInput.model_construct(
                expected_version=analyze.version, roles=analyze.roles, name=None
            ),
        )
    with pytest.raises(HubError, match="内置场景"):
        repository.save_scene(
            "analyze",
            SaveLocalSceneInput(
                expectedVersion=analyze.version, roles=[role("developer")]
            ),
        )


def test_custom_scene_original_planner_order_and_incremental_metadata(repository) -> None:
    planner = role(
        "planner", agent="planner-agent", model_id="planner-model", effort="high"
    )
    developer = role("developer", agent="developer-agent")
    reviewer = role("reviewer", agent="other-agent", model_id="other-model", effort="low")
    with pytest.raises(HubError, match="顺序"):
        repository.create_scene(
            CreateLocalSceneInput(
                name="wrong-order", roles=[developer, planner, reviewer], reviewMode="original_planner"
            ),
            "wrong-original-order",
        )
    scene = repository.create_scene(
        CreateLocalSceneInput(
            name="original planner", roles=[planner, developer, reviewer],
            reviewMode="original_planner",
        ),
        "original-planner",
    )
    saved_reviewer = scene.roles[2]
    assert saved_reviewer.agent_instance_id == "planner-agent"
    assert saved_reviewer.model_id_ == "planner-model"
    assert saved_reviewer.reasoning_effort == "high"
    assert scene.read_only is False

    updated = repository.save_scene(
        str(scene.id),
        SaveLocalSceneInput(
            expectedVersion=1,
            roles=[role("reviewer", enabled=False), developer],
            name="  implementation only  ",
            description="updated",
            reviewMode="independent",
        ),
    )
    assert updated.name == "implementation only" and updated.description == "updated"
    assert [item.role_id for item in updated.roles] == ["reviewer", "developer"]
    assert updated.read_only is False and updated.version == 2


def test_role_template_http_validation_and_required_idempotency(tmp_path: Path) -> None:
    hub = create_application(
        paths=HubPaths.resolve(tmp_path / "api"), token="test-token",
        ports=HubPorts.unavailable_defaults(), allowed_hosts={"testserver"},
        allowed_origins={"http://testserver"}, environment="test",
    )
    headers = {"Authorization": "Bearer test-token", "Origin": "http://testserver"}
    with TestClient(hub.app) as client:
        missing_key = client.post(
            "/api/v2/role-templates",
            json={"name": "x", "baseRoleId": "analyst", "instructions": ""},
            headers=headers,
        )
        assert missing_key.status_code == 422
        for index, body in enumerate((
            {"name": None, "baseRoleId": "analyst", "instructions": ""},
            {"name": "x", "baseRoleId": "analyst", "instructions": None},
            {"name": "x" * 121, "baseRoleId": "analyst", "instructions": ""},
            {"name": "x", "baseRoleId": "analyst", "instructions": "x" * 12001},
        )):
            response = client.post(
                "/api/v2/role-templates", json=body,
                headers={**headers, "Idempotency-Key": f"invalid-{index}"},
            )
            assert response.status_code == 422, response.text
        null_description = client.post(
            "/api/v2/scenes",
            json={"name": "null description", "description": None, "roles": [{
                "roleId": "analyst", "agentInstanceId": "", "instructions": "", "enabled": True,
            }]},
            headers={**headers, "Idempotency-Key": "null-scene-description"},
        )
        assert null_description.status_code == 422
        analyze = next(
            scene for scene in client.get("/api/v2/scenes", headers=headers).json()["data"]
            if scene["id"] == "analyze"
        )
        null_name = client.put(
            "/api/v2/scenes/analyze",
            json={"expectedVersion": analyze["version"], "name": None, "roles": analyze["roles"]},
            headers=headers,
        )
        assert null_name.status_code == 422


def test_custom_scene_real_workflow_freezes_template_copy_and_guards_continue(
    tmp_path: Path, monkeypatch
) -> None:
    from runtime import composition

    adapter = FakeAdapter()
    view = AgentView.model_validate({
        "id": "local.test-adapter.default", "adapterId": "test-adapter",
        "displayName": "Contract runtime", "version": "1.0", "status": "ready",
        "detectedAt": "2026-09-26T00:00:00Z", "assignedRoles": [], "isPrimaryFor": [],
        "capabilities": [
            {"id": item, "name": item, "hard": True, "source": "detected", "supported": True}
            for item in ["structured_output", "session_resume"]
        ],
    })

    class Manager:
        available = True
        unavailable_reason = None

        async def list_agents(self):
            return [view]

        def get(self, identifier):
            return adapter if identifier == "test-adapter" else None

    monkeypatch.setattr(composition, "_build_agent_port", lambda: Manager())
    ports = composition.build_ports()
    hub = create_application(
        paths=HubPaths.resolve(tmp_path / "workflow"), token="test-token", ports=ports,
        allowed_hosts={"testserver"}, allowed_origins={"http://testserver"}, environment="test",
    )
    asyncio.run(composition.bind_ports(hub, ports))
    workspace = tmp_path / "source"
    workspace.mkdir()
    code = hub.local_auth.issue_code("custom-scene-workflow")
    with TestClient(hub.app) as client:
        origin = {"Origin": "http://testserver"}
        assert client.post(
            "/api/v2/auth/local-session", json={"code": code}, headers=origin
        ).status_code == 200
        workspace_view = client.post(
            "/api/v2/workspaces", json={"path": str(workspace)}, headers=origin
        ).json()["data"]
        template = client.post(
            "/api/v2/role-templates",
            json={"name": "只读分析", "baseRoleId": "analyst", "instructions": "template-v1"},
            headers={**origin, "Idempotency-Key": "workflow-template"},
        ).json()["data"]
        scene = client.post(
            "/api/v2/scenes",
            json={"name": "自定义只读", "roles": [{
                "roleId": "analyst", "roleName": "自定义分析师",
                "roleTemplateId": template["id"], "roleTemplateVersion": 1,
                "agentInstanceId": "local.test-adapter.default",
                "instructions": "scene-copy-v1", "enabled": True,
            }]},
            headers={**origin, "Idempotency-Key": "workflow-scene"},
        ).json()["data"]
        conversation = client.post(
            "/api/v2/conversations",
            json={"title": "custom", "workspaceId": workspace_view["id"], "sceneId": scene["id"]},
            headers={**origin, "Idempotency-Key": "workflow-conversation"},
        ).json()["data"]

        def send(turn: int, mode: str) -> dict:
            key = f"workflow-message-{turn}"
            receipt = client.post(
                f"/api/v2/conversations/{conversation['id']}/messages",
                json={"clientMessageId": key, "text": f"turn-{turn}", "sessionMode": mode},
                headers={**origin, "Idempotency-Key": key},
            )
            assert receipt.status_code == 202, receipt.text
            run_id = receipt.json()["data"]["runId"]
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                run = client.get(f"/api/v2/runs/{run_id}").json()["data"]
                if run["status"] in {"succeeded", "failed"}:
                    return run
                time.sleep(0.01)
            raise AssertionError("custom scene run timed out")

        first = send(1, "new")
        assert first["status"] == "succeeded"
        assert first["sceneSnapshot"]["roles"][0]["instructions"] == "scene-copy-v1"
        assert adapter.started[0].role_instructions == "scene-copy-v1"
        assert str(adapter.started[0].role_id) == "analyst"
        with hub.database.locked_connection() as connection:
            profile_payload = connection.execute(
                "SELECT payload_json FROM team_profiles WHERE profile_id LIKE 'local-profile:%' "
                "ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()[0]
        assert json.loads(profile_payload)["roleBindings"]["analyst"]["roleName"] == "自定义分析师"

        updated_template = client.put(
            f"/api/v2/role-templates/{template['id']}",
            json={"expectedVersion": 1, "name": "只读分析v2", "instructions": "template-v2"},
            headers={**origin, "Idempotency-Key": "workflow-template-update"},
        )
        assert updated_template.status_code == 200
        assert client.get("/api/v2/scenes").json()["data"][-1]["roles"][0]["instructions"] == "scene-copy-v1"

        second = send(2, "continue")
        assert second["status"] == "succeeded"
        assert len(adapter.started) == 1 and len(adapter.resumed) == 1

        scene_update = client.put(
            f"/api/v2/scenes/{scene['id']}",
            json={"expectedVersion": 1, "roles": [{
                "roleId": "analyst", "roleName": "自定义分析师",
                "roleTemplateId": template["id"], "roleTemplateVersion": 2,
                "agentInstanceId": "local.test-adapter.default",
                "instructions": "scene-copy-v2", "enabled": True,
            }]},
            headers=origin,
        )
        assert scene_update.status_code == 200, scene_update.text
        third = send(3, "continue")
        assert third["status"] == "failed"
        assert "角色或模型配置已变化" in (third.get("error") or "")
        assert len(adapter.resumed) == 1
