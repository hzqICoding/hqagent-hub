"""Revision 3 reliable metadata and resource execution projection."""
from .common import Fault, digest, require, seconds, validated
from .native import RESOURCES
from .service import TERMINAL


class NativeEvents:
    def __init__(self, service): self.s = service

    def catalog(self, tx, owner, event):
        worker, store, payload = event['workerId'], event['workerStoreId'], event['payload']
        if event['wireRevision'] == 5:
            runtimes = {r['agentId']:r for r in payload.get('runtimes',[])}
            require(len(runtimes)==len(payload.get('runtimes',[])), 'REMOTE_SYNC_CONFLICT')
            bindings = list(payload.get('nativeImageCapabilities',[]))
            for scene in payload['scenes']:
                bindings.extend(scene.get('roleImageCapabilities',[]))
            for binding in bindings:
                runtime = runtimes.get(binding.get('agentId'))
                if runtime and binding.get('agentType'):
                    require(runtime['agentType']==binding['agentType'],'REMOTE_SYNC_CONFLICT')
                if binding.get('agentType')=='pi':
                    require(runtime is not None and runtime['agentType']=='pi','REMOTE_SYNC_CONFLICT')
                    if 'modelId' in binding:
                        validated('PiModelSelection',dict(modelId=binding['modelId']))
            for runtime in runtimes.values():
                guard=runtime.get('guard',{})
                if guard.get('status')=='ready':
                    require(guard.get('isolation')=='hub_extension_only' and guard.get('reasons')==[], 'REMOTE_SYNC_CONFLICT')
        require('authorizedRoots' in payload, 'REMOTE_SYNC_CONFLICT')
        require(len({r['rootId'] for r in payload['authorizedRoots']}) == len(payload['authorizedRoots']), 'REMOTE_SYNC_CONFLICT')
        before = tx.get(owner, 'catalog', worker)
        mapped = dict(payload, workspaces=[dict(w, workspaceId=self.s.workspace_public(tx, owner, worker, store, w['workspaceId'])) for w in payload['workspaces']])
        if before and before['workerStoreId'] == store:
            require(payload['capabilityRevision'] >= before['capabilityRevision'], 'REMOTE_EVENT_CONFLICT')
            if payload['capabilityRevision'] == before['capabilityRevision']:
                require(mapped == before, 'REMOTE_EVENT_CONFLICT')
        allowed = {w['workspaceId'] for w in mapped['workspaces']}
        tx.remove_native_workspaces(owner,worker,store,{w['workspaceId'] for w in payload['workspaces']},event['seq'])
        for index in tx.list(owner, 'native-index', worker=worker, store=store):
            if index['workspaceId'] not in allowed:
                tx.native_fence(owner, worker, store, index['_localId'], index['_generation'], event['seq'])
                tx.erase_native(owner, worker, store, index['_localId'])
        tx.after_commit(('query-catalog',owner,worker), lambda: self.recheck_pending(owner, worker))
        return mapped

    def recheck_pending(self, owner, worker):
        for item in list(self.s.queries.pending.values()):
            plan = item['plan']
            if plan.owner != owner or plan.connection.worker != worker: continue
            try:
                with self.s.repo.transaction() as tx: self.s.recheck_query(tx, plan)
            except Fault as exc:
                item['parts'].clear()
                if not item['future'].done(): item['future'].set_exception(exc)

    def delete(self, tx, owner, event):
        worker, store, local = event['workerId'], event['workerStoreId'], event['nativeSessionId']
        public, _ = tx.sync_id(owner, worker, store, 'native-index', local, '')
        tx.native_fence(owner, worker, store, local, event['syncGeneration'], event['seq'])
        tx.erase_native(owner, worker, store, local, event['syncGeneration'])
        fence = dict(eventId=event['eventId'], seq=event['seq'], generation=event['syncGeneration'], type=event['type'], conversation=None, nativeSessionId=local)
        tx.put(owner, 'deletion-fence', digest([worker,store,event['eventId']]), fence, worker=worker, store=store)
        tx.after_commit(('query-native',owner,public), lambda: self.s.queries.invalidate(owner, worker, store, 'NOT_FOUND', public))

    def apply(self, tx, owner, event):
        kind = event['type']; worker, store = event['workerId'], event['workerStoreId']
        if kind == 'native.index.deleted': return
        if kind == 'native.closure.confirmed':
            command = self.s.get(tx, owner, 'command', event['commandId'])
            frame = command['_frame']; payload = frame.get('payload', {})
            require(frame['wireRevision'] >= 3 and command['targetWorkerId'] == worker and frame['expectedWorkerStoreId'] == store, 'REMOTE_TARGET_MISMATCH')
            require(payload.get('nativeSessionId', command.get('_nativeId')) == event['nativeSessionId'] and payload.get('confirmation', payload.get('nativeConfirmation', command.get('_closureConfirmation'))) == event['confirmation'], 'REMOTE_EVENT_CONFLICT')
            tx.put(owner, 'native-confirmation', event['confirmation']['confirmationId'], dict(commandId=event['commandId'], nativeSessionId=event['nativeSessionId'], confirmation=event['confirmation']), worker=worker, store=store)
            return
        state = self.s.replica.generation(tx, owner, event)
        if state is None: return
        p = event['payload']; local = p['nativeSessionId']
        fence = tx.get(owner, 'native-fence', digest([worker,store,local]))
        if fence and (event['syncGeneration'],event['seq']) <= (fence['generation'],fence['seq']): return
        catalog = self.s.get(tx, owner, 'catalog', worker)
        workspace = self.s.workspace_public(tx, owner, worker, store, p['workspaceId'])
        require(catalog['workerStoreId'] == store and any(w['workspaceId'] == workspace for w in catalog['workspaces']), 'NOT_FOUND')
        public, _ = tx.sync_id(owner, worker, store, 'native-index', local, '')
        previous = tx.get(owner, 'native-index', public)
        if previous and previous['indexVersion'] >= p['indexVersion']:
            require(previous['indexVersion'] > p['indexVersion'] or previous['_hash'] == digest(p), 'REMOTE_SYNC_CONFLICT')
            return
        require(p['format']['status'] != 'readable' or bool(p['format'].get('readerId')), 'REMOTE_SYNC_CONFLICT')
        require(p['format']['status'] != 'unsupported' or bool(p['format'].get('reason')), 'REMOTE_SYNC_CONFLICT')
        if p['agentType']=='pi':
            require(event['wireRevision']==5,'REMOTE_REVISION_REQUIRED')
            if p['format']['status']=='readable':
                require(p['format'].get('readerId')=='pi.jsonl.v3.tree' and 'pi' in p['format'],'REMOTE_SYNC_CONFLICT')
            else:
                require('unsupportedReason' in p['format'],'REMOTE_SYNC_CONFLICT')
        value = dict(p, nativeSessionId=public, workspaceId=workspace, workerId=worker, _store=store, _localId=local, _generation=event['syncGeneration'], _hash=digest(p))
        self.s.save(tx, owner, 'native-index', public, value)

    def stale_index(self, tx, owner, event):
        worker,store,local=event['workerId'],event['workerStoreId'],event['payload']['nativeSessionId']
        state=self.s.replica.state(tx,owner,worker,store)
        fence=tx.get(owner,'native-fence',digest([worker,store,local]))
        return event['syncGeneration'] <= state['closedGeneration'] or event['syncGeneration'] < state['generation'] or bool(fence and (event['syncGeneration'],event['seq']) <= (fence['generation'],fence['seq']))

    def conversation(self, tx, owner, event):
        p = dict(event['payload']); worker, store = event['workerId'],event['workerStoreId']
        p['workspaceId'] = self.s.workspace_public(tx, owner, worker, store, p['workspaceId'])
        if p.get('conversationKind', 'scenario') == 'native':
            require('sceneId' not in p and 'sceneVersion' not in p and 'agentType' in p and 'nativeSessionId' in p, 'REMOTE_SYNC_CONFLICT')
            p['_nativeLocal'] = p['nativeSessionId']
            p['nativeSessionId'] = tx.sync_id(owner, worker, store, 'native-index', p['nativeSessionId'], '')[0]
        else:
            require('sceneId' in p and 'sceneVersion' in p and 'nativeSessionId' not in p and 'agentType' not in p, 'REMOTE_SYNC_CONFLICT')
        return dict(event, payload=p)

    def resource(self, tx, owner, event, command):
        frame = command['_frame']; kind = event['type']; worker, store = event['workerId'],event['workerStoreId']
        require(frame['wireRevision'] == event['wireRevision'] and frame['wireRevision'] >= 3 and command['type'] in RESOURCES and
                command['targetWorkerId'] == worker and frame['expectedWorkerStoreId'] == store and
                'conversationId' not in event and 'resultRef' not in event, 'REMOTE_TARGET_MISMATCH')
        if command['status'] in TERMINAL:
            require(not command.get('_granted') and kind == 'command.rejected', 'REMOTE_EVENT_CONFLICT')
            return
        if kind != 'command.rejected': require(command.get('_granted'), 'REMOTE_EVENT_CONFLICT')
        if kind == 'command.accepted':
            require(command['status'] == 'queued', 'REMOTE_EVENT_CONFLICT'); command['status'] = 'accepted'
        elif kind == 'command.rejected':
            require(command['status'] == 'queued', 'REMOTE_EVENT_CONFLICT'); command['status'] = 'rejected'
        else:
            require(command['status'] == 'accepted' and kind in {'command.completed','command.failed'}, 'REMOTE_EVENT_CONFLICT')
            command['status'] = 'completed' if kind == 'command.completed' else 'failed'
        if kind == 'command.completed':
            ref, control = event.get('resourceRef',{}), event.get('controlResult',{})
            required = {'workspaceId','conversationId','nativeSessionId'} if command['type'] == 'native.import' else {'workspaceId'}
            require(set(ref) == required and event['resultStatus'] == 'confirmed' and control.get('outcome') == 'confirmed' and control.get('evidence') == 'metadata_committed', 'REMOTE_EVENT_CONFLICT')
            mapped = dict(workspaceId=self.s.workspace_public(tx, owner, worker, store, ref['workspaceId']))
            if command['type'] == 'native.import':
                require(ref['nativeSessionId'] == command['_nativeId'], 'REMOTE_TARGET_MISMATCH')
                mapped.update(conversationId=tx.sync_id(owner, worker, store, 'conversation', ref['conversationId'],ref['conversationId'])[0], nativeSessionId=tx.sync_id(owner, worker, store, 'native-index',ref['nativeSessionId'],'')[0])
            command['resourceRef'] = mapped
        for key in ('controlResult','resultStatus','error'):
            if key in event: command[key] = event[key]
        if command.get('_deleted'):
            if 'controlResult' in command: command['controlResult']=dict(command['controlResult'],reason='Content removed')
            if 'error' in command: command['error']=dict(command['error'],message=command['error']['code'])
        command.update(deliveryState='acknowledged',observedAt=self.s.now())
        self.s.save(tx, owner,'command',command['commandId'],command)
        for prefix in ('command:','grant:'):
            box=tx.get(owner,'outbox',prefix+command['commandId'])
            if box:
                box['done']=True; self.s.save(tx,owner,'outbox',box['id'],box)
        self.s.command_event(tx,owner,command)
