"""Cookie-authenticated local UI; no browser access to the legacy Hub token."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request
from protocol.generated.python import (
    AddWorkspaceInput, ApprovalResponseInput, CreateLocalConversationInput,
    LocalAgentModelsView, LocalAuthInput, LocalAuthView, LocalEventPage,
    SaveLocalSceneInput, SendLocalMessageInput, TaskActionInput,
)
from api.envelopes import success_response
from core.constants import PROTOCOL_VERSION
from core.errors import HubError
from core.local_auth import COOKIE_NAME, LocalBrowserAuth
from core.security import token_matches
from runtime.local_chat import LocalChatService


def install_local_routes(app: Any, service: LocalChatService, auth: LocalBrowserAuth,
                         ports: Any, events: Any, token: str) -> None:
    def authenticated(request: Request) -> bool:
        bearer = request.headers.get("authorization", "")
        return auth.valid(request.cookies.get(COOKIE_NAME)) or (
            bearer.startswith("Bearer ") and token_matches(bearer[7:], token)
        )

    def require_auth(request: Request) -> None:
        if not authenticated(request):
            raise HubError("UNAUTHORIZED", "请先输入本机连接码")

    def require_key(key: str | None) -> str:
        if not key or len(key) > 200:
            raise HubError("VALIDATION_FAILED", "必须提供Idempotency-Key")
        return key

    public = APIRouter(prefix="/api/v2/auth")

    @public.get("/status")
    async def status(request: Request):
        return success_response(LocalAuthView(authenticated=authenticated(request), protocol_version=PROTOCOL_VERSION))

    @public.post("/local-session")
    async def login(value: LocalAuthInput, request: Request):
        secret = auth.exchange(value.code)
        response = success_response(LocalAuthView(authenticated=True, protocol_version=PROTOCOL_VERSION))
        response.set_cookie(COOKIE_NAME, secret, max_age=auth.session_ttl, httponly=True,
                            samesite="strict", secure=request.url.scheme == "https", path="/")
        response.headers["Cache-Control"] = "no-store"
        return response

    @public.post("/logout", dependencies=[Depends(require_auth)])
    async def logout(request: Request):
        auth.logout(request.cookies.get(COOKIE_NAME))
        response = success_response(LocalAuthView(authenticated=False, protocol_version=PROTOCOL_VERSION))
        response.delete_cookie(COOKIE_NAME, path="/")
        return response

    app.include_router(public)
    router = APIRouter(prefix="/api/v2", dependencies=[Depends(require_auth)])

    @router.get("/bootstrap")
    async def bootstrap():
        return success_response(await app.state.local_bootstrap.build())

    @router.get("/agents")
    async def agents():
        return success_response(await ports.agents.list_agents())

    @router.post("/agents/discover")
    async def discover():
        return success_response(await ports.agents.discover())

    @router.get("/agents/{agent_id}/models")
    async def models(agent_id: str):
        # Runtime catalogs are optional: never present guesses as available models.
        items = await ports.agents.list_agents()
        view = next((a for a in items if a.id == agent_id), None)
        if view is None:
            raise HubError("NOT_FOUND", "Agent不存在")
        from runtime.repositories import AdapterDirectory
        adapter = AdapterDirectory(ports.agents).adapter_for(agent_id)
        query = getattr(adapter, "list_models", None)
        if query is not None:
            return success_response(await query(agent_id))
        return success_response(LocalAgentModelsView(agent_instance_id=agent_id, models=[], verified=False,
            reason="该Runtime未提供可验证的模型目录；可明确填写模型，执行时由Runtime验证"))

    @router.get("/workspaces")
    async def workspaces(search: str | None = None):
        return success_response(await ports.workspaces.list_workspaces(search, 200))

    @router.post("/workspaces")
    async def add_workspace(value: AddWorkspaceInput):
        return success_response(await ports.workspaces.add_workspace(value))

    @router.get("/scenes")
    async def scenes():
        return success_response(service.repository.scenes())

    @router.put("/scenes/{scene_id}")
    async def save_scene(scene_id: str, value: SaveLocalSceneInput):
        return success_response(service.repository.save_scene(scene_id, value))

    @router.get("/conversations")
    async def conversations():
        return success_response(service.repository.conversations())

    @router.post("/conversations")
    async def create_conversation(value: CreateLocalConversationInput,
                                  idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
        return success_response(await service.create_conversation(value, require_key(idempotency_key)), 201)

    @router.get("/conversations/{conversation_id}/messages")
    async def messages(conversation_id: str, after: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=200)):
        return success_response(service.repository.messages(conversation_id, after, limit))

    @router.post("/conversations/{conversation_id}/messages")
    async def send_message(conversation_id: str, value: SendLocalMessageInput,
                           idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
        return success_response(service.send(conversation_id, value, require_key(idempotency_key)), 202)

    @router.get("/conversations/{conversation_id}/runs")
    async def runs(conversation_id: str):
        return success_response([await service.run(row["run_id"]) for row in service.repository.runs(conversation_id)])

    @router.get("/runs/{run_id}")
    async def run(run_id: str):
        return success_response(await service.run(run_id))

    @router.post("/runs/{run_id}/commands")
    async def control(run_id: str, value: TaskActionInput,
                      idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
        return success_response(await service.control(run_id, value, require_key(idempotency_key)), 202)

    @router.get("/approvals")
    async def approvals(status: str | None = None, task_id: str | None = Query(None, alias="taskId")):
        return success_response(await ports.approvals.list_approvals({"status": status, "taskId": task_id}))

    @router.post("/approvals/{approval_id}/decisions")
    async def decide(approval_id: str, value: ApprovalResponseInput,
                     idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
        return success_response(await ports.approvals.respond(approval_id, value, require_key(idempotency_key)))

    @router.get("/sessions")
    async def sessions():
        return success_response(await ports.sessions.list_sessions({}))

    @router.get("/events")
    async def event_page(after: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=200)):
        page = events.page(after, limit)
        return success_response(LocalEventPage(events=page.events, next_seq=page.last_seq, has_more=page.has_more))

    app.include_router(router)
