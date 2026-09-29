"""R1.5 replica/identity/coverage storage. SQL remains at the repository boundary."""
import json

from .common import canonical, digest, require, uid

SYNC_MIGRATION = """
ALTER TABLE records ADD COLUMN message_sequence INTEGER;
UPDATE records SET message_sequence=COALESCE(json_extract(body,'$.messageSequence'),ordinal) WHERE kind='message';
CREATE INDEX record_message_order ON records(owner,kind,parent,message_sequence);
CREATE TABLE sync_ids (
 owner TEXT NOT NULL, worker TEXT NOT NULL, store TEXT NOT NULL, kind TEXT NOT NULL,
 local_id TEXT NOT NULL, public_id TEXT NOT NULL, conversation TEXT NOT NULL,
 deleted INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(owner,worker,store,kind,local_id), UNIQUE(owner,kind,public_id));
CREATE INDEX sync_id_conversation ON sync_ids(owner,worker,store,conversation);
CREATE TABLE sync_log (
 owner TEXT NOT NULL, worker TEXT NOT NULL, store TEXT NOT NULL,
 event_id TEXT NOT NULL, first_seq INTEGER NOT NULL, last_seq INTEGER NOT NULL,
 event_hash TEXT NOT NULL, event_type TEXT NOT NULL, generation INTEGER,
 conversation TEXT, epoch TEXT NOT NULL, body TEXT, evidence TEXT, bytes INTEGER NOT NULL,
 snapshot_id TEXT, part_index INTEGER,
 applied INTEGER NOT NULL DEFAULT 0, redacted INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(owner,worker,store,event_id), UNIQUE(owner,worker,store,last_seq));
CREATE INDEX sync_log_continuity ON sync_log(owner,worker,store,first_seq);
CREATE INDEX sync_log_snapshot ON sync_log(owner,worker,store,snapshot_id,part_index);
CREATE TABLE sync_segments (
 owner TEXT NOT NULL, worker TEXT NOT NULL, store TEXT NOT NULL, generation INTEGER NOT NULL,
 conversation TEXT NOT NULL, message TEXT NOT NULL, revision INTEGER NOT NULL,
 part INTEGER NOT NULL, text TEXT NOT NULL, bytes INTEGER NOT NULL,
 PRIMARY KEY(owner,worker,store,generation,message,revision,part));
CREATE INDEX sync_segment_conversation ON sync_segments(owner,worker,store,conversation);
"""


class SyncRepository:
    def sync_unapplied(self, owner, worker, store):
        return self.db.execute('SELECT 1 FROM sync_log WHERE owner=? AND worker=? AND store=? AND applied=0 LIMIT 1', (owner, worker, store)).fetchone() is not None

    def legacy_pending(self, owner, worker, store):
        return self.db.execute('SELECT 1 FROM inbox WHERE owner=? AND worker=? AND store=? AND applied=0 LIMIT 1', (owner, worker, store)).fetchone() is not None

    def sync_stores(self, owner, worker):
        return [r[0] for r in self.db.execute("SELECT DISTINCT store FROM records WHERE owner=? AND worker=? AND store<>'' UNION SELECT store FROM sync_ids WHERE owner=? AND worker=?", (owner, worker, owner, worker))]

    def sync_message_high(self, owner, conversation):
        return self.db.execute("SELECT COALESCE(MAX(message_sequence),0) FROM records WHERE owner=? AND kind='message' AND parent=?", (owner, conversation)).fetchone()[0]

    def sync_message_page(self, owner, conversation, cut, before, limit):
        rows = self.db.execute("SELECT message_sequence,body FROM records WHERE owner=? AND kind='message' AND parent=? AND message_sequence<=? AND message_sequence<? ORDER BY message_sequence DESC LIMIT ?", (owner, conversation, cut, before, limit + 1))
        items = []; size = 0
        for row in rows:
            added = len(row[1].encode())
            if len(items) == limit or (items and size + added > 33554432):
                return items, True
            size += added
            items.append((row[0], json.loads(row[1])))
        return items, False

    def sync_message_collision(self, owner, conversation, seq, message):
        return self.db.execute("SELECT 1 FROM records WHERE owner=? AND kind='message' AND parent=? AND message_sequence=? AND id<>?", (owner, conversation, seq, message)).fetchone() is not None

    def retire_legacy_messages(self, owner, conversation):
        for row in self.db.execute("SELECT id,body FROM records WHERE owner=? AND kind='message' AND parent=?", (owner, conversation)).fetchall():
            if '_localId' not in json.loads(row[1]):
                self.remove_record(owner, 'message', row[0])

    def sync_batch_check(self, owner, event):
        count = event['batchEventCount']
        rows = self.db.execute('SELECT first_seq,last_seq,event_type,bytes FROM sync_log WHERE owner=? AND worker=? AND store=? AND last_seq<? ORDER BY last_seq DESC LIMIT ?', (owner, event['workerId'], event['workerStoreId'], event['seq'], count)).fetchall()
        marker = self.sync_entry(owner, event['workerId'], event['workerStoreId'], event_id=event['eventId'])
        require(len(rows) == count and sum(r[3] for r in rows) + marker['bytes'] <= 1048576, 'REMOTE_SYNC_CONFLICT')
        for offset, row in enumerate(rows, 1):
            require(row[0] == row[1] == event['seq'] - offset and row[2] in {'sync.conversation.upserted','sync.message.segment','sync.run.state','approval.state_changed','native.index.upserted'}, 'REMOTE_SYNC_CONFLICT')

    def sync_part_checked(self, owner, worker, store, generation, payload, quota):
        row = self.db.execute('SELECT text FROM sync_segments WHERE owner=? AND worker=? AND store=? AND generation=? AND message=? AND revision=? AND part=?',
                              (owner, worker, store, generation, payload['messageId'], payload['messageRevision'], payload['segmentIndex'])).fetchone()
        if not row:
            used = self.db.execute('SELECT COALESCE(SUM(bytes),0) FROM sync_segments WHERE owner=? AND worker=? AND store=? AND generation=? AND message=? AND revision=?', (owner, worker, store, generation, payload['messageId'], payload['messageRevision'])).fetchone()[0]
            require(used + len(payload['text'].encode()) <= payload['totalUtf8Bytes'], 'REMOTE_SYNC_CONFLICT')
            count, total = self.sync_part_usage(owner, worker, store)
            require(count < 16384 and total + len(payload['text'].encode()) <= quota, 'REMOTE_SYNC_RESOURCE_LIMIT')
        self.sync_part(owner, worker, store, generation, payload)
    def sync_id(self, owner, worker, store, kind, local, conversation, public=None):
        row = self.db.execute("SELECT public_id,conversation,deleted FROM sync_ids WHERE owner=? AND worker=? AND store=? AND kind=? AND local_id=?", (owner, worker, store, kind, local)).fetchone()
        if row:
            require(row[1] == conversation, "REMOTE_TARGET_MISMATCH")
            return row[0], bool(row[2])
        public = public or uid()
        self.db.execute("INSERT INTO sync_ids(owner,worker,store,kind,local_id,public_id,conversation) VALUES(?,?,?,?,?,?,?)", (owner, worker, store, kind, local, public, conversation))
        return public, False

    def sync_lookup(self, owner, worker, store, kind, local):
        row = self.db.execute("SELECT public_id,conversation,deleted FROM sync_ids WHERE owner=? AND worker=? AND store=? AND kind=? AND local_id=?", (owner, worker, store, kind, local)).fetchone()
        return dict(public=row[0], conversation=row[1], deleted=bool(row[2])) if row else None

    def sync_reverse(self, owner, kind, public):
        row = self.db.execute("SELECT worker,store,local_id,conversation,deleted FROM sync_ids WHERE owner=? AND kind=? AND public_id=?", (owner, kind, public)).fetchone()
        return dict(worker=row[0], store=row[1], local=row[2], conversation=row[3], deleted=bool(row[4])) if row else None

    def sync_entry(self, owner, worker, store, *, event_id=None, seq=None):
        column, value = ("event_id", event_id) if event_id is not None else ("last_seq", seq)
        row = self.db.execute(f"SELECT * FROM sync_log WHERE owner=? AND worker=? AND store=? AND {column}=?", (owner, worker, store, value)).fetchone()
        return dict(row) if row else None

    def sync_overlap(self, owner, worker, store, first, last):
        return self.db.execute("SELECT 1 FROM sync_log WHERE owner=? AND worker=? AND store=? AND first_seq<=? AND last_seq>=? LIMIT 1", (owner, worker, store, last, first)).fetchone() is not None

    def sync_log_put(self, owner, event, conversation=None, encoded_bytes=None):
        encoded = canonical(event)
        self.db.execute("""INSERT INTO sync_log(owner,worker,store,event_id,first_seq,last_seq,event_hash,event_type,generation,conversation,epoch,body,bytes,snapshot_id,part_index)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (owner, event['workerId'], event['workerStoreId'], event['eventId'], event.get('firstSeq', event['seq']), event['seq'], digest(event), event['type'], event.get('syncGeneration'), conversation, event['workerEpoch'], encoded, encoded_bytes if encoded_bytes is not None else len(encoded.encode()), event.get('snapshotId'), event.get('partIndex')))

    def sync_busy_part_exists(self, owner, event):
        return self.db.execute('SELECT 1 FROM sync_log WHERE owner=? AND worker=? AND store=? AND snapshot_id=? AND part_index=?', (owner, event['workerId'], event['workerStoreId'], event['snapshotId'], event['partIndex'])).fetchone() is not None

    def sync_snapshot_first(self, owner, worker, store, snapshot):
        return self.db.execute('SELECT MIN(first_seq) FROM sync_log WHERE owner=? AND worker=? AND store=? AND snapshot_id=?', (owner, worker, store, snapshot)).fetchone()[0]

    def sync_log_next(self, owner, worker, store, seq):
        row = self.db.execute("SELECT * FROM sync_log WHERE owner=? AND worker=? AND store=? AND first_seq=?", (owner, worker, store, seq)).fetchone()
        return dict(row) if row else None

    def sync_log_applied(self, owner, worker, store, event_id, forget=False):
        self.db.execute("UPDATE sync_log SET applied=1,body=CASE WHEN ? THEN NULL ELSE body END WHERE owner=? AND worker=? AND store=? AND event_id=?", (forget, owner, worker, store, event_id))

    def sync_pending_bytes(self, owner, worker, store):
        row = self.db.execute("SELECT COUNT(*),COALESCE(SUM(bytes),0) FROM sync_log WHERE owner=? AND worker=? AND store=? AND applied=0 AND redacted=0", (owner, worker, store)).fetchone()
        return row[0], row[1]

    def sync_cover(self, owner, worker, store, slot, generation, conversation):
        row = self.sync_entry(owner, worker, store, seq=slot['seq'])
        if row:
            require(row['event_id'] == slot['eventId'] and row['event_hash'] == slot['eventSha256'] and row['event_type'] == slot['originalType'], 'REMOTE_SYNC_CONFLICT')
            require(row['generation'] is None or row['generation'] <= generation, 'REMOTE_SYNC_CONFLICT')
            require(conversation is None or row['conversation'] == conversation, 'REMOTE_SYNC_CONFLICT')
            self.db.execute("UPDATE sync_log SET body=NULL,redacted=1 WHERE owner=? AND worker=? AND store=? AND event_id=?", (owner, worker, store, slot['eventId']))
        else:
            require(self.sync_entry(owner, worker, store, event_id=slot['eventId']) is None and not self.sync_overlap(owner, worker, store, slot['seq'], slot['seq']), 'REMOTE_SYNC_CONFLICT')
            self.db.execute("""INSERT INTO sync_log(owner,worker,store,event_id,first_seq,last_seq,event_hash,event_type,generation,conversation,epoch,bytes,redacted)
                VALUES(?,?,?,?,?,?,?,?,?,?,'',0,1)""", (owner, worker, store, slot['eventId'], slot['seq'], slot['seq'], slot['eventSha256'], slot['originalType'], generation, conversation))

    def sync_part(self, owner, worker, store, generation, payload):
        key = (owner, worker, store, generation, payload['messageId'], payload['messageRevision'], payload['segmentIndex'])
        row = self.db.execute("SELECT text FROM sync_segments WHERE owner=? AND worker=? AND store=? AND generation=? AND message=? AND revision=? AND part=?", key).fetchone()
        if row:
            require(row[0] == payload['text'], 'REMOTE_SYNC_CONFLICT')
            return
        self.db.execute("INSERT INTO sync_segments(owner,worker,store,generation,conversation,message,revision,part,text,bytes) VALUES(?,?,?,?,?,?,?,?,?,?)", (owner, worker, store, generation, payload['conversationId'], payload['messageId'], payload['messageRevision'], payload['segmentIndex'], payload['text'], len(payload['text'].encode())))

    def sync_parts(self, owner, worker, store, generation, message, revision):
        for row in self.db.execute("SELECT part,text,bytes FROM sync_segments WHERE owner=? AND worker=? AND store=? AND generation=? AND message=? AND revision=? ORDER BY part", (owner, worker, store, generation, message, revision)):
            yield row[0], row[1], row[2]

    def sync_parts_delete(self, owner, worker, store, message, through):
        self.db.execute("DELETE FROM sync_segments WHERE owner=? AND worker=? AND store=? AND message=? AND revision<=?", (owner, worker, store, message, through))

    def sync_part_usage(self, owner, worker, store):
        return self.db.execute("SELECT COUNT(*),COALESCE(SUM(bytes),0) FROM sync_segments WHERE owner=? AND worker=? AND store=?", (owner, worker, store)).fetchone()

    def sync_message_part_count(self, owner, worker, store, generation, message, revision):
        return self.db.execute('SELECT COUNT(*) FROM sync_segments WHERE owner=? AND worker=? AND store=? AND generation=? AND message=? AND revision=?', (owner, worker, store, generation, message, revision)).fetchone()[0]

    def remove_record(self, owner, kind, identifier):
        self.db.execute("DELETE FROM records WHERE owner=? AND kind=? AND id=?", (owner, kind, identifier))

    def sync_erase(self, owner, worker, store, conversation=None, permanent=False, through_generation=None):
        """Erase content, preserving only identity/hash/sequence/execution evidence."""
        ids = self.db.execute("SELECT kind,public_id FROM sync_ids WHERE owner=? AND worker=? AND store=?" + (" AND conversation=?" if conversation is not None else ""), (owner, worker, store, conversation) if conversation is not None else (owner, worker, store)).fetchall()
        public_conversations = {r[1] for r in ids if r[0] == 'conversation'}
        # Include pre-upgrade R1 public IDs, which have no sync_ids entry yet.
        for row in self.db.execute("SELECT id FROM records WHERE owner=? AND kind='conversation' AND worker=? AND store=?", (owner, worker, store)):
            if conversation is None or row[0] == conversation:
                public_conversations.add(row[0])
        for row in self.db.execute("SELECT kind,id,parent,body FROM records WHERE owner=? AND worker=? AND store=?", (owner, worker, store)).fetchall():
            kind, identifier, parent, raw = row
            data = json.loads(raw)
            related = conversation is None or parent in public_conversations or (kind == 'conversation' and identifier in public_conversations)
            if not related:
                continue
            if kind in {'conversation', 'message', 'run', 'run-ref', 'approval', 'segment-meta', 'sync-stage', 'create-reservation'} or (kind == 'catalog' and permanent and conversation is None):
                self.remove_record(owner, kind, identifier)
            elif kind in {'message-intent', 'approval-intent'}:
                data['_retired'] = True
                self.put(owner, kind, identifier, data, worker=worker, store=store, parent=parent)
            elif kind == 'outbox' and data['_frame']['type'] not in {'command.delivery_granted', 'conversation.skip'}:
                self.remove_record(owner, kind, identifier)
            elif kind == 'command':
                frame = data.get('_frame', {})
                data['_digest'] = data.get('_digest', digest(frame))
                data['_deleted'] = True
                data['_frame'] = {k: v for k, v in frame.items() if k != 'payload'}
                for field in ('error', 'controlResult'):
                    if field in data:
                        data[field] = dict(data[field])
                        if 'message' in data[field]: data[field]['message'] = data[field]['code']
                        if 'reason' in data[field]: data[field]['reason'] = 'Content removed'
                self.put(owner, kind, identifier, data, worker=worker, store=store, parent=parent)
        # Older caches can predate association columns; match their referenced IDs too.
        for row in self.db.execute("SELECT id,body FROM records WHERE owner=? AND kind='idempotency'", (owner,)).fetchall():
            result = json.loads(row[1]).get('result', {})
            if result.get('conversationId') in public_conversations:
                saved = json.loads(row[1])
                self.put(owner, 'idempotency', row[0], dict(content=saved['content'], _retired=True))
        for row in self.db.execute("SELECT ordinal,body FROM browser_outbox WHERE owner=?", (owner,)).fetchall():
            body = json.loads(row[1]); payload = body.get('payload', {})
            scoped_worker = body.get('workerId', payload.get('workerId', payload.get('targetWorkerId')))
            scoped_store = body.get('workerStoreId', payload.get('workerStoreId'))
            if body.get('conversationId') in public_conversations or payload.get('conversationId') in public_conversations or (conversation is None and scoped_worker == worker and scoped_store == store):
                self.db.execute("DELETE FROM browser_outbox WHERE owner=? AND ordinal=?", (owner, row[0]))
        args = (owner, worker, store)
        suffix = ''
        if conversation is not None:
            suffix = ' AND conversation=?'; args += (conversation,)
        generation_suffix = ' AND generation<=?' if through_generation is not None else ''
        generation_args = args + (through_generation,) if through_generation is not None else args
        self.db.execute("DELETE FROM sync_segments WHERE owner=? AND worker=? AND store=?" + suffix + generation_suffix, generation_args)
        self.db.execute("UPDATE sync_log SET body=NULL,redacted=1 WHERE owner=? AND worker=? AND store=? AND event_type IN ('sync.conversation.upserted','sync.message.segment','sync.run.state','sync.backfill.progress','message.appended')" + suffix + (' AND (generation IS NULL OR generation<=?)' if through_generation is not None else ''), generation_args)
        # Known execution facts cannot be covered by ContentRedaction. Retain a
        # separate, non-replayable minimal projection while erasing their display text.
        for row in self.db.execute('SELECT event_id,body FROM sync_log WHERE owner=? AND worker=? AND store=? AND body IS NOT NULL', (owner, worker, store)).fetchall():
            event = json.loads(row[1]); payload = event.get('payload', {})
            scoped = conversation is None or event.get('conversationId') in public_conversations | {conversation} or payload.get('conversationId') == conversation
            if not scoped or event['type'] in {'sync.reset', 'sync.conversation.deleted', 'sync.busy.snapshot'}:
                continue
            if event['type'] == 'capability.changed' and not permanent:
                continue
            evidence = dict(event)
            if event['type'].startswith('command.'):
                if 'error' in evidence:
                    evidence['error'] = dict(evidence['error'], message=evidence['error']['code'])
                if 'controlResult' in evidence:
                    evidence['controlResult'] = dict(evidence['controlResult'], reason='Content removed')
            else:
                evidence = {'_skip': True}
            self.db.execute('UPDATE sync_log SET body=NULL,evidence=? WHERE owner=? AND worker=? AND store=? AND event_id=?', (canonical(evidence), owner, worker, store, row[0]))
        if permanent:
            self.db.execute("UPDATE sync_ids SET deleted=1 WHERE owner=? AND worker=? AND store=?" + suffix, args)
        # Rev1 records, if present, retain their immutable digest without replayable content.
        for row in self.db.execute("SELECT event_id,body FROM inbox WHERE owner=? AND worker=? AND store=?", (owner, worker, store)).fetchall():
            value = json.loads(row[1])
            if conversation is None or value.get('conversationId') in public_conversations:
                safe = {k: value[k] for k in ('type','eventId','workerId','workerStoreId','seq','firstSeq') if k in value}
                safe.update(_redacted=True, _digest=value.get('_digest', digest(value)))
                self.db.execute("UPDATE inbox SET body=? WHERE owner=? AND event_id=?", (canonical(safe), owner, row[0]))
