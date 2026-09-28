"""Account PATs: non-recoverable secrets, explicit scopes and issuance intents."""
import hmac
import re
import secrets

from .common import canonical, require, seconds, stamp

PAT_PATTERN = re.compile(r'hqr_pat_([0-9a-f]{24})_[A-Za-z0-9_-]{43}\Z')
PAT_SCOPES = {'devices': 'devices:read', 'device': 'devices:read', 'catalog': 'devices:read',
              'patch_device': 'devices:manage', 'delete_device': 'devices:delete', 'revoke': 'devices:delete'}


class ApiTokens:
    def token_view(self, value):
        result = {k: v for k, v in value.items() if not k.startswith('_')}
        result['status'] = 'revoked' if 'revokedAt' in value else 'expired' if seconds(value['expiresAt']) <= self.settings.clock() else 'active'
        return result

    def issue_pat(self, tx, owner, body, key):
        intent_id = self.mac('pat-issue-key', key)
        content = self.mac('pat-issue-content', canonical(body))
        intent = tx.get(owner, 'pat-intent', intent_id)
        if intent:
            require(hmac.compare_digest(intent['content'], content), 'IDEMPOTENCY_MISMATCH')
            token = tx.get(owner, 'api-token', intent['tokenId'])
            return dict(token=self.token_view(token), secretAvailable=False)
        name = body['name'].strip()
        require(bool(name) and len(set(body['scopes'])) == len(body['scopes']))
        now = self.settings.clock()
        end = seconds(body['expiresAt']) if 'expiresAt' in body else now + 90 * 86400
        require(now < end <= now + 365 * 86400)
        selector = secrets.token_hex(12)
        while tx.auth_get('pat:' + selector):
            selector = secrets.token_hex(12)
        prefix = 'hqr_pat_' + selector
        secret = prefix + '_' + secrets.token_urlsafe(32)
        token_id = 'pat_' + selector
        token = dict(tokenId=token_id, name=name, tokenPrefix=prefix, scopes=body['scopes'],
                     createdAt=stamp(now), expiresAt=stamp(end), _verifier=self.mac('api-token-v1', secret))
        tx.put(owner, 'api-token', token_id, token)
        tx.auth_put('pat:' + selector, dict(owner=owner, tokenId=token_id), owner)
        tx.put(owner, 'pat-intent', intent_id, dict(content=content, tokenId=token_id))
        return dict(token=self.token_view(token), secretAvailable=True, secret=secret)

    def authenticate_pat(self, tx, header, operation, *, touch=False):
        scope = PAT_SCOPES.get(operation)
        require(scope is not None, 'REMOTE_API_TOKEN_SCOPE_INSUFFICIENT')
        token = header[7:] if header and header[:7].lower() == 'bearer ' else ''
        match = PAT_PATTERN.fullmatch(token)
        require(match is not None, 'REMOTE_API_TOKEN_INVALID')
        identity = tx.auth_get('pat:' + match[1])
        value = tx.get(identity['owner'], 'api-token', identity['tokenId']) if identity else None
        expected = value['_verifier'] if value else '0' * 64
        require(hmac.compare_digest(expected, self.mac('api-token-v1', token)) and value is not None, 'REMOTE_API_TOKEN_INVALID')
        require('revokedAt' not in value, 'REMOTE_API_TOKEN_INVALID')
        require(seconds(value['expiresAt']) > self.settings.clock(), 'REMOTE_API_TOKEN_EXPIRED')
        require(scope in value['scopes'], 'REMOTE_API_TOKEN_SCOPE_INSUFFICIENT')
        if touch:
            value['lastUsedAt'] = stamp(self.settings.clock())
            tx.put(identity['owner'], 'api-token', identity['tokenId'], value)
        return identity

    def revoke_pat(self, tx, owner, identifier):
        value = tx.get(owner, 'api-token', identifier)
        require(value is not None, 'NOT_FOUND')
        value.setdefault('revokedAt', stamp(self.settings.clock()))
        tx.put(owner, 'api-token', identifier, value)
        return dict(tokenId=identifier, revokedAt=value['revokedAt'], status='revoked')

    def list_pats(self, tx, service, owner, cursor, limit, include_revoked):
        scope = 'api-tokens:' + str(include_revoked)
        start = service.position(tx, owner, scope, cursor) if cursor else 0
        rows = []
        for ordinal, token in tx.ordered_records(owner, 'api-token', start):
            if not include_revoked and 'revokedAt' in token:
                continue
            rows.append((ordinal, self.token_view(token)))
            if len(rows) > limit:
                break
        result = dict(items=[t for _, t in rows[:limit]], hasMore=len(rows) > limit)
        if result['hasMore']:
            result['nextCursor'] = service.cursor(tx, owner, scope, rows[limit - 1][0])
        return result
