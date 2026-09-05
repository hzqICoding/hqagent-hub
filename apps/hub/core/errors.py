from __future__ import annotations

from typing import Any

from protocol.generated.python import ERROR_CATALOG


class HubError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        catalog = ERROR_CATALOG.get(code, ERROR_CATALOG["INTERNAL"])
        self.code = code
        self.message = message
        self.detail = detail
        self.http_status = int(catalog["http"])
        self.retryable = bool(catalog["retryable"])


class FeatureUnavailable(HubError):
    def __init__(self, feature: str, reason: str) -> None:
        super().__init__(
            "FEATURE_UNAVAILABLE",
            f"{feature} 当前不可用：{reason}",
            detail={"feature": feature, "reason": reason},
        )

