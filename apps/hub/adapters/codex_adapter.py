from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
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
    ApprovalDecision,
    ApprovalDispatch,
    ApprovalRequiredPayload,
    AuthKind,
    CancelMode,
    CancelOutcome,
    CancelRequest,
    CancelResult,
    CapabilityId,
    DangerousAction,
    DeclaredCapability,
    ResumeRequest,
    RiskLevel,
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
from adapters.event_mapper import EventMapper
from adapters.events import AdapterEvent, diagnostic_raw, utc_timestamp
from adapters.failures import failure, failure_event, parse_agent_result, version_tuple
from adapters.path_guard import PathGuard
from adapters.process import ProcessRunner, command_environment, executable_args
from adapters.prompt import build_task_prompt
from adapters.session_registry import (
    AdapterSessionState,
    PendingApproval,
    STREAM_END,
    SessionRegistry,
)


MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]
DisconnectHandler = Callable[[bool, str], Awaitable[None]]


class _CodexConnection:
    def __init__(
        self,
        process: asyncio.subprocess.Process,
        *,
        on_notification: MessageHandler,
        on_server_request: MessageHandler,
        on_disconnect: DisconnectHandler,
    ) -> None:
        self.process = process
        self.on_notification = on_notification
        self.on_server_request = on_server_request
        self.on_disconnect = on_disconnect
        self._next_id = 1
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._write_lock = asyncio.Lock()
        self.reader_task = asyncio.create_task(self._reader())
        self.stderr_task = asyncio.create_task(self._drain_stderr())

    async def request(
        self, method: str, params: dict[str, Any], *, timeout: float = 20
    ) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self._write({"id": request_id, "method": method, "params": params})
        try:
            message = await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(request_id, None)
        if "error" in message:
            raise RuntimeError(json.dumps(message["error"], ensure_ascii=False))
        result = message.get("result")
        return result if isinstance(result, dict) else {}

    async def respond(self, request_id: int | str, result: dict[str, Any]) -> None:
        await self._write({"id": request_id, "result": result})

    async def force_close(self) -> None:
        if self.process.returncode is None:
            self.process.kill()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=2)
            except TimeoutError:
                return

    async def _write(self, value: dict[str, Any]) -> None:
        if self.process.stdin is None or self.process.returncode is not None:
            raise BrokenPipeError("Codex App Server stdin 已关闭")
        data = (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        async with self._write_lock:
            self.process.stdin.write(data)
            await self.process.stdin.drain()

    async def _reader(self) -> None:
        assert self.process.stdout is not None
        try:
            while line := await self.process.stdout.readline():
                try:
                    message = json.loads(line.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    continue
                request_id = message.get("id")
                if request_id is not None and ("result" in message or "error" in message):
                    future = self._pending.get(request_id)
                    if future is not None and not future.done():
                        future.set_result(message)
                    continue
                if request_id is not None and "method" in message:
                    asyncio.create_task(self.on_server_request(message))
                    continue
                if "method" in message:
                    await self.on_notification(message)
            returncode = await self.process.wait()
            await self.on_disconnect(False, f"exitCode={returncode}")
        except Exception as exc:
            await self.on_disconnect(self.process.returncode is None, str(exc))
        finally:
            error = BrokenPipeError("Codex App Server 已断开")
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(error)

    async def _drain_stderr(self) -> None:
        if self.process.stderr is None:
            return
        while await self.process.stderr.readline():
            pass


class CodexAdapter(AgentAdapter):
    adapter_id = "codex"
    display_name = "Codex"
    minimum_version = "0.153.4"
    vendor_event_mappings = tuple(
        VendorEventMapping.model_validate(item)
        for item in (
            {"vendorType": "thread/started", "unifiedType": "agent.started"},
            {"vendorType": "thread/status/changed", "unifiedType": "agent.progress"},
            {"vendorType": "turn/started", "unifiedType": "agent.progress"},
            {
                "vendorType": "item/started:userMessage",
                "unifiedType": "agent.progress",
                "dropped": True,
            },
            {
                "vendorType": "item/completed:userMessage",
                "unifiedType": "agent.progress",
                "dropped": True,
            },
            {"vendorType": "item/started:agentMessage", "unifiedType": "agent.progress"},
            {"vendorType": "item/completed:agentMessage", "unifiedType": "agent.progress"},
            {"vendorType": "item/started:commandExecution", "unifiedType": "agent.tool_call"},
            {"vendorType": "item/completed:commandExecution", "unifiedType": "agent.tool_call"},
            {"vendorType": "item/started:fileChange", "unifiedType": "agent.tool_call"},
            {"vendorType": "item/completed:fileChange", "unifiedType": "agent.tool_call"},
            {"vendorType": "item/agentMessage/delta", "unifiedType": "agent.progress"},
            {"vendorType": "item/commandExecution/outputDelta", "unifiedType": "agent.progress"},
            {"vendorType": "item/fileChange/outputDelta", "unifiedType": "agent.progress"},
            {
                "vendorType": "item/commandExecution/requestApproval",
                "unifiedType": "approval.required",
            },
            {
                "vendorType": "item/fileChange/requestApproval",
                "unifiedType": "approval.required",
            },
            {"vendorType": "error", "unifiedType": "agent.progress"},
            {"vendorType": "turn/completed:success", "unifiedType": "agent.completed"},
            {"vendorType": "turn/completed:failed", "unifiedType": "agent.failed"},
            {
                "vendorType": "skills/changed",
                "unifiedType": "agent.progress",
                "dropped": True,
            },
            {"vendorType": "serverRequest/resolved", "unifiedType": "agent.progress"},
            {
                "vendorType": "__unknown__",
                "unifiedType": "agent.progress",
                "note": "未知 Codex 通知降级为诊断进度",
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
            CapabilityId.SHELL: True,
            CapabilityId.FILE_WRITE: True,
            CapabilityId.GIT_WORKTREE: True,
            CapabilityId.SESSION_RESUME: True,
            CapabilityId.STREAMING_EVENTS: True,
            CapabilityId.TOOL_APPROVAL: True,
            CapabilityId.STRUCTURED_OUTPUT: True,
            CapabilityId.VISION: False,
            CapabilityId.BROWSER: False,
        }
        notes = {
            CapabilityId.VISION: "AgentTaskSpec 没有图片输入字段，本轮不声明",
            CapabilityId.BROWSER: "本轮 App Server Adapter 不配置浏览器工具",
        }
        return [
            DeclaredCapability(
                id=item,
                supported=bool(enabled and supported[item]),
                note=None if enabled and supported[item] else notes.get(item, "Agent 未安装或版本不兼容"),
            )
            for item in CapabilityId
        ]

    async def detect(self) -> DetectResult:
        executable = self.runner.find("codex")
        if not executable:
            return AdapterDescriptor.model_validate(
                {
                    "adapterId": self.adapter_id,
                    "displayName": self.display_name,
                    "integrationKind": AdapterIntegrationKind.SDK,
                    "authKind": AuthKind.LOCAL_LOGIN,
                    "supportedPlatforms": [AdapterPlatform.WINDOWS],
                    "installed": False,
                    "minimumVersion": self.minimum_version,
                    "capabilities": self._capabilities(False),
                    "detectedAt": utc_timestamp(),
                }
            )
        try:
            probe = await self.runner.run(executable_args(executable, "--version"), timeout=10)
        except (OSError, TimeoutError) as exc:
            return failure(
                AdapterFailureKind.TRANSPORT_ERROR,
                "Codex 版本探测失败",
                retryable=True,
                raw=exc,
            )
        version = probe.stdout.strip() or probe.stderr.strip()
        compatible = probe.returncode == 0 and version_tuple(version) >= version_tuple(self.minimum_version)
        return AdapterDescriptor.model_validate(
            {
                "adapterId": self.adapter_id,
                "displayName": self.display_name,
                "integrationKind": AdapterIntegrationKind.SDK,
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
        executable = self.runner.find("codex")
        if not executable:
            return failure(AdapterFailureKind.NOT_INSTALLED, "未找到 Codex CLI", retryable=False)
        started = time.monotonic()
        try:
            probe = await self.runner.run(
                executable_args(executable, "login", "status"), timeout=10
            )
        except (OSError, TimeoutError) as exc:
            return failure(
                AdapterFailureKind.TRANSPORT_ERROR,
                "Codex 登录态探测失败",
                retryable=True,
                raw=exc,
            )
        latency = int((time.monotonic() - started) * 1000)
        output = (probe.stdout + "\n" + probe.stderr).strip()
        if probe.returncode != 0 or "not logged in" in output.lower():
            return AdapterHealth.model_validate(
                {
                    "status": AgentStatus.NOT_LOGGED_IN,
                    "checkedAt": utc_timestamp(),
                    "latencyMs": latency,
                    "authValid": False,
                    "diagnosticMessage": "请先运行 codex login",
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
        state = AdapterSessionState(
            session_id=f"session_{uuid.uuid4().hex}",
            external_session_id=spec.resume_session_id or "",
            spec=spec,
            guard=PathGuard(spec.worktree_path or "", spec.allowed_paths),
        )
        opened = await self._open_turn(
            state,
            build_task_prompt(spec),
            resume=spec.reuse_policy is not SessionReusePolicy.NEW_SESSION,
        )
        if isinstance(opened, AdapterFailure):
            return opened
        self.registry.add(state)
        return AgentSessionHandle.model_validate(
            {
                "sessionId": state.session_id,
                "externalSessionId": state.external_session_id,
                "adapterId": self.adapter_id,
                "startedAt": utc_timestamp(),
                "supportsResume": True,
                "workingDirectory": spec.worktree_path,
            }
        )

    async def _preflight(self, spec: AgentTaskSpec) -> AdapterFailure | None:
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
            return failure(AdapterFailureKind.NOT_INSTALLED, "未找到 Codex CLI", retryable=False)
        if version_tuple(descriptor.detected_version or "") < version_tuple(self.minimum_version):
            return failure(
                AdapterFailureKind.VERSION_INCOMPATIBLE,
                f"Codex 版本低于最低实测版本 {self.minimum_version}",
                retryable=False,
            )
        health = await self.health()
        if isinstance(health, AdapterFailure):
            return health
        if health.status is AgentStatus.NOT_LOGGED_IN:
            return failure(
                AdapterFailureKind.NOT_LOGGED_IN,
                "Codex 未登录，请先运行 codex login",
                retryable=False,
            )
        return None

    async def _open_turn(
        self, state: AdapterSessionState, message: str, *, resume: bool
    ) -> None | AdapterFailure:
        executable = self.runner.find("codex")
        if not executable:
            return failure(AdapterFailureKind.NOT_INSTALLED, "未找到 Codex CLI", retryable=False)
        try:
            process = await self.runner.start(
                executable_args(executable, "app-server", "--listen", "stdio://"),
                cwd=state.spec.worktree_path or "",
                env=command_environment("codex"),
            )
            state.process = process
            connection = _CodexConnection(
                process,
                on_notification=lambda value: self._handle_notification(state, value),
                on_server_request=lambda value: self._handle_server_request(state, value),
                on_disconnect=lambda alive, detail: self._handle_disconnect(state, alive, detail),
            )
            state.connection = connection
            await connection.request(
                "initialize",
                {
                    "clientInfo": {"name": "hqagent-hub", "version": "0.1.0"},
                    "capabilities": {},
                },
            )
            if resume:
                thread_result = await connection.request(
                    "thread/resume",
                    {
                        "threadId": state.external_session_id,
                        "cwd": state.spec.worktree_path,
                        "approvalPolicy": "on-request",
                        "sandbox": "read-only",
                        "excludeTurns": True,
                    },
                )
            else:
                thread_result = await connection.request(
                    "thread/start",
                    {
                        "cwd": state.spec.worktree_path,
                        "approvalPolicy": "on-request",
                        "sandbox": "read-only",
                        "ephemeral": False,
                        "experimentalRawEvents": False,
                    },
                )
            thread = thread_result.get("thread", {})
            external_id = thread.get("id")
            if not external_id or (resume and external_id != state.external_session_id):
                raise RuntimeError("Codex 没有返回预期 thread.id")
            state.external_session_id = str(external_id)
            await self._emit_started(state)
            turn_result = await connection.request(
                "turn/start",
                {
                    "threadId": state.external_session_id,
                    "input": [{"type": "text", "text": message}],
                    "outputSchema": AgentResult.model_json_schema(by_alias=True),
                },
            )
            state.active_turn_id = str(turn_result.get("turn", {}).get("id") or "") or None
            state.ready.set()
            return None
        except (OSError, TimeoutError, RuntimeError, BrokenPipeError) as exc:
            if state.connection is not None:
                state.expected_termination = True
                await state.connection.force_close()
            return failure(
                AdapterFailureKind.TRANSPORT_ERROR,
                "Codex App Server 启动或建线程失败",
                retryable=True,
                raw=exc,
            )

    async def resume(self, request: ResumeRequest) -> OperationResult:
        state = self.registry.get(request.session_id)
        if state is None:
            return failure(
                AdapterFailureKind.AGENT_ERROR,
                "Hub Session 不存在，不能猜测 --last",
                retryable=False,
            )
        if request.external_session_id and request.external_session_id != state.external_session_id:
            return failure(
                AdapterFailureKind.AGENT_ERROR,
                "externalSessionId 与已登记 thread.id 不一致",
                retryable=False,
            )
        if state.process is not None and state.process.returncode is None and not state.finished.is_set():
            return failure(AdapterFailureKind.AGENT_ERROR, "Codex turn 仍在运行", retryable=False)
        state.queue = asyncio.Queue()
        state.result = None
        state.failure = None
        state.stream_end = None
        state.active_turn_id = None
        state.expected_termination = False
        state.ready = asyncio.Event()
        state.finished = asyncio.Event()
        state.approvals.clear()
        state.vendor_items.clear()
        state.last_agent_message = None
        state.started_emitted = False
        return await self._open_turn(state, request.message, resume=True)

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
        for state in self.registry.values():
            pending = state.approvals.get(dispatch.approval_id)
            if pending is None and dispatch.external_request_id:
                pending = next(
                    (
                        item
                        for item in state.approvals.values()
                        if item.external_request_id == dispatch.external_request_id
                    ),
                    None,
                )
            if pending is None:
                continue
            if pending.agent_timed_out or pending.resolved or state.connection is None:
                return failure(
                    AdapterFailureKind.AGENT_ERROR,
                    "Codex Agent 侧审批请求已超时或放弃",
                    retryable=False,
                )
            decision = "accept" if dispatch.decision is ApprovalDecision.APPROVE else "decline"
            try:
                await state.connection.respond(pending.request_id, {"decision": decision})
            except (OSError, BrokenPipeError) as exc:
                pending.agent_timed_out = True
                return failure(
                    AdapterFailureKind.AGENT_ERROR,
                    "Codex Agent 侧审批请求已超时或连接已关闭",
                    retryable=False,
                    raw=exc,
                )
            pending.resolved = True
            return None
        return failure(
            AdapterFailureKind.AGENT_ERROR,
            "找不到对应的 Codex 审批请求",
            retryable=False,
        )

    async def cancel(self, request: CancelRequest) -> CancelResult:
        started = time.monotonic()
        state = self.registry.get(request.session_id)
        if state is None:
            return self._cancel_result(CancelOutcome.NOT_FOUND, started, "Hub Session 不存在")
        if state.finished.is_set() or not state.active_turn_id:
            return self._cancel_result(CancelOutcome.ALREADY_FINISHED, started, "Codex turn 已结束")
        connection = state.connection
        if connection is None:
            pid = state.process.pid if state.process and state.process.returncode is None else None
            return self._cancel_result(
                CancelOutcome.REFUSED,
                started,
                "Codex App Server 连接不可用",
                orphan_pids=[pid] if pid else [],
            )
        if request.mode is CancelMode.GRACEFUL:
            grace = float(request.grace_seconds or 0)
            deadline = time.monotonic() + grace
            state.expected_termination = True
            try:
                await asyncio.wait_for(
                    connection.request(
                        "turn/interrupt",
                        {"threadId": state.external_session_id, "turnId": state.active_turn_id},
                        timeout=max(grace, 0.001),
                    ),
                    timeout=max(grace, 0.001),
                )
            except (TimeoutError, RuntimeError, BrokenPipeError) as exc:
                state.expected_termination = False
                pid = state.process.pid if state.process and state.process.returncode is None else None
                return self._cancel_result(
                    CancelOutcome.REFUSED,
                    started,
                    f"Codex 拒绝或无法接收 graceful interrupt：{type(exc).__name__}",
                    orphan_pids=[pid] if pid else [],
                )
            remaining = max(0.0, deadline - time.monotonic())
            try:
                await asyncio.wait_for(state.finished.wait(), timeout=remaining)
            except TimeoutError:
                pid = state.process.pid if state.process and state.process.returncode is None else None
                return self._cancel_result(
                    CancelOutcome.REFUSED,
                    started,
                    "Codex 未在 Hub 指定的 graceSeconds 内停止",
                    orphan_pids=[pid] if pid else [],
                )
            return self._cancel_result(
                CancelOutcome.STOPPED_GRACEFULLY,
                started,
                "Codex turn 已由 turn/interrupt 停止",
            )
        state.expected_termination = True
        await connection.force_close()
        if state.stream_end is None:
            state.failure = failure(
                AdapterFailureKind.CANCELLED,
                "Codex App Server 已被 force kill",
                retryable=False,
            )
            await state.finish(
                AdapterStreamEnd.model_validate(
                    {
                        "status": AdapterStreamStatus.ENDED,
                        "endedAt": utc_timestamp(),
                        "resumable": False,
                        "detail": "force killed",
                    }
                )
            )
        pid = state.process.pid if state.process and state.process.returncode is None else None
        return self._cancel_result(
            CancelOutcome.FORCE_KILLED,
            started,
            "Codex App Server 已执行 force kill",
            orphan_pids=[pid] if pid else [],
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
                "Codex 尚未产生结构化结果",
                retryable=not state.finished.is_set(),
            )
        violations = state.guard.validate_changes(state.result.changed_files)
        if violations:
            return failure(
                AdapterFailureKind.PATH_VIOLATION,
                "Codex 结果包含越界文件",
                retryable=False,
                violation_paths=violations,
            )
        return state.result

    async def _emit_started(self, state: AdapterSessionState) -> None:
        if state.started_emitted:
            return
        state.started_emitted = True
        payload = AgentStartedPayload.model_validate(
            {
                "sessionId": state.session_id,
                "externalSessionId": state.external_session_id,
                "purpose": state.spec.session_purpose,
                "reusePolicy": state.spec.reuse_policy,
                "worktreePath": state.spec.worktree_path,
                "branch": state.spec.branch,
            }
        )
        await state.emit(AdapterEvent.create("thread/started", "agent.started", payload))

    async def _handle_notification(
        self, state: AdapterSessionState, message: dict[str, Any]
    ) -> None:
        method = str(message.get("method", "__unknown__"))
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        if method == "thread/started":
            await self._emit_started(state)
            return
        if method == "turn/started":
            turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
            state.active_turn_id = str(turn.get("id") or state.active_turn_id or "") or None
            await state.emit(
                AdapterEvent.create(
                    method,
                    "agent.progress",
                    AgentProgressPayload.model_validate(
                        {"message": "Codex turn 已开始", "raw": diagnostic_raw(params)}
                    ),
                )
            )
            return
        if method in {"item/started", "item/completed"}:
            item = params.get("item") if isinstance(params.get("item"), dict) else {}
            item_id = str(item.get("id", ""))
            if item_id:
                state.vendor_items[item_id] = item
            await self._handle_item(state, method, item)
            return
        if method == "item/agentMessage/delta":
            delta = str(params.get("delta", ""))
            state.last_agent_message = (state.last_agent_message or "") + delta
            if delta:
                await state.emit(
                    AdapterEvent.create(
                        method,
                        "agent.progress",
                        AgentProgressPayload.model_validate(
                            {"message": delta, "raw": diagnostic_raw(params)}
                        ),
                    )
                )
            return
        if method in {"item/commandExecution/outputDelta", "item/fileChange/outputDelta"}:
            await state.emit(
                AdapterEvent.create(
                    method,
                    "agent.progress",
                    AgentProgressPayload.model_validate(
                        {
                            "message": str(params.get("delta") or method)[:1000],
                            "raw": diagnostic_raw(params),
                        }
                    ),
                )
            )
            return
        if method == "error":
            will_retry = bool(params.get("willRetry"))
            error_value = params.get("error") if isinstance(params.get("error"), dict) else {}
            message_text = str(error_value.get("message") or "Codex error")
            if will_retry:
                await state.emit(
                    AdapterEvent.create(
                        method,
                        "agent.progress",
                        AgentProgressPayload.model_validate(
                            {"message": message_text, "raw": diagnostic_raw(params)}
                        ),
                    )
                )
            else:
                state.failure = failure(
                    AdapterFailureKind.AGENT_ERROR,
                    message_text,
                    retryable=False,
                    raw=params,
                )
                await state.emit(failure_event(state.failure, "turn/completed:failed"))
            return
        if method == "serverRequest/resolved":
            request_id = str(params.get("requestId") or params.get("id") or "")
            for pending in state.approvals.values():
                if pending.external_request_id == request_id and not pending.resolved:
                    pending.agent_timed_out = True
                    state.failure = failure(
                        AdapterFailureKind.AGENT_ERROR,
                        "Codex Agent 侧审批请求已超时或放弃",
                        retryable=False,
                    )
                    await state.emit(failure_event(state.failure, "turn/completed:failed"))
            return
        if method == "turn/completed":
            await self._complete_turn(state, params)
            return
        event = self.mapper.map(method, params)
        if event:
            await state.emit(event)

    async def _handle_item(
        self, state: AdapterSessionState, method: str, item: dict[str, Any]
    ) -> None:
        item_type = str(item.get("type", "unknown"))
        vendor_type = f"{method}:{item_type}"
        if item_type == "userMessage":
            self.mapper.map(vendor_type, item)
            return
        if item_type == "agentMessage":
            text = str(item.get("text") or item.get("message") or "")
            if text:
                state.last_agent_message = text
            await state.emit(
                AdapterEvent.create(
                    vendor_type,
                    "agent.progress",
                    AgentProgressPayload.model_validate(
                        {"message": text or "Codex 生成消息", "raw": diagnostic_raw(item)}
                    ),
                )
            )
            return
        if item_type in {"commandExecution", "fileChange", "mcpToolCall"}:
            tool_name = item_type
            summary = str(
                item.get("command")
                or item.get("path")
                or item.get("server")
                or item.get("status")
                or ""
            )
            await state.emit(
                AdapterEvent.create(
                    vendor_type,
                    "agent.tool_call",
                    AgentToolCallPayload.model_validate(
                        {
                            "toolName": tool_name,
                            "argumentsExcerpt": summary[:512] or None,
                            "resultSummary": str(item.get("aggregatedOutput") or "")[:512] or None,
                            "failed": str(item.get("status", "")).lower() in {"failed", "declined"},
                        }
                    ),
                )
            )
            return
        event = self.mapper.map(vendor_type, item)
        if event:
            await state.emit(event)

    async def _handle_server_request(
        self, state: AdapterSessionState, message: dict[str, Any]
    ) -> None:
        method = str(message.get("method", ""))
        request_id = message.get("id")
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        connection = state.connection
        if request_id is None or connection is None:
            return
        if method == "item/fileChange/requestApproval":
            item = state.vendor_items.get(str(params.get("itemId", "")), {})
            paths = list(PathGuard._extract_paths(item))
            violations = state.guard.violations(paths) if paths else ["<unknown file change path>"]
            if violations:
                await connection.respond(request_id, {"decision": "cancel"})
                await self._fail_path_violation(state, violations, params)
            else:
                await connection.respond(request_id, {"decision": "accept"})
            return
        if method == "item/commandExecution/requestApproval":
            command = str(params.get("command") or "")
            violations = state.guard.inspect_tool_call("shell", {"command": command})
            if violations:
                await connection.respond(request_id, {"decision": "cancel"})
                await self._fail_path_violation(state, violations, params)
                return
            action = self._dangerous_action(command)
            if state.spec.requires_approval and action in state.spec.requires_approval:
                approval_id = f"approval_{uuid.uuid4().hex}"
                external_request_id = str(request_id)
                pending = PendingApproval(
                    approval_id=approval_id,
                    external_request_id=external_request_id,
                    request_id=request_id,
                    method=method,
                )
                state.approvals[approval_id] = pending
                payload = ApprovalRequiredPayload.model_validate(
                    {
                        "approvalId": approval_id,
                        "action": action,
                        "targetResource": command[:512] or "Codex command",
                        "riskLevel": RiskLevel.HIGH,
                    }
                )
                await state.emit(
                    AdapterEvent.create(
                        method,
                        "approval.required",
                        payload,
                        external_request_id=external_request_id,
                    )
                )
                return
            await connection.respond(request_id, {"decision": "accept"})
            return
        await connection.respond(request_id, {})

    async def _complete_turn(self, state: AdapterSessionState, params: dict[str, Any]) -> None:
        turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
        status = str(turn.get("status", "failed"))
        state.active_turn_id = None
        unresolved = [item for item in state.approvals.values() if not item.resolved]
        if unresolved and not state.expected_termination:
            for item in unresolved:
                item.agent_timed_out = True
            state.failure = failure(
                AdapterFailureKind.AGENT_ERROR,
                "Codex Agent 侧审批请求已超时或放弃",
                retryable=False,
            )
        elif status == "completed":
            try:
                state.result = parse_agent_result(state.last_agent_message or "")
            except (ValueError, json.JSONDecodeError, ValidationError) as exc:
                state.failure = failure(
                    AdapterFailureKind.AGENT_ERROR,
                    "Codex 返回值不符合 AgentResult",
                    retryable=False,
                    raw=exc,
                )
        elif status == "interrupted":
            state.failure = failure(
                AdapterFailureKind.CANCELLED,
                "Codex turn 已中断",
                retryable=False,
            )
        else:
            state.failure = failure(
                AdapterFailureKind.AGENT_ERROR,
                f"Codex turn 失败：{status}",
                retryable=False,
                raw=turn.get("error"),
            )
        if state.result is not None and state.failure is None:
            await state.emit(
                AdapterEvent.create(
                    "turn/completed:success",
                    "agent.completed",
                    AgentCompletedPayload.model_validate({"result": state.result}),
                )
            )
        elif state.failure is not None:
            await state.emit(failure_event(state.failure, "turn/completed:failed"))
        await state.finish(
            AdapterStreamEnd.model_validate(
                {
                    "status": AdapterStreamStatus.ENDED,
                    "endedAt": utc_timestamp(),
                    "resumable": False,
                    "detail": f"turn.status={status}",
                }
            )
        )
        state.expected_termination = True
        if state.connection is not None:
            await state.connection.force_close()

    async def _handle_disconnect(
        self, state: AdapterSessionState, alive: bool, detail: str
    ) -> None:
        if state.stream_end is not None:
            return
        if state.expected_termination:
            await state.finish(
                AdapterStreamEnd.model_validate(
                    {
                        "status": AdapterStreamStatus.ENDED,
                        "endedAt": utc_timestamp(),
                        "resumable": False,
                        "detail": detail[:512],
                    }
                )
            )
            return
        state.failure = failure(
            AdapterFailureKind.TRANSPORT_ERROR if alive else AdapterFailureKind.AGENT_ERROR,
            "Codex App Server transport 丢失" if alive else "Codex App Server 进程已退出",
            retryable=alive,
            raw=detail,
        )
        await state.finish(
            AdapterStreamEnd.model_validate(
                {
                    "status": AdapterStreamStatus.TRANSPORT_LOST if alive else AdapterStreamStatus.AGENT_EXITED,
                    "endedAt": utc_timestamp(),
                    "resumable": alive,
                    "detail": detail[:512],
                }
            )
        )

    async def _fail_path_violation(
        self, state: AdapterSessionState, violations: list[str], raw: dict[str, Any]
    ) -> None:
        state.failure = failure(
            AdapterFailureKind.PATH_VIOLATION,
            "Codex 写入前路径检查拒绝了越界操作",
            retryable=False,
            raw=raw,
            violation_paths=violations,
        )
        await state.emit(failure_event(state.failure, "turn/completed:failed"))
        await state.finish(
            AdapterStreamEnd.model_validate(
                {
                    "status": AdapterStreamStatus.ENDED,
                    "endedAt": utc_timestamp(),
                    "resumable": False,
                    "detail": "path violation rejected before write",
                }
            )
        )
        state.expected_termination = True
        if state.connection is not None:
            await state.connection.force_close()

    @staticmethod
    def _dangerous_action(command: str) -> DangerousAction:
        value = command.lower()
        if "git push" in value:
            return DangerousAction.GIT_PUSH
        if "git merge" in value or "git rebase" in value:
            return DangerousAction.GIT_MERGE
        if any(item in value for item in ("remove-item", " del ", " rm ", " rmdir ")):
            return DangerousAction.DELETE
        if any(item in value for item in ("curl ", "wget ", "invoke-webrequest", "ssh ")):
            return DangerousAction.NETWORK
        if "migrate" in value:
            return DangerousAction.DB_MIGRATE
        if any(item in value for item in ("deploy", "publish", "release")):
            return DangerousAction.DEPLOY
        return DangerousAction.SHELL

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
