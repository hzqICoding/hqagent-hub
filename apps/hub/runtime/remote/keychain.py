"""Device credential storage; system vaults are optional, never plaintext backends."""
from __future__ import annotations

import hashlib
import logging
import os
import sys
import threading
import time
from pathlib import Path

from core.errors import HubError

MARKER = b'HQAGENT-SYSTEM-KEYRING-v1\n'
SERVICE = 'HQAgent-Hub.remote-device'


def system_keyring(platform=None):
    platform = platform or sys.platform
    try:
        if platform == 'darwin':
            from keyring.backends.macOS import Keyring
        elif platform.startswith('linux'):
            from keyring.backends.SecretService import Keyring
        else:
            return None
        backend = Keyring()
        if backend.priority <= 0:
            return None
        return backend
    except Exception:
        return None


class PosixCredentialStore:
    def __init__(self, directory: Path, *, backend_factory=None, atomic_write, monotonic=time.monotonic):
        self.directory = directory
        self.path = directory / 'device.credential'
        self.pending = directory / 'device.keyring-pending'
        self.account = hashlib.sha256(str(directory.resolve()).encode()).hexdigest()
        # Resolve lazily: callers/tests can replace discovery without a default
        # argument capturing the native backend at module import time.
        self.backend_factory = backend_factory or (lambda: system_keyring())
        self.atomic_write = atomic_write
        self.monotonic = monotonic
        self.retry_after = 0.0
        self.storage_mode = None
        self.lock = threading.RLock()

    def mode(self, name):
        if self.storage_mode != name:
            self.storage_mode = name
            logging.getLogger(__name__).warning('Device credential storage mode=%s', name)

    def _store_in_keyring(self, secret):
        if self.monotonic() < self.retry_after:
            return False
        try:
            backend = self.backend_factory()
            if backend is None:
                raise ValueError()
            # Journal any attempted keyring write so unlink can also clean up
            # partially completed migration. It contains no credential.
            self.atomic_write(self.pending, b'pending\n')
            backend.set_password(SERVICE, self.account, secret)
            if backend.get_password(SERVICE, self.account) != secret:
                raise ValueError()
            self.atomic_write(self.path, MARKER)
        except Exception:
            self.retry_after = self.monotonic() + 600
            return False
        self.pending.unlink(missing_ok=True)
        self.retry_after = 0.0
        self.mode('system-keyring')
        return True

    def migrate(self, secret):
        # A failed attempt never removes or rewrites the authoritative old file.
        if not self._store_in_keyring(secret):
            self.mode('file-0600')
        return secret

    def read(self):
        with self.lock:
            return self._read()

    def _read(self):
        try:
            if self.path.is_symlink():
                raise ValueError()
            if not self.path.exists() and self.pending.exists():
                backend = self.backend_factory()
                secret = backend.get_password(SERVICE, self.account) if backend else None
                if not isinstance(secret, str) or not secret:
                    raise ValueError()
                self.atomic_write(self.path, MARKER)
                self.pending.unlink(missing_ok=True)
            content = self.path.read_bytes()
            os.chmod(self.path, 0o600)
            if content == MARKER:
                backend = self.backend_factory()
                if backend is None:
                    raise ValueError()
                secret = backend.get_password(SERVICE, self.account)
                if not isinstance(secret, str) or not secret:
                    raise ValueError()
                self.mode('system-keyring')
                return secret
            secret = content.decode('ascii')
            if not secret:
                raise ValueError()
            self.directory.chmod(0o700)
            return self.migrate(secret)
        except Exception:
            raise HubError('REMOTE_DEVICE_AUTH_FAILED', '本机设备凭据不可用') from None

    def save(self, secret):
        with self.lock:
            return self._save(secret)

    def _save(self, secret):
        self.directory.mkdir(parents=True, exist_ok=True)
        self.directory.chmod(0o700)
        if self.path.is_symlink():
            raise HubError('REMOTE_DEVICE_AUTH_FAILED', '设备凭据路径无效')
        if self.path.exists() and self.path.read_bytes() == MARKER:
            backend = self.backend_factory()
            try:
                if backend is None:
                    raise ValueError()
                previous = backend.get_password(SERVICE, self.account)
                if previous and previous != secret:
                    # A live binding must be unlinked first; don't replace the
                    # only recoverable credential if backend verification fails.
                    raise ValueError()
                backend.set_password(SERVICE, self.account, secret)
                if backend.get_password(SERVICE, self.account) != secret:
                    raise ValueError()
                self.mode('system-keyring')
                return
            except Exception:
                raise HubError('REMOTE_DEVICE_AUTH_FAILED', '系统钥匙串暂不可用') from None
        if not self._store_in_keyring(secret):
            self.atomic_write(self.path, secret.encode('ascii'))
            self.mode('file-0600')

    def delete(self):
        with self.lock:
            return self._delete()

    def _delete(self):
        try:
            content = self.path.read_bytes() if self.path.exists() else None
            if content == MARKER or self.pending.exists():
                backend = self.backend_factory()
                if backend is None:
                    raise ValueError()
                if backend.get_password(SERVICE, self.account) is not None:
                    backend.delete_password(SERVICE, self.account)
                if backend.get_password(SERVICE, self.account) is not None:
                    raise ValueError()
            self.path.unlink(missing_ok=True)
            self.pending.unlink(missing_ok=True)
        except Exception:
            raise HubError('REMOTE_DEVICE_AUTH_FAILED', '设备凭据删除尚未完成') from None
