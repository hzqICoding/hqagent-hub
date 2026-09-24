from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def diagnostic_raw(value: Any) -> dict[str, str]:
    """把供应商原文限制在 2048 字符，并保持生成 DTO 要求的 object 形状。"""

    try:
        text = json.dumps(_public_diagnostic(value), ensure_ascii=False, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(value)
    return {"vendor": text[:2048]}


def _public_diagnostic(value: Any) -> Any:
    if isinstance(value, dict):
        if value.get("type") in {"reasoning", "thinking", "redacted_thinking"}:
            return {"type": value.get("type"), "redacted": True}
        hidden = {"authorization", "apikey", "api_key", "access_token", "refresh_token", "encrypted_content", "thinking"}
        return {key: "[redacted]" if key.lower() in hidden else _public_diagnostic(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_public_diagnostic(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"(?i)Bearer\s+\S+|sk-[A-Za-z0-9_-]+", "[redacted]", value)
    return value


@dataclass(frozen=True, slots=True)
class AdapterEvent:
    """Adapter 内部事件；Hub/W3 负责包装成带全局 seq 的 HubEvent。"""

    vendor_type: str
    unified_type: str
    payload: BaseModel | dict[str, Any]
    occurred_at: str
    external_request_id: str | None = None

    @classmethod
    def create(
        cls,
        vendor_type: str,
        unified_type: str,
        payload: BaseModel | dict[str, Any],
        *,
        external_request_id: str | None = None,
    ) -> "AdapterEvent":
        return cls(
            vendor_type=vendor_type,
            unified_type=unified_type,
            payload=payload,
            occurred_at=utc_timestamp(),
            external_request_id=external_request_id,
        )
