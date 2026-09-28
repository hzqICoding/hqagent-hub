import hashlib
import json
import secrets
from datetime import datetime, timezone

from protocol.generated import python as dto

MAX_SEQ = 2**53 - 1


def uid():
    return secrets.token_urlsafe(24)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def stamp(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def seconds(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def validated(name, value):
    return getattr(dto, name).model_validate(value).model_dump(mode="json", by_alias=True, exclude_none=True)


# Fixed messages deliberately contain neither user input nor exception text.
ERRORS = {
    "NOT_FOUND": (404, False), "VALIDATION_FAILED": (422, False),
    "IDEMPOTENCY_MISMATCH": (409, False), "INTERNAL": (500, True),
    "REMOTE_AUTH_REQUIRED": (401, False), "REMOTE_CSRF_REJECTED": (403, False),
    "REMOTE_DEVICE_REVOKED": (403, False), "REMOTE_DEVICE_AUTH_FAILED": (401, False),
    "REMOTE_DEVICE_OFFLINE": (409, True),
    "REMOTE_PAIRING_EXPIRED": (410, False), "REMOTE_PAIRING_CONFLICT": (409, False),
    "REMOTE_PAIRING_INVALID": (404, False), "REMOTE_COMMAND_EXPIRED": (410, False),
    "REMOTE_COMMAND_WITHDRAWN": (409, False), "REMOTE_WITHDRAWAL_TOO_LATE": (409, False),
    "REMOTE_STORE_CHANGED": (409, False), "REMOTE_EPOCH_STALE": (409, False),
    "REMOTE_PROTOCOL_UNSUPPORTED": (409, False), "REMOTE_EVENT_CONFLICT": (409, False),
    "REMOTE_ACK_CONFLICT": (409, False), "REMOTE_TARGET_MISMATCH": (409, False),
    "REMOTE_SCENE_VERSION_MISMATCH": (409, False), "REMOTE_SEQUENCE_GAP": (409, True),
    "REMOTE_APPROVAL_FORBIDDEN": (403, False), "REMOTE_CURSOR_EXPIRED": (410, False),
    "REMOTE_CURSOR_INVALID": (400, False), "REMOTE_RATE_LIMITED": (429, True),
    "REMOTE_FRAME_TOO_LARGE": (413, False), "CONVERSATION_AUTHORITY_MISMATCH": (409, False),
    "REMOTE_CONVERSATION_BUSY": (409, True), "REMOTE_STATE_NOT_READY": (409, True),
    "REMOTE_SYNC_CONFLICT": (409, False), "REMOTE_SYNC_DISABLED": (409, False),
    "REMOTE_DELIVERY_EXPIRED": (409, True), "REMOTE_REVISION_REQUIRED": (409, False),
    "REMOTE_SYNC_RESOURCE_LIMIT": (413, False),
    "FEATURE_UNAVAILABLE": (503, True),
}


class Fault(Exception):
    def __init__(self, code):
        self.code = code
        self.status, self.retryable = ERRORS[code]
        super().__init__(code)

    def view(self):
        message = '设备离线，发送失败' if self.code in {'REMOTE_DEVICE_OFFLINE', 'REMOTE_DELIVERY_EXPIRED'} else self.code
        return validated("RemoteError", dict(code=self.code, message=message, retryable=self.retryable))


def require(condition, code="VALIDATION_FAILED"):
    if not condition:
        raise Fault(code)
