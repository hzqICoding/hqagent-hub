import logging
import secrets

import pytest
from starlette.websockets import WebSocketDisconnect

from conftest import Browser, FakeWorker, PASSWORD, check_http
from server.common import uid
from server.security import COOKIE


def test_owner_isolation_all_resource_routes(env, paired):
    receipt = paired.send(paired.conv)
    resources = ["/devices/" + paired.worker, "/devices/" + paired.worker + "/catalog",
                 "/conversations/" + paired.conv, "/conversations/" + paired.conv + "/snapshot",
                 "/commands/" + receipt["commandId"]]
    resources += ["/conversations/" + paired.conv + "/" + k for k in ("messages", "runs", "commands")]
    for path in resources:
        assert env.alice.get(path).status_code == 200
        response = env.bob.get(path)
        assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"
    for path, body in [("/devices/" + paired.worker + "/revocations", {}),
                       ("/commands/" + receipt["commandId"] + "/cancellations", {}),
                       ("/conversations/" + paired.conv + "/messages", dict(clientMessageId=uid(), text="x", sessionMode="new"))]:
        assert env.bob.post(path, body).json()["error"]["code"] == "NOT_FOUND"
    assert env.bob.get("/devices").json()["data"]["items"] == []
    assert env.bob.get("/conversations").json()["data"]["items"] == []
    tail = env.bob.get("/events").json()["data"]["nextServerCursor"]
    paired.send(paired.conv)
    assert env.bob.get("/events?after=" + tail).json()["data"]["items"] == []
    assert env.bob.post("/conversations", dict(targetWorkerId=paired.worker, workerStoreId=paired.store, title="stolen", workspaceId="ws", sceneId="scene", sceneVersion=1)).status_code == 404
    for field in ("ownerId", "userId", "accountId", "tenantId", "conversationSeq"):
        body = dict(clientMessageId=uid(), text="x", sessionMode="new", **{field: "forged"})
        assert env.alice.post("/conversations/" + paired.conv + "/messages", body).status_code == 422


def test_pairing_expiration_and_poll_secret_scope(env):
    worker = FakeWorker(env, env.alice)
    path = "/api/v2/worker/pairing-requests/" + worker.challenge["pairRequestId"]
    for secret, code in ((worker.secret, 200), (secrets.token_urlsafe(32), 404)):
        result = env.client.get(path, headers={"Authorization": "Bearer " + secret, "Cookie": ""})
        check_http(result, "GET", path)
        assert result.status_code == code
        assert worker.challenge["pairCode"] not in result.text
    env.clock.advance(301)
    assert worker.register().json()["error"]["code"] == "REMOTE_PAIRING_EXPIRED"
    assert env.alice.post("/pairings/preview", dict(pairCode=worker.challenge["pairCode"])).status_code == 410
    assert env.alice.post("/pairings/" + worker.challenge["pairRequestId"] + "/confirm", dict(pairCode=worker.challenge["pairCode"])).status_code == 410
    worker.pair_key = uid()
    assert worker.register().status_code == 201


def test_revoke_disconnects_and_refuses_reconnect(env, paired):
    with paired.connect():
        result = env.alice.post("/devices/" + paired.worker + "/revocations")
        assert result.status_code == 200
        assert result.json()["data"]["executionMayStillBeRunning"] is True
        with pytest.raises(WebSocketDisconnect) as closed:
            paired.receive()
        assert closed.value.code == 4403
    with pytest.raises(WebSocketDisconnect):
        with paired.connect():
            pass
    assert paired.register().status_code == 409


@pytest.mark.parametrize("method", ["cookie", "query", "unpaired"])
def test_worker_only_authorization_header(env, paired, method):
    headers = {"Cookie": COOKIE + "=" + env.alice.cookie}
    query = ""
    if method == "query":
        headers = {"Authorization": "Bearer " + paired.secret}
        query = "?token=" + paired.secret
    if method == "unpaired":
        headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
    with pytest.raises(WebSocketDisconnect):
        with paired.connect(headers=headers, query=query):
            pass


def test_sessions_csrf_rotation_and_safe_auth_replay(env):
    cookie = env.alice.login_response.headers["set-cookie"]
    for flag in ("Secure", "HttpOnly", "SameSite=strict", "Path=/"):
        assert flag in cookie
    assert "Domain=" not in cookie
    assert env.alice.get("/auth/session").json()["data"]["authenticated"]
    assert env.alice.post("/pairings/preview", dict(pairCode="ABCDEFGH"), headers={"Origin": "https://evil.invalid"}).status_code == 403
    assert env.alice.post("/pairings/preview", dict(pairCode="ABCDEFGH"), headers={"X-CSRF-Token": env.bob.csrf}).status_code == 403
    body = dict(loginName="alice", password=PASSWORD)
    key = uid()
    first = env.alice.post("/auth/login", body, key=key)
    second = env.alice.post("/auth/login", body, key=key)
    assert first.headers["set-cookie"] == second.headers["set-cookie"]
    assert env.alice.get("/auth/session").json()["data"] == {"authenticated": False}
    browser = Browser(env, "alice")
    key = uid()
    assert browser.post("/auth/logout", key=key).status_code == 200
    assert browser.post("/auth/logout", key=key).status_code == 200
    assert browser.post("/auth/logout").status_code == 401
    assert browser.get("/devices").status_code == 401


def test_rate_limits_and_generic_login_failures(env):
    env.settings.rate_limit = 4
    env.clock.advance(61)
    errors = []
    for name in ("alice", "unknown", "another", "alice", "alice"):
        result = env.alice.post("/auth/login", dict(loginName=name, password="invalid-password"))
        errors.append(result)
    assert all(r.json()["error"]["code"] == "REMOTE_AUTH_REQUIRED" for r in errors[:4])
    assert errors[-1].json()["error"]["code"] == "REMOTE_RATE_LIMITED"
    assert errors[-1].status_code == 429 and int(errors[-1].headers["retry-after"]) > 0


def test_credentials_not_in_responses_logs_or_database(env, caplog):
    caplog.set_level(logging.DEBUG)
    worker = FakeWorker(env, env.alice)
    code = worker.challenge["pairCode"]
    worker.confirm()
    responses = [env.alice.get("/devices"), env.alice.get("/auth/session"),
                 env.alice.post("/pairings/preview", dict(pairCode=code)),
                 env.alice.post("/auth/login", dict(loginName="alice", password="invalid-secret-marker")),
                 env.alice.post("/pairings/preview", dict(pairCode="invalid-secret-marker"))]
    # A transport logger must not accidentally leak request URLs/headers on errors.
    for logger in ("uvicorn.access", "uvicorn.error", "websockets.server"):
        logging.getLogger(logger).error("Authorization=%s Cookie=%s code=%s", worker.secret, env.alice.cookie, code)
    text = "\n".join(r.text for r in responses) + caplog.text
    for sensitive in (PASSWORD, env.alice.cookie, worker.secret, code, "invalid-secret-marker"):
        assert sensitive not in text
    snapshot = env.settings.database.parent / "backup.sqlite3"
    env.service.repo.backup(snapshot)
    disk = snapshot.read_bytes()
    for sensitive in (PASSWORD, env.alice.cookie, worker.secret, code):
        assert sensitive.encode() not in disk
    assert all(r.headers["cache-control"] == "no-store" for r in responses)
