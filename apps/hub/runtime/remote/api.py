"""Shared local remote-link handlers; mounting determines v1/v2 authentication."""
from fastapi import APIRouter, Header, Request
from protocol.generated.python import RemoteLinkPairingInput, RemoteSyncSettingsInput
from api.envelopes import success_response
from core.errors import HubError


def install_remote_routes(app, link, sync=None):
    router = APIRouter(prefix="/remote")

    def response(view):
        result = success_response(view)
        result.headers["Cache-Control"] = "no-store"
        return result

    @router.get("/link")
    async def get_link():
        return response(await link.view())

    @router.get("/sync-settings")
    async def get_sync_settings():
        return response(sync.settings())

    @router.put("/sync-settings")
    async def set_sync_settings(value: RemoteSyncSettingsInput,
                                idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
        return response(sync.set_settings(value, idempotency_key))

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

    app.include_router(router, prefix="/api/v1")
    return router
