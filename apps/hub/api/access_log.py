"""ASGI metadata access logs; never reads bodies or writes protocol fields."""
import logging
import time
import uuid
from urllib.parse import parse_qs
from starlette.routing import Match

from core.diagnostics import REQUEST_LOG, emit, exception_fields


class AccessLogMiddleware:
    def __init__(self, app, router):
        self.app, self.router = app, router

    def template(self, scope):
        for route in self.router.routes:
            matched, _ = route.matches(scope)
            if matched is Match.FULL:
                return getattr(route, 'path', '/[mounted]')
        return scope.get('path', '/').split('?', 1)[0]

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        context = {'requestId': 'req_' + uuid.uuid4().hex}
        token = REQUEST_LOG.set(context)
        headers = dict(scope.get('headers', []))
        secrets = []
        authorization = headers.get(b'authorization', b'').decode('latin1')
        if authorization:
            secrets.extend((authorization, authorization.split(' ', 1)[-1]))
        for part in headers.get(b'cookie', b'').decode('latin1').split(';'):
            if '=' in part:
                secrets.append(part.split('=', 1)[1].strip())
        query = parse_qs(scope.get('query_string', b'').decode('latin1'))
        for key in ('ticket', 'token', 'code', 'pairCode', 'api_key'):
            secrets.extend(query.get(key, ()))
        context['_secrets'] = tuple(s for s in secrets if s)
        auth = 'bearer' if headers.get(b'authorization', b'').lower().startswith(b'bearer ') else 'cookie' if headers.get(b'cookie') else 'none'
        method, route = scope['method'], self.template(scope)
        status = 500
        started = time.monotonic()
        async def observed(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
                # Existing maintenance middleware may have selected its own ID.
                value = dict(message.get('headers', [])).get(b'x-request-id')
                if value:
                    context['requestId'] = value.decode('latin1')
            await send(message)
        try:
            await self.app(scope, receive, observed)
        except Exception as error:
            context.setdefault('errorCode', 'INTERNAL')
            emit('http.exception', level=logging.ERROR, method=method, route=route,
                 requestId=context['requestId'], **exception_fields(error))
            raise
        finally:
            if status >= 500:
                context.setdefault('errorCode', 'INTERNAL')
            level = logging.DEBUG if route == '/healthz' and status < 400 else logging.ERROR if status >= 500 else logging.INFO
            emit('http.access', level=level, method=method, route=route, status=status,
                 elapsedMs=(time.monotonic() - started) * 1000, auth=auth, **context)
            REQUEST_LOG.reset(token)
