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

from .common import Fault, require, stamp, uid, validated
from .config import Settings
from .events_sync import SyncEvents
from .repository import Repository
from .security import COOKIE, Security
from .service import KINDS
from .service_sync import SyncService
from .worker import WorkerTransport
from .static import SPAStaticFiles
from .http import RequestAudit, response
from .public_contract import OPENAPI
from .queries import QueryPlan
from .http import CONTEXT

LOG = logging.getLogger("hqremote")
MAINTENANCE_INTERVAL = 5


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
    ("PATCH", "/devices/{workerId}", "patch_device", "RemoteDevicePatchInput", "RemoteDeviceView", 200),
    ("DELETE", "/devices/{workerId}", "delete_device", None, "RemoteDeviceDeletionView", 200),
    ("POST", "/devices/{workerId}/revocations", "revoke", "RemoteDeviceRevokeInput", "RemoteDeviceRevocationView", 200),
    ("GET", "/devices/{workerId}/catalog", "catalog", None, "RemoteV3CatalogView", 200),
    ("GET", "/conversations", "conversations", None, "RemoteConversationPage", 200),
    ("POST", "/conversations", "create_conversation", "RemoteCreateConversationInput", "RemoteQueuedReceipt", 202),
    ("GET", "/conversations/{conversationId}", "conversation", None, "RemoteConversationView", 200),
    ("PATCH", "/conversations/{conversationId}", "update_conversation", "RemoteSyncConversationInput", "RemoteQueuedReceipt", 202),
    ("POST", "/conversations/{conversationId}/messages", "send", "RemoteSendMessageInput", "RemoteQueuedReceipt", 202),
    ("GET", "/conversations/{conversationId}/messages", "messages", None, "RemoteSyncMessagePage", 200),
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
    ("POST", "/api-tokens", "issue_token", "RemoteApiTokenCreateInput", "RemoteApiTokenIssuedView", 201),
    ("GET", "/api-tokens", "tokens", None, "RemoteApiTokenPage", 200),
    ("DELETE", "/api-tokens/{tokenId}", "revoke_token", None, "RemoteApiTokenRevocationView", 200),
    ("GET", "/openapi.json", "openapi", None, None, 200),
    ('GET', '/devices/{workerId}/native-sessions', 'native_list', None, 'RemoteNativeSessionPage', 200),
    ('GET', '/native-sessions/{nativeSessionId}', 'native_detail', None, 'RemoteNativeSessionView', 200),
    ('GET', '/native-sessions/{nativeSessionId}/messages', 'native_read', None, 'NativeMessagePage', 200),
    ('POST', '/native-sessions/{nativeSessionId}/imports', 'native_import', 'RemoteNativeImportInput', 'RemoteResourceQueuedReceipt', 202),
    ('POST', '/devices/{workerId}/directory-listings', 'directory_list', 'DirectoryListingInput', 'DirectoryListingPage', 200),
    ('POST', '/devices/{workerId}/workspaces', 'workspace_register', 'RemoteWorkspaceRegisterInput', 'RemoteResourceQueuedReceipt', 202),
]


def create_app(settings=None):
    protect_transport_logs()
    settings = settings or Settings.from_env()
    repo = Repository(settings.database)
    security = Security(repo, settings)
    service = SyncService(repo, settings, security)
    transport = WorkerTransport(service, SyncEvents(service))

    async def maintenance():
        while True:
            await asyncio.sleep(MAINTENANCE_INTERVAL)
            service.maintain()

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
    app.add_middleware(RequestAudit, security=security, settings=settings, static=bool(settings.static_dir))

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
            write = request.method in {"POST", "PATCH", "DELETE"}
            peer = request.client.host if request.client else "unknown"
            require(request.url.scheme == "https", "REMOTE_AUTH_REQUIRED")
            authorization = request.headers.get('authorization')
            pat = authorization is not None and operation not in {'pair_request', 'pair_status'}
            if pat:
                # Persist lastUsedAt even when a subsequently authorized business
                # operation fails. Revalidate in its write transaction below.
                with repo.transaction() as tx:
                    security.authenticate_pat(tx, authorization, operation, touch=True)
            if write and operation not in {'login', 'pair_request'} and not pat:
                security.rate('write:' + peer)
            if write:
                require(1 <= len(key) <= 200)
            if operation not in {"pair_request", "pair_status"} and write and not pat:
                require(request.headers.get("origin") == settings.origin, "REMOTE_CSRF_REJECTED")
            if operation in {"login", "pair_request", "pair_status"}:
                security.rate(operation + ":" + peer)
            if write:
                raw = bytearray()
                async for chunk in request.stream():
                    raw.extend(chunk)
                    require(len(raw) <= 262144, "REMOTE_FRAME_TOO_LARGE")
                if raw:
                    try:
                        body = json.loads(raw)
                    except (ValueError, RecursionError):
                        raise Fault('BAD_REQUEST') from None
                require(isinstance(body, dict))
                if input_model:
                    validated(input_model, body)  # no injected defaults in request hash
                else:
                    require(not body)
            contract = request.state.contract_operation
            allowed_query = {p['name'] for p in contract.get('parameters', []) if p['in'] == 'query'} if contract else set()
            require(set(request.query_params) <= allowed_query)
            require(len(request.query_params.multi_items()) == len(request.query_params))
            if operation == 'openapi':
                return JSONResponse(OPENAPI, headers={'Cache-Control': 'no-store'})
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
                    if pat:
                        identity = security.authenticate_pat(tx, authorization, operation)
                        owner = identity['owner']
                        request.state.audience = identity['tokenId']
                    else:
                        require(session is not None, "REMOTE_AUTH_REQUIRED")
                        owner = session['owner']
                        request.state.audience = 'cookie'
                    if write and not pat:
                        require(hmac.compare_digest(request.headers.get("x-csrf-token", ""), security.csrf(session["id"])), "REMOTE_CSRF_REJECTED")
                    if operation == "logout":
                        session.update(revoked=True, logoutKey=security.mac("logout", key))
                        tx.auth_put("session:" + session["id"], session, owner)
                        data = dict(authenticated=False)
                    else:
                        data = browser(tx, owner, operation, request, body, key)
                    if operation in {"revoke", 'delete_device'}:
                        disconnect = service.connections.get((owner, request.path_params["workerId"]))
                if operation == 'issue_token' and not data['secretAvailable']:
                    output_model, status = 'RemoteApiTokenIssueReplayView', 200
                result = None if isinstance(data, QueryPlan) else response(data, model=output_model, status=status)
            if isinstance(data, QueryPlan):
                value = await service.queries.execute(data, request)
                return response(value, model=output_model, status=status)
            if new_cookie:
                result.set_cookie(COOKIE, new_cookie, max_age=settings.session_ttl, path="/", secure=True, httponly=True, samesite="strict")
            if operation == "logout":
                result.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
            if disconnect:
                await disconnect.close(4403)
            return result
        except Fault as exc:
            result = response(fault=exc)
            if exc.code == "REMOTE_RATE_LIMITED":
                result.headers["Retry-After"] = str(settings.rate_window)
            return result
        except (ValidationError, ValueError, TypeError, RecursionError):
            return response(fault=Fault("VALIDATION_FAILED"))
        except Exception:
            return response(fault=Fault("INTERNAL"))

    def browser(tx, owner, operation, request, body, key):
        path = request.path_params
        resources = {"workerId": "device", "conversationId": "conversation", "runId": "run", "commandId": "command", "approvalId": "approval", 'nativeSessionId':'native-index'}
        workers = set()
        for name, kind in resources.items():
            if name in path:
                if operation == "control" and kind == "run":
                    value = tx.get(owner, "run", path[name]) or tx.get(owner, "run-ref", path[name])
                    require(value is not None, "NOT_FOUND")
                    service.browser_get(tx, owner, 'conversation', value['conversationId'])
                elif kind == 'native-index' and operation in {'native_detail', 'native_read'}:
                    value = service.native_get(tx, owner, path[name], check_sync=True)
                else:
                    value = service.browser_get(tx, owner, kind, path[name])  # authorize before cache replay
                workers.add(value.get("targetWorkerId", value.get("workerId", value.get("_worker"))))
        for worker in workers:
            if worker:
                service.expire(tx, owner, worker)
        if operation in {'create_conversation', 'update_conversation', 'send', 'control', 'withdraw', 'decide'}:
            if operation == 'create_conversation':
                workers.add(body['targetWorkerId'])
            exempt = (operation == 'control' and body['action'] == 'cancel') or (operation == 'decide' and body['decision'] == 'reject')
            for worker in workers:
                if worker:
                    device = service.get(tx, owner, 'device', worker)
                    require(device['status'] != 'revoked', 'REMOTE_DEVICE_REVOKED')
                    require(exempt or device.get('remoteAccess', 'enabled') != 'suspended', 'REMOTE_DEVICE_SUSPENDED')
        if operation == 'patch_device':
            require(value['status'] != 'revoked', 'REMOTE_DEVICE_REVOKED')
        if operation == 'revoke_token':
            require(tx.get(owner, 'api-token', path['tokenId']) is not None, 'NOT_FOUND')
        if operation == 'issue_token':
            return security.issue_pat(tx, owner, body, key)
        if operation == 'delete_device':
            return service.delete_device(tx, owner, path['workerId'])
        if operation in {'native_read','directory_list'}:
            return service.query_plan(tx, owner, operation, path, body, request.query_params, key, CONTEXT.get()['requestId'])
        if operation == 'native_list':
            return service.native_page(tx, owner, path['workerId'], request.query_params)
        if operation == 'native_detail':
            return service.native_view(owner, service.native_get(tx, owner, path['nativeSessionId'], check_sync=True))
        if operation in {'native_import','workspace_register'}:
            worker = value['workerId']
            service.r3_ready(tx, owner, worker)
        if operation == "confirm":
            challenge = tx.auth_get("challenge:" + path["pairRequestId"])
            require(challenge is not None and challenge.get("owner", owner) == owner, "NOT_FOUND")
        if operation == "preview":
            lookup = tx.auth_get("code:" + security.mac("pair-code", body["pairCode"]))
            challenge = tx.auth_get("challenge:" + lookup["id"]) if lookup else None
            require(challenge is None or challenge.get("owner", owner) == owner, "NOT_FOUND")
        if request.method in {"POST", "PATCH", "DELETE"}:
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
                if operation == 'patch_device':
                    return service.patch_device(tx, owner, path['workerId'], body)
                if operation == 'revoke_token':
                    return security.revoke_pat(tx, owner, path['tokenId'])
                if operation == 'native_import':
                    return service.import_native(tx, owner, path['nativeSessionId'], body, CONTEXT.get()['requestId'])
                if operation == 'workspace_register':
                    return service.register_workspace(tx, owner, path['workerId'], body, CONTEXT.get()['requestId'])
                if operation == "create_conversation":
                    return service.create_conversation(tx, owner, body)
                if operation == "update_conversation":
                    return service.update_conversation(tx, owner, path['conversationId'], body)
                if operation == "send":
                    return service.send_message(tx, owner, path["conversationId"], body)
                if operation == "control":
                    return service.control(tx, owner, path["runId"], body)
                if operation == "withdraw":
                    return service.withdraw(tx, owner, path["commandId"], body)
                if operation == "decide":
                    return service.approval(tx, owner, path["approvalId"], body)
                raise Fault("NOT_FOUND")
            audience = request.state.audience
            scope = operation + ':' + json.dumps(path, sort_keys=True)
            if audience != 'cookie':
                scope += ':pat:' + audience
            return service.replay(tx, owner, scope, key, body, action)
        if operation == "catalog":
            catalog = tx.get(owner, 'catalog', path['workerId'])
            require(catalog is not None, 'FEATURE_UNAVAILABLE' if service.online(owner, path['workerId']) else 'REMOTE_DEVICE_OFFLINE')
            return catalog
        if operation == "snapshot":
            return service.snapshot(tx, owner, path["conversationId"])
        query = request.query_params
        allowed = {"after", "limit"} if operation == "events" else {"cursor", "limit"} if operation in KINDS else set()
        if operation == 'messages':
            allowed = {'before', 'limit'}
        if operation == 'conversations':
            allowed |= {'workerId', 'workspaceId'}
        if operation == 'devices':
            allowed |= {'remoteAccess', 'online', 'includeRevoked'}
        if operation == 'tokens':
            allowed = {'cursor', 'limit', 'includeRevoked'}
        require(set(query.keys()) <= allowed)
        limit = int(query.get("limit", "100" if operation == "events" else "50"))
        require(1 <= limit <= (200 if operation == "events" else 100))
        def boolean(name, default=None):
            if name not in query:
                return default
            require(query[name] in {'true', 'false'})
            return query[name] == 'true'
        if operation == 'devices' and hasattr(service, 'devices'):
            access = query.get('remoteAccess')
            require(access is None or access in {'enabled', 'suspended'})
            filters = dict(remoteAccess=access, online=boolean('online'), includeRevoked=boolean('includeRevoked', False))
            return service.devices(tx, owner, query.get('cursor'), limit, filters, request.state.audience)
        if operation == 'tokens':
            return security.list_pats(tx, service, owner, query.get('cursor'), limit, boolean('includeRevoked', False))
        if operation == "events":
            return service.events(tx, owner, query.get("after"), limit)
        if operation == 'messages':
            return service.messages(tx, owner, path['conversationId'], query.get('before'), limit)
        if operation == 'conversations':
            return service.conversations(tx, owner, query.get('cursor'), limit, query.get('workerId'), query.get('workspaceId'))
        if operation in KINDS:
            return service.page(tx, owner, KINDS[operation][0], query.get("cursor"), limit, path.get("conversationId"))
        identifiers = {"device": "workerId", "conversation": "conversationId", "run": "runId", "command": "commandId", "approval": "approvalId"}
        return service.view(owner, operation, service.get(tx, owner, operation, path[identifiers[operation]]))

    for method, path, operation, input_model, output_model, status in ROUTES:
        def endpoint_factory(op, im, om, sc):
            async def endpoint(request: Request):
                return await handle(request, op, im, om, sc)
            return endpoint
        app.add_api_route("/api/v2" + path, endpoint_factory(operation, input_model, output_model, status), methods=[method], name=operation)

    @app.websocket("/ws/v2/worker")
    async def worker(socket: WebSocket):
        await transport.run(socket)

    if settings.static_dir:
        app.mount("/", SPAStaticFiles(directory=settings.static_dir, html=True), name="h5")
    return app
