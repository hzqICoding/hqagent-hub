"""Fixed-size, authenticated concealment of the existing signed event cursor.

Fresh 128-bit nonces select a domain-separated HMAC-SHA256 PRF stream; a
separate HMAC authenticates the ciphertext before decryption. Scope, owner,
expiry and retention validation remain in the inner signed cursor parser.
No per-poll database records and no exposed sequence number or length signal.
"""
import base64
import hmac
import secrets

from .common import require

PADDED_BYTES = 512


def mask(security, owner, nonce, data):
    stream = b''.join(bytes.fromhex(security.mac('event-cursor-mask', f'{owner}:{nonce}:{n}'))
                      for n in range(PADDED_BYTES // 32))
    return bytes(a ^ b for a, b in zip(data, stream))


def seal(security, owner, cursor):
    raw = cursor.encode('utf-8')
    require(len(raw) <= PADDED_BYTES - 2)
    padded = len(raw).to_bytes(2, 'big') + raw + bytes(PADDED_BYTES - 2 - len(raw))
    nonce = secrets.token_hex(16)
    payload = base64.urlsafe_b64encode(mask(security, owner, nonce, padded)).decode().rstrip('=')
    tag = security.mac('event-cursor-auth', f'{owner}:{nonce}:{payload}')
    return f'e1.{nonce}.{payload}.{tag}'


def unseal(security, owner, cursor):
    try:
        require(isinstance(cursor, str) and len(cursor) <= 2048, 'REMOTE_CURSOR_INVALID')
        version, nonce, payload, tag = cursor.split('.')
        require(version == 'e1' and len(nonce) == 32 and all(c in '0123456789abcdef' for c in nonce), 'REMOTE_CURSOR_INVALID')
        expected = security.mac('event-cursor-auth', f'{owner}:{nonce}:{payload}')
        require(hmac.compare_digest(tag, expected), 'REMOTE_CURSOR_INVALID')
        raw = base64.b64decode(payload + '=' * (-len(payload) % 4), altchars=b'-_', validate=True)
        require(len(raw) == PADDED_BYTES, 'REMOTE_CURSOR_INVALID')
        padded = mask(security, owner, nonce, raw)
        size = int.from_bytes(padded[:2], 'big')
        require(0 < size <= PADDED_BYTES - 2 and not any(padded[2 + size:]), 'REMOTE_CURSOR_INVALID')
        return padded[2:2 + size].decode('utf-8')
    except (ValueError, TypeError, UnicodeError):
        from .common import Fault
        raise Fault('REMOTE_CURSOR_INVALID') from None
