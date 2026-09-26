"""Authenticated internal admission and a thin bridge to the existing executor."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

from protocol.generated.python import (ApprovalResponseInput, LocalConversationView,
    RemoteServerOutboundFrame, SendLocalMessageInput, TaskActionInput)
from core.errors import HubError
from storage.idempotency import request_hash
from storage.local_chat import now, TERMINAL
from runtime.remote.link import expired
from runtime.remote.wire import WIRE_REVISION, canonical

BLOCKED_ACTIONS = frozenset({"git_push", "deploy", "delete", "db_migrate", "shell"})
CONNECTION_ERRORS = frozenset({"REMOTE_STORE_CHANGED", "REMOTE_EPOCH_STALE",
    "REMOTE_DEVICE_AUTH_FAILED", "REMOTE_DEVICE_REVOKED", "REMOTE_PROTOCOL_UNSUPPORTED",
    "REMOTE_ACK_CONFLICT", "REMOTE_FRAME_TOO_LARGE", "INTERNAL"})


def error_view(code):
    error = HubError(code, "远程命令无法按当前本机状态执行")
    return {"code": error.code, "message": error.message, "retryable": error.retryable}


def control_result(before, after, *, fallback="supervisor_unconfirmed"):
    observations = [before or {}, after or {}]
    results = [r for o in observations for source in ("controlEvidence", "unresolvedCancellation")
               for r in (o.get(source) or {}).get("cancellations", [])]
    pids = sorted({p for r in results for p in r.get("orphanProcessIds", [])})
    base = {"executionMayStillBeRunning": True, "orphanProcessIds": pids, "observedAt": now()}
    if any(o.get("recoveryRequired") for o in observations) or pids:
        return {**base, "outcome": "unconfirmed", "evidence": "recovery_flag", "reason": "执行仍需本机对账"}
    if any(r["outcome"] == "refused" for r in results):
        return {**base, "outcome": "rejected", "evidence": "adapter_refused", "reason": "Adapter 拒绝停止"}
    if any(r["outcome"] == "not_found" for r in results):
        return {**base, "outcome": "unconfirmed", "evidence": "missing_execution_handle", "reason": "无法确认原生执行停止"}
    if any(o.get("evidenceAvailable") is False for o in observations):
        return {**base, "outcome": "unconfirmed", "evidence": "supervisor_unconfirmed", "reason": "持久控制证据不可得"}
    evidence = (after or {}).get("controlEvidence") or {}
    kind = evidence.get("kind")
    if kind == "cancellation" and len(evidence.get("cancellations", [])) >= evidence.get("expectedHandles", 1) and all(r["outcome"] in {"stopped_gracefully", "force_killed", "already_finished"} for r in evidence["cancellations"]):
        kind = "adapter_confirmed"
    if kind in {"adapter_confirmed", "already_terminal", "node_boundary_paused", "supervisor_resumed", "retry_enqueued", "inbox_tombstone"}:
        return {**base, "outcome": "confirmed", "executionMayStillBeRunning": kind in {"node_boundary_paused", "supervisor_resumed", "retry_enqueued"},
            "evidence": kind, "reason": "本机结构化执行证据已确认"}
    return {**base, "outcome": "unconfirmed", "evidence": "missing_execution_handle" if kind == "missing_execution_handle" else fallback,
        "reason": "尚无充分执行确认，需核对本机状态"}


class CommandBridge:
    def __init__(self, repository, chat, link):
        self.repo, self.chat, self.link = repository, chat, link
        self.lock = asyncio.Lock()

    def policy(self):
        policy = self.repo.get("policy") or {"revision": 1, "blockedActions": []}
        return policy["revision"], BLOCKED_ACTIONS | set(policy["blockedActions"])

    async def receive(self, frame):
        frame = RemoteServerOutboundFrame.model_validate(frame).model_dump(mode="json", by_alias=True, exclude_none=True)
        if self.link.contains_credentials(canonical(frame)):
            # A receipt must echo command/conversation IDs. Treat credential
            # reflection as a connection fault rather than echo secret material.
            raise HubError("REMOTE_DEVICE_AUTH_FAILED", "远程连接包含不允许传播的凭据")
        async with self.lock:
            if not self.repo.check_continuity():
                raise HubError("REMOTE_STORE_CHANGED", "存储世代需要对账")
            link = self.repo.get("link")["view"]
            identity = self.repo.get("identity")
            if link["state"] != "paired":
                raise HubError("REMOTE_STORE_CHANGED", "当前连接禁止命令投递")
            if frame["expectedWorkerStoreId"] != identity["store"]:
                self.repo.freeze("REMOTE_STORE_CHANGED")
                raise HubError("REMOTE_STORE_CHANGED", "命令目标存储世代不匹配")
            workspaces = await self.chat.ports.workspaces.list_workspaces(None, None) if frame["type"] in {"run.submit", "conversation.skip", "command.withdraw"} else []
            registered = {w.id for w in workspaces}
            if self.repo.get("link")["view"] != link or self.repo.get("identity")["store"] != identity["store"]:
                raise HubError("REMOTE_EPOCH_STALE", "接单前绑定状态已变化")
            try:
                with self.repo.database.transaction() as tx:
                    receipt, gaps, execute = self._admit(tx, frame, registered)
            except HubError as error:
                if error.code in CONNECTION_ERRORS:
                    raise
                # The failed admission is fully rolled back before this separate
                # transaction commits the immutable rejection and ordering slot.
                receipt, gaps = self._record_rejection(frame, error.code, registered)
                execute = False
            if execute:
                await self._execute(frame)
            return receipt, gaps

    def _scope_key(self, prefix, value):
        return prefix + request_hash({"store": self.repo.get("identity")["store"],
            "worker": self.repo.get("link")["view"]["workerId"], "value": value})

    def _admit(self, tx, frame, registered):
        cached = self.repo.get(self._scope_key("command-rejection:", frame), tx)
        if cached is not None:
            return cached, [], False
        link = self.repo.get("link", tx)["view"]
        prior = self.repo.inbox(frame["commandId"], tx)
        digest = request_hash(frame)
        if prior and prior["digest"] == digest:
            receipt = json.loads(prior["receipt_json"]) if prior["receipt_json"] else None
            return receipt, [], prior["status"] == "admitted"
        if frame["targetWorkerId"] != link["workerId"]:
            raise HubError("REMOTE_TARGET_MISMATCH", "命令目标设备不匹配")
        binding = tx.connection.execute("SELECT worker_id,store_id FROM remote_conversations WHERE conversation_id=?", (frame["conversationId"],)).fetchone()
        if binding and (binding[0] != frame["targetWorkerId"] or binding[1] != frame["expectedWorkerStoreId"]):
            raise HubError("REMOTE_TARGET_MISMATCH", "对话不属于当前设备绑定")
        if prior:
            if prior["digest"] != "tombstone":
                raise HubError("IDEMPOTENCY_MISMATCH", "命令标识已用于不同内容")
            original = json.loads(prior["command_json"])
            if frame["type"] != "run.submit" or any(frame.get(k) != original.get(k) for k in ("conversationId", "conversationSeq")):
                raise HubError("REMOTE_TARGET_MISMATCH", "撤回记录与迟到命令不匹配")
            tx.connection.execute("UPDATE remote_inbox SET digest=? WHERE worker_id=? AND command_id=?", (digest, link["workerId"], frame["commandId"]))
            self.repo.seal(tx)
            return json.loads(prior["receipt_json"]), [], False
        tx.connection.execute("INSERT INTO remote_inbox(worker_id,command_id,digest,command_json,status) VALUES(?,?,?,?,?)",
            (link["workerId"], frame["commandId"], digest, canonical(frame), "received"))
        self._bind_conversation(tx, frame)
        gaps, execute = [], False
        if frame["type"] in {"run.submit", "conversation.skip"}:
            self._slot(tx, frame["conversationId"], frame["conversationSeq"], frame["commandId"], frame["type"])
            if frame["type"] == "run.submit" and frame["payload"]["workspaceId"] not in registered:
                raise HubError("NOT_FOUND", "工作区未登记")
            gaps = self._drain(tx, frame["conversationId"], registered)
        elif frame["type"] == "command.withdraw":
            self._withdraw(tx, frame)
            gaps = self._drain(tx, frame["conversationId"], registered)
            execute = self.repo.inbox(frame["commandId"], tx)["status"] == "admitted"
        elif self._expired(frame):
            raise HubError("REMOTE_COMMAND_EXPIRED", "命令已过期")
        else:
            record = self._bound_run(frame)
            self._accept(tx, frame, record["run_id"], status="admitted")
            execute = True
        row = self.repo.inbox(frame["commandId"], tx)
        receipt = json.loads(row["receipt_json"]) if row["receipt_json"] else None
        tx.after_commit(self.chat.wake_remote_queue)
        self.repo.seal(tx)
        return receipt, gaps, execute

    def _record_rejection(self, frame, code, registered):
        with self.repo.database.transaction() as tx:
            key = self._scope_key("command-rejection:", frame)
            cached = self.repo.get(key, tx)
            if cached is not None:
                return cached, []
            prior = self.repo.inbox(frame["commandId"], tx)
            if prior is None:
                worker = self.repo.get("link", tx)["view"]["workerId"]
                tx.connection.execute("INSERT INTO remote_inbox(worker_id,command_id,digest,command_json,status) VALUES(?,?,?,?,?)",
                    (worker, frame["commandId"], request_hash(frame), canonical(frame), "rejected"))
            # Conflicting variants must not replace an accepted command or its
            # receipt. Their rejection is independently cached by immutable hash.
            receipt = self._reject(tx, frame, code, persist=prior is None)
            self.repo.put(key, receipt, tx)
            gaps = self._record_rejected_slot(tx, frame, registered) if prior is None else []
            tx.after_commit(self.chat.wake_remote_queue)
            self.repo.seal(tx)
            return receipt, gaps

    def _record_rejected_slot(self, tx, frame, registered):
        if frame["type"] not in {"run.submit", "conversation.skip"}:
            return []
        worker = self.repo.get("link", tx)["view"]["workerId"]
        conversation, seq = frame["conversationId"], frame["conversationSeq"]
        occupied = tx.connection.execute("SELECT 1 FROM remote_slots WHERE worker_id=? AND conversation_id=? AND sequence=?", (worker, conversation, seq)).fetchone()
        if not occupied:
            self._slot(tx, conversation, seq, frame["commandId"], "rejected")
        # Never overwrite a slot owned by another command. Its original submit
        # or tombstone still controls whether the sequence can advance.
        binding = tx.connection.execute("SELECT worker_id,store_id FROM remote_conversations WHERE conversation_id=?", (conversation,)).fetchone()
        if binding and tuple(binding) == (worker, self.repo.get("identity", tx)["store"]):
            return self._drain(tx, conversation, registered)
        # A rejected target must not turn a local/foreign conversation into a
        # remote one. Keep its ordering cursor without adopting any target data.
        key = self._scope_key("rejected-order:", conversation)
        cursor = (self.repo.get(key, tx) or {}).get("consumed", 0)
        while True:
            slot = tx.connection.execute("SELECT i.status FROM remote_slots s JOIN remote_inbox i "
                "ON i.worker_id=s.worker_id AND i.command_id=s.command_id "
                "WHERE s.worker_id=? AND s.conversation_id=? AND s.sequence=?", (worker, conversation, cursor + 1)).fetchone()
            if not slot or slot[0] != "rejected":
                break
            cursor += 1
        self.repo.put(key, {"consumed": cursor}, tx)
        return []

    def _bind_conversation(self, tx, frame):
        conversation = frame["conversationId"]
        row = tx.connection.execute("SELECT * FROM remote_conversations WHERE conversation_id=?", (conversation,)).fetchone()
        target = {k: frame["payload"][k] for k in ("workspaceId", "sceneId", "sceneVersion")} if frame["type"] == "run.submit" else None
        if row and (row["worker_id"] != frame["targetWorkerId"] or row["store_id"] != frame["expectedWorkerStoreId"]):
            raise HubError("REMOTE_TARGET_MISMATCH", "对话不属于当前设备绑定")
        if row and row["target_json"] and target and json.loads(row["target_json"]) != target:
            raise HubError("REMOTE_TARGET_MISMATCH", "对话固定目标不匹配")
        if not row:
            existing = tx.connection.execute("SELECT 1 FROM local_conversations WHERE conversation_id=?", (conversation,)).fetchone()
            if existing:
                raise HubError("CONVERSATION_AUTHORITY_MISMATCH", "已有本机对话不能转为远程对话")
            cursor = (self.repo.get(self._scope_key("rejected-order:", conversation), tx) or {}).get("consumed", 0)
            tx.connection.execute("INSERT INTO remote_conversations VALUES(?,?,?,?,?)", (conversation, frame["targetWorkerId"], frame["expectedWorkerStoreId"], cursor, canonical(target) if target else None))
        elif target and not row["target_json"]:
            tx.connection.execute("UPDATE remote_conversations SET target_json=? WHERE conversation_id=?", (canonical(target), conversation))

    def _slot(self, tx, conversation, seq, command, kind):
        worker = self.repo.get("link", tx)["view"]["workerId"]
        row = tx.connection.execute("SELECT command_id,kind FROM remote_slots WHERE worker_id=? AND conversation_id=? AND sequence=?", (worker, conversation, seq)).fetchone()
        if row:
            if row[0] != command:
                raise HubError("REMOTE_EVENT_CONFLICT", "顺序槽已被另一命令占用")
            return
        tx.connection.execute("INSERT INTO remote_slots VALUES(?,?,?,?,?)", (worker, conversation, seq, command, kind))

    def _drain(self, tx, conversation, registered):
        worker = self.repo.get("link", tx)["view"]["workerId"]
        seq = tx.connection.execute("SELECT consumed_seq FROM remote_conversations WHERE conversation_id=?", (conversation,)).fetchone()[0] + 1
        while True:
            slot = tx.connection.execute("SELECT command_id,kind FROM remote_slots WHERE worker_id=? AND conversation_id=? AND sequence=?", (worker, conversation, seq)).fetchone()
            if not slot:
                break
            item = self.repo.inbox(slot[0], tx)
            frame = json.loads(item["command_json"])
            if slot[1] == "conversation.skip":
                event = self.repo.emit(tx, "conversation.skip_recorded", commandId=slot[0], conversationId=conversation, conversationSeq=seq)
                self.repo.patch_inbox(tx, slot[0], status="rejected", receipt_json=canonical(event))
            elif item["status"] == "received":
                try:
                    if self._expired(frame):
                        raise HubError("REMOTE_COMMAND_EXPIRED", "命令已过期")
                    payload = frame["payload"]
                    if payload["workspaceId"] not in registered:
                        raise HubError("NOT_FOUND", "工作区已不再登记")
                    scene = self.chat.repository.scene(payload["sceneId"])
                    if scene.version != payload["sceneVersion"]:
                        raise HubError("REMOTE_SCENE_VERSION_MISMATCH", "场景版本已变化")
                    if not tx.connection.execute("SELECT 1 FROM local_conversations WHERE conversation_id=?", (conversation,)).fetchone():
                        view = LocalConversationView.model_validate({"id": conversation, "title": "远程对话",
                            "workspaceId": payload["workspaceId"], "sceneId": payload["sceneId"], "authority": "remote",
                            "createdAt": now(), "updatedAt": now(), "version": 1, "archived": False})
                        tx.connection.execute("INSERT INTO local_conversations VALUES(?,?,?)", (conversation, view.model_dump_json(by_alias=True, exclude_none=True), now()))
                    message = SendLocalMessageInput.model_validate({k: payload[k] for k in ("clientMessageId", "text", "sessionMode")})
                    receipt = self.chat.repository.enqueue(conversation, message, frame["commandId"], transaction=tx)
                    self._accept(tx, frame, receipt.run_id)
                except HubError as error:
                    self._reject(tx, frame, error.code)
            seq += 1
        tx.connection.execute("UPDATE remote_conversations SET consumed_seq=? WHERE conversation_id=?", (seq - 1, conversation))
        following = tx.connection.execute("SELECT MIN(sequence) FROM remote_slots WHERE worker_id=? AND conversation_id=? AND sequence>?", (worker, conversation, seq)).fetchone()[0]
        if following:
            identity = self.repo.get("identity", tx)
            return [{"type": "conversation.gap", "wireRevision": WIRE_REVISION, "workerId": worker,
                "workerStoreId": identity["store"], "workerEpoch": identity["epoch"], "conversationId": conversation,
                "expectedSeq": seq, "receivedSeq": following}]
        return []

    @staticmethod
    def _expired(frame):
        try:
            if expired(frame["expiresAt"]):
                return True
            created = datetime.fromisoformat(frame["createdAt"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(frame["expiresAt"].replace("Z", "+00:00"))
        except ValueError:
            raise HubError("VALIDATION_FAILED", "命令时间字段无效") from None
        limit = 7 * 86400 if frame["type"] == "run.submit" else (900 if frame["type"].startswith("run.") else 300)
        return not 0 < (end - created).total_seconds() <= limit

    def _accept(self, tx, frame, run=None, *, status="accepted"):
        fields = {"commandId": frame["commandId"], "conversationId": frame["conversationId"], "receivedAt": now(), "status": "accepted"}
        if run:
            fields["resultRef"] = {"runId": run}
        event = self.repo.emit(tx, "command.accepted", **fields)
        self.repo.patch_inbox(tx, frame["commandId"], status=status, run_id=run, receipt_json=canonical(event))
        return event

    def _reject(self, tx, frame, code, *, persist=True):
        event = self.repo.emit(tx, "command.rejected", commandId=frame["commandId"], conversationId=frame["conversationId"],
            receivedAt=now(), status="rejected", error=error_view(code))
        if persist:
            self.repo.patch_inbox(tx, frame["commandId"], status="rejected", receipt_json=canonical(event))
        return event

    def _withdraw(self, tx, frame):
        if self._expired(frame):
            self._reject(tx, frame, "REMOTE_COMMAND_EXPIRED")
            return
        payload = frame["payload"]
        target = self.repo.inbox(payload["targetCommandId"], tx)
        if target and target["run_id"]:
            original = json.loads(target["command_json"])
            if original.get("type") != "run.submit" or original["conversationId"] != frame["conversationId"] or original["conversationSeq"] != payload["targetConversationSeq"]:
                raise HubError("REMOTE_TARGET_MISMATCH", "撤回目标不匹配")
            record = self.chat.repository.run_record(target["run_id"])
            if record["status"] in TERMINAL:
                self._reject(tx, frame, "REMOTE_WITHDRAWAL_TOO_LATE")
            else:
                self._accept(tx, frame, target["run_id"], status="admitted")
            return
        if target:
            original = json.loads(target["command_json"])
            if original.get("conversationId") != frame["conversationId"] or original.get("conversationSeq") != payload["targetConversationSeq"]:
                raise HubError("REMOTE_TARGET_MISMATCH", "撤回目标序号不匹配")
        self._slot(tx, frame["conversationId"], payload["targetConversationSeq"], payload["targetCommandId"], "tombstone")
        original = {"commandId": payload["targetCommandId"], "conversationId": frame["conversationId"], "conversationSeq": payload["targetConversationSeq"]}
        if target is None:
            tx.connection.execute("INSERT INTO remote_inbox(worker_id,command_id,digest,command_json,status) VALUES(?,?,?,?,?)",
                (frame["targetWorkerId"], payload["targetCommandId"], "tombstone", canonical(original), "rejected"))
        if target is None or target["status"] != "rejected":
            self._reject(tx, original, "REMOTE_COMMAND_WITHDRAWN")
        self._accept(tx, frame)
        result = control_result({}, {"controlEvidence": {"kind": "inbox_tombstone"}})
        self.repo.emit(tx, "command.completed", commandId=frame["commandId"], conversationId=frame["conversationId"], resultStatus="withdrawn", controlResult=result)
        self.repo.patch_inbox(tx, frame["commandId"], status="completed")

    def _bound_run(self, frame):
        run_id = frame["payload"].get("runId")
        if frame["type"] == "command.withdraw":
            target = self.repo.inbox(frame["payload"]["targetCommandId"])
            run_id = target["run_id"] if target else None
        if not run_id:
            raise HubError("REMOTE_TARGET_MISMATCH", "命令没有已接单的执行引用")
        record = self.chat.repository.run_record(run_id)
        if record["conversation_id"] != frame["conversationId"] or str(self.chat.repository.conversation(record["conversation_id"]).authority) != "remote":
            raise HubError("REMOTE_TARGET_MISMATCH", "执行引用不属于该远程对话")
        if frame["payload"].get("nodeId") and frame["type"] != "run.retry":
            raise HubError("REMOTE_TARGET_MISMATCH", "该命令不接受节点引用")
        return record

    def _observation(self, record):
        if not record["task_id"]:
            return {}
        method = getattr(type(self.chat.ports.tasks), "control_observation", None)
        if method is None:
            return {"evidenceAvailable": False}
        return self.chat.ports.tasks.control_observation(record["task_id"])

    async def _execute(self, frame):
        record = self._bound_run(frame)
        before = self._observation(record)
        with self.repo.database.transaction() as tx:
            self.repo.patch_inbox(tx, frame["commandId"], status="executing", observation_json=canonical({"before": before}))
            self.repo.seal(tx)
        ref = {"runId": record["run_id"]}
        if record["task_id"]:
            ref["executionTaskId"] = record["task_id"]
        try:
            if frame["type"] == "approval.decide":
                result = await self._approval(frame, record)
                if (result.details or {}).get("deliveryStatus") != "consumed":
                    self._finish(frame, ref, control_result({}, {}), record["status"])
                    return
                self._completed(frame, ref, "approval_consumed")
                return
            action = "cancel" if frame["type"] == "command.withdraw" else frame["type"].split(".")[1]
            prior_result = control_result(before, before)
            if action in {"resume", "retry"} and (before.get("evidenceAvailable") is False or before.get("recoveryRequired") or before.get("unresolvedCancellation") or prior_result["evidence"] in {"adapter_refused", "recovery_flag", "missing_execution_handle"}):
                self._finish(frame, ref, {**prior_result, "outcome": "unconfirmed", "evidence": "recovery_flag"}, record["status"])
                return
            if action in {"pause", "resume"} and record["status"] in TERMINAL:
                raise HubError("TASK_ACTION_INVALID", "当前执行不接受该控制动作")
            if action == "retry" and record["status"] not in TERMINAL:
                raise HubError("TASK_ACTION_INVALID", "远程重试需要已终止的轮次；节点重置由本机核对后处理")
            if frame["payload"].get("nodeId") and record["task_id"]:
                detail = await self.chat.ports.tasks.get_task(record["task_id"])
                if frame["payload"]["nodeId"] not in {n.id for n in detail.nodes}:
                    raise HubError("REMOTE_TARGET_MISMATCH", "节点不属于当前执行")
            view = await self.chat.consume_remote_control(record["run_id"], TaskActionInput.model_validate({"action": action,
                **({"nodeId": frame["payload"]["nodeId"]} if frame["payload"].get("nodeId") else {})}), "remote:" + frame["commandId"])
            updated = self.chat.repository.run_record(view.id)
            after = self._observation(updated)
            ref = {"runId": view.id, **({"executionTaskId": view.task_id} if view.task_id else {})}
            if view.task and view.task.parent_task_id:
                ref["parentExecutionTaskId"] = view.task.parent_task_id
            if action == "retry":
                if not view.task_id:
                    self._finish(frame, ref, control_result({}, {}), str(view.status))
                else:
                    self._completed(frame, ref, "retry_enqueued")
            else:
                if action == "cancel" and not record["task_id"] and record["status"] in {"queued", "cancelled"}:
                    after = {"controlEvidence": {"kind": "inbox_tombstone"}}
                result = control_result(before, after)
                self._finish(frame, ref, result, str(view.status))
        except Exception as error:
            # A transport/executor exception does not prove rejection or stop.
            # Approval delivery failures can occur after the decision was stored.
            if frame["type"] == "approval.decide":
                approval = await self.chat.ports.approvals.repository.get(frame["payload"]["approvalId"])
                if approval and (approval.details or {}).get("deliveryStatus") in {"dispatching", "failed"}:
                    self._finish(frame, ref, control_result({}, {}, fallback="delivery_unknown"), record["status"])
                    return
            if isinstance(error, HubError) and error.code in {"REMOTE_APPROVAL_FORBIDDEN", "REMOTE_TARGET_MISMATCH", "APPROVAL_EXPIRED", "TASK_ACTION_INVALID", "NOT_FOUND", "CONFLICT"}:
                if frame["type"] == "approval.decide":
                    self._failed(frame, ref, error.code)
                else:
                    result = {"outcome": "rejected", "executionMayStillBeRunning": True, "orphanProcessIds": [],
                        "evidence": "worker_policy", "reason": "当前本机策略或执行条件不允许该动作", "observedAt": now()}
                    self._finish(frame, ref, result, record["status"])
            else:
                self._finish(frame, ref, control_result(before, {}, fallback="delivery_unknown"), record["status"])

    async def recover(self):
        """Resume admission only; never re-issue a possibly delivered control."""
        link = self.repo.get("link")["view"]
        if link["state"] not in {"paired", "frozen"}:
            return
        with self.repo.database.locked_connection() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM remote_inbox WHERE worker_id=? AND status IN ('executing','admitted')", (link["workerId"],))]
        for item in rows:
            frame = json.loads(item["command_json"])
            if item["status"] == "admitted" and link["state"] == "paired":
                await self._execute(frame)
            elif item["status"] == "executing":
                record = self._bound_run(frame)
                ref = {"runId": record["run_id"], **({"executionTaskId": record["task_id"]} if record["task_id"] else {})}
                self._finish(frame, ref, control_result({}, {}, fallback="delivery_unknown"), record["status"])

    async def _approval(self, frame, record):
        payload = frame["payload"]
        tasks = self.chat.ports.tasks
        def guard(current):
            if current.task_id != record["task_id"]:
                raise HubError("REMOTE_TARGET_MISMATCH", "审批不属于当前执行")
            if str(current.status) != "pending" or expired(current.expires_at):
                raise HubError("APPROVAL_EXPIRED", "审批已失效")
            if expired(frame["expiresAt"]) or datetime.fromisoformat(frame["expiresAt"].replace("Z", "+00:00")) > datetime.fromisoformat(current.expires_at.replace("Z", "+00:00")):
                raise HubError("APPROVAL_EXPIRED", "审批决定时效不匹配")
            if payload["decision"] == "approve":
                _, blocked = self.policy()  # Re-read inside coordinator's guard.
                if str(current.action) in blocked:
                    raise HubError("REMOTE_APPROVAL_FORBIDDEN", "该动作必须在本机审批")
                try:
                    permissions = tasks.runtime.permissions
                    policy = permissions.role_policy(str(current.role_id))
                    permissions.assert_action_allowed(policy, current.action, approved=True)
                except Exception:
                    raise HubError("REMOTE_APPROVAL_FORBIDDEN", "当前本机策略不允许远程批准") from None
        return await self.chat.ports.approvals.respond(payload["approvalId"], ApprovalResponseInput.model_validate({
            "decision": payload["decision"], "reason": self.link.sanitized(payload.get("reason", "远程用户决定"))}),
            "remote:" + frame["commandId"], current_guard=guard)

    def _completed(self, frame, ref, status):
        if not self._same_binding(frame):
            return
        with self.repo.database.transaction() as tx:
            fields = {}
            if status == "retry_enqueued":
                fields["controlResult"] = control_result({}, {"controlEvidence": {"kind": "retry_enqueued"}})
            self.repo.emit(tx, "command.completed", commandId=frame["commandId"], conversationId=frame["conversationId"], resultStatus=status, resultRef=ref, **fields)
            self.repo.patch_inbox(tx, frame["commandId"], status="completed", run_id=ref["runId"])
            self.repo.seal(tx)

    def _failed(self, frame, ref, code):
        if not self._same_binding(frame):
            return
        with self.repo.database.transaction() as tx:
            self.repo.emit(tx, "command.failed", commandId=frame["commandId"], conversationId=frame["conversationId"], resultStatus="rejected", resultRef=ref, error=error_view(code))
            self.repo.patch_inbox(tx, frame["commandId"], status="failed")
            self.repo.seal(tx)

    def _finish(self, frame, ref, result, status):
        if not self._same_binding(frame):
            return
        with self.repo.database.transaction() as tx:
            common = {"commandId": frame["commandId"], "conversationId": frame["conversationId"], "resultRef": ref, "controlResult": result}
            self.repo.emit(tx, "command.control_result", **common, executionStatus=status)
            outcome = result["outcome"]
            if outcome == "confirmed":
                self.repo.emit(tx, "command.completed", **common, resultStatus="confirmed")
            elif outcome == "rejected":
                self.repo.emit(tx, "command.failed", **common, resultStatus="rejected", error=error_view("TASK_NOT_CANCELLABLE"))
            self.repo.patch_inbox(tx, frame["commandId"], status={"confirmed": "completed", "rejected": "failed", "unconfirmed": "unconfirmed"}[outcome])
            self.repo.seal(tx)

    def _same_binding(self, frame):
        view = self.repo.get("link")["view"]
        return (view.get("workerId") == frame["targetWorkerId"] and
                self.repo.get("identity")["store"] == frame["expectedWorkerStoreId"])
