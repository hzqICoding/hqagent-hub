"""Image verification is an operator-run, version/model/transport-bound fact."""
import hashlib
import json
from pathlib import Path
from protocol.generated.python import ImageInputCapability, AttachmentTargetCapabilities
from core.errors import HubError
from runtime.remote.security import CredentialVault
from storage.local_chat import now
TRANSPORTS = {'claude': 'stream-json-image-v1', 'codex': 'app-server-localImage-v1'}
REQUIRED_PROBES = frozenset({'new', 'resume', 'mixed-five', 'cancel', 'error'})

class VerificationStore:

    def __init__(self, root):
        self.root = Path(root) / 'image-verification'

    def key(self, agent, model):
        return hashlib.sha256(json.dumps([agent, model]).encode()).hexdigest() + '.json'

    def record(self, agent, version, model, outcomes, mime_types, *, diagnostics=None):
        self.root.mkdir(parents=True, exist_ok=True)
        result = dict(agent=agent, version=version, model=model, transport=TRANSPORTS[agent], observedAt=now(), passed=REQUIRED_PROBES <= outcomes.keys() and all(outcomes.values()), probes=outcomes, mimeTypes=mime_types)
        if diagnostics is not None:
            result['diagnostics'] = diagnostics
        CredentialVault.atomic_write(self.root / self.key(agent, model), json.dumps(result).encode())
        return result

    def capability(self, agent, version, model=None):
        valid = None
        try:
            record = json.loads((self.root / self.key(agent, model)).read_text(encoding='utf-8'))
            if record['version'] == version and record['model'] == model and (record['transport'] == TRANSPORTS.get(agent)) and record['passed'] and (REQUIRED_PROBES <= record['probes'].keys()) and all(record['probes'].values()):
                valid = record
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return ImageInputCapability(support='supported' if valid else 'unknown', cliEntry='supported' if valid else 'unknown', runtimeImplemented=agent in TRANSPORTS, verified=bool(valid), mimeTypes=valid['mimeTypes'] if valid else [], maxBytes=10000000 if valid else 0, **{} if valid else {'reason': '当前CLI版本/模型/传输尚未完成本机图片验证'})

class ImageCapabilities:

    def __init__(self, worker):
        self.worker = worker
        self.store = VerificationStore(worker.repo.witness.parent.parent)
        self.agents = {}
        self.values = {}

    async def refresh(self):
        ports = self.worker.bridge.chat.ports
        try:
            values = await ports.agents.list_agents()
            detect = getattr(type(ports.agents), 'detect', None)
            if detect is not None:
                current = {}
                for agent in values:
                    kind = str(agent.adapter_id)
                    if kind not in current:
                        descriptor = await ports.agents.detect(kind)
                        current[kind] = getattr(descriptor, 'detected_version', '') or ''
                values = [agent.model_copy(update={'version': current[str(agent.adapter_id)]}) for agent in values]
            self.agents = {a.id: a for a in values}
        except Exception:
            self.agents = {}
        self.values = {}
        for scene in self.worker.bridge.chat.repository.scenes():
            roles = []
            for role in scene.roles:
                if not role.enabled:
                    continue
                agent = self.agents.get(role.agent_instance_id)
                kind = str(agent.adapter_id) if agent else ''
                cap = self.store.capability(kind, agent.version, role.model_id_) if agent else self.store.capability('', '')
                roles.append(dict(roleId=str(role.role_id), agentId=role.agent_instance_id or 'unresolved', imageInput=cap.model_dump(mode='json', by_alias=True, exclude_none=True)))
            self.values[scene.id] = roles

    def native(self, kind):
        agents = [a for a in self.agents.values() if str(a.adapter_id) == kind]
        caps = [self.store.capability(kind, a.version) for a in agents]
        return dict(agentType=kind, imageInput=(caps[0] if len(caps) == 1 else self.store.capability('', '')).model_dump(mode='json', by_alias=True, exclude_none=True))

    def target(self, conversation):
        view = self.worker.bridge.chat.repository.conversation(conversation)
        native = str(view.conversation_kind) == 'native'
        return AttachmentTargetCapabilities(conversationKind='native' if native else 'scenario', capabilityRevision=self.worker.projector.capability_revision(), roles=[] if native else self.values.get(str(view.scene_id), []), **{'native': self.native(str(view.agent_type))} if native else {})

    def require(self, conversation, manifests):
        images = [m for m in manifests if m['kind'] == 'image']
        if not images:
            return
        target = self.target(conversation)
        caps = [target.native.image_input] if target.native else [r.image_input for r in target.roles]
        if not caps or any((c.support != 'supported' or not c.verified or (not c.runtime_implemented) or (c.cli_entry != 'supported') or any((m['mimeType'] not in c.mime_types or m['sizeBytes'] > c.max_bytes for m in images)) for c in caps)):
            raise HubError('AGENT_IMAGE_UNSUPPORTED', '目标Agent图片输入未验证或能力不匹配')
