"""Credential-independent request correlation and sanitized completion records."""
import json
import logging
import re
import time
from contextvars import ContextVar

from protocol.generated.python import ApiEnvelope, PROTOCOL_VERSION
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

from .common import Fault, require, uid, validated
from .public_contract import OPENAPI
from .security import COOKIE

CONTEXT = ContextVar('remote_http_request', default=None)
LOG = logging.getLogger('hqremote')
CLIENT_ID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z')
OPERATIONS = [(method.upper(), re.compile('[^/]+'.join(re.escape(part) for part in re.split(r'\{[^}]+\}', path)) + r'\Z'), op)
              for path, methods in OPENAPI['paths'].items() for method, op in methods.items()]


def response(data=None, *, model=None, fault=None, status=200):
    context = CONTEXT.get()
    identifier = context['requestId'] if context else uid()
    envelope = dict(success=fault is None, requestId=identifier, protocolVersion=PROTOCOL_VERSION)
    headers = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'X-Request-Id': identifier}
    if fault:
        envelope['error'] = fault.http_view()
        status = fault.status
        if context is not None:
            context['errorCode'] = fault.code
        if fault.code == 'REMOTE_RATE_LIMITED':
            headers['Retry-After'] = '60'
    else:
        if model not in {'RemotePairingChallenge', 'RemotePairingStatusView'}:
            from .client_features import legacy_request, legacy_shape
            if legacy_request():
                data = legacy_shape(data)
        envelope['data'] = validated(model, data)
    ApiEnvelope.model_validate(envelope)
    return JSONResponse(envelope, status_code=status, headers=headers)


def identity_headers(headers):
    authorizations = headers.getlist('authorization')
    cookies = [part.strip().partition('=')[0] for raw in headers.getlist('cookie') for part in raw.split(';')]
    require(len(authorizations) <= 1 and cookies.count(COOKIE) <= 1, 'REMOTE_AUTH_AMBIGUOUS')
    authorization = authorizations[0] if authorizations else None
    require(not (authorization and COOKIE in cookies), 'REMOTE_AUTH_AMBIGUOUS')
    return authorization


class RequestAudit:
    def __init__(self, app, security, settings, static=False):
        self.app, self.static, self.security, self.settings = app, static, security, settings

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        operation = next((op for method, path, op in OPERATIONS if method == scope['method'] and path.fullmatch(scope['path'])), None)
        context = dict(requestId=uid(), operation=operation['operationId'] if operation else
                       'static' if self.static and not scope['path'].startswith(('/api/', '/ws/')) else 'unmatched',
                       status=500, errorCode=None)
        scope.setdefault('state', {})['contract_operation'] = operation
        context['_worker'] = bool(operation and operation.get('x-auth-mode') == 'worker_device')
        reset = CONTEXT.set(context)
        start = time.monotonic(); started = False
        context['_started'] = start

        async def correlated(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
                MutableHeaders(scope=message)['X-Request-Id'] = context['requestId']
                context['status'] = message['status']
            await send(message)
        try:
            headers = Headers(scope=scope)
            if scope['path'].startswith('/api/'):
                require(scope['scheme'] == 'https', 'REMOTE_AUTH_REQUIRED')
            attempted_pat = bool(headers.getlist('authorization')) and (not operation or operation.get('x-auth-mode') != 'worker_device')
            if attempted_pat:
                peer = scope.get('client')
                self.security.rate('pat-source:' + (peer[0] if peer else 'unknown'))
            clients = headers.getlist('x-client-request-id')
            require(len(clients) <= 1 and (not clients or CLIENT_ID.fullmatch(clients[0])), 'BAD_REQUEST')
            if clients:
                context['clientRequestId'] = clients[0]
            identity_headers(headers)
            feature_headers = headers.getlist('x-hq-client-features')
            require(len(feature_headers) <= 1 and (not feature_headers or feature_headers[0] == 'pi-v1'))
            context['_features'] = ('pi-v1',) if feature_headers else ()
            if attempted_pat and (not operation or operation.get('x-auth-mode') != 'cookie_or_pat'):
                raise Fault('REMOTE_API_TOKEN_SCOPE_INSUFFICIENT')
            await self.app(scope, receive, correlated)
        except Exception as exc:
            if not started:
                fault = exc if isinstance(exc, Fault) else Fault('INTERNAL')
                result = response(fault=fault)
                if fault.code == 'REMOTE_RATE_LIMITED':
                    result.headers['Retry-After'] = str(self.settings.rate_window)
                await result(scope, receive, correlated)
            else:
                context['errorCode'] = 'INTERNAL'  # Never log exception text.
        finally:
            context['elapsedMs'] = round((time.monotonic() - start) * 1000, 3)
            LOG.info(json.dumps({k:v for k,v in context.items() if not k.startswith('_')}, ensure_ascii=True, separators=(',', ':')))
            CONTEXT.reset(reset)
