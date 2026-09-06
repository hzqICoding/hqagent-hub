from __future__ import annotations

import asyncio
import functools
from datetime import datetime, timezone
from typing import Any

from protocol.generated.python import (
    AdapterStreamEnd,
    AgentResult,
    AgentSessionHandle,
    AgentTaskSpec,
    ApprovalDispatch,
    ApprovalView,
    CancelMode,
    CancelOutcome,
    CancelRequest,
    CancelResult,
    HubEvent,
    PROTOCOL_VERSION,
    ResumeRequest,
    SessionView,
)

from orchestrator.domain import AgentCandidate, RuntimeEventDraft


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def async_test(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))

    return wrapped


def agent(
    instance_id: str,
    *,
    status: str = "ready",
    capabilities: tuple[str, ...] = ("file_write", "structured_output"),
    automatically_selectable: bool = True,
    adapter_id: str = "test-adapter",
) -> AgentCandidate:
    return AgentCandidate(
        instance_id=instance_id,
        adapter_id=adapter_id,
        display_name=instance_id,
        status=status,
        capabilities=frozenset(capabilities),
        automatically_selectable=automatically_selectable,
    )


class FakeEventSink:
    def __init__(self) -> None:
        self.events: list[HubEvent] = []

    async def append(self, draft: RuntimeEventDraft) -> HubEvent:
        event = HubEvent.model_validate(
            {
                "eventId": f"evt_{len(self.events) + 1}",
                "seq": len(self.events) + 1,
                "occurredAt": now(),
                "aggregateType": draft.aggregate_type,
                "aggregateId": draft.aggregate_id,
                "type": draft.type,
                "payload": draft.payload,
                "protocolVersion": PROTOCOL_VERSION,
                "taskId": draft.task_id,
                "nodeId": draft.node_id,
                "roleId": draft.role_id,
                "agentInstanceId": draft.agent_instance_id,
                "adapterId": draft.adapter_id,
            }
        )
        self.events.append(event)
        return event

    async def load_task_events(self, task_id: str, after_seq: int = 0) -> list[HubEvent]:
        return [
            event
            for event in self.events
            if event.task_id == task_id and event.seq > after_seq
        ]


class FakeSessionRepository:
    def __init__(self) -> None:
        self.items: dict[str, SessionView] = {}

    async def get(self, session_id: str) -> SessionView | None:
        return self.items.get(session_id)

    async def save(self, session: SessionView) -> None:
        self.items[session.id] = session

    async def list(self, query: dict[str, Any]) -> list[SessionView]:
        values = list(self.items.values())
        if query.get("taskId"):
            values = [item for item in values if item.task_id == query["taskId"]]
        return values


class FakeApprovalRepository:
    def __init__(self) -> None:
        self.items: dict[str, ApprovalView] = {}

    async def get(self, approval_id: str) -> ApprovalView | None:
        return self.items.get(approval_id)

    async def save(self, approval: ApprovalView) -> None:
        self.items[approval.id] = approval

    async def list(self, query: dict[str, Any]) -> list[ApprovalView]:
        values = list(self.items.values())
        if query.get("status"):
            values = [item for item in values if item.status.value == query["status"]]
        return values


class FakeAdapter:
    def __init__(self) -> None:
        self.started: list[AgentTaskSpec] = []
        self.resumed: list[ResumeRequest] = []
        self.approvals: list[ApprovalDispatch] = []
        self.cancels: list[CancelRequest] = []
        self.handle = AgentSessionHandle.model_validate(
            {
                "sessionId": "session_new",
                "externalSessionId": "external_new",
                "adapterId": "test-adapter",
                "startedAt": now(),
                "supportsResume": True,
            }
        )
        self.result = AgentResult.model_validate(
            {"status": "done", "summary": "done", "changedFiles": []}
        )
        self.cancel_results = {
            CancelMode.GRACEFUL: CancelResult.model_validate(
                {"outcome": "stopped_gracefully", "completedAt": now()}
            ),
            CancelMode.FORCE: CancelResult.model_validate(
                {"outcome": "force_killed", "completedAt": now()}
            ),
        }
        self.hang_graceful = False

    async def detect(self) -> Any:
        return None

    async def health(self) -> Any:
        return None

    async def start(self, spec: AgentTaskSpec) -> AgentSessionHandle:
        self.started.append(spec)
        return self.handle

    async def resume(self, request: ResumeRequest) -> None:
        self.resumed.append(request)

    async def approve(self, dispatch: ApprovalDispatch) -> None:
        self.approvals.append(dispatch)

    async def cancel(self, request: CancelRequest) -> CancelResult:
        self.cancels.append(request)
        if request.mode == CancelMode.GRACEFUL and self.hang_graceful:
            await asyncio.sleep(3600)
        return self.cancel_results[request.mode]

    async def collect_result(self, session_id: str) -> AgentResult:
        return self.result

    async def stream_events(self, session_id: str):
        if False:
            yield AdapterStreamEnd.model_validate({"status": "ended", "endedAt": now()})


class FakeAdapterDirectory:
    def __init__(self, candidates: tuple[AgentCandidate, ...], adapter: FakeAdapter | None = None) -> None:
        self.candidates = candidates
        self.adapter = adapter or FakeAdapter()

    async def list_candidates(self) -> tuple[AgentCandidate, ...]:
        return self.candidates

    def adapter_for(self, agent_instance_id: str) -> FakeAdapter:
        if agent_instance_id not in {item.instance_id for item in self.candidates}:
            raise KeyError(agent_instance_id)
        return self.adapter
