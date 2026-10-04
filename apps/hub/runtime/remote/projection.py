"""Publish bounded, durable, allow-listed execution facts (never adapter logs)."""
from __future__ import annotations

import json

from protocol.generated.python import ApprovalView, RemoteCatalogView, RemoteV3CatalogView
from core.errors import HubError
from storage.idempotency import request_hash
from storage.local_chat import now, TERMINAL
from runtime.remote.commands import control_result, error_view
from storage.remote import DEFER_EVENT


class Projector:
    def __init__(self, bridge):
        self.bridge = bridge
        self.repo, self.chat, self.link = bridge.repo, bridge.chat, bridge.link
        self.repo.source_mapper = self.source_event

    def source_event(self, tx, row):
        pi = getattr(self.chat, 'pi', None)
        if pi is not None and self.repo.get('identity', tx).get('wireRevision', 1) < 5:
            if pi.is_pi(json.loads(row['envelope_json'])):
                self.repo.put('pi-deferred', {'pending': True}, tx)
                return None
        """Map remote-critical source slots; only genuinely private slots omit.

        Raw provider payloads/logs never cross the boundary. Missing LocalRun
        bindings are deferred, not declared private to get past a sequence gap.
        """
        envelope = json.loads(row["envelope_json"])
        task_id = envelope.get("taskId")
        if not task_id:
            return None
        link = self.repo.get("link", tx)["view"]
        identity = self.repo.get("identity", tx)
        record = tx.connection.execute(
            "SELECT r.*,i.command_id FROM local_runs r JOIN remote_inbox i ON i.run_id=r.run_id "
            "JOIN remote_conversations c ON c.conversation_id=r.conversation_id "
            "WHERE r.task_id=? AND i.worker_id=? AND c.store_id=? LIMIT 1",
            (task_id, link["workerId"], identity["store"])).fetchone()
        if record is None:
            task = tx.connection.execute("SELECT profile_id,payload_json FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            profile_id = task[0] if task else ""
            if profile_id and profile_id.startswith("local-profile:"):
                run = tx.connection.execute("SELECT r.* FROM local_runs r JOIN remote_conversations c "
                    "ON c.conversation_id=r.conversation_id WHERE r.run_id=? AND c.worker_id=? AND c.store_id=?",
                    (profile_id[len("local-profile:"):], link["workerId"], identity["store"])).fetchone()
                if run is not None:
                    return DEFER_EVENT
            return None
        ref = {"runId": record["run_id"], "executionTaskId": task_id}
        kind = row["type"]
        payload = json.loads(row["payload_json"])
        if kind in {"approval.required", "approval.resolved"}:
            approval_id = payload.get("approvalId")
            approval = tx.connection.execute("SELECT payload_json FROM approvals WHERE approval_id=? AND task_id=?", (approval_id, task_id)).fetchone()
            if not approval:
                return DEFER_EVENT
            view = ApprovalView.model_validate_json(approval[0])
            return "approval.state_changed", {"conversationId": record["conversation_id"], "payload": self.approval_payload(view, ref)}
        status = payload.get("to")
        if kind == "task.created":
            status = "queued"
        if kind in {"task.created", "task.status_changed", "task.completed", "task.failed"} and status in {"queued", "running", "waiting_approval", "paused", "succeeded", "failed", "cancelled"}:
            return "run.state_changed", {"commandId": record["command_id"], "conversationId": record["conversation_id"],
                "payload": {**ref, "conversationId": record["conversation_id"], "status": status, "observedAt": row["occurred_at"]}}
        # The source event is visible as a safe activity marker. Full state and
        # structured errors are projected separately, never dropped as omitted.
        return "run.progress", {"conversationId": record["conversation_id"], "resultRef": ref,
            "message": "本机执行有新的状态观测"}

    def approval_payload(self, approval, ref):
        revision, blocked = self.bridge.policy()
        allowed = str(approval.action) not in blocked
        if allowed:
            try:
                permissions = self.chat.ports.tasks.runtime.permissions
                permissions.assert_action_allowed(permissions.role_policy(str(approval.role_id)), approval.action, approved=True)
            except Exception:
                allowed = False
        payload = {"approvalId": approval.id, "resultRef": {**ref, **({"nodeId": approval.node_id} if approval.node_id else {})},
            "action": str(approval.action), "targetSummary": self.link.sanitized(approval.target_resource),
            "riskLevel": str(approval.risk_level), "status": str(approval.status), "requestedAt": approval.requested_at,
            "expiresAt": approval.expires_at, "remoteApprovalAllowed": allowed, "workerPolicyRevision": revision}
        if not allowed:
            payload["denialCode"] = "REMOTE_APPROVAL_FORBIDDEN"
        return payload

    def changed(self, tx, key, value):
        digest = request_hash(value)
        row = tx.connection.execute("SELECT digest FROM remote_projections WHERE key=?", (key,)).fetchone()
        if row and row[0] == digest:
            return False
        tx.connection.execute("INSERT INTO remote_projections VALUES(?,?) ON CONFLICT(key) DO UPDATE SET digest=excluded.digest", (key, digest))
        return True

    def capability_revision(self):
        catalog = self.repo.get("catalog") or {}
        if catalog.get("store") != self.repo.get("identity")["store"]:
            return 1
        return catalog["revision"]

    async def catalog(self):
        link = self.repo.get("link")["view"]
        workspaces = await self.chat.ports.workspaces.list_workspaces(None, None)
        scenes = self.chat.repository.scenes()
        _, blocked = self.bridge.policy()
        value = {"workerId": link["workerId"], "workerStoreId": self.repo.get("identity")["store"],
            "capabilityRevision": self.capability_revision(), "observedAt": now(), "remotelyBlockedActions": sorted(blocked),
            "workspaces": [{"workspaceId": w.id, "name": self.link.sanitized(w.name), "displayPath": self.link.sanitized(w.path),
                "vcs": str(w.vcs), "canWrite": bool(w.capabilities and w.capabilities.can_run_write_tasks)} for w in workspaces],
            "scenes": [{"sceneId": s.id, "name": self.link.sanitized(s.name), "version": s.version, "readOnly": s.read_only} for s in scenes]}
        pi = getattr(self.chat, 'pi', None)
        revision = self.repo.get('identity').get('wireRevision', 1)
        if pi is not None:
            pi.rebuild()
            if revision < 5:
                value['scenes'] = [s for s in value['scenes'] if s['sceneId'] not in pi.scenes]
        try:
            if self.repo.get("identity").get("wireRevision", 1) >= 3:
                value["authorizedRoots"] = [{**r,"displayName":self.link.sanitized(r["displayName"])} for r in self.roots.catalog()]
                if self.repo.get('identity')['wireRevision'] >= 4:
                    from protocol.generated.python import RemoteV4CatalogView
                    capabilities = self.chat.attachments.capabilities
                    for scene in value['scenes']:
                        scene['roleImageCapabilities'] = capabilities.values.get(scene['sceneId'], [])
                        if revision < 5:
                            scene['roleImageCapabilities'] = [{k:v for k,v in role.items() if k in {'roleId','agentId','imageInput'}} for role in scene['roleImageCapabilities']]
                    value['nativeImageCapabilities'] = [capabilities.native(kind) for kind in ('claude','codex')]
                    if revision >= 5:
                        from protocol.generated.python import RemoteV5CatalogView
                        value['runtimes'] = []
                        for agent in capabilities.agents.values():
                            kind = str(agent.adapter_id)
                            if kind not in {'claude', 'codex', 'pi'}:
                                continue
                            entry = {'agentId': agent.id, 'agentType': kind, 'nativeSessionsSupported': kind != 'pi'}
                            if kind == 'pi':
                                adapter = self.chat.ports.tasks.directory.adapter_for(agent.id)
                                entry['guard'] = adapter.guard.model_dump(mode='json', by_alias=True, exclude_none=True)
                            value['runtimes'].append(entry)
                        known = {r['agentId'] for r in value['runtimes']}
                        for identifier in sorted(pi.agents - known):
                            adapter = self.chat.ports.agents.get('pi')
                            value['runtimes'].append({'agentId': identifier, 'agentType': 'pi',
                                'guard': adapter.guard.model_dump(mode='json', by_alias=True, exclude_none=True),
                                'nativeSessionsSupported': False})
                        native_pi = capabilities.native('pi')
                        # An unbound/ambiguous PI target is not an instance
                        # capability. Keep it unknown locally; do not advertise
                        # a binding the server cannot verify against runtimes.
                        if native_pi.get('agentId') in {r['agentId'] for r in value['runtimes']}:
                            value['nativeImageCapabilities'].append(native_pi)
                        RemoteV5CatalogView.model_validate(value)
                    else:
                        RemoteV4CatalogView.model_validate(value)
                else:
                    RemoteV3CatalogView.model_validate(value)
            else:
                RemoteCatalogView.model_validate(value)
        except Exception:
            raise HubError("REMOTE_FRAME_TOO_LARGE", "已登记目录索引超过协议边界，未上传不完整快照") from None
        with self.repo.database.transaction() as tx:
            contents = {k: v for k, v in value.items() if k not in {"observedAt", "capabilityRevision"}}
            digest = request_hash({'catalog': contents, 'imageResolution': self.chat.attachments.capabilities.fingerprint}) if self.repo.get('identity', tx).get('wireRevision', 1) >= 4 else request_hash(contents)
            previous = self.repo.get("catalog", tx) or {}
            if previous.get("store") != value["workerStoreId"] or previous.get("digest") != digest:
                value["capabilityRevision"] = previous["revision"] + 1 if previous.get("store") == value["workerStoreId"] else 1
                self.repo.emit(tx, "capability.changed", payload=value)
                self.repo.put("catalog", {"store": value["workerStoreId"], "revision": value["capabilityRevision"], "digest": digest}, tx)
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
                uncertain = observation.get("recoveryRequired") or observation.get("unresolvedCancellation") or result["evidence"] in {"adapter_refused", "recovery_flag", "missing_execution_handle"}
                if frame["type"] == "run.submit" and item["status"] == "accepted" and str(view.status) in TERMINAL and not uncertain:
                    if str(view.status) == "failed":
                        self.repo.emit(tx, "command.failed", commandId=frame["commandId"], conversationId=frame["conversationId"], resultStatus="failed", resultRef=ref, error=error_view("TASK_ACTION_INVALID"))
                    else:
                        self.repo.emit(tx, "command.completed", commandId=frame["commandId"], conversationId=frame["conversationId"], resultStatus=str(view.status), resultRef=ref)
                    self.repo.patch_inbox(tx, frame["commandId"], status="completed" if str(view.status) != "failed" else "failed")
                    changed = True
                for message in tx.connection.execute("SELECT * FROM local_messages WHERE run_id=? AND role IN ('assistant','system')", (view.id,)).fetchall():
                    text = self.link.sanitized(message["text"])
                    payload = {"messageId": message["message_id"], "conversationId": view.conversation_id,
                        "role": message["role"], "text": text, "createdAt": message["created_at"],
                        "runId": view.id, "commandId": frame["commandId"]}
                    if len(text) > 32000:
                        # Keep the original answer locally, explicitly report the
                        # transport limit, and do not roll back the real terminal
                        # state or silently truncate an answer into a fake one.
                        payload.update(messageId="notice:" + message["message_id"], role="system",
                            text="REMOTE_FRAME_TOO_LARGE：本轮完整结果超过远程消息上限，已保留在本机，请回到电脑查看。")
                    if self.changed(tx, "message:" + message["message_id"], payload):
                        self.repo.emit(tx, "message.appended", conversationId=view.conversation_id, payload=payload)
                        changed = True
                if changed:
                    self.repo.seal(tx)
            if not view.task_id or not self.chat.ports.approvals.available:
                continue
            for approval in await self.chat.ports.approvals.list_approvals({"taskId": view.task_id}):
                payload = self.approval_payload(approval, ref)
                with self.repo.database.transaction() as tx:
                    if self.changed(tx, "approval:" + approval.id, payload):
                        self.repo.emit(tx, "approval.state_changed", conversationId=view.conversation_id, payload=payload)
                        self.repo.seal(tx)
