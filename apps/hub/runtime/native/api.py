from fastapi import APIRouter, Header, Query, Request, Path
from fastapi.responses import JSONResponse
import json
from protocol.generated.python import RemoteNativeImportInput, RuntimeNativeAgentType
from api.envelopes import success_response
from core.errors import HubError
from storage.local_chat import uid


def native_router(service):
    router = APIRouter(prefix="/native-sessions")

    @router.get("")
    async def listing(workspace_id: str | None = Query(None, alias="workspaceId"),
                      agent_type: RuntimeNativeAgentType | None = Query(None, alias="agentType"), cursor: str | None = Query(None,min_length=16,max_length=4096),
                      limit: int = Query(50, ge=1, le=100)):
        if str(agent_type) == 'pi':
            raise HubError('NATIVE_SESSION_UNSUPPORTED', 'PI原生读取属于第二期，当前读取器尚未实现', detail={'reason': 'reader_not_implemented'})
        return success_response(await service.listing(workspace_id, agent_type, cursor, limit))

    @router.get("/{identifier}")
    async def detail(identifier: str = Path(min_length=1,max_length=160)):
        return success_response(await service.detail(identifier))

    @router.get("/{identifier}/messages")
    async def read(identifier: str = Path(min_length=1,max_length=160), source_revision: str | None = Query(None, alias="sourceRevision",pattern="^[0-9a-f]{64}$"),
                   before: str | None = Query(None,min_length=16,max_length=4096), limit: int = Query(50, ge=1, le=100)):
        return success_response(await service.read(identifier, revision=source_revision, before=before, limit=limit))

    @router.post("/{identifier}/imports")
    async def adopt(identifier: str, value: RemoteNativeImportInput, request: Request,
                    key: str | None = Header(None, alias="Idempotency-Key")):
        if not request.headers.get("origin"):
            raise HubError("ORIGIN_NOT_ALLOWED", "本机原生导入必须提供可信Origin")
        if not key or len(key)>200:
            raise HubError("VALIDATION_FAILED", "必须提供合法Idempotency-Key")
        request_id = uid("request")
        view = await service.import_session(identifier, value, key, request_id)
        response = success_response(view, status_code=201)
        body = json.loads(response.body)
        body["requestId"] = request_id
        return JSONResponse(body,status_code=201,headers={"X-Request-Id":request_id})

    return router
