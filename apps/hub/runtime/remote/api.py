"""v1 routes inherit the existing Hub boundary middleware."""
from fastapi import APIRouter, Header, Request
from protocol.generated.python import RemoteLinkPairingInput
from api.envelopes import success_response
from core.errors import HubError


def install_remote_routes(app, link):
    router = APIRouter(prefix="/api/v1/remote")

    def response(view):
        result = success_response(view)
        result.headers["Cache-Control"] = "no-store"
        return result

    @router.get("/link")
    async def get_link():
        return response(await link.view())

    @router.post("/pairing")
    async def pair(request: Request, idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
        try:
            raw = await request.json()
            # Origin is parsed before strict DTO validation, so invalid origins
            # return the frozen D43 error instead of a generic validation code.
            from runtime.remote.security import normalize_origin
            if not isinstance(raw, dict) or not isinstance(raw.get("serverOrigin"), str):
                raise ValueError()
            raw["serverOrigin"] = normalize_origin(raw["serverOrigin"], development=link.development)
            value = RemoteLinkPairingInput.model_validate(raw)
        except HubError:
            raise
        except Exception:
            raise HubError("VALIDATION_FAILED", "配对请求参数无效") from None
        return response(await link.pair(value, idempotency_key))

    @router.delete("/pairing")
    async def cancel(idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
        return response(await link.clear(idempotency_key))

    @router.post("/unlink")
    async def unlink(idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
        return response(await link.clear(idempotency_key, unlink=True))

    app.include_router(router)
