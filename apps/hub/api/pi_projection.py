"""Capability-scoped local HTTP projection; authentication remains in existing gates."""
import hashlib
import json
from urllib.parse import parse_qs

from api.envelopes import error_response
from core.errors import HubError
from core.local_auth import COOKIE_NAME
from core.security import token_matches
from runtime.pi_visibility import CLIENT_PI, HTTP_PROJECTION


def features(headers):
    return 'pi-v1' in {p.strip() for p in headers.get('x-hq-client-features', '').split(',')}


def cursor_scope(visibility, owner, enabled, after, *, snapshot=False):
    previous = visibility.cursor_scopes.get(owner)
    if after is not None and after > 0 and previous != enabled and (enabled or previous is not None):
        raise HubError('EVENT_CURSOR_EXPIRED', '客户端能力已变化，请重新获取快照', detail={'snapshotUrl': '/api/v2/bootstrap'})
    if snapshot or after == 0:
        if len(visibility.cursor_scopes) >= 256:
            visibility.cursor_scopes.clear()
        visibility.cursor_scopes[owner] = enabled


class PiProjectionMiddleware:
    def __init__(self, app, *, worker, auth, token):
        self.app, self.worker, self.auth, self.token = app, worker, auth, token

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope['path'].startswith('/api/'):
            await self.app(scope, receive, send)
            return
        headers = {k.decode('latin1').lower(): v.decode('latin1') for k, v in scope['headers']}
        bearer = headers.get('authorization', '')
        cookie = self.auth.cookie_from_headers(headers)
        if not (bearer.startswith('Bearer ') and token_matches(bearer[7:], self.token)) and not self.auth.valid(cookie):
            await self.app(scope, receive, send)
            return
        enabled = features(headers)
        owner = hashlib.sha256((bearer if bearer else cookie or '').encode()).hexdigest()
        queries = parse_qs(scope.get('query_string', b'').decode('utf-8'))
        visibility = self.worker.pi
        messages = []
        try:
            await visibility.refresh()
            after = int(queries['after'][0]) if 'after' in queries and queries['after'][0].isdigit() else None
            cursor_scope(visibility, owner, enabled, after, snapshot=scope['path'].endswith('/bootstrap'))
            if queries.get('page', [''])[0].isdigit():
                page = int(queries['page'][0])
                cursor_scope(visibility, owner + ':' + scope['path'], enabled, max(0, page - 1))
            if not enabled:
                if queries.get('agentType') == ['pi']:
                    raise HubError('NOT_FOUND', '资源不存在')
                identifiers = scope['path'].split('/') + [v for values in queries.values() for v in values]
                if any(v in visibility.resources or visibility.was_pi(v) for v in identifiers):
                    raise HubError('NOT_FOUND', '资源不存在')
            if scope['method'] not in {'GET', 'HEAD', 'OPTIONS'} and 'application/json' in headers.get('content-type', ''):
                size = 0
                while True:
                    message = await receive()
                    messages.append(message)
                    size += len(message.get('body', b''))
                    if size > 20 * 1024 * 1024:
                        raise HubError('VALIDATION_FAILED', '本机JSON请求超过限制')
                    if message['type'] != 'http.request' or not message.get('more_body'):
                        break
                try:
                    body = json.loads(b''.join(m.get('body', b'') for m in messages))
                except (ValueError, UnicodeError):
                    body = None
                if not enabled and visibility.mentions(body):
                    raise HubError('NOT_FOUND', '资源不存在')
        except HubError as error:
            await error_response(error)(scope, receive, send)
            return

        async def replay():
            return messages.pop(0) if messages else await receive()

        token = CLIENT_PI.set(enabled)
        projection = HTTP_PROJECTION.set((visibility, enabled, owner))
        try:
            await self.app(scope, replay, send)
        finally:
            HTTP_PROJECTION.reset(projection)
            CLIENT_PI.reset(token)
