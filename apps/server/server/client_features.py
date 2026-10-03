"""HTTP presentation capabilities; never authority and never Worker negotiation."""
from .common import require


def features():
    from .http import CONTEXT
    context = CONTEXT.get()
    return context.get('_features', ()) if context is not None else ()


def legacy_request():
    from .http import CONTEXT
    context = CONTEXT.get()
    return context is not None and not context.get('_worker') and 'pi-v1' not in features()


def cursor_scope(scope):
    return 'pi-v1:' + scope if 'pi-v1' in features() else scope


def legacy_shape(value):
    """Strip new public fields, without reading or rewriting text content."""
    if isinstance(value, list):
        return [legacy_shape(v) for v in value]
    if not isinstance(value, dict):
        return value
    result = {k: legacy_shape(v) for k, v in value.items()
              if k not in {'runtimes', 'guard', 'modelId', 'transport', 'unsupportedReason', 'pi'} and not k.startswith('_')}
    if 'roleId' in result and 'imageInput' in result:
        result.pop('agentType', None)
    if 'agentType' in result and 'imageInput' in result and 'roleId' not in result:
        result.pop('agentId', None)
    return result


class ClientProjection:
    def __init__(self, service):
        self.s = service

    @staticmethod
    def pi_scene(catalog, scene):
        runtime_types = {r['agentId']: r['agentType'] for r in catalog.get('runtimes', [])}
        return any(r.get('agentType') == 'pi' or runtime_types.get(r['agentId']) == 'pi'
                   for r in scene.get('roleImageCapabilities', []))

    def is_pi(self, tx, owner, value, *, references=True):
        if value.get('_pi') or value.get('agentType') == 'pi':
            return True
        payload = value.get('_frame', {}).get('payload', value)
        if payload.get('agentType') == 'pi':
            return True
        worker = value.get('targetWorkerId', value.get('workerId', value.get('_worker')))
        if worker and 'nativeSessionId' in payload:
            store = value.get('_frame',{}).get('expectedWorkerStoreId',value.get('workerStoreId',value.get('_store')))
            mapping = tx.sync_lookup(owner,worker,store,'native-index',payload['nativeSessionId']) if store else None
            if mapping and tx.get(owner,'pi-resource','native-index:'+mapping['public']):
                return True
        if worker and 'sceneId' in payload:
            catalog = tx.get(owner, 'catalog', worker) or {}
            scene = next((s for s in catalog.get('scenes', []) if s['sceneId'] == payload['sceneId']), {})
            if self.pi_scene(catalog, scene):
                return True
        if not references:
            return False
        conv_id = value.get('conversationId', value.get('_conversation', value.get('resourceRef', {}).get('conversationId')))
        if conv_id:
            if tx.get(owner,'pi-resource','conversation:'+conv_id):
                return True
            conv = tx.get(owner, 'conversation', conv_id) or tx.get(owner, 'create-reservation', conv_id)
            if conv and self.is_pi(tx, owner, conv, references=False):
                return True
        command_id = value.get('commandId')
        if command_id:
            if tx.get(owner,'pi-resource','command:'+command_id):
                return True
            command = tx.get(owner, 'command', command_id)
            if command and command.get('_pi'):
                return True
        return False

    def check_worker_event(self, tx, owner, event):
        if event['wireRevision'] >= 5:
            return
        worker, store = event['workerId'], event['workerStoreId']
        if event['type'] == 'capability.changed':
            previous = tx.get(owner,'catalog',worker) or {}
            for scene in event['payload']['scenes']:
                require(not self.pi_scene(previous,scene),'REMOTE_REVISION_REQUIRED')
        command = tx.get(owner,'command',event['commandId']) if 'commandId' in event else None
        if command:
            require(not self.is_pi(tx,owner,command),'REMOTE_REVISION_REQUIRED')
        local = event.get('payload',{}).get('conversationId',event.get('conversationId'))
        if local and not command:
            mapping = tx.sync_lookup(owner,worker,store,'conversation',local)
            if mapping:
                require(not tx.get(owner,'pi-resource','conversation:'+mapping['public']),'REMOTE_REVISION_REQUIRED')

    def guard_ready(self, tx, owner, conv):
        if not self.is_pi(tx,owner,conv):
            return
        catalog = self.s.get(tx,owner,'catalog',conv['targetWorkerId'])
        runtimes = {r['agentId']:r for r in catalog.get('runtimes',[])}
        if conv.get('agentType') == 'pi':
            candidates = [r for r in runtimes.values() if r['agentType']=='pi']
        else:
            scene = next((s for s in catalog['scenes'] if s['sceneId']==conv['sceneId']),{})
            roles = scene.get('roleImageCapabilities',[])
            candidates = [runtimes.get(r['agentId'],{}) for r in roles
                          if r.get('agentType')=='pi' or runtimes.get(r['agentId'],{}).get('agentType')=='pi']
        require(bool(candidates),'PI_GUARD_UNAVAILABLE')
        for candidate in candidates:
            guard = candidate.get('guard',{})
            require('uncontrolled_extensions' not in guard.get('reasons',[]),'PI_UNCONTROLLED_EXTENSIONS')
            require(guard.get('status')=='ready' and guard.get('isolation')=='hub_extension_only' and guard.get('reasons')==[], 'PI_GUARD_UNAVAILABLE')

    def allowed(self, tx, owner, value):
        return not legacy_request() or not self.is_pi(tx, owner, value)

    def require_visible(self, tx, owner, value):
        require(self.allowed(tx, owner, value), 'NOT_FOUND')

    def catalog(self, tx, owner, value):
        if not legacy_request():
            return value
        result = dict(value)
        result['scenes'] = [scene for scene in value['scenes'] if not self.pi_scene(value, scene)]
        if 'nativeImageCapabilities' in result:
            result['nativeImageCapabilities'] = [c for c in value['nativeImageCapabilities'] if c['agentType'] != 'pi']
        return legacy_shape(result)

    def scene_gate(self, tx, owner, worker, scene_id):
        catalog = self.s.get(tx, owner, 'catalog', worker)
        scene = next((s for s in catalog['scenes'] if s['sceneId'] == scene_id), None)
        require(scene is not None, 'NOT_FOUND')
        pi = self.pi_scene(catalog, scene)
        require(not pi or not legacy_request(), 'NOT_FOUND')
        return pi

    def event_allowed(self, tx, owner, event):
        if not legacy_request():
            return True
        return not event.get('_pi') and not self.is_pi(tx, owner, event) and not self.is_pi(tx, owner, event.get('payload', {}))
