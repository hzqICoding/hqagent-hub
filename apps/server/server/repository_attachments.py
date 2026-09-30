"""All attachment SQL stays inside the repository; owner is mandatory."""
import json
from .common import canonical

class AttachmentRepository:

    def attachment_deletion_owners(self):
        return [r[0] for r in self.db.execute("SELECT DISTINCT owner FROM records WHERE kind='attachment-deletion'")]

    def scrub_attachment_replays(self, owner, identifier):
        """Apply a retained deletion journal before serving a restored snapshot."""

        def scrub(value):
            if isinstance(value, list):
                return [scrub(v) for v in value if not (isinstance(v,
                    dict) and (v.get('attachmentId') == identifier or v.get('originAttachmentId') == identifier))]
            if isinstance(value, dict):
                return {k: scrub(v) for k, v in value.items()}
            return value
        retired = set()
        for row in self.db.execute("SELECT kind,id,body,worker,store,parent FROM records WHERE owner=? AND kind IN ('message','command','outbox','attachment-binding','attachment-local')",
            (owner,
            )).fetchall():
            kind, key, raw, worker, store, parent = row
            value = json.loads(raw)
            clean = scrub(value)
            if kind in {'attachment-binding', 'attachment-local'} and value['attachmentId'] == identifier:
                self.remove_record(owner, kind, key)
                continue
            if clean == value:
                continue
            if kind == 'outbox':
                self.remove_record(owner, kind, key)
                continue
            if kind == 'command':
                clean['_deleted'] = True
                clean['deliveryState'] = 'reconciliation_required'
                retired.add(key)
            self.put(owner, kind, key, clean, worker=worker, store=store, parent=parent)
        for row in self.db.execute("SELECT id,body FROM records WHERE owner=? AND kind='idempotency'",
            (owner,
            )).fetchall():
            value = json.loads(row[1])
            if value.get('result', {}).get('commandId') in retired or scrub(value) != value:
                self.put(owner, 'idempotency', row[0], dict(content=value['content'], _retired=True))
        for row in self.db.execute('SELECT ordinal,body FROM browser_outbox WHERE owner=?',
            (owner,
            )).fetchall():
            value = json.loads(row[1])
            clean = scrub(value)
            if clean != value:
                self.db.execute('DELETE FROM browser_outbox WHERE owner=? AND ordinal=?', (owner, row[0]))
        for row in self.db.execute('SELECT worker,store,event_id,body FROM sync_log WHERE owner=? AND body IS NOT NULL',
            (owner,
            )).fetchall():
            if scrub(json.loads(row[3])) != json.loads(row[3]):
                self.db.execute('UPDATE sync_log SET body=NULL,evidence=NULL,redacted=1 WHERE owner=? AND worker=? AND store=? AND event_id=?',
                    (owner,
                    *row[:3]))

    def attachment_usage(self, owner):
        used = self.db.execute("SELECT COALESCE(SUM(json_extract(body,'$.sizeBytes')),0) FROM records WHERE owner=? AND kind='attachment' AND json_extract(body,'$._blob') IS NOT NULL",
            (owner,
            )).fetchone()[0]
        reserved = self.db.execute("SELECT COALESCE(SUM(json_extract(body,'$.reserved')),0) FROM records WHERE owner=? AND kind='upload'",
            (owner,
            )).fetchone()[0]
        return (used, reserved)

    def blob_referenced(self, hash_):
        return self.db.execute("SELECT 1 FROM records WHERE kind='blob-ref' AND json_extract(body,'$.hash')=? LIMIT 1",
            (hash_,
            )).fetchone() is not None

    def attachment_owners(self):
        return [r[0] for r in self.db.execute("SELECT DISTINCT owner FROM records WHERE kind IN ('attachment','upload','blob-ref')")]

    def erase_attachment_intents(self, owner, ids):
        for row in self.db.execute("SELECT id,body FROM records WHERE owner=? AND kind='upload-intent'",
            (owner,
            )).fetchall():
            value = json.loads(row[1])
            if value['attachmentId'] in ids:
                self.put(owner, 'upload-retired', row[0], dict(content=value['content']))
                self.remove_record(owner, 'upload-intent', row[0])
