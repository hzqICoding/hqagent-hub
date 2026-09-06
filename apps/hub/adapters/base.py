from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from protocol.generated.python import (
    AdapterDescriptor,
    AdapterFailure,
    AdapterHealth,
    AdapterStreamEnd,
    AgentResult,
    AgentSessionHandle,
    AgentTaskSpec,
    ApprovalDispatch,
    CancelRequest,
    CancelResult,
    ResumeRequest,
    VendorEventMapping,
)

from adapters.events import AdapterEvent
from adapters.session_registry import SessionRegistry


DetectResult = AdapterDescriptor | AdapterFailure
HealthResult = AdapterHealth | AdapterFailure
StartResult = AgentSessionHandle | AdapterFailure
OperationResult = None | AdapterFailure
CollectResult = AgentResult | AdapterFailure
StreamItem = AdapterEvent | AdapterStreamEnd


class AgentAdapter(ABC):
    adapter_id: str
    vendor_event_mappings: tuple[VendorEventMapping, ...]

    def __init__(self, *, registry: SessionRegistry | None = None) -> None:
        self.registry = registry or SessionRegistry()

    @abstractmethod
    async def detect(self) -> DetectResult: ...

    @abstractmethod
    async def health(self) -> HealthResult: ...

    @abstractmethod
    async def start(self, spec: AgentTaskSpec) -> StartResult: ...

    @abstractmethod
    async def resume(self, request: ResumeRequest) -> OperationResult: ...

    @abstractmethod
    def stream_events(self, session_id: str) -> AsyncIterator[StreamItem]: ...

    @abstractmethod
    async def approve(self, dispatch: ApprovalDispatch) -> OperationResult: ...

    @abstractmethod
    async def cancel(self, request: CancelRequest) -> CancelResult: ...

    @abstractmethod
    async def collect_result(self, session_id: str) -> CollectResult: ...

    # 契约原文使用 camelCase；Python 消费方可用这两个无歧义别名。
    def streamEvents(self, session_id: str) -> AsyncIterator[StreamItem]:  # noqa: N802
        return self.stream_events(session_id)

    async def collectResult(self, session_id: str) -> CollectResult:  # noqa: N802
        return await self.collect_result(session_id)
