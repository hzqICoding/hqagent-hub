from __future__ import annotations

import json
from typing import get_args

from pydantic import ValidationError

from protocol.generated.python import (PROTOCOL_VERSION, RemoteWorkerHello,
    RemoteServerOutboundFrame, RemoteWorkerOutboundFrame,
    RemoteV2ServerOutboundFrame, RemoteV2WorkerOutboundFrame)
from core.errors import HubError

# The generated Literal is the frozen schema constant (no second version source).
WIRE_REVISION = get_args(RemoteWorkerHello.model_fields["wire_revision"].annotation)[0]
MAX_FRAME_BYTES = 256 * 1024
CODECS = {1: (RemoteWorkerOutboundFrame, RemoteServerOutboundFrame),
          2: (RemoteV2WorkerOutboundFrame, RemoteV2ServerOutboundFrame)}


def canonical(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def encode(value: dict) -> str:
    try:
        codec = CODECS.get(value.get("wireRevision"))
        if codec is None:
            raise HubError("REMOTE_PROTOCOL_UNSUPPORTED", "不支持的线路修订")
        value = codec[0].model_validate(value).model_dump(mode="json", by_alias=True, exclude_none=True)
    except ValidationError as error:
        oversized = any(e["type"] in {"string_too_long", "too_long"} for e in error.errors(include_input=False))
        raise HubError("REMOTE_FRAME_TOO_LARGE" if oversized else "REMOTE_PROTOCOL_UNSUPPORTED", "远程输出不符合线路边界") from None
    content = canonical(value)
    if len(content.encode("utf-8")) > MAX_FRAME_BYTES:
        raise HubError("REMOTE_FRAME_TOO_LARGE", "远程帧超过大小限制")
    return content


def decode(content: str | bytes, *, revision: int = 1, negotiation: bool = False) -> dict:
    if len(content.encode("utf-8") if isinstance(content, str) else content) > MAX_FRAME_BYTES:
        raise HubError("REMOTE_FRAME_TOO_LARGE", "远程帧超过大小限制")
    try:
        def unique_pairs(pairs):
            result = {}
            for key, item in pairs:
                if key in result:
                    raise ValueError("duplicate field")
                result[key] = item
            return result
        value = json.loads(content, object_pairs_hook=unique_pairs)
        # Negotiate before imposing revision 1's strict DTO. Unknown revisions
        # never get dispatched; their diagnostic text never reaches the UI.
        if isinstance(value, dict) and value.get("type") == "worker.hello_rejected":
            revisions = value.get("supportedWireRevisions")
            if isinstance(revisions, list) and 1 <= len(revisions) <= 16 and all(type(v) is int and 1 <= v <= 2147483647 for v in revisions):
                if revision not in revisions and not negotiation:
                    raise HubError("REMOTE_PROTOCOL_UNSUPPORTED", "服务端不支持当前线路修订")
        actual = value.get("wireRevision") if isinstance(value, dict) else None
        if actual != revision and not (negotiation and value.get("type") == "worker.hello_rejected"):
            raise HubError("REMOTE_PROTOCOL_UNSUPPORTED", "连接线路修订不匹配")
        mapped = CODECS[actual][1].model_validate(value).model_dump(mode="json", by_alias=True, exclude_none=True)
        if mapped != value:
            raise ValueError("wire field names must be camelCase")
        return mapped
    except HubError:
        raise
    except Exception:
        raise HubError("REMOTE_PROTOCOL_UNSUPPORTED", "远程帧无法按当前线路修订验证") from None
