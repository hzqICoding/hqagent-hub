from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable

from protocol import PACKAGE_ROOT
from protocol.generated.python import AgentProgressPayload, VendorEventMapping

from adapters.events import AdapterEvent, diagnostic_raw


PayloadFactory = Callable[[dict[str, Any]], Any]


def _load_frozen_event_types() -> frozenset[str]:
    dictionary = Path(PACKAGE_ROOT) / "events" / "event-dictionary.md"
    text = dictionary.read_text(encoding="utf-8")
    return frozenset(re.findall(r"\|\s*\d+\s*\|\s*`([^`]+)`", text))


FROZEN_EVENT_TYPES = _load_frozen_event_types()


class EventMapper:
    def __init__(self, mappings: Iterable[VendorEventMapping]) -> None:
        self.mappings = tuple(mappings)
        self._by_vendor = {item.vendor_type: item for item in self.mappings}
        self._dropped: Counter[str] = Counter()
        for item in self.mappings:
            if item.unified_type not in FROZEN_EVENT_TYPES:
                raise ValueError(f"未冻结的统一事件类型：{item.unified_type}")

    @property
    def dropped_counts(self) -> dict[str, int]:
        return dict(self._dropped)

    def map(
        self,
        vendor_type: str,
        raw: dict[str, Any],
        payload_factory: PayloadFactory | None = None,
    ) -> AdapterEvent | None:
        mapping = self._by_vendor.get(vendor_type)
        if mapping is None:
            self._dropped["__unknown__"] += 1
            payload = AgentProgressPayload.model_validate(
                {
                    "message": f"未识别的供应商事件：{vendor_type}",
                    "raw": diagnostic_raw(raw),
                }
            )
            return AdapterEvent.create(vendor_type, "agent.progress", payload)
        if mapping.dropped:
            self._dropped[vendor_type] += 1
            return None
        payload = payload_factory(raw) if payload_factory else AgentProgressPayload.model_validate(
            {
                "message": mapping.note or vendor_type,
                "raw": diagnostic_raw(raw),
            }
        )
        return AdapterEvent.create(vendor_type, mapping.unified_type, payload)
