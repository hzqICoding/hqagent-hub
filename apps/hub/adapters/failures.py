from __future__ import annotations

import json
import re
from typing import Any

from protocol.generated.python import (
    AdapterFailure,
    AdapterFailureKind,
    AgentFailedPayload,
    AgentResult,
    CapabilityId,
    ErrorCode,
)

from adapters.events import AdapterEvent


_ERROR_CODE_BY_KIND = {
    AdapterFailureKind.NOT_INSTALLED: ErrorCode.AGENT_NOT_FOUND,
    AdapterFailureKind.NOT_LOGGED_IN: ErrorCode.AGENT_NOT_LOGGED_IN,
    AdapterFailureKind.VERSION_INCOMPATIBLE: ErrorCode.AGENT_INCOMPATIBLE,
    AdapterFailureKind.CAPABILITY_MISSING: ErrorCode.CAPABILITY_MISSING,
    AdapterFailureKind.TRANSPORT_ERROR: ErrorCode.AGENT_OFFLINE,
    AdapterFailureKind.AGENT_ERROR: ErrorCode.INTERNAL,
    AdapterFailureKind.TIMEOUT: ErrorCode.INTERNAL,
    AdapterFailureKind.CANCELLED: ErrorCode.TASK_NOT_CANCELLABLE,
    AdapterFailureKind.PATH_VIOLATION: ErrorCode.PATH_NOT_ALLOWED,
}


def failure(
    kind: AdapterFailureKind,
    message: str,
    *,
    retryable: bool,
    raw: Any | None = None,
    missing_capabilities: list[CapabilityId] | None = None,
    violation_paths: list[str] | None = None,
) -> AdapterFailure:
    raw_text: str | None
    if raw is None:
        raw_text = None
    elif isinstance(raw, str):
        raw_text = raw[:2048]
    else:
        raw_text = json.dumps(raw, ensure_ascii=False, default=str)[:2048]
    return AdapterFailure.model_validate(
        {
            "kind": kind,
            "code": _ERROR_CODE_BY_KIND[kind],
            "message": message,
            "retryable": retryable,
            "raw": raw_text,
            "missingCapabilities": missing_capabilities,
            "violationPaths": violation_paths,
        }
    )


def failure_event(value: AdapterFailure, vendor_type: str) -> AdapterEvent:
    payload = AgentFailedPayload.model_validate(
        {
            "errorCode": value.code or _ERROR_CODE_BY_KIND[value.kind],
            "message": value.message,
        }
    )
    return AdapterEvent.create(vendor_type, "agent.failed", payload)


def parse_agent_result(value: Any) -> AgentResult:
    if isinstance(value, AgentResult):
        return value
    if isinstance(value, dict):
        return AgentResult.model_validate(value)
    if not isinstance(value, str):
        raise ValueError("供应商没有返回 JSON 对象")
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    return AgentResult.model_validate(json.loads(text))


def version_tuple(value: str) -> tuple[int, ...]:
    from adapters.versions import cli_version, version_tuple as numeric_version
    return numeric_version(cli_version(value)) or ()
