"""D42 negotiation boundary; retain old codecs here when adding revision N+1.

Revision 1 has no predecessor. Package versions are diagnostic only.
Persisted event content is never upgraded or rewritten on retransmission.
"""
import json

from .common import Fault, require, validated

MAX_FRAME_BYTES = 262144
CURRENT = 1
CODECS = {1: ("RemoteWorkerOutboundFrame", "RemoteServerOutboundFrame", "RemoteCommandEnvelope")}


def revision(frame):
    return frame["wireRevision"]


def decode(raw, revision=None):
    require(len(raw.encode("utf-8")) <= MAX_FRAME_BYTES, "REMOTE_FRAME_TOO_LARGE")
    try:
        value = json.loads(raw)
        require(isinstance(value, dict))
        # Read only bounded discriminator fields before selecting the strict DTO.
        offered = value.get("wireRevision")
        require(type(offered) is int and offered in CODECS, "REMOTE_PROTOCOL_UNSUPPORTED")
        require(revision is None or offered == revision, "REMOTE_PROTOCOL_UNSUPPORTED")
        if revision is None:
            require(value.get("type") == "worker.hello", "REMOTE_PROTOCOL_UNSUPPORTED")
        return validated(CODECS[offered][0], value)
    except Fault:
        raise
    except (ValueError, TypeError, RecursionError):
        raise Fault("VALIDATION_FAILED") from None


def encode(value, revision=CURRENT):
    require(revision in CODECS, "REMOTE_PROTOCOL_UNSUPPORTED")
    value = dict(value, wireRevision=revision)
    if value["type"] == "worker.hello_rejected":
        value["supportedWireRevisions"] = sorted(CODECS)
    result = validated(CODECS[revision][1], value)
    require(len(json.dumps(result, ensure_ascii=False).encode()) <= MAX_FRAME_BYTES, "REMOTE_FRAME_TOO_LARGE")
    return result


def command(value, revision=CURRENT):
    return validated(CODECS[revision][2], dict(value, wireRevision=revision))
