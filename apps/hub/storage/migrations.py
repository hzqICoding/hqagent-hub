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

MIGRATIONS += (
    Migration(7, """
        CREATE TABLE remote2_routes (
            worker_id TEXT NOT NULL, store_id TEXT NOT NULL, public_id TEXT NOT NULL,
            local_id TEXT NOT NULL, PRIMARY KEY(worker_id,store_id,public_id),
            UNIQUE(worker_id,store_id,local_id)
        );
        CREATE TABLE remote2_delivery (
            worker_id TEXT NOT NULL, store_id TEXT NOT NULL, command_id TEXT NOT NULL,
            digest TEXT NOT NULL, command_json TEXT, kind TEXT NOT NULL,
            public_id TEXT NOT NULL, local_id TEXT NOT NULL, conversation_seq INTEGER,
            state TEXT NOT NULL, run_id TEXT, deliver_by TEXT NOT NULL,
            received_json TEXT, result_json TEXT, grant_json TEXT, execution_json TEXT,
            PRIMARY KEY(worker_id,store_id,command_id)
        );
        CREATE TABLE remote2_order (
            worker_id TEXT NOT NULL, store_id TEXT NOT NULL, public_id TEXT NOT NULL,
            sequence INTEGER NOT NULL, command_id TEXT NOT NULL, consumed INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(worker_id,store_id,public_id,sequence)
        );
        CREATE TABLE remote2_gates (run_id TEXT PRIMARY KEY, state TEXT NOT NULL);
        CREATE TABLE remote_sync_changes (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
            resource_id TEXT NOT NULL, conversation_id TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE remote_sync_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT, backfill_id TEXT NOT NULL,
            kind TEXT NOT NULL, resource_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
            payload_json TEXT NOT NULL, text TEXT, revision INTEGER NOT NULL DEFAULT 1,
            segment_index INTEGER NOT NULL DEFAULT 0, segment_count INTEGER,
            content_hash TEXT, byte_count INTEGER, byte_offset INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX remote_sync_items_batch ON remote_sync_items(backfill_id,item_id);
        CREATE TABLE remote_sync_versions (
            store_id TEXT NOT NULL, generation INTEGER NOT NULL, kind TEXT NOT NULL,
            resource_id TEXT NOT NULL, revision INTEGER NOT NULL, digest TEXT NOT NULL,
            PRIMARY KEY(store_id,generation,kind,resource_id)
        );
        CREATE TABLE remote_sync_deletions (conversation_id TEXT PRIMARY KEY, deleted_at TEXT NOT NULL);
        CREATE TABLE remote_sync_redactions (
            store_id TEXT NOT NULL, deletion_seq INTEGER NOT NULL, redaction_id TEXT PRIMARY KEY,
            frame_json TEXT NOT NULL
        );
        CREATE TRIGGER remote_conversation_insert AFTER INSERT ON local_conversations BEGIN
            INSERT INTO remote_sync_changes(kind,resource_id,conversation_id) VALUES('conversation',NEW.conversation_id,NEW.conversation_id);
        END;
        CREATE TRIGGER remote_conversation_update AFTER UPDATE ON local_conversations BEGIN
            INSERT INTO remote_sync_changes(kind,resource_id,conversation_id) VALUES('conversation',NEW.conversation_id,NEW.conversation_id);
        END;
        CREATE TRIGGER remote_message_insert AFTER INSERT ON local_messages BEGIN
            INSERT INTO remote_sync_changes(kind,resource_id,conversation_id) VALUES('message',NEW.message_id,NEW.conversation_id);
        END;
        CREATE TRIGGER remote_message_update AFTER UPDATE ON local_messages BEGIN
            INSERT INTO remote_sync_changes(kind,resource_id,conversation_id) VALUES('message',NEW.message_id,NEW.conversation_id);
        END;
        CREATE TRIGGER remote_run_insert AFTER INSERT ON local_runs BEGIN
            INSERT INTO remote_sync_changes(kind,resource_id,conversation_id) VALUES('run',NEW.run_id,NEW.conversation_id);
        END;
        CREATE TRIGGER remote_run_update AFTER UPDATE ON local_runs WHEN
            NEW.status IS NOT OLD.status OR NEW.task_id IS NOT OLD.task_id OR NEW.error IS NOT OLD.error BEGIN
            INSERT INTO remote_sync_changes(kind,resource_id,conversation_id) VALUES('run',NEW.run_id,NEW.conversation_id);
        END;
        CREATE TRIGGER remote_conversation_delete AFTER DELETE ON local_conversations BEGIN
            INSERT OR IGNORE INTO remote_sync_deletions VALUES(OLD.conversation_id,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
            INSERT INTO remote_sync_changes(kind,resource_id,conversation_id,deleted) VALUES('conversation',OLD.conversation_id,OLD.conversation_id,1);
        END;
        CREATE TRIGGER remote_approval_insert AFTER INSERT ON approvals BEGIN
            INSERT INTO remote_sync_changes(kind,resource_id,conversation_id)
            SELECT 'approval',NEW.approval_id,conversation_id FROM local_runs WHERE task_id=NEW.task_id;
        END;
        CREATE TRIGGER remote_approval_update AFTER UPDATE ON approvals BEGIN
            INSERT INTO remote_sync_changes(kind,resource_id,conversation_id)
            SELECT 'approval',NEW.approval_id,conversation_id FROM local_runs WHERE task_id=NEW.task_id;
        END;
    """),
)

MIGRATIONS += (
    Migration(8, """
        CREATE TABLE native_sources (
            native_id TEXT PRIMARY KEY, binding_key TEXT NOT NULL UNIQUE,
            workspace_id TEXT NOT NULL, runtime_id TEXT NOT NULL, agent_type TEXT NOT NULL,
            source_json TEXT NOT NULL, index_json TEXT NOT NULL,
            conversation_id TEXT UNIQUE, session_id TEXT UNIQUE, confirmation_json TEXT,
            removed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE native_writers (
            binding_key TEXT PRIMARY KEY, session_id TEXT NOT NULL, owner TEXT NOT NULL,
            state TEXT NOT NULL, source_revision TEXT NOT NULL, started_at TEXT NOT NULL, input_hash TEXT NOT NULL
        );
        CREATE TABLE native_commands (
            worker_id TEXT NOT NULL, store_id TEXT NOT NULL, command_id TEXT NOT NULL,
            digest TEXT NOT NULL, frame_json TEXT NOT NULL, state TEXT NOT NULL,
            receipt_json TEXT NOT NULL, grant_json TEXT, result_json TEXT,
            PRIMARY KEY(worker_id,store_id,command_id)
        );
        CREATE TRIGGER native_source_insert AFTER INSERT ON native_sources BEGIN
            INSERT INTO remote_sync_changes(kind,resource_id,conversation_id)
            VALUES('native',NEW.native_id,'');
        END;
        CREATE TRIGGER native_source_update AFTER UPDATE ON native_sources WHEN
            NEW.index_json IS NOT OLD.index_json OR NEW.removed IS NOT OLD.removed
            OR NEW.conversation_id IS NOT OLD.conversation_id BEGIN
            INSERT INTO remote_sync_changes(kind,resource_id,conversation_id)
            VALUES('native',NEW.native_id,'');
        END;
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
