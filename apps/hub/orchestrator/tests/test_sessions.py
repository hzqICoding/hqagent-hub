from datetime import datetime, timezone

import pytest
from protocol.generated.python import (
    AdapterStreamEnd,
    AgentSessionHandle,
    SessionPurpose,
    SessionReusePolicy,
    SessionStatus,
)

from orchestrator.errors import InvalidTaskActionError, SessionNotResumableError
from orchestrator.sessions import SessionLifecycle, SessionManager
from orchestrator.tests.fakes import FakeAdapterDirectory, FakeSessionRepository, agent, async_test, now


@pytest.fixture
def session_manager() -> tuple[SessionManager, FakeSessionRepository]:
    repository = FakeSessionRepository()
    directory = FakeAdapterDirectory((agent("agent"),))
    manager = SessionManager(
        repository,
        directory,
        clock=lambda: datetime(2026, 9, 6, 12, tzinfo=timezone.utc),
    )
    return manager, repository


async def create_session(
    manager: SessionManager,
    session_id: str,
    *,
    external_session_id: str = "external",
    supports_resume: bool = True,
):
    return await manager.create_active(
        handle=AgentSessionHandle.model_validate(
            {
                "sessionId": session_id,
                "externalSessionId": external_session_id,
                "adapterId": "test-adapter",
                "startedAt": now(),
                "supportsResume": supports_resume,
            }
        ),
        workspace_id="workspace",
        workspace_name="workspace",
        role_id="general_implementer",
        agent_instance_id="agent",
        agent_display_name="agent",
        purpose=SessionPurpose.IMPLEMENT,
        reuse_policy=SessionReusePolicy.NEW_SESSION,
        task_id=f"task_{session_id}",
        node_id=f"node_{session_id}",
    )


@async_test
async def test_new_tasks_create_distinct_sessions(session_manager) -> None:
    manager, _ = session_manager
    first = await create_session(manager, "session_1")
    second = await create_session(manager, "session_2")

    assert first.id != second.id
    assert first.task_id != second.task_id


@async_test
async def test_invalid_is_irreversible_and_distinct_from_closed(session_manager) -> None:
    manager, repository = session_manager
    active = await create_session(manager, "session_invalid")
    invalid = SessionLifecycle.transition(active, SessionStatus.INVALID, now=now())
    await repository.save(invalid)

    with pytest.raises(InvalidTaskActionError):
        SessionLifecycle.transition(invalid, SessionStatus.ACTIVE, now=now())
    with pytest.raises(SessionNotResumableError) as error:
        await manager.plan(
            reuse_policy=SessionReusePolicy.RESUME_EXPLICIT,
            resume_session_id=invalid.id,
            agent_instance_id="agent",
            role_id="general_implementer",
        )
    assert "断开失效" in error.value.message

    other = await create_session(manager, "session_closed", supports_resume=False, external_session_id="")
    closed = await manager.close(other.id)
    assert closed.status == SessionStatus.CLOSED
    assert invalid.status == SessionStatus.INVALID


@async_test
async def test_transport_loss_keeps_active_but_agent_exit_invalidates(session_manager) -> None:
    manager, _ = session_manager
    active = await create_session(manager, "session_stream")

    transport_lost = await manager.apply_stream_end(
        active.id,
        AdapterStreamEnd.model_validate(
            {"status": "transport_lost", "endedAt": now(), "resumable": True}
        ),
    )
    assert transport_lost.status == SessionStatus.ACTIVE

    agent_exited = await manager.apply_stream_end(
        active.id,
        AdapterStreamEnd.model_validate(
            {"status": "agent_exited", "endedAt": now(), "detail": "process exited"}
        ),
    )
    assert agent_exited.status == SessionStatus.INVALID
    assert agent_exited.is_valid is False


@async_test
async def test_resume_requires_explicit_non_latest_id(session_manager) -> None:
    manager, _ = session_manager
    for session_id in (None, "latest"):
        with pytest.raises(SessionNotResumableError):
            await manager.plan(
                reuse_policy=SessionReusePolicy.RESUME_EXPLICIT,
                resume_session_id=session_id,
                agent_instance_id="agent",
                role_id="general_implementer",
            )


@async_test
async def test_same_agent_review_forces_isolated_new_session(session_manager) -> None:
    manager, _ = session_manager
    plan = await manager.plan(
        reuse_policy=SessionReusePolicy.CONTINUE_LINEAGE,
        resume_session_id="some-session",
        agent_instance_id="agent",
        role_id="reviewer",
        implementation_agent_id="agent",
    )
    assert plan.reuse_policy == SessionReusePolicy.NEW_SESSION
    assert plan.forced_isolation is True
