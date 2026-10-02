"""Durable all-or-nothing input preparation, before any Task/Agent start."""
import asyncio
from contextvars import ContextVar
import json
from core.errors import HubError
from protocol.generated.python import AgentInputAttachment, SendLocalMessageInput
from runtime.attachments.library import AttachmentLibrary
from runtime.attachments.capabilities import ImageCapabilities
from storage.local_chat import now, uid
CURRENT_INPUTS = ContextVar('local_attachment_inputs', default=())

class AttachmentService:

    def __init__(self, worker):
        self.worker = worker
        self.chat = worker.bridge.chat
        self.library = AttachmentLibrary(worker)
        self.repo = self.library.repo
        self.capabilities = ImageCapabilities(worker)
        from runtime.attachments.sync import AttachmentSync
        self.sync = AttachmentSync(self)
        self.jobs = {}
        self.locks = {}
        self.recovered = False
        self.chat.attachments = self
        self.chat.repository.attachments = self
        self.library.db.attachment_service = self

    async def check_execution(self, agent, model, inputs):
        if not any((v.get('attachment', {}).get('kind') == 'image' for v in inputs)):
            return
        adapter = self.chat.ports.tasks.directory.adapter_for(agent.instance_id)
        descriptor = await adapter.detect()
        cap = self.capabilities.store.capability(str(agent.adapter_id), getattr(descriptor, 'detected_version', ''), model)
        if cap.support != 'supported' or any((v['attachment']['mimeType'] not in cap.mime_types for v in inputs if v['attachment']['kind'] == 'image')):
            raise HubError('AGENT_IMAGE_UNSUPPORTED', '实际派发Agent图片输入未经当前版本验证')

    def lock(self, run):
        return self.locks.setdefault(run, asyncio.Lock())

    def bind_local(self, tx, conversation, message, run, identifiers):
        manifests = [json.loads(self.repo.row(i, tx)['manifest_json']) for i in identifiers]
        self.capabilities.require(conversation, manifests)
        self.repo.bind(tx, conversation, message, run, identifiers)
        if any((self.repo.row(i, tx)['file_key'] is None for i in identifiers)):
            prior = tx.connection.execute('SELECT p.source_json FROM attachment_preparations p JOIN local_runs r ON r.run_id=p.run_id JOIN local_attachment_messages a ON a.message_id=r.message_id WHERE a.attachment_id=? AND p.run_id<>? ORDER BY r.created_at LIMIT 1', (identifiers[0], run)).fetchone()
            if prior:
                tx.connection.execute('UPDATE attachment_preparations SET source_json=? WHERE run_id=?', (prior[0], run))

    def bind_remote(self, tx, frame, receipt):
        identifiers = []
        for original in frame['payload'].get('attachments', []):
            identifier = uid('attachment')
            manifest = {**original, 'attachmentId': identifier}
            self.repo.insert(tx, frame['localConversationId'], manifest, None, origin=original['attachmentId'])
            tx.connection.execute('UPDATE local_attachments SET sync_json=? WHERE attachment_id=?', (json.dumps({'status': 'available', 'serverId': original['attachmentId']}), identifier))
            identifiers.append(identifier)
        self.repo.bind(tx, frame['localConversationId'], receipt.message_id, receipt.run_id, identifiers, source={'commandId': frame['commandId'], 'store': frame['expectedWorkerStoreId'], 'worker': frame['targetWorkerId'], 'generation': self.worker.sync.settings().sync_generation})
        if identifiers:
            self.repo.transition(tx, receipt.run_id, 'ungranted')

    def retry_preparation(self, record, key):

        def create(tx):
            state = self.repo.preparation(record['run_id'], tx)
            identifiers = []
            for row in self.repo.message_rows(record['message_id']):
                identifier = uid('attachment')
                manifest = {**json.loads(row['manifest_json']), 'attachmentId': identifier}
                self.repo.insert(tx, record['conversation_id'], manifest, row['file_key'], origin=row['origin_id'])
                identifiers.append(identifier)
            receipt = self.chat.repository.enqueue(record['conversation_id'], SendLocalMessageInput(clientMessageId=key, text=self.chat.repository.run_text(record['run_id']), sessionMode=record['session_mode'], attachmentIds=identifiers), key, transaction=tx)
            tx.connection.execute('UPDATE attachment_preparations SET source_json=? WHERE run_id=?', (state['source_json'], receipt.run_id))
            return {'runId': receipt.run_id}
        value, _ = self.chat.repository.command('attachment-retry:' + record['run_id'], key, {}, create)
        self.chat.wake_remote_queue()
        return value['runId']

    async def prepare(self, record):
        state = self.repo.preparation(record['run_id'])
        if state is None:
            return []
        run = record['run_id']
        if state['state'] in {'cancelled', 'failed'}:
            raise HubError(state['error_code'] or 'ATTACHMENT_NOT_READY', '附件准备未完成')

        async def perform():
            with self.library.db.transaction() as tx:
                current = self.repo.preparation(run, tx)
                if current['state'] not in {'pending', 'preparing', 'ready'}:
                    raise HubError('ATTACHMENT_NOT_READY', '附件准备门闩未开放')
                self.repo.transition(tx, run, 'preparing')
                self.worker.repo.seal(tx)
            async with asyncio.timeout(300):
                rows = self.repo.message_rows(record['message_id'])
                if any(json.loads(row['manifest_json'])['kind'] == 'image' for row in rows):
                    await self.capabilities.refresh()
                self.capabilities.require(record['conversation_id'], [json.loads(r['manifest_json']) for r in rows])
                for row in rows:
                    if not row['file_key']:
                        source = json.loads(state['source_json'])
                        if source.get('store') != self.worker.repo.get('identity')['store']:
                            raise HubError('REMOTE_STORE_CHANGED', '附件准备绑定已变化')
                        delivery = self.worker.delivery.row(source['commandId'])
                        receipt = json.loads(delivery['result_json']) if delivery else {}
                        accepted_seq = receipt.get('seq')
                        if accepted_seq is None:
                            raise HubError('ATTACHMENT_NOT_READY', '附件接单回执尚未持久提交')
                        # P1 authorizes command-bound reads after applying accepted.
                        # This ACK is a transport prerequisite, never an execution grant.
                        while (self.worker.repo.get('identity')['ack'] or 0) < accepted_seq:
                            if self.worker.repo.get('identity')['store'] != source['store']:
                                raise HubError('REMOTE_STORE_CHANGED', '附件准备绑定已变化')
                            await asyncio.sleep(0.05)
                        manifest = {**json.loads(row['manifest_json']), 'attachmentId': row['origin_id']}
                        key = await self.library.fetch(manifest, record['conversation_id'], source['commandId'])
                        with self.library.db.transaction() as tx:
                            current = self.repo.preparation(run, tx)
                            if current['state'] != 'preparing':
                                self.library.directory(record['conversation_id']).joinpath(key).unlink(missing_ok=True)
                                raise asyncio.CancelledError()
                            tx.connection.execute('UPDATE local_attachments SET file_key=? WHERE attachment_id=?', (key, row['attachment_id']))
                            self.worker.repo.seal(tx)
                    await self.worker.native.io(self.library.check, self.repo.row(row['attachment_id']))
                inputs = [AgentInputAttachment(attachment=json.loads(row['manifest_json']), localPath=await self.worker.native.io(self.library.check, row)) for row in self.repo.message_rows(record['message_id'])]
                if any(value.attachment.kind == 'image' for value in inputs):
                    await self.capabilities.refresh()
                self.capabilities.require(record['conversation_id'], [v.attachment.model_dump(mode='json', by_alias=True) for v in inputs])
                with self.library.db.transaction() as tx:
                    self.repo.transition(tx, run, 'ready')
                    self.worker.repo.seal(tx)
                return inputs
        job = asyncio.create_task(perform())
        self.jobs[run] = job
        try:
            return await job
        except TimeoutError:
            with self.library.db.transaction() as tx:
                self.repo.transition(tx, run, 'failed', code='ATTACHMENT_DOWNLOAD_FAILED')
                self.worker.repo.seal(tx)
            raise HubError('ATTACHMENT_DOWNLOAD_FAILED', '附件准备超过总时限') from None
        except asyncio.CancelledError:
            raise
        except Exception as error:
            with self.library.db.transaction() as tx:
                self.repo.transition(tx, run, 'failed', code=error.code if isinstance(error, HubError) else 'ATTACHMENT_DOWNLOAD_FAILED')
                self.worker.repo.seal(tx)
            if isinstance(error, HubError):
                raise
            raise HubError('ATTACHMENT_DOWNLOAD_FAILED', '附件准备失败') from None
        finally:
            self.jobs.pop(run, None)

    async def start_task(self, record, inputs, spec):
        async with self.lock(record['run_id']):
            state = self.repo.preparation(record['run_id'])
            if state:
                with self.library.db.transaction() as tx:
                    current = self.repo.preparation(record['run_id'], tx)
                    if current['state'] != 'ready':
                        raise asyncio.CancelledError()
                    self.repo.transition(tx, record['run_id'], 'starting')
                    self.worker.repo.seal(tx)
            token = CURRENT_INPUTS.set(tuple(inputs))
            try:
                task = await self.chat.ports.tasks.create_task(spec, 'local-run:' + record['run_id'])
            finally:
                CURRENT_INPUTS.reset(token)
            if state:
                with self.library.db.transaction() as tx:
                    self.repo.transition(tx, record['run_id'], 'started')
                    self.worker.repo.seal(tx)
            return task

    async def cancel(self, run):
        async with self.lock(run):
            state = self.repo.preparation(run)
            if state is None or state['state'] not in {'pending', 'preparing', 'ready', 'cancelled'}:
                return False
            job = self.jobs.get(run)
            if job:
                job.cancel()
                await asyncio.gather(job, return_exceptions=True)
            evidence = {'outcome': 'confirmed', 'executionMayStillBeRunning': False, 'orphanProcessIds': [], 'evidence': 'input_preparation_cancelled', 'reason': '输入准备已停止，尚未派发Agent', 'observedAt': now()}
            with self.library.db.transaction() as tx:
                current = self.repo.preparation(run, tx)
                if current['state'] not in {'pending', 'preparing', 'ready', 'cancelled'}:
                    return False
                self.repo.transition(tx, run, 'cancelled', evidence=evidence)
                self.chat.repository.complete_run(run, 'cancelled', '本轮输入准备已取消。', transaction=tx)
                self.worker.repo.seal(tx)
            return True

    async def recover(self):
        if self.recovered:
            return
        await self.library.maintain(restart=True)
        with self.library.db.transaction() as tx:
            rows = tx.connection.execute("SELECT run_id FROM attachment_preparations WHERE state IN ('pending','preparing','ready')").fetchall()
            for row in rows:
                self.repo.transition(tx, row[0], 'failed', code='ATTACHMENT_PREPARATION_INTERRUPTED')
                self.chat.repository.complete_run(row[0], 'failed', '附件准备因上次进程中断而失败，请显式重试。', error='附件准备中断', error_code='ATTACHMENT_PREPARATION_INTERRUPTED', transaction=tx)
            self.worker.repo.seal(tx)
        self.recovered = True

    async def stop(self):
        await self.sync.stop()
        for job in list(self.jobs.values()):
            job.cancel()
        await asyncio.gather(*list(self.jobs.values()), return_exceptions=True)
