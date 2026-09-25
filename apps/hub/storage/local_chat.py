"""Durable local chat state; enqueue and request deduplication share a transaction."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from protocol.generated.python import (
    CreateLocalConversationInput, LocalConversationView, LocalMessageReceipt,
    LocalMessageView, LocalRunView, LocalSceneView, SaveLocalSceneInput,
    SendLocalMessageInput, ReviewMode,
)
from core.errors import HubError
from storage.database import Database, Transaction
from storage.idempotency import request_hash


TERMINAL = {"succeeded", "failed", "cancelled"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class LocalChatRepository:
    def __init__(self, database: Database) -> None:
        self.database = database
        self._seed_scenes()

    def _seed_scenes(self) -> None:
        scenes = [
            ("analyze", "代码分析", "只读梳理代码、调用关系和风险", True,
             [("analyst", True, "只读分析相关代码，给出文件依据与调用链，区分事实和推断。")]),
            ("plan", "需求规划", "讨论范围、方案与验收条件", True,
             [("planner", True, "分析需求与现有实现，输出实施方案和验收条件。本轮不修改代码。")]),
            ("develop", "开发修复", "在隔离工作树实施与验证", False,
             [("planner", False, "先阅读目标和约束，给执行者明确的实施建议。"),
              ("developer", True, "按要求实施并验证，报告实际改动、测试和未完成事项。"),
              ("reviewer", False, "阅读实际改动和验证证据，独立检查问题。")]),
        ]
        with self.database.transaction() as tx:
            for scene_id, name, description, read_only, roles in scenes:
                value = LocalSceneView.model_validate({
                    "id": scene_id, "name": name, "description": description,
                    "readOnly": read_only, "version": 1, "updatedAt": now(),
                    "roles": [{"roleId": role, "agentInstanceId": "", "instructions": text,
                               "enabled": enabled} for role, enabled, text in roles],
                })
                tx.connection.execute("INSERT OR IGNORE INTO local_scenes VALUES(?,?,?)",
                                      (scene_id, 1, value.model_dump_json(by_alias=True)))

    def scenes(self) -> list[LocalSceneView]:
        with self.database.locked_connection() as db:
            rows = db.execute("SELECT payload_json FROM local_scenes ORDER BY rowid").fetchall()
        return [LocalSceneView.model_validate_json(row[0]) for row in rows]

    def scene(self, scene_id: str) -> LocalSceneView:
        for value in self.scenes():
            if str(value.id) == scene_id:
                return value
        raise HubError("NOT_FOUND", "场景不存在")

    def save_scene(self, scene_id: str, value: SaveLocalSceneInput) -> LocalSceneView:
        required = {"analyze": "analyst", "plan": "planner", "develop": "developer"}
        permitted = {"analyze": {"analyst"}, "plan": {"planner"},
                     "develop": {"planner", "developer", "reviewer"}}
        if scene_id not in required:
            raise HubError("NOT_FOUND", "场景不存在")
        ids = [role.role_id for role in value.roles]
        enabled = {role.role_id for role in value.roles if role.enabled}
        if len(ids) != len(set(ids)) or set(ids) != permitted[scene_id] or required[scene_id] not in enabled:
            raise HubError("VALIDATION_FAILED", "角色集合不匹配或必需角色未启用")
        for role in value.roles:
            if len(role.instructions) > 12000:
                raise HubError("VALIDATION_FAILED", "角色职责过长")
        with self.database.transaction() as tx:
            row = tx.connection.execute("SELECT version,payload_json FROM local_scenes WHERE scene_id=?", (scene_id,)).fetchone()
            if row[0] != value.expected_version:
                raise HubError("IDEMPOTENCY_MISMATCH", "场景已更新，请刷新后再保存", detail={"currentVersion": row[0]})
            old = LocalSceneView.model_validate_json(row[1])
            mode = str(value.review_mode or old.review_mode or "independent")
            roles = value.roles
            if mode == "original_planner":
                if scene_id != "develop":
                    raise HubError("VALIDATION_FAILED", "原规划会话验收仅适用于开发场景")
                planner = next(r for r in roles if r.role_id == "planner")
                reviewer = next(r for r in roles if r.role_id == "reviewer")
                if not planner.enabled or not reviewer.enabled or not planner.agent_instance_id:
                    raise HubError("VALIDATION_FAILED", "原规划会话验收必须启用planner、developer、reviewer，并配置planner")
                roles = [r.model_copy(update={"agent_instance_id": planner.agent_instance_id,
                    "model_id_": planner.model_id_, "reasoning_effort": planner.reasoning_effort})
                    if r.role_id == "reviewer" else r for r in roles]
            updated = old.model_copy(update={"roles": roles, "review_mode": ReviewMode(mode),
                                             "version": row[0] + 1, "updated_at": now()})
            tx.connection.execute("UPDATE local_scenes SET version=?,payload_json=? WHERE scene_id=?",
                                  (updated.version, updated.model_dump_json(by_alias=True), scene_id))
        return updated

    def command(self, route: str, key: str, request: Any, operation: Callable[[Transaction], dict]) -> tuple[dict, bool]:
        if not key or len(key) > 200:
            raise HubError("VALIDATION_FAILED", "必须提供不超过200字符的Idempotency-Key")
        digest = request_hash(request)
        with self.database.transaction() as tx:
            row = tx.connection.execute("SELECT request_hash,response_json FROM local_commands WHERE route=? AND idempotency_key=?",
                                        (route, key)).fetchone()
            if row:
                if row[0] != digest:
                    raise HubError("IDEMPOTENCY_MISMATCH", "相同请求标识不能用于不同内容")
                return json.loads(row[1]), True
            result = operation(tx)
            tx.connection.execute("INSERT INTO local_commands VALUES(?,?,?,?)",
                                  (route, key, digest, json.dumps(result, ensure_ascii=False)))
            return result, False

    def conversations(self) -> list[LocalConversationView]:
        with self.database.locked_connection() as db:
            rows = db.execute("SELECT payload_json FROM local_conversations ORDER BY updated_at DESC LIMIT 200").fetchall()
        return [LocalConversationView.model_validate_json(row[0]) for row in rows]

    def conversation(self, conversation_id: str) -> LocalConversationView:
        with self.database.locked_connection() as db:
            row = db.execute("SELECT payload_json FROM local_conversations WHERE conversation_id=?", (conversation_id,)).fetchone()
        if row is None:
            raise HubError("NOT_FOUND", "对话不存在")
        return LocalConversationView.model_validate_json(row[0])

    def create_conversation(self, value: CreateLocalConversationInput, key: str) -> LocalConversationView:
        self.scene(str(value.scene_id))
        if not value.title.strip() or len(value.title) > 200:
            raise HubError("VALIDATION_FAILED", "标题必须为1到200字符")
        def create(tx: Transaction) -> dict:
            stamp = now()
            view = LocalConversationView.model_validate({"id": uid("conversation"), "title": value.title.strip(),
                "workspaceId": value.workspace_id, "sceneId": str(value.scene_id), "createdAt": stamp, "updatedAt": stamp})
            tx.connection.execute("INSERT INTO local_conversations VALUES(?,?,?)", (view.id, view.model_dump_json(by_alias=True), stamp))
            return view.model_dump(mode="json", by_alias=True)
        result, _ = self.command("conversation.create", key, value.model_dump(mode="json"), create)
        return LocalConversationView.model_validate(result)

    def enqueue(self, conversation_id: str, value: SendLocalMessageInput, key: str) -> LocalMessageReceipt:
        conversation = self.conversation(conversation_id)
        if not value.text.strip() or len(value.text) > 32000:
            raise HubError("VALIDATION_FAILED", "消息必须为1到32000字符")
        if not value.client_message_id or len(value.client_message_id) > 160:
            raise HubError("VALIDATION_FAILED", "clientMessageId必须为1到160字符")
        def create(tx: Transaction) -> dict:
            alias_route = f"client-message:{conversation_id}"
            digest = request_hash(value.model_dump(mode="json"))
            prior = tx.connection.execute("SELECT request_hash,response_json FROM local_commands WHERE route=? AND idempotency_key=?", (alias_route, value.client_message_id)).fetchone()
            if prior:
                if prior[0] != digest:
                    raise HubError("IDEMPOTENCY_MISMATCH", "相同clientMessageId不能用于不同内容")
                return {**json.loads(prior[1]), "duplicate": True}
            queued = tx.connection.execute("SELECT COUNT(*) FROM local_runs WHERE conversation_id=? AND status='queued'", (conversation_id,)).fetchone()[0]
            if queued >= 20:
                raise HubError("TASK_ACTION_INVALID", "排队消息过多，请等待当前任务完成")
            row = tx.connection.execute("SELECT payload_json FROM local_scenes WHERE scene_id=?", (str(conversation.scene_id),)).fetchone()
            run_id, message_id, stamp = uid("run"), uid("message"), now()
            seq = tx.connection.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM local_messages WHERE conversation_id=?", (conversation_id,)).fetchone()[0]
            tx.connection.execute("INSERT INTO local_messages VALUES(?,?,?,?,?,?,?)", (message_id, conversation_id, seq, "user", value.text, run_id, stamp))
            tx.connection.execute("INSERT INTO local_runs VALUES(?,?,?,?,?,?,?,?,?,?)", (run_id, conversation_id, message_id, None, row[0], str(value.session_mode), "queued", None, stamp, stamp))
            updated = conversation.model_copy(update={"last_run_id": run_id, "updated_at": stamp})
            tx.connection.execute("UPDATE local_conversations SET payload_json=?,updated_at=? WHERE conversation_id=?",
                                  (updated.model_dump_json(by_alias=True), stamp, conversation_id))
            receipt = {"commandId": uid("command"), "conversationId": conversation_id,
                    "messageId": message_id, "runId": run_id, "status": "queued", "duplicate": False}
            tx.connection.execute("INSERT INTO local_commands VALUES(?,?,?,?)", (alias_route, value.client_message_id, digest, json.dumps(receipt, ensure_ascii=False)))
            return receipt
        response, duplicate = self.command(f"messages:{conversation_id}", key, value.model_dump(mode="json"), create)
        response["duplicate"] = duplicate or response.get("duplicate", False)
        return LocalMessageReceipt.model_validate(response)

    def messages(self, conversation_id: str, after: int = 0, limit: int = 200) -> list[LocalMessageView]:
        self.conversation(conversation_id)
        with self.database.locked_connection() as db:
            rows = db.execute("SELECT * FROM local_messages WHERE conversation_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                              (conversation_id, after, min(max(limit, 1), 200))).fetchall()
        return [LocalMessageView.model_validate({"id": r["message_id"], "conversationId": conversation_id,
            "sequence": r["sequence"], "role": r["role"], "text": r["text"], "runId": r["run_id"], "createdAt": r["created_at"]}) for r in rows]

    def run_record(self, run_id: str) -> dict:
        with self.database.locked_connection() as db:
            row = db.execute("SELECT r.*,m.sequence AS message_sequence FROM local_runs r JOIN local_messages m ON m.message_id=r.message_id WHERE r.run_id=?", (run_id,)).fetchone()
        if row is None:
            raise HubError("NOT_FOUND", "执行轮次不存在")
        return dict(row)

    def runs(self, conversation_id: str) -> list[dict]:
        self.conversation(conversation_id)
        with self.database.locked_connection() as db:
            rows = db.execute("SELECT r.*,m.sequence AS message_sequence FROM local_runs r JOIN local_messages m ON m.message_id=r.message_id WHERE r.conversation_id=? ORDER BY m.sequence DESC LIMIT 200", (conversation_id,)).fetchall()
        return [dict(row) for row in rows]

    def next_run(self, conversation_id: str) -> dict | None:
        with self.database.locked_connection() as db:
            row = db.execute("SELECT r.*,m.sequence AS message_sequence FROM local_runs r JOIN local_messages m ON m.message_id=r.message_id WHERE r.conversation_id=? AND r.status NOT IN ('succeeded','failed','cancelled') ORDER BY m.sequence LIMIT 1", (conversation_id,)).fetchone()
        return dict(row) if row else None

    def run_text(self, run_id: str) -> str:
        with self.database.locked_connection() as db:
            row = db.execute("SELECT text FROM local_messages WHERE run_id=? AND role='user'", (run_id,)).fetchone()
        return row[0] if row else ""

    def update_run(self, run_id: str, status: str, *, task_id: str | None = None, error: str | None = None) -> None:
        with self.database.transaction() as tx:
            tx.connection.execute("UPDATE local_runs SET status=?,task_id=COALESCE(?,task_id),error=?,updated_at=? WHERE run_id=?",
                                  (status, task_id, error, now(), run_id))

    def reply(self, run_id: str, text: str) -> None:
        run = self.run_record(run_id)
        with self.database.transaction() as tx:
            seq = tx.connection.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM local_messages WHERE conversation_id=?", (run["conversation_id"],)).fetchone()[0]
            tx.connection.execute("INSERT OR IGNORE INTO local_messages VALUES(?,?,?,?,?,?,?)",
                                  (uid("message"), run["conversation_id"], seq, "assistant", text, run_id, now()))

    def complete_run(self, run_id: str, status: str, text: str, *, error: str | None = None,
                     transaction: Transaction | None = None) -> None:
        """A terminal projection and its visible answer must commit together."""
        def complete(tx):
            row = tx.connection.execute("SELECT conversation_id FROM local_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise HubError("NOT_FOUND", "执行轮次不存在")
            stamp = now()
            tx.connection.execute("UPDATE local_runs SET status=?,error=?,updated_at=? WHERE run_id=?", (status, error, stamp, run_id))
            seq = tx.connection.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM local_messages WHERE conversation_id=?", (row[0],)).fetchone()[0]
            tx.connection.execute("INSERT OR IGNORE INTO local_messages VALUES(?,?,?,?,?,?,?)", (uid("message"), row[0], seq, "assistant", text, run_id, stamp))
        if transaction is not None:
            complete(transaction)
        else:
            with self.database.transaction() as tx:
                complete(tx)

    def request_cancel(self, run_id: str, transaction: Transaction) -> None:
        transaction.connection.execute("INSERT INTO hub_state(key,value_json,updated_at) VALUES(?, '{}', ?) ON CONFLICT(key) DO NOTHING", (f"local-cancel:{run_id}", now()))
        transaction.connection.execute("UPDATE local_runs SET error=? WHERE run_id=?", ("已请求取消，等待派发确认", run_id))

    def cancel_requested(self, run_id: str) -> bool:
        with self.database.locked_connection() as db:
            return db.execute("SELECT 1 FROM hub_state WHERE key=?", (f"local-cancel:{run_id}",)).fetchone() is not None

    @staticmethod
    def view(record: dict, task: Any = None) -> LocalRunView:
        return LocalRunView.model_validate({"id": record["run_id"], "conversationId": record["conversation_id"],
            "messageId": record["message_id"], "taskId": record["task_id"] or "",
            "sceneSnapshot": json.loads(record["scene_json"]), "status": record["status"],
            "createdAt": record["created_at"], "updatedAt": record["updated_at"], "error": record["error"], "task": task})
