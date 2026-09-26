"""Publish bounded, durable, allow-listed execution facts (never adapter logs)."""
from __future__ import annotations

import json

from protocol.generated.python import RemoteCatalogView
from core.errors import HubError
from storage.idempotency import request_hash
from storage.local_chat import now, TERMINAL
from runtime.remote.commands import control_result, error_view


class Projector:
    def __init__(self, bridge):
        self.bridge = bridge
        self.repo, self.chat, self.link = bridge.repo, bridge.chat, bridge.link

    def changed(self, tx, key, value):
        digest = request_hash(value)
        row = tx.connection.execute("SELECT digest FROM remote_projections WHERE key=?", (key,)).fetchone()
        if row and row[0] == digest:
            return False
        tx.connection.execute("INSERT INTO remote_projections VALUES(?,?) ON CONFLICT(key) DO UPDATE SET digest=excluded.digest", (key, digest))
        return True

    async def catalog(self):
        link = self.repo.get("link")["view"]
        workspaces = await self.chat.ports.workspaces.list_workspaces(None, None)
        scenes = self.chat.repository.scenes()
        revision, blocked = self.bridge.policy()
        value = {"workerId": link["workerId"], "workerStoreId": self.repo.get("identity")["store"],
            "capabilityRevision": revision, "observedAt": now(), "remotelyBlockedActions": sorted(blocked),
            "workspaces": [{"workspaceId": w.id, "name": self.link.sanitized(w.name), "displayPath": self.link.sanitized(w.path),
                "vcs": str(w.vcs), "canWrite": w.capabilities.can_run_write_tasks} for w in workspaces],
            "scenes": [{"sceneId": s.id, "name": self.link.sanitized(s.name), "version": s.version, "readOnly": s.read_only} for s in scenes]}
        try:
            RemoteCatalogView.model_validate(value)
        except Exception:
            raise HubError("REMOTE_FRAME_TOO_LARGE", "已登记目录索引超过协议边界，未上传不完整快照") from None
        with self.repo.database.transaction() as tx:
            if self.changed(tx, "catalog:" + link["workerId"], {k: v for k, v in value.items() if k != "observedAt"}):
                self.repo.emit(tx, "capability.changed", payload=value)
                self.repo.seal(tx)

    async def poll(self):
        worker = self.repo.get("link")["view"].get("workerId")
        if not worker:
            return
        with self.repo.database.locked_connection() as db:
            records = [dict(r) for r in db.execute("SELECT * FROM remote_inbox WHERE worker_id=? AND run_id IS NOT NULL AND status NOT IN ('rejected')", (worker,))]
        for item in records:
            frame = json.loads(item["command_json"])
            view = await self.chat.run(item["run_id"])
            record = self.chat.repository.run_record(view.id)
            observation = self.bridge._observation(record)
            ref = {"runId": view.id, **({"executionTaskId": view.task_id} if view.task_id else {})}
            if view.task and view.task.parent_task_id:
                ref["parentExecutionTaskId"] = view.task.parent_task_id
            if frame["type"] == "run.pause" and item["status"] == "unconfirmed":
                before = json.loads(item["observation_json"] or "{}").get("before", {})
                result = control_result(before, observation)
                if result["outcome"] == "confirmed" and result["evidence"] == "node_boundary_paused":
                    self.bridge._finish(frame, ref, result, str(view.status))
            if frame["type"] not in {"run.submit", "run.retry"}:
                continue
            state = {"runId": view.id, "conversationId": view.conversation_id, "status": str(view.status),
                **({"executionTaskId": view.task_id} if view.task_id else {}),
                **({"parentExecutionTaskId": ref["parentExecutionTaskId"]} if "parentExecutionTaskId" in ref else {})}
            with self.repo.database.transaction() as tx:
                changed = False
                if self.changed(tx, "run:" + view.id, state):
                    self.repo.emit(tx, "run.state_changed", commandId=frame["commandId"], conversationId=frame["conversationId"], payload={**state, "observedAt": now()})
                    changed = True
                result = control_result(observation, observation)
                uncertain = observation.get("recoveryRequired") or result["evidence"] in {"adapter_refused", "recovery_flag", "missing_execution_handle"}
                if frame["type"] == "run.submit" and item["status"] == "accepted" and str(view.status) in TERMINAL and not uncertain:
                    if str(view.status) == "failed":
                        self.repo.emit(tx, "command.failed", commandId=frame["commandId"], conversationId=frame["conversationId"], resultStatus="failed", resultRef=ref, error=error_view("TASK_ACTION_INVALID"))
                    else:
                        self.repo.emit(tx, "command.completed", commandId=frame["commandId"], conversationId=frame["conversationId"], resultStatus=str(view.status), resultRef=ref)
                    self.repo.patch_inbox(tx, frame["commandId"], status="completed" if str(view.status) != "failed" else "failed")
                    changed = True
                for message in tx.connection.execute("SELECT * FROM local_messages WHERE run_id=? AND role IN ('assistant','system')", (view.id,)).fetchall():
                    payload = {"messageId": message["message_id"], "conversationId": view.conversation_id,
                        "role": message["role"], "text": self.link.sanitized(message["text"]), "createdAt": message["created_at"],
                        "runId": view.id, "commandId": frame["commandId"]}
                    if self.changed(tx, "message:" + message["message_id"], payload):
                        self.repo.emit(tx, "message.appended", conversationId=view.conversation_id, payload=payload)
                        changed = True
                if changed:
                    self.repo.seal(tx)
            if not view.task_id or not self.chat.ports.approvals.available:
                continue
            for approval in await self.chat.ports.approvals.list_approvals({"taskId": view.task_id}):
                revision, blocked = self.bridge.policy()
                payload = {"approvalId": approval.id, "resultRef": {**ref, "nodeId": approval.node_id},
                    "action": str(approval.action), "targetSummary": self.link.sanitized(approval.target_resource),
                    "riskLevel": str(approval.risk_level), "status": str(approval.status), "requestedAt": approval.requested_at,
                    "expiresAt": approval.expires_at, "remoteApprovalAllowed": str(approval.action) not in blocked,
                    "workerPolicyRevision": revision}
                if not payload["remoteApprovalAllowed"]:
                    payload["denialCode"] = "REMOTE_APPROVAL_FORBIDDEN"
                with self.repo.database.transaction() as tx:
                    if self.changed(tx, "approval:" + approval.id, payload):
                        self.repo.emit(tx, "approval.state_changed", conversationId=view.conversation_id, payload=payload)
                        self.repo.seal(tx)
