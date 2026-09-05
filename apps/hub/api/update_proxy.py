from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from protocol.generated.python import UpdateAgentRuntimeDescriptor

from core.errors import FeatureUnavailable, HubError


class UpdateAgentProxy:
    def __init__(self, descriptor_path: Path, timeout_seconds: float = 5.0) -> None:
        self.descriptor_path = descriptor_path
        self.timeout_seconds = timeout_seconds

    async def descriptor(self) -> UpdateAgentRuntimeDescriptor | None:
        try:
            raw = json.loads(self.descriptor_path.read_text(encoding="utf-8"))
            descriptor = UpdateAgentRuntimeDescriptor.model_validate(raw)
        except (OSError, ValueError):
            return None
        if descriptor.base_url != f"http://127.0.0.1:{descriptor.port}":
            return None
        if descriptor.pid <= 0 or not self._pid_exists(descriptor.pid):
            return None
        return descriptor

    async def availability(self) -> tuple[bool, str | None]:
        descriptor = await self.descriptor()
        if descriptor is None:
            return False, "Update Agent 未运行或 runtime/update-agent.json 无效"
        return True, None

    async def request(self, method: str, path: str, body: Any | None = None) -> Any:
        descriptor = await self.descriptor()
        if descriptor is None:
            raise FeatureUnavailable("updates", "Update Agent 未运行或运行时描述符无效")
        headers = {"Authorization": f"Bearer {descriptor.token}"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False) as client:
                response = await client.request(
                    method,
                    descriptor.base_url + path,
                    headers=headers,
                    json=body,
                )
        except httpx.HTTPError as exc:
            raise FeatureUnavailable("updates", f"Update Agent 无法连接：{type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise HubError(
                "FEATURE_UNAVAILABLE" if response.status_code >= 500 else "BAD_REQUEST",
                "Update Agent 请求失败",
                detail={"status": response.status_code, "path": path},
            )
        if not response.content:
            return None
        try:
            payload = response.json()
        except ValueError as exc:
            raise HubError("INTERNAL", "Update Agent 返回了无效 JSON") from exc
        if isinstance(payload, dict) and "success" in payload:
            if not payload.get("success"):
                error = payload.get("error") or {}
                raise HubError(
                    str(error.get("code", "INTERNAL")),
                    str(error.get("message", "Update Agent 请求失败")),
                    detail=error.get("detail"),
                )
            return payload.get("data")
        return payload

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        if pid == os.getpid():
            return True
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

