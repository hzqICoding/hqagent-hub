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
DEFER_EVENT = object()


class RemoteRepository:
    def __init__(self, database, events, directory: Path):
        self.database, self.events = database, events
        self.source_mapper = None
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
        # A background query audit can seal concurrently. Observe the database
        # identity and external witness as one pair, never old DB + new witness.
        with self.database.locked_connection():
            return self._check_continuity_locked()

    def _check_continuity_locked(self):
        identity = self.get("identity")
        try:
            witness = json.loads(self.witness.read_text())
        except (OSError, ValueError):
            witness = None
        if witness == {k: identity[k] for k in ("store", "revision")}:
            return True
        with self.database.transaction() as tx:
            identity.update(store=uid("store"), epoch=uid("epoch"), ack=None, high=0, covered=0,
                            reconciliationRequired=True)
            self.put("identity", identity, tx)
            # The restored queue can contain work that already ran after the
            # backup. It must not be picked up by the existing local supervisor.
            tx.connection.execute("UPDATE local_runs SET status='paused',error=? WHERE conversation_id IN "
                "(SELECT conversation_id FROM remote_conversations) AND status NOT IN ('succeeded','failed','cancelled')",
                ("远程存储恢复后执行事实待核对",))
            tx.connection.execute("UPDATE local_runs SET status='paused',error=? WHERE run_id IN "
                "(SELECT run_id FROM remote2_delivery WHERE run_id IS NOT NULL) AND status NOT IN ('succeeded','failed','cancelled')",
                ("远程存储恢复后执行事实待核对",))
            tx.connection.execute("UPDATE remote2_gates SET state='recovery' WHERE state IN ('provisional','granted')")
            link = self.get("link", tx)
            if link["view"]["state"] in {"paired", "frozen", "revoked"}:
                self.set_view(tx, {**link["view"], "state": "frozen", "connectionStatus": "offline", "lastErrorCode": "REMOTE_STORE_CHANGED"})
            self.seal(tx)
        return False

    def allow_dispatch(self, record):
        with self.database.locked_connection() as db:
            remote = db.execute("SELECT 1 FROM remote_conversations WHERE conversation_id=?", (record["conversation_id"],)).fetchone()
            remote = remote or db.execute("SELECT 1 FROM remote2_delivery WHERE run_id=?", (record["run_id"],)).fetchone()
        if not remote:
            return True
        return self.check_continuity() and not self.get("identity").get("reconciliationRequired", False)

    def boot(self):
        self.check_continuity()
        with self.database.transaction() as tx:
            identity = self.get("identity", tx)
            identity["epoch"] = uid("epoch")
            self.put("identity", identity, tx)
            view = self.get("link", tx)["view"]
            if view["state"] in {"paired", "revoked", "frozen"}:
                self.set_view(tx, {**view, "connectionStatus": "offline"})
            self.seal(tx)

    def new_binding_store(self, tx):
        """A new credential never transfers the old device's outbox/conversations."""
        old = self.get("identity", tx)
        self.put("identity", {"store": uid("store"), "epoch": uid("epoch"), "ack": None,
            "high": 0, "covered": 0, "privateThrough": self.high_water(tx), "revision": old["revision"]}, tx)

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
            return False
        first_private = None
        covered = identity["covered"]
        if identity.get("privateThrough", 0) > covered:
            # At credential creation all preceding history is provably outside
            # this binding, even if local event retention already pruned it.
            end = identity["privateThrough"]
            raw = self.base("events.omitted", end, identity)
            raw.update(firstSeq=covered + 1, reason="not_remote_visible")
            self.save_frame(tx, raw)
            covered = end
            identity.update(covered=end, high=max(identity["high"], end))
            self.put("identity", identity, tx)
            if covered == high:
                return True
        def flush(last):
            nonlocal first_private
            if first_private is not None:
                raw = self.base("events.omitted", last, identity)
                raw.update(firstSeq=first_private, reason="not_remote_visible")
                self.save_frame(tx, raw)
                first_private = None
        rows = tx.connection.execute("SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT 500",
                                     (covered,)).fetchall()
        if not rows:
            raise HubError("REMOTE_ACK_CONFLICT", "本机事件历史缺失，需要对账")
        for row in rows:
            if row["seq"] != covered + 1:
                raise HubError("REMOTE_ACK_CONFLICT", "本机事件序号存在无法证明的缺口")
            existing = tx.connection.execute("SELECT 1 FROM remote_outbox WHERE store_id=? AND seq=?",
                                             (identity["store"], row["seq"])).fetchone()
            if existing:
                flush(covered)
                covered = row["seq"]
                continue
            if row["aggregate_id"] == "remote-worker":
                original = json.loads(row["payload_json"])
                if original.get("workerStoreId") == identity["store"]:
                    # An out-of-order ack must never have deleted this frame.
                    raise HubError("REMOTE_ACK_CONFLICT", "远程关键事件缺少持久 Outbox")
                projected = None  # History belongs to a previous device binding.
            else:
                projected = self.source_mapper(tx, row) if self.source_mapper else None
            if projected is DEFER_EVENT:
                break  # Task creation committed; its LocalRun binding is in flight.
            if projected is None:
                if first_private is None:
                    first_private = row["seq"]
            else:
                flush(covered)
                kind, fields = projected
                raw = self.base(kind, row["seq"], identity)
                raw.update(fields, occurredAt=row["occurred_at"])
                self.save_frame(tx, raw)
            covered = row["seq"]
        flush(covered)
        identity.update(covered=covered, high=max(identity["high"], covered))
        self.put("identity", identity, tx)
        return covered > (rows[0]["seq"] - 1)

    def base(self, kind, seq, identity):
        if seq > MAX_SEQ:
            raise HubError("REMOTE_ACK_CONFLICT", "持久事件序号已耗尽，需要更换存储世代")
        return {"type": kind, "wireRevision": identity.get("wireRevision", WIRE_REVISION), "eventId": uid("remote"),
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
        # Pending source projections can leave earlier gaps. They must be filled
        # before covered or a peer's contiguous ack can advance past this event.
        if identity["covered"] == event.seq - 1:
            identity["covered"] = event.seq
        identity["high"] = event.seq
        self.put("identity", identity, tx)
        return raw

    def save_frame(self, tx, raw):
        content = encode(raw)
        tx.connection.execute("INSERT INTO remote_outbox VALUES(?,?,?,?,?)",
            (raw["workerStoreId"], raw["seq"], raw["eventId"], content, hashlib.sha256(content.encode()).hexdigest()))

    def frames(self):
        identity = self.get("identity")
        with self.database.locked_connection() as db:
            return [r[0] for r in db.execute("SELECT frame_json FROM remote_outbox WHERE store_id=? AND frame_json<>'{}' ORDER BY seq LIMIT 200", (identity["store"],))]

    def ack(self, position):
        if not self.check_continuity():
            raise HubError("REMOTE_STORE_CHANGED", "本机存储恢复需要对账")
        identity = self.get("identity")
        if (position is None and identity["ack"] is not None) or (position is not None and (
            position["workerStoreId"] != identity["store"] or position["seq"] > identity["high"] or
            position["seq"] < (identity["ack"] or 0))):
            self.freeze("REMOTE_ACK_CONFLICT")
            raise HubError("REMOTE_ACK_CONFLICT", "确认位置与持久事件记录不一致，需要对账")
        if position is None:
            return
        if position["seq"] > identity["covered"]:
            self.freeze("REMOTE_ACK_CONFLICT")
            raise HubError("REMOTE_ACK_CONFLICT", "确认跨过了尚未持久覆盖的事件")
        with self.database.locked_connection() as db:
            for row in db.execute("SELECT frame_json FROM remote_outbox WHERE store_id=? AND seq>?", (identity["store"], position["seq"])):
                raw = json.loads(row[0])
                if raw.get("type") == "events.omitted" and raw["firstSeq"] <= position["seq"]:
                    self.freeze("REMOTE_ACK_CONFLICT")
                    raise HubError("REMOTE_ACK_CONFLICT", "确认位置截断了不可变覆盖记录")
        with self.database.transaction() as tx:
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
