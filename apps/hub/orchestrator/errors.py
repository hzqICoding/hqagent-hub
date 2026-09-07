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


class AdapterStartFailedError(OrchestrationError):
    """start() 返回了 AdapterFailure。

    契约表（adapter-contract.md §1）给 start(spec) 列了 AgentSessionHandle 和
    AdapterFailure 两列，但没写清失败是「返回」还是「抛出」。W2 读成返回
    （联合类型），W3 的 Port 声明成 -> AgentSessionHandle 没处理联合，
    于是集成时直接去取 handle.session_id 炸了。

    W2 的读法是对的：AdapterFailureKind 那九个值就是给 Hub 做
    kind → 动作映射用的（见契约 §8 的失败分类表），抛异常会把这层结构丢掉。
    所以这里把返回值转成带结构的异常，让上层能按 kind 分别处理。
    """

    def __init__(self, failure: Any) -> None:
        self.failure = failure
        kind = getattr(failure, "kind", None)
        super().__init__(
            "AGENT_START_FAILED",
            getattr(failure, "message", "Adapter 启动失败"),
            {
                "kind": str(kind) if kind is not None else None,
                "retryable": getattr(failure, "retryable", None),
                "missingCapabilities": [
                    str(c) for c in (getattr(failure, "missing_capabilities", None) or [])
                ],
            },
        )
