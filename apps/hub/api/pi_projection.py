"""Capability-scoped local HTTP projection; authentication remains in existing gates."""
import hashlib
import json
from urllib.parse import parse_qs
from pydantic import TypeAdapter, ValidationError

from api.envelopes import error_response
from core.errors import HubError
from core.local_auth import COOKIE_NAME
from core.security import token_matches
from runtime.pi_visibility import CLIENT_PI, HTTP_PROJECTION

CURSOR_SCOPE_CAPACITY = 256
EVENT_PATHS = {'/api/v1/events': '/api/v1/bootstrap', '/api/v2/events': '/api/v2/bootstrap'}
SNAPSHOT_PATHS = frozenset(EVENT_PATHS.values())
_AFTER = TypeAdapter(int)


def features(headers):
    return 'pi-v1' in {p.strip() for p in headers.get('x-hq-client-features', '').split(',')}


def cursor_scope(visibility, owner, enabled, after, *, snapshot=False, snapshot_url='/api/v2/bootstrap'):
    scopes = visibility.cursor_scopes
    previous = scopes.get(owner)
    # A missing entry is absence of evidence, not evidence of a capability
    # change. Every valid access (including a rejected switch) touches the LRU.
    scopes[owner] = enabled if previous is None else previous
    scopes.move_to_end(owner)
    while len(scopes) > CURSOR_SCOPE_CAPACITY:
        scopes.popitem(last=False)
    if not snapshot and after is not None and after > 0 and previous is not None and previous != enabled:
        raise HubError('EVENT_CURSOR_EXPIRED', '客户端能力已变化，请重新获取快照',
            detail=visibility.worker.repo.events.cursor_expired_detail(snapshot_url))
    if snapshot or after == 0:
        scopes[owner] = enabled


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
            await visibility.refresh(cached=True)
            if scope['method'] == 'GET':
                if scope['path'] in EVENT_PATHS:
                    # Match the endpoint's scalar query semantics (last value,
                    # Pydantic integer parsing). Invalid input remains its 422.
                    raw_after = queries.get('after', ['0' if scope['path'] == '/api/v2/events' else ''])[-1]
                    try:
                        after = _AFTER.validate_python(raw_after)
                    except ValidationError:
                        after = None
                    if after is not None and after >= 0:
                        cursor_scope(visibility, owner, enabled, after, snapshot_url=EVENT_PATHS[scope['path']])
                elif scope['path'] in SNAPSHOT_PATHS:
                    cursor_scope(visibility, owner, enabled, None, snapshot=True, snapshot_url=scope['path'])
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
                from runtime.execution_selection import reject_pi_fallbacks
                reject_pi_fallbacks(body, visibility.agents)
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
