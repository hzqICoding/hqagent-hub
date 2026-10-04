"""PI 1.0.1 RPC adapter; prompts are gated by a pinned exclusive guard."""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import time

from protocol.generated.python import (
    AdapterDescriptor, AdapterFailure, AdapterHealth, AdapterStreamEnd,
    AgentCompletedPayload, AgentProgressPayload, AgentResult, AgentSessionHandle,
    AgentStartedPayload, AgentToolCallPayload, ApprovalRequiredPayload,
    CancelResult, LocalAgentModelsView, PiGuardHandshake, PiGuardDecision, RuntimeGuardView,
)
from adapters.base import AgentAdapter
from adapters.attachment_input import checked_inputs, file_prompt
from adapters.events import AdapterEvent, utc_timestamp
from adapters.failures import parse_agent_result, failure_event
from adapters.path_guard import PathGuard
from adapters.process import ProcessRunner, executable_args, command_environment
from adapters.prompt import build_task_prompt
from adapters.session_registry import AdapterSessionState, STREAM_END
from adapters.pi_rpc import PiRPC
from adapters.pi_guard import (GUARD_PATH, GUARD_SHA256, GUARD_REVISION, TOOLS, READ_TOOLS,
                               blocked_reason, canonical, selector, sha, unique_object, validate_check)
from runtime.instance import SingleInstanceLock


class PiIsolationError(ValueError):
    pass


class PiModelError(ValueError):
    pass


def denied(code='PI_GUARD_UNAVAILABLE', kind='capability_missing', *, message=None):
    messages = {
        'PI_GUARD_UNAVAILABLE': 'PI 安全扩展握手失败或保护状态已变化，未放行执行',
        'PI_UNCONTROLLED_EXTENSIONS': 'PI 扩展隔离或 CLI 版本未通过核验，未启动任务',
        'SESSION_NOT_RESUMABLE': 'PI 会话续接失败，请核对原生会话绑定与执行状态',
        'PI_TOOL_CALL_BLOCKED': 'PI 工具调用不符合当前安全策略，已被拦截',
        'PATH_NOT_ALLOWED': 'PI 工作目录不在授权范围内，未启动任务',
        'AGENT_OFFLINE': 'PI 连接已中断，执行状态仍需核对',
        'VALIDATION_FAILED': 'PI 模型选择或执行选项未通过本机清单校验',
        'INTERNAL': 'PI 本轮未返回可验证的执行结果',
        'TASK_NOT_CANCELLABLE': 'PI 本轮已停止',
    }
    return AdapterFailure(kind=kind, code=code, message=message or messages.get(code, 'PI 当前请求未被执行'), retryable=False)


def tool_denial(reason):
    message = {
        'path_outside_scope': 'PI 尝试访问工作区外或未授权的文件，已被拦截',
        'unsupported_shell': 'PI 尝试使用无法安全核验的命令，已被拦截',
        'read_only_tool': 'PI 尝试在只读任务中使用写入或执行工具，已被拦截',
        'approval_rejected': 'PI 工具调用未获当前审批许可，已被拦截',
        'approval_expired': 'PI 工具调用审批已过期，已被拦截',
    }.get(reason, 'PI 工具调用不符合当前安全策略，已被拦截')
    return denied('PI_TOOL_CALL_BLOCKED', 'path_violation' if reason == 'path_outside_scope' else 'agent_error', message=message)


def prompt_input(message, values):
    attachments = checked_inputs(values)
    images = []
    for item in attachments:
        if str(item.attachment.kind) == 'image':
            data = Path(item.local_path).read_bytes()
            if len(data) != item.attachment.size_bytes or hashlib.sha256(data).hexdigest() != item.attachment.sha256:
                raise ValueError('attachment changed')
            from runtime.attachments.content import image_mime, fail
            detected = image_mime(data[:512])
            if detected is None or detected != item.attachment.mime_type:
                fail('ATTACHMENT_TYPE_UNSUPPORTED')
            images.append({'type': 'image', 'data': base64.b64encode(data).decode('ascii'),
                           'mimeType': detected})
    return {'message': file_prompt(message, attachments), 'images': images}


@dataclass(slots=True)
class PiState(AdapterSessionState):
    context: dict = field(default_factory=dict)
    inventory: str = ''
    handshakes: int = 0
    launch_directory: Path | None = None
    session_file: Path | None = None
    writer: SingleInstanceLock | None = None
    private_roots: tuple = ()
    pending_checks: dict = field(default_factory=dict)
    consumed: set = field(default_factory=set)
    settled: asyncio.Event = field(default_factory=asyncio.Event)
    stopping: bool = False
    result_job: asyncio.Task | None = None
    policy_snapshot: str = ''
    turn_started: bool = False
    turn_ended: bool = False
    final_stop_reason: str | None = None
    tool_blocks: list = field(default_factory=list)


class PiAdapter(AgentAdapter):
    adapter_id = 'pi'
    display_name = 'PI'
    minimum_version = '1.0.1'
    vendor_event_mappings = ()

    def __init__(self, *, runner=None, registry=None, storage_dir=None, guard_timeout=10, approval_timeout=300):
        super().__init__(registry=registry)
        self.runner = runner or ProcessRunner()
        if storage_dir is None:
            from runtime.paths import HubPaths
            storage_dir = HubPaths.resolve().root / 'pi'
        self.root = Path(storage_dir).resolve()
        self.guard_timeout, self.approval_timeout = guard_timeout, approval_timeout
        self.bindings = {}
        self.models = []
        self.model_inputs = {}
        self.default_model = None
        self.configuration_hash = ''
        self.guard = self._guard_view('unverified', 'guard_not_loaded')
        self.locks = {}
        self.expire_approval = None
        self.admission = None
        self.secrets_provider = lambda: ()
        self.policy_state = lambda spec: None
        self.protected_paths = ()

    def _guard_view(self, status, reason=None, policy=None):
        return RuntimeGuardView(status=status, isolation='hub_extension_only' if status == 'ready' else 'unknown',
                                checkedAt=utc_timestamp(), reasons=[reason] if reason else [], **({'policyRevision': policy} if policy else {}))

    def verification_configuration(self):
        executable = self.runner.find('pi')
        return [self.configuration_hash, self.default_model, GUARD_SHA256, executable]

    def _launch(self):
        executable = self.runner.find('pi')
        if not executable:
            raise FileNotFoundError('PI unavailable')
        # Resolve metadata, not shim source; never run cmd.exe or npm wrappers.
        args = executable_args(executable)
        if len(args) == 1:
            entry = Path(executable).resolve(strict=True)
            node = shutil.which('node')
            if not node or entry.suffix not in {'.js', '.cjs', '.mjs'}:
                raise PiIsolationError('PI requires a verified node entry')
            args = [node, str(entry)]
        entry = Path(args[1]).resolve(strict=True)
        package = next((p for p in entry.parents if (p / 'package.json').is_file()), None)
        metadata = json.loads((package / 'package.json').read_text('utf-8')) if package else {}
        if metadata.get('name') != '@earendil-works/pi-coding-agent' or metadata.get('version') != '1.0.1':
            raise PiIsolationError('unverified PI package')
        bin_value = metadata.get('bin', {})
        relative = bin_value.get('pi') if isinstance(bin_value, dict) else bin_value
        if not relative or (package / relative).resolve() != entry:
            raise PiIsolationError('unexpected PI entry')
        if hashlib.sha256(GUARD_PATH.read_bytes()).hexdigest() != GUARD_SHA256:
            raise ValueError('guard integrity failed')
        self.install_root = package.resolve()
        return args

    async def detect(self):
        executable = self.runner.find('pi')
        installed, version = bool(executable), None
        verified = False
        if executable:
            try:
                args = self._launch()
                result = await self.runner.run([*args, '--version'], env=self._environment(), timeout=10)
                from adapters.versions import cli_version
                version = cli_version(result.stdout)
                verified = result.returncode == 0 and version == self.minimum_version
            except PiIsolationError:
                self.guard = self._guard_view('blocked', 'uncontrolled_extensions')
            except (OSError, ValueError, TimeoutError):
                self.guard = self._guard_view('blocked', 'guard_not_loaded')
        caps = ['orchestration', 'architecture', 'coding', 'review', 'testing', 'shell', 'file_write',
                'git_worktree', 'session_resume', 'streaming_events', 'tool_approval', 'structured_output']
        return AdapterDescriptor(adapterId='pi', displayName='PI', integrationKind='cli_stream', authKind='local_login',
            supportedPlatforms=['windows', 'linux', 'macos'], installed=installed, executablePath=executable,
            detectedVersion=version, minimumVersion=self.minimum_version, detectedAt=utc_timestamp(),
            capabilities=[{'id': c, 'supported': verified} for c in caps])

    @staticmethod
    def _environment():
        env = command_environment('pi')
        # Neither Node preloads nor an inherited extension context can take over
        # this owned process. PI alone reads its own local model credentials.
        for key in list(env):
            if key.upper() in {'NODE_OPTIONS', 'NODE_PATH', 'HQAGENT_PI_GUARD_CONTEXT', 'BASH_ENV', 'ENV', 'SHELLOPTS', 'BASHOPTS', 'ZDOTDIR'} or key.startswith('BASH_FUNC_'):
                env.pop(key)
        return env

    def _context(self, spec):
        return {'sessionId': spec.session_id, 'nodeId': spec.node_id, 'cwd': str(Path(spec.worktree_path).resolve()), 'readOnly': bool(spec.read_only),
                'policyRevision': sha(canonical([spec.model_dump(mode='json', by_alias=True), secrets.token_hex(16)]))}

    async def _new_connection(self, spec, *, metadata_only=False):
        descriptor = await self.detect()
        if not descriptor.installed or descriptor.detected_version != '1.0.1' or not all(c.supported for c in descriptor.capabilities):
            if 'uncontrolled_extensions' in self.guard.reasons:
                raise PiIsolationError('PI isolation not verified')
            raise ValueError('PI version not verified')
        args = self._launch()
        worktree = Path(spec.worktree_path).resolve()
        data_root = self.root.parent
        if not metadata_only:
            if data_root.is_relative_to(worktree):
                raise ValueError('application data cannot be a task workspace')
            if worktree.is_relative_to(data_root):
                relative = worktree.relative_to(data_root).parts
                managed_worktree = len(relative) >= 2 and relative[0] == 'worktrees'
                verification = len(relative) == 3 and relative[0] == 'image-verification' and relative[-1] == 'workspace'
                if not (managed_worktree or verification):
                    raise ValueError('application metadata cannot be a task workspace')
        self.root.mkdir(parents=True, exist_ok=True)
        directory = self.root / 'sessions' / secrets.token_hex(16)
        directory.mkdir(parents=True)
        if GUARD_PATH.resolve().is_relative_to(Path(spec.worktree_path).resolve()):
            raise ValueError('guard is inside task root')
        state = PiState(spec.session_id, '', spec,
                        PathGuard(spec.worktree_path, spec.allowed_paths, input_attachments=spec.input_attachments),
                        launch_directory=directory, context=self._context(spec), policy_snapshot=sha(canonical(self.policy_state(spec))), private_roots=(self.root, self.install_root, Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1], self.root.parent / 'remote', self.root.parent / 'runtime', self.root.parent / 'data'))
        extra = list(self.protected_paths)
        for name in ('PI_CODING_AGENT_DIR', 'CODEX_HOME', 'CLAUDE_CONFIG_DIR'):
            if os.environ.get(name):
                root = Path(os.environ[name]).expanduser()
                extra.append((root if root.is_absolute() else worktree / root).resolve())
        state.private_roots += tuple(extra)
        args += ['--mode', 'rpc', '--no-extensions', '-e', str(GUARD_PATH.resolve()), '--session-dir', str(directory)]
        launch_model = spec.model_id_ or (self.default_model if not metadata_only else None)
        if launch_model is not None:
            provider, model = selector(launch_model)
            args += ['--provider', provider, '--model', model]
        env = self._environment()
        env['HQAGENT_PI_GUARD_CONTEXT'] = canonical(state.context)
        state.process = await self.runner.start(args, cwd=spec.worktree_path, env=env)
        state.connection = PiRPC(state.process, lambda frame: self._event(state, frame), lambda: self._lost(state))
        try:
            await asyncio.wait_for(state.ready.wait(), self.guard_timeout)
            if state.failure:
                raise ValueError('guard rejected')
            native = await state.connection.request('get_state')
            if (state.failure is not None or native.get('isStreaming') is not False
                    or native.get('isCompacting') is not False
                    or type(native.get('pendingMessageCount')) is not int or native['pendingMessageCount'] != 0):
                raise ValueError('PI was not idle before prompt')
            available = await state.connection.request('get_available_models')
            self._models(available, native, default=spec.model_id_ is None)
            selected = spec.model_id_ or self.default_model
            if not metadata_only and selected not in {m['id'] for m in self.models}:
                raise PiModelError('model not available')
            actual = native.get('model') or {}
            if not metadata_only and selected != str(actual.get('provider', '')) + '/' + str(actual.get('id', '')):
                raise PiModelError('PI selected another model')
            return state, native
        except BaseException:
            if await state.connection.force_close():
                self._remove_launch(state)
            raise

    def _models(self, available, native, *, default=True):
        models, facts = [], []
        self.model_inputs = {}
        rows = available.get('models')
        if not isinstance(rows, list):
            raise ValueError('invalid model catalog shape')
        for row in rows:
            provider, model = selector(str(row.get('provider', '')) + '/' + str(row.get('id', '')))
            models.append({'id': provider + '/' + model, 'name': provider + '/' + model, 'efforts': [], 'isDefault': False})
            self.model_inputs[provider + '/' + model] = set(row.get('input', []))
            facts.append({k: row[k] for k in ('provider', 'id', 'input', 'api', 'baseUrl', 'reasoning', 'contextWindow', 'maxTokens', 'compat') if k in row})
        active = native.get('model') or {}
        default_id = str(active.get('provider', '')) + '/' + str(active.get('id', ''))
        if default:
            self.default_model = default_id if default_id in {m['id'] for m in models} else None
        for model in models:
            model['isDefault'] = model['id'] == self.default_model
        self.models = models
        self.configuration_hash = sha(canonical(sorted(facts, key=lambda v: (v['provider'], v['id']))))

    async def health(self):
        try:
            models = await self.list_models('local.pi.default')
            if not models.verified:
                return denied('VALIDATION_FAILED', message=models.reason)
            return AdapterHealth(status='ready', checkedAt=utc_timestamp(), authValid=True)
        except Exception:
            self.guard = self._guard_view('blocked', 'guard_not_loaded')
            return denied()

    async def list_models(self, agent_instance_id):
        from protocol.generated.python import AgentTaskSpec
        self.root.mkdir(parents=True, exist_ok=True)
        workspace = self.root / 'discovery'
        workspace.mkdir(exist_ok=True)
        spec = AgentTaskSpec(sessionId='pi-discovery-' + secrets.token_hex(8), taskId='discovery', nodeId='discovery',
            workspaceId='discovery', roleId='analyst', objective='metadata only', worktreePath=str(workspace),
            allowedPaths=[], readOnly=True, sessionPurpose='adhoc', reusePolicy='new_session')
        state, _ = await self._new_connection(spec, metadata_only=True)
        # Snapshot this response before awaiting cleanup; concurrent execution
        # metadata must not replace the result of this particular request.
        models = list(self.models)
        if not await state.connection.force_close():
            raise ValueError('metadata process did not stop')
        self._remove_launch(state)
        return LocalAgentModelsView(agentInstanceId=agent_instance_id, verified=bool(models), models=models,
            **{} if models else {'reason': 'PI 模型目录未就绪或读取权限不足，请检查本机 PI 配置后重试'})

    def _remove_directory(self, directory):
        # Only a per-launch directory directly beneath our managed sessions.
        # Reject replacement links rather than following them during cleanup.
        if directory is None or not directory.exists():
            return
        if (directory.is_symlink() or directory.resolve().parent != (self.root / 'sessions').resolve()
                or directory.resolve() != directory.absolute()):
            raise OSError('managed session directory changed')
        shutil.rmtree(directory)

    def _remove_launch(self, state):
        if state.session_file is None or state.session_file.parent != state.launch_directory:
            self._remove_directory(state.launch_directory)

    async def release_temporary_session(self, session_id):
        state = self.registry.get(session_id)
        if (state is None or state.spec.workspace_id != 'image-verification'
                or state.process.returncode is None or not state.settled.is_set()):
            return False
        if state.session_file is not None:
            self._remove_directory(state.session_file.parent)
            self._binding_path(state.external_session_id).unlink(missing_ok=True)
        self._remove_launch(state)
        return True

    def _binding_path(self, external):
        return self.root / 'bindings' / (sha(external) + '.json')

    def _bind(self, state, native, expected=None):
        external, raw_path = native.get('sessionId'), native.get('sessionFile')
        if not isinstance(external, str) or not external or not isinstance(raw_path, str):
            raise ValueError('missing exact session')
        path = Path(raw_path).resolve()
        if not path.is_relative_to(self.root / 'sessions'):
            raise ValueError('session outside managed storage')
        if expected and (external != expected['id'] or str(path) != expected['path']):
            raise ValueError('session identity mismatch')
        if expected:
            stat = path.stat()
            if expected['identity'] != [stat.st_dev, stat.st_ino]:
                raise ValueError('native file replaced during switch')
        state.external_session_id, state.session_file = external, path
        if state.writer is None:
            writer = SingleInstanceLock(self.root / 'writers' / (sha(external) + '.lock'), remove_on_release=False)
            writer.acquire()
            state.writer = writer
        self._save_binding(state)

    def _save_binding(self, state):
        from runtime.remote.security import CredentialVault
        path = state.session_file
        identity = None
        if path.exists():
            stat = path.stat()
            identity = [stat.st_dev, stat.st_ino]
        body = {'id': state.external_session_id, 'path': str(path), 'identity': identity,
                'cwd': str(state.guard.root), 'workspaceId': state.spec.workspace_id, 'active': not state.settled.is_set()}
        (self.root / 'bindings').mkdir(parents=True, exist_ok=True)
        CredentialVault.atomic_write(self._binding_path(state.external_session_id), canonical(body).encode())

    async def start(self, spec):
        from runtime.pi_visibility import CLIENT_PI
        if CLIENT_PI.get() is False:
            return denied('NOT_FOUND', 'capability_missing')
        if self.admission is not None and not self.admission(spec):
            return denied('REMOTE_REVISION_REQUIRED', 'capability_missing')
        state = None
        failure_code = 'PI_GUARD_UNAVAILABLE'
        stage = '启动安全核验'
        try:
            if not spec.worktree_path or not Path(spec.worktree_path).is_dir():
                return denied('PATH_NOT_ALLOWED', 'path_violation')
            if spec.reasoning_effort:
                return denied('VALIDATION_FAILED', 'agent_error')
            if spec.model_id_ is None:
                await self.list_models('local.pi.default')
            state, native = await self._new_connection(spec)
            if spec.resume_session_id:
                failure_code = 'SESSION_NOT_RESUMABLE'
                stage = '原会话写锁或恢复状态不可用'
                state.writer = SingleInstanceLock(self.root / 'writers' / (sha(spec.resume_session_id) + '.lock'), remove_on_release=False)
                state.writer.acquire()
                expected = json.loads(self._binding_path(spec.resume_session_id).read_text('utf-8'))
                if expected.get('active', True):
                    raise ValueError('previous writer needs recovery')
                stage = '原会话文件身份或工作区不匹配'
                path = Path(expected['path']).resolve()
                if not path.is_relative_to(self.root / 'sessions'):
                    raise ValueError('untrusted session binding')
                stat = path.stat()
                if expected['identity'] != [stat.st_dev, stat.st_ino] or expected.get('workspaceId') != spec.workspace_id:
                    raise ValueError('native file identity changed')
                stage = '切换会话后的安全扩展握手未完成'
                state.ready.clear()
                switched = await state.connection.request('switch_session', sessionPath=str(path))
                if switched.get('cancelled'):
                    raise ValueError('switch refused')
                await asyncio.wait_for(state.ready.wait(), self.guard_timeout)
                if state.failure:
                    raise ValueError('switch guard failed')
                native = await state.connection.request('get_state')
                stage = '切换会话后模型与当前选择不一致'
                restored = native.get('model') or {}
                wanted = spec.model_id_ or self.default_model
                if wanted != str(restored.get('provider', '')) + '/' + str(restored.get('id', '')):
                    raise ValueError('switch restored a different model')
                available = await state.connection.request('get_available_models')
                self._models(available, native, default=False)
                stage = '切换后的原生 ID 或文件身份不一致'
                self._bind(state, native, expected)
            else:
                self._bind(state, native)
            if any(str(v.attachment.kind) == 'image' for v in spec.input_attachments or []):
                from runtime.pi_visibility import PI_IMAGE_TARGET
                from runtime.attachments.verification_target import target_for
                expected = PI_IMAGE_TARGET.get()
                if 'image' not in self.model_inputs.get(spec.model_id_ or self.default_model, set()):
                    raise ValueError('PI model does not accept images')
                if expected is not None and target_for(expected['agentId'], 'pi', '1.0.1', spec.model_id_, self) != expected:
                    raise ValueError('PI image verification target changed')
            old = self.registry.get(spec.session_id)
            if old:
                if old.process is not None and old.process.returncode is None:
                    raise ValueError('session still owned')
                self.registry.forget_finished(spec.session_id)
            self.registry.add(state)
            state.active_turn_id = secrets.token_hex(16)
            failure_code = 'INTERNAL'
            state.connection.idle = False
            result = await state.connection.request('prompt', **prompt_input(build_task_prompt(spec) + '\n安全限制导致的拒绝也是已完成的回复：说明拒绝原因，不得声称执行被禁止的操作；正常完成说明时返回 status=done，并用 blockers.kind=permission_denied 记录。其它真实业务失败仍如实报告；验收缺少证据不能因为回复已结束就报告通过。\nAgentResult JSON Schema:\n' + json.dumps(AgentResult.model_json_schema(by_alias=True), ensure_ascii=False), spec.input_attachments))
            if result.get('disposition') == 'handled':
                raise ValueError('prompt did not start a turn')
            return AgentSessionHandle(adapterId='pi', sessionId=state.session_id, externalSessionId=state.external_session_id,
                                     startedAt=utc_timestamp(), supportsResume=True, workingDirectory=spec.worktree_path)
        except Exception as error:
            if state:
                stopped = await state.connection.force_close()
                if stopped:
                    self._release(state)
                    self._remove_launch(state)
            from core.errors import HubError
            if isinstance(error, PiModelError):
                return denied('VALIDATION_FAILED', 'agent_error')
            if isinstance(error, PiIsolationError):
                self.guard = self._guard_view('blocked', 'uncontrolled_extensions')
                return denied('PI_UNCONTROLLED_EXTENSIONS')
            if isinstance(error, HubError):
                return denied(error.code, 'agent_error', message=error.message)
            if failure_code == 'PI_GUARD_UNAVAILABLE':
                self.guard = self._guard_view('blocked', 'guard_not_loaded')
            return denied(failure_code, 'capability_missing' if failure_code == 'PI_GUARD_UNAVAILABLE' else 'agent_error',
                message=('PI 会话续接失败：' + stage) if failure_code == 'SESSION_NOT_RESUMABLE' else None)

    async def resume(self, request):
        state = self.registry.get(request.session_id)
        if state is None:
            if request.task_spec is None:
                return denied('SESSION_NOT_RESUMABLE', 'agent_error', message='PI 会话续接失败：缺少持久执行规格')
            spec = request.task_spec.model_copy(update={'session_id': request.session_id,
                'resume_session_id': request.external_session_id, 'objective': request.message})
            # Restarted owners use the durable inactive binding and exact-file
            # writer lease. start() still rejects unresolved previous writers.
            result = await self.start(spec)
            return result if isinstance(result, AdapterFailure) else None
        if not state.finished.is_set() or not state.settled.is_set():
            return denied('SESSION_NOT_RESUMABLE', 'agent_error', message='PI 会话续接失败：上一进程尚未确认停止')
        if request.external_session_id != state.external_session_id:
            return denied('SESSION_NOT_RESUMABLE', 'agent_error')
        if not await state.connection.force_close():
            return denied('SESSION_NOT_RESUMABLE', 'agent_error')
        spec = request.task_spec or state.spec
        spec = spec.model_copy(update={'session_id': request.session_id,
            'resume_session_id': state.external_session_id, 'objective': request.message})
        result = await self.start(spec)
        return result if isinstance(result, AdapterFailure) else None

    async def stream_events(self, session_id):
        state = self.registry.get(session_id)
        if state is None:
            yield AdapterStreamEnd(status='agent_exited', endedAt=utc_timestamp(), resumable=False)
            return
        while True:
            item = await state.queue.get()
            if item is STREAM_END:
                return
            yield item

    def can_resume_completed_turn(self, session_id):
        state = self.registry.get(session_id)
        return bool(state and state.result is not None and state.failure is None
                    and state.turn_ended and state.settled.is_set() and state.finished.is_set()
                    and state.process.returncode is not None and state.external_session_id)

    async def collect_result(self, session_id):
        state = self.registry.get(session_id)
        if state is None:
            return denied('SESSION_NOT_RESUMABLE', 'agent_error')
        try:
            await asyncio.wait_for(state.finished.wait(), state.spec.timeout_seconds or 600)
        except TimeoutError:
            return denied('INTERNAL', 'timeout')
        return state.failure or state.result or denied('INTERNAL', 'agent_error')

    @staticmethod
    def _release(state):
        if state.writer:
            state.writer.release()
            state.writer = None

    async def _lost(self, state):
        if state.finished.is_set():
            return
        state.failure = denied('AGENT_OFFLINE', 'transport_error')
        # EOF does not release writer ownership unless process death is known.
        if state.process.returncode is not None:
            self._release(state)
        await state.finish(AdapterStreamEnd(status='transport_lost', endedAt=utc_timestamp(), resumable=False))

    async def _event(self, state, frame):
        kind = frame.get('type')
        if kind == 'extension_ui_request':
            await self._guard_request(state, frame)
        elif kind == 'agent_start':
            if state.active_turn_id:
                state.turn_started = True
                state.turn_ended = False
                state.final_stop_reason = None
                if not state.started_emitted:
                    state.started_emitted = True
                    await state.emit(AdapterEvent.create(kind, 'agent.started', AgentStartedPayload(
                        sessionId=state.session_id, externalSessionId=state.external_session_id,
                        purpose=state.spec.session_purpose, reusePolicy=state.spec.reuse_policy,
                        worktreePath=state.spec.worktree_path)))
            else:
                state.failure = denied()
            state.connection.idle = False
        elif kind == 'message_end':
            message = frame.get('message') or {}
            if message.get('role') == 'assistant':
                state.final_stop_reason = message.get('stopReason')
        elif kind == 'agent_end':
            if state.active_turn_id and state.turn_started:
                state.turn_ended = True
                final = next((m for m in reversed(frame.get('messages') or [])
                              if isinstance(m, dict) and m.get('role') == 'assistant'), None)
                if final is not None:
                    state.final_stop_reason = final.get('stopReason')
        elif kind == 'agent_settled':
            if not state.active_turn_id or not state.turn_started or state.settled.is_set():
                return
            state.settled.set()
            state.connection.idle = True
            state.result_job = asyncio.create_task(self._complete(state))
        elif kind == 'message_update':
            event = frame.get('assistantMessageEvent') or {}
            if event.get('type') == 'text_delta' and isinstance(event.get('delta'), str):
                await state.emit(AdapterEvent.create(kind, 'agent.progress', AgentProgressPayload(message='PI 正在生成公开回复')))
        elif kind in {'tool_execution_start', 'tool_execution_end'}:
            tool = frame.get('toolName')
            if tool in TOOLS:
                await state.emit(AdapterEvent.create(kind, 'agent.tool_call', AgentToolCallPayload(
                    toolName=tool, resultSummary='PI工具活动', failed=bool(frame.get('isError')))))
        # agent_end and abort responses are deliberately not completion signals.

    async def _complete(self, state):
        try:
            if state.stopping:
                state.failure = denied('TASK_NOT_CANCELLABLE', 'cancelled')
            elif state.failure is None:
                if not state.turn_ended or state.final_stop_reason in {'error', 'aborted'}:
                    state.failure = denied('AGENT_OFFLINE', 'transport_error',
                        message='PI 未正常完成本轮输出，缺少结束信号或模型返回运行错误')
                    return
                reply = await state.connection.request('get_last_assistant_text')
                result = await self._completed_reply(state, reply.get('text'))
                if (state.spec.read_only and result.changed_files) or state.guard.validate_changes(result.changed_files):
                    state.failure = denied('PI_TOOL_CALL_BLOCKED', 'path_violation')
                else:
                    from adapters.history import public_text
                    def public(value):
                        if isinstance(value, str):
                            return public_text(value, self.secrets_provider())
                        if isinstance(value, list):
                            return [public(v) for v in value]
                        if isinstance(value, dict):
                            return {k: public(v) for k, v in value.items()}
                        return value
                    state.result = AgentResult.model_validate(public(result.model_dump(mode='json', by_alias=True)))
        except Exception:
            state.failure = denied('INTERNAL', 'agent_error')
        finally:
            # A settled turn may still own an idle RPC process and cwd handle.
            # Close it before releasing the exact native writer lease. Resume
            # starts a fresh owned process and switches the same bound file.
            stopped = await state.connection.force_close()
            if stopped:
                self._save_binding(state)
                self._release(state)
                self._remove_launch(state)
            else:
                state.failure = denied('AGENT_OFFLINE', 'transport_error')
            if state.result is not None and state.failure is None:
                await state.emit(AdapterEvent.create('agent_settled', 'agent.completed', AgentCompletedPayload(result=state.result)))
            healthy = stopped and (state.failure is None or state.stopping)
            await state.finish(AdapterStreamEnd(status='ended' if healthy else 'agent_exited',
                endedAt=utc_timestamp(), resumable=healthy))

    async def _completed_reply(self, state, text):
        if not isinstance(text, str) or not text.strip():
            raise ValueError('missing final output')
        try:
            result = parse_agent_result(text)
        except ValueError:
            # Only a read-only, observed guard refusal may finish with prose.
            # Never invent file-change evidence for a writable task, and never
            # reinterpret a malformed structured response as successful prose.
            if (not state.spec.read_only or str(state.spec.session_purpose) == 'review'
                    or not state.tool_blocks or text.lstrip().startswith(('{', '[', '```'))):
                raise
            result = AgentResult(status='blocked', summary=text, changedFiles=[])
        if not result.summary.strip():
            raise ValueError('missing final summary')
        model_refusal = bool(result.blockers) and all(b.kind == 'permission_denied' for b in result.blockers)
        refusal = bool(state.tool_blocks) or model_refusal
        if refusal:
            from protocol.generated.python import Blocker
            evidence = 'guard_decision' if state.tool_blocks else 'model_report'
            message = '本轮有操作被安全策略拦截，PI 已完成回复' if state.tool_blocks else 'PI 报告权限限制并拒绝操作，已完成回复'
            detail = {'errorCode': 'PI_TOOL_CALL_BLOCKED', 'evidence': evidence,
                      'reportedStatus': result.status}
            if state.tool_blocks:
                detail['guardReasons'] = sorted({str(d.reason) for d in state.tool_blocks})
            else:
                detail['reportedReason'] = 'permission_denied'
                # A completed self-refusal is audited in the result only;
                # it is neither a failed node nor a witnessed Host tool call.
            audit = Blocker(kind='permission_denied', message=message, detail=detail)
            blockers = list(result.blockers or [])
            # Only the safety refusal becomes a completed conversational reply.
            # Keep unrelated build/test/dependency failures and changes honest.
            completed_refusal = (str(state.spec.session_purpose) != 'review' and not result.changed_files
                and all(b.kind == 'permission_denied' for b in blockers)
                and all(t.passed for t in result.tests or []))
            result = result.model_copy(update={'status': 'done' if completed_refusal else result.status,
                                              'blockers': [*blockers, audit]})
        return result

    async def _guard_request(self, state, frame):
        identifier = frame.get('id')
        if not isinstance(identifier, str):
            return
        response = {'type': 'extension_ui_response', 'id': identifier, 'cancelled': True}
        try:
            if frame.get('method') != 'editor':
                raise ValueError('untrusted UI method')
            raw = unique_object(frame.get('prefill', ''))
            if frame.get('title') == 'hqagent.guard.handshake.v1':
                if state.ready.is_set():
                    raise ValueError('unsolicited guard handshake')
                value = PiGuardHandshake.model_validate(raw)
                expected = READ_TOOLS if state.spec.read_only else TOOLS
                if (value.session_id != state.session_id or value.guard_revision != GUARD_REVISION
                        or value.policy_revision != state.context['policyRevision'] or sorted(value.active_tools) != list(expected)
                        or hashlib.sha256(GUARD_PATH.read_bytes()).hexdigest() != GUARD_SHA256):
                    raise ValueError('guard handshake mismatch')
                state.inventory = value.tool_inventory_sha256
                state.handshakes += 1
                self.guard = self._guard_view('ready', policy=state.context['policyRevision'])
                response = {'type': 'extension_ui_response', 'id': identifier, 'value': 'ready'}
            elif frame.get('title') == 'hqagent.guard.check.v1' and state.ready.is_set():
                if raw.get('toolInventorySha256') != state.inventory:
                    self.guard = self._guard_view('blocked', 'tool_inventory_changed')
                    state.failure = denied()
                    raise ValueError('inventory changed')
                if state.policy_snapshot != sha(canonical(self.policy_state(state.spec))):
                    self.guard = self._guard_view('blocked', 'policy_unavailable')
                    state.failure = denied()
                    raise ValueError('policy changed')
                value, args, remaining = validate_check(raw, state, state.context, state.inventory)
                if value.request_id in state.consumed:
                    raise ValueError('reused guard request')
                state.consumed.add(value.request_id)
                reason = blocked_reason(state, value.tool_name, args)
                if hashlib.sha256(GUARD_PATH.read_bytes()).hexdigest() != GUARD_SHA256:
                    reason = 'guard_not_loaded'
                decision = {'requestId': value.request_id, 'sessionId': value.session_id, 'toolCallId': value.tool_call_id,
                    'argumentsSha256': value.arguments_sha256, 'policyRevision': value.policy_revision,
                    'expiresAt': value.expires_at, 'decision': 'block', 'reason': reason or 'approval_required'}
                if not reason and value.tool_name in {'bash', 'powershell'}:
                    decision = await self._approval(state, value, args, decision, min(remaining, self.approval_timeout))
                elif not reason:
                    decision.update(decision='allow')
                    decision.pop('reason', None)
                if decision['decision'] == 'block':
                    blocked = tool_denial(decision.get('reason'))
                    if decision.get('reason') == 'guard_not_loaded':
                        state.failure = denied()
                    else:
                        state.tool_blocks.append(PiGuardDecision.model_validate(decision))
                    # A denied tool is a recoverable action failure, not evidence
                    # that the native session is damaged. PI receives block and
                    # may continue with safe tools; retain structured auditing.
                    await state.emit(AdapterEvent.create('hqagent.guard.check.v1', 'agent.tool_call',
                        AgentToolCallPayload(toolName=value.tool_name, failed=True,
                                             resultSummary=blocked.message)))
                response = {'type': 'extension_ui_response', 'id': identifier,
                            'value': PiGuardDecision.model_validate(decision).model_dump_json(by_alias=True, exclude_none=True)}
            else:
                raise ValueError('untrusted UI request')
        except Exception:
            if frame.get('title') == 'hqagent.guard.check.v1' and state.ready.is_set():
                state.failure = state.failure or denied('PI_TOOL_CALL_BLOCKED', 'agent_error')
                await state.emit(failure_event(state.failure, 'hqagent.guard.check.v1'))
        await state.connection.write(response)
        if frame.get('title') == 'hqagent.guard.handshake.v1':
            if response.get('value') != 'ready':
                state.failure = denied()
            state.ready.set()

    async def _approval(self, state, value, args, decision, timeout):
        from adapters.codex_adapter import CodexAdapter
        approval_id = 'approval_' + secrets.token_hex(16)
        action = CodexAdapter._dangerous_action(args.get('command', ''))
        future = asyncio.get_running_loop().create_future()
        fingerprint = sha(canonical(state.spec.model_dump(mode='json', by_alias=True)))
        state.pending_checks[approval_id] = (value.request_id, future)
        try:
            await state.emit(AdapterEvent.create('hqagent.guard.check.v1', 'approval.required',
                ApprovalRequiredPayload(approvalId=approval_id, action=action, targetResource='PI 受控工具请求', riskLevel='high'),
                external_request_id=value.request_id))
            allowed = await asyncio.wait_for(future, timeout)
            if (allowed and not state.stopping and not state.finished.is_set() and state.process.returncode is None
                    and state.policy_snapshot == sha(canonical(self.policy_state(state.spec)))
                    and fingerprint == sha(canonical(state.spec.model_dump(mode='json', by_alias=True)))
                    and validate_check(value.model_dump(mode='json', by_alias=True), state, state.context, state.inventory)
                    and blocked_reason(state, value.tool_name, args) is None):
                decision.update(decision='allow', approvalId=approval_id)
                decision.pop('reason', None)
            else:
                decision['reason'] = 'approval_rejected'
        except (TimeoutError, ValueError):
            decision['reason'] = 'approval_expired'
            if self.expire_approval is not None:
                await self.expire_approval(state.spec.task_id)
        finally:
            state.pending_checks.pop(approval_id, None)
        return decision

    async def approve(self, dispatch):
        for state in self.registry.values():
            pending = state.pending_checks.get(dispatch.approval_id)
            if (pending and pending[0] == dispatch.external_request_id and not pending[1].done()
                    and not state.stopping and not state.finished.is_set() and state.process.returncode is None):
                pending[1].set_result(str(dispatch.decision) == 'approve')
                return None
        return denied('PI_TOOL_CALL_BLOCKED', 'agent_error')

    async def cancel(self, request):
        started = time.monotonic()
        state = self.registry.get(request.session_id)
        outcome, orphans = 'not_found', []
        if state:
            if state.finished.is_set() and not state.settled.is_set() and state.process.returncode is not None:
                return CancelResult(outcome='not_found', completedAt=utc_timestamp(),
                    elapsedMs=int((time.monotonic()-started)*1000), orphanProcessIds=[], detail='PI传输丢失后原生执行仍需核对')
            if state.settled.is_set():
                if state.result_job and state.result_job is not asyncio.current_task():
                    await asyncio.shield(state.result_job)
                if state.process.returncode is None and not await state.connection.force_close():
                    orphans = [state.process.pid]
                outcome = 'already_finished'
            else:
                state.stopping = True
                for _, future in state.pending_checks.values():
                    if not future.done():
                        future.set_result(False)
                try:
                    if str(request.mode) == 'graceful':
                        async with asyncio.timeout(max(0.001, request.grace_seconds or 0)):
                            await state.connection.request('abort')
                            await state.settled.wait()
                            await state.finished.wait()
                        outcome = 'stopped_gracefully'
                    else:
                        raise TimeoutError()
                except (TimeoutError, OSError, RuntimeError):
                    if await state.connection.force_close():
                        stopped_by_settlement = state.settled.is_set()
                        state.settled.set()
                        self._save_binding(state)
                        self._release(state)
                        if not state.finished.is_set():
                            state.failure = denied('TASK_NOT_CANCELLABLE', 'cancelled')
                            await state.finish(AdapterStreamEnd(status='ended', endedAt=utc_timestamp(), resumable=True))
                        outcome = 'stopped_gracefully' if stopped_by_settlement else 'force_killed'
                    else:
                        outcome, orphans = 'refused', [state.process.pid]
        return CancelResult(outcome=outcome, completedAt=utc_timestamp(), elapsedMs=int((time.monotonic()-started)*1000),
                            orphanProcessIds=orphans, detail='PI结构化停止证据')
