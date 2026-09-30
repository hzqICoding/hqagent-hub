"""Owner-scoped business transactions; no database dialect or socket operations."""
import base64
import hmac
import json

from .common import MAX_SEQ, Fault, canonical, digest, require, seconds, stamp, uid, validated
from . import wire

KINDS = {"devices": ("device", "RemoteDeviceView", "RemoteDevicePage"),
         "conversations": ("conversation", "RemoteConversationView", "RemoteConversationPage"),
         "commands": ("command", "RemoteCommandView", "RemoteCommandPage"),
         "runs": ("run", "RemoteRunView", "RemoteRunPage"),
         "messages": ("message", "RemoteMessageView", "RemoteMessagePage"),
         "approvals": ("approval", "RemoteApprovalView", None)}
TERMINAL = {"completed", "failed", "rejected"}
BLOCKED = {"git_push", "deploy", "delete", "db_migrate"}


class Service:
    def __init__(self, repo, settings, security):
        self.repo, self.settings, self.security = repo, settings, security
        self.connections = {}  # (owner, worker) -> authenticated transport, never authority

    def now(self):
        return stamp(self.settings.clock())

    def online(self, owner, worker):
        connection = self.connections.get((owner, worker))
        online = bool(connection and not connection.closed and self.settings.monotonic() - connection.last_seen < 45)
        if connection and not online:
            connection.wake()
        return online

    def notify(self, tx, owner, worker):
        def wake():
            connection = self.connections.get((owner, worker))
            if connection:
                connection.wake()
        tx.after_commit((owner, worker), wake)

    def save(self, tx, owner, kind, identifier, value, *, management=False):
        if kind=='command' and hasattr(self,'attachments'):
            self.attachments.release_failed(tx,owner,value)
        if kind == 'device':
            current = tx.get(owner, kind, identifier)
            if current and current.get('_deleted'):
                return  # A stale transport object cannot resurrect a tombstone.
            if current and not management:
                value = dict(value)
                for field in ('remoteAccess', 'version', 'displayName', 'suspendedAt'):
                    value.pop(field, None)
                    if field in current:
                        value[field] = current[field]
                if current['status'] == 'revoked':
                    value.update(status='revoked', revokedAt=current['revokedAt'])
            value.setdefault('remoteAccess', 'enabled')
            value.setdefault('version', 1)
        frame = value.get("_frame", value)
        tx.put(owner, kind, identifier, value,
               worker=frame.get("targetWorkerId", frame.get("workerId", value.get("_worker", ""))),
               store=frame.get("expectedWorkerStoreId", frame.get("workerStoreId", value.get("_store", ""))),
               parent=value.get("conversationId", value.get("_conversation", "")))

    def get(self, tx, owner, kind, identifier):
        value = tx.get(owner, kind, identifier)
        require(value is not None and (kind != 'device' or not value.get('_deleted')), "NOT_FOUND")
        return value

    def view(self, owner, kind, value):
        public = {k: v for k, v in value.items() if not k.startswith("_")}
        if kind == "device":
            public.setdefault('remoteAccess', 'enabled')
            public.setdefault('version', 1)
            if public["status"] not in {"revoked", "reconciliation_required"}:
                public["status"] = "online" if self.online(owner, value["workerId"]) else "offline"
            public["observedAt"] = self.now()
        if kind in {"command", "run"}:
            worker = value.get("targetWorkerId", value.get("_worker"))
            public["workerOnline"] = self.online(owner, worker)
            if kind == "command" and value["status"] == "queued" and not value["_dispatch"] and public["deliveryState"] != "reconciliation_required":
                public["deliveryState"] = "queued_online" if public["workerOnline"] else "queued_offline"
        return public

    def event(self, tx, owner, event_type, payload):
        tx.browser_add(owner, dict(type=event_type, recordedAt=self.now(), payload=payload))

    def command_event(self, tx, owner, command):
        self.event(tx, owner, "command.updated", self.view(owner, "command", command))

    def cursor(self, tx, owner, scope, position):
        # owner participates in the signature without exposing its identifier.
        generation = tx.browser_retention(owner)["generation"] if tx is not None and scope == "events" else 0
        claims = dict(scope=scope, position=position, expiresAt=int((self.settings.clock() + self.settings.cursor_ttl) * 1000), generation=generation)
        payload = base64.urlsafe_b64encode(canonical(claims).encode()).decode().rstrip("=")
        signature = self.security.mac("cursor-v1", canonical(dict(claims, owner=owner)))
        return "c1." + payload + "." + signature

    def position(self, tx, owner, scope, token):
        try:
            require(isinstance(token, str) and 16 <= len(token) <= 2048, "REMOTE_CURSOR_INVALID")
            version, payload, signature = token.split(".")
            require(version == "c1", "REMOTE_CURSOR_INVALID")
            raw = base64.b64decode(payload + "=" * (-len(payload) % 4), altchars=b"-_", validate=True)
            claims = json.loads(raw)
            require(isinstance(claims, dict) and set(claims) == {"scope", "position", "expiresAt", "generation"}, "REMOTE_CURSOR_INVALID")
            require(claims["scope"] == scope and type(claims["position"]) is int and claims["position"] >= 0
                    and type(claims["expiresAt"]) is int and type(claims["generation"]) is int and claims["generation"] >= 0, "REMOTE_CURSOR_INVALID")
            expected = self.security.mac("cursor-v1", canonical(dict(claims, owner=owner)))
            require(hmac.compare_digest(signature, expected), "REMOTE_CURSOR_INVALID")
            require(claims["expiresAt"] > self.settings.clock() * 1000, "REMOTE_CURSOR_EXPIRED")
            if tx is not None and scope == "events":
                retention = tx.browser_retention(owner)
                position, floor = claims["position"], retention["prunedThrough"]
                require(position > floor or (position == floor and claims["generation"] == retention["generation"]), "REMOTE_CURSOR_EXPIRED")
                require(position <= tx.browser_tail(owner), 'REMOTE_CURSOR_EXPIRED')
            return claims["position"]
        except Fault:
            raise
        except (ValueError, TypeError, KeyError, RecursionError):
            raise Fault("REMOTE_CURSOR_INVALID") from None

    def page(self, tx, owner, kind, token, limit, parent=None):
        scope = "page:" + kind + ":" + (parent or "")
        start = self.position(tx, owner, scope, token) if token else 0
        values = tx.list(owner, kind, parent=parent, limit=limit + 1, offset=start)
        result = dict(items=[self.view(owner, kind, item) for item in values[:limit]], hasMore=len(values) > limit)
        if result["hasMore"]:
            result["nextCursor"] = self.cursor(tx, owner, scope, start + limit)
        return result

    def events(self, tx, owner, token, limit):
        if not token:
            return dict(items=[], hasMore=False, nextServerCursor=self.cursor(tx, owner, "events", tx.browser_tail(owner)))
        position = self.position(tx, owner, "events", token)
        records = tx.browser_after(owner, position, limit + 1)
        items = []
        for index, body in records[:limit]:
            items.append(dict(body, serverCursor=self.cursor(tx, owner, "events", index)))
        end = records[min(len(records), limit) - 1][0] if records else position
        return dict(items=items, hasMore=len(records) > limit, nextServerCursor=self.cursor(tx, owner, "events", end))

    def replay(self, tx, owner, scope, key, body, action):
        identifier = self.security.mac("idempotency", scope + ":" + key)
        content = self.security.mac("intent", canonical(body))
        record = tx.get(owner, "idempotency", identifier)
        if record:
            require(record["content"] == content, "IDEMPOTENCY_MISMATCH")
            return record["result"]
        result = action()
        tx.put(owner, "idempotency", identifier, dict(content=content, result=result))
        return result

    def confirm(self, tx, owner, identifier, body):
        record = self.security.pairing_record(tx, body["pairCode"], identifier)
        require(tx.auth_get("credential:" + record["verifier"]) is None, "REMOTE_PAIRING_CONFLICT")
        device = dict(record["device"], workerId=record["workerId"], status="offline", capabilityRevision=0,
                      observedAt=self.now(), pairedAt=self.now(), _frozen=False, _everConnected=False,
                      _challenge=identifier)
        self.save(tx, owner, "device", device["workerId"], device)
        tx.auth_put("credential:" + record["verifier"], dict(owner=owner, worker=device["workerId"]), owner)
        record.update(status="paired", owner=owner)
        tx.auth_put("challenge:" + identifier, record, owner)
        return self.view(owner, "device", device)

    def device_writable(self, tx, owner, worker):
        device = self.get(tx, owner, "device", worker)
        require(device["status"] != "revoked", "REMOTE_DEVICE_REVOKED")
        require(not device["_frozen"], "REMOTE_STORE_CHANGED")
        return device

    def create_conversation(self, tx, owner, body):
        device = self.device_writable(tx, owner, body["targetWorkerId"])
        require(device["workerStoreId"] == body["workerStoreId"], "REMOTE_TARGET_MISMATCH")
        catalog = self.get(tx, owner, "catalog", device["workerId"])
        require(catalog["workerStoreId"] == body["workerStoreId"], "REMOTE_STORE_CHANGED")
        require(any(w["workspaceId"] == body["workspaceId"] for w in catalog["workspaces"]), "NOT_FOUND")
        scene = next((s for s in catalog["scenes"] if s["sceneId"] == body["sceneId"]), None)
        require(scene is not None, "NOT_FOUND")
        require(scene["version"] == body["sceneVersion"], "REMOTE_SCENE_VERSION_MISMATCH")
        value = dict(body, conversationId=uid(), authority="remote", createdAt=self.now(), updatedAt=self.now(), _nextSeq=1)
        self.save(tx, owner, "conversation", value["conversationId"], value)
        result = self.view(owner, "conversation", value)
        self.event(tx, owner, "conversation.updated", result)
        return result

    def conversation(self, tx, owner, identifier):
        value = self.get(tx, owner, "conversation", identifier)
        require(value["authority"] == "remote", "CONVERSATION_AUTHORITY_MISMATCH")
        device = self.device_writable(tx, owner, value["targetWorkerId"])
        require(device["workerStoreId"] == value["workerStoreId"], "REMOTE_STORE_CHANGED")
        return value

    def deadline(self, requested, default, maximum):
        now = self.settings.clock()
        expires = seconds(requested) if requested else now + default
        require(now < expires <= now + maximum, "REMOTE_COMMAND_EXPIRED")
        return stamp(expires)

    def enqueue(self, tx, owner, conv, command_type, payload, expires, sequence=None, command_id=None):
        identifier = command_id or uid()
        frame = dict(type=command_type, commandId=identifier, conversationId=conv["conversationId"],
                     targetWorkerId=conv["targetWorkerId"], expectedWorkerStoreId=conv["workerStoreId"],
                     createdAt=self.now(), expiresAt=expires, payload=payload)
        if sequence is not None:
            frame["conversationSeq"] = sequence
        frame = wire.command(frame, revision=1)
        previous = tx.get(owner, "command", identifier)
        if previous:
            # The caller must preserve all immutable fields, including time, on retransmit.
            require(digest(previous["_frame"]) == digest(frame), "IDEMPOTENCY_MISMATCH")
            return previous["_receipt"]
        is_online = self.online(owner, conv["targetWorkerId"])
        delivery = "queued_online" if is_online else "queued_offline"
        receipt = dict(commandId=identifier, conversationId=conv["conversationId"], status="queued", deliveryState=delivery, workerOnline=is_online, expiresAt=expires)
        if sequence is not None:
            receipt["conversationSeq"] = sequence
        value = dict(receipt, targetWorkerId=conv["targetWorkerId"], type=command_type, withdrawalState="none",
                     observedAt=self.now(), createdAt=frame["createdAt"], _frame=frame, _receipt=receipt, _dispatch=False)
        self.save(tx, owner, "command", identifier, value)
        self.outbox(tx, owner, frame)
        self.command_event(tx, owner, value)
        return receipt

    def outbox(self, tx, owner, frame):
        identifier = frame["commandId"]
        kind = "skip" if frame["type"] == "conversation.skip" else "command"
        self.save(tx, owner, "outbox", kind + ":" + identifier,
                  dict(id=kind + ":" + identifier, _frame=frame, done=False, dispatching=False, **({"conversationId": frame["conversationId"]} if "conversationId" in frame else {})))
        self.notify(tx, owner, frame["targetWorkerId"])

    def send_message(self, tx, owner, conv_id, body):
        conv = self.conversation(tx, owner, conv_id)
        key = digest([conv_id, body["clientMessageId"]])
        previous = tx.get(owner, "message-intent", key)
        if previous:
            require(previous["content"] == digest(body), "IDEMPOTENCY_MISMATCH")
            return previous["receipt"]
        seq = conv["_nextSeq"]
        require(seq <= MAX_SEQ, "REMOTE_STORE_CHANGED")
        expires = self.deadline(body.get("expiresAt"), 86400, 7 * 86400)
        payload = {k: body[k] for k in ("clientMessageId", "text", "sessionMode")}
        payload.update({k: conv[k] for k in ("workspaceId", "sceneId", "sceneVersion")})
        receipt = self.enqueue(tx, owner, conv, "run.submit", payload, expires, seq)
        message = dict(messageId=uid(), conversationId=conv_id, role="user", text=body["text"], createdAt=self.now(), commandId=receipt["commandId"])
        self.save(tx, owner, "message", message["messageId"], dict(message, _worker=conv["targetWorkerId"], _store=conv["workerStoreId"]))
        self.event(tx, owner, "message.appended", message)
        conv.update(_nextSeq=seq + 1, updatedAt=self.now())
        self.save(tx, owner, "conversation", conv_id, conv)
        tx.put(owner, "message-intent", key, dict(content=digest(body), receipt=receipt), worker=conv["targetWorkerId"], store=conv["workerStoreId"], parent=conv_id)
        return receipt

    def control(self, tx, owner, identifier, body):
        run = tx.get(owner, "run", identifier) or tx.get(owner, "run-ref", identifier)
        require(run is not None, "NOT_FOUND")
        conv = self.conversation(tx, owner, run["conversationId"])
        require("nodeId" not in body or body["action"] == "retry")
        payload = dict(runId=identifier, **{k: v for k, v in body.items() if k in {"nodeId", "reason"}})
        return self.enqueue(tx, owner, conv, "run." + body["action"], payload, self.deadline(body.get("expiresAt"), 300, 900))

    def approval(self, tx, owner, identifier, body):
        value = self.get(tx, owner, "approval", identifier)
        conv = self.conversation(tx, owner, value["_conversation"])
        require(value["status"] == "pending" and seconds(value["expiresAt"]) > self.settings.clock(), "REMOTE_COMMAND_EXPIRED")
        catalog = self.get(tx, owner, "catalog", conv["targetWorkerId"])
        run = self.get(tx, owner, "run", value["resultRef"]["runId"])
        require(run["status"] not in {"succeeded", "failed", "cancelled"}, "REMOTE_APPROVAL_FORBIDDEN")
        if body["decision"] == "approve":
            require(value["remoteApprovalAllowed"] and value["action"] not in BLOCKED | set(catalog["remotelyBlockedActions"]), "REMOTE_APPROVAL_FORBIDDEN")
            require(value["action"] != "shell" and value["riskLevel"] not in {"high", "critical"}, "REMOTE_APPROVAL_FORBIDDEN")
        previous = tx.get(owner, "approval-intent", identifier)
        if previous:
            require(previous["content"] == digest(body), "IDEMPOTENCY_MISMATCH")
            return previous["receipt"]
        expires = stamp(min(self.settings.clock() + 300, seconds(value["expiresAt"])))
        payload = dict(body, runId=value["resultRef"]["runId"], approvalId=identifier)
        receipt = self.enqueue(tx, owner, conv, "approval.decide", payload, expires)
        tx.put(owner, "approval-intent", identifier, dict(content=digest(body), receipt=receipt), worker=conv["targetWorkerId"], store=conv["workerStoreId"], parent=conv["conversationId"])
        return receipt

    def reject_undispatched(self, tx, owner, value, code):
        require(not value["_dispatch"] and value["status"] == "queued")
        value.update(status="rejected", observedAt=self.now(), error=Fault(code).view())
        self.save(tx, owner, "command", value["commandId"], value)
        box = self.get(tx, owner, "outbox", "command:" + value["commandId"])
        box["done"] = True
        self.save(tx, owner, "outbox", box["id"], box)
        if "conversationSeq" in value:
            skip = wire.encode(dict(type="conversation.skip", commandId=value["commandId"], conversationId=value["conversationId"],
                                    conversationSeq=value["conversationSeq"], targetWorkerId=value["targetWorkerId"],
                                    expectedWorkerStoreId=value["_frame"]["expectedWorkerStoreId"],
                                    reason="expired_before_dispatch" if code == "REMOTE_COMMAND_EXPIRED" else "withdrawn_before_dispatch", recordedAt=self.now()), revision=1)
            self.outbox(tx, owner, skip)
        self.command_event(tx, owner, value)
        self.notify(tx, owner, value["targetWorkerId"])

    def withdraw(self, tx, owner, identifier, body):
        value = self.get(tx, owner, "command", identifier)
        require(value["type"] == "run.submit" and "resultRef" not in value and value["status"] not in TERMINAL, "REMOTE_WITHDRAWAL_TOO_LATE")
        conv = self.conversation(tx, owner, value["conversationId"])
        if not value["_dispatch"]:
            value["withdrawalState"] = "confirmed"
            self.reject_undispatched(tx, owner, value, "REMOTE_COMMAND_WITHDRAWN")
        elif value["withdrawalState"] == "none":
            payload = dict(targetCommandId=identifier, targetConversationSeq=value["conversationSeq"], **body)
            receipt = self.enqueue(tx, owner, conv, "command.withdraw", payload, self.deadline(None, 300, 300))
            value.update(withdrawalState="requested", withdrawalCommandId=receipt["commandId"], observedAt=self.now())
            self.save(tx, owner, "command", identifier, value)
            self.command_event(tx, owner, value)
        return self.view(owner, "command", value)

    def revoke(self, tx, owner, worker):
        self.notify(tx, owner, worker)
        device = self.get(tx, owner, "device", worker)
        if device["status"] != "revoked":
            device.update(status="revoked", revokedAt=self.now(), version=device.get('version', 1) + 1)
            self.save(tx, owner, "device", worker, device, management=True)
            challenge = tx.auth_get("challenge:" + device["_challenge"])
            challenge["status"] = "revoked"
            tx.auth_put("challenge:" + device["_challenge"], challenge, owner)
            for value in tx.list(owner, "command", worker=worker):
                if value["status"] not in TERMINAL:
                    if not value["_dispatch"]:
                        self.reject_undispatched(tx, owner, value, "REMOTE_DEVICE_REVOKED")
                    else:
                        value["deliveryState"] = "reconciliation_required"
                        self.save(tx, owner, "command", value["commandId"], value)
                        self.command_event(tx, owner, value)
        return dict(workerId=worker, revokedAt=device["revokedAt"], status="revoked", executionMayStillBeRunning=True)

    def expire(self, tx, owner, worker):
        for value in tx.queued_due(owner, worker, self.settings.clock()):
            if value["status"] == "queued" and seconds(value["expiresAt"]) <= self.settings.clock():
                if not value["_dispatch"]:
                    self.reject_undispatched(tx, owner, value, "REMOTE_COMMAND_EXPIRED")
                elif value["deliveryState"] != "reconciliation_required":
                    value["deliveryState"] = "reconciliation_required"
                    self.save(tx, owner, "command", value["commandId"], value)
                    self.command_event(tx, owner, value)

    def maintain(self):
        """Low-frequency expiry/retention work; never invoked by HTTP handlers."""
        if hasattr(self,'attachments'):self.attachments.maintain()
        now = self.settings.clock()
        with self.repo.transaction() as tx:
            tx.cleanup_auth(now)
            for account in tx.auth_list("account:"):
                owner = account["owner"]
                tx.cleanup_owner(owner, now - self.settings.browser_retention_seconds)
                for worker in tx.due_workers(owner, now):
                    self.expire(tx, owner, worker)

    def freeze(self, tx, owner, device, code):
        self.notify(tx, owner, device["workerId"])
        device.update(_frozen=True, _freezeCode=code, status="reconciliation_required")
        self.save(tx, owner, "device", device["workerId"], device)
        for value in tx.list(owner, "command", worker=device["workerId"]):
            if value["status"] not in TERMINAL:
                value["deliveryState"] = "reconciliation_required"
                self.save(tx, owner, "command", value["commandId"], value)
                self.command_event(tx, owner, value)

    def snapshot(self, tx, owner, identifier):
        conv = self.get(tx, owner, "conversation", identifier)
        result = dict(conversation=self.view(owner, "conversation", conv), serverCursor=self.cursor(tx, owner, "events", tx.browser_tail(owner)), observedAt=self.now(), hasMore=False)
        for plural, kind in (("runs", "run"), ("commands", "command"), ("messages", "message")):
            items = tx.list(owner, kind, parent=identifier, limit=101)
            result[plural] = [self.view(owner, kind, item) for item in items[:100]]
            result["hasMore"] |= len(items) > 100
        approvals = tx.pending_approvals(owner, conv["targetWorkerId"], conv["workerStoreId"], identifier, result["observedAt"])
        result["approvals"] = [self.view(owner, "approval", value) for value in approvals[:100]]
        result["hasMore"] |= len(approvals) > 100
        return result
