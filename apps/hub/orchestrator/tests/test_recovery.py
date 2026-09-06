from protocol.generated.python import PROTOCOL_VERSION, HubEvent

from orchestrator.recovery import TaskEventReducer, TaskRecoveryService
from orchestrator.tests.fakes import FakeEventSink, async_test, now


def event(seq: int, event_type: str, payload: dict, *, aggregate_type: str = "task") -> HubEvent:
    return HubEvent.model_validate(
        {
            "eventId": f"event_{seq}",
            "seq": seq,
            "occurredAt": now(),
            "aggregateType": aggregate_type,
            "aggregateId": "task",
            "taskId": "task",
            "nodeId": "node",
            "roleId": "general_implementer",
            "agentInstanceId": "agent",
            "adapterId": "test-adapter",
            "type": event_type,
            "payload": payload,
            "protocolVersion": PROTOCOL_VERSION,
        }
    )


def recovery_events() -> list[HubEvent]:
    return [
        event(1, "task.created", {"objective": "work", "workspaceId": "ws", "profileId": "p"}),
        event(
            2,
            "node.resolved",
            {
                "roleId": "general_implementer",
                "resolvedAgentId": "agent",
                "resolvedAgentName": "Agent",
                "resolveSource": "fallback",
                "isFallback": True,
                "fallbackReason": "primary offline",
            },
        ),
        event(
            3,
            "agent.started",
            {"sessionId": "session", "externalSessionId": "external"},
        ),
        event(
            4,
            "approval.required",
            {"approvalId": "approval", "action": "git_push"},
            aggregate_type="approval",
        ),
        event(
            5,
            "approval.resolved",
            {"approvalId": "approval", "decision": "approve"},
            aggregate_type="approval",
        ),
        event(
            6,
            "agent.completed",
            {"result": {"changedFiles": [{"path": "apps/hub/orchestrator/runtime.py"}]}},
        ),
        event(7, "task.completed", {"from": "running", "to": "succeeded"}),
    ]


def test_reducer_rebuilds_task_after_interruption() -> None:
    reducer = TaskEventReducer()
    first_half = reducer.rebuild("task", recovery_events()[:4])
    assert first_half.status == "waiting_approval"
    assert first_half.pending_approval_id == "approval"

    recovered = reducer.rebuild("task", recovery_events()[4:], first_half)
    assert recovered.status == "succeeded"
    assert recovered.last_seq == 7
    assert recovered.nodes["node"].resolve_source == "fallback"
    assert recovered.nodes["node"].is_fallback is True
    assert recovered.nodes["node"].changed_files == ("apps/hub/orchestrator/runtime.py",)


@async_test
async def test_recovery_service_only_loads_events_after_checkpoint() -> None:
    sink = FakeEventSink()
    sink.events = recovery_events()
    reducer = TaskEventReducer()
    checkpoint = reducer.rebuild("task", recovery_events()[:3])

    recovered = await TaskRecoveryService(sink, reducer).recover("task", checkpoint)
    assert recovered.status == "succeeded"
    assert recovered.last_seq == 7
