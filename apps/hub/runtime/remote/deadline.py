"""Conservative server-time upper bound. Wall time is only a discontinuity alarm."""
import time
from datetime import datetime

from core.errors import HubError


def instant(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, OverflowError):
        raise HubError("VALIDATION_FAILED", "远程时间字段无效") from None


class DeliveryClock:
    def __init__(self, *, monotonic=time.monotonic, wall=time.time):
        self.monotonic, self.wall = monotonic, wall
        self.anchor = None

    def calibrate(self, server_time, started):
        received = self.monotonic()
        self.anchor = (received, self.wall(), instant(server_time) + max(0, received - started))

    def invalidate(self):
        self.anchor = None

    def upper(self):
        if self.anchor is None:
            raise HubError("REMOTE_DELIVERY_EXPIRED", "送达时钟尚未核对，命令不执行")
        mono, wall, server = self.anchor
        elapsed = self.monotonic() - mono
        # An unobserved long pause/sleep or a clock discontinuity cannot grant
        # additional execution time. A new handshake is needed to recalibrate.
        if elapsed < 0 or elapsed > 45 or abs((self.wall() - wall) - elapsed) > 1:
            self.invalidate()
            raise HubError("REMOTE_DELIVERY_EXPIRED", "送达时钟界限已失效，命令不执行")
        return server + elapsed

    def check(self, frame):
        end = instant(frame["deliverBy"])
        if not 0 < end - instant(frame["createdAt"]) <= 30:
            raise HubError("REMOTE_DELIVERY_EXPIRED", "送达期限无效，命令不执行")
        if self.upper() >= min(end, instant(frame["expiresAt"])):
            raise HubError("REMOTE_DELIVERY_EXPIRED", "设备离线，发送失败")
