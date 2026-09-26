"""Validate immutable Worker facts, then project a contiguous prefix atomically."""
from .common import MAX_SEQ, Fault, digest, require, seconds, validated
from .service import TERMINAL


class Events:
    def __init__(self, service):
        self.s = service

    def references(self, tx, owner, event, *, applying=False):
        worker, store = event["workerId"], event["workerStoreId"]
        conv_id = event.get("conversationId")
        if conv_id:
            conv = self.s.get(tx, owner, "conversation", conv_id)
            require(conv["targetWorkerId"] == worker and conv["workerStoreId"] == store, "REMOTE_TARGET_MISMATCH")
            require(conv["authority"] == "remote", "CONVERSATION_AUTHORITY_MISMATCH")
        if event.get("commandId"):
            command = self.s.get(tx, owner, "command", event["commandId"])
            require(command["targetWorkerId"] == worker and command["_frame"]["expectedWorkerStoreId"] == store and command["conversationId"] == conv_id, "REMOTE_TARGET_MISMATCH")
            if event["type"] != "conversation.skip_recorded":
                require(command["_dispatch"], "REMOTE_EVENT_CONFLICT")
        payload = event.get("payload", {})
        for key, expected in (("conversationId", conv_id), ("workerId", worker), ("workerStoreId", store)):
            if key in payload:
                require(payload[key] == expected, "REMOTE_TARGET_MISMATCH")
        if payload.get("commandId"):
            command = self.s.get(tx, owner, "command", payload["commandId"])
            require(command["conversationId"] == conv_id and command["targetWorkerId"] == worker and command["_frame"]["expectedWorkerStoreId"] == store, "REMOTE_TARGET_MISMATCH")
        refs = [event.get("resultRef"), payload.get("resultRef")]
        if payload.get("runId"):
            refs.append({"runId": payload["runId"], **({"executionTaskId": payload["executionTaskId"]} if "executionTaskId" in payload else {})})
        for ref in filter(None, refs):
            run = tx.get(owner, "run", ref["runId"]) or tx.get(owner, "run-ref", ref["runId"])
            if run:
                require(run["conversationId"] == conv_id and run["_worker"] == worker and run["_store"] == store, "REMOTE_TARGET_MISMATCH")
                if ref.get("executionTaskId") and run.get("executionTaskId"):
                    require(ref["executionTaskId"] == run["executionTaskId"], "REMOTE_TARGET_MISMATCH")
            elif applying and event["type"] not in {"command.accepted", "command.completed", "run.state_changed"}:
                raise Fault("NOT_FOUND")

    def accept(self, tx, owner, event):
        self.references(tx, owner, event)
        first, last = event.get("firstSeq", event["seq"]), event["seq"]
        require(first <= last <= MAX_SEQ, "REMOTE_EVENT_CONFLICT")
        previous = tx.event_id(owner, event["eventId"])
        if previous:
            require(digest(previous) == digest(event), "REMOTE_EVENT_CONFLICT")
        else:
            require(not tx.overlaps(owner, event["workerId"], event["workerStoreId"], first, last), "REMOTE_EVENT_CONFLICT")
            tx.event_put(owner, event)
        key = event["workerId"] + ":" + event["workerStoreId"]
        position = tx.get(owner, "event-position", key) or {"seq": 0}
        while True:
            next_event = tx.next_event(owner, event["workerId"], event["workerStoreId"], position["seq"] + 1)
            if next_event is None:
                break
            self.references(tx, owner, next_event, applying=True)
            self.project(tx, owner, next_event)
            tx.event_applied(owner, next_event["eventId"])
            position["seq"] = next_event["seq"]
        tx.put(owner, "event-position", key, position, worker=event["workerId"], store=event["workerStoreId"])
        return dict(workerStoreId=event["workerStoreId"], seq=position["seq"])

    def finish_matrix(self, command, event):
        kind, result = command["type"], event.get("resultStatus")
        ref, control = event.get("resultRef"), event.get("controlResult")
        expected = {"run.submit": {"succeeded", "cancelled"}, "run.pause": {"confirmed"},
                    "run.resume": {"confirmed"}, "run.cancel": {"confirmed"},
                    "run.retry": {"retry_enqueued"}, "approval.decide": {"approval_consumed"},
                    "command.withdraw": {"withdrawn", "confirmed"}}
        require(result in expected[kind], "REMOTE_EVENT_CONFLICT")
        if kind != "command.withdraw" or result != "withdrawn":
            require(ref is not None, "REMOTE_EVENT_CONFLICT")
        if kind == "run.retry":
            require(bool(ref.get("executionTaskId")), "REMOTE_EVENT_CONFLICT")
        if kind in {"run.pause", "run.resume", "run.cancel", "command.withdraw"}:
            require(control is not None and control["outcome"] == "confirmed", "REMOTE_EVENT_CONFLICT")
            evidence = {"run.pause": {"node_boundary_paused"}, "run.resume": {"supervisor_resumed"},
                        "run.cancel": {"adapter_confirmed", "already_terminal"},
                        "command.withdraw": {"inbox_tombstone"} if result == "withdrawn" else {"adapter_confirmed", "already_terminal"}}
            require(control["evidence"] in evidence[kind], "REMOTE_EVENT_CONFLICT")
            if kind in {"run.cancel", "command.withdraw"}:
                require(not control["executionMayStillBeRunning"] and not control["orphanProcessIds"], "REMOTE_EVENT_CONFLICT")

    def project(self, tx, owner, event):
        kind = event["type"]
        if kind == "events.omitted":
            return
        if kind == "capability.changed":
            payload = event["payload"]
            for collection, key in (("workspaces", "workspaceId"), ("scenes", "sceneId")):
                require(len({item[key] for item in payload[collection]}) == len(payload[collection]), "REMOTE_EVENT_CONFLICT")
            old = tx.get(owner, "catalog", event["workerId"])
            if old and old["workerStoreId"] == event["workerStoreId"]:
                require(payload["capabilityRevision"] > old["capabilityRevision"] or payload == old, "REMOTE_EVENT_CONFLICT")
            self.s.save(tx, owner, "catalog", event["workerId"], payload)
            device = self.s.get(tx, owner, "device", event["workerId"])
            device["capabilityRevision"] = payload["capabilityRevision"]
            self.s.save(tx, owner, "device", event["workerId"], device)
        elif kind.startswith("command."):
            self.command(tx, owner, event)
        elif kind == "run.state_changed":
            command = self.s.get(tx, owner, "command", event["commandId"])
            payload = event["payload"]
            if "resultRef" not in command:
                require(command["type"] == "run.submit" and command["status"] in {"accepted", "completed", "failed"}, "REMOTE_TARGET_MISMATCH")
                command["resultRef"] = {k: payload[k] for k in ("runId", "executionTaskId", "parentExecutionTaskId") if k in payload}
                self.s.save(tx, owner, "command", command["commandId"], command)
            require(command["resultRef"]["runId"] == payload["runId"], "REMOTE_TARGET_MISMATCH")
            known_task = command["resultRef"].get("executionTaskId")
            require(not known_task or payload.get("executionTaskId") == known_task, "REMOTE_TARGET_MISMATCH")
            view = dict(payload, workerOnline=False, _worker=event["workerId"], _store=event["workerStoreId"])
            self.s.save(tx, owner, "run", payload["runId"], view)
        elif kind == "message.appended":
            payload = event["payload"]
            old = tx.get(owner, "message", payload["messageId"])
            require(old is None or self.s.view(owner, "message", old) == payload, "REMOTE_EVENT_CONFLICT")
            self.s.save(tx, owner, "message", payload["messageId"], dict(payload, _worker=event["workerId"], _store=event["workerStoreId"]))
        elif kind == "approval.state_changed":
            payload = event["payload"]
            require(seconds(payload["expiresAt"]) > seconds(payload["requestedAt"]), "REMOTE_EVENT_CONFLICT")
            old = tx.get(owner, "approval", payload["approvalId"])
            if old:
                require(old["_conversation"] == event["conversationId"] and old["resultRef"] == payload["resultRef"], "REMOTE_TARGET_MISMATCH")
                require(old["status"] == "pending" or old["status"] == payload["status"], "REMOTE_EVENT_CONFLICT")
            self.s.save(tx, owner, "approval", payload["approvalId"], dict(payload, _worker=event["workerId"], _store=event["workerStoreId"], _conversation=event["conversationId"]))
        elif kind == "conversation.skip_recorded":
            box = self.s.get(tx, owner, "outbox", "skip:" + event["commandId"])
            require(box["_frame"]["conversationSeq"] == event["conversationSeq"], "REMOTE_EVENT_CONFLICT")
            box["done"] = True
            self.s.save(tx, owner, "outbox", box["id"], box)
        elif kind == "run.progress":
            self.s.get(tx, owner, "run", event["resultRef"]["runId"])
        self.s.event(tx, owner, "worker.event", validated("RemoteVisibleWorkerEvent", event))

    def command(self, tx, owner, event):
        value = self.s.get(tx, owner, "command", event["commandId"])
        kind = event["type"]
        require(value["status"] not in TERMINAL, "REMOTE_EVENT_CONFLICT")
        payload = value["_frame"]["payload"]
        ref = event.get("resultRef")
        previous_ref = value.get("resultRef")
        if ref and previous_ref and not (value["type"] == "run.retry" and kind == "command.completed"):
            for field in ("runId", "executionTaskId"):
                if field in previous_ref:
                    require(ref.get(field) == previous_ref[field], "REMOTE_TARGET_MISMATCH")
        if ref and "runId" in payload and not (value["type"] == "run.retry" and kind == "command.completed"):
            require(ref["runId"] == payload["runId"], "REMOTE_TARGET_MISMATCH")
        if kind == "command.completed":
            require(value["status"] == "accepted", "REMOTE_EVENT_CONFLICT")
            self.finish_matrix(value, event)
            value["status"] = "completed"
        elif kind == "command.accepted":
            require(value["status"] == "queued", "REMOTE_EVENT_CONFLICT")
            value["status"] = "accepted"
        elif kind == "command.rejected":
            require(value["status"] == "queued", "REMOTE_EVENT_CONFLICT")
            value["status"] = "rejected"
        elif kind == "command.failed":
            require(value["status"] == "accepted", "REMOTE_EVENT_CONFLICT")
            value["status"] = "failed"
        elif kind == "command.control_result":
            require(value["status"] == "accepted", "REMOTE_EVENT_CONFLICT")
            if value["type"] != "command.withdraw":
                require(ref is not None and "executionStatus" in event, "REMOTE_EVENT_CONFLICT")
        control = event.get("controlResult")
        if control:
            if control["outcome"] == "rejected" and control["evidence"] == "adapter_refused":
                require(control["executionMayStillBeRunning"], "REMOTE_EVENT_CONFLICT")
            if value["type"] == "run.cancel" and control["outcome"] == "confirmed":
                require(not control["executionMayStillBeRunning"] and not control["orphanProcessIds"], "REMOTE_EVENT_CONFLICT")
        for field in ("resultRef", "resultStatus", "controlResult", "error"):
            if field in event:
                value[field] = event[field]
        value.update(deliveryState="acknowledged", observedAt=self.s.now())
        self.s.save(tx, owner, "command", value["commandId"], value)
        box = self.s.get(tx, owner, "outbox", "command:" + value["commandId"])
        box["done"] = True
        self.s.save(tx, owner, "outbox", box["id"], box)
        if ref:
            old = tx.get(owner, "run", ref["runId"]) or tx.get(owner, "run-ref", ref["runId"])
            if old is None:
                require(value["type"] in {"run.submit", "run.retry", "command.withdraw"}, "REMOTE_TARGET_MISMATCH")
                # Binding a reference is NOT evidence for an execution status. Only
                # run.state_changed creates the browser Run projection.
                self.s.save(tx, owner, "run-ref", ref["runId"], dict(ref, conversationId=value["conversationId"], _worker=event["workerId"], _store=event["workerStoreId"]))
        if value["type"] == "command.withdraw" and kind in {"command.completed", "command.failed", "command.control_result", "command.rejected"}:
            original = self.s.get(tx, owner, "command", payload["targetCommandId"])
            original["withdrawalState"] = "confirmed" if kind == "command.completed" else ("denied" if kind in {"command.failed", "command.rejected"} else "requested")
            if kind == "command.completed" and event["resultStatus"] == "withdrawn":
                require(original["status"] == "queued", "REMOTE_EVENT_CONFLICT")
                original.update(status="rejected", error=Fault("REMOTE_COMMAND_WITHDRAWN").view())
                original_box = self.s.get(tx, owner, "outbox", "command:" + original["commandId"])
                original_box["done"] = True
                self.s.save(tx, owner, "outbox", original_box["id"], original_box)
            self.s.save(tx, owner, "command", original["commandId"], original)
            self.s.command_event(tx, owner, original)
