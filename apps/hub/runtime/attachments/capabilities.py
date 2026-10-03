"""Image verification is an operator-run, version/model/transport-bound fact."""
import hashlib
import asyncio
import json
from pathlib import Path
from protocol.generated.python import ImageInputCapability, AttachmentTargetCapabilities
from core.errors import HubError
from runtime.remote.security import CredentialVault
from storage.local_chat import now, uid
from runtime.attachments.verification_target import target_for, TRANSPORTS
from orchestrator.domain import ProfileSnapshot, ResolutionRequest, ResolutionGap
from runtime.execution_selection import scene_execution, native_execution_candidate
from storage.idempotency import request_hash
REQUIRED_PROBES = frozenset({'new', 'resume', 'mixed-five', 'cancel', 'error'})

class VerificationStore:

    def __init__(self, root):
        self.root = Path(root) / 'image-verification'

    def key(self, agent, model):
        return hashlib.sha256(json.dumps([agent, model]).encode()).hexdigest() + '.json'

    def record(self, agent, version, model, outcomes, mime_types, *, diagnostics=None, target=None, job_id=None, cleanup_confirmed=False, completed=True):
        self.root.mkdir(parents=True, exist_ok=True)
        result = dict(agent=agent, version=version, model=model, transport=TRANSPORTS[agent], observedAt=now(), passed=REQUIRED_PROBES <= outcomes.keys() and all(outcomes.values()), probes=outcomes, mimeTypes=mime_types)
        result['passed'] = result['passed'] and completed
        if diagnostics is not None:
            result['diagnostics'] = diagnostics
        if target is not None:
            result.update(target=target, recordId=uid('verification'), jobId=job_id,
                          cleanupConfirmed=cleanup_confirmed)
        else:
            result['legacy_unbound'] = True
        CredentialVault.atomic_write(self.root / self.key(target['agentId'] if target else agent, model), json.dumps(result).encode())
        return result

    def latest(self, agent_id, kind, model):
        for identifier in (agent_id, kind):
            try:
                return json.loads((self.root / self.key(identifier, model)).read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
        return None

    def capability(self, agent, version, model=None, *, target=None):
        valid = None
        try:
            record = self.latest(target['agentId'] if target else agent, agent, model)
            if target and record and record.get('target') == target and record.get('cleanupConfirmed') and record['version'] == version and record['model'] == model and (record['transport'] == TRANSPORTS.get(agent)) and record['passed'] and (REQUIRED_PROBES <= record['probes'].keys()) and all(record['probes'].values()):
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
        self.candidates = ()
        self.fingerprint = ''
        self.lock = asyncio.Lock()

    async def refresh(self):
        async with self.lock:
            await self._refresh()

    def unknown(self, reason, kind=''):
        return ImageInputCapability(support='unknown', cliEntry='unknown',
            runtimeImplemented=kind in TRANSPORTS, verified=False, mimeTypes=[], maxBytes=0, reason=reason)

    def selected(self, candidate, model):
        view = self.agents.get(candidate.instance_id)
        if view is None or str(view.status) != 'ready' or str(view.adapter_id) != str(candidate.adapter_id):
            return self.unknown('解析到的Agent没有一致且可用的当前状态', str(candidate.adapter_id))
        adapter = self.worker.bridge.chat.ports.tasks.directory.adapter_for(candidate.instance_id)
        target = target_for(candidate.instance_id, str(candidate.adapter_id), view.version, model, adapter)
        return self.store.capability(str(candidate.adapter_id), view.version, model, target=target)

    async def _refresh(self):
        ports = self.worker.bridge.chat.ports
        try:
            values = await ports.agents.list_agents()
            self.agents = {a.id: a for a in values}
            self.candidates = tuple(await ports.tasks.directory.list_candidates())
        except Exception:
            self.agents = {}
            self.candidates = ()
        resolved = {}
        self.usages = {}
        for scene in self.worker.bridge.chat.repository.scenes():
            roles = []
            profile, overrides, options = scene_execution(scene, 'preview:' + str(scene.id))
            snapshot = ProfileSnapshot.from_view(profile)
            planner = None
            for role in scene.roles:
                if not role.enabled:
                    continue
                identifier = 'unresolved'
                try:
                    candidates = self.candidates
                    override = overrides.get(role.role_id)
                    if str(scene.review_mode) == 'original_planner' and str(role.role_id) == 'reviewer':
                        if planner is None:
                            raise HubError('AGENT_IMAGE_UNSUPPORTED', '原规划验收的Agent尚不能确定')
                        override = planner
                        candidates = tuple(a for a in candidates if a.instance_id == planner)
                    decision, _, _ = ports.tasks.runtime.resolve_agent(ResolutionRequest(
                        role_id=str(role.role_id), agents=candidates, task_override_agent_id=override,
                        global_profile=snapshot, requires_approval=None))
                    if isinstance(decision, ResolutionGap):
                        cap = self.unknown(decision.reason)
                    else:
                        identifier = decision.agent.instance_id
                        model = options[role.role_id]['modelId']
                        self.usages.setdefault((identifier, model), []).append(dict(sceneId=scene.id, roleId=str(role.role_id)))
                        cap = self.selected(decision.agent, model)
                        if str(role.role_id) == 'planner':
                            planner = identifier
                except Exception:
                    cap = self.unknown('当前角色执行目标无法确定')
                roles.append(dict(roleId=str(role.role_id), agentId=identifier,
                    imageInput=cap.model_dump(mode='json', by_alias=True, exclude_none=True)))
            resolved[scene.id] = roles
        self.values = resolved
        # Only the digest is stored locally; model/configuration fields do not
        # become new catalog DTO fields. Unknown-to-unknown version changes still
        # invalidate the old capability revision.
        self.fingerprint = request_hash({
            'agents': sorted((a.id, a.version, str(a.status)) for a in self.agents.values()),
            'nativeBindings': sorted((p.agent_type, p.runtime_id) for p in self.worker.native.plugins),
        })
        if self.worker.repo.get('identity').get('wireRevision', 1) >= 4 and self.worker.repo.get('link')['view']['state'] == 'paired':
            await self.worker.projector.catalog()

    def native(self, kind, runtime_id=None):
        bindings = {p.runtime_id for p in self.worker.native.plugins if p.agent_type == kind}
        cap = self.unknown('原生Runtime绑定缺失或存在多个候选', kind)
        if runtime_id is None and len(bindings) == 1:
            runtime_id = next(iter(bindings))
        if runtime_id in bindings:
            try:
                candidate = native_execution_candidate(self.candidates, runtime_id, self.worker.bridge.chat.ports.tasks.runtime)
                cap = self.selected(candidate, None) if str(candidate.adapter_id) == kind else self.unknown('绑定的原生Runtime类型不一致', kind)
            except HubError as error:
                cap = self.unknown(error.message, kind)
        return dict(agentType=kind, imageInput=cap.model_dump(mode='json', by_alias=True, exclude_none=True))

    def target(self, conversation):
        view = self.worker.bridge.chat.repository.conversation(conversation)
        native = str(view.conversation_kind) == 'native'
        runtime_id = self.worker.native.row(conversation, conversation=True)['runtime_id'] if native else None
        return AttachmentTargetCapabilities(conversationKind='native' if native else 'scenario', capabilityRevision=self.worker.projector.capability_revision(), roles=[] if native else self.values.get(str(view.scene_id), []), **{'native': self.native(str(view.agent_type), runtime_id)} if native else {})

    def require(self, conversation, manifests):
        images = [m for m in manifests if m['kind'] == 'image']
        if not images:
            return
        target = self.target(conversation)
        caps = [target.native.image_input] if target.native else [r.image_input for r in target.roles]
        if not caps or any((c.support != 'supported' or not c.verified or (not c.runtime_implemented) or (c.cli_entry != 'supported') or any((m['mimeType'] not in c.mime_types or m['sizeBytes'] > c.max_bytes for m in images)) for c in caps)):
            raise HubError('AGENT_IMAGE_UNSUPPORTED', '目标Agent图片输入未验证或能力不匹配')
