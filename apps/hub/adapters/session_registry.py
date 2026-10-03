from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from protocol.generated.python import (
    AdapterFailure,
    AdapterStreamEnd,
    AgentResult,
    AgentTaskSpec,
)

from adapters.events import AdapterEvent
from adapters.path_guard import PathGuard


STREAM_END = object()


@dataclass(slots=True)
class PendingApproval:
    approval_id: str
    external_request_id: str
    request_id: int | str
    method: str
    resolved: bool = False
    agent_timed_out: bool = False


@dataclass(slots=True)
class AdapterSessionState:
    session_id: str
    external_session_id: str
    spec: AgentTaskSpec
    guard: PathGuard
    process: Any | None = None
    connection: Any | None = None
    reader_task: asyncio.Task[Any] | None = None
    stderr_task: asyncio.Task[Any] | None = None
    queue: asyncio.Queue[AdapterEvent | AdapterStreamEnd | object] = field(
        default_factory=asyncio.Queue
    )
    result: AgentResult | None = None
    failure: AdapterFailure | None = None
    stream_end: AdapterStreamEnd | None = None
    active_turn_id: str | None = None
    expected_termination: bool = False
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    approvals: dict[str, PendingApproval] = field(default_factory=dict)
    vendor_items: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_agent_message: str | None = None
    started_emitted: bool = False

    async def emit(self, value: AdapterEvent | AdapterStreamEnd) -> None:
        await self.queue.put(value)

    async def finish(self, end: AdapterStreamEnd) -> None:
        if self.stream_end is not None:
            return
        self.stream_end = end
        self.finished.set()
        await self.queue.put(end)
        await self.queue.put(STREAM_END)


class SessionRegistry:
    def __init__(self) -> None:
        self._items: dict[str, AdapterSessionState] = {}

    def add(self, state: AdapterSessionState) -> None:
        if state.session_id in self._items:
            raise ValueError(f"重复的 Hub Session：{state.session_id}")
        self._items[state.session_id] = state

    def get(self, session_id: str) -> AdapterSessionState | None:
        return self._items.get(session_id)

    def values(self) -> tuple[AdapterSessionState, ...]:
        return tuple(self._items.values())

    def forget_finished(self, session_id: str) -> None:
        """Forget an exclusively owned stopped session without issuing a cancel."""
        state = self._items.get(session_id)
        if state is None:
            return
        if not state.finished.is_set() or (state.process is not None and state.process.returncode is None):
            raise ValueError('session termination is not confirmed')
        self._items.pop(session_id, None)
