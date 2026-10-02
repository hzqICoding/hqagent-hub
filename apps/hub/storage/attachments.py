"""Local attachment metadata, ordered message bindings and preparation latch."""
import json
from datetime import datetime, timedelta, timezone
from core.errors import HubError
from protocol.generated.python import LocalAttachmentView, MessageAttachmentView
from storage.local_chat import now, uid

class AttachmentRepository:

    def __init__(self, database):
        self.db = database

    def row(self, identifier, tx=None, *, available=True):
        with self.db.locked_connection() as db:
            row = (tx.connection if tx else db).execute('SELECT * FROM local_attachments WHERE attachment_id=?', (identifier,)).fetchone()
        if row is None or (available and (row['state'] in {'deleted', 'expired'} or (row['state'] == 'uploaded' and row['expires_at'] <= now()))):
            raise HubError('NOT_FOUND', '附件不存在或已清理')
        return dict(row)

    def view(self, identifier):
        row = self.row(identifier)
        sync = json.loads(row['sync_json'])
        return LocalAttachmentView(attachment=json.loads(row['manifest_json']), conversationId=row['conversation_id'], state=row['state'], createdAt=row['created_at'], **{'expiresAt': row['expires_at']} if row['expires_at'] else {}, syncStatus=sync.get('status', 'not_synced'), **{'syncError': sync['error']} if sync.get('error') else {})

    def insert(self, tx, conversation, manifest, file_key, *, origin=None):
        stamp = now()
        expires = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace('+00:00', 'Z')
        tx.connection.execute('INSERT INTO local_attachments VALUES(?,?,?,?,?,?,?,?,?)', (manifest['attachmentId'], conversation, json.dumps(manifest), file_key, 'uploaded', stamp, expires, origin, '{}'))

    def bind(self, tx, conversation, message_id, run_id, identifiers, *, source=None):
        if len(identifiers) > 5:
            raise HubError('ATTACHMENT_COUNT_EXCEEDED', '每条消息附件不能超过5个')
        if len(set(identifiers)) != len(identifiers):
            raise HubError('VALIDATION_FAILED', '附件不能重复')
        for ordinal, identifier in enumerate(identifiers):
            row = self.row(identifier, tx)
            if row['conversation_id'] != conversation:
                raise HubError('NOT_FOUND', '附件不属于本机对话')
            tx.connection.execute('INSERT INTO local_attachment_messages VALUES(?,?,?,?)', (message_id, identifier, ordinal, (source or {}).get('commandId')))
            tx.connection.execute("UPDATE local_attachments SET state='attached',expires_at=NULL WHERE attachment_id=?", (identifier,))
        if identifiers:
            tx.connection.execute("INSERT INTO attachment_preparations VALUES(?,'pending',?,NULL,NULL)", (run_id, json.dumps(source or {})))

    def message_rows(self, message_id):
        with self.db.locked_connection() as db:
            return [dict(r) for r in db.execute('SELECT a.*,m.source_command_id FROM local_attachments a JOIN local_attachment_messages m ON a.attachment_id=m.attachment_id WHERE m.message_id=? ORDER BY m.ordinal', (message_id,))]

    def message_views(self, message_id):
        return [json.loads(row['manifest_json']) for row in self.message_rows(message_id)]

    def source(self, message_id, tx):
        row = tx.connection.execute('SELECT p.source_json FROM attachment_preparations p JOIN local_runs r ON r.run_id=p.run_id WHERE r.message_id=?', (message_id,)).fetchone()
        return json.loads(row[0]) if row else {}

    def preparation(self, run_id, tx=None):
        with self.db.locked_connection() as db:
            row = (tx.connection if tx else db).execute('SELECT * FROM attachment_preparations WHERE run_id=?', (run_id,)).fetchone()
        return dict(row) if row else None

    def transition(self, tx, run_id, state, *, code=None, evidence=None):
        tx.connection.execute('UPDATE attachment_preparations SET state=?,error_code=?,evidence_json=? WHERE run_id=?', (state, code, json.dumps(evidence) if evidence else None, run_id))

    def touch_message(self, tx, message_id):
        tx.connection.execute("INSERT INTO remote_sync_changes(kind,resource_id,conversation_id) SELECT 'message',message_id,conversation_id FROM local_messages WHERE message_id=?", (message_id,))
