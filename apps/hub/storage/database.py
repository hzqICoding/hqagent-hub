from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from storage.migrations import LATEST_SCHEMA_VERSION, MIGRATIONS, current_version


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Transaction:
    def __init__(self, database: "Database") -> None:
        self.database = database
        self.connection = database.connection
        self._after_commit: list[Callable[[], None]] = []

    def after_commit(self, callback: Callable[[], None]) -> None:
        self._after_commit.append(callback)

    def __enter__(self) -> "Transaction":
        self.database._lock.acquire()
        self.connection.execute("BEGIN IMMEDIATE")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        callbacks: list[Callable[[], None]] = []
        try:
            if exc_type is None:
                self.connection.execute("COMMIT")
                callbacks = list(self._after_commit)
            else:
                self.connection.execute("ROLLBACK")
        finally:
            self.database._lock.release()
        for callback in callbacks:
            callback()
        return False


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(
            self.path,
            check_same_thread=False,
            isolation_level=None,
            timeout=15,
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=15000")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("PRAGMA journal_mode=WAL")

    def initialize(self, target_version: int = LATEST_SCHEMA_VERSION) -> None:
        if target_version < 1 or target_version > LATEST_SCHEMA_VERSION:
            raise ValueError(f"unsupported target schema version: {target_version}")
        with self._lock:
            version = current_version(self.connection)
            if version > target_version:
                raise RuntimeError(f"database schema {version} is newer than supported {target_version}")
            for migration in MIGRATIONS:
                if version < migration.version <= target_version:
                    updated_at = _timestamp().replace("'", "''")
                    script = (
                        "BEGIN IMMEDIATE;\n"
                        + migration.sql
                        + "\nINSERT INTO schema_version(singleton, version, updated_at) "
                        + f"VALUES(1, {migration.version}, '{updated_at}') "
                        + "ON CONFLICT(singleton) DO UPDATE SET "
                        + f"version={migration.version}, updated_at='{updated_at}';\nCOMMIT;"
                    )
                    try:
                        self.connection.executescript(script)
                    except Exception:
                        if self.connection.in_transaction:
                            self.connection.execute("ROLLBACK")
                        raise
                    version = migration.version

    @property
    def schema_version(self) -> int:
        with self._lock:
            return current_version(self.connection)

    def transaction(self) -> Transaction:
        return Transaction(self)

    @contextmanager
    def locked_connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            yield self.connection

    def checkpoint(self, mode: str = "TRUNCATE") -> tuple[int, int, int]:
        if mode not in {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}:
            raise ValueError("invalid WAL checkpoint mode")
        with self._lock:
            row = self.connection.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
            return int(row[0]), int(row[1]), int(row[2])

    def backup(self, destination: Path) -> Path:
        destination = destination.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.checkpoint("FULL")
            target = sqlite3.connect(destination)
            try:
                self.connection.backup(target)
                target.execute("PRAGMA integrity_check")
            finally:
                target.close()
        return destination

    def restore_from_backup(self, source: Path) -> None:
        source = source.resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        with self._lock:
            backup = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
            try:
                integrity = backup.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    raise RuntimeError(f"backup integrity check failed: {integrity}")
                backup.backup(self.connection)
            finally:
                backup.close()
            self.connection.execute("PRAGMA journal_mode=WAL")

    def close(self) -> None:
        with self._lock:
            try:
                self.checkpoint("TRUNCATE")
            finally:
                self.connection.close()
