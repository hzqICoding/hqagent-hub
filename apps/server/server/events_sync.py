import json

from .common import Fault, canonical, digest, require, seconds
from .events import Events
from .replica import CONTENT
from .service import TERMINAL


class SyncEvents(Events):
    def accept(self, tx, owner, event, connection=None, encoded_bytes=None):
        if event['wireRevision'] == 1:
            prior = tx.event_id(owner, event['eventId'])
            if prior and prior.get('_redacted'):
                require(prior['_digest'] == digest(event), 'REMOTE_EVENT_CONFLICT')
                return self.position(tx, owner, event['workerId'], event['workerStoreId'])
            return super().accept(tx, owner, event)
        worker, store = event['workerId'], event['workerStoreId']
        if event['type'] == 'sync.content.redaction':
            self.redact(tx, owner, event)
            return self.advance(tx, owner, worker, store, connection)
        first, last = event.get('firstSeq', event['seq']), event['seq']
        require(first <= last, 'REMOTE_EVENT_CONFLICT')
        prior = tx.sync_entry(owner, worker, store, event_id=event['eventId'])
        if prior:
            require(prior['event_hash'] == digest(event) and prior['last_seq'] == last and prior['event_type'] == event['type'], 'REMOTE_EVENT_CONFLICT')
            if prior['redacted']:
                require(prior['generation'] is None or event.get('syncGeneration', 0) <= prior['generation'], 'REMOTE_SYNC_CONFLICT')
                if prior['conversation'] is not None:
                    require(event.get('payload', {}).get('conversationId', event.get('conversationId')) == prior['conversation'], 'REMOTE_SYNC_CONFLICT')
            return self.advance(tx, owner, worker, store, connection)
        require(not tx.sync_overlap(owner, worker, store, first, last) and first > self.position(tx, owner, worker, store)['seq'], 'REMOTE_EVENT_CONFLICT')
        require(event['type'] != 'message.appended', 'REMOTE_SYNC_CONFLICT')
        if event['type'] == 'run.state_changed':
            require('summary' not in event['payload'], 'REMOTE_SYNC_CONFLICT')
        deleting = event['type'] in {'sync.reset', 'sync.conversation.deleted'}
        pending, size = tx.sync_pending_bytes(owner, worker, store)
        encoded_bytes = encoded_bytes if encoded_bytes is not None else len(canonical(event).encode())
        require(deleting or (pending < 16 and size + encoded_bytes <= 1048576), 'REMOTE_SYNC_RESOURCE_LIMIT')
        local = event.get('payload', {}).get('conversationId') if event['type'].startswith('sync.') else None
        if event['type'] == 'sync.conversation.deleted':
            local = event['conversationId']
        if event['type'] == 'approval.state_changed':
            local = event['conversationId']
        if event['type'] == 'sync.busy.snapshot':
            require(not tx.sync_busy_part_exists(owner, event), 'REMOTE_SYNC_CONFLICT')
        tx.sync_log_put(owner, event, local, encoded_bytes)
        if deleting:
            self.s.replica.predelete(tx, owner, event)
        elif event['type'] == 'command.received':
            self.s.received(tx, owner, event)
        elif event['type'] == 'sync.busy.snapshot':
            self.s.replica.observe_busy(tx, owner, event, connection)
        return self.advance(tx, owner, worker, store, connection)

    def position(self, tx, owner, worker, store):
        value = tx.get(owner, 'event-position', worker + ':' + store) or dict(seq=0)
        return dict(workerStoreId=store, seq=value['seq'])

    def advance(self, tx, owner, worker, store, connection):
        position = self.position(tx, owner, worker, store)
        while True:
            row = tx.sync_log_next(owner, worker, store, position['seq'] + 1)
            if row is None:
                break
            if not row['redacted']:
                event = json.loads(row['body'] or row['evidence'])
                if event.get('_skip'):
                    pass
                elif event['type'].startswith('sync.'):
                    self.s.replica.apply(tx, owner, event, connection)
                elif event['type'] not in {'command.received', 'events.omitted'}:
                    self.execution(tx, owner, event)
            tx.sync_log_applied(owner, worker, store, row['event_id'], forget=True)
            position['seq'] = row['last_seq']
        tx.put(owner, 'event-position', worker + ':' + store, dict(seq=position['seq']), worker=worker, store=store)
        return position

    def redact(self, tx, owner, frame):
        worker, store = frame['workerId'], frame['workerStoreId']
        fence = tx.get(owner, 'deletion-fence', digest([worker, store, frame['deletionEventId']]))
        require(fence is not None and fence['seq'] == frame['deletionSeq'] and fence['generation'] == frame['syncGeneration'], 'REMOTE_SYNC_CONFLICT')
        if fence['type'] == 'sync.conversation.deleted':
            require(frame.get('conversationId') == fence['conversation'], 'REMOTE_SYNC_CONFLICT')
        else:
            require('conversationId' not in frame, 'REMOTE_SYNC_CONFLICT')
        key = digest([worker, store, frame['redactionId']])
        old = tx.get(owner, 'redaction-proof', key)
        require(old is None or old['hash'] == digest(frame), 'REMOTE_SYNC_CONFLICT')
        require(len({slot['seq'] for slot in frame['slots']}) == len(frame['slots']), 'REMOTE_SYNC_CONFLICT')
        for slot in frame['slots']:
            require(slot['seq'] < fence['seq'] and slot['originalType'] in CONTENT, 'REMOTE_SYNC_CONFLICT')
            require(fence['conversation'] is None or slot['originalType'] != 'sync.backfill.progress', 'REMOTE_SYNC_CONFLICT')
            tx.sync_cover(owner, worker, store, slot, fence['generation'], fence['conversation'])
        tx.put(owner, 'redaction-proof', key, dict(hash=digest(frame)), worker=worker, store=store)

    def reference(self, tx, owner, event, ref, local_conversation):
        result = dict(ref)
        public, _ = tx.sync_id(owner, event['workerId'], event['workerStoreId'], 'run', ref['runId'], local_conversation)
        result['runId'] = public
        return result

    def execution(self, tx, owner, event):
        kind = event['type']; worker, store = event['workerId'], event['workerStoreId']
        if kind == 'capability.changed':
            payload = event['payload']
            require(payload['workerId'] == worker and payload['workerStoreId'] == store, 'REMOTE_TARGET_MISMATCH')
            for group, key in [('workspaces','workspaceId'), ('scenes','sceneId')]:
                require(len({v[key] for v in payload[group]}) == len(payload[group]), 'REMOTE_EVENT_CONFLICT')
            self.s.save(tx, owner, 'catalog', worker, payload)
            device = self.s.get(tx, owner, 'device', worker)
            device['capabilityRevision'] = payload['capabilityRevision']
            self.s.save(tx, owner, 'device', worker, device)
            return
        value = None
        if 'commandId' in event:
            value = self.s.get(tx, owner, 'command', event['commandId'])
            require(value['targetWorkerId'] == worker and value['_frame']['expectedWorkerStoreId'] == store and value['conversationId'] == event['conversationId'], 'REMOTE_TARGET_MISMATCH')
            public, local = value['conversationId'], value['_frame']['localConversationId']
        else:
            local = event['conversationId']
            mapping = tx.sync_lookup(owner, worker, store, 'conversation', local)
            require(mapping is not None, 'NOT_FOUND')
            public = mapping['public']
        mapped = dict(event, conversationId=public)
        if 'resultRef' in event:
            mapped['resultRef'] = self.reference(tx, owner, event, event['resultRef'], local)
        if kind.startswith('command.'):
            self.command_v2(tx, owner, event, mapped, value)
        elif kind == 'conversation.skip_recorded':
            box = self.s.get(tx, owner, 'outbox', 'skip:' + event['commandId'])
            require(box['_frame']['conversationSeq'] == event['conversationSeq'], 'REMOTE_EVENT_CONFLICT')
            box['done'] = True; self.s.save(tx, owner, 'outbox', box['id'], box)
        elif kind == 'approval.state_changed':
            if not tx.get(owner, 'conversation', public):
                return
            payload = event['payload']; require(seconds(payload['expiresAt']) > seconds(payload['requestedAt']), 'REMOTE_EVENT_CONFLICT')
            identifier = self.s.replica.bind(tx, owner, worker, store, 'approval', payload['approvalId'], local)
            ref = self.reference(tx, owner, event, payload['resultRef'], local)
            self.s.get(tx, owner, 'run', ref['runId'])
            payload = dict(payload, approvalId=identifier, resultRef=ref)
            mapped['payload'] = payload
            self.s.save(tx, owner, 'approval', identifier, dict(payload, _localId=event['payload']['approvalId'], _worker=worker, _store=store, _conversation=public))
        elif kind == 'run.state_changed':
            # Revision 2 producers use sync.run.state; legacy-shaped observations
            # may corroborate references but cannot replace the synced replica.
            require('summary' not in event['payload'], 'REMOTE_SYNC_CONFLICT')
            payload = event['payload']
            require(payload['conversationId'] == local, 'REMOTE_TARGET_MISMATCH')
            mapped['payload'] = dict(payload, conversationId=public, runId=self.reference(tx, owner, event, dict(runId=payload['runId']), local)['runId'])
        elif kind == 'message.appended':
            raise Fault('REMOTE_SYNC_CONFLICT')  # new producers must use bounded segments
        if self.s.replica.visible(tx, owner, public) or (kind.startswith('command.') and self.s.command_visible(tx, owner, public)):
            self.s.event(tx, owner, 'worker.event', mapped)

    def command_v2(self, tx, owner, raw, event, value):
        kind = event['type']; frame = value['_frame']; payload = frame.get('payload', {})
        require(frame['wireRevision'] == 2, 'REMOTE_PROTOCOL_UNSUPPORTED')
        if raw.get('resultRef') and 'runId' in payload and not (value['type'] == 'run.retry' and kind == 'command.completed'):
            require(raw['resultRef']['runId'] == payload['runId'], 'REMOTE_TARGET_MISMATCH')
        if event.get('resultRef') and value.get('resultRef') and not (value['type'] == 'run.retry' and kind == 'command.completed'):
            for field in ('runId', 'executionTaskId'):
                if field in value['resultRef']:
                    require(event['resultRef'].get(field) == value['resultRef'][field], 'REMOTE_TARGET_MISMATCH')
        if value['status'] in TERMINAL:
            require(value.get('error', {}).get('code') in {'REMOTE_DELIVERY_EXPIRED', 'REMOTE_DEVICE_SUSPENDED'} and kind == 'command.rejected', 'REMOTE_EVENT_CONFLICT')
            return
        if kind in {'command.accepted', 'command.completed', 'command.failed', 'command.control_result'}:
            require(value.get('_granted'), 'REMOTE_EVENT_CONFLICT')
        if kind == 'command.accepted':
            require(value['status'] == 'queued', 'REMOTE_EVENT_CONFLICT'); value['status'] = 'accepted'
        elif kind == 'command.rejected':
            require(value['status'] == 'queued', 'REMOTE_EVENT_CONFLICT'); value['status'] = 'rejected'
        elif kind in {'command.completed', 'command.failed', 'command.control_result'}:
            require(value['status'] == 'accepted', 'REMOTE_EVENT_CONFLICT')
            if kind == 'command.completed':
                if value['type'] in {'conversation.create', 'conversation.update'}:
                    control = event.get('controlResult', {})
                    require(event['resultStatus'] == 'confirmed' and control.get('outcome') == 'confirmed' and control.get('evidence') == 'metadata_committed' and 'resultRef' not in event, 'REMOTE_EVENT_CONFLICT')
                else:
                    self.finish_matrix(value, event)
                value['status'] = 'completed'
            elif kind == 'command.failed':
                value['status'] = 'failed'
            elif value['type'] != 'command.withdraw':
                require('resultRef' in event and 'executionStatus' in event, 'REMOTE_EVENT_CONFLICT')
        control = event.get('controlResult')
        if control and control['outcome'] == 'rejected' and control['evidence'] == 'adapter_refused':
            require(control['executionMayStillBeRunning'], 'REMOTE_EVENT_CONFLICT')
        if control and value['type'] == 'run.cancel' and control['outcome'] == 'confirmed':
            require(not control['executionMayStillBeRunning'] and not control['orphanProcessIds'], 'REMOTE_EVENT_CONFLICT')
        for key in ('resultRef', 'controlResult', 'resultStatus', 'error'):
            if key in event:
                value[key] = event[key]
        if value.get('_deleted'):
            if 'error' in value: value['error'] = dict(value['error'], message=value['error']['code'])
            if 'controlResult' in value: value['controlResult'] = dict(value['controlResult'], reason='Content removed')
        value.update(deliveryState='acknowledged', observedAt=self.s.now())
        self.s.save(tx, owner, 'command', value['commandId'], value)
        for prefix in ('command:', 'grant:'):
            box = tx.get(owner, 'outbox', prefix + value['commandId'])
            if box:
                box['done'] = True; self.s.save(tx, owner, 'outbox', box['id'], box)
        if event.get('resultRef') and not value.get('_deleted'):
            ref = event['resultRef']
            self.s.save(tx, owner, 'run-ref', ref['runId'], dict(ref, conversationId=value['conversationId'], _worker=raw['workerId'], _store=raw['workerStoreId'], _localId=raw['resultRef']['runId']))
        if value['type'] == 'command.withdraw' and kind in {'command.completed', 'command.failed', 'command.rejected', 'command.control_result'} and payload.get('targetCommandId'):
            original = self.s.get(tx, owner, 'command', payload['targetCommandId'])
            original['withdrawalState'] = 'confirmed' if kind == 'command.completed' else 'requested' if kind == 'command.control_result' else 'denied'
            if kind == 'command.completed' and event['resultStatus'] == 'withdrawn' and original['status'] == 'queued':
                original.update(status='rejected', error=Fault('REMOTE_COMMAND_WITHDRAWN').view())
                for prefix in ('command:', 'grant:'):
                    old_box = tx.get(owner, 'outbox', prefix + original['commandId'])
                    if old_box:
                        old_box['done'] = True; self.s.save(tx, owner, 'outbox', old_box['id'], old_box)
            self.s.save(tx, owner, 'command', original['commandId'], original)
            self.s.command_event(tx, owner, original)
