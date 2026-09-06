from protocol.generated.python import AdapterFailure, AgentResult, CancelMode, CancelResult, FileChange, ResolveSource, SessionPurpose, TaskStatus

from orchestrator.catalog import BuiltinCatalog
from orchestrator.domain import ProfileSnapshot, ResolutionGap, RoleBinding
from orchestrator.role_resolver import RoleResolver
from orchestrator.runtime import DispatchOutcome, NodeDispatchRequest, WorkflowRuntime
from orchestrator.sessions import SessionManager
from orchestrator.tests.fakes import (
    FakeAdapter,
    FakeAdapterDirectory,
    FakeEventSink,
    FakeSessionRepository,
    agent,
    async_test,
    now,
)
from security.permissions import PermissionEngine


def build_runtime(candidates, adapter: FakeAdapter | None = None):
    catalog = BuiltinCatalog.load()
    directory = FakeAdapterDirectory(tuple(candidates), adapter)
    sessions = SessionManager(FakeSessionRepository(), directory)
    events = FakeEventSink()
    runtime = WorkflowRuntime(
        RoleResolver(catalog),
        PermissionEngine(catalog),
        sessions,
        directory,
        events,
    )
    return runtime, directory.adapter, events


def request(candidates, **overrides):
    values = {
        "task_id": "task",
        "node_id": "node",
        "workspace_id": "workspace",
        "workspace_name": "workspace",
        "role_id": "general_implementer",
        "objective": "implement",
        "agents": tuple(candidates),
        "allowed_paths": ("apps/hub/orchestrator/**",),
        "requires_approval": (),
        "session_purpose": SessionPurpose.IMPLEMENT,
    }
    values.update(overrides)
    return NodeDispatchRequest(**values)


@async_test
async def test_dispatch_emits_truthful_node_resolved_and_role_only_task_spec() -> None:
    primary = agent("primary", status="offline")
    fallback = agent("fallback")
    runtime, adapter, events = build_runtime((primary, fallback))
    workspace = ProfileSnapshot(
        profile_id="workspace",
        scope="workspace",
        bindings={
            "general_implementer": RoleBinding(
                primary_agent_id="primary",
                fallback_agent_ids=("fallback",),
            )
        },
    )

    outcome = await runtime.dispatch(
        request((primary, fallback), workspace_profile=workspace)
    )

    assert isinstance(outcome, DispatchOutcome)
    assert outcome.resolution.source == ResolveSource.FALLBACK
    assert events.events[0].type == "node.resolved"
    assert events.events[0].payload["resolveSource"] == "fallback"
    assert events.events[0].payload["isFallback"] is True
    assert events.events[0].payload["fallbackReason"]
    assert str(adapter.started[0].role_id) == "general_implementer"
    assert "fallback" not in adapter.started[0].objective
    assert adapter.started[0].allowed_paths == ["apps/hub/orchestrator/**"]


@async_test
async def test_approval_capability_gate_runs_before_adapter_start() -> None:
    candidate = agent("no-tool-approval")
    runtime, adapter, _ = build_runtime((candidate,))

    result = await runtime.dispatch(
        request((candidate,), requires_approval=("git_push",))
    )

    assert isinstance(result, ResolutionGap)
    assert result.missing_capabilities == ("tool_approval",)
    assert adapter.started == []


@async_test
async def test_collect_result_detects_post_run_path_violation() -> None:
    candidate = agent("agent")
    adapter = FakeAdapter()
    adapter.result = AgentResult.model_validate(
        {
            "status": "done",
            "summary": "changed files",
            "changedFiles": [
                {"path": "apps/hub/orchestrator/runtime.py", "changeKind": "modified"},
                {"path": "apps/hub/core/ports.py", "changeKind": "modified"},
            ],
        }
    )
    runtime, _, events = build_runtime((candidate,), adapter)
    outcome = await runtime.dispatch(request((candidate,)))
    assert isinstance(outcome, DispatchOutcome)

    completed = await runtime.collect_result(outcome)

    assert completed.violation_paths == ("apps/hub/core/ports.py",)
    assert completed.session.status.value == "closed"
    assert [event.type for event in events.events][-2:] == ["task.path_violation", "task.failed"]


@async_test
async def test_cancel_refused_is_failed_not_cancelled() -> None:
    candidate = agent("agent")
    adapter = FakeAdapter()
    adapter.cancel_results[CancelMode.GRACEFUL] = CancelResult.model_validate(
        {
            "outcome": "refused",
            "completedAt": now(),
            "detail": "no interrupt endpoint",
            "orphanProcessIds": [123],
        }
    )
    runtime, _, events = build_runtime((candidate,), adapter)
    outcome = await runtime.dispatch(request((candidate,)))
    assert isinstance(outcome, DispatchOutcome)

    cancelled = await runtime.cancel(outcome, reason="user requested", grace_seconds=1)

    assert cancelled.task_status.value == "failed"
    assert cancelled.session_status.value == "active"
    assert [event.type for event in events.events][-2:] == ["agent.failed", "task.failed"]


@async_test
async def test_graceful_timeout_escalates_to_force() -> None:
    candidate = agent("agent")
    adapter = FakeAdapter()
    adapter.hang_graceful = True
    runtime, _, _ = build_runtime((candidate,), adapter)
    outcome = await runtime.dispatch(request((candidate,)))
    assert isinstance(outcome, DispatchOutcome)

    cancelled = await runtime.cancel(outcome, reason="timeout", grace_seconds=0)

    assert [item.mode for item in adapter.cancels] == [CancelMode.GRACEFUL, CancelMode.FORCE]
    assert cancelled.result.outcome.value == "force_killed"
    assert cancelled.task_status.value == "cancelled"


@async_test
async def test_same_agent_reviewer_uses_new_session_and_rereads_diff() -> None:
    candidate = agent("agent", capabilities=("structured_output",))
    runtime, adapter, _ = build_runtime((candidate,))

    outcome = await runtime.dispatch(
        request(
            (candidate,),
            role_id="reviewer",
            allowed_paths=(),
            session_purpose=SessionPurpose.REVIEW,
            implementation_agent_id="agent",
            review_context_paths=(".hqagent/handoffs/implementation.diff",),
            acceptance=("pytest -q",),
        )
    )

    assert isinstance(outcome, DispatchOutcome)
    assert outcome.session_plan.forced_isolation is True
    assert outcome.session.reuse_policy.value == "new_session"
    assert adapter.started[0].read_first == [".hqagent/handoffs/implementation.diff"]
    assert adapter.started[0].acceptance == ["pytest -q"]


@async_test
async def test_agent_side_approval_timeout_is_reported_as_agent_error() -> None:
    candidate = agent("agent")
    runtime, _, events = build_runtime((candidate,))
    outcome = await runtime.dispatch(request((candidate,)))
    assert isinstance(outcome, DispatchOutcome)

    await runtime.record_adapter_failure(
        outcome,
        AdapterFailure.model_validate(
            {
                "kind": "agent_error",
                "message": "Agent 侧工具审批超时，Agent 已停止等待",
                "retryable": False,
            }
        ),
        previous_status=TaskStatus.WAITING_APPROVAL,
    )

    failed = events.events[-2]
    assert failed.type == "agent.failed"
    assert failed.payload["blockers"][0]["detail"]["agentSideTimeout"] is True
    assert events.events[-1].type == "task.failed"
    assert "Agent 侧" in events.events[-1].payload["reason"]
