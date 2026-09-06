from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def diagnostic_raw(value: Any) -> dict[str, str]:
    """把供应商原文限制在 2048 字符，并保持生成 DTO 要求的 object 形状。"""

    try:
        text = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(value)
    return {"vendor": text[:2048]}


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
