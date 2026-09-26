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
from runtime.remote.wire import WIRE_REVISION, MAX_FRAME_BYTES, encode, decode
from runtime.remote.projection import Projector


class NoRedirectConnect(connect):
    def process_redirect(self, exc):
        # Never forward the device credential to a redirect target.
        return exc


class RemoteWorker:
    def __init__(self, repository, link, bridge, *, connector=None, retry_seconds=1.0):
        self.repo, self.link, self.bridge = repository, link, bridge
        self.projector = Projector(bridge)
        self.connector = connector or NoRedirectConnect
        self.retry_seconds = retry_seconds
        self.job = None
        self.socket = None
        self.closed = False
        self.link.disconnect = self.disconnect
        # websockets DEBUG includes request headers. Isolate the transport logger
        # from application handlers, including applications enabling root DEBUG.
        self.logger = logging.Logger("remote.transport.silent", level=logging.CRITICAL + 1)
        self.logger.addHandler(logging.NullHandler())
        self.logger.propagate = False

    async def start(self):
        self.repo.boot()
        self.closed = False
        self.job = asyncio.create_task(self.run())

    async def stop(self):
        self.closed = True
        await self.disconnect()
        if self.job:
            self.job.cancel()
            await asyncio.gather(self.job, return_exceptions=True)
            self.job = None

    async def disconnect(self):
        if self.socket:
            await self.socket.close()

    def state(self, status, *, code=None, connected=False, frozen=False, revoked=False):
        with self.repo.database.transaction() as tx:
            view = self.repo.get("link", tx)["view"]
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
            self.repo.set_view(tx, view)
            self.repo.seal(tx)

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
            try:
                if not self.repo.check_continuity():
                    continue
                await self.connection(view, generation)
                delay = self.retry_seconds
            except asyncio.CancelledError:
                raise
            except HubError as error:
                terminal = error.code in {"REMOTE_PROTOCOL_UNSUPPORTED", "REMOTE_STORE_CHANGED", "REMOTE_ACK_CONFLICT", "REMOTE_EPOCH_STALE", "REMOTE_FRAME_TOO_LARGE"}
                self.state("offline", code=error.code, frozen=terminal)
            except Exception as error:
                code = getattr(getattr(error, "rcvd", None), "code", None)
                status = getattr(getattr(error, "response", None), "status_code", None)
                self.state("offline", code="REMOTE_DEVICE_REVOKED" if code == 4403 or status == 403 else "REMOTE_SERVER_UNREACHABLE",
                    revoked=code == 4403 or status == 403, frozen=code == 4409)
            finally:
                self.socket = None
            if self.repo.get("link")["generation"] == generation:
                self.state("offline")
            await asyncio.sleep(delay + random.random() * delay * 0.2)
            delay = min(60, delay * 2)

    async def connection(self, view, generation):
        self.state("connecting")
        origin = view["serverOrigin"]
        url = ("wss" if origin.startswith("https:") else "ws") + origin[origin.index(":"):] + "/ws/v2/worker"
        async with self.connector(url, additional_headers={"Authorization": "Bearer " + self.link.vault.read()},
            max_size=MAX_FRAME_BYTES, open_timeout=10, ping_interval=None, logger=self.logger, proxy=None) as ws:
            self.socket = ws
            identity = self.repo.get("identity")
            common = {"workerId": view["workerId"], "workerStoreId": identity["store"], "workerEpoch": identity["epoch"]}
            ack = lambda: None if self.repo.get("identity")["ack"] is None else {"workerStoreId": identity["store"], "seq": self.repo.get("identity")["ack"]}
            await asyncio.wait_for(ws.send(encode({"type": "worker.hello", "wireRevision": WIRE_REVISION,
                "protocolVersion": PROTOCOL_VERSION, **common, **machine(), "capabilityRevision": self.bridge.policy()[0], "lastServerAck": ack()})), 10)
            hello = decode(await asyncio.wait_for(ws.recv(), 10))
            if hello["type"] == "worker.hello_rejected":
                raise HubError(hello["error"]["code"], "Worker 握手被服务端拒绝")
            if hello["type"] != "worker.hello_ack" or any(hello.get(k) != v for k, v in common.items()):
                raise HubError("REMOTE_EPOCH_STALE", "握手身份或存储世代不匹配")
            if generation != self.repo.get("link")["generation"]:
                return
            self.repo.ack(hello["lastServerAck"])
            if hello["commandDelivery"] == "frozen" and "reason" not in hello:
                raise HubError("REMOTE_STORE_CHANGED", "服务端冻结响应缺少原因")
            self.state("online", connected=True, frozen=hello["commandDelivery"] == "frozen",
                code=hello.get("reason", {}).get("code"))
            connection_id = hello["connectionId"]
            send_lock = asyncio.Lock()
            async def send(value):
                async with send_lock:
                    await ws.send(encode(value) if isinstance(value, dict) else value)
            async def heartbeat():
                while True:
                    await asyncio.sleep(15)
                    await send({"type": "worker.heartbeat", "wireRevision": WIRE_REVISION, **common,
                        "connectionId": connection_id, "sentAt": now(), "lastServerAck": ack()})
            async def publish():
                sent = set()
                while True:
                    if generation != self.repo.get("link")["generation"]:
                        return
                    await self.projector.catalog()
                    await self.projector.poll()
                    with self.repo.database.transaction() as tx:
                        self.repo.cover_private(tx)
                        self.repo.seal(tx)
                    for content in self.repo.frames():
                        event = json.loads(content)
                        if event["eventId"] not in sent:
                            await send(content)
                            sent.add(event["eventId"])
                    await asyncio.sleep(0.2)
            queue = asyncio.Queue(maxsize=200)
            async def consume():
                while True:
                    frame = await queue.get()
                    if generation != self.repo.get("link")["generation"]:
                        return
                    receipt, gaps = await self.bridge.receive(frame)
                    if receipt:
                        await send(receipt)
                    for gap in gaps:
                        await send(gap)
            async def receive():
                async for content in ws:
                    frame = decode(content)
                    if generation != self.repo.get("link")["generation"]:
                        return
                    if frame["type"] in {"worker.events_ack", "server.heartbeat"}:
                        if frame["connectionId"] != connection_id:
                            raise HubError("REMOTE_EPOCH_STALE", "连接栅栏不匹配")
                        if frame["type"] == "worker.events_ack":
                            if frame["workerId"] != common["workerId"]:
                                raise HubError("REMOTE_TARGET_MISMATCH", "确认设备不匹配")
                            self.repo.ack(frame["position"])
                    else:
                        if hello["commandDelivery"] == "frozen":
                            raise HubError("REMOTE_STORE_CHANGED", "冻结世代禁止命令投递")
                        await queue.put(frame)
            jobs = [asyncio.create_task(fn()) for fn in (heartbeat, publish, consume, receive)]
            try:
                done, _ = await asyncio.wait(jobs, return_when=asyncio.FIRST_COMPLETED)
                for job in done:
                    job.result()
            finally:
                for job in jobs:
                    job.cancel()
                await asyncio.gather(*jobs, return_exceptions=True)
