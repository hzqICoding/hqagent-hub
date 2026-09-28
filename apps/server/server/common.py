import hashlib
import json
import secrets
from datetime import datetime, timezone

from protocol.generated import python as dto
from .public_contract import HTTP_ERRORS

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


class Fault(Exception):
    def __init__(self, code, *, detail=None):
        self.code = code
        mapping = HTTP_ERRORS[code]
        self.status, self.retryable = mapping['status'], mapping['retryable']
        self.detail = detail
        super().__init__(code)

    def view(self):
        message = HTTP_ERRORS[self.code]['message'] if self.code in {'REMOTE_DEVICE_OFFLINE', 'REMOTE_DELIVERY_EXPIRED', 'REMOTE_DEVICE_SUSPENDED'} else self.code
        return validated("RemoteError", dict(code=self.code, message=message, retryable=self.retryable))

    def http_view(self):
        result = dict(code=self.code, message=HTTP_ERRORS[self.code]['message'], retryable=self.retryable)
        if self.detail:
            result['detail'] = validated('RemoteHttpErrorDetail', self.detail)
        return validated('RemoteHttpError', result)


def require(condition, code="VALIDATION_FAILED"):
    if not condition:
        raise Fault(code)
