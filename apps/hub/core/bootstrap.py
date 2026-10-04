from __future__ import annotations

from datetime import datetime
import asyncio
import time
from contextvars import Context

from protocol.generated.python import (
    BootstrapAgentsSummary,
    BootstrapUpdateSummary,
    BootstrapView,
    FeatureAvailability,
    FeatureState,
)

from core.constants import APP_VERSION, PROTOCOL_VERSION
from core.ports import HubPorts
from core.agent_snapshot import agent_snapshot
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
        self._background = None
        self._refreshed_at = None
        self._closed = False
        self._workspaces = []
        self._active_tasks = []
        self._update_available = False
        self._update_reason = 'Update Agent 状态正在后台检测'
        self._update_summary = self._empty_update()

    @staticmethod
    def _empty_update():
        return {'phase': 'idle', 'hasUpdate': False, 'currentVersion': APP_VERSION, 'unacknowledgedResult': False}

    def start(self):
        if self._closed or self._background is not None and not self._background.done():
            return
        if self._refreshed_at is None or time.monotonic() - self._refreshed_at >= 5:
            self._background = asyncio.create_task(self._refresh_dependencies(), context=Context())

    async def close(self):
        self._closed = True
        if self._background is not None:
            self._background.cancel()
            await asyncio.gather(self._background, return_exceptions=True)

    async def _refresh_dependencies(self):
        async def workspaces():
            try:
                async with asyncio.timeout(4):
                    self._workspaces = await self.ports.workspaces.list_workspaces(None, None)
            except Exception:
                pass
        async def active():
            try:
                async with asyncio.timeout(1):
                    self._active_tasks = await self.ports.drain.active_task_ids()
            except Exception:
                pass
        async def update():
            summary = self._empty_update()
            available, reason = False, 'Update Agent 状态暂不可用'
            try:
                async with asyncio.timeout(5):
                    available, reason = await self.update_proxy.availability()
                    if available:
                        state = await self.update_proxy.request('GET', '/internal/v1/state')
                        summary.update(phase=state.get('phase', 'idle'), currentVersion=state.get('currentVersion', APP_VERSION),
                            latestVersion=state.get('latestVersion'), hasUpdate=bool(state.get('latestVersion') and
                                state.get('latestVersion') != APP_VERSION), mandatory=state.get('mandatory'))
            except Exception as error:
                available, reason = False, f'Update Agent 无法连接：{type(error).__name__}'
            self._update_available, self._update_reason, self._update_summary = available, reason, summary
        await asyncio.gather(workspaces(), active(), update())
        self._refreshed_at = time.monotonic()

    @staticmethod
    def _state(port: object) -> FeatureState:
        available = bool(getattr(port, "available", True))
        reason = getattr(port, "unavailable_reason", None)
        return FeatureState.model_validate({"available": available, "reason": reason})

    async def build(self) -> BootstrapView:
        self.start()
        agent_total = agent_ready = agent_issues = 0
        if getattr(self.ports.agents, "available", False):
            agents = await agent_snapshot(self.ports.agents)
            agent_total = len(agents)
            agent_ready = sum(1 for item in agents if str(getattr(item, "status", "")) == "ready")
            agent_issues = agent_total - agent_ready

        snapshot = getattr(type(self.ports.workspaces), 'cached_workspaces', None)
        workspaces = await snapshot(self.ports.workspaces) if snapshot else self._workspaces
        update_available, update_reason = self._update_available, self._update_reason
        update_summary = dict(self._update_summary)
        active_tasks = self._active_tasks
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
