"""Replaceable blob storage. Business code never interprets keys or local paths."""
import hashlib
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, ContextManager, Iterable, Protocol

from .common import require, uid

BLOCK = 65536


class Stage(Protocol):
    """Opaque writer; implementations own handles and cleanup on validation failure."""
    identifier: str
    size: int
    closed: bool

    @property
    def sha256(self) -> str: ...
    def write(self, chunk: bytes) -> None: ...
    def finish(self) -> None: ...


class BlobStore(Protocol):
    def stage_write(self, stream: BinaryIO | None, maxBytes: int, expectedSha256: str,
                    *, expectedBytes: int | None = None) -> Stage: ...
    def commit(self, stage: Stage, sha256: str) -> str: ...
    def open_read(self, sha256: str) -> BinaryIO: ...
    def delete(self, sha256: str) -> None: ...
    def exists(self, sha256: str) -> bool: ...
    def size(self, sha256: str) -> int: ...
    def abort(self, stage: Stage) -> None: ...
    def iter_blobs(self) -> Iterable[str]: ...
    def purge_staging(self) -> None: ...
    def materialize(self, source: Stage | str) -> ContextManager[os.PathLike]: ...


def object_key(sha256):
    require(len(sha256) == 64 and all(c in '0123456789abcdef' for c in sha256))
    return f'cas/{sha256[:2]}/{sha256[2:4]}/{sha256}'


class _LocalStage:
    def __init__(self, store, identifier, limit, expected, expected_size):
        self._store = store
        self.identifier = identifier
        self.limit = limit
        self.expected = expected
        self.expected_size = expected_size
        self.size = 0
        self.closed = False
        self.verified = False
        self._hash = hashlib.sha256()

    @property
    def sha256(self):
        return self._hash.hexdigest()

    def write(self, chunk):
        self._store._write_stage(self, chunk)

    def finish(self):
        self._store._finish_stage(self)


class LocalBlobStore:
    def __init__(self, root):
        self.root = Path(root)
        # These diagnostics remain for existing local filesystem tests only.
        # No service depends on temp/cas/path: they are not BlobStore methods.
        self.temp = self.root / 'temp'
        self.cas = self.root / 'cas'
        self.temp.mkdir(parents=True, exist_ok=True)
        self.cas.mkdir(exist_ok=True)
        self._lock = threading.RLock()
        self._stages = {}
        self._materialized = set()
        self._readers = {}

    def _path(self, sha256):
        return self.root / object_key(sha256)

    def path(self, sha256):
        """Local-only diagnostic for tests that simulate disk restore/corruption."""
        path = self._path(sha256)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _existing_path(self, sha256):
        path = self._path(sha256)
        # Compatibility with the previous flat layout; new writes are layered.
        return path if path.is_file() else self.cas / sha256

    def stage_write(self, stream, maxBytes, expectedSha256, *, expectedBytes=None):
        object_key(expectedSha256)
        require(maxBytes > 0 and (expectedBytes is None or 0 <= expectedBytes <= maxBytes))
        stage = _LocalStage(self, uid(), maxBytes, expectedSha256, expectedBytes)
        with self._lock:
            path = self.temp / stage.identifier
            self._stages[stage.identifier] = (path, path.open('xb'))
        if stream is not None:
            try:
                while chunk := stream.read(BLOCK):
                    stage.write(chunk)
                stage.finish()
            except BaseException:
                self.abort(stage)
                raise
        return stage

    def _write_stage(self, stage, chunk):
        with self._lock:
            try:
                require(stage.identifier in self._stages and not stage.closed, 'NOT_FOUND')
                require(len(chunk) <= BLOCK and stage.size + len(chunk) <= stage.limit,
                        'ATTACHMENT_TOO_LARGE')
                if stage.expected_size is not None:
                    require(stage.size + len(chunk) <= stage.expected_size, 'ATTACHMENT_HASH_MISMATCH')
                self._stages[stage.identifier][1].write(chunk)
                stage._hash.update(chunk)
                stage.size += len(chunk)
            except BaseException:
                self.abort(stage)
                raise

    def _finish_stage(self, stage):
        with self._lock:
            try:
                require(stage.identifier in self._stages and not stage.closed, 'NOT_FOUND')
                handle = self._stages[stage.identifier][1]
                handle.flush()
                os.fsync(handle.fileno())
                handle.close()
                stage.closed = True
                require(stage.expected_size is None or stage.size == stage.expected_size,
                        'ATTACHMENT_HASH_MISMATCH')
                require(stage.sha256 == stage.expected, 'ATTACHMENT_HASH_MISMATCH')
                stage.verified = True
            except BaseException:
                self.abort(stage)
                raise

    def commit(self, stage, sha256):
        with self._lock:
            require(stage._store is self and stage.verified and stage.sha256 == sha256,
                    'ATTACHMENT_HASH_MISMATCH')
            entry = self._stages.get(stage.identifier)
            if entry is None:
                require(self.exists(sha256), 'NOT_FOUND')
                return sha256  # Repeating a successful commit is safe.
            target = self._path(sha256)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(entry[0], target)
            except FileExistsError:
                pass  # A losing same-hash writer never removes the winner.
            if os.name == 'posix':
                descriptor = os.open(target.parent, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            self._discard_stage(stage, invalidate=False)
            return sha256

    def _discard_stage(self, stage, *, invalidate):
        entry = self._stages.pop(stage.identifier, None)
        if entry:
            path, handle = entry
            handle.close()
            if path.exists():
                path.chmod(0o600)
                path.unlink()
        stage.closed = True
        if invalidate:
            stage.verified = False

    def abort(self, stage):
        with self._lock:
            self._discard_stage(stage, invalidate=True)

    def open_read(self, sha256):
        with self._lock:
            handle = self._existing_path(sha256).open('rb')
            readers = self._readers.setdefault(sha256, set())
            readers.difference_update({h for h in readers if h.closed})
            readers.add(handle)
            return handle

    def size(self, sha256):
        with self._lock:
            return self._existing_path(sha256).stat().st_size

    def exists(self, sha256):
        with self._lock:
            return self._existing_path(sha256).is_file()

    def delete(self, sha256):
        with self._lock:
            for handle in self._readers.pop(sha256, set()):
                handle.close()
            for path in {self._path(sha256), self.cas / sha256}:
                if path.exists():
                    path.chmod(0o600)
                    path.unlink()
            parent = self._path(sha256).parent
            while parent != self.cas:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent

    def iter_blobs(self):
        # No owner, display name or user path participates in an object key.
        with self._lock:
            values = {path.name for path in self.cas.rglob('*') if path.is_file()
                      and len(path.name) == 64 and all(c in '0123456789abcdef' for c in path.name)}
        return iter(sorted(values))

    def purge_staging(self):
        with self._lock:
            protected = {p for p, _ in self._stages.values()} | self._materialized
            for path in self.temp.iterdir():
                if path.is_file() and path not in protected:
                    path.chmod(0o600)
                    path.unlink()

    @contextmanager
    def materialize(self, source):
        """Lease a read-only local file; remote adapters may use a temp download.

        Blob materialization uses a bounded temporary copy so its cleanup and
        permissions never modify the durable object. Stages are already local.
        """
        temporary = isinstance(source, str)
        with self._lock:
            if temporary:
                path = self.temp / uid()
                try:
                    with self._existing_path(source).open('rb') as reader, path.open('xb') as writer:
                        while chunk := reader.read(BLOCK):
                            writer.write(chunk)
                except BaseException:
                    path.unlink(missing_ok=True)
                    raise
            else:
                require(source._store is self and source.verified and source.identifier in self._stages,
                        'NOT_FOUND')
                path = self._stages[source.identifier][0]
            self._materialized.add(path)
            path.chmod(0o400)
        try:
            yield path
        finally:
            with self._lock:
                self._materialized.discard(path)
                if path.exists():
                    path.chmod(0o600)
                    if temporary:
                        path.unlink()


BACKENDS = {'local': LocalBlobStore}


def validate_backend(name):
    if name not in BACKENDS:
        raise ValueError('Unknown blob backend')


def create_blob_store(settings) -> BlobStore:
    validate_backend(settings.blob_backend)
    return BACKENDS[settings.blob_backend](settings.database.parent / 'blobs')
