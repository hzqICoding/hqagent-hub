from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from protocol.generated.python import AgentTaskSpec, SessionView, TaskNodeView

from core.errors import HubError
from runtime.tasks import TaskService
from security.worktrees import WorktreeSpec


def session_view(
    session_id: str,
    *,
    workspace_id: str = "workspace",
    role_id: str = "developer",
) -> SessionView:
    return SessionView.model_validate(
        {
            "id": session_id,
            "status": "idle",
            "workspaceId": workspace_id,
            "workspaceName": workspace_id,
            "roleId": role_id,
            "agentInstanceId": "agent",
            "agentDisplayName": "agent",
            "adapterId": "codex",
            "externalSessionId": "external",
            "purpose": "implement" if role_id == "developer" else "architect",
            "reusePolicy": "new_session",
            "taskId": "old-task",
            "nodeId": "old-node",
            "createdAt": "2026-09-25T00:00:00Z",
            "lastUsedAt": "2026-09-25T00:00:00Z",
            "isValid": True,
        }
    )


def task_spec(
    root: Path,
    session_id: str,
    *,
    workspace_id: str = "workspace",
    role_id: str = "developer",
    read_only: bool = False,
) -> AgentTaskSpec:
    return AgentTaskSpec.model_validate(
        {
            "sessionId": session_id,
            "taskId": "old-task",
            "nodeId": "old-node",
            "workspaceId": workspace_id,
            "roleId": role_id,
            "objective": "old objective",
            "worktreePath": str(root),
            "branch": None if read_only else "hq/old-task/developer",
            "baseCommit": None if read_only else "a" * 40,
            "allowedPaths": [] if read_only else ["**"],
            "sessionPurpose": "architect" if read_only else "implement",
            "reusePolicy": "new_session",
            "readOnly": read_only,
        }
    )


class Sessions:
    def __init__(self, session: SessionView, spec: AgentTaskSpec) -> None:
        self.session = session
        self.spec = spec

    async def get(self, session_id: str):
        return self.session if session_id == self.session.id else None

    async def get_spec(self, session_id: str):
        return self.spec if session_id == self.session.id else None


class State:
    def __init__(self) -> None:
        self.values: dict[str, dict] = {}

    def put(self, key: str, value: dict) -> None:
        self.values[key] = value


class Worktrees:
    def __init__(self, root: Path) -> None:
        self.worktree_root = root
        self.create_calls = 0
        self.validated: WorktreeSpec | None = None

    def create(self, spec: WorktreeSpec):
        self.create_calls += 1
        raise AssertionError("continued session must not create a new worktree")

    def validate(self, spec: WorktreeSpec, _scope):
        self.validated = spec
        return SimpleNamespace(violation_paths=())


def node(role_id: str = "developer") -> TaskNodeView:
    return TaskNodeView.model_validate(
        {
            "id": "new-node",
            "taskId": "new-task",
            "roleId": role_id,
            "resolvedAgentId": "",
            "resolvedAgentName": "",
            "resolveSource": "manual",
            "status": "pending",
        }
    )


def service_for(
    session: SessionView,
    spec: AgentTaskSpec,
    worktree_root: Path,
    *,
    read_only: bool,
) -> tuple[TaskService, State, Worktrees]:
    service = object.__new__(TaskService)
    state = State()
    worktrees = Worktrees(worktree_root)
    service.state = state
    service.worktrees = worktrees
    service.runtime = SimpleNamespace(
        permissions=SimpleNamespace(
            role_policy=lambda _role: SimpleNamespace(read_only=read_only)
        ),
        sessions=SimpleNamespace(repository=Sessions(session, spec)),
    )
    return service, state, worktrees


def task_state(role_id: str, session_id: str, workspace_root: Path) -> dict:
    return {
        "request": {
            "objective": "continue",
            "workspaceId": "workspace",
            "workflowRoles": [role_id],
            "resumeSessions": {role_id: session_id},
        },
        "workspace": {"path": str(workspace_root)},
        "worktrees": {},
    }


def test_write_continue_reuses_actual_worktree_and_validation_metadata(tmp_path: Path) -> None:
    async def scenario() -> None:
        repository = tmp_path / "repo"
        old_worktree = tmp_path / "worktrees" / "old-developer"
        repository.mkdir()
        old_worktree.mkdir(parents=True)
        session_id = "session-old"
        spec = task_spec(old_worktree, session_id)
        service, state_store, worktrees = service_for(
            session_view(session_id), spec, tmp_path / "worktrees", read_only=False
        )
        state = task_state("developer", session_id, repository)

        result = await service._prepare_execution_path(
            "new-task", node(), "developer", {"path": str(repository)}, state
        )

        assert result is not None
        assert result["path"] == str(old_worktree.resolve())
        assert result["branch"] == spec.branch
        assert result["base_commit"] == spec.base_commit
        assert result["allowed_paths"] == ["**"]
        assert worktrees.create_calls == 0
        saved = state_store.values["task_spec:new-task"]["worktrees"]["new-node"]
        assert saved["worktreePath"] == str(old_worktree.resolve())
        assert saved["branch"] == spec.branch
        assert saved["baseCommit"] == spec.base_commit
        validation_spec = WorktreeSpec(
            Path(saved["repositoryPath"]),
            Path(saved["worktreePath"]),
            saved["branch"],
            saved["baseCommit"],
        )
        worktrees.validate(validation_spec, object())
        assert worktrees.validated is not None
        assert worktrees.validated.worktree_path == old_worktree.resolve()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("session_workspace", "session_role", "spec_workspace", "spec_role"),
    [
        ("other", "developer", "workspace", "developer"),
        ("workspace", "reviewer", "workspace", "developer"),
        ("workspace", "developer", "other", "developer"),
        ("workspace", "developer", "workspace", "reviewer"),
    ],
)
def test_continue_rejects_workspace_or_role_mismatch(
    tmp_path: Path,
    session_workspace: str,
    session_role: str,
    spec_workspace: str,
    spec_role: str,
) -> None:
    async def scenario() -> None:
        repository = tmp_path / "repo"
        old_worktree = tmp_path / "worktrees" / "old"
        repository.mkdir()
        old_worktree.mkdir(parents=True)
        session_id = "session-old"
        service, _, worktrees = service_for(
            session_view(session_id, workspace_id=session_workspace, role_id=session_role),
            task_spec(
                old_worktree,
                session_id,
                workspace_id=spec_workspace,
                role_id=spec_role,
            ),
            tmp_path / "worktrees",
            read_only=False,
        )
        with pytest.raises(HubError) as error:
            await service._prepare_execution_path(
                "new-task",
                node(),
                "developer",
                {"path": str(repository)},
                task_state("developer", session_id, repository),
            )
        assert error.value.code == "SESSION_NOT_RESUMABLE"
        assert worktrees.create_calls == 0

    asyncio.run(scenario())


def test_read_only_continue_keeps_its_own_scope_without_worktree_metadata(tmp_path: Path) -> None:
    async def scenario() -> None:
        repository = tmp_path / "repo"
        planner_root = tmp_path / "planner-root"
        repository.mkdir()
        planner_root.mkdir()
        session_id = "session-planner"
        service, state_store, worktrees = service_for(
            session_view(session_id, role_id="planner"),
            task_spec(planner_root, session_id, role_id="planner", read_only=True),
            tmp_path / "worktrees",
            read_only=True,
        )
        state = task_state("planner", session_id, repository)
        result = await service._prepare_execution_path(
            "new-task", node("planner"), "planner", {"path": str(repository)}, state
        )
        assert result is not None
        assert result["path"] == str(planner_root.resolve())
        assert result["allowed_paths"] == []
        assert state_store.values == {}
        assert state["worktrees"] == {}
        assert worktrees.create_calls == 0

    asyncio.run(scenario())


def test_continue_rejects_explicit_allowed_paths_change(tmp_path: Path) -> None:
    async def scenario() -> None:
        repository = tmp_path / "repo"
        old_worktree = tmp_path / "worktrees" / "old-developer"
        repository.mkdir()
        old_worktree.mkdir(parents=True)
        session_id = "session-old"
        service, _, worktrees = service_for(
            session_view(session_id),
            task_spec(old_worktree, session_id),
            tmp_path / "worktrees",
            read_only=False,
        )
        state = task_state("developer", session_id, repository)
        state["request"]["allowedPaths"] = ["src/**"]

        with pytest.raises(HubError) as error:
            await service._prepare_execution_path(
                "new-task", node(), "developer", {"path": str(repository)}, state
            )

        assert error.value.code == "SESSION_NOT_RESUMABLE"
        assert "allowedPaths" in error.value.message
        assert worktrees.create_calls == 0

    asyncio.run(scenario())
