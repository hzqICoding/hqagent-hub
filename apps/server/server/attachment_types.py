"""Bounded content classification, never execute or extract source/PDF content."""
import codecs
import re
import unicodedata
from urllib.parse import unquote
from .common import require
EXTENSIONS = ['.' + e for e in 'pdf txt md json c h cpp hpp cc cxx py js ts jsx tsx java kt kts go rs swift m mm cs rb php sh ps1 sql yaml yml toml'.split()]
LIMITS = dict(imageMaxBytes=10000000,
    fileMaxBytes=20000000,
    messageMaxCount=5,
    accountQuotaBytes=5000000000,
    unattachedTtlSeconds=86400,
    imageMimeTypes=['image/jpeg',
    'image/png',
    'image/webp',
    'image/gif'],
    fileExtensions=EXTENSIONS)

def filename(raw):
    require(0 < len(raw) <= 512, 'BAD_REQUEST')
    require(not re.search('%(?![0-9a-fA-F]{2})', raw), 'BAD_REQUEST')
    name = unicodedata.normalize('NFC', unquote(raw, encoding='utf-8', errors='strict'))
    name = name.replace('\\', '/').split('/')[-1].split(':')[-1]
    name = ''.join((c for c in name if not unicodedata.category(c).startswith('C') and c not in '<>:"/\\|?*')).strip(' .')
    if not name or re.fullmatch('(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\\..*)?', name):
        name = 'attachment.txt'
    return name[:120]

class Detector:

    def __init__(self, name):
        self.name = name
        self.prefix = b''
        self.kind = None
        self.mime = None
        self.extension = None
        self.decoder = codecs.getincrementaldecoder('utf-8')('strict')

    def feed(self, chunk, final=False):
        if self.kind is None:
            self.prefix += chunk
            if len(self.prefix) < 16 and (not final):
                return
            chunk = self.prefix
            self.prefix = b''
            p = chunk[:512]
            if p.startswith(b'\x89PNG\r\n\x1a\n'):
                self.kind, self.mime, self.extension = ('image', 'image/png', '.png')
            elif p.startswith(b'\xff\xd8\xff'):
                self.kind, self.mime, self.extension = ('image', 'image/jpeg', '.jpg')
            elif p.startswith((b'GIF87a', b'GIF89a')):
                self.kind, self.mime, self.extension = ('image', 'image/gif', '.gif')
            elif p.startswith(b'RIFF') and p[8:12] == b'WEBP':
                self.kind, self.mime, self.extension = ('image', 'image/webp', '.webp')
            elif p.startswith(b'%PDF-'):
                self.kind, self.mime, self.extension = ('file', 'application/pdf', '.pdf')
            else:
                ext = '.' + self.name.rsplit('.', 1)[-1].lower()
                require(ext in EXTENSIONS and ext != '.pdf', 'ATTACHMENT_TYPE_UNSUPPORTED')
                stripped = p.lstrip(b'\xef\xbb\xbf \t\r\n').lower()
                require(not stripped.startswith((b'mz',
                    b'\x7felf',
                    b'pk\x03\x04',
                    b'<svg',
                    b'<?xml',
                    b'<!doctype html',
                    b'<html',
                    b'<script')),
                    'ATTACHMENT_TYPE_UNSUPPORTED')
                self.kind, self.mime, self.extension = ('file', 'text/plain', ext)
        if self.mime == 'text/plain':
            require(b'\x00' not in chunk and (not any((c < 32 and c not in (9,
                10,
                12,
                13) for c in chunk))),
                'ATTACHMENT_TYPE_UNSUPPORTED')
            try:
                self.decoder.decode(chunk, final=final)
            except UnicodeDecodeError:
                require(False, 'ATTACHMENT_TYPE_UNSUPPORTED')

    def normalized_name(self):
        stem = self.name.rsplit('.', 1)[0] if '.' in self.name else self.name
        return stem[:120 - len(self.extension)] + self.extension
