from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class OrchestrationError(Exception):
    code: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


class RoleUnresolvedError(OrchestrationError):
    def __init__(
        self,
        role_id: str,
        message: str,
        *,
        missing_capabilities: tuple[str, ...] = (),
        attempted: tuple[str, ...] = (),
    ) -> None:
        super().__init__(
            "ROLE_UNRESOLVED",
            message,
            {
                "roleId": role_id,
                "missingCapabilities": list(missing_capabilities),
                "attempted": list(attempted),
            },
        )


class CapabilityMissingError(OrchestrationError):
    def __init__(self, missing_capabilities: tuple[str, ...], message: str | None = None) -> None:
        super().__init__(
            "CAPABILITY_MISSING",
            message or f"缺少硬能力：{', '.join(missing_capabilities)}",
            {"missingCapabilities": list(missing_capabilities)},
        )


class SessionNotResumableError(OrchestrationError):
    def __init__(self, session_id: str, reason: str) -> None:
        super().__init__(
            "SESSION_NOT_RESUMABLE",
            reason,
            {"sessionId": session_id},
        )


class InvalidTaskActionError(OrchestrationError):
    def __init__(self, message: str, **detail: Any) -> None:
        super().__init__("TASK_ACTION_INVALID", message, detail)


class PathNotAllowedError(OrchestrationError):
    def __init__(self, violation_paths: tuple[str, ...], allowed_paths: tuple[str, ...]) -> None:
        super().__init__(
            "PATH_NOT_ALLOWED",
            f"检测到越界路径：{', '.join(violation_paths)}",
            {
                "violationPaths": list(violation_paths),
                "allowedPaths": list(allowed_paths),
            },
        )


class ApprovalError(OrchestrationError):
    pass
