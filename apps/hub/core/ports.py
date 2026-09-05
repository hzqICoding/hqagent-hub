from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from core.errors import FeatureUnavailable


class FeaturePort(Protocol):
    @property
    def available(self) -> bool: ...

    @property
    def unavailable_reason(self) -> str | None: ...


class AgentPort(FeaturePort, Protocol):
    async def list_agents(self) -> list[Any]: ...
    async def discover(self) -> Any: ...


class WorkspacePort(Protocol):
    async def list_workspaces(self, search: str | None, limit: int | None) -> list[Any]: ...


class TeamProfilePort(FeaturePort, Protocol):
    async def list_profiles(self) -> list[Any]: ...
    async def get_profile(self, profile_id: str) -> Any: ...
    async def save_profile(self, profile_id: str, value: Any) -> Any: ...
    async def resolve(self, value: Any) -> Any: ...


class TaskPort(FeaturePort, Protocol):
    async def list_tasks(self, query: dict[str, Any]) -> Any: ...
    async def create_task(self, value: Any, idempotency_key: str | None) -> Any: ...
    async def get_task(self, task_id: str) -> Any: ...
    async def act(self, task_id: str, value: Any, idempotency_key: str | None) -> Any: ...


class SessionPort(FeaturePort, Protocol):
    async def list_sessions(self, query: dict[str, Any]) -> Any: ...
    async def resume(self, session_id: str, value: Any) -> Any: ...


class ApprovalPort(FeaturePort, Protocol):
    async def list_approvals(self, query: dict[str, Any]) -> list[Any]: ...
    async def respond(self, approval_id: str, value: Any, idempotency_key: str | None) -> Any: ...


class DrainHooks(Protocol):
    async def checkpoint(self) -> None: ...
    async def active_task_ids(self) -> list[str]: ...
    async def busy_operation_count(self) -> int: ...
    async def worker_pids(self) -> list[int]: ...


class UnavailablePort:
    def __init__(self, feature: str, reason: str) -> None:
        self.feature = feature
        self._reason = reason

    @property
    def available(self) -> bool:
        return False

    @property
    def unavailable_reason(self) -> str:
        return self._reason

    def __getattr__(self, _name: str) -> Any:
        async def unavailable(*_args: Any, **_kwargs: Any) -> Any:
            raise FeatureUnavailable(self.feature, self._reason)

        return unavailable


class EmptyWorkspacePort:
    async def list_workspaces(self, search: str | None, limit: int | None) -> list[Any]:
        return []


class EmptyDrainHooks:
    async def checkpoint(self) -> None:
        return None

    async def active_task_ids(self) -> list[str]:
        return []

    async def busy_operation_count(self) -> int:
        return 0

    async def worker_pids(self) -> list[int]:
        return []


@dataclass(slots=True)
class HubPorts:
    agents: AgentPort
    workspaces: WorkspacePort
    team_profiles: TeamProfilePort
    tasks: TaskPort
    sessions: SessionPort
    approvals: ApprovalPort
    drain: DrainHooks

    @classmethod
    def unavailable_defaults(cls) -> "HubPorts":
        return cls(
            agents=UnavailablePort("agents", "Agent Adapter 尚未接入（W2 未完成）"),
            workspaces=EmptyWorkspacePort(),
            team_profiles=UnavailablePort("teamProfiles", "Role Resolver 尚未接入（W3 未完成）"),
            tasks=UnavailablePort("tasks", "Workflow Orchestrator 尚未接入（W3 未完成）"),
            sessions=UnavailablePort("sessions", "Agent Adapter 尚未接入（W2 未完成）"),
            approvals=UnavailablePort("approvals", "Permission Engine 尚未接入（W3 未完成）"),
            drain=EmptyDrainHooks(),
        )

