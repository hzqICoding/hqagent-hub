# Project chat backend handoff

## Scope

- Branch: `feat/project-chat-backend`
- Base: `d4379b0`
- Protocol prerequisite: `362d3ba` (`0.4.0`)
- Writable implementation: `apps/hub/api/local_chat.py`, `apps/hub/storage/local_chat.py`, `apps/hub/runtime/local_chat.py`, `apps/hub/tests/test_local_chat.py`

## Implemented behavior

- `PATCH /api/v2/conversations/{conversation_id}` requires `Idempotency-Key` and generated `UpdateLocalConversationInput`.
- Metadata edits validate a nonempty patch, trim titles, reject null/blank values, enforce `expectedVersion`, and increment `version` exactly once per successful idempotent command.
- Old conversation payloads project `version=1` and `archived=false`; metadata remains in `payload_json`, so no database migration is required.
- Conversation lists include every stored conversation and derive `lastRunStatus` from the latest run joined to the durable `tasks.status`; the derived status is never persisted in conversation JSON.
- Archiving checks effective task/run status and rejects queued, running, waiting-approval, or paused work without cancelling it.
- Enqueue rereads conversation metadata inside the same `BEGIN IMMEDIATE` transaction, preventing stale metadata from overwriting rename/archive changes.
- Archived conversations reject messages and execution-producing `append_instruction`, `resume`, and `retry` commands until restored. Idempotent replay of a previously accepted message still returns its original receipt without another enqueue.

## Concurrency boundary

HQAgent-Hub is a single-instance process. `LocalChatService` uses one `asyncio.Lock` per conversation around archive/restore and execution-producing run controls. The lock spans the awaited `TaskPort.act` call, so archive cannot pass between the precondition check and retry/resume creation. Direct message enqueue remains synchronized with archive by the SQLite write transaction and its in-transaction archived check.

## Verification

```powershell
Set-Location E:\OtherPro\HQAgent-Hub-worktrees\project-chat-backend\apps\hub
& 'E:\OtherPro\HQAgent-Hub-worktrees\vnext-integration\.venv\Scripts\python.exe' -m pytest tests\test_local_chat.py tests\test_restart_recovery.py -q
```

Result: `19 passed, 1 warning in 2.32s`. The warning is the existing Starlette `TestClient` deprecation warning.

Covered cases include metadata persistence/reopen, legacy defaults, idempotent replay, stale version conflict, null/blank patch rejection, more than 200 conversations, actual task-status projection, archive/send transaction races, archived retry rejection, retry/archive races across awaited `TaskPort.act`, and terminal reply persistence before archive.
