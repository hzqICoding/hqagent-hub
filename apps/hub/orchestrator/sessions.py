from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from protocol.generated.python import (
    AdapterStreamEnd,
    AdapterStreamStatus,
    AdapterFailure,
    AgentSessionHandle,
    CancelOutcome,
    CancelResult,
    ResumeRequest,
    SessionPurpose,
    SessionReusePolicy,
    SessionStatus,
    SessionView,
)

from .errors import AdapterStartFailedError, InvalidTaskActionError, SessionNotResumableError
from .ports import AdapterDirectoryPort, SessionRepositoryPort


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class SessionPlan:
    reuse_policy: SessionReusePolicy
    resume_session: SessionView | None = None
    forced_isolation: bool = False


class SessionLifecycle:
    _ALLOWED = {
        SessionStatus.ACTIVE: {
            SessionStatus.IDLE,
            SessionStatus.CLOSED,
            SessionStatus.INVALID,
        },
        SessionStatus.IDLE: {
            SessionStatus.ACTIVE,
            SessionStatus.CLOSED,
            SessionStatus.INVALID,
        },
        SessionStatus.CLOSED: set(),
        SessionStatus.INVALID: set(),
    }

    @classmethod
    def transition(cls, session: SessionView, target: SessionStatus, *, now: str) -> SessionView:
        if target == session.status:
            return session
        if target not in cls._ALLOWED[session.status]:
            raise InvalidTaskActionError(
                f"非法 Session 状态迁移：{session.status.value} -> {target.value}",
                sessionId=session.id,
                current=session.status.value,
                target=target.value,
            )
        return session.model_copy(
            update={
                "status": target,
                "last_used_at": now,
                "is_valid": False if target == SessionStatus.INVALID else session.is_valid,
            }
        )

    @classmethod
    def on_stream_end(
        cls,
        session: SessionView,
        stream_end: AdapterStreamEnd,
        *,
        now: str,
    ) -> SessionView:
        if stream_end.status == AdapterStreamStatus.TRANSPORT_LOST:
            return session
        if stream_end.status == AdapterStreamStatus.AGENT_EXITED:
            return cls.transition(session, SessionStatus.INVALID, now=now)
        if stream_end.status == AdapterStreamStatus.ENDED:
            target = SessionStatus.IDLE if session.is_valid else SessionStatus.CLOSED
            return cls.transition(session, target, now=now)
        return session


class SessionManager:
    def __init__(
        self,
        repository: SessionRepositoryPort,
        adapters: AdapterDirectoryPort,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.repository = repository
        self.adapters = adapters
        self.clock = clock
        self._locks: dict[str, asyncio.Lock] = {}

    async def plan(
        self,
        *,
        reuse_policy: SessionReusePolicy,
        resume_session_id: str | None,
        agent_instance_id: str,
        role_id: str,
        implementation_agent_id: str | None = None,
    ) -> SessionPlan:
        if role_id == "reviewer" and implementation_agent_id == agent_instance_id:
            return SessionPlan(SessionReusePolicy.NEW_SESSION, forced_isolation=True)
        if reuse_policy == SessionReusePolicy.NEW_SESSION:
            return SessionPlan(reuse_policy)
        if not resume_session_id or resume_session_id.lower() == "latest":
            raise SessionNotResumableError(
                resume_session_id or "",
                "恢复会话必须提供明确的 Hub 本地 Session ID，禁止使用 latest",
            )
        session = await self.repository.get(resume_session_id)
        if session is None:
            raise SessionNotResumableError(resume_session_id, "指定 Session 不存在")
        if session.status == SessionStatus.INVALID:
            raise SessionNotResumableError(resume_session_id, "Session 已断开失效，不能续接；请开启新话题，原生对话需另建对话")
        if session.status == SessionStatus.CLOSED:
            raise SessionNotResumableError(resume_session_id, "Session 已正常结束，不能继续")
        if session.status != SessionStatus.IDLE or not session.is_valid:
            raise SessionNotResumableError(resume_session_id, "Session 当前不可恢复")
        if session.agent_instance_id != agent_instance_id:
            raise SessionNotResumableError(resume_session_id, "Session 与本次解析出的 Agent 不一致")
        return SessionPlan(reuse_policy, resume_session=session)

    async def create_active(
        self,
        *,
        handle: AgentSessionHandle,
        workspace_id: str,
        workspace_name: str,
        role_id: str,
        agent_instance_id: str,
        agent_display_name: str,
        purpose: SessionPurpose,
        reuse_policy: SessionReusePolicy,
        task_id: str,
        node_id: str,
        parent_session_id: str | None = None,
        root_task_id: str | None = None,
    ) -> SessionView:
        # 裁决 D28：externalSessionId 现在是可选的。原来用空字符串顶替，
        # 让前端分不清「这个 Agent 不支持恢复」和「支持但凭据丢了」——
        # 而 Session 页那个「继续」按钮该不该出现，正取决于这个区别。
        external_session_id = handle.external_session_id or None
        value = SessionView.model_validate(
            {
                "id": handle.session_id,
                "status": SessionStatus.ACTIVE.value,
                "workspaceId": workspace_id,
                "workspaceName": workspace_name,
                "roleId": role_id,
                "agentInstanceId": agent_instance_id,
                "agentDisplayName": agent_display_name,
                "adapterId": handle.adapter_id,
                "externalSessionId": external_session_id,
                "purpose": purpose.value,
                "reusePolicy": reuse_policy.value,
                "taskId": task_id,
                "nodeId": node_id,
                "parentSessionId": parent_session_id,
                "rootTaskId": root_task_id or task_id,
                "createdAt": handle.started_at,
                "lastUsedAt": handle.started_at,
                "isValid": bool(handle.supports_resume and external_session_id),
                "turnCount": 1,
            }
        )
        await self.repository.save(value)
        return value

    async def resume(self, session: SessionView, message: str, acceptance: list[str] | None, *, input_attachments=None) -> SessionView:
        lock = self._locks.setdefault(session.id, asyncio.Lock())
        async with lock:
            current = await self.repository.get(session.id)
            if current is None:
                raise SessionNotResumableError(session.id, "指定 Session 不存在")
            if current.status != SessionStatus.IDLE or not current.is_valid:
                raise SessionNotResumableError(session.id, "Session 当前不可恢复或已有活跃执行")
            spec = await self.repository.get_spec(session.id)
            if spec is None:
                raise SessionNotResumableError(
                    session.id,
                    "Session 缺少持久化 AgentTaskSpec，无法可靠重建 Adapter 状态",
                )
            adapter = self.adapters.adapter_for(current.agent_instance_id)
            if input_attachments is not None:
                from protocol.generated.python import AgentTaskSpec
                spec = AgentTaskSpec.model_validate({**spec.model_dump(mode='json',by_alias=True), 'inputAttachments':input_attachments or None})
                await self.repository.save_spec(session.id, spec)
            native = getattr(getattr(self.repository, "database", None), "native_service", None)
            if native is not None:
                await native.acquire_session(current.id, message)
            result = await adapter.resume(
                ResumeRequest.model_validate(
                    {
                        "sessionId": current.id,
                        "externalSessionId": current.external_session_id,
                        "message": message,
                        "acceptance": acceptance,
                        "taskSpec": spec.model_dump(mode="json", by_alias=True, exclude_none=True),
                    }
                )
            )
            if isinstance(result, AdapterFailure):
                raise AdapterStartFailedError(result)
            active = SessionLifecycle.transition(
                current,
                SessionStatus.ACTIVE,
                now=timestamp(self.clock()),
            ).model_copy(update={"turn_count": (current.turn_count or 0) + 1})
            await self.repository.save(active)
            return active

    async def apply_stream_end(self, session_id: str, stream_end: AdapterStreamEnd) -> SessionView:
        session = await self.repository.get(session_id)
        if session is None:
            raise SessionNotResumableError(session_id, "指定 Session 不存在")
        updated = SessionLifecycle.on_stream_end(
            session,
            stream_end,
            now=timestamp(self.clock()),
        )
        await self.repository.save(updated)
        return updated

    async def close(self, session_id: str) -> SessionView:
        session = await self.repository.get(session_id)
        if session is None:
            raise SessionNotResumableError(session_id, "指定 Session 不存在")
        closed = SessionLifecycle.transition(
            session,
            SessionStatus.CLOSED,
            now=timestamp(self.clock()),
        )
        await self.repository.save(closed)
        native = getattr(getattr(self.repository, "database", None), "native_service", None)
        if native is not None:
            await native.io(native.release_session, session_id, safe=False)
        return closed

    async def finish_cancelled(self, session_id: str, task_id: str, result: CancelResult) -> SessionView:
        """Retain native context only after a proven, fully stopped cancellation.

        The production repository already exposes the durable execution state.
        Repositories without that evidence keep the original close behavior;
        an Adapter stop receipt alone cannot disprove unresolved side effects.
        task_id is the current execution, not SessionView's original owner Task.
        """
        session = await self.repository.get(session_id)
        if session is None:
            raise SessionNotResumableError(session_id, "指定 Session 不存在")
        state = getattr(self.repository, "execution_state", None)
        spec = state.get(f"task_spec:{task_id}") if state is not None else None
        confirmed = (
            result.outcome in {CancelOutcome.STOPPED_GRACEFULLY, CancelOutcome.FORCE_KILLED}
            and not result.orphan_process_ids
            and spec is not None
            and not spec.get("unresolvedCancellation")
            and not spec.get("recoveryRequired")
        )
        # create_active derives is_valid from the Adapter handle's supportsResume
        # AND externalSessionId. Never reopen a CLOSED/INVALID historical session.
        if (confirmed and session.is_valid and session.external_session_id
                and session.status in {SessionStatus.ACTIVE, SessionStatus.IDLE}):
            return await self.finish(session_id)
        return await self.close(session_id)

    async def finish(self, session_id: str) -> SessionView:
        session = await self.repository.get(session_id)
        if session is None:
            raise SessionNotResumableError(session_id, "指定 Session 不存在")
        target = SessionStatus.IDLE if session.is_valid else SessionStatus.CLOSED
        finished = SessionLifecycle.transition(
            session,
            target,
            now=timestamp(self.clock()),
        )
        await self.repository.save(finished)
        native = getattr(getattr(self.repository, "database", None), "native_service", None)
        if native is not None:
            await native.io(native.release_session, session_id, safe=True)
        return finished
