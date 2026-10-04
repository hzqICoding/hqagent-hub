from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from pathlib import Path

from protocol import PACKAGE_ROOT
from protocol.generated.python import (
    AdapterDescriptor,
    AdapterFailure,
    AdapterFailureKind,
    AgentDiscoveryCompletedPayload,
    AgentDiscoveryError,
    AgentDiscoveryResult,
    AgentStatus,
    AgentView,
    CapabilityId,
    CapabilityItem,
    ErrorCode,
)

from adapters.base import AgentAdapter
from adapters.events import utc_timestamp
from adapters.failures import version_tuple


@dataclass(frozen=True, slots=True)
class _CapabilityMetadata:
    display_name: str
    description: str | None
    hard: bool


def _load_capability_metadata() -> dict[CapabilityId, _CapabilityMetadata]:
    path = Path(PACKAGE_ROOT) / "registry" / "capabilities.yaml"
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*- id:\s*", text)[1:]
    result: dict[CapabilityId, _CapabilityMetadata] = {}
    for block in blocks:
        lines = block.splitlines()
        capability_id = CapabilityId(lines[0].strip())
        display = re.search(r"(?m)^\s*displayName:\s*(.+)$", block)
        description = re.search(r"(?m)^\s*description:\s*(.+)$", block)
        hard = re.search(r"(?m)^\s*hard:\s*(true|false)$", block)
        result[capability_id] = _CapabilityMetadata(
            display_name=display.group(1).strip() if display else capability_id.value,
            description=description.group(1).strip() if description else None,
            hard=bool(hard and hard.group(1) == "true"),
        )
    return result


_CAPABILITY_METADATA = _load_capability_metadata()


class AdapterManager:
    """W1 AgentPort 的实现；只做注册、发现、轻量健康检查与 detect 缓存。"""

    available = True
    unavailable_reason = None

    def __init__(self, adapters: list[AgentAdapter], *, detect_ttl_seconds: float = 60) -> None:
        self._adapters = {adapter.adapter_id: adapter for adapter in adapters}
        if len(self._adapters) != len(adapters):
            raise ValueError("adapterId 必须唯一")
        self._detect_ttl = detect_ttl_seconds
        self._detect_cache: dict[str, tuple[float, AdapterDescriptor | AdapterFailure]] = {}
        self._last_agents: list[AgentView] = []
        self._last_discovery = None
        self._discovery_lock = asyncio.Lock()

    def runtime_instances(self, adapter_id: str) -> tuple[str, ...]:
        # The same registry-owned identity used by discovery, even while a
        # previously configured runtime is temporarily unavailable.
        return (f"local.{adapter_id}.default",) if adapter_id in self._adapters else ()

    def get(self, adapter_id: str) -> AgentAdapter | None:
        return self._adapters.get(adapter_id)

    async def detect(self, adapter_id: str, *, refresh: bool = False) -> AdapterDescriptor | AdapterFailure:
        now = time.monotonic()
        cached = self._detect_cache.get(adapter_id)
        if cached and not refresh and now - cached[0] < self._detect_ttl:
            return cached[1]
        adapter = self._adapters.get(adapter_id)
        if adapter is None:
            return AdapterFailure.model_validate(
                {
                    "kind": AdapterFailureKind.NOT_INSTALLED,
                    "code": ErrorCode.AGENT_NOT_FOUND,
                    "message": f"未知 Adapter：{adapter_id}",
                    "retryable": False,
                }
            )
        value = await adapter.detect()
        self._detect_cache[adapter_id] = (now, value)
        return value

    async def list_agents(self) -> list[AgentView]:
        if self._last_discovery is None or time.monotonic() - self._last_discovery >= self._detect_ttl:
            async with self._discovery_lock:
                if self._last_discovery is None or time.monotonic() - self._last_discovery >= self._detect_ttl:
                    await self._discover()
        return [item.model_copy(update={'guard': self._adapters['pi'].guard})
                if str(item.adapter_id) == 'pi' and hasattr(self._adapters.get('pi'), 'guard') else item
                for item in self._last_agents]

    async def discover(self) -> AgentDiscoveryResult:
        async with self._discovery_lock:
            return await self._discover()

    async def _discover(self) -> AgentDiscoveryResult:
        started = time.monotonic()
        rows = [await self._discover_one(adapter) for adapter in self._adapters.values()]
        agents = [item[0] for item in rows if item[0] is not None]
        errors = [item[1] for item in rows if item[1] is not None]
        self._last_agents = agents
        self._last_discovery = time.monotonic()
        return AgentDiscoveryResult.model_validate(
            {
                "discovered": agents,
                "total": len(agents),
                "timestamp": utc_timestamp(),
                "errors": errors,
                "durationMs": int((time.monotonic() - started) * 1000),
            }
        )

    async def discovery_payload(self) -> AgentDiscoveryCompletedPayload:
        result = await self.discover()
        ready = sum(1 for item in result.discovered if item.status is AgentStatus.READY)
        return AgentDiscoveryCompletedPayload.model_validate(
            {
                "total": result.total,
                "ready": ready,
                "errors": result.errors,
                "durationMs": result.duration_ms,
            }
        )

    async def _discover_one(
        self, adapter: AgentAdapter
    ) -> tuple[AgentView | None, AgentDiscoveryError | None]:
        descriptor = await self.detect(adapter.adapter_id, refresh=True)
        if isinstance(descriptor, AdapterFailure):
            return None, self._discovery_error(adapter.adapter_id, descriptor)
        compatible = bool(
            descriptor.installed
            and version_tuple(descriptor.detected_version or "")
            >= version_tuple(descriptor.minimum_version or "0")
        )
        if not descriptor.installed or not compatible:
            status = AgentStatus.INCOMPATIBLE
            diagnostic = (
                "Agent 未安装"
                if not descriptor.installed
                else f"版本低于 {descriptor.minimum_version}"
            )
        else:
            health = await adapter.health()
            if isinstance(health, AdapterFailure):
                status = (
                    AgentStatus.NOT_LOGGED_IN
                    if health.kind is AdapterFailureKind.NOT_LOGGED_IN
                    else AgentStatus.OFFLINE
                )
                diagnostic = health.message
            else:
                status = health.status
                diagnostic = health.diagnostic_message
        capabilities = []
        for declared in descriptor.capabilities:
            metadata = _CAPABILITY_METADATA[declared.id]
            capabilities.append(
                CapabilityItem.model_validate(
                    {
                        "id": declared.id,
                        "name": metadata.display_name,
                        "description": metadata.description,
                        "hard": metadata.hard,
                        "source": "detected",
                        "supported": declared.supported,
                        "note": declared.note,
                    }
                )
            )
        agent = AgentView.model_validate(
            {
                "id": self.runtime_instances(adapter.adapter_id)[0],
                "adapterId": adapter.adapter_id,
                "displayName": descriptor.display_name,
                "version": descriptor.detected_version or "unknown",
                "status": status,
                "detectedAt": descriptor.detected_at or utc_timestamp(),
                "capabilities": capabilities,
                "assignedRoles": [],
                "isPrimaryFor": [],
                "diagnosticMessage": diagnostic,
                "authKind": descriptor.auth_kind,
                "executablePath": descriptor.executable_path,
                "minimumVersion": descriptor.minimum_version,
            }
        )
        if adapter.adapter_id == 'pi':
            agent = agent.model_copy(update={'guard': adapter.guard})
        return agent, None

    @staticmethod
    def _discovery_error(adapter_id: str, value: AdapterFailure) -> AgentDiscoveryError:
        return AgentDiscoveryError.model_validate(
            {
                "adapterId": adapter_id,
                "code": value.code or ErrorCode.INTERNAL,
                "message": value.message,
            }
        )
