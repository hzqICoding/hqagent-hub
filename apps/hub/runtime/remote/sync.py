"""Computer-owned full-copy sync. Transport windows never authorize execution."""
from __future__ import annotations

import hashlib
import json
import codecs

from protocol.generated.python import ApprovalView, RemoteSyncSettingsView
from core.errors import HubError
from storage.idempotency import request_hash
from storage.local_chat import now, uid
from runtime.remote.wire import canonical, encode

CONTENT_TYPES = frozenset({"sync.conversation.upserted", "sync.message.segment", "sync.run.state", "message.appended", "native.index.upserted"})
WINDOW_BYTES = 1024 * 1024


class SyncService:
    def __init__(self, repository, chat, link, busy):
        self.repo, self.chat, self.link, self.busy = repository, chat, link, busy
        self.delivery = None
        self.cancel_queries = lambda: None
        with self.repo.database.transaction() as tx:
            if self.repo.get("sync-settings", tx) is None:
                self.repo.put("sync-settings", {"mirrorEnabled": True, "version": 1, "syncGeneration": 1}, tx)
                self.repo.seal(tx)

    def settings(self):
        return RemoteSyncSettingsView.model_validate(self.repo.get("sync-settings"))

    def active(self):
        return self.repo.get("identity").get("wireRevision", 1) >= 2

    def context(self):
        return self.repo.get("identity")["store"], self.settings().sync_generation

    def set_settings(self, value, key):
        def change(tx):
            old = self.repo.get("sync-settings", tx)
            if value.expected_version != old["version"]:
                raise HubError("CONFLICT", "同步设置已变化，请刷新后重试")
            if not self.active() and self.repo.get("link", tx)["view"].get("workerId"):
                raise HubError("REMOTE_REVISION_REQUIRED", "服务端不支持同步")
            if value.mirror_enabled == old["mirrorEnabled"]:
                return old
            changed = {"mirrorEnabled": value.mirror_enabled, "version": old["version"] + 1,
                       "syncGeneration": old["syncGeneration"] + 1}
            self.repo.put("sync-settings", changed, tx)
            recovery = self.repo.get("sync-recovery", tx) or {}
            if recovery.get("phase") in {"requested", "waiting_reset_ack", "backfilling"}:
                recovery["phase"] = "cancelled"
                self.repo.put("sync-recovery", recovery, tx)
            tx.after_commit(self.cancel_queries)
            if not value.mirror_enabled:
                tx.after_commit(self.chat.attachments.sync.cancel_pending)
                tx.connection.execute("UPDATE local_attachments SET sync_json='{}'")
            tx.connection.execute("DELETE FROM remote_sync_items")
            self.repo.put("sync-work", {"phase": "pending", "resetPending": not value.mirror_enabled}, tx)
            if self.active() and self.repo.get("link", tx)["view"].get("workerId"):
                if value.mirror_enabled:
                    self.capture(tx)
                else:
                    self.reset(tx)
            self.repo.seal(tx)
            return changed
        result, _ = self.chat.repository.command("remote.sync-settings", key,
            value.model_dump(mode="json", by_alias=True), change)
        return RemoteSyncSettingsView.model_validate(result)

    def metadata(self, row):
        value = self.chat.repository._conversation_view(row["payload_json"])
        native = str(value.conversation_kind) == "native"
        fields = {"conversationKind": "native", "agentType": str(value.agent_type), "nativeSessionId": value.native_session_id} if native else {
            "sceneId": str(value.scene_id), "sceneVersion": self.chat.repository.scene(str(value.scene_id)).version}
        if native:
            if value.native_activity:
                fields["nativeActivity"] = value.native_activity.model_dump(mode="json",by_alias=True,exclude_none=True)
            if value.native_source_revision:
                fields["nativeSourceRevision"] = value.native_source_revision
        return {"conversationId": value.id, "workspaceId": value.workspace_id,
                **fields,
                "title": self.link.sanitized(value.title), "createdAt": value.created_at,
                "updatedAt": value.updated_at, "archived": bool(value.archived),
                "visibility": str(value.visibility or "both"), "metadataVersion": value.version or 1,
                "authority": str(value.authority or "local")}

    def _stage(self, tx, batch, kind, row, *, force=False):
        if row['conversation_id'] and tx.connection.execute(
            'SELECT 1 FROM local_conversation_deletions WHERE conversation_id=?',
            (row['conversation_id'],),
        ).fetchone():
            return
        store, generation = self.context()
        pi = getattr(self.chat, 'pi', None)
        if pi is not None and self.repo.get('identity', tx).get('wireRevision', 1) < 5:
            reference = {'id': row['native_id']} if kind == 'native' else {'conversationId': row['conversation_id']}
            if kind == 'native':
                reference.update(json.loads(row['index_json']))
            if pi.is_pi(reference):
                self.repo.put('pi-deferred', {'pending': True}, tx)
                return
        text = None
        revision3 = self.repo.get("identity", tx).get("wireRevision", 1) >= 3
        if kind == "native":
            if not revision3 or row["removed"] or row["conversation_id"]:
                return
            resource = row["native_id"]
            payload = json.loads(row["index_json"])
        elif kind == "conversation":
            resource = row["conversation_id"]
            payload = self.metadata(row)
        elif kind == "message":
            resource = row["message_id"]
            text = self.link.sanitized(row["text"])
            text = self.chat.attachments.library.public_text(text)
            payload = {"messageId": resource, "conversationId": row["conversation_id"],
                "messageSequence": row["sequence"], "role": row["role"], "createdAt": row["created_at"]}
            if row["run_id"]:
                payload["runId"] = row["run_id"]
            attachments = self.chat.attachments
            if attachments.repo.message_rows(resource):
                if self.repo.get('identity',tx).get('wireRevision',1)<4:
                    return
                sources = attachments.repo.message_rows(resource)
                original = attachments.repo.source(resource, tx)
                for source in sources:
                    if source['source_command_id'] and original.get('store') == store and original.get('generation') == generation:
                        delivery = self.delivery.row(source['source_command_id'], tx)
                        if not delivery or not delivery['grant_json']:
                            return
                manifest,command = attachments.sync.manifest(tx,resource)
                payload['attachments']=manifest
                if command: payload['sourceCommandId']=command
        elif kind == "approval":
            resource = row["approval_id"]
            approval = ApprovalView.model_validate_json(row["payload_json"])
            run = tx.connection.execute("SELECT run_id FROM local_runs WHERE task_id=? LIMIT 1", (approval.task_id,)).fetchone()
            revision, blocked = self.delivery.policy()
            allowed = str(approval.action) not in blocked
            if allowed:
                try:
                    permissions = self.chat.ports.tasks.runtime.permissions
                    permissions.assert_action_allowed(permissions.role_policy(str(approval.role_id)), approval.action, approved=True)
                except Exception:
                    allowed = False
            payload = {"approvalId": approval.id, "resultRef": {"runId": run[0], "executionTaskId": approval.task_id},
                "action": str(approval.action), "targetSummary": "本机审批请求；详细目标请在电脑核对", "riskLevel": str(approval.risk_level),
                "status": str(approval.status), "requestedAt": approval.requested_at, "expiresAt": approval.expires_at,
                "remoteApprovalAllowed": allowed, "workerPolicyRevision": revision}
            if not payload["remoteApprovalAllowed"]:
                payload["denialCode"] = "REMOTE_APPROVAL_FORBIDDEN"
        else:
            resource = row["run_id"]
            state = self.busy.observe(row)
            payload = {"runId": resource, "conversationId": row["conversation_id"],
                "status": state["status"], "observedAt": row["updated_at"],
                "recoveryRequired": state["recoveryRequired"]}
            if row["task_id"]:
                payload["executionTaskId"] = row["task_id"]
        if kind != "native" and not revision3:
            conv = tx.connection.execute("SELECT payload_json FROM local_conversations WHERE conversation_id=?", (row["conversation_id"],)).fetchone()
            if conv and json.loads(conv[0]).get("conversationKind") == "native":
                return  # No reliable seq is allocated for deferred native data.
        digest = request_hash({"payload": payload, "text": text})
        previous = tx.connection.execute("SELECT revision,digest FROM remote_sync_versions WHERE store_id=? AND generation=? AND kind=? AND resource_id=?",
                                        (store, generation, kind, resource)).fetchone()
        if previous and previous[1] == digest and not force:
            return
        revision = previous[0] + int(previous[1] != digest) if previous else 1
        if kind == "message":
            payload["messageRevision"] = revision
        tx.connection.execute("INSERT INTO remote_sync_versions VALUES(?,?,?,?,?,?) ON CONFLICT(store_id,generation,kind,resource_id) "
            "DO UPDATE SET revision=excluded.revision,digest=excluded.digest", (store, generation, kind, resource, revision, digest))
        body = text.encode("utf-8") if text is not None else b""
        tx.connection.execute("INSERT INTO remote_sync_items(backfill_id,kind,resource_id,conversation_id,payload_json,text,revision,segment_count,content_hash,byte_count) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (batch, kind, resource, row["conversation_id"] or "", canonical(payload), text, revision,
             max(1, (len(text) + 15999) // 16000) if text is not None else None,
             hashlib.sha256(body).hexdigest() if text is not None else None, len(body)))

    def capture(self, tx):
        store, generation = self.context()
        if self.repo.get('identity', tx).get('wireRevision', 1) >= 5:
            self.repo.put('pi-deferred', {'pending': False}, tx)
        # Staging has no allocated reliable identity. A new full snapshot
        # supersedes it atomically; keep the immutable Outbox itself untouched.
        tx.connection.execute("DELETE FROM remote_sync_items")
        batch = uid("backfill")
        high = tx.connection.execute("SELECT COALESCE(MAX(sequence),0) FROM remote_sync_changes").fetchone()[0]
        for kind, table, order in (("conversation", "local_conversations", "conversation_id"),
                                   ("message", "local_messages", "conversation_id,sequence"),
                                   ("run", "local_runs", "conversation_id,created_at")):
            # The cursor materializes one resource at a time in this snapshot
            # transaction; no list containing the entire conversation history.
            for row in tx.connection.execute(f"SELECT * FROM {table} ORDER BY {order}"):
                self._stage(tx, batch, kind, row, force=True)
        for row in tx.connection.execute("SELECT a.*,r.conversation_id FROM approvals a JOIN local_runs r ON r.task_id=a.task_id ORDER BY a.approval_id"):
            self._stage(tx, batch, "approval", row, force=True)
        for row in tx.connection.execute("SELECT * FROM native_sources WHERE removed=0 AND conversation_id IS NULL ORDER BY native_id"):
            self._stage(tx, batch, "native", row, force=True)
        self.repo.put("sync-work", {"store": store, "generation": generation, "backfillId": batch,
            "phase": "backfilling", "high": high, "cursor": high, "batch": 0, "waitAck": None}, tx)

    def prepare(self):
        if not self.active():
            return
        with self.repo.database.transaction() as tx:
            work = self.repo.get("sync-work", tx) or {}
            store, generation = self.context()
            if not self.settings().mirror_enabled:
                if work.get("resetPending") or work.get("store") != store:
                    self.reset(tx)
            elif work.get("store") != store or work.get("generation") != generation or work.get("phase") in {"pending", "synced"}:
                self.capture(tx)
            elif work.get('backfillId') and work.get('phase') in {'backfilling', 'waiting_complete_ack'}:
                # Older reconnects could retain staging from a superseded
                # snapshot. Its data is covered by this full capture; it has
                # no reliable seq and must not strand the upgrade fence.
                tx.connection.execute('DELETE FROM remote_sync_items WHERE backfill_id<>?', (work['backfillId'],))
            self.repo.seal(tx)

    def reset(self, tx):
        if self.delivery is not None:
            self.delivery.release_pending(tx, "REMOTE_SYNC_DISABLED")
        event = self.repo.emit(tx, "sync.reset", syncGeneration=self.settings().sync_generation)
        self.retire(tx, event)
        self.repo.put("sync-work", {"store": event["workerStoreId"], "generation": event["syncGeneration"],
            "phase": "waiting_reset_ack", "resetSeq": event["seq"], "resetPending": False}, tx)

    def retire(self, tx, deletion):
        store = deletion["workerStoreId"]
        pending = []
        def proof(slots):
            frame = {"type": "sync.content.redaction", "wireRevision": deletion["wireRevision"], "redactionId": uid("redaction"),
                **{k: deletion[k] for k in ("workerId", "workerStoreId", "workerEpoch", "syncGeneration")},
                "deletionEventId": deletion["eventId"], "deletionSeq": deletion["seq"], "slots": slots}
            tx.connection.execute("INSERT INTO remote_sync_redactions VALUES(?,?,?,?)", (store, deletion["seq"], frame["redactionId"], encode(frame)))
        for row in tx.connection.execute("SELECT * FROM remote_outbox WHERE store_id=? AND seq<? ORDER BY seq", (store, deletion["seq"])):
            frame = json.loads(row["frame_json"])
            if frame.get("type") not in CONTENT_TYPES:
                continue
            pending.append({"seq": row["seq"], "eventId": row["event_id"],
                            "eventSha256": row["digest"], "originalType": frame["type"]})
            tx.connection.execute("UPDATE remote_outbox SET frame_json='{}' WHERE store_id=? AND seq=?", (store, row["seq"]))
            local = tx.connection.execute("SELECT envelope_json FROM events WHERE seq=? AND aggregate_id='remote-worker'", (row["seq"],)).fetchone()
            if local:
                envelope = json.loads(local[0])
                envelope["payload"] = {}
                tx.connection.execute("UPDATE events SET payload_json='{}',envelope_json=? WHERE seq=?", (canonical(envelope), row["seq"]))
            if len(pending) == 100:
                proof(pending)
                pending = []
        if pending:
            proof(pending)
        self._erase_event_copies(tx, store)
        tx.connection.execute("DELETE FROM remote_sync_items")
        tx.connection.execute("UPDATE remote2_delivery SET command_json=NULL WHERE worker_id=? AND store_id=?", (deletion["workerId"], store))
        tx.connection.execute("UPDATE remote_inbox SET command_json='{}' WHERE worker_id=? AND command_id IN "
            "(SELECT command_id FROM remote2_delivery WHERE worker_id=? AND store_id=?)", (deletion["workerId"], deletion["workerId"], store))

    def _erase_event_copies(self, tx, store):
        # ACK pruning removes Outbox bodies, but the private Hub event store may
        # still contain transport copies. Native local messages are untouched.
        for row in tx.connection.execute("SELECT seq,envelope_json,payload_json FROM events WHERE aggregate_id='remote-worker' AND json_extract(payload_json,'$.workerStoreId')=?", (store,)):
            if json.loads(row["payload_json"]).get("type") in CONTENT_TYPES:
                envelope = json.loads(row["envelope_json"])
                envelope["payload"] = {}
                tx.connection.execute("UPDATE events SET payload_json='{}',envelope_json=? WHERE seq=?", (canonical(envelope), row["seq"]))

    def discard_binding(self, tx):
        tx.after_commit(self.cancel_queries)
        tx.after_commit(self.chat.attachments.sync.cancel_pending)
        tx.connection.execute("UPDATE local_attachments SET sync_json='{}'")
        if not self.active():
            return
        if self.delivery is not None and self.repo.get("link", tx)["view"].get("workerId"):
            self.delivery.release_pending(tx, "REMOTE_DEVICE_REVOKED")
        store = self.repo.get("identity", tx)["store"]
        self._erase_event_copies(tx, store)
        for row in tx.connection.execute("SELECT seq,frame_json FROM remote_outbox WHERE store_id=?", (store,)):
            if json.loads(row["frame_json"]).get("type") in CONTENT_TYPES:
                tx.connection.execute("UPDATE remote_outbox SET frame_json='{}' WHERE store_id=? AND seq=?", (store, row["seq"]))
        tx.connection.execute("DELETE FROM remote_sync_items")
        tx.connection.execute("UPDATE remote2_delivery SET command_json=NULL WHERE store_id=?", (store,))
        tx.connection.execute("UPDATE remote_inbox SET command_json='{}' WHERE EXISTS "
            "(SELECT 1 FROM remote2_delivery d WHERE d.store_id=? AND d.worker_id=remote_inbox.worker_id AND d.command_id=remote_inbox.command_id)", (store,))
        self.repo.put("sync-work", {"phase": "revoked"}, tx)

    def revoked(self):
        # Revocation itself authorizes no new outbound connection. The server
        # owns erasure of its revoked device; locally discard retransmittable data.
        with self.repo.database.transaction() as tx:
            self.discard_binding(tx)
            self.repo.seal(tx)

    def on_ack(self):
        if not self.active():
            return
        with self.repo.database.transaction() as tx:
            identity = self.repo.get("identity", tx)
            ack = identity["ack"] or 0
            tx.connection.execute("DELETE FROM remote_sync_redactions WHERE store_id=? AND deletion_seq<=?", (identity["store"], ack))
            work = self.repo.get("sync-work", tx) or {}
            changed = False
            if work.get("phase") == "waiting_reset_ack" and ack >= work["resetSeq"]:
                recovery = self.repo.get("sync-recovery", tx) or {}
                if (self.settings().mirror_enabled and recovery.get("phase") == "waiting_reset_ack"
                        and recovery.get("store") == identity["store"]
                        and recovery.get("generation") == self.settings().sync_generation):
                    # reset closes its generation permanently. Rebuild only in
                    # a strictly newer generation after its contiguous ACK.
                    settings = self.repo.get("sync-settings", tx)
                    settings.update(version=settings["version"] + 1, syncGeneration=settings["syncGeneration"] + 1)
                    self.repo.put("sync-settings", settings, tx)
                    self.capture(tx)
                    work = self.repo.get("sync-work", tx)
                    recovery.update(phase="backfilling", generation=settings["syncGeneration"])
                    self.repo.put("sync-recovery", recovery, tx)
                    changed = True
                else:
                    work["phase"], changed = "disabled", True
            if work.get("phase") == "waiting_complete_ack" and ack >= work["waitAck"]:
                work.update(phase="synced", waitAck=None)
                recovery = self.repo.get("sync-recovery", tx) or {}
                if recovery.get("store") == identity["store"] and recovery.get("generation") == self.settings().sync_generation:
                    recovery["phase"] = "complete"
                    self.repo.put("sync-recovery", recovery, tx)
                changed = True
            if changed:
                self.repo.put("sync-work", work, tx)
                self.repo.seal(tx)

    def control_frames(self):
        with self.repo.database.locked_connection() as db:
            identity = self.repo.get("identity")
            store, ack = identity["store"], identity["ack"] or 0
            rows = db.execute("SELECT deletion_seq,frame_json FROM remote_sync_redactions WHERE store_id=? ORDER BY deletion_seq,rowid", (store,))
            frames, seen = [], set()
            for row in rows:
                if max(s["seq"] for s in json.loads(row[1])["slots"]) <= ack:
                    continue
                if row[0] not in seen:
                    event = db.execute("SELECT frame_json FROM remote_outbox WHERE store_id=? AND seq=?", (store, row[0])).fetchone()
                    if event:
                        frames.append(event[0])
                    seen.add(row[0])
                frames.append(row[1])
                if len(frames) >= 16:
                    break
            return frames

    def upsert(self, tx, conversation):
        if not self.settings().mirror_enabled:
            return
        row = tx.connection.execute("SELECT * FROM local_conversations WHERE conversation_id=?", (conversation,)).fetchone()
        payload = self.metadata(row)
        pi = getattr(self.chat, 'pi', None)
        if pi is not None and self.repo.get('identity', tx).get('wireRevision', 1) < 5 and pi.is_pi(payload):
            self.repo.put('pi-deferred', {'pending': True}, tx)
            return
        if payload.get("conversationKind") == "native" and self.repo.get("identity", tx).get("wireRevision", 1) < 3:
            return
        tx.connection.execute("DELETE FROM remote_sync_items WHERE kind='conversation' AND conversation_id=?", (conversation,))
        self.repo.emit(tx, "sync.conversation.upserted", syncGeneration=self.settings().sync_generation, payload=payload)

    def pump(self):
        if not self.active() or not self.settings().mirror_enabled:
            return
        work = self.repo.get("sync-work") or {}
        if work.get("phase") not in {"backfilling", "synced"}:
            return
        identity = self.repo.get("identity")
        if work.get("waitAck") and (identity["ack"] or 0) < work["waitAck"]:
            return
        with self.repo.database.transaction() as tx:
            unacked = tx.connection.execute("SELECT COUNT(*),COALESCE(SUM(length(CAST(frame_json AS BLOB))),0) FROM remote_outbox WHERE store_id=? AND frame_json<>'{}'", (identity["store"],)).fetchone()
            if unacked[0] >= 15 or unacked[1] >= WINDOW_BYTES - 4096:
                return
            if work["phase"] == "synced":
                self._incremental(tx, work)
            count, size = 0, 0
            while count < min(100, 15 - unacked[0]):
                # Read a bounded UTF-8 byte range. SQLite TEXT substr/length stop
                # at embedded NUL; BLOB slicing preserves every original byte.
                row = tx.connection.execute("SELECT item_id,kind,conversation_id,payload_json,segment_index,segment_count,content_hash,byte_count,"
                    "substr(CAST(text AS BLOB),byte_offset+1,64000) AS segment FROM remote_sync_items WHERE backfill_id=? ORDER BY item_id LIMIT 1",
                    (work["backfillId"],)).fetchone()
                if row is None:
                    break
                payload = json.loads(row["payload_json"])
                if row["kind"] == "message":
                    segment = codecs.getincrementaldecoder("utf-8")().decode(row["segment"], final=False)[:16000]
                    payload.update(text=segment, segmentIndex=row["segment_index"], segmentCount=row["segment_count"],
                        totalUtf8Bytes=row["byte_count"], contentSha256=row["content_hash"])
                    kind = "sync.message.segment"
                elif row["kind"] == "native":
                    kind = "native.index.upserted"
                elif row["kind"] == "approval":
                    kind = "approval.state_changed"
                else:
                    kind = "sync.conversation.upserted" if row["kind"] == "conversation" else "sync.run.state"
                extra = {"conversationId": row["conversation_id"]} if row["kind"] == "approval" else {"syncGeneration": self.settings().sync_generation}
                projected = {**self.repo.base(kind, self.repo.high_water(tx) + 1, self.repo.get("identity", tx)),
                             **extra, "payload": payload}
                frame_size = len(encode(projected).encode("utf-8"))
                if size + frame_size + 4096 > WINDOW_BYTES - unacked[1]:
                    break
                emitted = self.repo.emit(tx, kind, **extra, payload=payload)
                if row['kind']=='message' and row['segment_index']+1==row['segment_count']:
                    self.chat.attachments.sync.allocated(tx,payload['messageId'],emitted['seq'],payload)
                size += frame_size
                count += 1
                if row["kind"] == "message" and row["segment_index"] + 1 < row["segment_count"]:
                    tx.connection.execute("UPDATE remote_sync_items SET segment_index=segment_index+1,byte_offset=byte_offset+? WHERE item_id=?", (len(segment.encode("utf-8")), row["item_id"]))
                else:
                    tx.connection.execute("DELETE FROM remote_sync_items WHERE item_id=?", (row["item_id"],))
            pending = tx.connection.execute("SELECT 1 FROM remote_sync_items WHERE backfill_id=? LIMIT 1", (work["backfillId"],)).fetchone()
            complete = work["phase"] == "backfilling" and pending is None and count == 0 and not self.chat.attachments.sync.pending(tx)
            if count or complete:
                event = self.repo.emit(tx, "sync.backfill.progress", syncGeneration=self.settings().sync_generation,
                    backfillId=work["backfillId"], batchIndex=work["batch"], batchEventCount=count,
                    snapshotHighWater=work["high"], complete=complete)
                work.update(batch=work["batch"] + 1, waitAck=event["seq"])
                if complete:
                    work["phase"] = "waiting_complete_ack"
            self.repo.put("sync-work", work, tx)
            self.repo.seal(tx)

    def _incremental(self, tx, work):
        changes = tx.connection.execute("SELECT * FROM remote_sync_changes WHERE sequence>? ORDER BY sequence LIMIT 100", (work["cursor"],)).fetchall()
        for change in changes:
            work["cursor"] = change["sequence"]
            if change["kind"] == "native":
                row = tx.connection.execute("SELECT * FROM native_sources WHERE native_id=?", (change["resource_id"],)).fetchone()
                if row:
                    self._stage(tx, work["backfillId"], "native", row)
                continue
            if change["deleted"]:
                continue  # No frozen local per-conversation deletion entry point.
            if change["kind"] == "approval":
                row = tx.connection.execute("SELECT a.*,r.conversation_id FROM approvals a JOIN local_runs r ON r.task_id=a.task_id WHERE a.approval_id=?", (change["resource_id"],)).fetchone()
                if row:
                    self._stage(tx, work["backfillId"], "approval", row)
                continue
            table, column = {"conversation": ("local_conversations", "conversation_id"),
                             "message": ("local_messages", "message_id"), "run": ("local_runs", "run_id")}[change["kind"]]
            row = tx.connection.execute(f"SELECT * FROM {table} WHERE {column}=?", (change["resource_id"],)).fetchone()
            if row:
                self._stage(tx, work["backfillId"], change["kind"], row)
                if change["kind"] == "run" and row["task_id"]:
                    for approval in tx.connection.execute("SELECT a.*,r.conversation_id FROM approvals a JOIN local_runs r ON r.task_id=a.task_id WHERE a.task_id=?", (row["task_id"],)):
                        self._stage(tx, work["backfillId"], "approval", approval)

    def prune_native(self):
        if self.repo.get("identity").get("wireRevision", 1) < 3 or not self.settings().mirror_enabled:
            return
        with self.repo.database.transaction() as tx:
            store, generation = self.context()
            for row in tx.connection.execute("SELECT * FROM native_sources WHERE removed<>0 OR conversation_id IS NOT NULL"):
                tx.connection.execute("DELETE FROM remote_sync_items WHERE kind='native' AND resource_id=?", (row["native_id"],))
                previous = tx.connection.execute("SELECT 1 FROM remote_sync_versions WHERE store_id=? AND generation=? AND kind='native' AND resource_id=?", (store,generation,row["native_id"])).fetchone()
                tombstone = f"native-deleted:{store}:{generation}:" + row["native_id"]
                if previous is None or self.repo.get(tombstone, tx):
                    continue
                deletion = self.repo.emit(tx, "native.index.deleted", syncGeneration=generation,
                    nativeSessionId=row["native_id"], workspaceId=row["workspace_id"], deletedAt=now(),
                    reason="imported" if row["conversation_id"] else "source_removed" if row["removed"] == 2 else "workspace_removed")
                slots = []
                for outbox in tx.connection.execute("SELECT * FROM remote_outbox WHERE store_id=? AND seq<?", (store,deletion["seq"])):
                    old = json.loads(outbox["frame_json"])
                    if old.get("type") == "native.index.upserted" and old["payload"]["nativeSessionId"] == row["native_id"]:
                        slots.append({"seq":outbox["seq"],"eventId":outbox["event_id"],"eventSha256":outbox["digest"],"originalType":old["type"]})
                        tx.connection.execute("UPDATE remote_outbox SET frame_json='{}' WHERE store_id=? AND seq=?", (store,outbox["seq"]))
                for record in tx.connection.execute("SELECT seq,envelope_json,payload_json FROM events WHERE aggregate_id='remote-worker'"):
                    body = json.loads(record["payload_json"])
                    if body.get("type") == "native.index.upserted" and body.get("workerStoreId") == store and body["payload"]["nativeSessionId"] == row["native_id"]:
                        envelope = json.loads(record["envelope_json"]); envelope["payload"] = {}
                        tx.connection.execute("UPDATE events SET payload_json='{}',envelope_json=? WHERE seq=?", (canonical(envelope),record["seq"]))
                for start in range(0,len(slots),100):
                    proof = {"type":"sync.content.redaction","wireRevision":self.repo.get("identity",tx)["wireRevision"],"redactionId":uid("redaction"),
                        **{k:deletion[k] for k in ("workerId","workerStoreId","workerEpoch","syncGeneration","nativeSessionId")},
                        "deletionEventId":deletion["eventId"],"deletionSeq":deletion["seq"],"slots":slots[start:start+100]}
                    tx.connection.execute("INSERT INTO remote_sync_redactions VALUES(?,?,?,?)", (store,deletion["seq"],proof["redactionId"],encode(proof)))
                self.repo.put(tombstone, {"seq":deletion["seq"]}, tx)
            self.repo.seal(tx)

    def source_event(self, tx, row):
        if self.repo.get("identity",tx).get("wireRevision", 1) >= 3 and row["type"] == "native.closure.confirmed":
            payload = json.loads(row["payload_json"])
            if payload.get("commandId") and payload.get("_storeId") == self.repo.get("identity",tx)["store"] and payload.get("_workerId") == self.repo.get("link",tx)["view"].get("workerId"):
                return "native.closure.confirmed",{k:payload[k] for k in ("commandId","nativeSessionId","confirmation")}
        # The local kernel event log is private. Migration 7 journals durable
        # conversation/message/run/approval changes separately, in their source
        # transactions. Sync emits those after metadata, in bounded batches;
        # raw provider events never masquerade as already-synced content.
        return None

    async def poll_execution(self, bridge):
        with self.repo.database.locked_connection() as db:
            rows = [dict(r) for r in db.execute("SELECT i.*,d.local_id FROM remote_inbox i JOIN remote2_delivery d "
                "ON d.worker_id=i.worker_id AND d.command_id=i.command_id WHERE d.store_id=? AND i.run_id IS NOT NULL "
                "AND i.status IN ('accepted','unconfirmed','completed')", (self.repo.get("identity")["store"],))]
        for item in rows:
            frame = bridge.execution_frame(item["command_id"])
            if not frame or frame['wireRevision'] != self.repo.get('identity')['wireRevision']:
                continue
            view = await self.chat.run(item["run_id"])
            record = self.chat.repository.run_record(view.id)
            observation = bridge._observation(record)
            from runtime.remote.commands import control_result
            if frame["type"] == "run.pause" and item["status"] == "unconfirmed":
                before = json.loads(item["observation_json"] or "{}").get("before", {})
                result = control_result(before, observation)
                if result["outcome"] == "confirmed" and result["evidence"] == "node_boundary_paused":
                    bridge._finish(frame, bridge.result_ref(record), result, str(view.status))
            if frame["type"] == "run.submit" and item["status"] == "accepted" and str(view.status) in {"succeeded", "failed", "cancelled"}:
                if observation.get("recoveryRequired") or observation.get("unresolvedCancellation"):
                    # A terminal LocalRun with uncertain native effects cannot
                    # be reported as success, but leaving admission accepted
                    # forever loses its final reconciliation outcome too.
                    result = control_result({}, {**observation, 'recoveryRequired': True})
                    bridge._finish(frame, bridge.result_ref(record), result, str(view.status))
                else:
                    if str(view.status) == "failed":
                        bridge._failed(frame, bridge.result_ref(record), self.chat.repository.failure_code(view.id) or "TASK_ACTION_INVALID")
                    else:
                        bridge._completed(frame, bridge.result_ref(record), str(view.status))
