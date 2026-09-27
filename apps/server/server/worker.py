import asyncio
from dataclasses import dataclass, field

from starlette.websockets import WebSocketDisconnect
from starlette.responses import JSONResponse
from protocol.generated.python import PROTOCOL_VERSION

from .common import Fault, require, uid, validated
from . import wire

HELLO_TIMEOUT = 10
FALLBACK_INTERVAL = 5


def cancel_task(task):
    """Cancel owned waiters without replacing an ASGI cancellation during teardown."""
    task.cancel()
    task.add_done_callback(lambda finished: None if finished.cancelled() else finished.exception())


@dataclass
class Connection:
    socket: object
    owner: str
    worker: str
    store: str
    epoch: str
    identifier: str
    last_seen: float
    revision: int = wire.CURRENT
    closed: bool = False
    busy_fresh: bool = False
    replay: list = field(default_factory=list)
    wakeup: asyncio.Event = field(default_factory=asyncio.Event)
    loop: object = field(default_factory=asyncio.get_running_loop, repr=False)

    def wake(self):
        # HTTP/tests may commit from another thread; schedule on this connection's loop.
        try:
            self.loop.call_soon_threadsafe(self.wakeup.set)
        except RuntimeError:
            pass  # loop already closed; reconnect performs initial durable delivery

    async def close(self, code):
        self.closed = True
        self.wake()
        try:
            await self.socket.close(code=code)
        except (RuntimeError, WebSocketDisconnect):
            pass


class WorkerTransport:
    def __init__(self, service, events):
        self.s, self.events = service, events

    def hello(self, tx, owner, device, frame, connection_id):
        require(frame["type"] == "worker.hello", "REMOTE_PROTOCOL_UNSUPPORTED")
        require(frame["workerId"] == device["workerId"], "REMOTE_DEVICE_AUTH_FAILED")
        require(frame["platform"] == device["platform"] and frame["architecture"] == device["architecture"], "REMOTE_TARGET_MISMATCH")
        store = frame["workerStoreId"]
        changed = store != device["workerStoreId"]
        position = tx.get(owner, "event-position", frame["workerId"] + ":" + store) or {"seq": 0}
        ack = frame["lastServerAck"]
        bad_ack = bool(ack and (ack["workerStoreId"] != store or ack["seq"] > position["seq"]))
        if not changed and device.get("_lastReportedAck", 0) > (ack["seq"] if ack else 0):
            bad_ack = True
        if changed:
            self.s.freeze(tx, owner, device, "REMOTE_STORE_CHANGED")
            device["workerStoreId"] = store
            device["_lastReportedAck"] = 0
            bad_ack |= ack is not None
        if bad_ack:
            self.s.freeze(tx, owner, device, "REMOTE_ACK_CONFLICT")
        device.update(_everConnected=True, _epoch=frame["workerEpoch"], capabilityRevision=frame["capabilityRevision"], lastSeenAt=self.s.now())
        if ack and not bad_ack:
            device["_lastReportedAck"] = ack["seq"]
        if hasattr(self.s, 'on_hello'):
            self.s.on_hello(tx, owner, device, frame, connection_id)
        self.s.save(tx, owner, "device", device["workerId"], device)
        result = dict(type="worker.hello_ack", connectionId=connection_id, workerId=device["workerId"], workerStoreId=store,
                      workerEpoch=frame["workerEpoch"], commandDelivery="frozen" if device["_frozen"] else "ready",
                      lastServerAck=dict(workerStoreId=store, seq=position["seq"]),
                      pendingCommandCursor=self.s.cursor(tx, owner, "worker:" + device["workerId"] + ":" + store, 0),
                      heartbeatIntervalSeconds=15, offlineAfterSeconds=45, serverTime=self.s.now())
        if device["_frozen"]:
            result["reason"] = Fault(device["_freezeCode"]).view()
        return wire.encode(result, wire.revision(frame))

    def fence_check(self, tx, connection):
        require(self.s.connections.get((connection.owner, connection.worker)) is connection and not connection.closed, "REMOTE_EPOCH_STALE")
        device = self.s.get(tx, connection.owner, "device", connection.worker)
        require(device["status"] != "revoked", "REMOTE_DEVICE_REVOKED")
        require(device["workerStoreId"] == connection.store and device.get("_epoch") == connection.epoch, "REMOTE_EPOCH_STALE")
        return device

    def deliver(self, tx, connection, sent):
        device = self.fence_check(tx, connection)
        self.s.expire(tx, connection.owner, connection.worker)
        if device["_frozen"]:
            return []
        boxes = tx.pending_outbox(connection.owner, connection.worker, connection.store)
        # Stable per-conversation slot ordering even if a skip was created later.
        boxes.sort(key=lambda b: (b["conversationId"], b["_frame"].get("conversationSeq", 0), b["id"]))
        frames = [("replay:" + f["commandId"], f) for f in connection.replay[:16]]
        del connection.replay[:16]
        for box in boxes:
            if len(frames) >= 16:
                break  # consume incoming heartbeats between bounded delivery batches
            if box["done"] or box["id"] in sent:
                continue
            frame = box["_frame"]
            if frame['wireRevision'] != connection.revision:
                continue
            box["dispatching"] = True
            self.s.save(tx, connection.owner, "outbox", box["id"], box)
            if frame["type"] not in {"conversation.skip", "command.delivery_granted"}:
                command = self.s.get(tx, connection.owner, "command", frame["commandId"])
                if command["status"] != "queued":
                    continue
                command.update(_dispatch=True, observedAt=self.s.now())
                if command.get('_granted'):
                    command['deliveryState'] = 'granted'
                elif command["deliveryState"] != "reconciliation_required":
                    command["deliveryState"] = "awaiting_receipt" if connection.revision == 2 else "sent"
                self.s.save(tx, connection.owner, "command", command["commandId"], command)
                self.s.command_event(tx, connection.owner, command)
            frames.append((box["id"], frame))
        return frames

    async def run(self, socket):
        connection = None
        accepted = False
        receiving = None
        negotiated = 1
        try:
            self.s.security.rate("device-auth:" + (socket.client.host if socket.client else "unknown"))
            require(socket.url.scheme == "wss", "REMOTE_DEVICE_AUTH_FAILED")
            require(not socket.url.query, "REMOTE_DEVICE_AUTH_FAILED")
            _, verifier = self.s.security.bearer(socket.headers.get("authorization"))
            with self.s.repo.transaction() as tx:
                owner, device = self.s.security.device_identity(tx, verifier)
            await socket.accept()
            accepted = True
            raw = await asyncio.wait_for(socket.receive_text(), timeout=HELLO_TIMEOUT)
            negotiated = wire.offered(raw)
            hello = wire.decode(raw)
            identifier = uid()
            with self.s.repo.transaction() as tx:
                owner, device = self.s.security.device_identity(tx, verifier)
                response = self.hello(tx, owner, device, hello, identifier)
            connection = Connection(socket, owner, device["workerId"], hello["workerStoreId"], hello["workerEpoch"], identifier, self.s.settings.monotonic(), wire.revision(hello))
            old = self.s.connections.get((owner, connection.worker))
            self.s.connections[(owner, connection.worker)] = connection
            if old:
                await old.close(4409)
            await socket.send_json(response)
            sent = set()
            connection.wakeup.set()
            receiving = asyncio.create_task(socket.receive_text())
            next_fallback = self.s.settings.monotonic() + FALLBACK_INTERVAL
            while not connection.closed:
                require(self.s.settings.monotonic() - connection.last_seen < 45, "REMOTE_DEVICE_OFFLINE")
                if self.s.settings.monotonic() >= next_fallback:
                    connection.wakeup.set()
                    next_fallback = self.s.settings.monotonic() + FALLBACK_INTERVAL
                if connection.wakeup.is_set():
                    connection.wakeup.clear()
                    with self.s.repo.transaction() as tx:
                        frames = self.deliver(tx, connection, sent)
                    for box_id, frame in frames:
                        require(self.s.connections.get((owner, connection.worker)) is connection and not connection.closed, "REMOTE_EPOCH_STALE")
                        remaining = max(0.01, 45 - (self.s.settings.monotonic() - connection.last_seen))
                        await asyncio.wait_for(socket.send_json(wire.encode(frame, connection.revision)), timeout=remaining)
                        sent.add(box_id)
                    if len(frames) == 16:
                        connection.wakeup.set()  # continue bounded batches without a timer delay
                waking = asyncio.create_task(connection.wakeup.wait())
                try:
                    remaining = max(0, 45 - (self.s.settings.monotonic() - connection.last_seen))
                    until_fallback = max(0, next_fallback - self.s.settings.monotonic())
                    done, _ = await asyncio.wait({receiving, waking}, timeout=min(until_fallback, remaining), return_when=asyncio.FIRST_COMPLETED)
                finally:
                    cancel_task(waking)
                if not done:
                    connection.wakeup.set()  # expiry/missed-notification fallback, at most once per 5s
                    next_fallback = self.s.settings.monotonic() + FALLBACK_INTERVAL
                if receiving not in done:
                    continue
                raw = receiving.result()
                receiving = asyncio.create_task(socket.receive_text())
                frame = wire.decode(raw, connection.revision)
                freeze_fault = None
                with self.s.repo.transaction() as tx:
                    device = self.fence_check(tx, connection)
                    require(frame.get("workerId") == connection.worker and frame.get("workerStoreId") == connection.store, "REMOTE_TARGET_MISMATCH")
                    if frame["type"] == "worker.heartbeat":
                        require(frame["connectionId"] == identifier and frame["workerEpoch"] == connection.epoch, "REMOTE_EPOCH_STALE")
                        ack = frame["lastServerAck"]
                        position = tx.get(owner, "event-position", connection.worker + ":" + connection.store) or {"seq": 0}
                        if (ack and (ack["workerStoreId"] != connection.store or ack["seq"] > position["seq"])) or (ack["seq"] if ack else 0) < device.get("_lastReportedAck", 0):
                            self.s.freeze(tx, owner, device, "REMOTE_ACK_CONFLICT")
                            freeze_fault = Fault("REMOTE_ACK_CONFLICT")
                        else:
                            device["_lastReportedAck"] = ack["seq"] if ack else 0
                        answer = dict(type="server.heartbeat", connectionId=identifier, receivedAt=self.s.now())
                    elif frame["type"] == "conversation.gap":
                        require(frame["workerEpoch"] == connection.epoch, "REMOTE_EPOCH_STALE")
                        conv = self.s.get(tx, owner, "conversation", frame["conversationId"])
                        require(conv["targetWorkerId"] == connection.worker and conv["workerStoreId"] == connection.store, "REMOTE_TARGET_MISMATCH")
                        require(frame["expectedSeq"] < frame["receivedSeq"], "REMOTE_SEQUENCE_GAP")
                        for box in tx.list(owner, "outbox", worker=connection.worker, store=connection.store, parent=frame["conversationId"]):
                            seq = box["_frame"].get("conversationSeq")
                            if seq and frame["expectedSeq"] <= seq < frame["receivedSeq"]:
                                original = self.s.get(tx, owner, "command", box["_frame"]["commandId"])
                                if box["_frame"]["type"] == "conversation.skip" or original["_dispatch"]:
                                    connection.replay.append(box["_frame"])
                                else:
                                    sent.discard(box["id"])
                        self.s.notify(tx, owner, connection.worker)
                        answer = None
                    else:
                        require("eventId" in frame or frame['type'] == 'sync.content.redaction', "REMOTE_PROTOCOL_UNSUPPORTED")
                        if connection.revision == 2:
                            position = self.events.accept(tx, owner, frame, connection, encoded_bytes=len(raw.encode()))
                        else:
                            position = self.events.accept(tx, owner, frame)
                        device = self.s.get(tx, owner, "device", connection.worker)
                        answer = dict(type="worker.events_ack", connectionId=identifier, workerId=connection.worker, position=position)
                    connection.last_seen = self.s.settings.monotonic()
                    device["lastSeenAt"] = self.s.now()
                    self.s.save(tx, owner, "device", connection.worker, device)
                if freeze_fault:
                    raise freeze_fault
                if answer:
                    await socket.send_json(wire.encode(answer, connection.revision))
        except Fault as exc:
            if not accepted and "websocket.http.response" in socket.scope.get("extensions", {}):
                headers = {"Cache-Control": "no-store"}
                if exc.code == "REMOTE_RATE_LIMITED":
                    headers["Retry-After"] = str(self.s.settings.rate_window)
                envelope = validated("ApiEnvelope", dict(success=False, requestId=uid(), protocolVersion=PROTOCOL_VERSION, error=exc.view()))
                await socket.send_denial_response(JSONResponse(envelope, status_code=exc.status, headers=headers))
                return
            if accepted and (connection is None or not connection.closed):
                try:
                    await socket.send_json(wire.encode(dict(type="worker.hello_rejected", error=exc.view()), connection.revision if connection else negotiated))
                except (RuntimeError, WebSocketDisconnect):
                    pass
            code = 1009 if exc.code == "REMOTE_FRAME_TOO_LARGE" else (4401 if exc.status == 401 else 4403 if exc.status == 403 else 4409)
            if connection:
                await connection.close(code)
            else:
                await socket.close(code=code)
        except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError, KeyError, ValueError):
            if connection:
                await connection.close(4409)
            elif accepted:
                await socket.close(code=4409)
        except Exception:
            # Never let a DB/transport exception render raw request data or headers.
            if connection:
                await connection.close(1011)
            elif accepted:
                await socket.close(code=1011)
        finally:
            if receiving:
                cancel_task(receiving)
            if connection:
                connection.closed = True
                if self.s.connections.get((connection.owner, connection.worker)) is connection:
                    del self.s.connections[(connection.owner, connection.worker)]
