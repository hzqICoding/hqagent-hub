from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from protocol.generated.python import DrainProgress, ProcessDescriptor

from core.constants import PROTOCOL_VERSION
from core.ports import DrainHooks
from storage.database import Database
from storage.events import EventDraft, EventStore


def _timestamp(value: datetime | None = None) -> str:
    return (value or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")


class MaintenanceState:
    def __init__(self) -> None:
        self.enabled = False
        self.reason = ""


class DrainCoordinator:
    def __init__(
        self,
        database: Database,
        events: EventStore,
        hooks: DrainHooks,
        maintenance: MaintenanceState,
        backup_dir: Path,
        update_proxy: object,
    ) -> None:
        self.database = database
        self.events = events
        self.hooks = hooks
        self.maintenance = maintenance
        self.backup_dir = backup_dir
        self.update_proxy = update_proxy
        self._lock = asyncio.Lock()
        self._progress = DrainProgress.model_validate(
            {"step": "stop_accepting", "activeTasksRemaining": 0, "percent": 0, "backupCompleted": False}
        )
        self.last_backup: Path | None = None

    @property
    def progress(self) -> DrainProgress:
        return self._progress

    def set_maintenance(self, enabled: bool, reason: str = "") -> None:
        if self.maintenance.enabled == enabled and self.maintenance.reason == reason:
            return
        self.maintenance.enabled = enabled
        self.maintenance.reason = reason
        with self.database.transaction() as transaction:
            self.events.append(
                transaction,
                EventDraft(
                    aggregate_type="system",
                    aggregate_id="local-hub",
                    type="system.maintenance",
                    payload={"active": enabled, "reason": reason},
                ),
            )

    async def start(
        self,
        timeout_seconds: float = 30,
        desktop_pid: int | None = None,
        update_agent_pid: int | None = None,
    ) -> DrainProgress:
        async with self._lock:
            started = datetime.now(timezone.utc)
            timeout_at = started + timedelta(seconds=max(timeout_seconds, 0.1))
            self.set_maintenance(True, "正在为升级排空任务")
            await self._set_progress("stop_accepting", 10, started, timeout_at)
            await self._set_progress("save_sessions", 20, started, timeout_at)
            await self.hooks.checkpoint()
            await self._checkpoint_storage_state()

            while True:
                active = await self.hooks.active_task_ids()
                busy = await self.hooks.busy_operation_count()
                if not active and busy == 0:
                    break
                if datetime.now(timezone.utc) >= timeout_at:
                    await self._set_progress("wait_running_tasks", 45, started, timeout_at, active)
                    return self._progress
                await self._set_progress("wait_running_tasks", 35, started, timeout_at, active)
                await asyncio.sleep(0.05)

            await self._set_progress("backup_data", 70, started, timeout_at)
            self.database.checkpoint("TRUNCATE")
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            backup = self.backup_dir / f"hub-{started.strftime('%Y%m%dT%H%M%SZ')}.db"
            self.last_backup = self.database.backup(backup)
            await self._set_progress("ready", 100, started, timeout_at, wait_pids=await self._wait_pids(desktop_pid, update_agent_pid), backup=True)
            return self._progress

    async def backup_database(self) -> Path:
        now = datetime.now(timezone.utc)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        destination = self.backup_dir / f"hub-{now.strftime('%Y%m%dT%H%M%S.%fZ')}.db"
        self.last_backup = self.database.backup(destination)
        return self.last_backup

    async def _checkpoint_storage_state(self) -> None:
        active = await self.hooks.active_task_ids()
        if not active:
            return
        now = _timestamp()
        with self.database.transaction() as transaction:
            for task_id in active:
                transaction.connection.execute(
                    "INSERT INTO task_checkpoints(checkpoint_id,task_id,payload_json,created_at) VALUES(?,?,?,?)",
                    (f"chk_{uuid.uuid4().hex}", task_id, '{"reason":"update-drain"}', now),
                )

    async def _wait_pids(self, desktop_pid: int | None, update_agent_pid: int | None) -> list[ProcessDescriptor]:
        values: list[dict[str, Any]] = [{"component": "core", "pid": os.getpid(), "name": "hqagent-core"}]
        if desktop_pid and desktop_pid > 0:
            values.append({"component": "desktop", "pid": desktop_pid, "name": "hqagent-desktop"})
        descriptor = await self.update_proxy.descriptor()
        resolved_update_pid = update_agent_pid or (descriptor.pid if descriptor else None)
        if resolved_update_pid and resolved_update_pid > 0:
            values.append({"component": "update-agent", "pid": resolved_update_pid, "name": "hqagent-update-agent"})
        for pid in await self.hooks.worker_pids():
            if pid > 0:
                values.append({"component": "agent-worker", "pid": pid})
        seen: set[int] = set()
        result = []
        for item in values:
            if item["pid"] not in seen:
                seen.add(item["pid"])
                result.append(ProcessDescriptor.model_validate(item))
        return result

    async def _set_progress(
        self,
        step: str,
        percent: int,
        started: datetime,
        timeout_at: datetime,
        waiting: list[str] | None = None,
        wait_pids: list[ProcessDescriptor] | None = None,
        backup: bool = False,
    ) -> None:
        self._progress = DrainProgress.model_validate(
            {
                "step": step,
                "activeTasksRemaining": len(waiting or []),
                "percent": percent,
                "startedAt": _timestamp(started),
                "timeoutAt": _timestamp(timeout_at),
                "waitingTaskIds": waiting or [],
                "waitPids": wait_pids,
                "backupCompleted": backup,
            }
        )
        with self.database.transaction() as transaction:
            self.events.append(
                transaction,
                EventDraft(
                    aggregate_type="update",
                    aggregate_id="local-update",
                    type="update.tasks.draining",
                    payload={
                        "active": True,
                        "reason": "正在为升级排空任务",
                        "drainProgress": self._progress.model_dump(mode="json", by_alias=True, exclude_none=True),
                        "protocolVersion": PROTOCOL_VERSION,
                    },
                ),
            )
