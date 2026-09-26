import asyncio
import hmac
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles
from protocol.generated.python import ApiEnvelope, PROTOCOL_VERSION

from .common import Fault, require, stamp, uid, validated
from .config import Settings
from .events import Events
from .repository import Repository
from .security import COOKIE, Security
from .service import KINDS, Service
from .worker import WorkerTransport

LOG = logging.getLogger("hqremote")


class TransportLogFilter(logging.Filter):
    """Transport records can include credential-bearing URLs and tracebacks.

    Replace them with application audit records containing only fixed operation
    names and status codes. Do not enable request/response debug logging.
    """
    def filter(self, record):
        return False


def protect_transport_logs():
    for name in ("uvicorn.access", "uvicorn.error", "websockets.server", "websockets.client"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, TransportLogFilter) for f in logger.filters):
            logger.addFilter(TransportLogFilter())


def response(data=None, *, model=None, fault=None, status=200):
    envelope = dict(success=fault is None, requestId=uid(), protocolVersion=PROTOCOL_VERSION)
    headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    if fault:
        envelope["error"] = fault.view()
        status = fault.status
        if fault.code == "REMOTE_RATE_LIMITED":
            headers["Retry-After"] = "60"
    else:
        envelope["data"] = validated(model, data)
    ApiEnvelope.model_validate(envelope)
    return JSONResponse(envelope, status_code=status, headers=headers)


# Explicit HTTP bindings; boundary validation exclusively uses generated DTOs.
ROUTES = [
    ("POST", "/auth/login", "login", "RemoteLoginInput", "RemoteAuthenticatedSession", 200),
    ("GET", "/auth/session", "session", None, "RemoteBrowserSessionView", 200),
    ("POST", "/auth/logout", "logout", None, "RemoteAnonymousSession", 200),
    ("POST", "/worker/pairing-requests", "pair_request", "RemotePairingRequestInput", "RemotePairingChallenge", 201),
    ("GET", "/worker/pairing-requests/{pairRequestId}", "pair_status", None, "RemotePairingStatusView", 200),
    ("POST", "/pairings/preview", "preview", "RemotePairingPreviewInput", "RemotePairingPreview", 200),
    ("POST", "/pairings/{pairRequestId}/confirm", "confirm", "RemotePairingConfirmInput", "RemoteDeviceView", 200),
    ("GET", "/devices", "devices", None, "RemoteDevicePage", 200),
    ("GET", "/devices/{workerId}", "device", None, "RemoteDeviceView", 200),
    ("POST", "/devices/{workerId}/revocations", "revoke", "RemoteDeviceRevokeInput", "RemoteDeviceRevocationView", 200),
    ("GET", "/devices/{workerId}/catalog", "catalog", None, "RemoteCatalogView", 200),
    ("GET", "/conversations", "conversations", None, "RemoteConversationPage", 200),
    ("POST", "/conversations", "create_conversation", "RemoteCreateConversationInput", "RemoteConversationView", 201),
    ("GET", "/conversations/{conversationId}", "conversation", None, "RemoteConversationView", 200),
    ("POST", "/conversations/{conversationId}/messages", "send", "RemoteSendMessageInput", "RemoteQueuedReceipt", 202),
    ("GET", "/conversations/{conversationId}/messages", "messages", None, "RemoteMessagePage", 200),
    ("GET", "/conversations/{conversationId}/runs", "runs", None, "RemoteRunPage", 200),
    ("GET", "/conversations/{conversationId}/commands", "commands", None, "RemoteCommandPage", 200),
    ("GET", "/runs/{runId}", "run", None, "RemoteRunView", 200),
    ("POST", "/runs/{runId}/commands", "control", "RemoteRunControlInput", "RemoteQueuedReceipt", 202),
    ("GET", "/commands/{commandId}", "command", None, "RemoteCommandView", 200),
    ("POST", "/commands/{commandId}/cancellations", "withdraw", "RemoteCommandWithdrawalInput", "RemoteCommandView", 202),
    ("GET", "/approvals/{approvalId}", "approval", None, "RemoteApprovalView", 200),
    ("POST", "/approvals/{approvalId}/decisions", "decide", "RemoteApprovalDecisionInput", "RemoteQueuedReceipt", 202),
    ("GET", "/events", "events", None, "RemoteBrowserEventPage", 200),
    ("GET", "/conversations/{conversationId}/snapshot", "snapshot", None, "RemoteConversationSnapshot", 200),
]


def create_app(settings=None):
    protect_transport_logs()
    settings = settings or Settings.from_env()
    repo = Repository(settings.database)
    security = Security(repo, settings)
    service = Service(repo, settings, security)
    transport = WorkerTransport(service, Events(service))

    async def maintenance():
        while True:
            await asyncio.sleep(0.2)
            with repo.transaction() as tx:
                for account in tx.auth_list("account:"):
                    service.expire(tx, account["owner"])

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(maintenance())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            for connection in list(service.connections.values()):
                await connection.close(1001)
            repo.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = service
    app.state.transport = transport

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def validation_error(request, exc):
        return response(fault=Fault("VALIDATION_FAILED"))

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return response(fault=Fault("NOT_FOUND" if exc.status_code == 404 else "VALIDATION_FAILED"))

    async def handle(request, operation, input_model, output_model, status):
        try:
            body = {}
            key = request.headers.get("idempotency-key", "")
            write = request.method == "POST"
            peer = request.client.host if request.client else "unknown"
            require(request.url.scheme == "https", "REMOTE_AUTH_REQUIRED")
            if write:
                require(1 <= len(key) <= 200)
            if operation not in {"pair_request", "pair_status"} and write:
                require(request.headers.get("origin") == settings.origin, "REMOTE_CSRF_REJECTED")
            if operation in {"login", "pair_request", "pair_status"}:
                security.rate(operation + ":" + peer)
            if write:
                raw = bytearray()
                async for chunk in request.stream():
                    raw.extend(chunk)
                    require(len(raw) <= 262144, "REMOTE_FRAME_TOO_LARGE")
                if raw:
                    body = json.loads(raw)
                require(isinstance(body, dict))
                if input_model:
                    validated(input_model, body)  # no injected defaults in request hash
                else:
                    require(not body)
            cookie = request.cookies.get(COOKIE)
            new_cookie, disconnect = None, None
            with repo.transaction() as tx:
                if operation == "login":
                    data, new_cookie = security.login(tx, body, key, cookie)
                elif operation == "session":
                    session = security.session(tx, cookie)
                    data = security.session_view(session) if session else dict(authenticated=False)
                elif operation in {"pair_request", "pair_status"}:
                    require(request.url.scheme == "https", "REMOTE_DEVICE_AUTH_FAILED")
                    secret, verifier = security.bearer(request.headers.get("authorization"))
                    if operation == "pair_request":
                        data = security.challenge(tx, secret, verifier, body, key)
                    else:
                        record = tx.auth_get("challenge:" + request.path_params["pairRequestId"])
                        require(record is not None and hmac.compare_digest(record["verifier"], verifier), "NOT_FOUND")
                        state = record["status"]
                        if state == "pending" and record["expires"] <= settings.clock():
                            state = "expired"
                        data = dict(pairRequestId=record["id"], workerId=record["workerId"], status=state, expiresAt=stamp(record["expires"]))
                else:
                    session = security.session(tx, cookie)
                    # Dedicated authenticated logout replay, not a command cache.
                    if operation == "logout" and session is None and cookie and "." in cookie:
                        sid = cookie.split(".")[0]
                        old = tx.auth_get("session:" + sid)
                        if old and hmac.compare_digest(security.token(sid), cookie) and old["expires"] > settings.clock() and old.get("logoutKey") == security.mac("logout", key):
                            session = old
                    require(session is not None, "REMOTE_AUTH_REQUIRED")
                    owner = session["owner"]
                    if write:
                        require(hmac.compare_digest(request.headers.get("x-csrf-token", ""), security.csrf(session["id"])), "REMOTE_CSRF_REJECTED")
                    service.expire(tx, owner)
                    if operation == "logout":
                        session.update(revoked=True, logoutKey=security.mac("logout", key))
                        tx.auth_put("session:" + session["id"], session, owner)
                        data = dict(authenticated=False)
                    else:
                        data = browser(tx, owner, operation, request, body, key)
                    if operation == "revoke":
                        disconnect = service.connections.get((owner, request.path_params["workerId"]))
                result = response(data, model=output_model, status=status)  # validate before commit
            if new_cookie:
                result.set_cookie(COOKIE, new_cookie, max_age=settings.session_ttl, path="/", secure=True, httponly=True, samesite="strict")
            if operation == "logout":
                result.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
            if disconnect:
                await disconnect.close(4403)
            LOG.info("operation=%s status=%d", operation, status)
            return result
        except Fault as exc:
            result = response(fault=exc)
            if exc.code == "REMOTE_RATE_LIMITED":
                result.headers["Retry-After"] = str(settings.rate_window)
            return result
        except (ValidationError, ValueError, TypeError, RecursionError):
            return response(fault=Fault("VALIDATION_FAILED"))
        except Exception:
            LOG.error("operation=%s error=INTERNAL", operation)
            return response(fault=Fault("INTERNAL"))

    def browser(tx, owner, operation, request, body, key):
        path = request.path_params
        resources = {"workerId": "device", "conversationId": "conversation", "runId": "run", "commandId": "command", "approvalId": "approval"}
        for name, kind in resources.items():
            if name in path:
                if operation == "control" and kind == "run":
                    require(tx.get(owner, "run", path[name]) is not None or tx.get(owner, "run-ref", path[name]) is not None, "NOT_FOUND")
                else:
                    service.get(tx, owner, kind, path[name])  # authorize before cache replay
        if operation == "confirm":
            challenge = tx.auth_get("challenge:" + path["pairRequestId"])
            require(challenge is not None and challenge.get("owner", owner) == owner, "NOT_FOUND")
        if operation == "preview":
            lookup = tx.auth_get("code:" + security.mac("pair-code", body["pairCode"]))
            challenge = tx.auth_get("challenge:" + lookup["id"]) if lookup else None
            require(challenge is None or challenge.get("owner", owner) == owner, "NOT_FOUND")
        if request.method == "POST":
            def action():
                if operation == "preview":
                    lookup = tx.auth_get("code:" + security.mac("pair-code", body["pairCode"]))
                    record = tx.auth_get("challenge:" + lookup["id"]) if lookup else None
                    require(record is None or record.get("owner", owner) == owner, "NOT_FOUND")
                    record = security.pairing_record(tx, body["pairCode"])
                    return dict(pairRequestId=record["id"], expiresAt=stamp(record["expires"]), **{k: record["device"][k] for k in ("deviceName", "platform", "architecture")})
                if operation == "confirm":
                    return service.confirm(tx, owner, path["pairRequestId"], body)
                if operation == "revoke":
                    return service.revoke(tx, owner, path["workerId"])
                if operation == "create_conversation":
                    return service.create_conversation(tx, owner, body)
                if operation == "send":
                    return service.send_message(tx, owner, path["conversationId"], body)
                if operation == "control":
                    return service.control(tx, owner, path["runId"], body)
                if operation == "withdraw":
                    return service.withdraw(tx, owner, path["commandId"], body)
                if operation == "decide":
                    return service.approval(tx, owner, path["approvalId"], body)
                raise Fault("NOT_FOUND")
            return service.replay(tx, owner, operation + ":" + json.dumps(path, sort_keys=True), key, body, action)
        if operation == "catalog":
            return service.get(tx, owner, "catalog", path["workerId"])
        if operation == "snapshot":
            return service.snapshot(tx, owner, path["conversationId"])
        query = request.query_params
        allowed = {"after", "limit"} if operation == "events" else {"cursor", "limit"} if operation in KINDS else set()
        require(set(query.keys()) <= allowed)
        limit = int(query.get("limit", "100" if operation == "events" else "50"))
        require(1 <= limit <= (200 if operation == "events" else 100))
        if operation == "events":
            return service.events(tx, owner, query.get("after"), limit)
        if operation in KINDS:
            return service.page(tx, owner, KINDS[operation][0], query.get("cursor"), limit, path.get("conversationId"))
        identifiers = {"device": "workerId", "conversation": "conversationId", "run": "runId", "command": "commandId", "approval": "approvalId"}
        return service.view(owner, operation, service.get(tx, owner, operation, path[identifiers[operation]]))

    for method, path, operation, input_model, output_model, status in ROUTES:
        def endpoint_factory(op, im, om, sc):
            async def endpoint(request: Request):
                if request.method == "POST" and op not in {"login", "pair_request"}:
                    try:
                        security.rate("write:" + (request.client.host if request.client else "unknown"))
                    except Fault as exc:
                        result = response(fault=exc)
                        result.headers["Retry-After"] = str(settings.rate_window)
                        return result
                return await handle(request, op, im, om, sc)
            return endpoint
        app.add_api_route("/api/v2" + path, endpoint_factory(operation, input_model, output_model, status), methods=[method], name=operation)

    @app.websocket("/ws/v2/worker")
    async def worker(socket: WebSocket):
        await transport.run(socket)

    if settings.static_dir:
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="h5")
    return app
