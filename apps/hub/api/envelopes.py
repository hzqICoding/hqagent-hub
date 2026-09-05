from __future__ import annotations

import uuid
from typing import Any

from fastapi.responses import JSONResponse
from protocol.generated.python import ApiEnvelope, ApiError

from core.constants import PROTOCOL_VERSION
from core.errors import HubError


def dump_model(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, list):
        return [dump_model(item) for item in value]
    if isinstance(value, dict):
        return {key: dump_model(item) for key, item in value.items()}
    return value


def success_response(data: Any, status_code: int = 200) -> JSONResponse:
    envelope = ApiEnvelope.model_validate(
        {
            "success": True,
            "data": dump_model(data),
            "requestId": f"req_{uuid.uuid4().hex}",
            "protocolVersion": PROTOCOL_VERSION,
        }
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json", by_alias=True, exclude_none=True),
    )


def error_response(error: HubError) -> JSONResponse:
    api_error = ApiError.model_validate(
        {
            "code": error.code,
            "message": error.message,
            "detail": error.detail,
            "retryable": error.retryable,
        }
    )
    envelope = ApiEnvelope.model_validate(
        {
            "success": False,
            "error": api_error,
            "requestId": f"req_{uuid.uuid4().hex}",
            "protocolVersion": PROTOCOL_VERSION,
        }
    )
    return JSONResponse(
        status_code=error.http_status,
        content=envelope.model_dump(mode="json", by_alias=True, exclude_none=True),
    )

