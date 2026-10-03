"""Computer-owned replicas. No execution, admission lock, or model configuration."""
import hashlib

from .common import canonical, digest, require

CONTENT = {'sync.conversation.upserted', 'sync.message.segment', 'sync.run.state', 'sync.backfill.progress', 'message.appended'}


class Replica:
    def __init__(self, service):
        self.s = service

    def state(self, tx, owner, worker, store):
        key = digest([worker, store])
        return tx.get(owner, 'sync-state', key) or dict(id=key, workerId=worker, workerStoreId=store,
            generation=0, closedGeneration=0, enabled=True, busyFresh=False, busy=[], busySeen=0, busySeq=0, complete=False)

    def save_state(self, tx, owner, state):
        self.s.save(tx, owner, 'sync-state', state['id'], state)

    def bind(self, tx, owner, worker, store, kind, local, conversation):
        legacy = tx.get(owner, kind, local)
        candidate = local if legacy and legacy.get('targetWorkerId', legacy.get('_worker')) == worker and legacy.get('workerStoreId', legacy.get('_store')) == store else None
        public, deleted = tx.sync_id(owner, worker, store, kind, local, conversation, public=candidate)
        require(not deleted, 'NOT_FOUND')
        return public

    def visible(self, tx, owner, public):
        conv = tx.get(owner, 'conversation', public)
        return bool(conv and conv.get('visibility', 'both') != 'pc_only')

    def generation(self, tx, owner, event):
        state = self.state(tx, owner, event['workerId'], event['workerStoreId'])
        generation = event['syncGeneration']
        if generation <= state['closedGeneration'] or generation < state['generation']:
            return None
        if generation > state['generation']:
            state.update(generation=generation, enabled=True, backfill=None, complete=False)
            self.save_state(tx, owner, state)
        return state

    def browser_event(self, tx, owner, value):
        tx.browser_add(owner, dict(value, recordedAt=self.s.now()))

    def predelete(self, tx, owner, event):
        worker, store = event['workerId'], event['workerStoreId']
        state = self.state(tx, owner, worker, store)
        generation = event['syncGeneration']
        if event['type'] == 'sync.reset':
            if generation >= state['generation']:
                self.s.erase_replica(tx, owner, worker, store, through_generation=generation)
                state.update(generation=generation, closedGeneration=max(generation, state['closedGeneration']), enabled=False, complete=False)
                self.save_state(tx, owner, state)
                self.browser_event(tx, owner, dict(type='store.reset', workerId=worker, workerStoreId=store))
        else:
            local = event['conversationId']
            public, _ = tx.sync_id(owner, worker, store, 'conversation', local, local)
            was_visible = self.visible(tx, owner, public)
            was_pi = bool(tx.get(owner,'pi-resource','conversation:'+public))
            self.s.erase_replica(tx, owner, worker, store, local, permanent=True, through_generation=generation)
            if was_visible:
                self.browser_event(tx, owner, dict(type='conversation.deleted', conversationId=public, _pi=was_pi))
        fence = dict(eventId=event['eventId'], seq=event['seq'], generation=generation, type=event['type'], conversation=event.get('conversationId'))
        tx.put(owner, 'deletion-fence', digest([worker, store, event['eventId']]), fence, worker=worker, store=store)

    def apply(self, tx, owner, event, connection):
        kind = event['type']
        if kind in {'sync.reset', 'sync.conversation.deleted'}:
            return
        if kind == 'sync.busy.snapshot':
            self.busy(tx, owner, event, connection)
            return
        state = self.generation(tx, owner, event)
        if state is None:
            return
        if kind == 'sync.backfill.progress':
            previous = state.get('backfill')
            if previous and previous['id'] == event['backfillId']:
                require(previous['high'] == event['snapshotHighWater'] and event['batchIndex'] == previous['batch'] + 1, 'REMOTE_SYNC_CONFLICT')
            else:
                require(event['batchIndex'] == 0, 'REMOTE_SYNC_CONFLICT')
            tx.sync_batch_check(owner, event)
            if event['complete']:
                require(not any(a['availability']=='pending_upload' for a in tx.list(owner,'attachment',worker=event['workerId'],store=event['workerStoreId'])),'ATTACHMENT_NOT_READY')
                require(tx.sync_part_usage(owner, event['workerId'], event['workerStoreId'])[0] == 0, 'REMOTE_SYNC_CONFLICT')
                # A complete computer backfill replaces R1 server-only shadows;
                # absence is not inferred before this durable completion marker.
                for legacy in tx.list(owner, 'conversation', worker=event['workerId'], store=event['workerStoreId']):
                    if '_localId' not in legacy:
                        self.s.erase_replica(tx, owner, event['workerId'], event['workerStoreId'], legacy['conversationId'])
                        self.browser_event(tx, owner, dict(type='conversation.deleted', conversationId=legacy['conversationId']))
            completed = event['complete'] or bool(previous and previous['id'] == event['backfillId'] and state['complete'])
            state.update(backfill=dict(id=event['backfillId'], high=event['snapshotHighWater'], batch=event['batchIndex']), complete=completed)
            self.save_state(tx, owner, state)
            return
        payload = event['payload']; local = payload['conversationId']
        existing = tx.sync_lookup(owner, event['workerId'], event['workerStoreId'], 'conversation', local)
        if existing and existing['deleted']:
            return
        if kind == 'sync.conversation.upserted':
            self.conversation(tx, owner, event)
        elif kind == 'sync.message.segment':
            require(existing is not None and tx.get(owner, 'conversation', existing['public']) is not None, 'NOT_FOUND')
            self.message(tx, owner, event, existing['public'])
        elif kind == 'sync.run.state':
            require(existing is not None and tx.get(owner, 'conversation', existing['public']) is not None, 'NOT_FOUND')
            public = self.bind(tx, owner, event['workerId'], event['workerStoreId'], 'run', payload['runId'], local)
            previous = tx.get(owner, 'run', public)
            if previous and previous['observedAt'] > payload['observedAt']:
                return
            value = {k: v for k, v in payload.items() if k != 'recoveryRequired'}
            value.update(runId=public, conversationId=existing['public'], workerOnline=False,
                         _worker=event['workerId'], _store=event['workerStoreId'], _localId=payload['runId'], _recovery=payload.get('recoveryRequired', False))
            self.s.save(tx, owner, 'run', public, value)
            conv = self.s.get(tx, owner, 'conversation', existing['public'])
            conv['lastActivityAt'] = max(conv.get('lastActivityAt', conv['updatedAt']), payload['observedAt'])
            self.s.save(tx, owner, 'conversation', conv['conversationId'], conv)
            if self.visible(tx, owner, conv['conversationId']):
                self.s.event(tx, owner, 'conversation.updated', self.s.view(owner, 'conversation', conv))
                if event['wireRevision'] == 5:
                    self.s.browser_events.sync_run(tx, owner, event, value)

    def conversation(self, tx, owner, event):
        local_workspace = event['payload']['workspaceId']
        if event['wireRevision'] >= 3:
            event = self.s.native_events.conversation(tx, owner, event)
        payload = event['payload']; local = payload['conversationId']
        public = self.bind(tx, owner, event['workerId'], event['workerStoreId'], 'conversation', local, local)
        previous = tx.get(owner, 'conversation', public)
        # Revision 2 stored the local workspace ID; revision 3 projects it to
        # an owner/device/store-scoped public ID. Compare the same identity
        # domain across an upgrade without treating a real metadata edit as
        # activity. Never reinterpret an already-public workspace as local.
        rebound_workspace = bool(event['wireRevision'] >= 3 and previous and
            previous.get('workspaceId') == local_workspace and local_workspace != payload['workspaceId'] and
            tx.sync_reverse(owner, 'workspace', local_workspace) is None)
        if rebound_workspace:
            previous = dict(previous, workspaceId=payload['workspaceId'])
        if previous and '_localId' not in previous:
            tx.retire_legacy_messages(owner, public)
        if previous and previous.get('metadataVersion', 0) >= payload['metadataVersion']:
            if previous['metadataVersion'] > payload['metadataVersion']:
                return
            # LocalConversationView.version is a metadata CAS revision: message
            # and run activity may advance updatedAt without incrementing it.
            # Compare all actual metadata, not a hash that includes activity.
            require(all(previous.get(k) == v for k, v in payload.items()
                        if k not in {'conversationId', 'updatedAt'}), 'REMOTE_SYNC_CONFLICT')
            if payload['updatedAt'] <= previous['updatedAt'] and not rebound_workspace:
                return
            value = dict(previous, updatedAt=max(payload['updatedAt'], previous['updatedAt']),
                         lastActivityAt=max(previous.get('lastActivityAt', previous['updatedAt']), payload['updatedAt']),
                         _metadataHash=digest(payload))
            self.s.save(tx, owner, 'conversation', public, value)
            if payload['visibility'] != 'pc_only':
                self.s.event(tx, owner, 'conversation.updated', self.s.view(owner, 'conversation', value))
            return
        value = dict(payload, conversationId=public, targetWorkerId=event['workerId'], workerId=event['workerId'],
                     workerStoreId=event['workerStoreId'], lastActivityAt=max(payload['updatedAt'], (previous or {}).get('lastActivityAt', '')), _localId=local,
                     _metadataHash=digest(payload), _generation=event['syncGeneration'])
        state = self.state(tx, owner, event['workerId'], event['workerStoreId'])
        value.update(_busy=local in state['busy'], _busyConnection=state.get('busyConnection'))
        if state.get('busyObservedAt'):
            value['_busyObservedAt'] = state['busyObservedAt']
        self.s.save(tx, owner, 'conversation', public, value)
        tx.remove_record(owner, 'create-reservation', public)
        if payload['visibility'] != 'pc_only':
            self.s.event(tx, owner, 'conversation.updated', self.s.view(owner, 'conversation', value))
        elif previous and previous.get('visibility', 'both') != 'pc_only':
            self.browser_event(tx, owner, dict(type='conversation.deleted', conversationId=public, _pi=self.s.projection.is_pi(tx,owner,value)))

    def message(self, tx, owner, event, conversation):
        p = event['payload']; worker, store = event['workerId'], event['workerStoreId']
        require(p['segmentIndex'] < p['segmentCount'], 'REMOTE_SYNC_CONFLICT')
        require(len(p['text'].encode()) <= 64000, 'REMOTE_SYNC_RESOURCE_LIMIT')
        require(p['segmentCount'] <= 4096 and p['totalUtf8Bytes'] <= self.s.settings.sync_message_bytes, 'REMOTE_SYNC_RESOURCE_LIMIT')
        public = self.bind(tx, owner, worker, store, 'message', p['messageId'], p['conversationId'])
        metadata = {k: v for k, v in p.items() if k not in {'text', 'segmentIndex'}}
        previous = tx.get(owner, 'message', public)
        if previous and previous.get('_generation', event['syncGeneration']) == event['syncGeneration'] and p['messageRevision'] <= previous['messageRevision']:
            if p['messageRevision'] == previous['messageRevision']:
                require(previous['_metadataHash'] == digest(metadata), 'REMOTE_SYNC_CONFLICT')
                # Even a repeated completed revision must not smuggle a different piece.
                require(previous['_partHashes'][p['segmentIndex']] == digest(p['text']), 'REMOTE_SYNC_CONFLICT')
            return
        require(not tx.sync_message_collision(owner, conversation, p['messageSequence'], public), 'REMOTE_SYNC_CONFLICT')
        staged = tx.get(owner, 'segment-meta', public)
        if staged and staged['generation'] != event['syncGeneration']:
            tx.sync_parts_delete(owner, worker, store, p['messageId'], 2**53 - 1)
            tx.remove_record(owner, 'segment-meta', public)
            staged = None
        if staged and p['messageRevision'] < staged['revision']:
            return
        if staged and p['messageRevision'] == staged['revision']:
            require(staged['hash'] == digest(metadata) and staged['generation'] == event['syncGeneration'], 'REMOTE_SYNC_CONFLICT')
        else:
            tx.sync_parts_delete(owner, worker, store, p['messageId'], p['messageRevision'] - 1)
            self.s.save(tx, owner, 'segment-meta', public, dict(hash=digest(metadata), revision=p['messageRevision'], generation=event['syncGeneration'], _worker=worker, _store=store, _conversation=conversation))
        tx.sync_part_checked(owner, worker, store, event['syncGeneration'], p, self.s.settings.sync_staging_bytes)
        if tx.sync_message_part_count(owner, worker, store, event['syncGeneration'], p['messageId'], p['messageRevision']) != p['segmentCount']:
            return
        hasher = hashlib.sha256(); total = 0; count = 0; part_hashes = []
        for index, text, size in tx.sync_parts(owner, worker, store, event['syncGeneration'], p['messageId'], p['messageRevision']):
            if index != count:
                return
            hasher.update(text.encode()); total += size; count += 1; part_hashes.append(digest(text))
        if count != p['segmentCount']:
            return
        require(total == p['totalUtf8Bytes'] and hasher.hexdigest() == p['contentSha256'], 'REMOTE_SYNC_CONFLICT')
        text = ''.join(part[1] for part in tx.sync_parts(owner, worker, store, event['syncGeneration'], p['messageId'], p['messageRevision']))
        value = dict(messageId=public, conversationId=conversation, role=p['role'], text=text, createdAt=p['createdAt'], messageSequence=p['messageSequence'], messageRevision=p['messageRevision'],
                     _worker=worker, _store=store, _localId=p['messageId'], _generation=event['syncGeneration'], _contentHash=p['contentSha256'], _metadataHash=digest(metadata), _partHashes=part_hashes)
        if p.get('runId'):
            value['runId'] = self.bind(tx, owner, worker, store, 'run', p['runId'], p['conversationId'])
        if 'attachments' in p:
            value['attachments']=self.s.attachments.sync_message(tx,owner,event,value)
        self.s.save(tx, owner, 'message', public, value)
        tx.sync_parts_delete(owner, worker, store, p['messageId'], p['messageRevision'])
        tx.remove_record(owner, 'segment-meta', public)
        conv = self.s.get(tx, owner, 'conversation', conversation)
        conv['lastActivityAt'] = max(conv.get('lastActivityAt', conv['updatedAt']), p['createdAt'])
        self.s.save(tx, owner, 'conversation', conversation, conv)
        if self.visible(tx, owner, conversation):
            self.s.event(tx, owner, 'message.appended', self.s.view(owner, 'message', value))

    def observe_busy(self, tx, owner, event, connection):
        if event['connectionId'] != connection.identifier or event['workerEpoch'] != connection.epoch:
            return
        state = self.state(tx, owner, connection.worker, connection.store)
        first = tx.sync_snapshot_first(owner, connection.worker, connection.store, event['snapshotId'])
        if first < state['busySeq'] or (state.get('busyPending') != event['snapshotId'] and first < state.get('busyPendingFirst', 0)):
            return
        if event['seq'] > state['busySeen']:
            connection.busy_fresh = False
            state.update(busySeen=event['seq'], busyFresh=False, busyPending=event['snapshotId'], busyPendingFirst=first)
            self.save_state(tx, owner, state)
            keep = digest([connection.worker, connection.store, event['snapshotId']])
            for old in tx.list(owner, 'sync-stage', worker=connection.worker, store=connection.store):
                if old['id'] != keep:
                    tx.remove_record(owner, 'sync-stage', old['id'])

    def busy(self, tx, owner, event, connection):
        if event['connectionId'] != connection.identifier or event['workerEpoch'] != connection.epoch:
            return
        require(event['partIndex'] < event['partCount'] <= 1024, 'REMOTE_SYNC_RESOURCE_LIMIT')
        state = self.state(tx, owner, connection.worker, connection.store)
        if tx.sync_snapshot_first(owner, connection.worker, connection.store, event['snapshotId']) < state['busySeq']:
            return
        if state.get('busyPending') != event['snapshotId']:
            return
        key = digest([connection.worker, connection.store, event['snapshotId']])
        staged = tx.get(owner, 'sync-stage', key) or dict(id=key, parts={}, count=event['partCount'], captured=event['capturedAt'], connection=connection.identifier, _worker=connection.worker, _store=connection.store)
        require(staged['count'] == event['partCount'] and staged['captured'] == event['capturedAt'] and staged['connection'] == connection.identifier, 'REMOTE_SYNC_CONFLICT')
        part = str(event['partIndex'])
        require(part not in staged['parts'] or staged['parts'][part] == event['conversationIds'], 'REMOTE_SYNC_CONFLICT')
        staged['parts'][part] = event['conversationIds']
        self.s.save(tx, owner, 'sync-stage', key, staged)
        if len(staged['parts']) != event['partCount'] or state.get('busyPending') != event['snapshotId']:
            return
        ids = [item for index in range(event['partCount']) for item in staged['parts'][str(index)]]
        require(len(ids) == len(set(ids)), 'REMOTE_SYNC_CONFLICT')
        require(ids or event['partCount'] == 1, 'REMOTE_SYNC_CONFLICT')
        fresh = not self.s.get(tx, owner, 'device', connection.worker)['_frozen']
        state.update(busy=ids, busyFresh=fresh, busyConnection=connection.identifier, busyObservedAt=event['capturedAt'], busySeq=event['seq'])
        self.save_state(tx, owner, state)
        tx.after_commit(('busy', owner, connection.worker), lambda: setattr(connection, 'busy_fresh', fresh))
        for old in tx.list(owner, 'sync-stage', worker=connection.worker, store=connection.store):
            tx.remove_record(owner, 'sync-stage', old['id'])
        for conv in tx.list(owner, 'conversation', worker=connection.worker, store=connection.store):
            unchanged = (conv.get('_busyConnection') == connection.identifier and
                         conv.get('_busy', False) == (conv.get('_localId') in ids) and fresh)
            conv.update(_busy=conv.get('_localId') in ids, _busyConnection=connection.identifier, _busyObservedAt=event['capturedAt'])
            self.s.save(tx, owner, 'conversation', conv['conversationId'], conv)
            if conv.get('visibility', 'both') != 'pc_only' and not (event['wireRevision'] == 5 and unchanged):
                # The validated whole snapshot and its browser event commit
                # together; connection.busy_fresh changes only after commit.
                self.s.event(tx, owner, 'conversation.updated', self.s.view(owner, 'conversation', conv, busy_fresh=fresh))
