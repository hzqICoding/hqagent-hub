"""Revision-3 resource command admission and idempotent, model-free commits."""
import asyncio
import json
import logging
from core.diagnostics import emit
import time

from protocol.generated.python import RemoteNativeImportInput, AddWorkspaceInput
from core.errors import HubError
from runtime.remote.commands import error_view
from runtime.remote.deadline import instant
from runtime.remote.wire import canonical
from storage.idempotency import request_hash
from storage.local_chat import now


class ResourceCommands:
    def __init__(self, worker):
        self.worker = worker
        self.repo, self.native, self.roots = worker.repo, worker.native, worker.roots
        self.jobs = {}

    def row(self, command_id):
        with self.repo.database.locked_connection() as db:
            row = db.execute("SELECT * FROM native_commands WHERE worker_id=? AND store_id=? AND command_id=?",
                (*self.worker.delivery.scope(), command_id)).fetchone()
        return dict(row) if row else None

    def event(self, tx, frame, kind, **fields):
        return self.repo.emit(tx, kind, commandId=frame["commandId"], **fields)

    def reject(self, tx, frame, code):
        if frame["type"] == "workspace.register":
            self.roots.audit(frame["requestId"],frame["payload"]["rootId"],code,operation="workspace.register",transaction=tx)
        event = self.event(tx, frame, "command.rejected", status="rejected", receivedAt=now(), error=error_view(code))
        tx.connection.execute("UPDATE native_commands SET state='rejected',result_json=? WHERE worker_id=? AND store_id=? AND command_id=?",
            (canonical(event), *self.worker.delivery.scope(), frame["commandId"]))
        return event

    def conflict(self, frame):
        with self.repo.database.transaction() as tx:
            key = "resource-conflict:" + request_hash(frame)
            event = self.repo.get(key,tx)
            if event is None:
                event = self.event(tx,frame,"command.rejected",status="rejected",receivedAt=now(),error=error_view("IDEMPOTENCY_MISMATCH"))
                self.repo.put(key,event,tx)
                self.repo.seal(tx)
            return event,[]

    async def validate(self, frame):
        self.worker.delivery._check_connection(frame)
        if not self.worker.sync.settings().mirror_enabled:
            raise HubError("REMOTE_SYNC_DISABLED", "远程同步已关闭")
        stage, started = 'clock_before', time.monotonic()
        try:
            self.check_clock(frame)
            payload = frame["payload"]
            if frame["type"] == "native.import":
                stage = 'registered_workspace'
                row = self.native.row(payload["nativeSessionId"])
                await self.native.registered(row)
                stage = 'ready_source'
                try:
                    source = await self.native.io(self.native.ready_source, row)
                except HubError as error:
                    if error.code in {'REMOTE_STATE_NOT_READY', 'NATIVE_SESSION_CHANGED'}:
                        self.native.request_scan()
                    raise
                stage = 'source_binding'
                if payload["expectedIndexVersion"] != json.loads(row["index_json"])["indexVersion"] or payload["sourceRevision"] != source.revision:
                    raise HubError("NATIVE_SESSION_CHANGED", "原生索引已变化")
                if payload["confirmation"]["requestId"] != frame["requestId"]:
                    raise HubError("REMOTE_TARGET_MISMATCH", "确认请求身份不匹配")
                stage = 'activity_confirmation'
                await self.native.io(self.native.check, row, source, payload["confirmation"])
            else:
                stage = 'directory_selection'
                def check_directory():
                    with self.roots.selected(payload["rootId"], payload["rootVersion"], payload["directoryToken"]):
                        pass
                await self.native.io(check_directory)
            stage = 'clock_after'
            self.check_clock(frame)
        except HubError as error:
            # Fixed stage/code and duration only; no frame, paths, exception
            # message, token, source text or arbitrary request ID in logs.
            logging.getLogger(__name__).info(
                "resource admission rejected stage=%s elapsed_ms=%.1f code=%s",
                stage, (time.monotonic()-started)*1000, error.code)
            emit('remote.admission', stage=stage, elapsedMs=(time.monotonic()-started)*1000, errorCode=error.code)
            raise

    def check_clock(self, frame):
        # A missing bound says nothing about actual expiry. It still forbids
        # admission; never extend deliverBy or treat continuous ACK as a grant.
        clock = self.worker.delivery.clock
        if clock.anchor is None:
            raise HubError('REMOTE_STATE_NOT_READY', '送达时钟尚未校准，请稍后重试')
        try:
            clock.check(frame)
        except HubError as error:
            if error.code == 'REMOTE_DELIVERY_EXPIRED' and clock.anchor is None:
                raise HubError('REMOTE_STATE_NOT_READY', '送达时钟界限失效，请重新校准') from None
            raise

    async def receive(self, frame):
        self.worker.delivery._check_connection(frame)
        async with self.worker.delivery.lock:
            if frame["type"] == "command.delivery_granted":
                return await self.grant(frame)
            old = self.row(frame["commandId"])
            if old:
                if old["digest"] == request_hash(frame):
                    return json.loads(old["result_json"] or old["receipt_json"]), []
                return self.conflict(frame)
            code = None
            try:
                if self.repo.inbox(frame["commandId"]):
                    raise HubError("IDEMPOTENCY_MISMATCH", "命令标识已用于另一种操作")
                await self.validate(frame)
            except HubError as error:
                code = error.code
            with self.repo.database.transaction() as tx:
                event = self.event(tx, frame, "command.received", commandDigest=request_hash(frame),
                    deliverBy=frame["deliverBy"], receivedAt=now()) if code is None else None
                tx.connection.execute("INSERT INTO native_commands VALUES(?,?,?,?,?,'provisional',?,NULL,NULL)",
                    (*self.worker.delivery.scope(), frame["commandId"], request_hash(frame), canonical(frame), canonical(event or {})))
                if code:
                    event = self.reject(tx, frame, code)
                self.repo.seal(tx)
                return event, []

    async def grant(self, grant):
        row = self.row(grant["commandId"])
        if row is None:
            with self.repo.database.transaction() as tx:
                key = "resource-unknown-grant:" + request_hash(grant)
                result = self.repo.get(key,tx)
                if result is None:
                    result = self.event(tx,grant,"command.rejected",status="rejected",receivedAt=now(),error=error_view("REMOTE_TARGET_MISMATCH"))
                    self.repo.put(key,result,tx)
                    self.repo.seal(tx)
                return result,[]
        if row["state"] != "provisional":
            if row["grant_json"] and json.loads(row["grant_json"]) != grant:
                return self.conflict(grant)
            return json.loads(row["result_json"] or row["receipt_json"]), []
        frame = json.loads(row["frame_json"])
        code = None
        try:
            await self.validate(frame)
            received = json.loads(row["receipt_json"])
            if ("conversationId" in grant or grant["commandDigest"] != row["digest"] or
                    grant["receivedEventId"] != received["eventId"] or grant["deliverBy"] != frame["deliverBy"]):
                raise HubError("REMOTE_TARGET_MISMATCH", "资源许可与收件不匹配")
            if not instant(frame["createdAt"]) <= instant(grant["grantedAt"]) < instant(frame["deliverBy"]):
                raise HubError("REMOTE_DELIVERY_EXPIRED", "资源许可已过期")
        except HubError as error:
            code = error.code
        with self.repo.database.transaction() as tx:
            if code:
                result = self.reject(tx, frame, code)
            else:
                result = self.event(tx, frame, "command.accepted", status="accepted", receivedAt=now())
                tx.connection.execute("UPDATE native_commands SET state='admitted',grant_json=?,receipt_json=? WHERE worker_id=? AND store_id=? AND command_id=?",
                    (canonical(grant), canonical(result), *self.worker.delivery.scope(), frame["commandId"]))
                tx.after_commit(lambda: self.schedule(frame))
            self.repo.seal(tx)
        return result, []

    def schedule(self, frame):
        if frame["commandId"] not in self.jobs:
            task = asyncio.create_task(self.execute(frame))
            self.jobs[frame["commandId"]] = task
            def finished(done):
                self.jobs.pop(frame["commandId"], None)
                if not done.cancelled():
                    done.exception()
            task.add_done_callback(finished)

    def finish(self, tx, frame, ref):
        if not self.worker.delivery._same_binding(frame):
            return
        result = self.event(tx,frame,"command.completed",resultStatus="confirmed",resourceRef=ref,
            controlResult={"outcome":"confirmed","evidence":"metadata_committed","executionMayStillBeRunning":False,
                "orphanProcessIds":[],"reason":"本机资源已提交","observedAt":now()})
        tx.connection.execute("UPDATE native_commands SET state='completed',result_json=? WHERE worker_id=? AND store_id=? AND command_id=?",
            (canonical(result),frame["targetWorkerId"],frame["expectedWorkerStoreId"],frame["commandId"]))
        self.repo.seal(tx)

    async def execute(self, frame):
        try:
            if not self.worker.delivery._same_binding(frame):
                return
            payload = frame["payload"]
            if frame["type"] == "native.import":
                view = await self.native.import_session(payload["nativeSessionId"], RemoteNativeImportInput(
                    terminalClosedConfirmed=True, expectedIndexVersion=payload["expectedIndexVersion"], sourceRevision=payload["sourceRevision"]),
                    "remote:" + frame["commandId"], frame["requestId"], confirmation=payload["confirmation"],command_id=frame["commandId"],
                    remote_scope=(frame["targetWorkerId"],frame["expectedWorkerStoreId"]),on_commit=lambda tx,ref:self.finish(tx,frame,ref))
                ref = {"conversationId":view.id,"workspaceId":view.workspace_id,"nativeSessionId":view.native_session_id}
            else:
                with self.roots.selected(payload["rootId"],payload["rootVersion"],payload["directoryToken"]) as (path, identity):
                    service = self.worker.bridge.chat.ports.workspaces
                    def commit(record):
                        with self.repo.database.transaction() as tx:
                            with self.roots.selected(payload["rootId"],payload["rootVersion"],payload["directoryToken"]):
                                service.repository.save(record, transaction=tx)
                                self.roots.audit(frame["requestId"],payload["rootId"],"OK",operation="workspace.register",transaction=tx)
                                self.repo.put("authorized-roots-catalog-pending", {"requestId":frame["requestId"]}, tx)
                                self.finish(tx,frame,{"workspaceId":record.id})
                                self.repo.seal(tx)
                        return record
                    view = await service.add_workspace(AddWorkspaceInput(path=str(path),name=payload.get("name")),commit=commit)
                    ref = {"workspaceId":view.id}
            if not self.worker.delivery._same_binding(frame):
                return
            if self.row(frame["commandId"])["state"] == "completed":
                return
            with self.repo.database.transaction() as tx:
                self.finish(tx,frame,ref)
        except Exception as error:
            if not self.worker.delivery._same_binding(frame):
                return
            if self.row(frame["commandId"])["state"] == "completed":
                return  # Post-commit view refresh cannot undo committed metadata.
            with self.repo.database.transaction() as tx:
                if frame["type"] == "workspace.register":
                    self.roots.audit(frame["requestId"],frame["payload"]["rootId"],
                        error.code if isinstance(error,HubError) else "INTERNAL",operation="workspace.register",transaction=tx)
                result = self.event(tx, frame, "command.failed",resultStatus="rejected",error=error_view(error.code if isinstance(error,HubError) else "INTERNAL"))
                tx.connection.execute("UPDATE native_commands SET state='failed',result_json=? WHERE worker_id=? AND store_id=? AND command_id=?",
                    (canonical(result),frame["targetWorkerId"],frame["expectedWorkerStoreId"],frame["commandId"]))
                self.repo.seal(tx)

    async def recover(self, *, restart=False):
        eligible = await self.repo.database.read_async(lambda:
            self.repo.get('identity').get('wireRevision', 1) >= 3 and bool(self.repo.get('link')['view'].get('workerId')))
        if not eligible:
            return
        if self.repo.get("identity").get("wireRevision", 1) < 3 or not self.repo.get("link")["view"].get("workerId"):
            return
        with self.repo.database.transaction() as tx:
            rows = list(tx.connection.execute("SELECT * FROM native_commands WHERE worker_id=? AND store_id=? AND state IN ('provisional','admitted')", self.worker.delivery.scope()))
            for row in rows:
                frame = json.loads(row["frame_json"])
                if row["state"] == "provisional":
                    try:
                        if restart:
                            raise HubError("REMOTE_DELIVERY_EXPIRED", "重启收件无许可")
                        self.worker.delivery.clock.check(frame)
                    except HubError:
                        self.reject(tx, frame, "REMOTE_DELIVERY_EXPIRED")
                elif not restart:
                    tx.after_commit(lambda f=frame:self.schedule(f))
            self.repo.seal(tx)
