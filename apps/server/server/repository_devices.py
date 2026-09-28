"""Owner-scoped administration queries and permanent device erasure."""
import json

from .common import canonical


class DeviceRepository:
    def ordered_records(self, owner, kind, after=0):
        for row in self.db.execute('SELECT ordinal,body FROM records WHERE owner=? AND kind=? AND ordinal>? ORDER BY ordinal', (owner, kind, after)):
            yield row[0], json.loads(row[1])

    def ungranted_windows(self, owner, worker):
        return [json.loads(row[0]) for row in self.db.execute("""SELECT body FROM records
            WHERE owner=? AND worker=? AND kind='command' AND command_status='queued'
            AND json_extract(body,'$._frame.wireRevision')=2
            AND COALESCE(json_extract(body,'$._granted'),0)=0""", (owner, worker))]

    def delete_device_content(self, owner, worker, deleted):
        device = self.get(owner, 'device', worker)
        # revoke/sync_erase has already retired content-linked replay intents.
        for row in self.db.execute("SELECT id,body FROM records WHERE owner=? AND kind='idempotency'", (owner,)).fetchall():
            saved = json.loads(row[1]); result = saved.get('result', {})
            if result.get('workerId', result.get('targetWorkerId')) == worker or result.get('pairRequestId') == device.get('_challenge'):
                self.put(owner, 'idempotency', row[0], dict(content=saved['content'], _retired=True))
        for row in self.db.execute("SELECT id,body FROM records WHERE owner=? AND worker=? AND kind='command'", (owner, worker)).fetchall():
            command = json.loads(row[1])
            # Preserve uncertainty/grant facts, never a replayable display object.
            safe = {k: command[k] for k in ('commandId', '_digest', '_granted', '_dispatch', 'status', 'deliveryState') if k in command}
            self.put(owner, 'command-tombstone', row[0], safe, worker=worker)
        self.db.execute("DELETE FROM records WHERE owner=? AND worker=? AND kind NOT IN ('command-tombstone','event-position')", (owner, worker))
        self.put(owner, 'device', worker, dict(workerId=worker, status='revoked', _deleted=True, deletedAt=deleted), worker=worker)
        self.db.execute('DELETE FROM sync_segments WHERE owner=? AND worker=?', (owner, worker))
        self.db.execute('UPDATE sync_log SET body=NULL,evidence=NULL,redacted=1 WHERE owner=? AND worker=?', (owner, worker))
        self.db.execute('UPDATE sync_ids SET deleted=1 WHERE owner=? AND worker=?', (owner, worker))
        # Erase even store-less catalog/reset events. Old cursors cannot replay them.
        for row in self.db.execute('SELECT ordinal,body FROM browser_outbox WHERE owner=?', (owner,)).fetchall():
            event = json.loads(row[1]); payload = event.get('payload', {})
            if event.get('workerId', payload.get('workerId', payload.get('targetWorkerId'))) == worker:
                self.db.execute('DELETE FROM browser_outbox WHERE owner=? AND ordinal=?', (owner, row[0]))
        for row in self.db.execute('SELECT key,body FROM auth WHERE owner=?', (owner,)).fetchall():
            value = json.loads(row[1])
            if row[0].startswith('challenge:') and value.get('workerId') == worker:
                safe = {k: value[k] for k in ('id','workerId','owner','verifier','expires')}
                safe['status'] = 'revoked'
                self.auth_put(row[0], safe, owner)
            # credential:<HMAC> remains as a deny record: the same device secret
            # cannot create a new pairing or authenticate the deleted worker.
