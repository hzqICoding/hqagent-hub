"""R1.5 browser admission and public projections. Legacy Service remains the R1 ledger."""
import base64
import hmac
import json

from . import wire
from .common import Fault, MAX_SEQ, canonical, digest, require, seconds, stamp, uid
from .replica import Replica
from .service import BLOCKED, Service, TERMINAL


class SyncService(Service):
    def __init__(self, repo, settings, security):
        super().__init__(repo, settings, security)
        self.replica = Replica(self)
        with repo.transaction() as tx:
            for account in tx.auth_list('account:'):
                owner = account['owner']
                for state in tx.list(owner, 'sync-state'):
                    state.update(busyFresh=False, busyPending=None, busyConnection=None)
                    self.replica.save_state(tx, owner, state)
                for staged in tx.list(owner, 'sync-stage'):
                    tx.remove_record(owner, 'sync-stage', staged['id'])

    def on_hello(self, tx, owner, device, frame, connection_id):
        requested = frame['wireRevision']; previous = device.get('_wireRevision', 1)
        if previous == 2 and requested == 1:
            raise Fault('REMOTE_PROTOCOL_UNSUPPORTED')
        if requested == 2 and previous == 1:
            pending = [c for c in tx.list(owner, 'command', worker=device['workerId']) if c['_frame']['wireRevision'] == 1 and
                       (c['status'] not in TERMINAL or c.get('controlResult', {}).get('outcome') == 'unconfirmed' or c.get('controlResult', {}).get('orphanProcessIds'))]
            pending_boxes = [b for b in tx.list(owner, 'outbox', worker=device['workerId']) if not b['done'] and b['_frame']['wireRevision'] == 1]
            position = tx.get(owner, 'event-position', device['workerId'] + ':' + frame['workerStoreId']) or dict(seq=0)
            require(not pending and not pending_boxes and not tx.legacy_pending(owner, device['workerId'], frame['workerStoreId']), 'REMOTE_REVISION_REQUIRED')
            report = frame['lastServerAck']
            require(not position['seq'] or (report and report['workerStoreId'] == frame['workerStoreId'] and report['seq'] == position['seq']), 'REMOTE_REVISION_REQUIRED')
            device['_upgradeAck'] = position['seq']
        device['_supported'] = sorted(set(device.get('_supported', [])) | {requested})
        if not device['_frozen']:
            device['_wireRevision'] = requested
        if requested == 2:
            state = self.replica.state(tx, owner, device['workerId'], frame['workerStoreId'])
            state.update(busyFresh=False, busyConnection=connection_id, busyPending=None)
            self.replica.save_state(tx, owner, state)
            for old in tx.list(owner, 'sync-stage', worker=device['workerId'], store=frame['workerStoreId']):
                tx.remove_record(owner, 'sync-stage', old['id'])

    def browser_get(self, tx, owner, kind, identifier):
        value = self.get(tx, owner, kind, identifier)
        require(not value.get('_deleted'), 'NOT_FOUND')
        conv_id = identifier if kind == 'conversation' else value.get('conversationId', value.get('_conversation'))
        if conv_id:
            conv = tx.get(owner, 'conversation', conv_id)
            if not conv and kind == 'command' and tx.get(owner, 'create-reservation', conv_id):
                return value
            require(conv is not None and conv.get('visibility', 'both') != 'pc_only', 'NOT_FOUND')
        return value

    def replay(self, tx, owner, scope, key, body, action):
        identifier = self.security.mac('idempotency', scope + ':' + key)
        record = tx.get(owner, 'idempotency', identifier)
        if record and record.get('_retired'):
            require(record['content'] == self.security.mac('intent', canonical(body)), 'IDEMPOTENCY_MISMATCH')
            raise Fault('NOT_FOUND')
        result = super().replay(tx, owner, scope, key, body, action)
        if isinstance(result, dict) and result.get('commandId'):
            command = tx.get(owner, 'command', result['commandId'])
            require(not command or command.get('error', {}).get('code') != 'REMOTE_DELIVERY_EXPIRED', 'REMOTE_DELIVERY_EXPIRED')
        return result

    def view(self, owner, kind, value):
        result = super().view(owner, kind, value)
        if kind == 'device':
            conn = self.connections.get((owner, value['workerId']))
            online = self.online(owner, value['workerId'])
            result.update(online=online, busySnapshotFresh=bool(online and conn and not conn.closed and getattr(conn, 'busy_fresh', False)), supportedWireRevisions=value.get('_supported', []))
        if kind == 'conversation':
            conn = self.connections.get((owner, value['targetWorkerId']))
            fresh = bool(conn and self.online(owner, value['targetWorkerId']) and getattr(conn, 'busy_fresh', False) and value.get('_busyConnection') == conn.identifier)
            result.update(workerId=value['targetWorkerId'], visibility=value.get('visibility', 'both'),
                          busy=value.get('_busy', False), busyFresh=fresh,
                          archived=value.get('archived', False), lastActivityAt=value.get('lastActivityAt', value['updatedAt']))
            if value.get('_busyObservedAt'):
                result['busyObservedAt'] = value['_busyObservedAt']
        if kind == 'command' and value.get('_frame', {}).get('wireRevision') == 2:
            if result['deliveryState'] in {'queued_offline', 'sent'}:
                result['deliveryState'] = 'awaiting_receipt'
            if value.get('_granted') and value['status'] == 'queued':
                result['deliveryState'] = 'granted'
        return result

    def command_event(self, tx, owner, command):
        if self.command_visible(tx, owner, command['conversationId']):
            super().command_event(tx, owner, command)

    def command_visible(self, tx, owner, conversation):
        return self.replica.visible(tx, owner, conversation) or (tx.get(owner, 'conversation', conversation) is None and tx.get(owner, 'create-reservation', conversation) is not None)

    def ready(self, tx, owner, worker, store):
        device = self.get(tx, owner, 'device', worker)
        require(device['status'] != 'revoked', 'REMOTE_DEVICE_REVOKED')
        require(self.online(owner, worker), 'REMOTE_DEVICE_OFFLINE')
        conn = self.connections[(owner, worker)]
        require(conn.revision == 2, 'REMOTE_REVISION_REQUIRED')
        require(not device['_frozen'] and conn.store == store == device['workerStoreId'], 'REMOTE_STORE_CHANGED')
        require(self.replica.state(tx, owner, worker, store)['enabled'], 'REMOTE_SYNC_DISABLED')
        return conn

    def conversation(self, tx, owner, identifier):
        conv = self.browser_get(tx, owner, 'conversation', identifier)
        self.ready(tx, owner, conv['targetWorkerId'], conv['workerStoreId'])
        require('_localId' in conv, 'REMOTE_STATE_NOT_READY')
        return conv

    def enqueue_v2(self, tx, owner, conv, kind, payload, expires=None, *, sequence=None):
        self.ready(tx, owner, conv['targetWorkerId'], conv['workerStoreId'])
        now = self.settings.clock()
        end = min(now + 30, seconds(expires)) if expires else now + 30
        require(end > now, 'REMOTE_DELIVERY_EXPIRED')
        identifier = uid(); deadline = stamp(end)
        frame = dict(type=kind, commandId=identifier, conversationId=conv['conversationId'], localConversationId=conv['_localId'],
                     targetWorkerId=conv['targetWorkerId'], expectedWorkerStoreId=conv['workerStoreId'], createdAt=stamp(now), expiresAt=deadline, deliverBy=deadline, payload=payload)
        if sequence is not None:
            frame['conversationSeq'] = sequence
        frame = wire.command(frame, 2)
        receipt = dict(commandId=identifier, conversationId=conv['conversationId'], status='queued', deliveryState='queued_online', workerOnline=True, expiresAt=deadline)
        if sequence is not None:
            receipt['conversationSeq'] = sequence
        value = dict(receipt, targetWorkerId=conv['targetWorkerId'], type=kind, withdrawalState='none', observedAt=stamp(now), createdAt=stamp(now), deliverBy=deadline,
                     _frame=frame, _digest=digest(frame), _receipt=receipt, _dispatch=False, _granted=False)
        self.save(tx, owner, 'command', identifier, value)
        self.outbox(tx, owner, frame)
        self.command_event(tx, owner, value)
        return receipt

    def create_conversation(self, tx, owner, body):
        self.ready(tx, owner, body['targetWorkerId'], body['workerStoreId'])
        catalog = self.get(tx, owner, 'catalog', body['targetWorkerId'])
        require(catalog['workerStoreId'] == body['workerStoreId'], 'REMOTE_STORE_CHANGED')
        require(any(w['workspaceId'] == body['workspaceId'] for w in catalog['workspaces']), 'NOT_FOUND')
        scene = next((s for s in catalog['scenes'] if s['sceneId'] == body['sceneId']), None)
        require(scene is not None, 'NOT_FOUND')
        require(scene['version'] == body['sceneVersion'], 'REMOTE_SCENE_VERSION_MISMATCH')
        local = uid()
        public, _ = tx.sync_id(owner, body['targetWorkerId'], body['workerStoreId'], 'conversation', local, local)
        reservation = dict(conversationId=public, targetWorkerId=body['targetWorkerId'], workerStoreId=body['workerStoreId'], _localId=local)
        self.save(tx, owner, 'create-reservation', public, reservation)
        return self.enqueue_v2(tx, owner, reservation, 'conversation.create', body)

    def update_conversation(self, tx, owner, identifier, body):
        conv = self.conversation(tx, owner, identifier)
        require(bool(set(body) & {'title', 'archived', 'visibility'}))
        return self.enqueue_v2(tx, owner, conv, 'conversation.update', dict(body, conversationId=conv['_localId']))

    def send_message(self, tx, owner, identifier, body):
        conv = self.conversation(tx, owner, identifier)
        key = digest([identifier, body['clientMessageId']])
        previous = tx.get(owner, 'message-intent', key)
        if previous:
            require(previous['content'] == digest(body), 'IDEMPOTENCY_MISMATCH')
            require(not previous.get('_retired'), 'NOT_FOUND')
            command = self.get(tx, owner, 'command', previous['receipt']['commandId'])
            require(command.get('error', {}).get('code') != 'REMOTE_DELIVERY_EXPIRED', 'REMOTE_DELIVERY_EXPIRED')
            return previous['receipt']
        conn = self.connections[(owner, conv['targetWorkerId'])]
        state = self.replica.state(tx, owner, conn.worker, conn.store)
        require(state.get('busyFresh') and state.get('busyConnection') == conn.identifier and getattr(conn, 'busy_fresh', False), 'REMOTE_STATE_NOT_READY')
        require(conv['_localId'] not in state['busy'], 'REMOTE_CONVERSATION_BUSY')
        order = tx.get(owner, 'remote-order', identifier) or dict(next=1)
        require(order['next'] <= MAX_SEQ, 'REMOTE_SYNC_RESOURCE_LIMIT')
        payload = {k: body[k] for k in ('clientMessageId', 'text', 'sessionMode')}
        payload.update({k: conv[k] for k in ('workspaceId', 'sceneId', 'sceneVersion')})
        receipt = self.enqueue_v2(tx, owner, conv, 'run.submit', payload, body.get('expiresAt'), sequence=order['next'])
        tx.put(owner, 'remote-order', identifier, dict(next=order['next'] + 1), worker=conn.worker, store=conn.store, parent=identifier)
        tx.put(owner, 'message-intent', key, dict(content=digest(body), receipt=receipt), worker=conn.worker, store=conn.store, parent=identifier)
        return receipt

    def control(self, tx, owner, identifier, body):
        run = tx.get(owner, 'run', identifier) or tx.get(owner, 'run-ref', identifier)
        require(run is not None, 'NOT_FOUND')
        conv = self.conversation(tx, owner, run['conversationId'])
        require('nodeId' not in body or body['action'] == 'retry')
        require('_localId' in run, 'REMOTE_STATE_NOT_READY')
        payload = dict(runId=run['_localId'], **{k: v for k, v in body.items() if k in {'nodeId', 'reason'}})
        return self.enqueue_v2(tx, owner, conv, 'run.' + body['action'], payload, body.get('expiresAt'))

    def approval(self, tx, owner, identifier, body):
        value = self.browser_get(tx, owner, 'approval', identifier)
        conv = self.conversation(tx, owner, value['_conversation'])
        require(value['status'] == 'pending' and seconds(value['expiresAt']) > self.settings.clock(), 'REMOTE_COMMAND_EXPIRED')
        catalog = self.get(tx, owner, 'catalog', conv['targetWorkerId'])
        if body['decision'] == 'approve':
            require(value['remoteApprovalAllowed'] and value['action'] not in BLOCKED | {'shell'} | set(catalog['remotelyBlockedActions']) and value['riskLevel'] not in {'high','critical'}, 'REMOTE_APPROVAL_FORBIDDEN')
        old = tx.get(owner, 'approval-intent', identifier)
        if old:
            require(old['content'] == digest(body), 'IDEMPOTENCY_MISMATCH')
            require(not old.get('_retired'), 'NOT_FOUND')
            return old['receipt']
        run = self.get(tx, owner, 'run', value['resultRef']['runId'])
        require(run['status'] not in {'succeeded','cancelled','failed'}, 'REMOTE_APPROVAL_FORBIDDEN')
        receipt = self.enqueue_v2(tx, owner, conv, 'approval.decide', dict(body, approvalId=value['_localId'], runId=run['_localId']), value['expiresAt'])
        tx.put(owner, 'approval-intent', identifier, dict(content=digest(body), receipt=receipt), worker=conv['targetWorkerId'], store=conv['workerStoreId'], parent=conv['conversationId'])
        return receipt

    def withdraw(self, tx, owner, identifier, body):
        value = self.browser_get(tx, owner, 'command', identifier)
        conv = self.conversation(tx, owner, value['conversationId'])
        require(value['_frame']['wireRevision'] == 2, 'REMOTE_REVISION_REQUIRED')
        require(value['type'] == 'run.submit' and 'resultRef' not in value and value['status'] not in TERMINAL, 'REMOTE_WITHDRAWAL_TOO_LATE')
        if value['withdrawalState'] == 'none':
            receipt = self.enqueue_v2(tx, owner, conv, 'command.withdraw', dict(body, targetCommandId=identifier, targetConversationSeq=value['conversationSeq']))
            value.update(withdrawalState='requested', withdrawalCommandId=receipt['commandId'])
            self.save(tx, owner, 'command', identifier, value)
        return self.view(owner, 'command', value)

    def expire(self, tx, owner, worker):
        for value in tx.queued_due(owner, worker, self.settings.clock()):
            if value['_frame']['wireRevision'] == 1:
                # Historical R1 facts are reconciled using their original semantics.
                if not value['_dispatch']:
                    super().reject_undispatched(tx, owner, value, 'REMOTE_COMMAND_EXPIRED')
                elif value['deliveryState'] != 'reconciliation_required':
                    value['deliveryState'] = 'reconciliation_required'
                    self.save(tx, owner, 'command', value['commandId'], value)
                continue
            if not value.get('_granted') and seconds(value['deliverBy']) <= self.settings.clock():
                self.delivery_expired(tx, owner, value)

    def delivery_expired(self, tx, owner, value):
        require(not value.get('_granted'), 'REMOTE_EVENT_CONFLICT')
        value.update(status='failed', deliveryState='acknowledged', error=Fault('REMOTE_DELIVERY_EXPIRED').view(), observedAt=self.now())
        self.save(tx, owner, 'command', value['commandId'], value)
        box = tx.get(owner, 'outbox', 'command:' + value['commandId'])
        if box:
            box['done'] = True
            self.save(tx, owner, 'outbox', box['id'], box)
        if 'conversationSeq' in value:
            frame = value['_frame']
            skip = wire.encode(dict(type='conversation.skip', commandId=value['commandId'], conversationId=value['conversationId'], conversationSeq=value['conversationSeq'],
                targetWorkerId=value['targetWorkerId'], expectedWorkerStoreId=frame['expectedWorkerStoreId'], reason='expired_before_dispatch', recordedAt=self.now()), 2)
            self.outbox(tx, owner, skip)
        self.command_event(tx, owner, value)

    def received(self, tx, owner, event):
        value = self.get(tx, owner, 'command', event['commandId'])
        frame = value['_frame']
        require(frame['wireRevision'] == 2 and value['targetWorkerId'] == event['workerId'] and frame['expectedWorkerStoreId'] == event['workerStoreId'] and value['conversationId'] == event['conversationId'], 'REMOTE_TARGET_MISMATCH')
        require(value['_digest'] == event['commandDigest'] and frame['deliverBy'] == event['deliverBy'], 'REMOTE_EVENT_CONFLICT')
        if value.get('_granted') or value['status'] in TERMINAL or value.get('_deleted'):
            return
        received_now = self.settings.clock()
        if received_now >= seconds(value['deliverBy']):
            self.delivery_expired(tx, owner, value)
            return
        require(value['_dispatch'], 'REMOTE_EVENT_CONFLICT')
        value.update(_granted=True, deliveryState='granted')
        self.save(tx, owner, 'command', value['commandId'], value)
        grant = wire.encode(dict(type='command.delivery_granted', commandId=value['commandId'], conversationId=value['conversationId'],
            targetWorkerId=value['targetWorkerId'], expectedWorkerStoreId=event['workerStoreId'], receivedEventId=event['eventId'], commandDigest=value['_digest'], deliverBy=event['deliverBy'], grantedAt=stamp(received_now)), 2)
        self.save(tx, owner, 'outbox', 'grant:' + value['commandId'], dict(id='grant:' + value['commandId'], _frame=grant, done=False, dispatching=False, conversationId=value['conversationId']))
        self.command_event(tx, owner, value)
        self.notify(tx, owner, event['workerId'])

    def reject_undispatched(self, tx, owner, value, code):
        if value['_frame']['wireRevision'] == 1:
            return super().reject_undispatched(tx, owner, value, code)
        if not value.get('_granted'):
            self.delivery_expired(tx, owner, value)

    def revoke(self, tx, owner, worker):
        result = super().revoke(tx, owner, worker)
        for store in tx.sync_stores(owner, worker):
            self.erase_replica(tx, owner, worker, store, permanent=True)
            self.replica.browser_event(tx, owner, dict(type='store.reset', workerId=worker, workerStoreId=store))
        return result

    def erase_replica(self, tx, owner, worker, store, conversation=None, permanent=False, through_generation=None):
        for value in tx.list(owner, 'command', worker=worker, store=store):
            frame = value['_frame']
            if conversation is not None and frame.get('localConversationId') != conversation:
                continue
            if frame['wireRevision'] == 2 and not value.get('_granted') and value['status'] == 'queued':
                code = 'REMOTE_DEVICE_REVOKED' if permanent and conversation is None else 'REMOTE_SYNC_DISABLED'
                value.update(status='rejected', error=Fault(code).view(), observedAt=self.now())
                self.save(tx, owner, 'command', value['commandId'], value)
                if 'conversationSeq' in value:
                    # No execution grant ever existed: retire the remote order slot
                    # even if a provisional transport write may have happened.
                    skip = wire.encode(dict(type='conversation.skip', commandId=value['commandId'], conversationId=value['conversationId'], conversationSeq=value['conversationSeq'], targetWorkerId=worker, expectedWorkerStoreId=store, reason='withdrawn_before_dispatch', recordedAt=self.now()), 2)
                    self.outbox(tx, owner, skip)
        tx.sync_erase(owner, worker, store, conversation, permanent, through_generation)

    def token(self, owner, scope, data, expires=None):
        claims = dict(scope=scope, data=data, expires=expires or int(self.settings.clock() + self.settings.cursor_ttl))
        payload = base64.urlsafe_b64encode(canonical(claims).encode()).decode().rstrip('=')
        return 'p2.' + payload + '.' + self.security.mac('page-v2', canonical(dict(claims, owner=owner)))

    def untoken(self, owner, scope, token):
        try:
            require(len(token) <= 2048, 'REMOTE_CURSOR_INVALID')
            version, payload, signature = token.split('.')
            require(version == 'p2', 'REMOTE_CURSOR_INVALID')
            claims = json.loads(base64.b64decode(payload + '=' * (-len(payload) % 4), altchars=b'-_', validate=True))
            require(claims['scope'] == scope and hmac.compare_digest(signature, self.security.mac('page-v2', canonical(dict(claims, owner=owner)))), 'REMOTE_CURSOR_INVALID')
            require(claims['expires'] > self.settings.clock(), 'REMOTE_CURSOR_EXPIRED')
            return claims
        except Fault:
            raise
        except (ValueError, TypeError, KeyError):
            raise Fault('REMOTE_CURSOR_INVALID') from None

    def messages(self, tx, owner, identifier, before, limit):
        conv = self.browser_get(tx, owner, 'conversation', identifier)
        scope = digest(['messages', conv['targetWorkerId'], conv['workerStoreId'], identifier])
        if before:
            claims = self.untoken(owner, scope, before); data = claims['data']
            require(data.get('generation') == conv.get('_generation', 0), 'REMOTE_CURSOR_EXPIRED')
            require(data['cut'] <= tx.sync_message_high(owner, identifier), 'REMOTE_CURSOR_EXPIRED')
        else:
            high = tx.sync_message_high(owner, identifier)
            data = dict(cut=high, before=high + 1, generation=conv.get('_generation', 0))
            claims = dict(expires=int(self.settings.clock() + self.settings.cursor_ttl))
        items, has_more = tx.sync_message_page(owner, identifier, data['cut'], data['before'], limit)
        result = dict(items=[self.view(owner, 'message', row[1]) for row in items], hasMore=has_more,
                      snapshotCursor=self.token(owner, scope, dict(cut=data['cut'], before=data['cut'] + 1, generation=data['generation']), claims['expires']))
        if result['hasMore']:
            result['before'] = self.token(owner, scope, dict(cut=data['cut'], before=items[-1][0], generation=data['generation']), claims['expires'])
        return result

    def conversations(self, tx, owner, cursor, limit, worker=None, workspace=None):
        if worker:
            self.get(tx, owner, 'device', worker)
        scope = digest(['conversations', worker, workspace])
        values = [v for v in tx.list(owner, 'conversation', worker=worker) if v.get('visibility', 'both') != 'pc_only' and (not workspace or v['workspaceId'] == workspace)]
        def key(v):
            return [v.get('lastActivityAt', v['updatedAt']), v['conversationId']]
        values.sort(key=key, reverse=True)
        claims = self.untoken(owner, scope, cursor) if cursor else dict(data=dict(cut=key(values[0]) if values else ['', ''], before=None), expires=int(self.settings.clock() + self.settings.cursor_ttl))
        data = claims['data']
        values = [v for v in values if key(v) <= data['cut'] and (data['before'] is None or key(v) < data['before'])]
        result = dict(items=[self.view(owner, 'conversation', v) for v in values[:limit]], hasMore=len(values) > limit)
        if result['hasMore']:
            result['nextCursor'] = self.token(owner, scope, dict(cut=data['cut'], before=key(values[limit - 1])), claims['expires'])
        return result

    def events(self, tx, owner, token, limit):
        if not token:
            return super().events(tx, owner, token, limit)
        position = self.position(tx, owner, 'events', token)
        items = []; size = 0; budget_full = False
        while len(items) < limit + 1:
            rows = tx.browser_after(owner, position, limit + 1)
            if not rows:
                break
            for index, body in rows:
                payload = body.get('payload', {})
                conversation = body.get('conversationId') or payload.get('conversationId')
                command_event = body['type'] == 'command.updated' or (body['type'] == 'worker.event' and payload.get('type', '').startswith('command.'))
                allowed = body['type'] in {'conversation.deleted', 'store.reset'} or conversation is None or self.replica.visible(tx, owner, conversation) or (command_event and self.command_visible(tx, owner, conversation))
                if allowed:
                    added = len(canonical(body).encode())
                    if items and size + added > 33554432:
                        budget_full = True
                        break
                    items.append((index, body))
                    size += added
                    if len(items) > limit:
                        break
                position = index
            if len(items) > limit or budget_full:
                break
        has_more = len(items) > limit or budget_full
        end = items[min(limit, len(items))-1][0] if has_more else position
        return dict(items=[dict(body, serverCursor=self.cursor(tx, owner, 'events', index)) for index, body in items[:limit]],
                    hasMore=has_more, nextServerCursor=self.cursor(tx, owner, 'events', end))

    def snapshot(self, tx, owner, identifier):
        conv = self.browser_get(tx, owner, 'conversation', identifier)
        value = dict(conversation=self.view(owner, 'conversation', conv), serverCursor=self.cursor(tx, owner, 'events', tx.browser_tail(owner)), observedAt=self.now(), hasMore=False)
        for plural, kind in [('runs', 'run'), ('commands', 'command')]:
            rows = tx.list(owner, kind, parent=identifier, limit=101)
            value[plural] = [self.view(owner, kind, row) for row in rows[:100]]
            value['hasMore'] |= len(rows) > 100
        approvals = tx.pending_approvals(owner, conv['targetWorkerId'], conv['workerStoreId'], identifier, value['observedAt'])
        value['approvals'] = [self.view(owner, 'approval', row) for row in approvals[:100]]
        value['hasMore'] |= len(approvals) > 100
        page = self.messages(tx, owner, identifier, None, 100)
        value['messages'] = page['items']; value['hasMore'] |= page['hasMore']
        return value
