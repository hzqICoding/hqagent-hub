"""R3 admission, public identity mapping and resource command transactions."""
from .common import Fault, canonical, digest, require, stamp, uid, validated
from . import wire

RESOURCES = {'native.import', 'workspace.register'}


class NativeService:
    def r3_ready(self, tx, owner, worker, *, read=False):
        device = self.get(tx, owner, 'device', worker)
        connection = self.ready(tx, owner, worker, device['workerStoreId'], exempt=read)
        require(connection.revision == 3, 'REMOTE_REVISION_REQUIRED')
        return connection

    def workspace_public(self, tx, owner, worker, store, local):
        return tx.sync_id(owner, worker, store, 'workspace', local, '')[0]

    def workspace_local(self, tx, owner, worker, store, public):
        mapping = tx.sync_reverse(owner, 'workspace', public)
        require(mapping and (mapping['worker'], mapping['store']) == (worker, store) and not mapping['deleted'], 'NOT_FOUND')
        catalog = self.get(tx, owner, 'catalog', worker)
        require(catalog['workerStoreId'] == store and any(w['workspaceId'] == public for w in catalog['workspaces']), 'NOT_FOUND')
        return mapping['local']

    def native_get(self, tx, owner, identifier):
        value = self.browser_get(tx, owner, 'native-index', identifier)
        device = self.get(tx, owner, 'device', value['workerId'])
        require(device['workerStoreId'] == value['_store'], 'NOT_FOUND')
        self.workspace_local(tx, owner, value['workerId'], value['_store'], value['workspaceId'])
        return value

    def native_view(self, owner, value):
        return dict({k: v for k, v in value.items() if not k.startswith('_')}, workerOnline=self.online(owner, value['workerId']))

    def native_page(self, tx, owner, worker, query):
        device = self.get(tx, owner, 'device', worker)
        limit = int(query.get('limit', 50)); require(1 <= limit <= 100)
        workspace, agent = query.get('workspaceId'), query.get('agentType')
        require(agent is None or agent in {'claude', 'codex'})
        if workspace:
            self.workspace_local(tx, owner, worker, device['workerStoreId'], workspace)
        scope = digest(['native-index', worker, device['workerStoreId'], workspace, agent])
        rows = [v for v in tx.list(owner, 'native-index', worker=worker, store=device['workerStoreId'])
                if (not workspace or v['workspaceId'] == workspace) and (not agent or v['agentType'] == agent)]
        def order(v): return [v['updatedAt'], v['nativeSessionId']]
        rows.sort(key=order, reverse=True)
        claim = self.untoken(owner, scope, query['cursor']) if query.get('cursor') else dict(data=dict(cut=order(rows[0]) if rows else ['', ''], before=None), expires=int(self.settings.clock()+self.settings.cursor_ttl))
        bounds = claim['data']
        rows = [v for v in rows if order(v) <= bounds['cut'] and (bounds['before'] is None or order(v) < bounds['before'])]
        result = dict(items=[self.native_view(owner, v) for v in rows[:limit]], hasMore=len(rows)>limit)
        if result['hasMore']:
            result['nextCursor'] = self.token(owner, scope, dict(cut=bounds['cut'], before=order(rows[limit-1])), claim['expires'])
        return result

    def root_check(self, tx, owner, worker, body):
        catalog = self.get(tx, owner, 'catalog', worker)
        root = next((r for r in catalog.get('authorizedRoots', []) if r['rootId'] == body['rootId']), None)
        require(root is not None, 'REMOTE_ROOT_NOT_AUTHORIZED')
        require(root['version'] == body['rootVersion'], 'REMOTE_DIRECTORY_CHANGED')

    def closure(self, source, request_id):
        return validated('NativeClosureConfirmation', dict(confirmationId=uid(), confirmedAt=self.now(), requestId=request_id,
                        sourceRevision=source, terminalClosedConfirmed=True))

    def import_native(self, tx, owner, identifier, body, request_id):
        value = self.native_get(tx, owner, identifier)
        connection = self.r3_ready(tx, owner, value['workerId'])
        require(value['format']['status'] == 'readable', 'NATIVE_SESSION_UNSUPPORTED')
        require(body['terminalClosedConfirmed'] is True)
        require(value['indexVersion'] == body['expectedIndexVersion'] and value['sourceRevision'] == body['sourceRevision'], 'NATIVE_SESSION_CHANGED')
        evidence = value['activity']
        require(evidence['processMatch'] != 'present' and evidence['activity'] != 'likely_active' and not evidence['recentlyModified'], 'NATIVE_SESSION_ACTIVE')
        payload = dict(nativeSessionId=value['_localId'], expectedIndexVersion=body['expectedIndexVersion'], sourceRevision=body['sourceRevision'], confirmation=self.closure(body['sourceRevision'], request_id))
        return self.enqueue_resource(tx, owner, connection, 'native.import', payload, request_id)

    def register_workspace(self, tx, owner, worker, body, request_id):
        connection = self.r3_ready(tx, owner, worker)
        self.root_check(tx, owner, worker, body)
        return self.enqueue_resource(tx, owner, connection, 'workspace.register', body, request_id)

    def enqueue_resource(self, tx, owner, connection, kind, payload, request_id):
        identifier = uid(); now = self.now(); deadline = stamp(self.settings.clock()+30)
        frame = wire.command(dict(type=kind, commandId=identifier, targetWorkerId=connection.worker, expectedWorkerStoreId=connection.store,
                                  createdAt=now, expiresAt=deadline, deliverBy=deadline, requestId=request_id, payload=payload), 3)
        receipt = dict(commandId=identifier, targetWorkerId=connection.worker, type=kind, status='queued', deliveryState='queued_online', workerOnline=True, expiresAt=deadline)
        value = dict(receipt, withdrawalState='none', observedAt=now, createdAt=now, deliverBy=deadline,
                     _frame=frame, _digest=digest(frame), _receipt=receipt, _dispatch=False, _granted=False)
        if kind == 'native.import':
            value.update(_nativeId=payload['nativeSessionId'], _closureConfirmation=payload['confirmation'])
        self.save(tx, owner, 'command', identifier, value)
        self.outbox(tx, owner, frame)
        self.command_event(tx, owner, value)
        return receipt

    def native_command_payload(self, tx, owner, frame):
        if self.connections[(owner, frame['targetWorkerId'])].revision != 3:
            return frame
        payload = dict(frame['payload'])
        if 'workspaceId' in payload:
            payload['workspaceId'] = self.workspace_local(tx, owner, frame['targetWorkerId'], frame['expectedWorkerStoreId'], payload['workspaceId'])
        return dict(frame, payload=payload)

    def submit_metadata(self, tx, owner, conv, body):
        if conv.get('conversationKind', 'scenario') != 'native':
            require('nativeConfirmation' not in body)
            return {k: conv[k] for k in ('workspaceId','sceneId','sceneVersion')}
        require(self.connections[(owner, conv['targetWorkerId'])].revision == 3, 'REMOTE_REVISION_REQUIRED')
        require(body['sessionMode'] == 'continue', 'SESSION_NOT_RESUMABLE')
        evidence = conv.get('nativeActivity', {})
        require(evidence.get('processMatch') != 'present' and evidence.get('activity') != 'likely_active', 'NATIVE_SESSION_ACTIVE')
        result = dict(workspaceId=conv['workspaceId'], conversationKind='native', agentType=conv['agentType'], nativeSessionId=conv['_nativeLocal'])
        if 'nativeConfirmation' in body:
            confirm = body['nativeConfirmation']
            require(confirm['terminalClosedConfirmed'] is True)
            require(confirm['sourceRevision'] == conv.get('nativeSourceRevision'), 'NATIVE_SESSION_CHANGED')
            from .http import CONTEXT
            result['nativeConfirmation'] = self.closure(confirm['sourceRevision'], CONTEXT.get()['requestId'])
        else:
            require(evidence.get('activity') == 'closed_confirmed', 'NATIVE_SESSION_ACTIVE')
        return result

    def query_plan(self, tx, owner, operation, path, body, query, key, request_id):
        from .queries import QueryPlan
        if operation == 'native_read':
            value = self.native_get(tx, owner, path['nativeSessionId'])
            connection = self.r3_ready(tx, owner, value['workerId'], read=True)
            require(value['format']['status'] == 'readable', 'NATIVE_SESSION_UNSUPPORTED')
            payload = dict(nativeSessionId=value['_localId'], limit=int(query.get('limit', 50)))
            if 'before' in query: payload['before'] = query['before']
            validated('NativeReadInput', payload)
            return QueryPlan(owner, connection, 'native.messages', payload, request_id, value['nativeSessionId'])
        connection = self.r3_ready(tx, owner, path['workerId'])
        self.root_check(tx, owner, connection.worker, body)
        identifier = self.security.mac('directory-intent', connection.worker+':'+key)
        content = self.security.mac('directory-body', canonical(body))
        prior = tx.get(owner, 'query-intent', identifier)
        require(not prior or prior['content'] == content, 'IDEMPOTENCY_MISMATCH')
        tx.put(owner, 'query-intent', identifier, dict(content=content), worker=connection.worker, store=connection.store)
        return QueryPlan(owner, connection, 'directory.list', dict(body, limit=body.get('limit',50)), request_id)

    def recheck_query(self, tx, plan):
        connection = self.r3_ready(tx, plan.owner, plan.connection.worker, read=plan.kind=='native.messages')
        require(connection is plan.connection and not connection.closed, 'REMOTE_DEVICE_OFFLINE')
        if plan.kind == 'native.messages':
            value = self.native_get(tx, plan.owner, plan.public_id)
            require(value['_localId'] == plan.payload['nativeSessionId'], 'NOT_FOUND')
        else:
            self.root_check(tx, plan.owner, connection.worker, plan.payload)
