from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from protocol.generated.python import (
    AcknowledgeUpdateResultInput,
    AppearanceSettings,
    ApprovalResponseInput,
    CreateTaskInput,
    HealthView,
    ResolveTeamProfileInput,
    ResumeSessionInput,
    SaveTeamProfileInput,
    TaskActionInput,
    UpdateActionInput,
    WsTicketRequest,
)

from api.envelopes import dump_model, error_response, success_response
from api.update_proxy import UpdateAgentProxy
from core.bootstrap import BootstrapService
from core.constants import APP_VERSION, MAX_EVENT_PAGE_SIZE, PROTOCOL_VERSION
from core.errors import FeatureUnavailable, HubError
from core.maintenance import DrainCoordinator, MaintenanceState
from core.ports import HubPorts
from core.security import WsTicketStore, token_matches
from runtime.paths import HubPaths
from storage.database import Database
from storage.events import EventStore
from storage.idempotency import IdempotencyRepository
from storage.settings import SettingsRepository


DEFAULT_ALLOWED_ORIGINS = frozenset(
    {
        "tauri://localhost",
        "https://tauri.localhost",
        "http://tauri.localhost",
        "http://localhost:1420",
        "http://127.0.0.1:1420",
    }
)


@dataclass(slots=True)
class HubApplication:
    app: FastAPI
    database: Database
    events: EventStore
    drain: DrainCoordinator
    settings: SettingsRepository
    update_proxy: UpdateAgentProxy
    token: str
    instance_id: str
    started_at: datetime


class LocalBoundaryMiddleware:
    def __init__(
        self,
        app: Any,
        token: str,
        allowed_origins: set[str] | frozenset[str],
        allowed_hosts: set[str] | frozenset[str],
    ) -> None:
        self.app = app
        self.token = token
        self.allowed_origins = allowed_origins
        self.allowed_hosts = allowed_hosts

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope["headers"]}
        host = headers.get("host", "").split(":", 1)[0].lower()
        origin = headers.get("origin")
        cors_headers: list[tuple[bytes, bytes]] = []
        if host not in self.allowed_hosts:
            await self._reject(send, HubError("UNAUTHORIZED", "请求来源未授权"))
            return
        if origin is not None:
            if origin not in self.allowed_origins:
                await self._reject(send, HubError("UNAUTHORIZED", "Origin 未授权"))
                return
            cors_headers = [
                (b"access-control-allow-origin", origin.encode("latin1")),
                (b"vary", b"Origin"),
                (b"access-control-allow-credentials", b"true"),
            ]
        if scope["method"] == "OPTIONS":
            requested_headers = headers.get("access-control-request-headers", "authorization,content-type,idempotency-key")
            response_headers = cors_headers + [
                (b"access-control-allow-methods", b"GET,POST,PUT,OPTIONS"),
                (b"access-control-allow-headers", requested_headers.encode("latin1")),
                (b"access-control-max-age", b"600"),
            ]
            await send({"type": "http.response.start", "status": 204, "headers": response_headers})
            await send({"type": "http.response.body", "body": b""})
            return
        if scope["path"] != "/healthz":
            authorization = headers.get("authorization", "")
            prefix = "Bearer "
            supplied = authorization[len(prefix) :] if authorization.startswith(prefix) else ""
            if not supplied or not token_matches(supplied, self.token):
                await self._reject(send, HubError("UNAUTHORIZED", "未授权"), cors_headers)
                return

        async def send_with_cors(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start" and cors_headers:
                message["headers"] = list(message.get("headers", [])) + cors_headers
            await send(message)

        await self.app(scope, receive, send_with_cors)

    @staticmethod
    async def _reject(
        send: Any,
        error: HubError,
        extra_headers: list[tuple[bytes, bytes]] | None = None,
    ) -> None:
        response = error_response(error)
        headers = [(key.encode("latin1"), value.encode("latin1")) for key, value in response.headers.items()]
        headers.extend(extra_headers or [])
        await send({"type": "http.response.start", "status": response.status_code, "headers": headers})
        await send({"type": "http.response.body", "body": response.body})


def create_application(
    *,
    paths: HubPaths,
    token: str,
    ports: HubPorts | None = None,
    instance_id: str | None = None,
    started_at: datetime | None = None,
    environment: str = "production",
    allowed_origins: set[str] | None = None,
    allowed_hosts: set[str] | None = None,
    close_database_on_shutdown: bool = True,
    update_agent_proxy: UpdateAgentProxy | None = None,
) -> HubApplication:
    paths.create()
    database = Database(paths.data / "hub.db")
    database.initialize()
    event_store = EventStore(database)
    settings = SettingsRepository(database, paths.data, paths.logs)
    update_proxy = update_agent_proxy or UpdateAgentProxy(paths.runtime / "update-agent.json")
    maintenance = MaintenanceState()
    resolved_ports = ports or HubPorts.unavailable_defaults()
    resolved_instance_id = instance_id or f"hub_{uuid.uuid4().hex}"
    resolved_started_at = started_at or datetime.now(timezone.utc)
    ticket_store = WsTicketStore()
    idempotency = IdempotencyRepository(database)
    drain = DrainCoordinator(database, event_store, resolved_ports.drain, maintenance, paths.backup, update_proxy)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if close_database_on_shutdown:
            database.close()

    app = FastAPI(title="HQAgent-Hub Local Hub", version=APP_VERSION, lifespan=lifespan)
    app.add_middleware(
        LocalBoundaryMiddleware,
        token=token,
        allowed_origins=allowed_origins or set(DEFAULT_ALLOWED_ORIGINS),
        allowed_hosts=allowed_hosts or {"127.0.0.1", "localhost"},
    )

    bootstrap = BootstrapService(
        resolved_ports,
        settings,
        event_store,
        update_proxy,
        resolved_instance_id,
        resolved_started_at,
        environment,
        maintenance,
    )

    @app.exception_handler(HubError)
    async def handle_hub_error(_request: Request, exc: HubError) -> JSONResponse:
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        detail = {"errors": exc.errors(include_url=False, include_context=False, include_input=False)}
        return error_response(HubError("VALIDATION_FAILED", "请求参数校验失败", detail=detail))

    @app.get("/healthz")
    async def health() -> JSONResponse:
        status = "maintenance" if maintenance.enabled else "ok"
        view = HealthView.model_validate(
            {
                "status": status,
                "appVersion": APP_VERSION,
                "protocolVersion": PROTOCOL_VERSION,
                "pid": os.getpid(),
                "startedAt": resolved_started_at.isoformat().replace("+00:00", "Z"),
            }
        )
        return JSONResponse(content=dump_model(view))

    @app.get("/api/v1/bootstrap")
    async def get_bootstrap() -> JSONResponse:
        return success_response(await bootstrap.build())

    @app.post("/api/v1/auth/ws-ticket")
    async def ws_ticket(value: WsTicketRequest | None = None) -> JSONResponse:
        purpose = value.purpose if value and value.purpose else "events"
        return success_response(ticket_store.issue(purpose))

    @app.get("/api/v1/agents")
    async def list_agents() -> JSONResponse:
        return success_response(await resolved_ports.agents.list_agents())

    @app.post("/api/v1/agents/discovery")
    async def discover_agents() -> JSONResponse:
        return success_response(await resolved_ports.agents.discover())

    @app.get("/api/v1/workspaces")
    async def list_workspaces(search: str | None = None, limit: int | None = None) -> JSONResponse:
        return success_response(await resolved_ports.workspaces.list_workspaces(search, limit))

    @app.get("/api/v1/team-profiles")
    async def list_team_profiles() -> JSONResponse:
        return success_response(await resolved_ports.team_profiles.list_profiles())

    @app.post("/api/v1/team-profiles/resolve")
    async def resolve_team_profile(value: ResolveTeamProfileInput) -> JSONResponse:
        return success_response(await resolved_ports.team_profiles.resolve(value))

    @app.get("/api/v1/team-profiles/{profile_id}")
    async def get_team_profile(profile_id: str) -> JSONResponse:
        return success_response(await resolved_ports.team_profiles.get_profile(profile_id))

    @app.put("/api/v1/team-profiles/{profile_id}")
    async def save_team_profile(profile_id: str, value: SaveTeamProfileInput) -> JSONResponse:
        return success_response(await resolved_ports.team_profiles.save_profile(profile_id, value))

    @app.get("/api/v1/tasks")
    async def list_tasks(
        page: int = 1,
        page_size: int = Query(50, alias="pageSize", ge=1, le=200),
        status: str | None = None,
        workspace_id: str | None = Query(None, alias="workspaceId"),
        search: str | None = None,
    ) -> JSONResponse:
        query = {"page": page, "pageSize": page_size, "status": status, "workspaceId": workspace_id, "search": search}
        return success_response(await resolved_ports.tasks.list_tasks(query))

    @app.post("/api/v1/tasks")
    async def create_task(
        value: CreateTaskInput,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ) -> JSONResponse:
        if maintenance.enabled:
            raise HubError("HUB_MAINTENANCE", "Local Hub 正在维护，暂不接受新任务")
        return success_response(await resolved_ports.tasks.create_task(value, idempotency_key))

    @app.get("/api/v1/tasks/{task_id}")
    async def get_task(task_id: str) -> JSONResponse:
        return success_response(await resolved_ports.tasks.get_task(task_id))

    @app.post("/api/v1/tasks/{task_id}/actions")
    async def task_action(
        task_id: str,
        value: TaskActionInput,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ) -> JSONResponse:
        return success_response(await resolved_ports.tasks.act(task_id, value, idempotency_key))

    @app.get("/api/v1/sessions")
    async def list_sessions(
        workspace_id: str | None = Query(None, alias="workspaceId"),
        task_id: str | None = Query(None, alias="taskId"),
        only_valid: bool | None = Query(None, alias="onlyValid"),
        page: int = 1,
        page_size: int = Query(50, alias="pageSize", ge=1, le=200),
    ) -> JSONResponse:
        return success_response(
            await resolved_ports.sessions.list_sessions(
                {"workspaceId": workspace_id, "taskId": task_id, "onlyValid": only_valid, "page": page, "pageSize": page_size}
            )
        )

    @app.post("/api/v1/sessions/{session_id}/resume")
    async def resume_session(session_id: str, value: ResumeSessionInput) -> JSONResponse:
        return success_response(await resolved_ports.sessions.resume(session_id, value))

    @app.get("/api/v1/approvals")
    async def list_approvals(status: str | None = None, task_id: str | None = Query(None, alias="taskId")) -> JSONResponse:
        return success_response(await resolved_ports.approvals.list_approvals({"status": status, "taskId": task_id}))

    @app.post("/api/v1/approvals/{approval_id}/response")
    async def respond_approval(
        approval_id: str,
        value: ApprovalResponseInput,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ) -> JSONResponse:
        return success_response(await resolved_ports.approvals.respond(approval_id, value, idempotency_key))

    @app.get("/api/v1/settings")
    async def get_settings() -> JSONResponse:
        return success_response(settings.get_all())

    @app.put("/api/v1/settings/appearance")
    async def set_appearance(
        value: AppearanceSettings,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ) -> JSONResponse:
        raw = value.model_dump(mode="json", by_alias=True)
        result = idempotency.execute(
            idempotency_key,
            "/api/v1/settings/appearance",
            raw,
            lambda transaction: dump_model(settings.set_appearance_in_transaction(transaction, value)),
        )
        return success_response(result)

    async def proxy_state_after(method: str, path: str, body: Any | None = None) -> Any:
        result = await update_proxy.request(method, path, body)
        if result is None:
            result = await update_proxy.request("GET", "/internal/v1/state")
        return result

    @app.get("/api/v1/updates/state")
    async def update_state() -> JSONResponse:
        return success_response(await update_proxy.request("GET", "/internal/v1/state"))

    @app.post("/api/v1/updates/check")
    async def update_check() -> JSONResponse:
        return success_response(await proxy_state_after("POST", "/internal/v1/check"))

    @app.post("/api/v1/updates/download")
    async def update_download() -> JSONResponse:
        return success_response(await proxy_state_after("POST", "/internal/v1/download"))

    @app.post("/api/v1/updates/cancel")
    async def update_cancel() -> JSONResponse:
        return success_response(await proxy_state_after("POST", "/internal/v1/cancel"))

    @app.post("/api/v1/updates/install")
    async def update_install(value: UpdateActionInput | None = None) -> JSONResponse:
        await drain.start()
        return success_response(
            await proxy_state_after("POST", "/internal/v1/install", dump_model(value) if value else None)
        )

    @app.post("/api/v1/updates/defer")
    async def update_defer(_value: UpdateActionInput) -> JSONResponse:
        raise FeatureUnavailable("updates.defer", "冻结的 Update Agent 私有协议未定义 defer 路径")

    @app.get("/api/v1/updates/releases")
    async def update_releases() -> JSONResponse:
        return success_response(await update_proxy.request("GET", "/internal/v1/releases"))

    @app.get("/api/v1/updates/result")
    async def update_result() -> JSONResponse:
        return success_response(await update_proxy.request("GET", "/internal/v1/result"))

    @app.post("/api/v1/updates/result/acknowledge")
    async def acknowledge_update(_value: AcknowledgeUpdateResultInput | None = None) -> JSONResponse:
        raise FeatureUnavailable("updates.result.acknowledge", "冻结的 Update Agent 私有协议未定义 acknowledge 路径")

    @app.get("/api/v1/events")
    async def get_events(after: int = Query(..., ge=0), limit: int = Query(200, ge=1, le=MAX_EVENT_PAGE_SIZE)) -> JSONResponse:
        return success_response(event_store.page(after, limit))

    @app.websocket("/api/v1/events/stream")
    async def event_stream(websocket: WebSocket, ticket: str, after: int | None = Query(None, ge=0)) -> None:
        host = websocket.headers.get("host", "").split(":", 1)[0].lower()
        origin = websocket.headers.get("origin")
        valid_boundary = host in (allowed_hosts or {"127.0.0.1", "localhost"}) and (
            origin is None or origin in (allowed_origins or set(DEFAULT_ALLOWED_ORIGINS))
        )
        if not valid_boundary or not ticket_store.consume(ticket):
            await websocket.close(code=4401)
            return
        try:
            async with event_store.broker.subscribe() as queue:
                replay = event_store.page(after if after is not None else event_store.latest_seq(), MAX_EVENT_PAGE_SIZE)
                await websocket.accept()
                last_sent = after or 0
                for event in replay.events:
                    await websocket.send_json(dump_model(event))
                    last_sent = event.seq
                while True:
                    event = await queue.get()
                    if event.seq > last_sent:
                        await websocket.send_json(dump_model(event))
                        last_sent = event.seq
        except WebSocketDisconnect:
            return
        except HubError:
            await websocket.close(code=4410)

    @app.post("/internal/maintenance")
    async def set_maintenance(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        enabled = bool(body.get("enabled", True))
        drain.set_maintenance(enabled, str(body.get("reason", "")))
        return success_response({"maintenance": maintenance.enabled, "reason": maintenance.reason})

    @app.get("/internal/drain/state")
    async def drain_state() -> JSONResponse:
        return success_response(drain.progress)

    @app.post("/internal/drain/start")
    async def drain_start(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        result = await drain.start(
            timeout_seconds=float(body.get("timeoutSeconds", 30)),
            desktop_pid=body.get("desktopPid"),
            update_agent_pid=body.get("updateAgentPid"),
        )
        return success_response(result)

    @app.post("/internal/backup/database")
    async def backup_database() -> JSONResponse:
        backup = await drain.backup_database()
        return success_response({"backupPath": str(backup), "backupCompleted": True})

    return HubApplication(
        app=app,
        database=database,
        events=event_store,
        drain=drain,
        settings=settings,
        update_proxy=update_proxy,
        token=token,
        instance_id=resolved_instance_id,
        started_at=resolved_started_at,
    )
