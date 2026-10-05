"""Bounded revision-2 send window; no cached body survives a sync reset."""
import json
import time

from core.errors import HubError
from core.diagnostics import remote_command
from runtime.remote.sync import CONTENT_TYPES, WINDOW_BYTES


class SendWindow:
    def __init__(self, repository, sync):
        self.repo, self.sync = repository, sync
        self.pending = {}

    async def flush(self, send):
        ack = self.repo.get("identity")["ack"] or 0
        self.pending = {k: v for k, v in self.pending.items() if v["end"] > ack}
        proofs = self.sync.control_frames()
        frames = self.repo.frames()
        urgent = [f for f in frames if json.loads(f)["type"] in {
            "command.received", "command.accepted", "command.rejected", "command.completed", "command.failed",
            "command.control_result", "sync.busy.snapshot", "approval.state_changed", "sync.reset"}]
        # At most two ahead-of-prefix observations per pass. Always leave room
        # for the oldest gap so priority delivery cannot deadlock contiguous ACK.
        candidates = proofs + urgent[:2] + frames
        seen = set()
        for content in candidates:
            frame = json.loads(content)
            if frame.get("wireRevision") != self.repo.get("identity").get("wireRevision"):
                raise HubError("REMOTE_PROTOCOL_UNSUPPORTED", "禁止重写旧线路事件")
            key = frame.get("eventId") or frame["redactionId"]
            if key in seen:
                continue
            seen.add(key)
            privacy = frame["type"] in {"sync.reset", "sync.content.redaction", "native.index.deleted"}
            end = frame["seq"] if "seq" in frame else max(s["seq"] for s in frame["slots"])
            if end <= ack:
                continue
            if frame["type"] in CONTENT_TYPES:
                if not self.sync.settings().mirror_enabled or frame.get("syncGeneration") != self.sync.settings().sync_generation:
                    continue
                with self.repo.database.locked_connection() as db:
                    current = db.execute("SELECT frame_json FROM remote_outbox WHERE store_id=? AND seq=?",
                        (frame["workerStoreId"], frame["seq"])).fetchone()
                if current is None or current[0] != content:
                    continue
            previous = self.pending.get(key)
            if previous and time.monotonic() - previous["sent"] < 15:
                continue
            size = len(content.encode("utf-8"))
            if previous is None:
                used = sum(p["size"] for p in self.pending.values())
                if len(self.pending) >= (16 if privacy else 14) or used + size > (WINDOW_BYTES if privacy else WINDOW_BYTES - 128 * 1024):
                    continue
                if frame["type"] in CONTENT_TYPES and sum(p["content"] for p in self.pending.values()) >= 12:
                    continue
            await send(content)
            remote_command(frame, 'sent')
            self.pending[key] = {"end": end, "size": size, "sent": time.monotonic(), "content": frame["type"] in CONTENT_TYPES}
