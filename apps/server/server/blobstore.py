"""Internal content-addressed storage; callers hold the repository commit/GC fence."""
import hashlib
import os
import json
from pathlib import Path
from typing import Protocol

from .common import require, uid

BLOCK = 65536


class BlobStore(Protocol):
    def stage_write(self, stream, maxBytes, expectedSha256): ...
    def commit(self, stage, sha256): ...
    def open_read(self, sha256): ...
    def delete(self, sha256): ...
    def exists(self, sha256): ...
    def abort(self, stage): ...


class Stage:
    def __init__(self, path, limit, expected):
        self.path, self.limit, self.expected = path, limit, expected
        self.handle = path.open('xb'); self.hash = hashlib.sha256(); self.size = 0
        self.closed = False

    def write(self, chunk):
        require(not self.closed, 'NOT_FOUND')
        require(len(chunk) <= BLOCK, 'ATTACHMENT_TOO_LARGE')
        self.size += len(chunk)
        require(self.size <= self.limit, 'ATTACHMENT_TOO_LARGE')
        self.hash.update(chunk); self.handle.write(chunk)

    def finish(self):
        require(not self.closed, 'NOT_FOUND')
        self.handle.flush(); os.fsync(self.handle.fileno()); self.handle.close(); self.closed = True
        require(self.hash.hexdigest() == self.expected, 'ATTACHMENT_HASH_MISMATCH')


class LocalBlobStore:
    def __init__(self, root):
        self.root = Path(root); self.temp = self.root / 'temp'; self.cas = self.root / 'cas'
        self.temp.mkdir(parents=True, exist_ok=True); self.cas.mkdir(exist_ok=True)
        self.deleted=self.root/'deleted';self.deleted.mkdir(exist_ok=True)

    def remember_deletion(self,owner,identifier):
        key=hashlib.sha256((owner+':'+identifier).encode()).hexdigest()
        target=self.deleted/key
        if target.exists():return
        temporary=self.deleted/(key+'.part')
        with temporary.open('w',encoding='utf-8') as out:
            json.dump(dict(owner=owner,attachmentId=identifier),out);out.flush();os.fsync(out.fileno())
        os.replace(temporary,target)

    def deletions(self):
        for path in self.deleted.iterdir():
            if path.suffix=='.part':path.unlink(missing_ok=True);continue
            yield json.loads(path.read_text(encoding='utf-8'))

    def path(self, sha256):
        require(len(sha256) == 64 and all(c in '0123456789abcdef' for c in sha256))
        return self.cas / sha256

    def stage_write(self, stream, maxBytes, expectedSha256):
        stage = Stage(self.temp / uid(), maxBytes, expectedSha256)
        if stream is not None:
            try:
                while chunk := stream.read(BLOCK): stage.write(chunk)
                stage.finish()
            except BaseException:
                self.abort(stage); raise
        return stage

    def commit(self, stage, sha256):
        require(stage.closed and stage.hash.hexdigest() == sha256, 'ATTACHMENT_HASH_MISMATCH')
        target = self.path(sha256)
        # Atomic create-if-absent: a losing same-hash writer never removes winner.
        try: os.link(stage.path, target)
        except FileExistsError: pass
        if os.name=='posix':
            descriptor=os.open(self.cas,os.O_RDONLY)
            try:os.fsync(descriptor)
            finally:os.close(descriptor)
        stage.path.unlink(missing_ok=True)
        return sha256

    def open_read(self, sha256): return self.path(sha256).open('rb')
    def delete(self, sha256): self.path(sha256).unlink(missing_ok=True)
    def exists(self, sha256): return self.path(sha256).is_file()
    def abort(self, stage):
        if not stage.handle.closed: stage.handle.close()
        stage.closed = True; stage.path.unlink(missing_ok=True)
