from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from protocol.generated.python import (
    AdapterFailure,
    AdapterStreamStatus,
    AgentTaskSpec,
    CapabilityId,
    ResumeRequest,
)

from adapters.claude_adapter import ClaudeAdapter
from adapters.path_guard import PathGuard
from adapters.session_registry import AdapterSessionState


def task_spec(root: Path, *, session_id: str = "session_test") -> AgentTaskSpec:
    return AgentTaskSpec.model_validate(
        {
            "sessionId": session_id,
            "taskId": "task_test",
            "nodeId": "node_test",
            "workspaceId": "workspace_test",
            "roleId": "analyst",
            "objective": "analyze",
            "worktreePath": str(root),
            "allowedPaths": [],
            "sessionPurpose": "adhoc",
            "reusePolicy": "new_session",
            "readOnly": True,
            "modelId": "claude-test",
            "roleInstructions": "read only",
        }
    )


class FinishedProcess:
    returncode = 0


class ResumeTestClaude(ClaudeAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.launches: list[tuple[str, bool, str]] = []

    async def _preflight(self, spec):
        return None

    async def _launch(self, state, message: str, *, resume: bool):
        self.launches.append((state.external_session_id, resume, message))
        state.process = FinishedProcess()
        state.ready.set()
        return None


def test_claude_declares_resume_and_new_handle_is_resumable(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = ResumeTestClaude()
        capability = next(
            item for item in adapter._capabilities(True) if item.id is CapabilityId.SESSION_RESUME
        )
        handle = await adapter.start(task_spec(tmp_path))
        assert capability.supported is True
        assert not isinstance(handle, AdapterFailure)
        assert handle.supports_resume is True
        assert handle.external_session_id

    asyncio.run(scenario())


def test_resume_rebuilds_missing_registry_state_from_persisted_spec(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = ResumeTestClaude()
        spec = task_spec(tmp_path)
        external_id = str(uuid.uuid4())
        result = await adapter.resume(
            ResumeRequest.model_validate(
                {
                    "sessionId": spec.session_id,
                    "externalSessionId": external_id,
                    "message": "continue exactly this session",
                    "taskSpec": spec.model_dump(mode="json", by_alias=True),
                }
            )
        )
        assert result is None
        state = adapter.registry.get(spec.session_id)
        assert state is not None
        assert state.external_session_id == external_id
        assert state.spec == spec
        assert adapter.launches == [(external_id, True, "continue exactly this session")]

    asyncio.run(scenario())


def test_resume_rejects_missing_spec_and_context_changes(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = ResumeTestClaude()
        spec = task_spec(tmp_path)
        external_id = str(uuid.uuid4())
        state = AdapterSessionState(
            session_id=spec.session_id,
            external_session_id=external_id,
            spec=spec,
            guard=PathGuard(str(tmp_path), []),
            process=FinishedProcess(),
        )
        adapter.registry.add(state)

        missing = await adapter.resume(
            ResumeRequest.model_validate(
                {"sessionId": spec.session_id, "externalSessionId": external_id, "message": "x"}
            )
        )
        assert isinstance(missing, AdapterFailure)
        assert "AgentTaskSpec" in missing.message

        other_root = tmp_path / "other"
        other_root.mkdir()
        changed = spec.model_copy(update={"worktree_path": str(other_root)})
        mismatch = await adapter.resume(
            ResumeRequest.model_validate(
                {
                    "sessionId": spec.session_id,
                    "externalSessionId": external_id,
                    "message": "x",
                    "taskSpec": changed.model_dump(mode="json", by_alias=True),
                }
            )
        )
        assert isinstance(mismatch, AdapterFailure)
        assert "权限边界" in mismatch.message

    asyncio.run(scenario())


def test_successful_claude_stream_end_is_resumable(tmp_path: Path) -> None:
    class Reader:
        def __init__(self, lines: list[dict]) -> None:
            self.lines = [
                (json.dumps(item, ensure_ascii=False) + "\n").encode("utf-8") for item in lines
            ]

        async def readline(self) -> bytes:
            return self.lines.pop(0) if self.lines else b""

    class Process:
        returncode = 0

        def __init__(self, lines: list[dict]) -> None:
            self.stdout = Reader(lines)

        async def wait(self) -> int:
            return 0

    async def scenario() -> None:
        adapter = ClaudeAdapter()
        spec = task_spec(tmp_path)
        external_id = str(uuid.uuid4())
        state = AdapterSessionState(
            session_id=spec.session_id,
            external_session_id=external_id,
            spec=spec,
            guard=PathGuard(str(tmp_path), []),
        )
        state.process = Process(
            [
                {"type": "system", "subtype": "init", "session_id": external_id},
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "session_id": external_id,
                    "structured_output": {"status": "done", "summary": "ok"},
                },
            ]
        )
        await adapter._read_stream(state)
        assert state.failure is None
        assert state.result is not None
        assert state.stream_end is not None
        assert state.stream_end.status is AdapterStreamStatus.ENDED
        assert state.stream_end.resumable is True

    asyncio.run(scenario())
