import asyncio
import json
import re
import secrets
from contextlib import contextmanager
from http.cookies import SimpleCookie

import pytest
from fastapi.testclient import TestClient
from protocol.generated import python as dto

from server.app import ROUTES, create_app
from server.common import stamp, uid
from server.config import Settings
from server.security import COOKIE

PASSWORD = "test-only-password-very-long"


class Clock:
    def __init__(self):
        self.value = 1800000000.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def check_http(result, method, path, routes=None):
    dto.ApiEnvelope.model_validate(result.json())
    if result.json()["success"]:
        for verb, route, _, _, output, _ in (routes or ROUTES):
            if method == verb and re.fullmatch("/api/v2" + re.sub(r"\{[^}]+\}", "[^/]+", route), path.split("?")[0]):
                if output == 'RemoteApiTokenIssuedView' and result.status_code == 200:
                    output = 'RemoteApiTokenIssueReplayView'
                getattr(dto, output).model_validate(result.json()["data"])
                return
        raise AssertionError("No response DTO binding")
    dto.RemoteHttpError.model_validate(result.json()["error"])


class Browser:
    def __init__(self, env, name):
        self.env = env
        result = env.client.post("/api/v2/auth/login", json=dict(loginName=name, password=PASSWORD), headers={"Origin": env.settings.origin, "Idempotency-Key": uid(), "Cookie": ""})
        check_http(result, "POST", "/api/v2/auth/login")
        assert result.status_code == 200, result.text
        cookies = SimpleCookie(result.headers["set-cookie"])
        self.cookie = cookies[COOKIE].value
        self.csrf = result.json()["data"]["csrfToken"]
        self.login_response = result

    def request(self, method, path, body=None, key=None, headers=None):
        auth = {"Origin": self.env.settings.origin, "Cookie": COOKIE + "=" + self.cookie, "X-CSRF-Token": self.csrf, "Idempotency-Key": key or uid()}
        auth.update(headers or {})
        transport_path = path
        if getattr(self.env, 'legacy', False) and '/messages?cursor=' in path:
            transport_path = path.replace('/messages?cursor=', '/messages?before=')
        result = self.env.client.request(method, "/api/v2" + transport_path, json=body, headers=auth)
        check_http(result, method, "/api/v2" + path, self.env.routes)
        return result

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, body=None, **kwargs):
        return self.request("POST", path, {} if body is None else body, **kwargs)


class FakeWorker:
    def __init__(self, env, browser):
        self.env, self.browser = env, browser
        self.secret = secrets.token_urlsafe(32)
        self.store, self.epoch = uid(), uid()
        self.seq = 0
        self.request_body = dict(deviceName="private-computer", workerStoreId=self.store, platform="windows", architecture="x86_64")
        self.pair_key = uid()
        result = self.register()
        assert result.status_code == 201, result.text
        self.challenge = result.json()["data"]
        self.worker = self.challenge["workerId"]
        self.confirm_key = uid()

    def register(self):
        result = self.env.client.post("/api/v2/worker/pairing-requests", json=self.request_body,
                                     headers={"Authorization": "Bearer " + self.secret, "Idempotency-Key": self.pair_key, "Cookie": ""})
        check_http(result, "POST", "/api/v2/worker/pairing-requests")
        return result

    def confirm(self):
        result = self.browser.post("/pairings/" + self.challenge["pairRequestId"] + "/confirm", dict(pairCode=self.challenge["pairCode"]), key=self.confirm_key)
        assert result.status_code == 200, result.text
        return result

    def hello(self, **changes):
        frame = dict(type="worker.hello", wireRevision=1, protocolVersion=dto.PROTOCOL_VERSION,
                     workerId=self.worker, workerStoreId=self.store, workerEpoch=self.epoch,
                     platform="windows", architecture="x86_64", capabilityRevision=1, lastServerAck=None)
        frame.update(changes)
        return frame

    @contextmanager
    def connect(self, hello=None, headers=None, query=""):
        with self.env.client.websocket_connect("wss://testserver/ws/v2/worker" + query, headers=headers or {"Authorization": "Bearer " + self.secret}) as ws:
            self.ws = ws
            async def bounded_receive():
                return await asyncio.wait_for(ws._send_rx.receive(), timeout=3)
            ws.receive = lambda: ws.portal.call(bounded_receive)
            ws.send_json(hello or self.hello())
            self.ack = self.receive()
            yield self

    def receive(self):
        frame = self.ws.receive_json()
        dto.RemoteServerOutboundFrame.model_validate(frame)
        return frame

    def event(self, kind, seq=None, **fields):
        self.seq = self.seq + 1 if seq is None else seq
        frame = dict(type=kind, wireRevision=1, workerId=self.worker, workerStoreId=self.store,
                     workerEpoch=self.epoch, eventId=uid(), seq=self.seq, occurredAt=stamp(self.env.clock()))
        frame.update(fields)
        dto.RemoteWorkerOutboundFrame.model_validate(frame)
        return frame

    def emit(self, frame):
        self.ws.send_json(frame)
        return self.receive()

    def catalog(self, seq=None, **changes):
        value = dict(workerId=self.worker, workerStoreId=self.store, capabilityRevision=1,
                     observedAt=stamp(self.env.clock()), workspaces=[dict(workspaceId="ws", name="Project", displayPath="E:/project", vcs="git", canWrite=True)],
                     scenes=[dict(sceneId="scene", name="Default", version=1, readOnly=False)], remotelyBlockedActions=[])
        value.update(changes)
        return self.emit(self.event("capability.changed", seq, payload=value))

    def conversation(self):
        result = self.browser.post("/conversations", dict(targetWorkerId=self.worker, workerStoreId=self.store, title="Conversation", workspaceId="ws", sceneId="scene", sceneVersion=1))
        assert result.status_code == 201, result.text
        return result.json()["data"]["conversationId"]

    def send(self, conv, text="hello", **changes):
        value = dict(clientMessageId=uid(), text=text, sessionMode="new")
        value.update(changes)
        result = self.browser.post("/conversations/" + conv + "/messages", value)
        assert result.status_code == 202, result.text
        return result.json()["data"]


class Environment:
    pass


@contextmanager
def environment(tmp_path, legacy=False):
    value = Environment()
    value.clock = Clock()
    value.settings = Settings(tmp_path / "hub.sqlite3", secrets.token_bytes(32), origin="https://testserver", clock=value.clock, monotonic=value.clock, rate_limit=10000)
    value.legacy = legacy
    value.routes = ROUTES
    if legacy:
        from legacy_support import HistoricalService, LEGACY_ROUTES
        from server.events import Events
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr('server.app.SyncService', HistoricalService)
            patch.setattr('server.app.SyncEvents', Events)
            patch.setattr('server.app.ROUTES', LEGACY_ROUTES)
            value.app = create_app(value.settings)
        value.routes = LEGACY_ROUTES
    else:
        value.app = create_app(value.settings)
    value.service = value.app.state.service
    for name in ("alice", "bob"):
        value.service.security.create_account(name, PASSWORD, name.title())
    with TestClient(value.app, base_url=value.settings.origin) as client:
        value.client = client
        value.alice = Browser(value, "alice")
        value.bob = Browser(value, "bob")
        yield value


@pytest.fixture
def env(tmp_path):
    with environment(tmp_path, legacy=True) as value:
        yield value


@pytest.fixture
def r15_env(tmp_path):
    with environment(tmp_path) as value:
        yield value


@pytest.fixture
def paired(env):
    worker = FakeWorker(env, env.alice)
    worker.confirm()
    with worker.connect():
        assert worker.ack["commandDelivery"] == "ready"
        assert worker.catalog()["position"]["seq"] == 1
    worker.conv = worker.conversation()
    return worker
