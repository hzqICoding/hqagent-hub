from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    sql: str


MIGRATIONS = (
    Migration(
        1,
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            version INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS agents (
            agent_instance_id TEXT PRIMARY KEY, adapter_id TEXT NOT NULL,
            display_name TEXT NOT NULL, version TEXT, status TEXT NOT NULL, detected_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS agent_capabilities (
            agent_instance_id TEXT NOT NULL, capability TEXT NOT NULL,
            source TEXT NOT NULL CHECK (source IN ('detected','user')), hard INTEGER NOT NULL,
            PRIMARY KEY (agent_instance_id, capability)
        );
        CREATE TABLE IF NOT EXISTS workspaces (
            workspace_id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
            vcs TEXT NOT NULL, default_profile_id TEXT
        );
        CREATE TABLE IF NOT EXISTS team_profiles (
            profile_id TEXT PRIMARY KEY, name TEXT NOT NULL, scope TEXT NOT NULL,
            payload_json TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS role_bindings (
            profile_id TEXT NOT NULL, role_id TEXT NOT NULL, primary_agent TEXT,
            fallback_json TEXT NOT NULL, constraints_json TEXT NOT NULL,
            PRIMARY KEY (profile_id, role_id)
        );
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, profile_id TEXT,
            objective TEXT NOT NULL, status TEXT NOT NULL, source TEXT NOT NULL,
            payload_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task_nodes (
            node_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, role_id TEXT NOT NULL,
            resolved_agent TEXT, resolve_source TEXT, status TEXT NOT NULL, payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, node_id TEXT,
            workspace_id TEXT NOT NULL, role_id TEXT NOT NULL, agent_instance_id TEXT NOT NULL,
            external_session_id TEXT, purpose TEXT NOT NULL, parent_session_id TEXT,
            reuse_policy TEXT NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL, last_used_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
            aggregate_type TEXT NOT NULL, aggregate_id TEXT NOT NULL, type TEXT NOT NULL,
            payload_json TEXT NOT NULL, envelope_json TEXT NOT NULL, occurred_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS approvals (
            approval_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, node_id TEXT,
            action TEXT NOT NULL, payload_json TEXT NOT NULL, status TEXT NOT NULL, decided_at TEXT
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task_checkpoints (
            checkpoint_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS worktrees (
            worktree_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, node_id TEXT,
            path TEXT NOT NULL, branch TEXT NOT NULL, base_commit TEXT NOT NULL, status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS artifacts (
            artifact_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, node_id TEXT,
            kind TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS idempotency_records (
            key TEXT NOT NULL, route TEXT NOT NULL, request_hash TEXT NOT NULL,
            response_json TEXT NOT NULL, expires_at TEXT NOT NULL,
            PRIMARY KEY (key, route)
        );
        """,
    ),
    Migration(
        2,
        """
        CREATE TABLE IF NOT EXISTS hub_state (
            key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_occurred_at ON events(occurred_at);
        CREATE INDEX IF NOT EXISTS idx_events_aggregate ON events(aggregate_type, aggregate_id, seq);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, updated_at);
        CREATE INDEX IF NOT EXISTS idx_sessions_task ON sessions(task_id, last_used_at);
        CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status, task_id);
        """,
    ),
    Migration(
        3,
        """
        -- workspaces 缺一个「上次打开时间」。这是持久事实，要存。
        -- branch / isClean / memoryDirPresent / capabilities 一律不存——
        -- 它们是文件系统的当前状态，存下来立刻过期，读时现算才是对的。
        ALTER TABLE workspaces ADD COLUMN last_opened_at TEXT;
        CREATE INDEX IF NOT EXISTS idx_workspaces_path ON workspaces(path);
        """,
    ),
    Migration(
        4,
        """
        CREATE TABLE local_scenes (
            scene_id TEXT PRIMARY KEY, version INTEGER NOT NULL, payload_json TEXT NOT NULL
        );
        CREATE TABLE local_conversations (
            conversation_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE local_messages (
            message_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, sequence INTEGER NOT NULL,
            role TEXT NOT NULL, text TEXT NOT NULL, run_id TEXT, created_at TEXT NOT NULL,
            UNIQUE(conversation_id, sequence), UNIQUE(run_id, role)
        );
        CREATE TABLE local_runs (
            run_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, message_id TEXT NOT NULL,
            task_id TEXT, scene_json TEXT NOT NULL, session_mode TEXT NOT NULL,
            status TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE local_commands (
            route TEXT NOT NULL, idempotency_key TEXT NOT NULL, request_hash TEXT NOT NULL,
            response_json TEXT NOT NULL, PRIMARY KEY(route, idempotency_key)
        );
        CREATE INDEX idx_local_messages_conversation ON local_messages(conversation_id, sequence);
        CREATE INDEX idx_local_runs_queue ON local_runs(conversation_id, created_at);
        """,
    ),
    Migration(
        5,
        """
        CREATE TABLE local_role_templates (
            template_id TEXT PRIMARY KEY,
            base_role_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX idx_local_role_templates_updated ON local_role_templates(updated_at DESC);
        """,
    ),
)

# R1-P2 appends a migration; older migration bytes remain unchanged.
MIGRATIONS += (
    Migration(6, """
        CREATE TABLE remote_state (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
        CREATE TABLE remote_inbox (
            worker_id TEXT NOT NULL, command_id TEXT NOT NULL, digest TEXT NOT NULL,
            command_json TEXT NOT NULL, status TEXT NOT NULL, run_id TEXT,
            receipt_json TEXT, observation_json TEXT,
            PRIMARY KEY(worker_id, command_id)
        );
        CREATE TABLE remote_slots (
            worker_id TEXT NOT NULL, conversation_id TEXT NOT NULL, sequence INTEGER NOT NULL,
            command_id TEXT NOT NULL, kind TEXT NOT NULL,
            PRIMARY KEY(worker_id, conversation_id, sequence),
            UNIQUE(worker_id, command_id)
        );
        CREATE TABLE remote_conversations (
            conversation_id TEXT PRIMARY KEY, worker_id TEXT NOT NULL, store_id TEXT NOT NULL,
            consumed_seq INTEGER NOT NULL DEFAULT 0, target_json TEXT
        );
        CREATE TABLE remote_outbox (
            store_id TEXT NOT NULL, seq INTEGER NOT NULL, event_id TEXT NOT NULL UNIQUE,
            frame_json TEXT NOT NULL, digest TEXT NOT NULL,
            PRIMARY KEY(store_id, seq)
        );
        CREATE TABLE remote_operations (
            route TEXT NOT NULL, key TEXT NOT NULL, digest TEXT NOT NULL,
            generation INTEGER NOT NULL, PRIMARY KEY(route, key)
        );
        CREATE TABLE remote_projections (key TEXT PRIMARY KEY, digest TEXT NOT NULL);
    """),
)

LATEST_SCHEMA_VERSION = MIGRATIONS[-1].version


def current_version(connection: sqlite3.Connection) -> int:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if not exists:
        return 0
    row = connection.execute("SELECT version FROM schema_version WHERE singleton=1").fetchone()
    return int(row[0]) if row else 0
