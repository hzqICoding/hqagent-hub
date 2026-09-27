from __future__ import annotations

import asyncio
import json
import logging
import random
import time

from websockets.asyncio.client import connect
from protocol.generated.python import PROTOCOL_VERSION
from core.errors import HubError
from storage.local_chat import now
from runtime.remote.link import machine
from runtime.remote.security import normalize_origin
from runtime.remote.wire import WIRE_REVISION, MAX_FRAME_BYTES, encode, decode
from runtime.remote.projection import Projector
from runtime.remote.busy import BusyState
from runtime.remote.delivery import DeliveryBridge
from runtime.remote.sync import SyncService
from runtime.remote.window import SendWindow


class Renegotiate(Exception):
    """Close the current transport without treating an upgrade probe as failure."""


class NoRedirectConnect(connect):
    def process_redirect(self, exc):
        # Never forward the device credential to a redirect target.
        return exc


class RemoteWorker:
    def __init__(self, repository, link, bridge, *, connector=None, retry_seconds=1.0):
        self.repo, self.link, self.bridge = repository, link, bridge
        self.projector = Projector(bridge)
        self.busy = BusyState(repository, bridge.chat)
        self.sync = SyncService(repository, bridge.chat, link, self.busy)
        self.delivery = DeliveryBridge(repository, bridge.chat, link, self.busy, self.sync)
        bridge.chat.repository.busy_state = self.busy
        self.probe_revision2 = True
        self.peer_revision2 = None
        self.revision_probe_seconds = 30
        self.next_revision2_probe = 0.0
        self.connector = connector or NoRedirectConnect
        self.retry_seconds = retry_seconds
        self.job = None
        self.expiry_job = None
        self.socket = None
        self.closed = False
        self.link.disconnect = self.disconnect
        self.link.before_clear = self.sync.discard_binding
        # websockets DEBUG includes request headers. Isolate the transport logger
        # from application handlers, including applications enabling root DEBUG.
        self.logger = logging.Logger("remote.transport.silent", level=logging.CRITICAL + 1)
        self.logger.addHandler(logging.NullHandler())
        self.logger.propagate = False

    async def start(self):
        if self.job is not None:
            return
        self.repo.boot()
        self.delivery.clock.invalidate()
        self.busy.connection_id = None
        if self.sync.active():
            self.repo.source_mapper = self.sync.source_event
        # Startup cannot depend on a successful socket or wait behind connect
        # timeout/backoff. Only ungranted receipts are rejected here.
        await self.delivery.expire_pending(recovery=True)
        self.probe_revision2 = True
        self.peer_revision2 = None
        self.closed = False
        self.expiry_job = asyncio.create_task(self.expire_reservations())
        self.job = asyncio.create_task(self.run())

    async def stop(self):
        self.closed = True
        if self.expiry_job:
            self.expiry_job.cancel()
            await asyncio.gather(self.expiry_job, return_exceptions=True)
            self.expiry_job = None
        await self.disconnect()
        if self.job:
            self.job.cancel()
            await asyncio.gather(self.job, return_exceptions=True)
            self.job = None
        await self.bridge.cancel_executions()
        await self.delivery.cancel_executions()
        self.delivery.clock.invalidate()
        self.state("offline")

    async def expire_reservations(self):
        # This task belongs to the Worker lifecycle, not to any connection.
        # Unlink/revocation/reset reuse it: no matching pending rows is a no-op.
        while not self.closed:
            await asyncio.sleep(1)
            try:
                await self.delivery.expire_pending()
            except Exception:
                # Retry transient storage failures without reflecting command
                # bodies, transport headers or credential-bearing exceptions.
                logging.getLogger(__name__).error("远程送达预留清理暂未完成，将重试")

    async def disconnect(self):
        if self.socket:
            await self.socket.close()

    def state(self, status, *, code=None, connected=False, frozen=False, revoked=False, generation=None):
        with self.repo.database.transaction() as tx:
            link = self.repo.get("link", tx)
            if generation is not None and generation != link["generation"]:
                return
            view = link["view"]
            if view["state"] not in {"paired", "frozen", "revoked"}:
                return
            view.update(connectionStatus=status)
            if connected:
                view["lastConnectedAt"] = now()
            if frozen:
                view["state"] = "frozen"
            if revoked:
                view.update(state="revoked", connectionStatus="offline")
            if code:
                view["lastErrorCode"] = code
            elif connected and not frozen:
                view.pop("lastErrorCode", None)
            self.repo.set_view(tx, view)
            self.repo.seal(tx)
        if revoked and self.sync.active():
            self.sync.revoked()

    def can_upgrade(self):
        identity = self.repo.get("identity")
        if identity.get("wireRevision", 1) != 1:
            return False
        with self.repo.database.locked_connection() as db:
            pending = db.execute("SELECT 1 FROM remote_inbox WHERE worker_id=? AND json_extract(command_json,'$.expectedWorkerStoreId')=? "
                "AND json_extract(command_json,'$.wireRevision')=1 AND status NOT IN ('completed','failed','rejected') LIMIT 1",
                (self.repo.get("link")["view"].get("workerId"), identity["store"])).fetchone()
            outbox = db.execute("SELECT 1 FROM remote_outbox WHERE store_id=? LIMIT 1", (identity["store"],)).fetchone()
            projecting = db.execute("SELECT 1 FROM remote_inbox i JOIN local_runs r ON r.run_id=i.run_id "
                "WHERE i.worker_id=? AND json_extract(i.command_json,'$.expectedWorkerStoreId')=? "
                "AND json_extract(i.command_json,'$.wireRevision')=1 AND (r.status NOT IN ('succeeded','failed','cancelled') "
                "OR EXISTS(SELECT 1 FROM local_messages m WHERE m.run_id=r.run_id AND m.role='assistant' "
                "AND NOT EXISTS(SELECT 1 FROM remote_projections p WHERE p.key='message:'||m.message_id))) LIMIT 1",
                (self.repo.get("link")["view"].get("workerId"), identity["store"])).fetchone()
        return pending is None and outbox is None and projecting is None

    async def run(self):
        delay = self.retry_seconds
        while not self.closed:
            view = self.repo.get("link")["view"]
            if view["state"] == "pairing":
                try:
                    await self.link.poll()
                except HubError:
                    pass
                await asyncio.sleep(min(2, self.retry_seconds))
                continue
            if view["state"] != "paired":
                await asyncio.sleep(min(1, self.retry_seconds))
                continue
            generation = self.repo.get("link")["generation"]
            attempt_started = time.monotonic()
            try:
                if not self.repo.check_continuity():
                    continue
                await self.connection(view, generation)
            except asyncio.CancelledError:
                raise
            except Renegotiate:
                continue
            except HubError as error:
                terminal = error.code in {"REMOTE_PROTOCOL_UNSUPPORTED", "REMOTE_STORE_CHANGED", "REMOTE_ACK_CONFLICT", "REMOTE_EPOCH_STALE", "REMOTE_FRAME_TOO_LARGE", "REMOTE_DEVICE_AUTH_FAILED", "REMOTE_SERVER_ORIGIN_INVALID"}
                self.state("offline", code=error.code, frozen=terminal,
                    revoked=error.code == "REMOTE_DEVICE_REVOKED", generation=generation)
            except Exception as error:
                code = getattr(getattr(error, "rcvd", None), "code", None)
                status = getattr(getattr(error, "response", None), "status_code", None)
                auth_failed = code == 4401 or status == 401
                revoked = code == 4403 or status == 403
                self.state("offline", code="REMOTE_DEVICE_REVOKED" if revoked else "REMOTE_DEVICE_AUTH_FAILED" if auth_failed else "REMOTE_SERVER_UNREACHABLE",
                    revoked=revoked, frozen=code == 4409 or auth_failed, generation=generation)
            finally:
                self.socket = None
                self.busy.connection_id = None
                self.delivery.clock.invalidate()
            if self.repo.get("link")["generation"] == generation:
                self.state("offline")
            if time.monotonic() - attempt_started >= 45:
                delay = self.retry_seconds
            await asyncio.sleep(delay + random.random() * delay * 0.2)
            delay = min(60, delay * 2)

    async def connection(self, view, generation):
        self.state("connecting")
        active = self.repo.get("identity").get("wireRevision", 1)
        revision = 2 if active == 2 or (self.probe_revision2 and self.can_upgrade()) else 1
        origin = normalize_origin(view["serverOrigin"], development=self.link.development)
        url = ("wss" if origin.startswith("https:") else "ws") + origin[origin.index(":"):] + "/ws/v2/worker"
        async with self.connector(url, additional_headers={"Authorization": "Bearer " + self.link.vault.read()},
            max_size=MAX_FRAME_BYTES, open_timeout=10, ping_interval=None, logger=self.logger, proxy=None) as ws:
            self.socket = ws
            identity = self.repo.get("identity")
            common = {"workerId": view["workerId"], "workerStoreId": identity["store"], "workerEpoch": identity["epoch"]}
            ack = lambda: None if self.repo.get("identity")["ack"] is None else {"workerStoreId": identity["store"], "seq": self.repo.get("identity")["ack"]}
            started = time.monotonic()
            await asyncio.wait_for(ws.send(encode({"type": "worker.hello", "wireRevision": revision,
                "protocolVersion": PROTOCOL_VERSION, **common, **machine(), "capabilityRevision": self.projector.capability_revision(), "lastServerAck": ack()})), 10)
            hello = decode(await asyncio.wait_for(ws.recv(), 10), revision=revision, negotiation=True)
            if hello["type"] == "worker.hello_rejected":
                if revision == 2 and active == 1 and 1 in hello["supportedWireRevisions"]:
                    self.probe_revision2 = False
                    self.peer_revision2 = 2 in hello["supportedWireRevisions"]
                    self.next_revision2_probe = time.monotonic() + self.revision_probe_seconds
                    self.state("offline", code="REMOTE_REVISION_REQUIRED")
                    raise Renegotiate()
                raise HubError(hello["error"]["code"], "Worker 握手被服务端拒绝")
            if hello["type"] != "worker.hello_ack" or any(hello.get(k) != v for k, v in common.items()):
                raise HubError("REMOTE_EPOCH_STALE", "握手身份或存储世代不匹配")
            if generation != self.repo.get("link")["generation"]:
                return
            self.repo.ack(hello["lastServerAck"])
            if hello["commandDelivery"] == "frozen" and "reason" not in hello:
                raise HubError("REMOTE_STORE_CHANGED", "服务端冻结响应缺少原因")
            if revision == 2 and active == 1:
                if hello["commandDelivery"] != "ready":
                    self.probe_revision2 = False
                    self.peer_revision2 = True
                    self.next_revision2_probe = time.monotonic() + self.revision_probe_seconds
                    raise Renegotiate()
                # A ready rev2 handshake is the server's gate. Locally no old
                # command/event is pending, and both acknowledgement watermarks
                # are persisted before any revision-2 event is allocated.
                if not self.can_upgrade():
                    raise HubError("REMOTE_STORE_CHANGED", "旧线路未完成核对")
                with self.repo.database.transaction() as tx:
                    current = self.repo.get("identity", tx)
                    current.update(wireRevision=2, upgradeFence={"local": current["high"], "server": current["ack"]})
                    self.repo.put("identity", current, tx)
                    self.repo.seal(tx)
            self.repo.source_mapper = self.sync.source_event if revision == 2 else self.projector.source_event
            self.state("online", connected=True, frozen=hello["commandDelivery"] == "frozen",
                code=hello.get("reason", {}).get("code") or (
                    ("REMOTE_REVISION_REQUIRED" if self.peer_revision2 is False else "REMOTE_STATE_NOT_READY") if revision == 1 else None))
            connection_id = hello["connectionId"]
            bridge = self.delivery if revision == 2 else self.bridge
            if revision == 2:
                self.delivery.clock.calibrate(hello["serverTime"], started)
                await self.delivery.recover()
                self.busy.reconcile()
                self.busy.connection_id = connection_id
                self.busy.snapshot(force=True)
                self.sync.prepare()
            window = SendWindow(self.repo, self.sync) if revision == 2 else None
            heartbeat_sends = []
            last_server_time = hello["serverTime"]
            send_lock = asyncio.Lock()
            async def send(value):
                async with send_lock:
                    await ws.send(encode(value) if isinstance(value, dict) else value)
            async def heartbeat():
                while True:
                    await asyncio.sleep(15)
                    heartbeat_sends.append(time.monotonic())
                    await send({"type": "worker.heartbeat", "wireRevision": revision, **common,
                        "connectionId": connection_id, "sentAt": now(), "lastServerAck": ack()})
            async def publish():
                sent = set()
                retransmit_at = time.monotonic() + 15
                catalog_at = 0.0
                while True:
                    if generation != self.repo.get("link")["generation"]:
                        return
                    if not self.repo.check_continuity():
                        raise HubError("REMOTE_STORE_CHANGED", "本机存储需要对账")
                    if time.monotonic() >= catalog_at:
                        await self.projector.catalog()
                        catalog_at = time.monotonic() + 5
                    if revision == 2:
                        await self.delivery.tick()
                        await self.sync.poll_execution(self.delivery)
                        self.busy.snapshot()
                        self.sync.pump()
                    else:
                        await self.projector.poll()
                    with self.repo.database.transaction() as tx:
                        if self.repo.cover_private(tx):
                            self.repo.seal(tx)
                    if revision == 2:
                        await window.flush(send)
                        await asyncio.sleep(0.2)
                        continue
                    contents = self.repo.frames()
                    if time.monotonic() >= retransmit_at:
                        sent.clear()
                        retransmit_at = time.monotonic() + 15
                    sent.intersection_update(json.loads(c)["eventId"] for c in contents)
                    for content in contents:
                        event = json.loads(content)
                        if event["eventId"] not in sent:
                            await send(content)
                            sent.add(event["eventId"])
                    if (self.probe_revision2 or (self.peer_revision2 is True and time.monotonic() >= self.next_revision2_probe)) and self.can_upgrade():
                        self.probe_revision2 = True
                        raise Renegotiate()
                    await asyncio.sleep(0.2)
            queue = asyncio.Queue(maxsize=200)
            async def consume():
                if revision == 1:
                    await bridge.recover()
                while True:
                    frame = await queue.get()
                    if generation != self.repo.get("link")["generation"]:
                        return
                    receipt, gaps = await bridge.receive(frame)
                    if receipt:
                        # New rev2 events pass through the bounded send window;
                        # already ACKed immutable receipts can replay immediately.
                        if revision == 1 or receipt.get("seq", 0) <= (self.repo.get("identity")["ack"] or 0):
                            await send(receipt)
                    for gap in gaps:
                        await send(gap)
            async def receive():
                nonlocal last_server_time
                async for content in ws:
                    frame = decode(content, revision=revision)
                    if generation != self.repo.get("link")["generation"]:
                        return
                    if frame["type"] == "worker.hello_rejected":
                        # P1 also uses this generated error envelope when an
                        # established connection fails event validation. It is
                        # not evidence of an epoch/connectionId mismatch.
                        code = frame["error"]["code"]
                        if not frame["error"]["retryable"] and code != "REMOTE_DEVICE_REVOKED":
                            self.state("offline", code=code, frozen=True, generation=generation)
                        raise HubError(code, "服务端拒绝当前 Worker 连接")
                    if frame["type"] in {"worker.events_ack", "server.heartbeat"}:
                        if frame["connectionId"] != connection_id:
                            raise HubError("REMOTE_EPOCH_STALE", "连接栅栏不匹配")
                        if frame["type"] == "worker.events_ack":
                            if frame["workerId"] != common["workerId"]:
                                raise HubError("REMOTE_TARGET_MISMATCH", "确认设备不匹配")
                            self.repo.ack(frame["position"])
                            if revision == 2:
                                self.sync.on_ack()
                        elif revision == 2 and heartbeat_sends and frame["receivedAt"] > last_server_time:
                            sent_at = heartbeat_sends.pop(0)
                            if time.monotonic() - sent_at <= 45:
                                self.delivery.clock.calibrate(frame["receivedAt"], sent_at)
                                last_server_time = frame["receivedAt"]
                    else:
                        if hello["commandDelivery"] == "frozen":
                            raise HubError("REMOTE_STORE_CHANGED", "冻结世代禁止命令投递")
                        if frame["type"] not in {"run.submit", "run.pause", "run.resume", "run.cancel", "run.retry", "approval.decide", "command.withdraw", "conversation.skip", "conversation.create", "conversation.update", "command.delivery_granted"}:
                            raise HubError("REMOTE_EPOCH_STALE", "连接中出现非命令握手帧")
                        await queue.put(frame)
            jobs = [asyncio.create_task(fn()) for fn in (heartbeat, publish, consume, receive)]
            try:
                done, _ = await asyncio.wait(jobs, return_when=asyncio.FIRST_COMPLETED)
                for job in done:
                    job.result()
            finally:
                try:
                    for job in jobs:
                        job.cancel()
                    await asyncio.gather(*jobs, return_exceptions=True)
                finally:
                    # Keep the existing lost-delivery contract: cancel transport
                    # control jobs before reconnect recovery, not LocalChat runs.
                    await bridge.cancel_executions()
                    if revision == 2:
                        self.delivery.clock.invalidate()
