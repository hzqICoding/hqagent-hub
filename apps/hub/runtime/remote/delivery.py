"""Revision 2: receive -> provisional -> explicit grant -> admitted execution."""
from __future__ import annotations

import json

from protocol.generated.python import (ApprovalView, LocalConversationView,
    RemoteV2ServerOutboundFrame, SendLocalMessageInput, UpdateLocalConversationInput)
from core.errors import HubError
from storage.idempotency import request_hash
from storage.local_chat import now
from runtime.remote.commands import CommandBridge, control_result, error_view
from runtime.remote.deadline import DeliveryClock, instant
from runtime.remote.wire import canonical


class DeliveryBridge(CommandBridge):
    def __init__(self, repository, chat, link, busy, sync):
        super().__init__(repository, chat, link)
        self.busy, self.sync = busy, sync
        self.clock = DeliveryClock()
        self.busy.expire = self.expire
        self.sync.delivery = self

    def scope(self):
        return self.repo.get("link")["view"]["workerId"], self.repo.get("identity")["store"]

    def row(self, command_id, tx=None):
        with self.repo.database.locked_connection() as db:
            row = (tx.connection if tx else db).execute("SELECT * FROM remote2_delivery WHERE worker_id=? AND store_id=? AND command_id=?",
                                                       (*self.scope(), command_id)).fetchone()
        return dict(row) if row else None

    def execution_frame(self, command_id):
        row = self.row(command_id)
        return json.loads(row["execution_json"]) if row and row["execution_json"] else None

    def _check_connection(self, frame):
        if self.repo.get("identity").get("wireRevision") != 2:
            raise HubError("REMOTE_PROTOCOL_UNSUPPORTED", "连接尚未切换到修订2")
        if not self.repo.check_continuity() or self.repo.get("link")["view"]["state"] != "paired":
            raise HubError("REMOTE_STORE_CHANGED", "当前世代需要核对")
        worker, store = self.scope()
        if frame["targetWorkerId"] != worker or frame["expectedWorkerStoreId"] != store:
            raise HubError("REMOTE_STORE_CHANGED", "命令绑定不匹配")
        if self.link.contains_credentials(canonical(frame)):
            raise HubError("REMOTE_DEVICE_AUTH_FAILED", "远程命令含不允许传播的凭据")

    def _route(self, tx, frame):
        worker, store = self.scope()
        public, local = frame["conversationId"], frame["localConversationId"]
        a = tx.connection.execute("SELECT local_id FROM remote2_routes WHERE worker_id=? AND store_id=? AND public_id=?", (worker, store, public)).fetchone()
        b = tx.connection.execute("SELECT public_id FROM remote2_routes WHERE worker_id=? AND store_id=? AND local_id=?", (worker, store, local)).fetchone()
        if (a and a[0] != local) or (b and b[0] != public):
            raise HubError("REMOTE_TARGET_MISMATCH", "对话映射不匹配")
        tx.connection.execute("INSERT OR IGNORE INTO remote2_routes VALUES(?,?,?,?)", (worker, store, public, local))

    def _validate(self, tx, frame, workspaces):
        if not self.sync.settings().mirror_enabled:
            raise HubError("REMOTE_SYNC_DISABLED", "电脑已关闭同步")
        self.clock.check(frame)
        payload, kind = frame["payload"], frame["type"]
        local = frame["localConversationId"]
        if kind == "conversation.create":
            if not payload["title"].strip():
                raise HubError("VALIDATION_FAILED", "标题不能为空")
            if payload["targetWorkerId"] != frame["targetWorkerId"] or payload["workerStoreId"] != frame["expectedWorkerStoreId"]:
                raise HubError("REMOTE_TARGET_MISMATCH", "创建目标不匹配")
            if tx.connection.execute("SELECT 1 FROM local_conversations WHERE conversation_id=?", (local,)).fetchone() or tx.connection.execute("SELECT 1 FROM remote_sync_deletions WHERE conversation_id=?", (local,)).fetchone():
                raise HubError("CONFLICT", "本机对话标识已使用")
        else:
            conversation = self.chat.repository.conversation(local)
            if kind == "run.submit" and (conversation.workspace_id != payload["workspaceId"] or str(conversation.scene_id) != payload["sceneId"]):
                raise HubError("REMOTE_TARGET_MISMATCH", "对话执行目标不匹配")
            if kind == "conversation.update":
                if payload["conversationId"] != local:
                    raise HubError("REMOTE_TARGET_MISMATCH", "元数据目标不匹配")
                fields = set(payload) & {"title", "archived", "visibility"}
                if not fields:
                    raise HubError("VALIDATION_FAILED", "至少提供一项元数据修改")
                if conversation.version != payload["expectedVersion"]:
                    raise HubError("CONFLICT", "对话版本已变化")
            elif kind not in {"run.submit", "command.withdraw"}:
                record = self._bound_run(frame)
                if kind == "approval.decide":
                    raw = tx.connection.execute("SELECT payload_json FROM approvals WHERE approval_id=?", (payload["approvalId"],)).fetchone()
                    if raw is None:
                        raise HubError("NOT_FOUND", "审批不存在")
                    approval = ApprovalView.model_validate_json(raw[0])
                    if approval.task_id != record["task_id"] or str(approval.status) != "pending":
                        raise HubError("APPROVAL_EXPIRED", "审批已失效")
                    if self.clock.upper() >= instant(approval.expires_at) or instant(frame["expiresAt"]) > instant(approval.expires_at):
                        raise HubError("APPROVAL_EXPIRED", "审批决定超过当前本机请求期限")
                    if payload["decision"] == "approve" and str(approval.action) in self.policy()[1]:
                        raise HubError("REMOTE_APPROVAL_FORBIDDEN", "该动作必须在电脑审批")
        if kind in {"run.submit", "conversation.create"}:
            if payload["workspaceId"] not in workspaces:
                raise HubError("NOT_FOUND", "工作区未登记")
            if self.chat.repository.scene(payload["sceneId"]).version != payload["sceneVersion"]:
                raise HubError("REMOTE_SCENE_VERSION_MISMATCH", "场景版本已变化")

    def _insert(self, tx, frame):
        worker, store = self.scope()
        digest = request_hash(frame)
        # Execution metadata is explicitly separate from original immutable body.
        # Reset can erase the body without losing already-admitted control facts.
        executable = {k: v for k, v in frame.items() if k != "payload"}
        executable["payload"] = {k: v for k, v in frame["payload"].items()
            if k in {"runId", "nodeId", "approvalId", "decision", "targetCommandId", "targetConversationSeq"}}
        tx.connection.execute("INSERT INTO remote2_delivery(worker_id,store_id,command_id,digest,command_json,kind,public_id,local_id,conversation_seq,state,deliver_by,execution_json) VALUES(?,?,?,?,?,?,?,?,?,'waiting',?,?)",
            (worker, store, frame["commandId"], digest, canonical(frame), frame["type"], frame["conversationId"],
             frame["localConversationId"], frame.get("conversationSeq"), frame["deliverBy"], canonical(executable)))
        tx.connection.execute("INSERT INTO remote_inbox(worker_id,command_id,digest,command_json,status) VALUES(?,?,?,?,?)",
            (worker, frame["commandId"], digest, canonical(frame), "provisional"))

    def _slot(self, tx, frame):
        if frame["type"] != "run.submit":
            return
        row = tx.connection.execute("SELECT command_id FROM remote2_order WHERE worker_id=? AND store_id=? AND public_id=? AND sequence=?",
            (*self.scope(), frame["conversationId"], frame["conversationSeq"])).fetchone()
        if row and row[0] != frame["commandId"]:
            raise HubError("REMOTE_EVENT_CONFLICT", "远程序号已使用")
        tx.connection.execute("INSERT OR IGNORE INTO remote2_order VALUES(?,?,?,?,?,0)",
            (*self.scope(), frame["conversationId"], frame["conversationSeq"], frame["commandId"]))

    def _ordered(self, tx, frame):
        if frame["type"] != "run.submit":
            return True
        preceding = tx.connection.execute("SELECT COUNT(*),COALESCE(SUM(consumed),0) FROM remote2_order WHERE worker_id=? AND store_id=? AND public_id=? AND sequence<?",
            (*self.scope(), frame["conversationId"], frame["conversationSeq"])).fetchone()
        return preceding[0] == preceding[1] == frame["conversationSeq"] - 1

    def _consume_slot(self, tx, command_id):
        tx.connection.execute("UPDATE remote2_order SET consumed=1 WHERE worker_id=? AND store_id=? AND command_id=?", (*self.scope(), command_id))

    def _tombstone_key(self, command_id):
        return "r15-tombstone:" + request_hash([*self.scope(), command_id])

    def _prepare(self, tx, frame, workspaces):
        self._validate(tx, frame, workspaces)
        self._route(tx, frame)
        run_id = None
        if frame["type"] == "run.submit":
            self.busy.require_idle(tx, frame["localConversationId"])
            self.clock.check(frame)
            message = SendLocalMessageInput.model_validate({k: frame["payload"][k] for k in ("clientMessageId", "text", "sessionMode")})
            receipt = self.chat.repository.enqueue(frame["localConversationId"], message, "r15:" + frame["commandId"], transaction=tx, legacy=True)
            if receipt.duplicate:
                raise HubError("IDEMPOTENCY_MISMATCH", "消息已由其它命令提交")
            run_id = receipt.run_id
            tx.connection.execute("INSERT INTO remote2_gates VALUES(?,'provisional')", (run_id,))
            self.busy.record_snapshot(tx)
        event = self.repo.emit(tx, "command.received", commandId=frame["commandId"], conversationId=frame["conversationId"],
            commandDigest=request_hash(frame), deliverBy=frame["deliverBy"], receivedAt=now())
        tx.connection.execute("UPDATE remote2_delivery SET state='provisional',run_id=?,received_json=? WHERE worker_id=? AND store_id=? AND command_id=?",
            (run_id, canonical(event), *self.scope(), frame["commandId"]))
        self.repo.patch_inbox(tx, frame["commandId"], run_id=run_id, receipt_json=canonical(event))
        return event

    def _rejected(self, tx, frame, code):
        row = self.row(frame["commandId"], tx)
        if row and row["run_id"]:
            tx.connection.execute("UPDATE remote2_gates SET state='rejected' WHERE run_id=?", (row["run_id"],))
            tx.connection.execute("UPDATE local_runs SET status='cancelled',error=?,updated_at=? WHERE run_id=? AND task_id IS NULL", ("远程送达未取得执行许可", now(), row["run_id"]))
        event = self.repo.emit(tx, "command.rejected", commandId=frame["commandId"], conversationId=frame["conversationId"],
            receivedAt=now(), status="rejected", error=error_view(code))
        tx.connection.execute("UPDATE remote2_delivery SET state='rejected',result_json=?,command_json=NULL WHERE worker_id=? AND store_id=? AND command_id=?",
            (canonical(event), *self.scope(), frame["commandId"]))
        self.repo.patch_inbox(tx, frame["commandId"], status="rejected", receipt_json=canonical(event))
        self._consume_slot(tx, frame["commandId"])
        return event

    def expire(self, tx, *, recovery=False):
        if not self.busy.enabled() or not self.repo.get("link", tx)["view"].get("workerId"):
            return
        rows = [dict(r) for r in tx.connection.execute("SELECT * FROM remote2_delivery WHERE worker_id=? AND store_id=? AND state IN ('waiting','provisional')", self.scope())]
        for row in rows:
            frame = json.loads(row["command_json"])
            code = None
            if recovery:
                code = "REMOTE_DELIVERY_EXPIRED"
            elif row["run_id"]:
                run = tx.connection.execute("SELECT status FROM local_runs WHERE run_id=?", (row["run_id"],)).fetchone()
                if not run or run[0] != "queued":
                    code = "REMOTE_COMMAND_WITHDRAWN"
            if code is None:
                try:
                    self.clock.check(frame)
                except HubError:
                    code = "REMOTE_DELIVERY_EXPIRED"
            if code:
                self._rejected(tx, frame, code)

    def release_pending(self, tx, code):
        rows = tx.connection.execute("SELECT command_json FROM remote2_delivery WHERE worker_id=? AND store_id=? AND state IN ('waiting','provisional')", self.scope()).fetchall()
        for row in rows:
            self._rejected(tx, json.loads(row[0]), code)

    async def receive(self, raw):
        frame = RemoteV2ServerOutboundFrame.model_validate(raw).model_dump(mode="json", by_alias=True, exclude_none=True)
        self._check_connection(frame)
        workspaces = {w.id for w in await self.chat.ports.workspaces.list_workspaces(None, None)}
        async with self.lock:
            self._check_connection(frame)
            if frame["type"] == "command.delivery_granted":
                return self._grant(frame, workspaces), []
            if frame["type"] == "conversation.skip":
                return self._skip(frame), []
            with self.repo.database.transaction() as tx:
                self.expire(tx)
                old = self.row(frame["commandId"], tx)
                if old:
                    if old["digest"] != request_hash(frame):
                        return self._conflict(tx, frame), []
                    cached = old["result_json"] or old["received_json"]
                    self.repo.seal(tx)
                    return json.loads(cached) if cached else None, self._gaps(tx, frame)
                tombstone = self.repo.get(self._tombstone_key(frame["commandId"]), tx)
                if tombstone:
                    matches = frame["type"] == "run.submit" and frame["conversationId"] == tombstone["frame"]["conversationId"] and frame["conversationSeq"] == tombstone["frame"]["conversationSeq"]
                    return self._conflict(tx, frame, "REMOTE_COMMAND_WITHDRAWN" if matches else "REMOTE_TARGET_MISMATCH"), []
                existing = self.repo.inbox(frame["commandId"], tx)
                if existing:
                    return self._conflict(tx, frame), []
                self._insert(tx, frame)
                try:
                    self._slot(tx, frame)
                    self._validate(tx, frame, workspaces)
                except HubError as error:
                    event = self._rejected(tx, frame, error.code)
                else:
                    event = None
                    if self._ordered(tx, frame):
                        tx.connection.execute("SAVEPOINT provisional")
                        try:
                            event = self._prepare(tx, frame, workspaces)
                        except HubError as error:
                            tx.connection.execute("ROLLBACK TO provisional")
                            event = self._rejected(tx, frame, error.code)
                        finally:
                            tx.connection.execute("RELEASE provisional")
                self.repo.seal(tx)
                return event, self._gaps(tx, frame)

    def _conflict(self, tx, frame, code="IDEMPOTENCY_MISMATCH"):
        key = self._scope_key("r15-rejection:", frame)
        event = self.repo.get(key, tx)
        if event is None:
            event = self.repo.emit(tx, "command.rejected", commandId=frame["commandId"], conversationId=frame["conversationId"],
                receivedAt=now(), status="rejected", error=error_view(code))
            self.repo.put(key, event, tx)
            self.repo.seal(tx)
        return event

    def _gaps(self, tx, frame):
        if frame["type"] != "run.submit" or self._ordered(tx, frame):
            return []
        rows = tx.connection.execute("SELECT sequence,consumed FROM remote2_order WHERE worker_id=? AND store_id=? AND public_id=? ORDER BY sequence",
            (*self.scope(), frame["conversationId"])).fetchall()
        expected = 1
        for row in rows:
            if row[0] != expected or not row[1]:
                break
            expected += 1
        return [{"type": "conversation.gap", "wireRevision": 2, "workerId": self.scope()[0], "workerStoreId": self.scope()[1],
            "workerEpoch": self.repo.get("identity", tx)["epoch"], "conversationId": frame["conversationId"],
            "expectedSeq": expected, "receivedSeq": frame["conversationSeq"]}]

    def _grant(self, grant, workspaces):
        with self.repo.database.transaction() as tx:
            row = self.row(grant["commandId"], tx)
            if row is None:
                # Without a durable receipt a grant can never create execution.
                return self._conflict(tx, grant)
            if row["state"] not in {"waiting", "provisional"}:
                if row["grant_json"] and json.loads(row["grant_json"]) != grant:
                    return self._conflict(tx, grant)
                return json.loads(row["result_json"] or row["received_json"])
            frame = json.loads(row["command_json"])
            tx.connection.execute("SAVEPOINT grant_validation")
            try:
                self._validate(tx, frame, workspaces)
                receipt = json.loads(row["received_json"] or "{}")
                if row["state"] != "provisional" or grant["conversationId"] != row["public_id"] or grant["commandDigest"] != row["digest"] or grant["receivedEventId"] != receipt.get("eventId") or grant["deliverBy"] != row["deliver_by"]:
                    raise HubError("REMOTE_TARGET_MISMATCH", "执行许可与持久收件不匹配")
                if not instant(frame["createdAt"]) <= instant(grant["grantedAt"]) < instant(grant["deliverBy"]):
                    raise HubError("REMOTE_DELIVERY_EXPIRED", "执行许可期限无效")
                if row["run_id"] and frame["type"] == "run.submit":
                    record = self.chat.repository.run_record(row["run_id"])
                    if record["status"] != "queued" or record["task_id"]:
                        raise HubError("REMOTE_COMMAND_WITHDRAWN", "预留已被本机取消")
                    if frame["localConversationId"] in self.busy.ids(tx, exclude_run=row["run_id"]):
                        raise HubError("REMOTE_CONVERSATION_BUSY", "已有其它轮次执行，预留不再可用")
                self._route(tx, frame)
                if frame["type"] in {"conversation.create", "conversation.update"}:
                    self._metadata_commit(tx, frame)
                elif frame["type"] == "command.withdraw":
                    target = self.row(frame["payload"]["targetCommandId"], tx)
                    if target is None or target["public_id"] != row["public_id"] or target["conversation_seq"] != frame["payload"]["targetConversationSeq"]:
                        raise HubError("REMOTE_TARGET_MISMATCH", "撤回目标不匹配")
                    if target["state"] in {"waiting", "provisional"}:
                        self._rejected(tx, json.loads(target["command_json"]), "REMOTE_COMMAND_WITHDRAWN")
                    else:
                        raise HubError("REMOTE_WITHDRAWAL_TOO_LATE", "已接单轮次请使用run.cancel")
            except HubError as error:
                tx.connection.execute("ROLLBACK TO grant_validation")
                result = self._rejected(tx, frame, error.code)
                self.repo.seal(tx)
                return result
            finally:
                tx.connection.execute("RELEASE grant_validation")
            run_id = row["run_id"]
            if frame["type"] not in {"run.submit", "conversation.create", "conversation.update", "command.withdraw"}:
                run_id = self._bound_run(frame)["run_id"]
            fields = {"commandId": frame["commandId"], "conversationId": frame["conversationId"], "status": "accepted", "receivedAt": now()}
            if run_id:
                fields["resultRef"] = {"runId": run_id}
            accepted = self.repo.emit(tx, "command.accepted", **fields)
            if frame["type"] == "run.submit":
                tx.connection.execute("UPDATE remote2_gates SET state='granted' WHERE run_id=?", (run_id,))
            state = "accepted" if frame["type"] == "run.submit" else "admitted"
            self.repo.patch_inbox(tx, frame["commandId"], status=state, run_id=run_id, receipt_json=canonical(accepted))
            tx.connection.execute("UPDATE remote2_delivery SET state='accepted',grant_json=?,result_json=?,run_id=? WHERE worker_id=? AND store_id=? AND command_id=?",
                (canonical(grant), canonical(accepted), run_id, *self.scope(), frame["commandId"]))
            self._consume_slot(tx, frame["commandId"])
            if frame["type"] in {"conversation.create", "conversation.update", "command.withdraw"}:
                if frame["type"] != "command.withdraw":
                    self.sync.upsert(tx, frame["localConversationId"])
                result = {"outcome": "confirmed", "executionMayStillBeRunning": False, "orphanProcessIds": [],
                    "evidence": "inbox_tombstone" if frame["type"] == "command.withdraw" else "metadata_committed",
                    "reason": "电脑已持久提交", "observedAt": now()}
                event = self.repo.emit(tx, "command.completed", commandId=frame["commandId"], conversationId=frame["conversationId"],
                    resultStatus="withdrawn" if frame["type"] == "command.withdraw" else "confirmed", controlResult=result)
                self._cache(tx, frame, event, "completed")
            elif frame["type"] != "run.submit":
                tx.after_commit(lambda: self._schedule(frame, run_id))
            tx.after_commit(self.chat.wake_remote_queue)
            self.repo.seal(tx)
            return accepted

    def _metadata_commit(self, tx, frame):
        payload, local = frame["payload"], frame["localConversationId"]
        if frame["type"] == "conversation.create":
            value = LocalConversationView.model_validate({"id": local, "workspaceId": payload["workspaceId"], "sceneId": payload["sceneId"],
                "title": payload["title"].strip(), "createdAt": now(), "updatedAt": now(), "authority": "remote",
                "visibility": "both", "archived": False, "version": 1})
            tx.connection.execute("INSERT INTO local_conversations VALUES(?,?,?)", (local, value.model_dump_json(by_alias=True, exclude_none=True), value.updated_at))
        else:
            value = UpdateLocalConversationInput.model_validate({k: v for k, v in payload.items() if k != "conversationId"})
            self.chat.repository.update_conversation(local, value, "r15:" + frame["commandId"], transaction=tx)

    def _skip(self, frame):
        with self.repo.database.transaction() as tx:
            key = self._tombstone_key(frame["commandId"])
            tombstone = self.repo.get(key, tx)
            if tombstone is not None:
                return tombstone["event"] if tombstone["frame"] == frame else self._conflict(tx, frame)
            old = self.row(frame["commandId"], tx)
            if old is not None:
                return self._conflict(tx, frame, "REMOTE_WITHDRAWAL_TOO_LATE")
            slot = tx.connection.execute("SELECT command_id FROM remote2_order WHERE worker_id=? AND store_id=? AND public_id=? AND sequence=?",
                (*self.scope(), frame["conversationId"], frame["conversationSeq"])).fetchone()
            if slot and slot[0] != frame["commandId"]:
                return self._conflict(tx, frame, "REMOTE_EVENT_CONFLICT")
            tx.connection.execute("INSERT OR IGNORE INTO remote2_order VALUES(?,?,?,?,?,1)",
                (*self.scope(), frame["conversationId"], frame["conversationSeq"], frame["commandId"]))
            event = self.repo.emit(tx, "conversation.skip_recorded", commandId=frame["commandId"],
                conversationId=frame["conversationId"], conversationSeq=frame["conversationSeq"])
            self.repo.put(key, {"frame": frame, "event": event}, tx)
            self.repo.seal(tx)
            return event

    def _bound_run(self, frame):
        record = self.chat.repository.run_record(frame["payload"]["runId"])
        if record["conversation_id"] != frame["localConversationId"]:
            raise HubError("REMOTE_TARGET_MISMATCH", "执行不属于目标本机对话")
        if frame["payload"].get("nodeId") and frame["type"] != "run.retry":
            raise HubError("REMOTE_TARGET_MISMATCH", "只有重试可指定节点")
        return record

    @staticmethod
    def result_ref(record):
        return {"runId": record["run_id"], **({"executionTaskId": record["task_id"]} if record["task_id"] else {})}

    def _cache(self, tx, frame, event, state):
        self.repo.patch_inbox(tx, frame["commandId"], status=state)
        tx.connection.execute("UPDATE remote2_delivery SET state=?,result_json=? WHERE worker_id=? AND store_id=? AND command_id=?",
            (state, canonical(event), *self.scope(), frame["commandId"]))

    def _completed(self, frame, ref, status):
        if not self._same_binding(frame):
            return
        with self.repo.database.transaction() as tx:
            extra = {"controlResult": control_result({}, {"controlEvidence": {"kind": "retry_enqueued"}})} if status == "retry_enqueued" else {}
            event = self.repo.emit(tx, "command.completed", commandId=frame["commandId"], conversationId=frame["conversationId"], resultStatus=status, resultRef=ref, **extra)
            self._cache(tx, frame, event, "completed")
            self.repo.patch_inbox(tx, frame["commandId"], run_id=ref["runId"])
            self.repo.seal(tx)

    def _failed(self, frame, ref, code):
        if not self._same_binding(frame):
            return
        with self.repo.database.transaction() as tx:
            event = self.repo.emit(tx, "command.failed", commandId=frame["commandId"], conversationId=frame["conversationId"], resultStatus="rejected", resultRef=ref, error=error_view(code))
            self._cache(tx, frame, event, "failed")
            self.repo.seal(tx)

    def _finish(self, frame, ref, result, status):
        if not self._same_binding(frame):
            return
        with self.repo.database.transaction() as tx:
            common = {"commandId": frame["commandId"], "conversationId": frame["conversationId"], "resultRef": ref, "controlResult": result}
            event = self.repo.emit(tx, "command.control_result", **common, executionStatus=status)
            outcome = result["outcome"]
            if outcome == "confirmed":
                event = self.repo.emit(tx, "command.completed", **common, resultStatus="confirmed")
            elif outcome == "rejected":
                event = self.repo.emit(tx, "command.failed", **common, resultStatus="rejected", error=error_view("TASK_NOT_CANCELLABLE"))
            self._cache(tx, frame, event, {"confirmed": "completed", "rejected": "failed", "unconfirmed": "unconfirmed"}[outcome])
            self.repo.seal(tx)

    async def tick(self):
        workspaces = {w.id for w in await self.chat.ports.workspaces.list_workspaces(None, None)}
        async with self.lock:
            with self.repo.database.transaction() as tx:
                self.expire(tx)
                rows = tx.connection.execute("SELECT command_json FROM remote2_delivery WHERE worker_id=? AND store_id=? AND state='waiting' ORDER BY rowid", self.scope()).fetchall()
                for row in rows:
                    frame = json.loads(row[0])
                    if self._ordered(tx, frame):
                        tx.connection.execute("SAVEPOINT prepare_waiting")
                        try:
                            self._prepare(tx, frame, workspaces)
                        except HubError as error:
                            tx.connection.execute("ROLLBACK TO prepare_waiting")
                            self._rejected(tx, frame, error.code)
                        finally:
                            tx.connection.execute("RELEASE prepare_waiting")
                self.repo.seal(tx)

    async def recover(self):
        async with self.lock:
            with self.repo.database.transaction() as tx:
                self.expire(tx, recovery=True)
                self.repo.seal(tx)
            with self.repo.database.locked_connection() as db:
                rows = [dict(r) for r in db.execute("SELECT i.status,i.run_id,d.execution_json FROM remote_inbox i JOIN remote2_delivery d "
                    "ON i.worker_id=d.worker_id AND i.command_id=d.command_id WHERE d.worker_id=? AND d.store_id=? "
                    "AND i.status IN ('admitted','executing') ORDER BY i.rowid", self.scope())]
            for row in rows:
                frame = json.loads(row["execution_json"])
                if row["status"] == "executing":
                    self._report_unknown(frame, row["run_id"])
                else:
                    self._schedule(frame, row["run_id"])
