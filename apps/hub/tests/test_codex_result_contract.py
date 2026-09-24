from __future__ import annotations

import asyncio
import json
from pathlib import Path

from protocol.generated.python import AgentTaskSpec

from adapters.codex_adapter import CodexAdapter
from adapters.path_guard import PathGuard
from adapters.session_registry import AdapterSessionState


# Shape copied from the failed native thread's last public assistant message.
# Human text is shortened; file/test fields and nullability match the real output.
REAL_FINAL_RESULT = json.dumps(
    {
        "artifacts": ["index.html", "src/counter.js", "tests/counter.test.cjs"],
        "blockers": None,
        "branch": None,
        "changedFiles": [
            {
                "changeKind": "added",
                "deletions": 0,
                "insertions": 119,
                "path": "index.html",
                "renamedFrom": None,
            },
            {
                "changeKind": "added",
                "deletions": 0,
                "insertions": 68,
                "path": "src/counter.js",
                "renamedFrom": None,
            },
            {
                "changeKind": "added",
                "deletions": 0,
                "insertions": 71,
                "path": "tests/counter.test.cjs",
                "renamedFrom": None,
            },
        ],
        "commit": None,
        "questions": None,
        "status": "done",
        "summary": "developer 已完成三份目标文件并真实运行 Node 内置测试。",
        "tests": [
            {
                "command": "node --test tests/counter.test.cjs",
                "durationMs": 93,
                "exitCode": 0,
                "name": "Node 内置计数器测试",
                "outputExcerpt": "tests 9; pass 9; fail 0",
                "passed": True,
            }
        ],
    },
    ensure_ascii=False,
    separators=(",", ":"),
)


def state_for(root: Path) -> AdapterSessionState:
    spec = AgentTaskSpec.model_validate(
        {
            "sessionId": "session",
            "taskId": "task",
            "nodeId": "node",
            "workspaceId": "workspace",
            "roleId": "developer",
            "objective": "implement",
            "worktreePath": str(root),
            "allowedPaths": ["**"],
            "sessionPurpose": "implement",
            "reusePolicy": "new_session",
        }
    )
    return AdapterSessionState(
        session_id=spec.session_id,
        external_session_id="thread",
        spec=spec,
        guard=PathGuard(str(root), spec.allowed_paths),
    )


def result_message(text: str, *, phase: str | None = "commentary", item_id: str) -> dict:
    return {"id": item_id, "type": "agentMessage", "text": text, "phase": phase}


def test_turn_completed_uses_last_valid_item_not_concatenated_deltas(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = CodexAdapter()
        state = state_for(tmp_path)
        state.last_agent_message = '{"status":"done"}{"status":"done"}'
        progress = json.dumps({"status": "done", "summary": "interim commentary"})

        await adapter._complete_turn(
            state,
            {
                "turn": {
                    "status": "completed",
                    "items": [
                        result_message(progress, item_id="message-1"),
                        result_message(progress, item_id="message-2"),
                        result_message(REAL_FINAL_RESULT, item_id="message-3"),
                    ],
                }
            },
        )

        assert state.failure is None
        assert state.result is not None
        assert len(state.result.changed_files or []) == 3
        assert len(state.result.tests or []) == 1
        assert state.result.tests[0].exit_code == 0

    asyncio.run(scenario())


def test_final_answer_phase_wins_over_later_commentary(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = CodexAdapter()
        state = state_for(tmp_path)
        later_commentary = json.dumps({"status": "done", "summary": "not terminal"})

        await adapter._complete_turn(
            state,
            {
                "turn": {
                    "status": "completed",
                    "items": [
                        result_message(REAL_FINAL_RESULT, phase="final_answer", item_id="final"),
                        result_message(later_commentary, phase="commentary", item_id="late"),
                    ],
                }
            },
        )

        assert state.failure is None
        assert state.result is not None
        assert len(state.result.changed_files or []) == 3

    asyncio.run(scenario())


def test_invalid_public_messages_remain_failed_without_raw_text(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = CodexAdapter()
        state = state_for(tmp_path)
        private_marker = "Bearer SHOULD_NOT_APPEAR_IN_FAILURE"

        await adapter._complete_turn(
            state,
            {
                "turn": {
                    "status": "completed",
                    "items": [result_message(private_marker, item_id="invalid")],
                }
            },
        )

        assert state.result is None
        assert state.failure is not None
        assert state.failure.message == "Codex 返回值不符合 AgentResult"
        assert private_marker not in (state.failure.raw or "")
        diagnostic = json.loads(state.failure.raw or "{}")
        assert diagnostic["candidateCount"] == 1
        assert diagnostic["validationErrors"][0]["errorType"] == "JSONDecodeError"

    asyncio.run(scenario())


def test_agent_message_delta_is_progress_only(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = CodexAdapter()
        state = state_for(tmp_path)
        await adapter._handle_notification(
            state,
            {"method": "item/agentMessage/delta", "params": {"delta": "partial"}},
        )
        assert state.last_agent_message is None
        event = await state.queue.get()
        assert event.unified_type == "agent.progress"

    asyncio.run(scenario())


def test_command_execution_completed_exposes_real_integer_exit_code(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = CodexAdapter()
        state = state_for(tmp_path)
        await adapter._handle_item(
            state,
            "item/completed",
            {
                "id": "command-1",
                "type": "commandExecution",
                "command": "node --test tests/counter.test.cjs",
                "status": "completed",
                "exitCode": 7,
                "aggregatedOutput": "tests failed",
            },
        )
        event = await state.queue.get()
        assert event.payload.exit_code == 7

        await adapter._handle_item(
            state,
            "item/completed",
            {
                "id": "command-2",
                "type": "commandExecution",
                "command": "echo bool",
                "status": "completed",
                "exitCode": True,
            },
        )
        bool_event = await state.queue.get()
        assert bool_event.payload.exit_code is None

    asyncio.run(scenario())
