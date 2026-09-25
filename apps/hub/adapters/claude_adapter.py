from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from protocol.generated.python import (
    AdapterDescriptor,
    AdapterFailure,
    AdapterFailureKind,
    AdapterHealth,
    AdapterIntegrationKind,
    AdapterPlatform,
    AdapterStreamEnd,
    AdapterStreamStatus,
    AgentCompletedPayload,
    AgentProgressPayload,
    AgentResult,
    AgentSessionHandle,
    AgentStartedPayload,
    AgentStatus,
    AgentTaskSpec,
    AgentToolCallPayload,
    ApprovalDispatch,
    AuthKind,
    CancelMode,
    CancelOutcome,
    CancelRequest,
    CancelResult,
    CapabilityId,
    DeclaredCapability,
    ErrorCode,
    ResumeRequest,
    SessionReusePolicy,
    VendorEventMapping,
)

from adapters.base import (
    AgentAdapter,
    CollectResult,
    DetectResult,
    HealthResult,
    OperationResult,
    StartResult,
)
from adapters.claude_catalog import query_models
from adapters.event_mapper import EventMapper
from adapters.events import AdapterEvent, diagnostic_raw, utc_timestamp
from adapters.failures import failure, failure_event, parse_agent_result, version_tuple
from adapters.path_guard import PathGuard
from adapters.process import ProcessRunner, command_environment, executable_args, terminate_process_tree
from adapters.prompt import build_task_prompt
from adapters.session_registry import AdapterSessionState, STREAM_END, SessionRegistry


class ClaudeAdapter(AgentAdapter):
    adapter_id = "claude"
    display_name = "Claude Code"
    # Native transcript persistence was re-verified with 2.1.281. The prior
    # 2.1.263 baseline failed exact --resume in this host environment.
    minimum_version = "2.1.281"
    vendor_event_mappings = tuple(
        VendorEventMapping.model_validate(item)
        for item in (
            {"vendorType": "system:init", "unifiedType": "agent.started"},
            {"vendorType": "assistant:text", "unifiedType": "agent.progress"},
            {"vendorType": "assistant:tool_use", "unifiedType": "agent.tool_call"},
            {"vendorType": "user:tool_result", "unifiedType": "agent.tool_call"},
            {"vendorType": "tool_progress", "unifiedType": "agent.progress"},
            {"vendorType": "system:permission_denied", "unifiedType": "agent.progress"},
            {"vendorType": "system:task_started", "unifiedType": "agent.progress"},
            {"vendorType": "system:task_notification", "unifiedType": "agent.progress"},
            {"vendorType": "result:success", "unifiedType": "agent.completed"},
            {"vendorType": "result:error", "unifiedType": "agent.failed"},
            {
                "vendorType": "rate_limit_event",
                "unifiedType": "agent.progress",
                "dropped": True,
                "note": "供应商限流诊断由 Adapter 计数，不进入 UI",
            },
            {
                "vendorType": "system:thinking_tokens",
                "unifiedType": "agent.progress",
                "dropped": True,
            },
            {
                "vendorType": "user:replay",
                "unifiedType": "agent.progress",
                "dropped": True,
            },
            {
                "vendorType": "__unknown__",
                "unifiedType": "agent.progress",
                "note": "未知 Claude 事件降级为诊断进度",
            },
        )
    )

    def __init__(
        self,
        *,
        runner: ProcessRunner | None = None,
        registry: SessionRegistry | None = None,
    ) -> None:
        super().__init__(registry=registry)
        self.runner = runner or ProcessRunner()
        self.mapper = EventMapper(self.vendor_event_mappings)

    def _capabilities(self, enabled: bool) -> list[DeclaredCapability]:
        supported = {
            CapabilityId.ORCHESTRATION: True,
            CapabilityId.ARCHITECTURE: True,
            CapabilityId.CODING: True,
            CapabilityId.REVIEW: True,
            CapabilityId.TESTING: True,
            CapabilityId.SHELL: False,
            CapabilityId.FILE_WRITE: False,
            CapabilityId.GIT_WORKTREE: True,
            CapabilityId.SESSION_RESUME: True,
            CapabilityId.STREAMING_EVENTS: True,
            CapabilityId.TOOL_APPROVAL: False,
            CapabilityId.STRUCTURED_OUTPUT: True,
            CapabilityId.VISION: False,
            CapabilityId.BROWSER: False,
        }
        notes = {
            CapabilityId.FILE_WRITE: "当前CLI接入仅开放只读工具；写入需具备可验证的宿主审批",
            CapabilityId.SHELL: "当前CLI接入未开放shell工具",
            CapabilityId.TOOL_APPROVAL: "前台 stream-json 未实测到可回传的 host approval request",
            CapabilityId.VISION: "AgentTaskSpec 没有图片输入字段，本轮不声明",
            CapabilityId.BROWSER: "本轮 Adapter 不启用 Claude in Chrome",
        }
        return [
            DeclaredCapability(
                id=item,
                supported=bool(enabled and supported[item]),
                note=None if enabled and supported[item] else notes.get(item, "Agent 未安装或版本不兼容"),
            )
            for item in CapabilityId
        ]

    async def list_models(self, agent_instance_id: str):
        return await query_models(self.runner, agent_instance_id)

    async def detect(self) -> DetectResult:
        executable = self.runner.find("claude")
        if not executable:
            return AdapterDescriptor.model_validate(
                {
                    "adapterId": self.adapter_id,
                    "displayName": self.display_name,
                    "integrationKind": AdapterIntegrationKind.CLI_STREAM,
                    "authKind": AuthKind.LOCAL_LOGIN,
                    "supportedPlatforms": [AdapterPlatform.WINDOWS],
                    "installed": False,
                    "minimumVersion": self.minimum_version,
                    "capabilities": self._capabilities(False),
                    "detectedAt": utc_timestamp(),
                }
            )
        try:
            probe = await self.runner.run(executable_args(executable, "--version"),
                                          env=command_environment("claude"), timeout=10)
        except (OSError, TimeoutError) as exc:
            return failure(
                AdapterFailureKind.TRANSPORT_ERROR,
                "Claude 版本探测失败",
                retryable=True,
                raw=exc,
            )
        version = probe.stdout.strip() or probe.stderr.strip()
        compatible = probe.returncode == 0 and version_tuple(version) >= version_tuple(self.minimum_version)
        return AdapterDescriptor.model_validate(
            {
                "adapterId": self.adapter_id,
                "displayName": self.display_name,
                "integrationKind": AdapterIntegrationKind.CLI_STREAM,
                "authKind": AuthKind.LOCAL_LOGIN,
                "supportedPlatforms": [AdapterPlatform.WINDOWS],
                "installed": True,
                "detectedVersion": version,
                "minimumVersion": self.minimum_version,
                "executablePath": executable,
                "capabilities": self._capabilities(compatible),
                "detectedAt": utc_timestamp(),
            }
        )

    async def health(self) -> HealthResult:
        executable = self.runner.find("claude")
        if not executable:
            return failure(
                AdapterFailureKind.NOT_INSTALLED,
                "未找到 Claude Code CLI",
                retryable=False,
            )
        started = time.monotonic()
        try:
            probe = await self.runner.run(
                executable_args(executable, "auth", "status", "--json"),
                env=command_environment("claude"), timeout=10
            )
            raw = json.loads(probe.stdout)
        except (OSError, TimeoutError, json.JSONDecodeError) as exc:
            return failure(
                AdapterFailureKind.TRANSPORT_ERROR,
                "Claude 登录态探测失败",
                retryable=True,
                raw=exc,
            )
        latency = int((time.monotonic() - started) * 1000)
        if not raw.get("loggedIn"):
            return AdapterHealth.model_validate(
                {
                    "status": AgentStatus.NOT_LOGGED_IN,
                    "checkedAt": utc_timestamp(),
                    "latencyMs": latency,
                    "authValid": False,
                    "diagnosticMessage": "请先运行 claude auth login",
                }
            )
        return AdapterHealth.model_validate(
            {
                "status": AgentStatus.READY,
                "checkedAt": utc_timestamp(),
                "latencyMs": latency,
                "authValid": True,
            }
        )

    async def start(self, spec: AgentTaskSpec) -> StartResult:
        preflight = await self._preflight(spec)
        if preflight is not None:
            return preflight
        if spec.reuse_policy is not SessionReusePolicy.NEW_SESSION and not spec.resume_session_id:
            return failure(
                AdapterFailureKind.AGENT_ERROR,
                "显式恢复必须提供明确的 resumeSessionId",
                retryable=False,
            )
        # 裁决 D25：sessionId 由 Hub 生成并通过 AgentTaskSpec 传入，Adapter 原样使用。
        # 自行生成等于把会话身份的所有权从 Hub 拿走，D7 的「实现与复核必须两个会话」
        # 就失去了强制手段——Adapter 不知道自己这次是在实现还是在复核。
        session_id = spec.session_id
        external_id = spec.resume_session_id or str(uuid.uuid4())
        state = AdapterSessionState(
            session_id=session_id,
            external_session_id=external_id,
            spec=spec,
            guard=PathGuard(spec.worktree_path or "", spec.allowed_paths),
        )
        launched = await self._launch(
            state,
            build_task_prompt(spec),
            resume=spec.reuse_policy is not SessionReusePolicy.NEW_SESSION,
        )
        if isinstance(launched, AdapterFailure):
            return launched
        try:
            await asyncio.wait_for(state.ready.wait(), timeout=10)
        except TimeoutError:
            await self._force_stop(state)
            await self._join_tasks(state)
            return failure(
                AdapterFailureKind.TIMEOUT,
                "Claude 启动后未在 10 秒内给出 init 事件",
                retryable=True,
            )
        if state.failure is not None:
            return state.failure
        self.registry.add(state)
        return AgentSessionHandle.model_validate(
            {
                "sessionId": session_id,
                "externalSessionId": external_id,
                "adapterId": self.adapter_id,
                "startedAt": utc_timestamp(),
                "supportsResume": True,
                "workingDirectory": spec.worktree_path,
            }
        )

    async def _preflight(self, spec: AgentTaskSpec) -> AdapterFailure | None:
        if spec.requires_approval:
            return failure(
                AdapterFailureKind.CAPABILITY_MISSING,
                "Claude 前台 JSONL 接入未验证宿主工具审批",
                retryable=False,
                missing_capabilities=[CapabilityId.TOOL_APPROVAL],
            )
        if not spec.worktree_path or not Path(spec.worktree_path).is_dir():
            return failure(
                AdapterFailureKind.PATH_VIOLATION,
                "任务必须提供存在的独立 worktreePath",
                retryable=False,
                violation_paths=[spec.worktree_path or "<missing worktreePath>"],
            )
        descriptor = await self.detect()
        if isinstance(descriptor, AdapterFailure):
            return descriptor
        if not descriptor.installed:
            return failure(
                AdapterFailureKind.NOT_INSTALLED,
                "未找到 Claude Code CLI",
                retryable=False,
            )
        if version_tuple(descriptor.detected_version or "") < version_tuple(self.minimum_version):
            return failure(
                AdapterFailureKind.VERSION_INCOMPATIBLE,
                f"Claude 版本低于最低实测版本 {self.minimum_version}",
                retryable=False,
            )
        health = await self.health()
        if isinstance(health, AdapterFailure):
            return health
        if health.status is AgentStatus.NOT_LOGGED_IN:
            return failure(
                AdapterFailureKind.NOT_LOGGED_IN,
                "Claude Code 未登录，请先运行 claude auth login",
                retryable=False,
            )
        return None

    async def _launch(
        self, state: AdapterSessionState, message: str, *, resume: bool
    ) -> None | AdapterFailure:
        executable = self.runner.find("claude")
        if not executable:
            return failure(AdapterFailureKind.NOT_INSTALLED, "未找到 Claude Code CLI", retryable=False)
        result_schema = json.dumps(
            AgentResult.model_json_schema(by_alias=True), ensure_ascii=False, separators=(",", ":")
        )
        args = executable_args(
            executable,
            "--safe-mode",
            "--print",
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            "dontAsk",
            "--permission-prompts",
            "none",
            "--json-schema",
            result_schema,
        )
        args.extend(["--resume" if resume else "--session-id", state.external_session_id])
        args.extend(["--tools", "Read,Glob,Grep"])
        if state.spec.model_id_:
            args.extend(["--model", state.spec.model_id_])
        if state.spec.reasoning_effort:
            args.extend(["--effort", state.spec.reasoning_effort])
        try:
            state.process = await self.runner.start(
                args,
                cwd=state.spec.worktree_path or "",
                env=command_environment("claude"),
            )
            if state.process.stdin is None:
                raise BrokenPipeError("Claude stdin 不可用")
            state.process.stdin.write((message + "\n").encode("utf-8"))
            await state.process.stdin.drain()
            state.process.stdin.close()
        except OSError as exc:
            return failure(
                AdapterFailureKind.TRANSPORT_ERROR,
                "Claude 子进程启动失败",
                retryable=True,
                raw=exc,
            )
        state.reader_task = asyncio.create_task(self._read_stream(state))
        state.stderr_task = asyncio.create_task(self._drain_stderr(state))
        return None

    async def resume(self, request: ResumeRequest) -> OperationResult:
        state = self.registry.get(request.session_id)
        spec = request.task_spec
        if spec is None:
            return failure(
                AdapterFailureKind.AGENT_ERROR,
                "Claude 精确恢复需要持久化 AgentTaskSpec，不能猜测上下文",
                retryable=False,
            )
        if not request.external_session_id:
            return failure(
                AdapterFailureKind.AGENT_ERROR,
                "Claude 精确恢复必须提供 externalSessionId，禁止 latest/continue 猜测",
                retryable=False,
            )
        try:
            parsed_external_id = uuid.UUID(request.external_session_id)
        except (ValueError, AttributeError):
            return failure(
                AdapterFailureKind.AGENT_ERROR,
                "Claude externalSessionId 必须是明确的规范 UUID，禁止 latest/continue/搜索词",
                retryable=False,
            )
        if str(parsed_external_id) != request.external_session_id:
            return failure(
                AdapterFailureKind.AGENT_ERROR,
                "Claude externalSessionId 必须使用小写连字符规范 UUID",
                retryable=False,
            )
        if spec.session_id != request.session_id:
            return failure(
                AdapterFailureKind.AGENT_ERROR,
                "恢复规格的 sessionId 与目标 Hub Session 不一致",
                retryable=False,
            )
        preflight = await self._preflight(spec)
        if preflight is not None:
            return preflight
        if state is None:
            state = AdapterSessionState(
                session_id=request.session_id,
                external_session_id=request.external_session_id,
                spec=spec,
                guard=PathGuard(spec.worktree_path or "", spec.allowed_paths),
            )
            new_state = True
        else:
            new_state = False
            if request.external_session_id != state.external_session_id:
                return failure(
                    AdapterFailureKind.AGENT_ERROR,
                    "externalSessionId 与已登记会话不一致",
                    retryable=False,
                )
            if self._resume_context(spec) != self._resume_context(state.spec):
                return failure(
                    AdapterFailureKind.AGENT_ERROR,
                    "恢复规格试图改变原生会话的工作区、角色、模型或权限边界",
                    retryable=False,
                )
            state.spec = spec
            state.guard = PathGuard(spec.worktree_path or "", spec.allowed_paths)
        if state.process is not None and state.process.returncode is None:
            return failure(AdapterFailureKind.AGENT_ERROR, "会话仍在运行", retryable=False)
        state.queue = asyncio.Queue()
        state.failure = None
        state.result = None
        state.stream_end = None
        state.expected_termination = False
        state.ready = asyncio.Event()
        state.finished = asyncio.Event()
        resume_spec = spec.model_copy(
            update={
                "objective": request.message,
                "acceptance": request.acceptance if request.acceptance is not None else spec.acceptance,
            }
        )
        state.spec = resume_spec
        launched = await self._launch(state, build_task_prompt(resume_spec), resume=True)
        if isinstance(launched, AdapterFailure):
            return launched
        try:
            await asyncio.wait_for(state.ready.wait(), timeout=10)
        except TimeoutError:
            await self._force_stop(state)
            await self._join_tasks(state)
            return failure(AdapterFailureKind.TIMEOUT, "Claude resume 启动超时", retryable=True)
        if state.failure is not None:
            return state.failure
        if new_state:
            self.registry.add(state)
        return None

    @staticmethod
    def _resume_context(spec: AgentTaskSpec) -> tuple[object, ...]:
        worktree = str(Path(spec.worktree_path or "").resolve())
        return (
            spec.workspace_id,
            str(spec.role_id),
            worktree,
            spec.branch,
            spec.base_commit,
            tuple(spec.allowed_paths),
            bool(spec.read_only),
            spec.model_id_,
            spec.reasoning_effort,
            spec.role_instructions,
        )

    async def stream_events(self, session_id: str) -> AsyncIterator[AdapterEvent | AdapterStreamEnd]:
        state = self.registry.get(session_id)
        if state is None:
            yield AdapterStreamEnd.model_validate(
                {
                    "status": AdapterStreamStatus.AGENT_EXITED,
                    "endedAt": utc_timestamp(),
                    "resumable": False,
                    "detail": "Hub Session 不存在",
                }
            )
            return
        while True:
            item = await state.queue.get()
            if item is STREAM_END:
                return
            yield item

    async def approve(self, dispatch: ApprovalDispatch) -> OperationResult:
        return failure(
            AdapterFailureKind.CAPABILITY_MISSING,
            "Claude 前台 JSONL 接入没有已验证的宿主审批回传入口",
            retryable=False,
            missing_capabilities=[CapabilityId.TOOL_APPROVAL],
        )

    async def cancel(self, request: CancelRequest) -> CancelResult:
        started = time.monotonic()
        state = self.registry.get(request.session_id)
        if state is None:
            return self._cancel_result(CancelOutcome.NOT_FOUND, started, "Hub Session 不存在")
        if state.finished.is_set() or state.process is None or state.process.returncode is not None:
            return self._cancel_result(CancelOutcome.ALREADY_FINISHED, started, "会话已经结束")
        if request.mode is CancelMode.GRACEFUL:
            return self._cancel_result(
                CancelOutcome.REFUSED,
                started,
                "Claude 前台 stream-json 没有已验证的 graceful 中断入口",
                orphan_pids=[state.process.pid],
            )
        state.expected_termination = True
        await self._force_stop(state)
        orphans = [state.process.pid] if state.process.returncode is None else []
        return self._cancel_result(
            CancelOutcome.REFUSED if orphans else CancelOutcome.FORCE_KILLED,
            started,
            "Claude 子进程已执行 force kill",
            orphan_pids=orphans,
        )

    async def collect_result(self, session_id: str) -> CollectResult:
        state = self.registry.get(session_id)
        if state is None:
            return failure(AdapterFailureKind.AGENT_ERROR, "Hub Session 不存在", retryable=False)
        if state.failure is not None:
            return state.failure
        if state.result is None:
            return failure(
                AdapterFailureKind.AGENT_ERROR,
                "Claude 尚未产生结构化结果",
                retryable=not state.finished.is_set(),
            )
        violations = state.guard.validate_changes(state.result.changed_files)
        if violations:
            return failure(
                AdapterFailureKind.PATH_VIOLATION,
                "Claude 结果包含越界文件",
                retryable=False,
                violation_paths=violations,
            )
        return state.result

    async def _read_stream(self, state: AdapterSessionState) -> None:
        process = state.process
        assert process is not None and process.stdout is not None
        try:
            while line := await process.stdout.readline():
                try:
                    raw = json.loads(line.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    self.mapper.map("__unknown__", {"line": line.decode(errors="replace")})
                    continue
                await self._handle_vendor_event(state, raw)
            returncode = await process.wait()
            state.ready.set()
            if state.stream_end is None:
                if state.failure is not None:
                    status = AdapterStreamStatus.AGENT_EXITED
                elif state.result is not None or state.expected_termination:
                    status = AdapterStreamStatus.ENDED
                else:
                    status = AdapterStreamStatus.AGENT_EXITED
                    state.failure = failure(
                        AdapterFailureKind.AGENT_ERROR,
                        f"Claude 进程已退出，exitCode={returncode}",
                        retryable=False,
                    )
                resumable = bool(
                    status is AdapterStreamStatus.ENDED
                    and state.result is not None
                    and state.failure is None
                    and state.external_session_id
                )
                await state.finish(
                    AdapterStreamEnd.model_validate(
                        {
                            "status": status,
                            "endedAt": utc_timestamp(),
                            "resumable": resumable,
                            "detail": f"exitCode={returncode}",
                        }
                    )
                )
        except Exception as exc:
            state.ready.set()
            cleaned = process.returncode is not None
            if process.returncode is None:
                try:
                    cleaned = await terminate_process_tree(process)
                except Exception:
                    cleaned = False
            state.failure = failure(
                AdapterFailureKind.TRANSPORT_ERROR,
                "Claude 事件流读取失败，已清理专属进程树"
                if cleaned
                else "Claude 事件流读取失败，专属进程树清理未确认",
                retryable=False,
                raw={"channel": "stdout", "exceptionType": type(exc).__name__, "processTreeCleaned": cleaned},
            )
            await state.finish(
                AdapterStreamEnd.model_validate(
                    {
                        "status": AdapterStreamStatus.AGENT_EXITED,
                        "endedAt": utc_timestamp(),
                        "resumable": False,
                        "detail": (
                            f"stdout reader failed ({type(exc).__name__}); "
                            f"processTreeCleaned={str(cleaned).lower()}"
                        ),
                    }
                )
            )

    async def _handle_vendor_event(self, state: AdapterSessionState, raw: dict[str, Any]) -> None:
        event_type = str(raw.get("type", "__unknown__"))
        if event_type == "system":
            subtype = str(raw.get("subtype", "unknown"))
            vendor_type = f"system:{subtype}"
            if subtype == "init":
                native_session_id = str(raw.get("session_id") or "")
                if not native_session_id or native_session_id != state.external_session_id:
                    state.failure = failure(
                        AdapterFailureKind.AGENT_ERROR,
                        "Claude init 返回的 session_id 与明确目标不一致",
                        retryable=False,
                    )
                    state.ready.set()
                    state.expected_termination = True
                    await state.emit(failure_event(state.failure, "system:init"))
                    await self._force_stop(state)
                    return
                state.ready.set()
                payload = AgentStartedPayload.model_validate(
                    {
                        "sessionId": state.session_id,
                        "externalSessionId": raw.get("session_id") or state.external_session_id,
                        "purpose": state.spec.session_purpose,
                        "reusePolicy": state.spec.reuse_policy,
                        "worktreePath": state.spec.worktree_path,
                        "branch": state.spec.branch,
                    }
                )
                await state.emit(AdapterEvent.create(vendor_type, "agent.started", payload))
                return
            event = self.mapper.map(vendor_type, raw)
            if event:
                await state.emit(event)
            return
        if event_type == "assistant":
            for content in raw.get("message", {}).get("content", []):
                content_type = content.get("type")
                if content_type == "text":
                    text = str(content.get("text", "")).strip()
                    if text:
                        payload = AgentProgressPayload.model_validate(
                            {"message": text, "raw": diagnostic_raw(raw)}
                        )
                        await state.emit(AdapterEvent.create("assistant:text", "agent.progress", payload))
                elif content_type == "tool_use":
                    tool_name = str(content.get("name", "unknown"))
                    tool_input = content.get("input") if isinstance(content.get("input"), dict) else {}
                    violations = state.guard.inspect_tool_call(tool_name, tool_input)
                    if violations:
                        # 带上工具名：只说「访问越界路径」而不说是哪个工具，
                        # 排障时分不清是 Agent 想写还是我们的读写判别写错了。
                        await self._fail_path_violation(state, violations, raw, tool_name)
                        return
                    excerpt = json.dumps(tool_input, ensure_ascii=False, default=str)[:512]
                    payload = AgentToolCallPayload.model_validate(
                        {"toolName": tool_name, "argumentsExcerpt": excerpt}
                    )
                    await state.emit(
                        AdapterEvent.create("assistant:tool_use", "agent.tool_call", payload)
                    )
            return
        if event_type == "user":
            contents = raw.get("message", {}).get("content", [])
            if raw.get("isReplay"):
                self.mapper.map("user:replay", raw)
                return
            for content in contents if isinstance(contents, list) else []:
                if content.get("type") == "tool_result":
                    payload = AgentToolCallPayload.model_validate(
                        {
                            "toolName": "tool_result",
                            "resultSummary": str(content.get("content", ""))[:512],
                            "failed": bool(content.get("is_error")),
                        }
                    )
                    await state.emit(
                        AdapterEvent.create("user:tool_result", "agent.tool_call", payload)
                    )
            return
        if event_type == "tool_progress":
            payload = AgentProgressPayload.model_validate(
                {
                    "message": f"{raw.get('tool_name', 'tool')} 已运行 {raw.get('elapsed_time_seconds', 0)} 秒",
                    "raw": diagnostic_raw(raw),
                }
            )
            await state.emit(AdapterEvent.create("tool_progress", "agent.progress", payload))
            return
        if event_type == "result":
            state.ready.set()
            result_session_id = raw.get("session_id")
            if result_session_id and str(result_session_id) != state.external_session_id:
                state.failure = failure(
                    AdapterFailureKind.AGENT_ERROR,
                    "Claude result 返回的 session_id 与明确目标不一致",
                    retryable=False,
                )
                await state.emit(failure_event(state.failure, "result:error"))
                return
            if raw.get("is_error") or raw.get("subtype") != "success":
                state.failure = failure(
                    AdapterFailureKind.AGENT_ERROR,
                    "Claude 执行失败",
                    retryable=False,
                    raw=raw.get("errors") or raw.get("result") or raw,
                )
                await state.emit(failure_event(state.failure, "result:error"))
                return
            try:
                state.result = parse_agent_result(raw.get("structured_output") or raw.get("result"))
            except (ValueError, json.JSONDecodeError, ValidationError) as exc:
                state.failure = failure(
                    AdapterFailureKind.AGENT_ERROR,
                    "Claude 返回值不符合 AgentResult",
                    retryable=False,
                    raw=exc,
                )
                await state.emit(failure_event(state.failure, "result:error"))
                return
            payload = AgentCompletedPayload.model_validate({"result": state.result})
            await state.emit(AdapterEvent.create("result:success", "agent.completed", payload))
            return
        event = self.mapper.map(event_type, raw)
        if event:
            await state.emit(event)

    async def _fail_path_violation(
        self,
        state: AdapterSessionState,
        violations: list[str],
        raw: dict[str, Any],
        tool_name: str = "",
    ) -> None:
        state.failure = failure(
            AdapterFailureKind.PATH_VIOLATION,
            f"Claude 用工具 {tool_name or '<unknown>'} 访问了越界路径",
            retryable=False,
            raw=raw,
            violation_paths=violations,
        )
        state.expected_termination = True
        await state.emit(failure_event(state.failure, "result:error"))
        await self._force_stop(state)

    async def _drain_stderr(self, state: AdapterSessionState) -> None:
        process = state.process
        if process is None or process.stderr is None:
            return
        try:
            while await process.stderr.readline():
                pass
        except Exception as exc:
            cleaned = process.returncode is not None
            if process.returncode is None:
                try:
                    cleaned = await terminate_process_tree(process)
                except Exception:
                    cleaned = False
            if state.stream_end is not None:
                return
            state.failure = failure(
                AdapterFailureKind.TRANSPORT_ERROR,
                "Claude stderr 读取失败，已清理专属进程树"
                if cleaned
                else "Claude stderr 读取失败，专属进程树清理未确认",
                retryable=False,
                raw={"channel": "stderr", "exceptionType": type(exc).__name__, "processTreeCleaned": cleaned},
            )
            await state.finish(
                AdapterStreamEnd.model_validate(
                    {
                        "status": AdapterStreamStatus.AGENT_EXITED,
                        "endedAt": utc_timestamp(),
                        "resumable": False,
                        "detail": (
                            f"stderr reader failed ({type(exc).__name__}); "
                            f"processTreeCleaned={str(cleaned).lower()}"
                        ),
                    }
                )
            )

    async def _force_stop(self, state: AdapterSessionState) -> None:
        process = state.process
        if process is None or process.returncode is not None:
            return
        await terminate_process_tree(process)

    @staticmethod
    async def _join_tasks(state: AdapterSessionState) -> None:
        tasks = [task for task in (state.reader_task, state.stderr_task) if task is not None]
        if tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=3)
            except TimeoutError:
                for task in tasks:
                    task.cancel()

    @staticmethod
    def _cancel_result(
        outcome: CancelOutcome,
        started: float,
        detail: str,
        *,
        orphan_pids: list[int] | None = None,
    ) -> CancelResult:
        return CancelResult.model_validate(
            {
                "outcome": outcome,
                "completedAt": utc_timestamp(),
                "elapsedMs": int((time.monotonic() - started) * 1000),
                "detail": detail,
                "orphanProcessIds": orphan_pids or [],
            }
        )
