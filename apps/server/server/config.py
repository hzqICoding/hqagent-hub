import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit


def default_data():
    if os.name == "nt":
        return Path(os.environ["LOCALAPPDATA"]) / "HQAgent-Hub" / "remote-server"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "hqagent-hub/remote-server"


@dataclass
class Settings:
    database: Path
    key: bytes
    origin: str = "https://localhost"
    static_dir: Path | None = None
    session_ttl: int = 86400
    cursor_ttl: int = 86400
    browser_retention_seconds: int = 7 * 86400
    sync_message_bytes: int = 16 * 1024 * 1024
    sync_staging_bytes: int = 128 * 1024 * 1024
    rate_limit: int = 30
    rate_window: int = 60
    blob_backend: str = 'local'
    clock: Callable[[], float] = field(default=time.time, repr=False)
    monotonic: Callable[[], float] = field(default=time.monotonic, repr=False)

    def __post_init__(self):
        from .blobstore import validate_backend
        validate_backend(self.blob_backend)
        parsed = urlsplit(self.origin)
        if len(self.key) < 32 or parsed.scheme != "https" or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError("Invalid server security configuration")
        if type(self.browser_retention_seconds) is not int or self.browser_retention_seconds <= 0:
            raise ValueError("Browser event retention must be a positive integer")
        if min(self.sync_message_bytes, self.sync_staging_bytes) <= 0:
            raise ValueError('Sync resource quotas must be positive')

    @classmethod
    def from_env(cls):
        data = Path(os.environ.get("HQREMOTE_DATA_DIR", default_data())).resolve()
        data.mkdir(parents=True, exist_ok=True)
        keyfile = Path(os.environ.get("HQREMOTE_KEY_FILE", str(data / "server.key")))
        if not keyfile.exists():
            fd = os.open(keyfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(secrets.token_bytes(32))
        static = os.environ.get("HQREMOTE_STATIC_DIR")
        return cls(database=data / "hub.sqlite3", key=keyfile.read_bytes(),
                   origin=os.environ.get("HQREMOTE_ORIGIN", "https://localhost"),
                   static_dir=Path(static) if static else None,
                   session_ttl=int(os.environ.get("HQREMOTE_SESSION_TTL", "86400")),
                   cursor_ttl=int(os.environ.get("HQREMOTE_CURSOR_TTL", "86400")),
                   browser_retention_seconds=int(os.environ.get("HQREMOTE_BROWSER_RETENTION_SECONDS", "604800")),
                   sync_message_bytes=int(os.environ.get('HQREMOTE_SYNC_MESSAGE_BYTES', '16777216')),
                   sync_staging_bytes=int(os.environ.get('HQREMOTE_SYNC_STAGING_BYTES', '134217728')),
                   blob_backend=os.environ.get('HQREMOTE_BLOB_BACKEND', 'local'),
                   rate_limit=int(os.environ.get("HQREMOTE_RATE_LIMIT", "30")))
