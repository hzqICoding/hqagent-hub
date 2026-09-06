from __future__ import annotations

from datetime import datetime

from protocol.generated.python import (
    BootstrapAgentsSummary,
    BootstrapUpdateSummary,
    BootstrapView,
    FeatureAvailability,
    FeatureState,
)

from core.constants import APP_VERSION, PROTOCOL_VERSION
from core.ports import HubPorts
from storage.events import EventStore
from storage.settings import SettingsRepository


class BootstrapService:
    def __init__(
        self,
        ports: HubPorts,
        settings: SettingsRepository,
        events: EventStore,
        update_proxy: object,
        instance_id: str,
        started_at: datetime,
        environment: str,
        maintenance: object,
    ) -> None:
        self.ports = ports
        self.settings = settings
        self.events = events
        self.update_proxy = update_proxy
        self.instance_id = instance_id
        self.started_at = started_at
        self.environment = environment
        self.maintenance = maintenance

    @staticmethod
    def _state(port: object) -> FeatureState:
        available = bool(getattr(port, "available", True))
        reason = getattr(port, "unavailable_reason", None)
        return FeatureState.model_validate({"available": available, "reason": reason})

    async def build(self) -> BootstrapView:
        agent_total = agent_ready = agent_issues = 0
        if getattr(self.ports.agents, "available", False):
            agents = await self.ports.agents.list_agents()
            agent_total = len(agents)
            agent_ready = sum(1 for item in agents if str(getattr(item, "status", "")) == "ready")
            agent_issues = agent_total - agent_ready

        workspaces = await self.ports.workspaces.list_workspaces(None, None)
        update_available, update_reason = await self.update_proxy.availability()
        update_summary = {
            "phase": "idle",
            "hasUpdate": False,
            "currentVersion": APP_VERSION,
            "unacknowledgedResult": False,
        }
        if update_available:
            try:
                state = await self.update_proxy.request("GET", "/internal/v1/state")
                update_summary.update(
                    {
                        "phase": state.get("phase", "idle"),
                        "currentVersion": state.get("currentVersion", APP_VERSION),
                        "latestVersion": state.get("latestVersion"),
                        "hasUpdate": bool(state.get("latestVersion") and state.get("latestVersion") != APP_VERSION),
                        "mandatory": state.get("mandatory"),
                    }
                )
            except Exception as exc:
                update_available = False
                update_reason = f"Update Agent 无法连接：{type(exc).__name__}"

        active_tasks = await self.ports.drain.active_task_ids()
        raw = {
            "protocolVersion": PROTOCOL_VERSION,
            "appVersion": APP_VERSION,
            "environment": self.environment,
            "maintenance": self.maintenance.enabled,
            "appearance": self.settings.get_appearance(),
            "agents": BootstrapAgentsSummary.model_validate(
                {"total": agent_total, "ready": agent_ready, "issues": agent_issues}
            ),
            "defaultProfileId": None,
            "currentWorkspace": workspaces[0] if workspaces else None,
            "workspaceCount": len(workspaces),
            "activeTasksCount": len(active_tasks),
            "pendingApprovalsCount": 0,
            "update": BootstrapUpdateSummary.model_validate(update_summary),
            "features": FeatureAvailability.model_validate(
                {
                    "agents": self._state(self.ports.agents),
                    "teamProfiles": self._state(self.ports.team_profiles),
                    "tasks": self._state(self.ports.tasks),
                    "sessions": self._state(self.ports.sessions),
                    "approvals": self._state(self.ports.approvals),
                    "updates": {"available": update_available, "reason": update_reason},
                }
            ),
            "instanceId": self.instance_id,
            "lastEventSeq": self.events.latest_seq(),
            "hubStartedAt": self.started_at.isoformat().replace("+00:00", "Z"),
        }
        return BootstrapView.model_validate(raw)

