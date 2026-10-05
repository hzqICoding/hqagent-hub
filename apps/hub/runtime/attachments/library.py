"""Bounded local file storage; no display name is ever a filesystem path."""
import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import quote
import httpx
from protocol.generated.python import AttachmentManifestItem
from core.errors import HubError
from runtime.attachments.content import CHUNK, LIMITS, display_name, inspect_file, fail, image_mime
from runtime.remote.security import normalize_origin
from runtime.attachments.transport import attachment_client
from storage.attachments import AttachmentRepository
from storage.idempotency import request_hash
from storage.local_chat import uid, now

class AttachmentLibrary:

    def __init__(self, worker):
        self.worker = worker
        self.db = worker.repo.database
        self.repo = AttachmentRepository(self.db)
        self.root = worker.repo.witness.parent.parent / 'attachments'
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink():
            fail('ATTACHMENT_NOT_READY')
        if os.name != 'nt':
            self.root.chmod(448)
        self.uploads = set()
        self.http_factory = lambda: httpx.AsyncClient(follow_redirects=False, trust_env=False, timeout=60)
        self.streams = {}
        self.maintenance_at = 0

    def directory(self, conversation):
        # Local IDs are opaque, but imported/remote IDs need not be safe path components.
        key = self.directory_key(conversation)
        path = self.root / key
        path.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or path.resolve().parent != self.root.resolve():
            fail('ATTACHMENT_NOT_READY')
        if os.name != 'nt':
            path.chmod(448)
        return path

    @staticmethod
    def directory_key(conversation):
        return conversation if re.fullmatch('[A-Za-z0-9_-]{1,128}', conversation) else hashlib.sha256(conversation.encode()).hexdigest()

    def path(self, row):
        if not row['file_key'] or not re.fullmatch('[a-f0-9]{32}\\.[a-z0-9]{1,8}', row['file_key']):
            fail('ATTACHMENT_NOT_READY')
        path = self.directory(row['conversation_id']) / row['file_key']
        if path.is_symlink():
            fail('ATTACHMENT_NOT_READY')
        return path

    def check(self, row):
        manifest = json.loads(row['manifest_json'])
        path = self.path(row)
        try:
            actual, _ = inspect_file(path, manifest['fileName'], manifest['sizeBytes'], manifest['sha256'])
        except OSError:
            fail('ATTACHMENT_NOT_READY')
        if any((actual[k] != manifest[k] for k in ('kind', 'mimeType', 'sizeBytes', 'sha256'))):
            fail('ATTACHMENT_HASH_MISMATCH')
        return str(path)

    def headers(self, headers):
        try:
            length = int(headers.get('content-length', '0'))
        except ValueError:
            fail('BAD_REQUEST')
        if length == 0:
            fail('VALIDATION_FAILED')
        if length < 0 or headers.get('content-type', '').split(';')[0] != 'application/octet-stream':
            fail('BAD_REQUEST')
        if length > LIMITS.file_max_bytes:
            fail('ATTACHMENT_TOO_LARGE')
        hash_ = headers.get('x-content-sha256', '')
        if not re.fullmatch('[0-9a-f]{64}', hash_):
            fail('BAD_REQUEST')
        name = self.worker.link.sanitized(display_name(headers.get('x-file-name', '')))
        key = headers.get('idempotency-key')
        if not key or len(key) > 200:
            fail('VALIDATION_FAILED')
        return (length, hash_, name, key)

    def public_text(self, text):
        for root in {str(self.root), self.root.as_posix(), str(self.root).replace('\\', '\\\\')}:
            text = re.sub(re.escape(root) + '[/\\\\]+[A-Za-z0-9_-]+[/\\\\]+[a-f0-9]{32}\\.[a-z0-9]{1,8}', '[本机附件]', text)
        return text

    async def upload(self, conversation, request):
        async with self.worker.bridge.chat._conversation_lock(conversation):
            return await self._upload(conversation, request)

    async def _upload(self, conversation, request):
        self.worker.bridge.chat.repository.conversation(conversation)
        length, hash_, name, key = self.headers(request.headers)
        digest = request_hash([length, hash_, name])
        scope = (conversation, key)
        if scope in self.uploads:
            fail('CONFLICT')
        self.uploads.add(scope)
        temporary = self.directory(conversation) / (uid('part') + '.part')
        final = None
        try:
            with self.db.transaction() as tx:
                old = tx.connection.execute('SELECT * FROM attachment_upload_keys WHERE conversation_id=? AND request_key=?', scope).fetchone()
                if old and old['digest'] != digest:
                    fail('IDEMPOTENCY_MISMATCH')
                if not old:
                    tx.connection.execute('INSERT INTO attachment_upload_keys VALUES(?,?,?,NULL)', (*scope, digest))
            count = 0
            prefix = b''
            with temporary.open('xb') as stream:
                if os.name != 'nt':
                    os.chmod(temporary, 384)
                async with asyncio.timeout(120):
                    async for data in request.stream():
                        for offset in range(0, len(data), CHUNK):
                            chunk = data[offset:offset + CHUNK]
                            count += len(chunk)
                            if len(prefix) < 12:
                                prefix += chunk[:12 - len(prefix)]
                            if count > length:
                                fail('ATTACHMENT_HASH_MISMATCH')
                            if image_mime(prefix) and count > LIMITS.image_max_bytes:
                                fail('ATTACHMENT_TOO_LARGE')
                            await self.worker.native.io(stream.write, chunk)
                    await self.worker.native.io(stream.flush)
                    await self.worker.native.io(os.fsync, stream.fileno())
            metadata, ext = await self.worker.native.io(inspect_file, temporary, name, length, hash_)
            if old and old['attachment_id']:
                await self.worker.native.io(self.check, self.repo.row(old['attachment_id']))
                return self.repo.view(old['attachment_id'])
            import uuid
            file_key = uuid.uuid4().hex + ext
            final = self.directory(conversation) / file_key
            await self.worker.native.io(os.replace, temporary, final)
            identifier = uid('attachment')
            manifest = AttachmentManifestItem(attachmentId=identifier, **metadata).model_dump(mode='json', by_alias=True)
            with self.db.transaction() as tx:
                self.worker.bridge.chat.repository.conversation(conversation)
                self.repo.insert(tx, conversation, manifest, file_key)
                tx.connection.execute('UPDATE attachment_upload_keys SET attachment_id=? WHERE conversation_id=? AND request_key=?', (identifier, *scope))
                self.worker.repo.seal(tx)
            final = None
            return self.repo.view(identifier)
        except TimeoutError:
            fail('ATTACHMENT_DOWNLOAD_FAILED')
        except OSError:
            fail('ATTACHMENT_NOT_READY')
        finally:
            temporary.unlink(missing_ok=True)
            if final:
                final.unlink(missing_ok=True)
            self.uploads.discard(scope)

    def delete(self, identifier):
        with self.db.transaction() as tx:
            row = self.repo.row(identifier, tx)
            if row['state'] != 'uploaded':
                fail('ATTACHMENT_IN_USE')
            tx.connection.execute("UPDATE local_attachments SET state='deleted' WHERE attachment_id=?", (identifier,))
            self.worker.repo.seal(tx)
        self.erase(row)
        return {'attachmentId': identifier, 'deleted': True}

    async def quiesce_conversation(self, conversation):
        """Stop only file I/O owned by this conversation, never model execution."""
        with self.db.locked_connection() as db:
            rows = [dict(row) for row in db.execute(
                'SELECT * FROM local_attachments WHERE conversation_id=?', (conversation,))]
        identifiers = {row['attachment_id'] for row in rows}
        sync = self.worker.attachments.sync
        jobs = [task for key, task in list(sync.jobs.items()) if key[-1] in identifiers]
        for task in jobs:
            task.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        for identifier in identifiers:
            for stream in list(self.streams.pop(identifier, ())):
                stream.close()

    async def erase_conversation(self, conversation):
        """Close readers and writers before removing only Hub-owned attachment files."""
        await self.quiesce_conversation(conversation)
        directory = self.root / self.directory_key(conversation)
        if not directory.exists():
            return
        if directory.is_symlink() or directory.resolve().parent != self.root.resolve():
            raise OSError('invalid attachment directory')
        # Storage owns this flat per-conversation directory; never follow links,
        # recurse into a workspace, or touch a vendor history source.
        for path in directory.iterdir():
            if path.is_dir() and not path.is_symlink():
                raise OSError('unexpected attachment directory')
            path.unlink(missing_ok=True)
        directory.rmdir()

    def erase(self, row):
        for stream in list(self.streams.get(row['attachment_id'], ())):
            stream.close()
        if row['file_key']:
            self.path(row).unlink(missing_ok=True)
        with self.db.transaction() as tx:
            tx.connection.execute("UPDATE local_attachments SET file_key=NULL,manifest_json='{}',sync_json='{}',origin_id=NULL WHERE attachment_id=? AND state IN ('deleted','expired')", (row['attachment_id'],))
            tx.connection.execute('DELETE FROM local_attachment_messages WHERE attachment_id=?', (row['attachment_id'],))
            tx.connection.execute('DELETE FROM attachment_sync_jobs WHERE attachment_id=?', (row['attachment_id'],))
            self.worker.repo.seal(tx)

    def _expired(self):
        with self.db.transaction() as tx:
            tx.connection.execute("UPDATE local_attachments SET state='expired' WHERE state='uploaded' AND expires_at<=?", (now(),))
            return [dict(r) for r in tx.connection.execute("SELECT * FROM local_attachments WHERE state IN ('deleted','expired')")]

    async def maintain(self, *, restart=False):
        import time
        if not restart and time.monotonic() - self.maintenance_at < 60:
            return
        self.maintenance_at = time.monotonic()
        rows = await self.worker.native.io(self._expired)
        for row in rows:
            await self.worker.native.io(self.erase, row)
        if restart:
            for path in self.root.glob('*/*.part'):
                await self.worker.native.io(path.unlink, missing_ok=True)
            with self.db.locked_connection() as db:
                live = {(self.directory_key(r[0]), r[1]) for r in db.execute('SELECT conversation_id,file_key FROM local_attachments WHERE file_key IS NOT NULL')}
            for path in self.root.glob('*/*'):
                if path.is_file() and (path.parent.name, path.name) not in live:
                    await self.worker.native.io(path.unlink, missing_ok=True)

    def origin(self):
        view = self.worker.repo.get('link')['view']
        if view.get('state') != 'paired':
            fail('REMOTE_DEVICE_REVOKED')
        return normalize_origin(view['serverOrigin'], development=self.worker.link.development)

    async def fetch(self, manifest, conversation, command):
        import uuid
        if manifest['sizeBytes'] > (LIMITS.image_max_bytes if manifest['kind'] == 'image' else LIMITS.file_max_bytes):
            fail('ATTACHMENT_TOO_LARGE')
        temporary = self.directory(conversation) / (uuid.uuid4().hex + '.part')
        try:
            for attempt in range(3):
                try:
                    async with asyncio.timeout(60):
                        async with attachment_client(self.http_factory) as client:
                            url = self.origin() + '/api/v2/worker/attachments/' + quote(manifest['attachmentId'], safe='') + '/content'
                            async with client.stream('GET', url, params={'commandId': command}, follow_redirects=False, headers={'Authorization': 'Bearer ' + self.worker.link.vault.read()}) as response:
                                if response.status_code >= 500:
                                    raise httpx.NetworkError('temporary')
                                if response.status_code != 200:
                                    fail('ATTACHMENT_DOWNLOAD_FAILED')
                                if response.headers.get('content-length') != str(manifest['sizeBytes']):
                                    fail('ATTACHMENT_HASH_MISMATCH')
                                count = 0
                                with temporary.open('wb') as stream:
                                    if os.name != 'nt':
                                        os.chmod(temporary, 384)
                                    async for chunk in response.aiter_bytes(CHUNK):
                                        count += len(chunk)
                                        if count > manifest['sizeBytes']:
                                            fail('ATTACHMENT_HASH_MISMATCH')
                                        await self.worker.native.io(stream.write, chunk)
                                    await self.worker.native.io(stream.flush)
                                    await self.worker.native.io(os.fsync, stream.fileno())
                        actual, ext = await self.worker.native.io(inspect_file, temporary, manifest['fileName'], manifest['sizeBytes'], manifest['sha256'])
                        if any((actual[k] != manifest[k] for k in ('mimeType', 'kind'))):
                            fail('ATTACHMENT_TYPE_UNSUPPORTED')
                        file_key = uuid.uuid4().hex + ext
                        await self.worker.native.io(os.replace, temporary, self.directory(conversation) / file_key)
                        return file_key
                except (httpx.TransportError, TimeoutError):
                    temporary.unlink(missing_ok=True)
                    if attempt == 2:
                        fail('ATTACHMENT_DOWNLOAD_FAILED')
                    await asyncio.sleep(attempt + 1)
        finally:
            temporary.unlink(missing_ok=True)

    async def thumbnail(self, identifier):
        row = self.repo.row(identifier)
        view = self.worker.repo.get('link')['view']
        state = json.loads(row['sync_json'])
        if view.get('state') != 'paired' or view.get('connectionStatus') != 'online' or (not state.get('serverId')):
            fail('ATTACHMENT_THUMBNAIL_UNAVAILABLE')
        async with attachment_client(self.http_factory) as client:
            url = self.origin() + '/api/v2/worker/attachments/' + quote(state['serverId'], safe='') + '/content'
            async with client.stream('GET', url, params={'variant': 'thumbnail'}, follow_redirects=False, headers={'Authorization': 'Bearer ' + self.worker.link.vault.read()}) as response:
                if response.status_code != 200 or response.headers.get('content-type') != 'image/png':
                    fail('ATTACHMENT_THUMBNAIL_UNAVAILABLE')
                result = bytearray()
                async for chunk in response.aiter_bytes(CHUNK):
                    if len(result) + len(chunk) > 524288:
                        fail('ATTACHMENT_THUMBNAIL_UNAVAILABLE')
                    result.extend(chunk)
                if response.headers.get('content-length') != str(len(result)) or not result.startswith(b'\x89PNG\r\n\x1a\n'):
                    fail('ATTACHMENT_THUMBNAIL_UNAVAILABLE')
                return bytes(result)
