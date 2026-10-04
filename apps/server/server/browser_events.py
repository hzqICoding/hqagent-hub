"""0.11.1 HTTP-only projections. Never pass these copies back to Worker codecs."""
from .common import validated, require
from .client_features import legacy_shape

DIAGNOSTICS = ('type', 'eventId', 'workerId', 'workerStoreId', 'workerEpoch', 'seq', 'occurredAt')
APPROVAL_FIELDS = ('approvalId', 'resultRef', 'action', 'targetSummary', 'riskLevel', 'status',
                   'requestedAt', 'expiresAt', 'remoteApprovalAllowed', 'workerPolicyRevision', 'denialCode')
RUN_FIELDS = ('runId', 'conversationId', 'executionTaskId', 'status', 'observedAt', 'summary', 'parentExecutionTaskId')
CATALOG_FIELDS = ('workerId', 'workerStoreId', 'capabilityRevision', 'observedAt', 'workspaces', 'scenes', 'remotelyBlockedActions')


def fields(value, names):
    return {key: value[key] for key in names if key in value}


class BrowserEvents:
    def __init__(self, service):
        self.s = service

    def emit(self, tx, owner, event, frame, *, pi=False, conversation=None, model='RemoteBrowserV2WorkerEvent'):
        record = dict(type='worker.event', recordedAt=self.s.now(), payload=frame)
        record.update(_worker=event['workerId'], _store=event['workerStoreId'])
        if pi:
            record['_pi'] = True
        if conversation:
            record['_conversation'] = conversation
        try:
            # Validation placeholder is not persisted; the real cursor is minted
            # only on a subsequent authorized, feature-scoped read.
            validated(model, dict(type='worker.event', recordedAt=record['recordedAt'],
                                  payload=frame, serverCursor='projection_validation_only'))
        except ValueError:
            record.update(payload={}, _snapshot_required=True)
        tx.browser_add(owner, record)

    def approval(self, tx, owner, event):
        conv = self.s.get(tx, owner, 'conversation', event['conversationId'])
        pi = self.s.projection.is_pi(tx, owner, conv)
        if not pi and not self.proven_non_pi(tx, owner, conv):
            # Missing binding evidence is not proof of an old-client-safe source.
            # Conservatively gate its historical conversation, never relabel pi.
            conv = dict(conv, _pi=True)
            self.s.save(tx, owner, 'conversation', conv['conversationId'], conv)
            pi = True
        frame = dict(fields(event, DIAGNOSTICS), conversationId=event['conversationId'], wireRevision=5 if pi else 2)
        payload = fields(event['payload'], APPROVAL_FIELDS)
        denial = payload.get('denialCode')
        require(not denial or not payload['remoteApprovalAllowed'], 'REMOTE_EVENT_CONFLICT')
        if denial and not pi:
            try:
                validated('RemoteWire2ErrorCode', denial)
            except ValueError:
                payload['denialCode'] = 'REMOTE_APPROVAL_FORBIDDEN'
        frame['payload'] = payload
        self.emit(tx, owner, event, frame, pi=pi, conversation=event['conversationId'],
                  model='RemoteBrowserPiApprovalEvent' if pi else 'RemoteBrowserLegacyApprovalEvent')

    def proven_non_pi(self, tx, owner, conv):
        if conv.get('conversationKind', 'scenario') == 'native':
            return conv.get('agentType') in {'claude', 'codex'}
        catalog = tx.get(owner, 'catalog', conv['targetWorkerId']) or {}
        scene = next((s for s in catalog.get('scenes', []) if s['sceneId'] == conv.get('sceneId')), {})
        types = {r['agentId']: r['agentType'] for r in catalog.get('runtimes', [])}
        roles = scene.get('roleImageCapabilities', [])
        return bool(roles) and all(r.get('agentType', types.get(r['agentId'])) in {'claude', 'codex'} for r in roles)

    def execution(self, tx, owner, event):
        """Only explicitly frozen cases can acquire a browser compatibility tag."""
        conv = self.s.get(tx, owner, 'conversation', event['conversationId'])
        pi = self.s.projection.is_pi(tx, owner, conv)
        frame = dict(fields(event, DIAGNOSTICS), wireRevision=2, conversationId=event['conversationId'])
        if event['type'] == 'run.progress':
            frame.update(fields(event, ('resultRef', 'message')))
        elif event['type'] == 'run.state_changed':
            frame.update(commandId=event['commandId'], payload=fields(event['payload'], RUN_FIELDS))
        elif event['type'] == 'conversation.skip_recorded':
            return  # Internal order reconciliation, not a fabricated execution result.
        else:
            # No safe legacy notification: authorized readers must resnapshot.
            frame = {}
        self.emit(tx, owner, event, frame, pi=pi, conversation=event['conversationId'])

    def sync_run(self, tx, owner, event, value):
        # The frozen browser union lacks sync.run.state. A public conversation
        # update is already emitted by Replica; the explicit fallback additionally
        # ensures legacy clients refresh the authoritative Run/approval snapshot.
        conv = self.s.get(tx, owner, 'conversation', value['conversationId'])
        self.emit(tx, owner, event, {}, pi=self.s.projection.is_pi(tx, owner, conv), conversation=value['conversationId'])

    def legacy_catalog(self, value):
        filtered = dict(value)
        filtered['scenes'] = [scene for scene in value['scenes'] if not self.s.projection.pi_scene(value, scene)]
        if 'nativeImageCapabilities' in value:
            filtered['nativeImageCapabilities'] = [c for c in value['nativeImageCapabilities'] if c['agentType'] != 'pi']
        return legacy_shape(filtered)

    def catalog(self, tx, owner, event, before, current):
        old = self.legacy_catalog(before) if before else None
        new = self.legacy_catalog(current)
        def semantic(value):
            result = {k: v for k, v in (value or {}).items() if k not in {'observedAt', 'capabilityRevision'}}
            for optional in ('nativeImageCapabilities', 'authorizedRoots'):
                if not result.get(optional):
                    result.pop(optional, None)
            return result
        pi_only = before is not None and semantic(old) == semantic(new)
        payload = fields(new, CATALOG_FIELDS)
        payload['scenes'] = [fields(s, ('sceneId', 'name', 'version', 'readOnly')) for s in payload['scenes']]
        frame = dict(fields(event, DIAGNOSTICS), wireRevision=2, payload=payload)
        self.emit(tx, owner, event, frame, pi=pi_only)
