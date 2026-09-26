from __future__ import annotations

import json
from typing import get_args

from protocol.generated.python import (PROTOCOL_VERSION, RemoteWorkerHello,
    RemoteServerOutboundFrame, RemoteWorkerOutboundFrame)
from core.errors import HubError

# The generated Literal is the frozen schema constant (no second version source).
WIRE_REVISION = get_args(RemoteWorkerHello.model_fields["wire_revision"].annotation)[0]
MAX_FRAME_BYTES = 256 * 1024


def canonical(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def encode(value: dict) -> str:
    value = RemoteWorkerOutboundFrame.model_validate(value).model_dump(mode="json", by_alias=True, exclude_none=True)
    content = canonical(value)
    if len(content.encode("utf-8")) > MAX_FRAME_BYTES:
        raise HubError("REMOTE_FRAME_TOO_LARGE", "远程帧超过大小限制")
    return content


def decode(content: str | bytes) -> dict:
    if len(content.encode("utf-8") if isinstance(content, str) else content) > MAX_FRAME_BYTES:
        raise HubError("REMOTE_FRAME_TOO_LARGE", "远程帧超过大小限制")
    try:
        value = json.loads(content)
        # Negotiate before imposing revision 1's strict DTO. Unknown revisions
        # never get dispatched; their diagnostic text never reaches the UI.
        if isinstance(value, dict) and value.get("type") == "worker.hello_rejected":
            revisions = value.get("supportedWireRevisions")
            if isinstance(revisions, list) and 1 <= len(revisions) <= 16 and all(type(v) is int and 1 <= v <= 2147483647 for v in revisions):
                if WIRE_REVISION not in revisions:
                    raise HubError("REMOTE_PROTOCOL_UNSUPPORTED", "服务端不支持当前线路修订")
        return RemoteServerOutboundFrame.model_validate(value).model_dump(mode="json", by_alias=True, exclude_none=True)
    except HubError:
        raise
    except Exception:
        raise HubError("REMOTE_PROTOCOL_UNSUPPORTED", "远程帧无法按当前线路修订验证") from None
