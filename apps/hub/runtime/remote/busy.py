"""Computer-owned busy projection. Recovery warnings never become locks."""
import json

from core.errors import HubError
from storage.local_chat import now, uid

ACTIVE = {"queued", "running", "waiting_approval"}


class BusyState:
    def __init__(self, repository, chat):
        self.repo, self.chat = repository, chat
        self.expire = None
        self.reservation_live = None
        self.connection_id = None
        self.last = None

    def enabled(self):
        return self.repo.get("identity").get("wireRevision", 1) >= 2

    def observe(self, record):
        if record["task_id"]:
            method = getattr(type(self.chat.ports.tasks), "activity_observation", None)
            if method is not None:
                try:
                    return self.chat.ports.tasks.activity_observation(record["task_id"])
                except HubError:
                    return {"status": record["status"], "recoveryRequired": True}
            with self.repo.database.locked_connection() as db:
                task = db.execute("SELECT status FROM tasks WHERE task_id=?", (record["task_id"],)).fetchone()
                spec = db.execute("SELECT value_json FROM hub_state WHERE key=?", ("task_spec:" + record["task_id"],)).fetchone()
            return {"status": task[0] if task else record["status"],
                    "recoveryRequired": bool(json.loads(spec[0]).get("recoveryRequired")) if spec else True}
        with self.repo.database.locked_connection() as db:
            gate = db.execute("SELECT state FROM remote2_gates WHERE run_id=?", (record["run_id"],)).fetchone()
        job = self.chat._jobs.get(record["conversation_id"])
        unknown = bool(record["status"] == "running" and (job is None or job.done()))
        # Read paths never need a write transaction to stop displaying an
        # expired reservation as busy. Keep its actual queued status until the
        # independent expiry transaction persists the rejection.
        reservation_live = True
        if gate and gate[0] == "provisional":
            reservation_live = self.reservation_live is not None and self.reservation_live(record["run_id"])
        return {"status": record["status"], "recoveryRequired": unknown or bool(gate and gate[0] == "recovery"),
                "reservationLive": reservation_live}

    def ids(self, tx=None, *, exclude_run=None):
        with self.repo.database.locked_connection() as db:
            records = [dict(r) for r in (tx.connection if tx else db).execute(
                "SELECT * FROM local_runs WHERE status IN ('queued','running','waiting_approval','paused')")]
        return sorted({r["conversation_id"] for r in records if r["run_id"] != exclude_run and (lambda s:
            s["status"] in ACTIVE and not s["recoveryRequired"] and s.get("reservationLive", True))(self.observe(r))})

    def require_idle(self, tx, conversation, *, force=False):
        if not self.enabled() and not force:
            return
        if self.expire is not None:
            self.expire(tx)
        if conversation in self.ids(tx):
            raise HubError("REMOTE_CONVERSATION_BUSY", "电脑或手机上正在进行，结束后再继续")

    def decorate(self, view):
        return view.model_copy(update={"busy": view.id in self.ids(), "busy_observed_at": now()})

    def reconcile(self):
        if not self.enabled():
            return
        with self.repo.database.transaction() as tx:
            rows = tx.connection.execute("SELECT * FROM local_runs WHERE status IN ('queued','running','waiting_approval')").fetchall()
            for row in rows:
                if self.observe(row)["recoveryRequired"]:
                    tx.connection.execute("INSERT INTO remote2_gates VALUES(?,'recovery') ON CONFLICT(run_id) DO UPDATE SET state='recovery'", (row["run_id"],))
                    tx.connection.execute("UPDATE local_runs SET status='paused',error=?,updated_at=? WHERE run_id=?", ("原执行需要本机恢复核对", now(), row["run_id"]))
            self.repo.seal(tx)

    def snapshot(self, *, force=False):
        if not self.enabled() or self.connection_id is None:
            return
        with self.repo.database.transaction() as tx:
            if self.expire is not None:
                self.expire(tx)
            self.record_snapshot(tx, force=force)
            self.repo.seal(tx)

    def record_snapshot(self, tx, *, force=False):
        if not self.enabled() or self.connection_id is None or not self.repo.get("link", tx)["view"].get("workerId"):
            return
        ids = self.ids(tx)
        if self.repo.get("identity", tx).get("wireRevision", 1) < 3:
            ids = [identifier for identifier in ids if str(self.chat.repository.conversation(identifier).conversation_kind) != "native"]
        identity = (self.connection_id, tuple(ids))
        if identity == self.last and not force:
            return
        parts = [ids[i:i + 100] for i in range(0, len(ids), 100)] or [[]]
        snapshot, stamp = uid("busy"), now()
        for index, part in enumerate(parts):
            self.repo.emit(tx, "sync.busy.snapshot", snapshotId=snapshot,
                connectionId=self.connection_id, capturedAt=stamp, partIndex=index,
                partCount=len(parts), conversationIds=part)
        self.repo.seal(tx)
        tx.after_commit(lambda: setattr(self, "last", identity))
