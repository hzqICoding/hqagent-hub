from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from protocol.generated.python import (
    AdapterFailure,
    AdapterFailureKind,
    AdapterHealth,
    AdapterStreamStatus,
    AgentResult,
    AgentTaskSpec,
    ApprovalDecision,
    ApprovalDispatch,
    CancelMode,
    CancelOutcome,
    CancelRequest,
    DangerousAction,
    ResumeRequest,
    SessionPurpose,
    SessionReusePolicy,
    VendorEventMapping,
)

from adapters.claude_adapter import ClaudeAdapter
from adapters.codex_adapter import CodexAdapter
from adapters.event_mapper import EventMapper, FROZEN_EVENT_TYPES
from adapters.events import diagnostic_raw
from adapters.path_guard import PathGuard
from adapters.process import CommandResult
from adapters.session_registry import AdapterSessionState, PendingApproval


def task_spec(
    root: Path,
    *,
    purpose: SessionPurpose = SessionPurpose.IMPLEMENT,
    reuse: SessionReusePolicy = SessionReusePolicy.NEW_SESSION,
    resume_id: str | None = None,
    requires_approval: list[DangerousAction] | None = None,
) -> AgentTaskSpec:
    return AgentTaskSpec.model_validate(
        {
            # 裁决 D25：sessionId 由 Hub 生成后传入，Adapter 不得自行生成
            "sessionId": f"session_{uuid.uuid4().hex}",
            "taskId": f"task_{uuid.uuid4().hex}",
            "nodeId": f"node_{uuid.uuid4().hex}",
            "workspaceId": "workspace_test",
            "roleId": "reviewer" if purpose is SessionPurpose.REVIEW else "general_implementer",
            "objective": "完成测试任务",
            "worktreePath": str(root),
            "allowedPaths": ["apps/hub/adapters/**"],
            "sessionPurpose": purpose,
            "reusePolicy": reuse,
            "resumeSessionId": resume_id,
            "requiresApproval": requires_approval,
        }
    )


def state_for(root: Path, *, session_id: str = "session_test") -> AdapterSessionState:
    spec = task_spec(root)
    return AdapterSessionState(
        session_id=session_id,
        external_session_id=f"external_{session_id}",
        spec=spec,
        guard=PathGuard(str(root), spec.allowed_paths),
    )


class FakeProcess:
    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid
        self.returncode: int | None = None
        self.killed = False

    def kill(self) -> None:
        self.killed = True
        self.returncode = 137

    async def wait(self) -> int:
        return self.returncode or 0


def test_diagnostics_do_not_forward_private_reasoning_or_credentials():
    result = diagnostic_raw({"content": [{"type": "thinking", "thinking": "PRIVATE_REASONING_MARKER"},
        {"type": "text", "text": "public summary"}], "authorization": "Bearer PRIVATE_TOKEN_MARKER"})
    assert "PRIVATE_REASONING_MARKER" not in result["vendor"]
    assert "PRIVATE_TOKEN_MARKER" not in result["vendor"]
    assert "public summary" in result["vendor"]


def test_codex_failure_preserves_rate_limit_cause(tmp_path):
    async def scenario():
        adapter = CodexAdapter()
        state = state_for(tmp_path)
        await adapter._complete_turn(state, {"turn": {"status": "failed", "error": {"message": "429 Too Many Requests"}}})
        assert "429" in state.failure.message
        assert state.failure.retryable is True
        assert state.finished.is_set()
    asyncio.run(scenario())


class FakeConnection:
    def __init__(self, state: AdapterSessionState | None = None) -> None:
        self.state = state
        self.requests: list[tuple[str, dict[str, Any], float]] = []
        self.responses: list[tuple[int | str, dict[str, Any]]] = []
        self.force_closed = False

    async def request(
        self, method: str, params: dict[str, Any], *, timeout: float
    ) -> dict[str, Any]:
        self.requests.append((method, params, timeout))
        if self.state is not None:
            self.state.finished.set()
        return {}

    async def respond(self, request_id: int | str, result: dict[str, Any]) -> None:
        self.responses.append((request_id, result))

    async def force_close(self) -> None:
        self.force_closed = True


class ProbeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def find(self, command: str) -> str:
        return f"C:/probe/{command}.exe"

    async def run(self, args: list[str], **_kwargs: Any) -> CommandResult:
        self.calls.append(tuple(args))
        if "--version" in args:
            return CommandResult(0, "2.1.263 (Claude Code)\n", "")
        return CommandResult(0, '{"loggedIn":true}', "")


class StartableCodex(CodexAdapter):
    async def _preflight(self, _spec: AgentTaskSpec) -> AdapterFailure | None:
        return None

    async def _open_turn(
        self, state: AdapterSessionState, _message: str, *, resume: bool
    ) -> AdapterFailure | None:
        if not resume:
            state.external_session_id = f"thread_{uuid.uuid4().hex}"
        state.active_turn_id = f"turn_{uuid.uuid4().hex}"
        await self._emit_started(state)
        return None


def test_both_adapters_implement_all_eight_port_methods() -> None:
    methods = {
        "detect",
        "health",
        "start",
        "resume",
        "stream_events",
        "approve",
        "cancel",
        "collect_result",
    }
    for adapter_type in (ClaudeAdapter, CodexAdapter):
        for name in methods:
            assert callable(getattr(adapter_type, name, None)), f"{adapter_type.__name__}.{name}"
        assert inspect.isasyncgenfunction(adapter_type.stream_events)

def test_d20_detect_and_health_are_separate_probes() -> None:
    async def scenario() -> None:
        runner = ProbeRunner()
        adapter = ClaudeAdapter(runner=runner)

        descriptor = await adapter.detect()
        assert not isinstance(descriptor, AdapterFailure)
        assert len(runner.calls) == 1
        assert "--version" in runner.calls[0]

        health = await adapter.health()
        assert isinstance(health, AdapterHealth)
        assert len(runner.calls) == 2
        assert ("auth", "status", "--json") == runner.calls[1][-3:]

    asyncio.run(scenario())


def test_d17_claude_reports_refused_then_force_killed_without_extending_grace(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        adapter = ClaudeAdapter()
        state = state_for(tmp_path)
        state.process = FakeProcess()
        adapter.registry.add(state)

        started = time.monotonic()
        graceful = await adapter.cancel(
            CancelRequest(sessionId=state.session_id, mode=CancelMode.GRACEFUL, graceSeconds=30)
        )
        assert graceful.outcome is CancelOutcome.REFUSED
        assert graceful.orphan_process_ids == [4242]
        assert time.monotonic() - started < 1

        forced = await adapter.cancel(
            CancelRequest(sessionId=state.session_id, mode=CancelMode.FORCE)
        )
        assert forced.outcome is CancelOutcome.FORCE_KILLED
        assert state.process.killed is True
        assert forced.orphan_process_ids == []

    asyncio.run(scenario())


def test_d17_codex_graceful_interrupt_uses_hub_grace_deadline(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = CodexAdapter()
        state = state_for(tmp_path)
        state.process = FakeProcess()
        state.active_turn_id = "turn_1"
        connection = FakeConnection(state)
        state.connection = connection
        adapter.registry.add(state)

        result = await adapter.cancel(
            CancelRequest(sessionId=state.session_id, mode=CancelMode.GRACEFUL, graceSeconds=2)
        )

        assert result.outcome is CancelOutcome.STOPPED_GRACEFULLY
        assert connection.requests[0][0] == "turn/interrupt"
        assert connection.requests[0][2] <= 2
        assert result.elapsed_ms < 2000

    asyncio.run(scenario())


def test_d18_transport_lost_and_agent_exited_are_distinct(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = CodexAdapter()
        transport = state_for(tmp_path, session_id="session_transport")
        exited = state_for(tmp_path, session_id="session_exited")

        await adapter._handle_disconnect(transport, True, "pipe broke")
        await adapter._handle_disconnect(exited, False, "exitCode=1")

        assert transport.stream_end is not None
        assert transport.stream_end.status is AdapterStreamStatus.TRANSPORT_LOST
        assert transport.stream_end.resumable is True
        assert exited.stream_end is not None
        assert exited.stream_end.status is AdapterStreamStatus.AGENT_EXITED
        assert exited.stream_end.resumable is False

    asyncio.run(scenario())


def test_d19_agent_side_approval_timeout_is_agent_error_and_hub_time_is_not_rechecked(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        adapter = CodexAdapter()
        state = state_for(tmp_path)
        state.connection = FakeConnection()
        pending = PendingApproval(
            approval_id="approval_1",
            external_request_id="19",
            request_id=19,
            method="item/commandExecution/requestApproval",
            agent_timed_out=True,
        )
        state.approvals[pending.approval_id] = pending
        adapter.registry.add(state)

        result = await adapter.approve(
            ApprovalDispatch.model_validate(
                {
                    "approvalId": "approval_1",
                    "externalRequestId": "19",
                    "decision": ApprovalDecision.APPROVE,
                    "decidedAt": "2000-01-01T00:00:00Z",
                }
            )
        )

        assert isinstance(result, AdapterFailure)
        assert result.kind is AdapterFailureKind.AGENT_ERROR
        assert "Agent 侧" in result.message

    asyncio.run(scenario())


def test_d21_mapping_is_frozen_and_drops_are_counted_not_silent() -> None:
    mapper = EventMapper(
        [
            VendorEventMapping(
                vendorType="noise", unifiedType="agent.progress", dropped=True
            ),
            VendorEventMapping(
                vendorType="progress", unifiedType="agent.progress", dropped=False
            ),
        ]
    )

    assert mapper.map("noise", {"value": 1}) is None
    assert mapper.dropped_counts == {"noise": 1}
    unknown = mapper.map("new_vendor_event", {"secret": "x" * 5000})
    assert unknown is not None
    assert unknown.unified_type == "agent.progress"
    assert len(unknown.payload.raw["vendor"]) <= 2048
    assert mapper.dropped_counts["__unknown__"] == 1
    assert all(
        item.unified_type in FROZEN_EVENT_TYPES
        for item in ClaudeAdapter.vendor_event_mappings + CodexAdapter.vendor_event_mappings
    )


def test_d22_codex_rejects_out_of_scope_file_before_approval(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = CodexAdapter()
        state = state_for(tmp_path)
        connection = FakeConnection()
        state.connection = connection
        state.vendor_items["item_1"] = {
            "id": "item_1",
            "type": "fileChange",
            "changes": [{"path": "apps/hub/core/forbidden.py"}],
        }

        await adapter._handle_server_request(
            state,
            {
                "id": 7,
                "method": "item/fileChange/requestApproval",
                "params": {"itemId": "item_1", "threadId": "thread", "turnId": "turn"},
            },
        )

        assert connection.responses == [(7, {"decision": "cancel"})]
        assert state.failure is not None
        assert state.failure.kind is AdapterFailureKind.PATH_VIOLATION
        assert state.failure.violation_paths == ["apps/hub/core/forbidden.py"]

    asyncio.run(scenario())


def test_d22_collect_result_keeps_post_write_validation_as_second_gate(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = ClaudeAdapter()
        state = state_for(tmp_path)
        state.result = AgentResult.model_validate(
            {
                "status": "done",
                "summary": "done",
                "changedFiles": [
                    {"path": "apps/hub/core/forbidden.py", "changeKind": "modified"}
                ],
            }
        )
        adapter.registry.add(state)

        result = await adapter.collect_result(state.session_id)
        assert isinstance(result, AdapterFailure)
        assert result.kind is AdapterFailureKind.PATH_VIOLATION
        assert result.violation_paths == ["apps/hub/core/forbidden.py"]

    asyncio.run(scenario())


def test_new_implement_and_review_tasks_use_isolated_sessions(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = StartableCodex()
        implement = await adapter.start(task_spec(tmp_path, purpose=SessionPurpose.IMPLEMENT))
        review = await adapter.start(task_spec(tmp_path, purpose=SessionPurpose.REVIEW))

        assert not isinstance(implement, AdapterFailure)
        assert not isinstance(review, AdapterFailure)
        assert implement.session_id != review.session_id
        assert implement.external_session_id != review.external_session_id
        implement_state = adapter.registry.get(implement.session_id)
        review_state = adapter.registry.get(review.session_id)
        assert implement_state is not None
        assert review_state is not None
        implement_event = await implement_state.queue.get()
        review_event = await review_state.queue.get()
        assert implement_event.payload.purpose is SessionPurpose.IMPLEMENT
        assert review_event.payload.purpose is SessionPurpose.REVIEW

    asyncio.run(scenario())


def test_explicit_resume_requires_exact_external_id_and_never_uses_latest(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        adapter = StartableCodex()
        invalid = await adapter.start(
            task_spec(tmp_path, reuse=SessionReusePolicy.RESUME_EXPLICIT, resume_id=None)
        )
        assert isinstance(invalid, AdapterFailure)
        assert "resumeSessionId" in invalid.message

        missing = await adapter.resume(
            ResumeRequest(sessionId="missing", externalSessionId=None, message="继续")
        )
        assert isinstance(missing, AdapterFailure)
        assert "--last" in missing.message

    asyncio.run(scenario())


def test_read_only_tools_are_not_checked_against_the_writable_allowlist(tmp_path) -> None:
    """只读工具只校验 worktree 边界，不校验可写白名单。

    D22 要求写入前拦下越界路径。但 inspect_tool_call 原来对任何工具都提取
    path/file_path 去比对可写白名单，而 Read / Grep / Glob 的入参里同样有
    这些字段——于是只读角色（reviewer 的 writablePaths 是空的）连要复核的
    文件都打不开，一 Read 就被判越界。集成时 reviewer 节点就是这么失败的。
    """
    from adapters.path_guard import PathGuard

    (tmp_path / "backend").mkdir()
    target = tmp_path / "backend" / "x.txt"
    target.write_text("hi", encoding="utf-8")
    guard = PathGuard(str(tmp_path), [])  # 只读角色：可写白名单为空

    assert guard.inspect_tool_call("Read", {"file_path": str(target)}) == []
    assert guard.inspect_tool_call("Grep", {"path": str(tmp_path / "backend")}) == []


def test_read_outside_the_worktree_is_still_blocked(tmp_path) -> None:
    """越界读同样是信息泄漏，不能因为「只是读」就放行。"""
    from adapters.path_guard import PathGuard

    guard = PathGuard(str(tmp_path), [])
    assert guard.inspect_tool_call("Read", {"file_path": "C:/Windows/System32/config/SAM"})


def test_unknown_tools_are_treated_as_writes(tmp_path) -> None:
    """名单外的工具一律按写处理。

    不认识的工具宁可误拦，也不能让一个能写的工具因为没被列进只读名单
    就绕过可写白名单——这个方向错了就是安全漏洞。
    """
    from adapters.path_guard import PathGuard

    (tmp_path / "backend").mkdir()
    guard = PathGuard(str(tmp_path), [])
    assert guard.inspect_tool_call("SomeBrandNewTool", {"path": str(tmp_path / "backend" / "z.txt")})
