"""Upload bytes only after the server ACKed the complete pending message."""
import asyncio
import json
from urllib.parse import quote
import httpx
from core.errors import HubError
from runtime.attachments.content import CHUNK
from runtime.attachments.transport import attachment_client
from storage.local_chat import now

class AttachmentSync:

    def __init__(self, service):
        self.service = service
        self.worker = service.worker
        self.db = service.library.db
        self.jobs = {}
        self.closed = False

    def manifest(self, tx, message):
        store = self.worker.repo.get('identity', tx)['store']
        generation = self.worker.sync.settings().sync_generation
        values = []
        source = None
        original = self.service.repo.source(message, tx)
        current_origin = original.get('store') == store and original.get('generation') == generation
        for row in self.service.repo.message_rows(message):
            meta = json.loads(row['manifest_json'])
            if current_origin and row['origin_id'] and row['source_command_id']:
                value = {k: v for k, v in meta.items() if k != 'attachmentId'}
                value.update(localAttachmentId=row['attachment_id'], originAttachmentId=row['origin_id'], availability='available')
                source = row['source_command_id']
            else:
                key = (store, generation, message, row['attachment_id'])
                tx.connection.execute("INSERT OR IGNORE INTO attachment_sync_jobs(store_id,generation,message_id,attachment_id,status) VALUES(?,?,?,?,'pending_upload')", key)
                job = tx.connection.execute('SELECT * FROM attachment_sync_jobs WHERE store_id=? AND generation=? AND message_id=? AND attachment_id=?', key).fetchone()
                if job['status'] == 'pending_upload':
                    tx.connection.execute('UPDATE local_attachments SET sync_json=? WHERE attachment_id=?', (json.dumps({'status': 'pending_upload'}), row['attachment_id']))
                value = {k: v for k, v in meta.items() if k != 'attachmentId'}
                value.update(localAttachmentId=row['attachment_id'], availability=job['status'])
                if job['error_code']:
                    value['errorCode'] = job['error_code']
            values.append(value)
        return (values, source)

    def allocated(self, tx, message, seq, payload):
        if any((v['availability'] == 'pending_upload' for v in payload.get('attachments', []))):
            store, generation = self.worker.sync.context()
            tx.connection.execute("UPDATE attachment_sync_jobs SET after_seq=COALESCE(after_seq,?) WHERE store_id=? AND generation=? AND message_id=? AND status='pending_upload'", (seq, store, generation, message))

    def pending(self, tx):
        store, generation = self.worker.sync.context()
        return tx.connection.execute("SELECT 1 FROM attachment_sync_jobs WHERE store_id=? AND generation=? AND status='pending_upload' LIMIT 1", (store, generation)).fetchone() is not None

    async def tick(self):
        if self.closed or self.worker.repo.get('identity')['wireRevision'] < 4 or (not self.worker.sync.settings().mirror_enabled):
            return
        store, generation = self.worker.sync.context()
        ack = self.worker.repo.get('identity')['ack'] or 0
        with self.db.locked_connection() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM attachment_sync_jobs WHERE store_id=? AND generation=? AND status='pending_upload' AND after_seq<=? ORDER BY rowid LIMIT 1", (store, generation, ack))]
        for row in rows:
            attachment = self.service.repo.row(row['attachment_id'])
            if not attachment['file_key']:
                with self.db.locked_connection() as db:
                    preparing = db.execute("SELECT 1 FROM local_runs r JOIN attachment_preparations p ON p.run_id=r.run_id WHERE r.message_id=? AND p.state IN ('pending','preparing','ready')", (row['message_id'],)).fetchone()
                if preparing:
                    continue
            key = (store, generation, row['message_id'], row['attachment_id'])
            if key in self.jobs:
                continue
            job = asyncio.create_task(self.upload(row))
            self.jobs[key] = job

            def done(task, k=key):
                self.jobs.pop(k, None)
                if not task.cancelled():
                    task.exception()
            job.add_done_callback(done)

    def active(self, row):
        return self.worker.sync.settings().mirror_enabled and self.worker.sync.context() == (row['store_id'], row['generation']) and (self.worker.repo.get('link')['view']['state'] == 'paired')

    async def upload(self, row):
        library = self.service.library
        key = (row['store_id'], row['generation'], row['message_id'], row['attachment_id'])
        result = None
        code = None
        try:
            attachment = self.service.repo.row(row['attachment_id'])
            metadata = json.loads(attachment['manifest_json'])
            path = await self.worker.native.io(library.check, attachment)
            for attempt in range(row['attempts'], 3):
                if not self.active(row):
                    return
                with self.db.transaction() as tx:
                    tx.connection.execute('UPDATE attachment_sync_jobs SET attempts=? WHERE store_id=? AND generation=? AND message_id=? AND attachment_id=?', (attempt + 1, *key))

                async def chunks():
                    with open(path, 'rb') as stream:
                        while True:
                            if not self.active(row):
                                raise asyncio.CancelledError()
                            chunk = await self.worker.native.io(stream.read, CHUNK)
                            if not chunk:
                                return
                            yield chunk
                headers = {'Authorization': 'Bearer ' + self.worker.link.vault.read(), 'Content-Type': 'application/octet-stream', 'Content-Length': str(metadata['sizeBytes']), 'X-File-Name': quote(metadata['fileName'], safe=''), 'X-Content-Sha256': metadata['sha256'], 'Idempotency-Key': 'upload:' + ':'.join(map(str, key)), 'X-Worker-Store-Id': row['store_id'], 'X-Sync-Generation': str(row['generation']), 'X-Local-Conversation-Id': attachment['conversation_id'], 'X-Local-Message-Id': row['message_id'], 'X-Local-Attachment-Id': row['attachment_id']}
                try:
                    async with asyncio.timeout(120):
                        async with attachment_client(library.http_factory) as client:
                            response = await client.post(library.origin() + '/api/v2/worker/attachments', headers=headers, content=chunks(), follow_redirects=False)
                    if response.status_code >= 500:
                        raise httpx.NetworkError('temporary')
                    if response.status_code not in {200, 201}:
                        try:
                            code = response.json()['error']['code']
                        except Exception:
                            code = 'ATTACHMENT_DOWNLOAD_FAILED'
                        break
                    from protocol.generated.python import RemoteAttachmentView
                    result = RemoteAttachmentView.model_validate(response.json()['data'])
                    break
                except (httpx.TransportError, TimeoutError):
                    if attempt == 2:
                        code = 'ATTACHMENT_DOWNLOAD_FAILED'
                        break
                    await asyncio.sleep(attempt + 1)
            if result is None and code is None:
                code = 'ATTACHMENT_DOWNLOAD_FAILED'
        except asyncio.CancelledError:
            raise
        except Exception as error:
            code = error.code if isinstance(error, HubError) else 'ATTACHMENT_DOWNLOAD_FAILED'
        if not self.active(row):
            return
        status = 'available' if result else 'unavailable'
        from protocol.generated.python import RemoteWire4ErrorCode
        if code:
            try:
                RemoteWire4ErrorCode(code)
            except ValueError:
                code = 'ATTACHMENT_DOWNLOAD_FAILED'
        with self.db.transaction() as tx:
            if not self.active(row):
                return
            current = self.service.repo.row(row['attachment_id'], tx)
            tx.connection.execute('UPDATE attachment_sync_jobs SET status=?,server_id=?,error_code=? WHERE store_id=? AND generation=? AND message_id=? AND attachment_id=?', (status, result.attachment.attachment_id if result else None, code, *key))
            tx.connection.execute('UPDATE local_attachments SET sync_json=? WHERE attachment_id=?', (json.dumps({'status': status, 'serverId': result.attachment.attachment_id if result else None, 'error': code}), row['attachment_id']))
            message = tx.connection.execute('SELECT * FROM local_messages WHERE message_id=?', (row['message_id'],)).fetchone()
            work = self.worker.repo.get('sync-work', tx) or {}
            if message and work.get('backfillId'):
                self.worker.sync._stage(tx, work['backfillId'], 'message', message)
            self.service.repo.touch_message(tx, row['message_id'])
            self.worker.repo.seal(tx)

    async def stop(self):
        self.closed = True
        self.cancel_pending()
        await asyncio.gather(*list(self.jobs.values()), return_exceptions=True)

    def cancel_pending(self):
        for task in list(self.jobs.values()):
            task.cancel()
