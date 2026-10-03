"""The same local maintenance operations under the two authentication surfaces."""
import json
import re
import uuid
from fastapi import APIRouter, Depends, Header, Query, Request
from protocol.generated.python import (StartLocalImageVerificationInput,
    CancelLocalImageVerificationInput, LocalConversationDeletionView)
from api.envelopes import success_response
from core.errors import HubError


def maintenance_path(path, method):
    return '/agents/image-verification' in path or (
        method == 'DELETE' and re.fullmatch(r'/api/v[12]/conversations/[^/]+', path))


class MaintenanceBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not maintenance_path(scope['path'], scope['method']):
            return await self.app(scope, receive, send)
        supplied = dict(scope['headers']).get(b'x-request-id', b'').decode('latin1')
        identifier = supplied if re.fullmatch(r'[A-Za-z0-9._:-]{1,160}', supplied) else 'req_' + uuid.uuid4().hex
        scope.setdefault('state', {})['maintenance_request_id'] = identifier
        start, bodies = None, []
        async def wrapped(message):
            nonlocal start
            if message['type'] == 'http.response.start':
                start = message
            elif message['type'] == 'http.response.body':
                bodies.append(message.get('body', b''))
                if message.get('more_body'):
                    return
                body = b''.join(bodies)
                try:
                    value = json.loads(body)
                    if isinstance(value, dict):
                        value['requestId'] = identifier
                        body = json.dumps(value, ensure_ascii=False).encode()
                except (ValueError, UnicodeDecodeError):
                    pass
                headers = [(k, v) for k, v in start.get('headers', [])
                           if k.lower() not in {b'cache-control', b'x-request-id', b'content-length'}]
                headers.extend([(b'cache-control', b'no-store'), (b'x-request-id', identifier.encode()),
                                (b'content-length', str(len(body)).encode())])
                await send({**start, 'headers': headers})
                await send({**message, 'body': body})
            else:
                await send(message)
        await self.app(scope, receive, wrapped)


def maintenance_router(service):
    def origin(request: Request):
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and not request.headers.get('origin'):
            raise HubError('ORIGIN_NOT_ALLOWED', '本机维护写请求必须提供可信Origin')
    router = APIRouter(dependencies=[Depends(origin)])
    coordinator = service.verifications

    def key(value):
        if not value or len(value) > 200:
            raise HubError('VALIDATION_FAILED', '必须提供Idempotency-Key')
        return value

    @router.get('/agents/image-verifications')
    async def matrix(agentId: str | None = None, modelId: str | None = None,
                     includeInactiveModels: bool = False, cursor: str | None = None,
                     limit: int = Query(50, ge=1, le=100)):
        if modelId is not None:
            if not agentId:
                raise HubError('VALIDATION_FAILED', '查询型号必须指定Agent')
            try:
                StartLocalImageVerificationInput.model_validate(dict(agentId=agentId, modelId=modelId,
                    expectedTargetRevision='query', acknowledgeModelUsage=True))
            except ValueError:
                raise HubError('VALIDATION_FAILED', '模型选择器无效') from None
        return success_response(await coordinator.matrix(agentId, modelId, includeInactiveModels, cursor, limit))

    @router.post('/agents/image-verification-jobs')
    async def start(value: StartLocalImageVerificationInput, request: Request,
                    idempotency_key: str | None = Header(None, alias='Idempotency-Key')):
        if (await request.json()).get('acknowledgeModelUsage') is not True:
            raise HubError('VALIDATION_FAILED', '必须明确确认本次模型用量')
        return success_response(await coordinator.start(value, key(idempotency_key),
            request.state.maintenance_request_id), 202)

    @router.get('/agents/image-verification-jobs/{job_id}')
    async def get(job_id: str):
        return success_response(await coordinator.get(job_id))

    @router.post('/agents/image-verification-jobs/{job_id}/cancellations')
    async def cancel(job_id: str, value: CancelLocalImageVerificationInput,
                     idempotency_key: str | None = Header(None, alias='Idempotency-Key')):
        job, status = await coordinator.cancel(job_id, key(idempotency_key))
        return success_response(job, status)

    @router.delete('/conversations/{conversation_id}')
    async def delete(conversation_id: str, request: Request,
                     expectedVersion: int = Query(..., ge=1, le=9007199254740991),
                     idempotency_key: str | None = Header(None, alias='Idempotency-Key')):
        if not re.fullmatch(r'[1-9][0-9]*', request.query_params.get('expectedVersion', '')):
            raise HubError('VALIDATION_FAILED', 'expectedVersion必须为正安全整数')
        if await request.body():
            raise HubError('VALIDATION_FAILED', '删除对话不接受请求体')
        result = await service.chat.delete_conversation(conversation_id, expectedVersion, key(idempotency_key))
        return success_response(LocalConversationDeletionView.model_validate(result))

    return router
