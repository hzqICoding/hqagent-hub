"""Bounded metadata detection; never execute or extract document contents."""
import codecs
import hashlib
import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote
from core.errors import HubError
from protocol.generated.python import AttachmentLimits
CHUNK = 65536
EXTENSIONS = ['.' + e for e in 'pdf txt md json c h cpp hpp cc cxx py js ts jsx tsx java kt kts go rs swift m mm cs rb php sh ps1 sql yaml yml toml'.split()]
IMAGE_EXTENSIONS = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/gif': '.gif', 'image/webp': '.webp'}
LIMITS = AttachmentLimits(imageMaxBytes=10000000, fileMaxBytes=20000000, messageMaxCount=5, accountQuotaBytes=5000000000, unattachedTtlSeconds=86400, imageMimeTypes=list(IMAGE_EXTENSIONS), fileExtensions=EXTENSIONS)

def fail(code):
    raise HubError(code, '附件不符合当前输入要求')

def image_mime(prefix):
    if prefix.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if prefix.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if prefix.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    if prefix.startswith(b'RIFF') and prefix[8:12] == b'WEBP':
        return 'image/webp'
    return None

def display_name(encoded):
    if not isinstance(encoded, str) or not 0 < len(encoded) <= 512 or re.search('%(?![0-9a-fA-F]{2})', encoded):
        fail('BAD_REQUEST')
    try:
        name = unicodedata.normalize('NFC', unquote(encoded, encoding='utf-8', errors='strict'))
    except UnicodeError:
        fail('BAD_REQUEST')
    name = name.replace('\\', '/').split('/')[-1].split(':')[-1]
    name = ''.join((c for c in name if not unicodedata.category(c).startswith('C') and c not in '<>:"/\\|?*')).strip(' .')[:120]
    if not name or re.fullmatch('(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\\..*)?', name):
        name = 'attachment.txt'
    return name

def inspect_file(path, name, expected_size, expected_hash):
    size, sha, prefix = (0, hashlib.sha256(), b'')
    with Path(path).open('rb') as stream:
        while (chunk := stream.read(CHUNK)):
            size += len(chunk)
            if size > expected_size or size > LIMITS.file_max_bytes:
                fail('ATTACHMENT_HASH_MISMATCH' if size > expected_size else 'ATTACHMENT_TOO_LARGE')
            sha.update(chunk)
            if len(prefix) < 512:
                prefix += chunk[:512 - len(prefix)]
    if not size or size != expected_size or sha.hexdigest() != expected_hash:
        fail('ATTACHMENT_HASH_MISMATCH')
    image = image_mime(prefix)
    if image:
        if size > LIMITS.image_max_bytes:
            fail('ATTACHMENT_TOO_LARGE')
        try:
            from PIL import Image
            with Image.open(path) as value:
                if value.width * value.height > 40000000 or Image.MIME.get(value.format) != image:
                    fail('ATTACHMENT_TYPE_UNSUPPORTED')
                value.verify()
        except HubError:
            raise
        except Exception:
            fail('ATTACHMENT_TYPE_UNSUPPORTED')
        kind, mime, ext = ('image', image, IMAGE_EXTENSIONS[image])
    elif prefix.startswith(b'%PDF-'):
        kind, mime, ext = ('file', 'application/pdf', '.pdf')
    else:
        ext = Path(name).suffix.lower()
        forbidden = prefix.lstrip(b'\xef\xbb\xbf \t\r\n').lower()
        if ext not in EXTENSIONS or ext == '.pdf' or forbidden.startswith((b'mz', b'\x7felf', b'pk\x03\x04', b'<svg', b'<?xml', b'<!doctype html', b'<html', b'<script')):
            fail('ATTACHMENT_TYPE_UNSUPPORTED')
        decoder = codecs.getincrementaldecoder('utf-8')('strict')
        try:
            with Path(path).open('rb') as stream:
                while (chunk := stream.read(CHUNK)):
                    if any((c < 32 and c not in (9, 10, 12, 13) for c in chunk)):
                        fail('ATTACHMENT_TYPE_UNSUPPORTED')
                    decoder.decode(chunk)
                decoder.decode(b'', final=True)
        except UnicodeError:
            fail('ATTACHMENT_TYPE_UNSUPPORTED')
        kind, mime = ('file', 'text/plain')
    stem = name.rsplit('.', 1)[0] if '.' in name else name
    return (dict(fileName=stem[:120 - len(ext)] + ext, kind=kind, mimeType=mime, sizeBytes=size, sha256=expected_hash), ext)
