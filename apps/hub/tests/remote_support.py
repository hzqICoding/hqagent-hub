"""Offline R1 integration harness: real TLS HTTP/WS, SQLite and execution core."""
from __future__ import annotations

import asyncio
import json
import hashlib
import logging
import socket
import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketDisconnected
from protocol.generated.python import (
    AgentResult, ApiEnvelope, RemotePairingChallenge, RemotePairingRequestInput,
    RemotePairingStatusView, RemoteServerOutboundFrame, RemoteWorkerOutboundFrame,
    TeamProfileView, WorkspaceView,
    RemoteV2WorkerOutboundFrame, RemoteV2ServerOutboundFrame,
    RemoteV3WorkerOutboundFrame, RemoteV3ServerOutboundFrame,
    RemoteV4WorkerOutboundFrame, RemoteV4ServerOutboundFrame,
    RemoteV5WorkerOutboundFrame, RemoteV5ServerOutboundFrame,
)
from api.app import create_application
from core.ports import HubPorts
from orchestrator.catalog import BuiltinCatalog
from orchestrator.role_resolver import RoleResolver
from orchestrator.runtime import WorkflowRuntime
from orchestrator.sessions import SessionManager
from orchestrator.tests.fakes import FakeAdapter, FakeAdapterDirectory, agent
from runtime.paths import HubPaths
from runtime.repositories import ApprovalRepository, EventSink, SessionRepository
from runtime.remote.link import PairingHTTP
from runtime.remote.worker import NoRedirectConnect
from runtime.tasks import ApprovalService, SessionService, TaskService
from security.approvals import ApprovalCoordinator
from security.permissions import PermissionEngine
from storage.local_chat import now
from storage.tasks import TaskRepository

TOKEN = "hub-test-" + "H" * 43
TLS_FILES = Path(__file__).parent / "fixtures" / "remote"
WORKER_CODECS = {1: RemoteWorkerOutboundFrame, 2: RemoteV2WorkerOutboundFrame, 3: RemoteV3WorkerOutboundFrame, 4: RemoteV4WorkerOutboundFrame, 5: RemoteV5WorkerOutboundFrame}
SERVER_CODECS = {1: RemoteServerOutboundFrame, 2: RemoteV2ServerOutboundFrame, 3: RemoteV3ServerOutboundFrame, 4: RemoteV4ServerOutboundFrame, 5: RemoteV5ServerOutboundFrame}


def later(seconds=300):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


async def until(predicate, timeout=8):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


def dump(value):
    return value.model_dump(mode="json", by_alias=True, exclude_none=True)


class FakeRemoteServer:
    def __init__(self, *, auto_ack=True, reject_revisions=None, frozen=False, revision=1):
        self.auto_ack, self.reject_revisions, self.frozen = auto_ack, reject_revisions, frozen
        self.revision = revision
        self.upgrade_pending = False
        self.claimed = False
        self.expires_at = later()
        self.pair_calls, self.connections = 0, 0
        self.requests, self.frames, self.hellos, self.errors = [], [], [], []
        self.requested_revisions = []
        self.deletions, self.segment_sets, self.replica_messages = {}, {}, {}
        self.busy_ids, self.busy_version = set(), 0
        self.event_bytes, self.coverage, self.acks = {}, {}, {}
        self.challenge_gate = None
        self.challenge_entered = asyncio.Event()
        self.ws = None
        self.workers = []
        self.secret = None
        self.app = FastAPI()
        self._routes()

    def envelope(self, value):
        return dump(ApiEnvelope(success=True, data=dump(value), requestId="test-response", protocolVersion="0.6.1"))

    def _routes(self):
        @self.app.post("/api/v2/worker/pairing-requests", status_code=201)
        async def pair(request: Request):
            value = RemotePairingRequestInput.model_validate(await request.json())
            assert request.url.scheme == "https"
            assert request.headers["authorization"].startswith("Bearer ")
            secret = request.headers["authorization"][7:]
            if self.secret is None:
                self.secret = secret
            assert self.secret == secret
            self.pair_calls += 1
            self.requests.append((request.url.path, request.headers["idempotency-key"], dump(value)))
            self.challenge_entered.set()
            if self.challenge_gate:
                await self.challenge_gate.wait()
            return self.envelope(RemotePairingChallenge(pairRequestId="pair-test", workerId="worker-test",
                pairCode="ABCD2345", expiresAt=self.expires_at, status="pending"))

        @self.app.get("/api/v2/worker/pairing-requests/{request_id}")
        async def status(request_id: str, request: Request):
            assert request_id == "pair-test"
            assert request.headers["authorization"] == "Bearer " + self.secret
            return self.envelope(RemotePairingStatusView(pairRequestId=request_id, workerId="worker-test",
                status="paired" if self.claimed else "pending", expiresAt=self.expires_at))

        @self.app.websocket("/ws/v2/worker")
        async def worker(ws: WebSocket):
            try:
                assert ws.url.scheme == "wss"
                assert ws.headers["authorization"] == "Bearer " + self.secret
                await ws.accept()
                raw_hello = json.loads(await ws.receive_text())
                requested = raw_hello["wireRevision"]
                self.requested_revisions.append(requested)
                if requested == 2 and self.upgrade_pending:
                    await self.send({"type": "worker.hello_rejected", "wireRevision": 1,
                        "supportedWireRevisions": [1, 2], "error": {
                            "code": "REMOTE_PROTOCOL_UNSUPPORTED", "message": "old commands pending", "retryable": True}}, ws)
                    await ws.close(code=4409)
                    return
                if requested != self.revision and self.reject_revisions is None and not (requested == 1 and self.upgrade_pending):
                    await self.send({"type": "worker.hello_rejected", "wireRevision": self.revision,
                        "supportedWireRevisions": [self.revision], "error": {
                            "code": "REMOTE_PROTOCOL_UNSUPPORTED", "message": "unsupported", "retryable": False}}, ws)
                    await ws.close(code=4409)
                    return
                self.connections += 1
                revision = requested
                hello = dump(WORKER_CODECS[requested].model_validate(raw_hello))
                assert hello["type"] == "worker.hello"
                self.hellos.append(hello)
                if self.reject_revisions:
                    await self.send({"type": "worker.hello_rejected", "wireRevision": self.revision,
                        "supportedWireRevisions": self.reject_revisions, "error": {
                            "code": "REMOTE_PROTOCOL_UNSUPPORTED", "message": "unsupported", "retryable": False}}, ws)
                    await ws.close(code=4409)
                    return
                self.connection_id = "connection-" + str(self.connections)
                connection_id = self.connection_id
                store = hello["workerStoreId"]
                ack = self.acks.get(store)
                response = {"type": "worker.hello_ack", "wireRevision": revision,
                    **{k: hello[k] for k in ("workerId", "workerStoreId", "workerEpoch")},
                    "connectionId": self.connection_id, "commandDelivery": "frozen" if self.frozen else "ready",
                    "lastServerAck": None if ack is None else {"workerStoreId": store, "seq": ack},
                    "pendingCommandCursor": "opaque-pending-cursor", "heartbeatIntervalSeconds": 15,
                    "offlineAfterSeconds": 45, "serverTime": now()}
                if self.frozen:
                    response["reason"] = {"code": "REMOTE_STORE_CHANGED", "message": "reconcile", "retryable": False}
                await self.send(response, ws)
                self.ws = ws
                while True:
                    raw = await ws.receive_text()
                    frame = dump(WORKER_CODECS[revision].model_validate_json(raw))
                    self.frames.append(frame)
                    if frame["type"] == "sync.reset":
                        self.deletions[frame["eventId"]] = frame
                        self.segment_sets = {k: v for k, v in self.segment_sets.items() if k[0] != store}
                        self.replica_messages = {k: v for k, v in self.replica_messages.items() if k[0] != store}
                    if frame["type"] == "sync.message.segment" and frame["syncGeneration"] > max(
                        (d["syncGeneration"] for d in self.deletions.values() if d["workerStoreId"] == store), default=0):
                        p = frame["payload"]
                        key = (store, frame["syncGeneration"], p["messageId"], p["messageRevision"])
                        pieces = self.segment_sets.setdefault(key, {})
                        assert pieces.get(p["segmentIndex"], p["text"]) == p["text"]
                        pieces[p["segmentIndex"]] = p["text"]
                        if len(pieces) == p["segmentCount"]:
                            whole = "".join(pieces[i] for i in range(p["segmentCount"]))
                            assert len(whole.encode("utf-8")) == p["totalUtf8Bytes"]
                            assert hashlib.sha256(whole.encode("utf-8")).hexdigest() == p["contentSha256"]
                            current = self.replica_messages.get((store, p["messageId"]))
                            if current is None or current["revision"] <= p["messageRevision"]:
                                self.replica_messages[(store, p["messageId"])] = {"text": whole, "revision": p["messageRevision"]}
                    if "eventId" in frame:
                        key = (frame["workerStoreId"], frame["seq"])
                        encoded = json.dumps(frame, sort_keys=True, ensure_ascii=False)
                        assert self.event_bytes.get(key, encoded) == encoded
                        self.event_bytes[key] = encoded
                        self.coverage[key] = frame.get("firstSeq", frame["seq"])
                    elif frame["type"] == "sync.content.redaction":
                        deletion = self.deletions[frame["deletionEventId"]]
                        assert deletion["seq"] == frame["deletionSeq"] and deletion["syncGeneration"] == frame["syncGeneration"]
                        for slot in frame["slots"]:
                            assert slot["seq"] < deletion["seq"]
                            previous = self.event_bytes.get((store, slot["seq"]))
                            if previous is not None:
                                canonical = json.dumps(json.loads(previous), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                                assert hashlib.sha256(canonical.encode()).hexdigest() == slot["eventSha256"]
                            self.coverage[(store, slot["seq"])] = slot["seq"]
                    if "eventId" in frame or frame["type"] == "sync.content.redaction":
                        if self.auto_ack:
                            contiguous = self.acks.get(store, 0)
                            for (item_store, end), start in sorted(self.coverage.items()):
                                if item_store == store and start <= contiguous + 1 and end > contiguous:
                                    contiguous = end
                            self.acks[store] = contiguous
                            snapshots = {}
                            for event in self.frames:
                                if event["type"] == "sync.busy.snapshot" and event["connectionId"] == connection_id and event["workerEpoch"] == hello["workerEpoch"] and event["seq"] <= contiguous:
                                    snapshots.setdefault(event["snapshotId"], {})[event["partIndex"]] = event
                            for parts in snapshots.values():
                                last = max(e["seq"] for e in parts.values())
                                if len(parts) == next(iter(parts.values()))["partCount"] and last > self.busy_version:
                                    self.busy_ids = {item for e in parts.values() for item in e["conversationIds"]}
                                    self.busy_version = last
                            await self.send({"type": "worker.events_ack", "wireRevision": revision,
                                "connectionId": connection_id, "workerId": hello["workerId"],
                                "position": {"workerStoreId": store, "seq": contiguous}}, ws)
                    elif frame["type"] == "worker.heartbeat":
                        await self.send({"type": "server.heartbeat", "wireRevision": revision,
                            "connectionId": connection_id, "receivedAt": now()}, ws)
            except (WebSocketDisconnect, WebSocketDisconnected):
                # Tests deliberately close a live socket while receipts/acks may
                # be in flight. Starlette distinguishes closed-send from EOF.
                pass
            except Exception as error:
                self.errors.append(error)
                try:
                    await ws.close(code=1011)
                except Exception:
                    pass

    async def send(self, value, ws=None):
        value = dump(SERVER_CODECS[value["wireRevision"]].model_validate(value))
        await (ws or self.ws).send_json(value)

    async def __aenter__(self):
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        port = self.socket.getsockname()[1]
        self.origin = f"https://127.0.0.1:{port}"
        config = uvicorn.Config(self.app, log_config=None, log_level="critical", access_log=False,
            ssl_certfile=str(TLS_FILES / "test-cert.pem"), ssl_keyfile=str(TLS_FILES / "test-key.pem"),
            ws="websockets-sansio", lifespan="off")
        self.server = uvicorn.Server(config)
        self.job = asyncio.create_task(self.server.serve(sockets=[self.socket]))
        await until(lambda: self.server.started)
        self.client_tls = ssl.create_default_context(cafile=str(TLS_FILES / "test-cert.pem"))
        return self

    async def __aexit__(self, *_args):
        # Stop clients before the listening server; otherwise the intentional
        # reconnect loop can open a replacement socket during server shutdown.
        for worker in self.workers:
            await worker.stop()
        self.server.should_exit = True
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
        await asyncio.wait_for(self.job, 5)
        self.socket.close()


class Profiles:
    available = True
    def __init__(self):
        self.items = {}
    async def save_profile(self, profile_id, value):
        view = TeamProfileView.model_validate({**dump(value), "updatedAt": now()})
        self.items[profile_id] = view
        return view
    async def get_profile(self, profile_id):
        return self.items[profile_id]


class Workspaces:
    available = True
    def __init__(self, directory):
        self.items = [WorkspaceView(id="workspace", name="registered", path=str(directory),
            vcs="none", lastOpenedAt=now(), capabilities={"canRunWriteTasks": False})]
    async def list_workspaces(self, *_args):
        return self.items


class ControlledAdapter(FakeAdapter):
    def __init__(self, *, hold=False):
        super().__init__()
        self.release = asyncio.Event()
        if not hold:
            self.release.set()
        self.before_start = None
    async def start(self, spec):
        if self.before_start:
            self.before_start(spec)
        return await super().start(spec)
    async def stream_events(self, session_id):
        await self.release.wait()
        if False:
            yield None


class System:
    def __init__(self, path, *, hold=False):
        self.ports = HubPorts.unavailable_defaults()
        self.ports.team_profiles = Profiles()
        self.ports.workspaces = Workspaces(path)
        self.application = create_application(paths=HubPaths.resolve(path / "data-root"), token=TOKEN,
            ports=self.ports, close_database_on_shutdown=False)
        self.db, self.events = self.application.database, self.application.events
        self.worker = self.application.app.state.remote_worker
        self.chat = self.application.local_chat
        self.repo, self.link, self.bridge = self.worker.repo, self.worker.link, self.worker.bridge
        self.adapter = ControlledAdapter(hold=hold)
        self.adapter.result = AgentResult(status="done", summary="remote result", changedFiles=[])
        directory = FakeAdapterDirectory((agent("agent", capabilities=("structured_output", "tool_approval", "session_resume")),), self.adapter)
        catalog = BuiltinCatalog.load()
        session_repo = SessionRepository(self.db)
        sessions = SessionManager(session_repo, directory)
        sink = EventSink(self.db, self.events)
        runtime = WorkflowRuntime(RoleResolver(catalog), PermissionEngine(catalog), sessions, directory, sink)
        approval_repo = ApprovalRepository(self.db)
        self.coordinator = ApprovalCoordinator(approval_repo, sink, directory)
        self.tasks = TaskService(TaskRepository(self.db), runtime, directory,
            self.ports.team_profiles, sink, self.ports.workspaces, approval_coordinator=self.coordinator)
        self.tasks.execution_commit_observer = self.repo.seal
        self.ports.tasks = self.tasks
        self.ports.sessions = SessionService(session_repo, sessions)
        self.ports.approvals = ApprovalService(approval_repo, self.coordinator)
        self.chat.poll_seconds = 0.01
        self.worker.retry_seconds = 0.02
        self.local = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.application.app),
            base_url="http://127.0.0.1", headers={"Authorization": "Bearer " + TOKEN})

    async def pair(self, server, *, start=False):
        self.link.http = PairingHTTP(self.link.vault, transport=httpx.AsyncHTTPTransport(verify=server.client_tls))
        self.worker.connector = lambda uri, **kwargs: NoRedirectConnect(uri, ssl=server.client_tls, **kwargs)
        response = await self.local.post("/api/v1/remote/pairing", json={"serverOrigin": server.origin,
            "deviceName": "test device"}, headers={"Idempotency-Key": "pair"})
        assert response.status_code == 200, response.text
        server.claimed = True
        await self.link.poll()
        if start:
            server.workers.append(self.worker)
            await self.chat.start()
            await self.worker.start()
            await until(lambda: self.repo.get("link")["view"].get("connectionStatus") == "online" or
                        self.repo.get("link")["view"]["state"] == "frozen")
        return response

    def command(self, identifier, *, seq=1, conversation="conversation-remote", kind="run.submit", payload=None):
        value = {"type": kind, "wireRevision": 1, "commandId": identifier, "conversationId": conversation,
            "targetWorkerId": "worker-test", "expectedWorkerStoreId": self.repo.get("identity")["store"],
            "createdAt": now(), "expiresAt": later(120), "payload": payload or {
                "clientMessageId": identifier, "text": identifier, "workspaceId": "workspace",
                "sceneId": "analyze", "sceneVersion": 1, "sessionMode": "new"}}
        if kind == "run.submit":
            value["conversationSeq"] = seq
        return dump(RemoteServerOutboundFrame.model_validate(value))

    async def close(self):
        await self.worker.stop()
        await self.chat.stop()
        await self.tasks.shutdown()
        await self.local.aclose()
        self.db.close()


def command_events(server, identifier, kind=None):
    return [f for f in server.frames if f.get("commandId") == identifier and (kind is None or f["type"] == kind)]
