"""Single SQLite admission/outbox ledger, sharing the Hub's durable event sequence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from protocol.generated.python import RemoteLinkView
from core.errors import HubError
from runtime.remote.security import CredentialVault
from runtime.remote.wire import WIRE_REVISION, canonical, encode
from storage.events import EventDraft
from storage.local_chat import now, uid

MAX_SEQ = 2**53 - 1


class RemoteRepository:
    def __init__(self, database, events, directory: Path):
        self.database, self.events = database, events
        self.witness = directory / "store.witness"
        directory.mkdir(parents=True, exist_ok=True)
        with database.transaction() as tx:
            if self.get("identity", tx) is None:
                self.put("identity", {"store": uid("store"), "epoch": uid("epoch"), "ack": None,
                    "high": 0, "covered": 0, "revision": 0}, tx)
                self.put("link", {"view": {"state": "unpaired"}, "generation": 0}, tx)
                self.seal(tx)
        self.check_continuity()

    def get(self, key, tx=None):
        with self.database.locked_connection() as db:
            row = (tx.connection if tx else db).execute("SELECT value_json FROM remote_state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key, value, tx):
        tx.connection.execute("INSERT INTO remote_state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json", (key, canonical(value)))

    def seal(self, tx):
        """External monotonic witness precedes COMMIT; a crash gap freezes safely.

        Kept outside hub.db/backups. Restoring only the database is detectable,
        even when no outbound event was ever acknowledged by the server.
        """
        identity = self.get("identity", tx)
        identity["revision"] += 1
        self.put("identity", identity, tx)
        CredentialVault.atomic_write(self.witness, canonical({k: identity[k] for k in ("store", "revision")}).encode())

    def check_continuity(self):
        identity = self.get("identity")
        try:
            witness = json.loads(self.witness.read_text())
        except (OSError, ValueError):
            witness = None
        if witness == {k: identity[k] for k in ("store", "revision")}:
            return True
        with self.database.transaction() as tx:
            identity.update(store=uid("store"), epoch=uid("epoch"), ack=None, high=0, covered=0)
            self.put("identity", identity, tx)
            link = self.get("link", tx)
            if link["view"]["state"] in {"paired", "frozen", "revoked"}:
                self.set_view(tx, {**link["view"], "state": "frozen", "connectionStatus": "offline", "lastErrorCode": "REMOTE_STORE_CHANGED"})
            self.seal(tx)
        return False

    def boot(self):
        self.check_continuity()
        with self.database.transaction() as tx:
            identity = self.get("identity", tx)
            identity["epoch"] = uid("epoch")
            self.put("identity", identity, tx)
            self.seal(tx)

    def view(self):
        return RemoteLinkView.model_validate(self.get("link")["view"])

    def set_view(self, tx, value):
        # GET and event share the generated mapper, including required nulls.
        mapped = RemoteLinkView.model_validate(value).model_dump(mode="json", by_alias=True, exclude_none=True)
        link = self.get("link", tx)
        if link["view"] == mapped:
            return
        link["view"] = mapped
        self.put("link", link, tx)
        self.events.append(tx, EventDraft(aggregate_type="system", aggregate_id="remote-link",
            type="remote.link.changed", payload=mapped))

    def freeze(self, code):
        with self.database.transaction() as tx:
            value = self.get("link", tx)["view"]
            if value["state"] in {"paired", "frozen"}:
                self.set_view(tx, {**value, "state": "frozen", "lastErrorCode": code})
            self.seal(tx)

    @staticmethod
    def high_water(tx):
        row = tx.connection.execute("SELECT seq FROM sqlite_sequence WHERE name='events'").fetchone()
        return int(row[0]) if row else 0

    def cover_private(self, tx):
        identity = self.get("identity", tx)
        high = self.high_water(tx)
        if high <= identity["covered"]:
            return
        # Source Hub events remain local. Dedicated remote projections below
        # carry execution results, never raw adapter logs or local pairing codes.
        raw = self.base("events.omitted", high, identity)
        raw.update(firstSeq=identity["covered"] + 1, reason="not_remote_visible")
        self.save_frame(tx, raw)
        identity.update(covered=high, high=high)
        self.put("identity", identity, tx)

    def base(self, kind, seq, identity):
        if seq > MAX_SEQ:
            raise HubError("REMOTE_ACK_CONFLICT", "持久事件序号已耗尽，需要更换存储世代")
        return {"type": kind, "wireRevision": WIRE_REVISION, "eventId": uid("remote"),
            "workerId": self.get("link")["view"]["workerId"], "workerStoreId": identity["store"],
            "workerEpoch": identity["epoch"], "seq": seq, "occurredAt": now()}

    def emit(self, tx, kind, **fields):
        self.cover_private(tx)
        identity = self.get("identity", tx)
        raw = self.base(kind, self.high_water(tx) + 1, identity)
        raw.update(fields)
        content = encode(raw)
        event, _ = self.events.append(tx, EventDraft(aggregate_type="system", aggregate_id="remote-worker",
            type=kind, payload=json.loads(content), event_id=raw["eventId"], occurred_at=raw["occurredAt"]))
        assert event.seq == raw["seq"]
        self.save_frame(tx, raw)
        identity.update(covered=event.seq, high=event.seq)
        self.put("identity", identity, tx)
        return raw

    def save_frame(self, tx, raw):
        content = encode(raw)
        tx.connection.execute("INSERT INTO remote_outbox VALUES(?,?,?,?,?)",
            (raw["workerStoreId"], raw["seq"], raw["eventId"], content, hashlib.sha256(content.encode()).hexdigest()))

    def frames(self):
        identity = self.get("identity")
        with self.database.locked_connection() as db:
            return [r[0] for r in db.execute("SELECT frame_json FROM remote_outbox WHERE store_id=? ORDER BY seq LIMIT 200", (identity["store"],))]

    def ack(self, position):
        identity = self.get("identity")
        if (position is None and identity["ack"] is not None) or (position is not None and (
            position["workerStoreId"] != identity["store"] or position["seq"] > identity["high"] or
            position["seq"] < (identity["ack"] or 0))):
            self.freeze("REMOTE_ACK_CONFLICT")
            raise HubError("REMOTE_ACK_CONFLICT", "确认位置与持久事件记录不一致，需要对账")
        if position is None:
            return
        with self.database.transaction() as tx:
            # Never trim into the middle of an immutable omitted range.
            for row in tx.connection.execute("SELECT frame_json FROM remote_outbox WHERE store_id=? AND seq>?", (identity["store"], position["seq"])):
                raw = json.loads(row[0])
                if raw["type"] == "events.omitted" and raw["firstSeq"] <= position["seq"]:
                    raise HubError("REMOTE_ACK_CONFLICT", "确认位置截断了不可变覆盖记录")
            tx.connection.execute("DELETE FROM remote_outbox WHERE store_id=? AND seq<=?", (identity["store"], position["seq"]))
            identity["ack"] = position["seq"]
            self.put("identity", identity, tx)
            self.seal(tx)

    def inbox(self, command_id, tx=None):
        worker = self.get("link", tx)["view"]["workerId"]
        with self.database.locked_connection() as db:
            row = (tx.connection if tx else db).execute("SELECT * FROM remote_inbox WHERE worker_id=? AND command_id=?", (worker, command_id)).fetchone()
        return dict(row) if row else None

    def patch_inbox(self, tx, command_id, **values):
        assert set(values) <= {"status", "run_id", "receipt_json", "observation_json"}
        worker = self.get("link", tx)["view"]["workerId"]
        columns = ",".join(f"{k}=?" for k in values)
        tx.connection.execute(f"UPDATE remote_inbox SET {columns} WHERE worker_id=? AND command_id=?", (*values.values(), worker, command_id))
