"""Identical local Bearer/Cookie attachment APIs, with raw bounded streams."""
import httpx
from urllib.parse import quote
from fastapi import APIRouter, Header, Request
from fastapi.responses import Response, StreamingResponse
from api.envelopes import success_response
from core.errors import HubError
from runtime.attachments.content import CHUNK, LIMITS
from storage.local_chat import uid

def attachment_router(service):
    router = APIRouter()
    library = service.library

    def envelope(value, status=200):
        result = success_response(value, status_code=status)
        result.headers['Cache-Control'] = 'no-store'
        return result

    def binary_headers(name, size):
        return {'Content-Disposition': "attachment; filename*=UTF-8''" + quote(name, safe=''), 'Content-Length': str(size), 'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store', 'X-Request-Id': uid('request')}

    @router.get('/attachments/limits')
    async def limits():
        return envelope(LIMITS)

    @router.post('/conversations/{conversation_id}/attachments')
    async def upload(conversation_id: str, request: Request):
        return envelope(await library.upload(conversation_id, request), 201)

    @router.get('/attachments/{attachment_id}')
    async def info(attachment_id: str):
        return envelope(library.repo.view(attachment_id))

    @router.delete('/attachments/{attachment_id}')
    async def remove(attachment_id: str, key: str | None=Header(None, alias='Idempotency-Key')):
        if not key or len(key) > 200:
            raise HubError('VALIDATION_FAILED', '必须提供Idempotency-Key')
        return envelope(await service.worker.native.io(library.delete, attachment_id))

    @router.get('/attachments/{attachment_id}/content')
    async def content(attachment_id: str, request: Request):
        if 'range' in request.headers:
            raise HubError('BAD_REQUEST', '本期不支持Range')
        row = library.repo.row(attachment_id)
        path = await service.worker.native.io(library.check, row)
        metadata = library.repo.view(attachment_id).attachment

        def chunks():
            with open(path, 'rb') as stream:
                library.streams.setdefault(attachment_id, set()).add(stream)
                try:
                    while True:
                        library.repo.row(attachment_id)
                        data = stream.read(CHUNK)
                        if not data:
                            break
                        yield data
                finally:
                    library.streams[attachment_id].discard(stream)
        return StreamingResponse(chunks(), media_type='application/octet-stream', headers=binary_headers(metadata.file_name, metadata.size_bytes))

    @router.get('/attachments/{attachment_id}/thumbnail')
    async def thumbnail(attachment_id: str, request: Request):
        if 'range' in request.headers:
            raise HubError('BAD_REQUEST', '本期不支持Range')
        try:
            body = await library.thumbnail(attachment_id)
        except (httpx.HTTPError, TimeoutError):
            raise HubError('ATTACHMENT_THUMBNAIL_UNAVAILABLE', '服务端缩略图暂不可用') from None
        return Response(body, media_type='image/png', headers=binary_headers('thumbnail.png', len(body)))

    @router.get('/conversations/{conversation_id}/attachment-capabilities')
    async def capabilities(conversation_id: str):
        await service.capabilities.refresh()
        return envelope(service.capabilities.target(conversation_id))
    return router
