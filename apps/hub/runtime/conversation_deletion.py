"""Durable, local-only conversation erasure and existing-wire deletion facts."""
from __future__ import annotations

import json
import logging
import os
import shutil
import uuid

from core.errors import HubError
from protocol.generated.python import LocalConversationDeletionView
from storage.idempotency import request_hash
from storage.local_chat import TERMINAL, now, uid


def initialize_deletion_storage(database):
    # These additive maintenance tables also work while legacy fixture stores
    # are opened before their normal schema upgrade.
    with database.transaction() as tx:
        tx.connection.execute('''CREATE TABLE IF NOT EXISTS local_conversation_deletions (
            conversation_id TEXT PRIMARY KEY, request_key_hash TEXT NOT NULL,
            expected_version INTEGER NOT NULL, deleted_at TEXT NOT NULL,
            state TEXT NOT NULL, remote_status TEXT NOT NULL,
            remote_store TEXT, remote_seq INTEGER)''')
        tx.connection.execute('''CREATE TABLE IF NOT EXISTS local_deleted_native_bindings (
            binding_key TEXT PRIMARY KEY)''')
        tx.connection.execute('''CREATE TABLE IF NOT EXISTS local_deleted_execution_resources (
            resource_id TEXT PRIMARY KEY, kind TEXT NOT NULL)''')
        tx.connection.execute('''CREATE TRIGGER IF NOT EXISTS local_conversation_deletion_fence
            BEFORE INSERT ON local_conversations
            WHEN EXISTS(SELECT 1 FROM local_conversation_deletions
                        WHERE conversation_id=NEW.conversation_id)
            BEGIN SELECT RAISE(ABORT, 'conversation_deleted'); END''')


def _contains(value, identifiers, identifier_context=False):
    """Exact structured identifiers, never substring-match user text or paths."""
    if isinstance(value, dict):
        return any(_contains(v, identifiers, identifier_context or
                   key.lower().replace('_', '').endswith(('id', 'ids')) or key in {'resumeSessions'})
                   for key, v in value.items())
    if isinstance(value, list):
        return any(_contains(v, identifiers, identifier_context) for v in value)
    return identifier_context and isinstance(value, str) and value in identifiers


class ConversationDeletion:
    def __init__(self, chat):
        self.chat = chat
        self.db = chat.repository.database

    @property
    def worker(self):
        attachments = getattr(self.chat, 'attachments', None)
        return attachments.worker if attachments else None

    def _row(self, conversation, connection=None):
        with self.db.locked_connection() as db:
            row = (connection or db).execute(
                'SELECT * FROM local_conversation_deletions WHERE conversation_id=?',
                (conversation,),
            ).fetchone()
        return dict(row) if row else None

    def _tasks(self, connection, runs):
        direct = {r['task_id'] for r in runs if r['task_id']}
        profiles = {'local-profile:' + r['run_id'] for r in runs}
        tasks = [dict(r) for r in connection.execute('SELECT * FROM tasks')]
        selected = {t['task_id'] for t in tasks if t['task_id'] in direct or t['profile_id'] in profiles}
        # Execution child tasks can be created before LocalRun.task_id is bound.
        while True:
            expanded = selected | {t['task_id'] for t in tasks
                                   if json.loads(t['payload_json']).get('parentTaskId') in selected}
            if expanded == selected:
                return [t for t in tasks if t['task_id'] in selected]
            selected = expanded

    def _execution_scope(self, db, conversation):
        runs = [dict(r) for r in db.execute('SELECT * FROM local_runs WHERE conversation_id=?', (conversation,))]
        tasks = self._tasks(db, runs)
        task_ids = {t['task_id'] for t in tasks}
        shared = {r[0] for r in db.execute('SELECT task_id FROM local_runs WHERE conversation_id<>?', (conversation,))}
        session_owners = {r['session_id']: r['task_id'] for r in db.execute('SELECT session_id,task_id FROM sessions')
                          if r['task_id'] in task_ids}
        for spec in db.execute("SELECT key,value_json FROM hub_state WHERE key LIKE 'task_spec:%'"):
            if spec['key'][len('task_spec:'):] not in task_ids:
                value = json.loads(spec['value_json'])
                shared.update(owner for session, owner in session_owners.items() if _contains(value, {session}))
        while True:
            related = shared | {t['task_id'] for t in tasks
                                if json.loads(t['payload_json']).get('parentTaskId') in shared}
            if related == shared:
                return runs, tasks, task_ids - shared
            shared = related

    def _blockers(self, tx, conversation, runs, tasks):
        blockers, reasons = set(), set()
        if self.worker and self.worker.repo.get('link', tx)['view'].get('workerId'):
            # Include not-yet-projected source slots in the same preflight.
            # The ordinary Worker pump will deliver them if this check blocks.
            self.worker.repo.cover_private(tx)
        by_task = {r['task_id']: r['run_id'] for r in runs if r['task_id']}
        by_profile = {'local-profile:' + r['run_id']: r['run_id'] for r in runs}
        ids = {r['run_id'] for r in runs}
        for run in runs:
            reason = None
            if run['status'] not in TERMINAL:
                reason = 'active_runs'
            gate = tx.connection.execute('SELECT state FROM remote2_gates WHERE run_id=?', (run['run_id'],)).fetchone()
            prep = tx.connection.execute('SELECT state,evidence_json FROM attachment_preparations WHERE run_id=?', (run['run_id'],)).fetchone()
            if gate and gate[0] == 'recovery':
                reason = 'recovery_required'
            if prep:
                evidence = json.loads(prep[1] or '{}')
                if prep[0] in {'pending', 'preparing', 'ready', 'ungranted', 'starting', 'cancel_requested'}:
                    reason = 'active_runs'
                if evidence.get('recoveryRequired') or evidence.get('unresolvedCancellation'):
                    reason = 'cancellation_unconfirmed'
            attachment_service = getattr(self.chat, 'attachments', None)
            pending = attachment_service.jobs.get(run['run_id']) if attachment_service else None
            if pending and not pending.done():
                reason = 'active_runs'
            if reason:
                blockers.add(run['run_id'])
                reasons.add(reason)
        for task in tasks:
            reason = 'active_runs' if task['status'] not in TERMINAL else None
            spec = tx.connection.execute('SELECT value_json FROM hub_state WHERE key=?', ('task_spec:' + task['task_id'],)).fetchone()
            state = json.loads(spec[0]) if spec else {}
            if state.get('recoveryRequired') or state.get('pauseRequested'):
                reason = 'recovery_required'
            if state.get('unresolvedCancellation'):
                reason = 'cancellation_unconfirmed'
            if any(r[0] not in TERMINAL | {'skipped'} for r in tx.connection.execute(
                    'SELECT status FROM task_nodes WHERE task_id=?', (task['task_id'],))):
                reason = reason or 'active_runs'
            task_service = self.chat.ports.tasks
            if task['task_id'] in getattr(task_service, '_dispatching', ()) or any(
                row[0] in getattr(task_service, '_outcomes', {}) for row in tx.connection.execute(
                    'SELECT node_id FROM task_nodes WHERE task_id=?', (task['task_id'],))
            ):
                reason = 'active_runs'
            for session in tx.connection.execute('SELECT session_id,agent_instance_id FROM sessions WHERE task_id=?', (task['task_id'],)):
                registry = self._registry(session['agent_instance_id'])
                state = registry.get(session['session_id']) if registry else None
                if state and (not state.finished.is_set() or (state.process is not None and state.process.returncode is None)):
                    reason = 'recovery_required'
            observer = getattr(type(self.chat.ports.tasks), 'activity_observation', None)
            if observer is not None:
                try:
                    observed = self.chat.ports.tasks.activity_observation(task['task_id'])
                except Exception:
                    observed = {'recoveryRequired': True}
                if observed.get('recoveryRequired') or observed.get('pauseRequested'):
                    reason = reason or 'recovery_required'
                if observed.get('status', task['status']) not in TERMINAL:
                    reason = reason or 'active_runs'
            if reason:
                # Child executions are associated with their originating run.
                run_id = by_task.get(task['task_id']) or by_profile.get(task['profile_id'])
                blockers.update([run_id] if run_id else ids)
                reasons.add(reason)
        native = tx.connection.execute('SELECT binding_key FROM native_sources WHERE conversation_id=?', (conversation,)).fetchone()
        if native and tx.connection.execute('SELECT 1 FROM native_writers WHERE binding_key=?', (native[0],)).fetchone():
            blockers.update(ids)
            reasons.add('recovery_required')
        # Metadata/control grants have no new LocalRun. They still hold the
        # same admission boundary until their structured result is terminal.
        deliveries = tx.connection.execute(
            "SELECT run_id,state FROM remote2_delivery WHERE local_id=? AND state NOT IN ('completed','failed','rejected')",
            (conversation,),
        ).fetchall()
        for delivery in deliveries:
            blockers.update([delivery['run_id']] if delivery['run_id'] else ids)
            reasons.add('cancellation_unconfirmed' if delivery['state'] == 'unconfirmed' else 'active_runs')
        for inbox in tx.connection.execute("SELECT run_id FROM remote_inbox WHERE status IN ('admitted','executing')"):
            if inbox[0] in ids:
                blockers.add(inbox[0]); reasons.add('active_runs')
        for outbox in tx.connection.execute('SELECT frame_json FROM remote_outbox'):
            frame = json.loads(outbox[0])
            if frame.get('type') == 'approval.state_changed' and frame.get('conversationId') == conversation:
                # Existing wire revisions deliberately forbid redacting
                # approval/control facts. Never claim erasure while their
                # immutable targetSummary body remains pending transport ACK.
                ref = frame.get('payload', {}).get('resultRef', {})
                blockers.update([ref['runId']] if ref.get('runId') else ids)
                reasons.add('cancellation_unconfirmed')
        if reasons:
            reason = next(r for r in ('cancellation_unconfirmed', 'recovery_required', 'active_runs') if r in reasons)
            ordered = sorted(blockers)
            raise HubError('CONFLICT', '对话仍有执行或恢复事项，不能删除', detail={
                'reason': reason, 'blockingRunIds': ordered[:100],
                'hasMoreBlockingRuns': len(ordered) > 100,
            })

    def _registry(self, agent):
        directory = getattr(self.chat.ports.tasks, 'directory', None)
        if directory is None:
            return None
        try:
            return getattr(directory.adapter_for(agent), 'registry', None)
        except Exception:
            return None

    def _remote_intent(self, tx, conversation):
        """Emit a durable deletion even while offline; ACK alone confirms erasure."""
        worker = self.worker
        # Sync version rows survive ACK pruning, so they are historical proof.
        versions = tx.connection.execute("SELECT DISTINCT store_id FROM remote_sync_versions WHERE kind='conversation' AND resource_id=?", (conversation,)).fetchall()
        remote = tx.connection.execute('SELECT store_id FROM remote_conversations WHERE conversation_id=?', (conversation,)).fetchone()
        pending = []
        for row in tx.connection.execute('SELECT * FROM remote_outbox'):
            frame = json.loads(row['frame_json'])
            if frame.get('conversationId') == conversation or frame.get('payload', {}).get('conversationId') == conversation:
                pending.append((dict(row), frame))
        stores = {r[0] for r in versions} | ({remote[0]} if remote else set()) | {r['store_id'] for r, _ in pending}
        if not stores:
            return 'not_required', None, None
        if worker is None:
            return 'unconfirmed', None, None
        identity = worker.repo.get('identity', tx)
        link = worker.repo.get('link', tx)['view']
        if stores != {identity['store']} or not link.get('workerId') or identity.get('wireRevision', 1) < 2 or link.get('state') not in {'paired', 'frozen'}:
            return 'unconfirmed', None, None
        deletion = worker.repo.emit(tx, 'sync.conversation.deleted',
            syncGeneration=worker.sync.settings().sync_generation, conversationId=conversation, deletedAt=now())
        from runtime.remote.wire import encode
        content = {'sync.conversation.upserted', 'sync.message.segment', 'sync.run.state', 'message.appended'}
        slots = []
        for row, frame in pending:
            if frame.get('type') not in content or row['store_id'] != identity['store']:
                continue
            slots.append({'seq': row['seq'], 'eventId': row['event_id'], 'eventSha256': row['digest'], 'originalType': frame['type']})
            tx.connection.execute("UPDATE remote_outbox SET frame_json='{}' WHERE store_id=? AND seq=?", (row['store_id'], row['seq']))
        for offset in range(0, len(slots), 100):
            proof = {'type': 'sync.content.redaction', 'wireRevision': deletion['wireRevision'],
                     'redactionId': uid('redaction'), 'deletionEventId': deletion['eventId'],
                     'deletionSeq': deletion['seq'], 'conversationId': conversation,
                     'slots': slots[offset:offset + 100],
                     **{k: deletion[k] for k in ('workerId', 'workerStoreId', 'workerEpoch', 'syncGeneration')}}
            tx.connection.execute('INSERT INTO remote_sync_redactions VALUES(?,?,?,?)',
                                  (identity['store'], deletion['seq'], proof['redactionId'], encode(proof)))
        return 'pending', identity['store'], deletion['seq']

    async def delete(self, conversation, expected_version, key):
        if type(expected_version) is not int or not 1 <= expected_version <= 9007199254740991:
            raise HubError('VALIDATION_FAILED', 'expectedVersion必须为正安全整数')
        if not isinstance(key, str) or not key or len(key) > 200:
            raise HubError('VALIDATION_FAILED', '必须提供不超过200字符的Idempotency-Key')
        async with self.chat._conversation_lock(conversation):
            with self.db.transaction() as tx:
                old = self._row(conversation, tx.connection)
                if old:
                    if old['request_key_hash'] != request_hash(key):
                        if old['state'] != 'completed':
                            raise HubError('CONFLICT', '对话正在删除', detail={'reason': 'deleting'})
                        raise HubError('NOT_FOUND', '对话不存在')
                    if old['expected_version'] != expected_version:
                        raise HubError('IDEMPOTENCY_MISMATCH', '相同删除标识不能用于不同版本')
                else:
                    row = self.chat.repository._conversation_row(tx.connection, conversation)
                    if row is None:
                        raise HubError('NOT_FOUND', '对话不存在')
                    version = self.chat.repository._conversation_view(*row).version
                    if version != expected_version:
                        raise HubError('CONFLICT', '对话已更新，请刷新后重试',
                                       detail={'reason': 'version_mismatch', 'currentVersion': version})
                    runs = [dict(r) for r in tx.connection.execute('SELECT * FROM local_runs WHERE conversation_id=?', (conversation,))]
                    self._blockers(tx, conversation, runs, self._tasks(tx.connection, runs))
                    status, store, seq = self._remote_intent(tx, conversation)
                    tx.connection.execute('INSERT INTO local_conversation_deletions VALUES(?,?,?,?,?,?,?,?)',
                        (conversation, request_hash(key), expected_version, now(), 'cleaning', status, store, seq))
                    tx.connection.execute('DELETE FROM remote_sync_items WHERE conversation_id=?', (conversation,))
                    tx.connection.execute('DELETE FROM remote_sync_changes WHERE conversation_id=?', (conversation,))
                    if self.worker:
                        self.worker.repo.seal(tx)
            if not old or old['state'] != 'completed':
                await self._finish(conversation)
            return self.receipt(conversation)

    async def _finish(self, conversation):
        try:
            attachments = getattr(self.chat, 'attachments', None)
            if attachments:
                await attachments.library.quiesce_conversation(conversation)
                with self.db.transaction() as tx:
                    self._retain_shared_inputs(tx, conversation, attachments.library)
                    if self.worker:
                        self.worker.repo.seal(tx)
                await attachments.library.erase_conversation(conversation)
            with self.db.transaction() as tx:
                self._erase_rows(tx, conversation)
                tx.connection.execute("UPDATE local_conversation_deletions SET state='completed' WHERE conversation_id=?", (conversation,))
                if self.worker:
                    self.worker.repo.seal(tx)
        except Exception as error:
            raise HubError('INTERNAL', '对话清理未完成，可使用相同请求标识重试') from error

    def _retain_shared_inputs(self, tx, conversation, library):
        """Transfer referenced bytes before erasing this conversation's files.

        Copy+fsync precedes the ownership transaction. On interruption either
        the old owner still has its original bytes, or the retained owner has a
        durable copy; retry and orphan maintenance are safe in both cases.
        """
        db = tx.connection
        _, _, exclusive = self._execution_scope(db, conversation)
        owners = {}
        for row in db.execute(
            'SELECT r.task_id,r.conversation_id,r.message_id FROM local_runs r '
            'WHERE r.conversation_id<>? AND r.task_id IS NOT NULL '
            'AND NOT EXISTS(SELECT 1 FROM local_conversation_deletions d WHERE d.conversation_id=r.conversation_id) '
            'ORDER BY r.conversation_id,r.message_id', (conversation,)):
            owners.setdefault(row['task_id'], dict(row))
        specs = {}
        needed = {}
        for row in db.execute("SELECT key,value_json FROM hub_state WHERE key LIKE 'task_spec:%'").fetchall():
            task = row['key'][len('task_spec:'):]
            if task in exclusive:
                continue
            # An independently retained Task also owns its inputs even without
            # a LocalRun. Its private storage bucket is not a conversation.
            owner = owners.setdefault(task, {'conversation_id': 'retained-task-' + task, 'message_id': None})
            spec = json.loads(row['value_json']); specs[task] = spec
            for value in spec.get('inputAttachments', []):
                identifier = value.get('attachment', {}).get('attachmentId')
                if identifier:
                    needed.setdefault(identifier, owner)
        for row in db.execute('SELECT * FROM local_attachments WHERE conversation_id=?', (conversation,)).fetchall():
            identifier = row['attachment_id']
            owner = needed.get(identifier)
            if not owner:
                continue
            new_key = row['file_key']
            new_path = None
            if row['file_key']:
                old_path = library.path(row)
                new_key = uuid.uuid4().hex + old_path.suffix
                new_path = library.directory(owner['conversation_id']) / new_key
                with old_path.open('rb') as source, new_path.open('xb') as destination:
                    shutil.copyfileobj(source, destination, 65536)
                    destination.flush()
                    os.fsync(destination.fileno())
            db.execute("UPDATE local_attachments SET conversation_id=?,file_key=?,sync_json='{}' WHERE attachment_id=?",
                       (owner['conversation_id'], new_key, identifier))
            db.execute('DELETE FROM attachment_sync_jobs WHERE attachment_id=?', (identifier,))
            db.execute('DELETE FROM local_attachment_messages WHERE attachment_id=? AND message_id IN '
                       '(SELECT message_id FROM local_messages WHERE conversation_id=?)', (identifier, conversation))
            if owner['message_id']:
                ordinal = db.execute('SELECT COALESCE(MAX(ordinal),-1)+1 FROM local_attachment_messages WHERE message_id=?',
                                     (owner['message_id'],)).fetchone()[0]
                db.execute('INSERT OR IGNORE INTO local_attachment_messages VALUES(?,?,?,NULL)',
                           (owner['message_id'], identifier, ordinal))
            for task, spec in specs.items():
                changed = False
                for value in spec.get('inputAttachments', []):
                    if value.get('attachment', {}).get('attachmentId') == identifier:
                        if new_path:
                            value['localPath'] = str(new_path)
                        if 'sourceMessageId' in value and owner['message_id']:
                            value['sourceMessageId'] = owner['message_id']
                        changed = True
                if changed:
                    db.execute('UPDATE hub_state SET value_json=? WHERE key=?', (json.dumps(spec), 'task_spec:' + task))
                    from protocol.generated.python import AgentInputAttachment
                    for session in db.execute('SELECT session_id,agent_instance_id FROM sessions WHERE task_id=?', (task,)):
                        registry = self._registry(session['agent_instance_id'])
                        state = registry.get(session['session_id']) if registry else None
                        if state:
                            state.spec = state.spec.model_copy(update={'input_attachments': tuple(
                                AgentInputAttachment.model_validate(value) for value in spec.get('inputAttachments', []))})

    def _erase_rows(self, tx, conversation):
        db = tx.connection
        runs, tasks, task_ids = self._execution_scope(db, conversation)
        identifiers = {conversation} | {r['run_id'] for r in runs} | {r[0] for r in db.execute('SELECT message_id FROM local_messages WHERE conversation_id=?', (conversation,))} | task_ids
        for task in task_ids:
            for table, column in (('sessions', 'session_id'), ('task_nodes', 'node_id'),
                                  ('approvals', 'approval_id'), ('task_checkpoints', 'checkpoint_id'),
                                  ('worktrees', 'worktree_id'), ('artifacts', 'artifact_id')):
                identifiers.update(row[0] for row in db.execute(f'SELECT {column} FROM {table} WHERE task_id=?', (task,)))
        for action in db.execute("SELECT value_json FROM hub_state WHERE key LIKE 'task_action:%'"):
            value = json.loads(action[0])
            if value.get('taskId') in task_ids and value.get('actionId'):
                identifiers.add(value['actionId'])
        native_rows = db.execute('SELECT * FROM native_sources WHERE conversation_id=?', (conversation,)).fetchall()
        for native in native_rows:
            identifiers.update({native['native_id'], native['session_id']})
            db.execute('INSERT OR IGNORE INTO local_deleted_native_bindings VALUES(?)', (native['binding_key'],))
            db.execute('DELETE FROM native_writers WHERE binding_key=?', (native['binding_key'],))
            db.execute('DELETE FROM sessions WHERE session_id=?', (native['session_id'],))
            # One rebuildable history cache entry per source; remove that entry
            # without ever unlinking the vendor file it describes.
            path = json.loads(native['source_json']).get('path')
            if path:
                for cached in db.execute('SELECT cache_key,metadata_json FROM native_history_indexes').fetchall():
                    if (json.loads(cached[1]).get('source') or {}).get('path') == path:
                        db.execute('DELETE FROM native_history_indexes WHERE cache_key=?', (cached[0],))
                native_service = getattr(self.chat, 'native', None)
                if native_service:
                    for index in getattr(native_service, 'indexes', {}).values():
                        index.entries.pop(index.key(path), None)
        identifiers.discard(None)
        attachment_ids = {r[0] for r in db.execute('SELECT attachment_id FROM local_attachments WHERE conversation_id=?', (conversation,))}
        identifiers |= attachment_ids
        for attachment in attachment_ids:
            db.execute('DELETE FROM local_attachment_messages WHERE attachment_id=?', (attachment,))
            db.execute('DELETE FROM attachment_sync_jobs WHERE attachment_id=?', (attachment,))
        for run in runs:
            for table in ('attachment_preparations', 'remote2_gates'):
                db.execute(f'DELETE FROM {table} WHERE run_id=?', (run['run_id'],))
            db.execute('DELETE FROM hub_state WHERE key=?', ('local-run-session-mode:' + run['run_id'],))
        for task_id in task_ids:
            db.execute("INSERT OR IGNORE INTO local_deleted_execution_resources VALUES(?,'task')", (task_id,))
            for session in db.execute('SELECT session_id,agent_instance_id FROM sessions WHERE task_id=?', (task_id,)):
                registry = self._registry(session['agent_instance_id'])
                if registry:
                    registry.forget_finished(session['session_id'])
            for table in ('task_nodes', 'sessions', 'approvals', 'task_checkpoints', 'worktrees', 'artifacts'):
                db.execute(f'DELETE FROM {table} WHERE task_id=?', (task_id,))
            db.execute('DELETE FROM tasks WHERE task_id=?', (task_id,))
            db.execute('DELETE FROM hub_state WHERE key=?', ('task_spec:' + task_id,))
        for task in tasks:
            profile = task['profile_id']
            if profile and profile.startswith('local-profile:') and not db.execute('SELECT 1 FROM tasks WHERE profile_id=?', (profile,)).fetchone():
                db.execute('DELETE FROM role_bindings WHERE profile_id=?', (profile,))
                db.execute('DELETE FROM team_profiles WHERE profile_id=?', (profile,))
                db.execute("INSERT OR IGNORE INTO local_deleted_execution_resources VALUES(?,'profile')", (profile,))
                identifiers.add(profile)
        for run in runs:
            profile = 'local-profile:' + run['run_id']
            if not db.execute('SELECT 1 FROM tasks WHERE profile_id=?', (profile,)).fetchone():
                db.execute("INSERT OR IGNORE INTO local_deleted_execution_resources VALUES(?,'profile')", (profile,))
                db.execute('DELETE FROM role_bindings WHERE profile_id=?', (profile,))
                db.execute('DELETE FROM team_profiles WHERE profile_id=?', (profile,))
                identifiers.add(profile)
        # Remove private copies, including source Inbox bodies, not just UI rows.
        for table, key_column, payload_column in (
            ('hub_state', 'key', 'value_json'), ('local_commands', 'rowid', 'response_json'),
            ('remote_state', 'key', 'value_json'),
            ('idempotency_records', 'rowid', 'response_json'), ('events', 'seq', 'envelope_json'),
            ('native_commands', 'rowid', 'frame_json'), ('native_history_indexes', 'cache_key', 'metadata_json'),
        ):
            for row in db.execute(f'SELECT {key_column},{payload_column} FROM {table}').fetchall():
                if table == 'remote_state' and row[0] in {'identity', 'link', 'sync-work'}:
                    continue  # Binding identity and sync watermarks are shared, never conversation bodies.
                if _contains(json.loads(row[1]), identifiers):
                    if table == 'events':
                        # Keep event identities/watermarks valid for the shared Outbox.
                        body = json.loads(row[1]); body['payload'] = {}
                        db.execute("UPDATE events SET payload_json='{}',envelope_json=? WHERE seq=?", (json.dumps(body), row[0]))
                    else:
                        db.execute(f'DELETE FROM {table} WHERE {key_column}=?', (row[0],))
        for table, column in (('remote2_delivery', 'local_id'), ('remote_inbox', None)):
            for row in db.execute(f'SELECT rowid,* FROM {table}').fetchall():
                if (column and row[column] == conversation) or row['run_id'] in identifiers or _contains(json.loads(row['command_json'] or '{}'), identifiers):
                    if table == 'remote2_delivery':
                        db.execute('UPDATE remote2_delivery SET command_json=NULL,grant_json=NULL,execution_json=NULL,result_json=NULL,received_json=NULL WHERE rowid=?', (row['rowid'],))
                    else:
                        db.execute("UPDATE remote_inbox SET command_json='{}',receipt_json=NULL,observation_json=NULL WHERE rowid=?", (row['rowid'],))
        for table in ('local_attachments', 'attachment_upload_keys', 'native_sources', 'remote_conversations', 'local_messages', 'local_runs', 'remote_sync_items', 'remote_sync_changes'):
            db.execute(f'DELETE FROM {table} WHERE conversation_id=?', (conversation,))
        for identifier in identifiers:
            db.execute('DELETE FROM remote_sync_versions WHERE resource_id=?', (identifier,))
            db.execute('DELETE FROM remote_projections WHERE key IN (?,?,?,?)',
                       (identifier, 'message:' + identifier, 'run:' + identifier, 'approval:' + identifier))
        db.execute('DELETE FROM local_conversations WHERE conversation_id=?', (conversation,))
        db.execute('DELETE FROM remote_sync_changes WHERE conversation_id=?', (conversation,))

    def receipt(self, conversation):
        row = self._row(conversation)
        status = row['remote_status']
        if status == 'pending' and self.worker:
            identity = self.worker.repo.get('identity')
            if identity['store'] != row['remote_store']:
                status = 'unconfirmed'
            elif (identity['ack'] or 0) >= row['remote_seq']:
                status = 'confirmed'
            if status != row['remote_status']:
                with self.db.transaction() as tx:
                    tx.connection.execute('UPDATE local_conversation_deletions SET remote_status=? WHERE conversation_id=?', (status, conversation))
        return LocalConversationDeletionView(conversationId=conversation, deletedAt=row['deleted_at'],
                                             localDeleted=True, remoteCleanup=status)

    async def recover(self):
        with self.db.locked_connection() as db:
            conversations = [r[0] for r in db.execute("SELECT conversation_id FROM local_conversation_deletions WHERE state<>'completed'")]
        for conversation in conversations:
            async with self.chat._conversation_lock(conversation):
                try:
                    await self._finish(conversation)
                except HubError:
                    # A locked local file retains its durable fence; unrelated
                    # conversations and explicit retry must remain available.
                    logging.getLogger(__name__).warning('conversation cleanup pending')
