"""Durable copy-on-apply role templates for local chat scenes."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from protocol.generated.python import (
    CreateLocalRoleTemplateInput,
    LocalRoleTemplateView,
    UpdateLocalRoleTemplateInput,
)

from core.errors import HubError
from storage.database import Database, Transaction
from storage.idempotency import request_hash


BASE_ROLES = {"analyst", "planner", "developer", "reviewer"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _uid() -> str:
    return f"role_template_{uuid.uuid4().hex}"


class LocalRoleTemplateRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def _command(self, route: str, key: str, request: Any,
                 operation: Callable[[Transaction], dict]) -> tuple[dict, bool]:
        if not key or len(key) > 200:
            raise HubError("VALIDATION_FAILED", "必须提供不超过200字符的Idempotency-Key")
        digest = request_hash(request)
        with self.database.transaction() as tx:
            row = tx.connection.execute(
                "SELECT request_hash,response_json FROM local_commands "
                "WHERE route=? AND idempotency_key=?",
                (route, key),
            ).fetchone()
            if row:
                if row[0] != digest:
                    raise HubError("IDEMPOTENCY_MISMATCH", "相同请求标识不能用于不同内容")
                return json.loads(row[1]), True
            result = operation(tx)
            tx.connection.execute(
                "INSERT INTO local_commands VALUES(?,?,?,?)",
                (route, key, digest, json.dumps(result, ensure_ascii=False)),
            )
            return result, False

    @staticmethod
    def _validate_text(name: Any, instructions: Any) -> tuple[str, str]:
        if not isinstance(name, str):
            raise HubError("VALIDATION_FAILED", "模板名称不能为null")
        normalized_name = name.strip()
        if not normalized_name or len(normalized_name) > 120:
            raise HubError("VALIDATION_FAILED", "模板名称必须为1到120字符")
        if not isinstance(instructions, str):
            raise HubError("VALIDATION_FAILED", "模板职责不能为null")
        if len(instructions) > 12000:
            raise HubError("VALIDATION_FAILED", "模板职责不能超过12000字符")
        return normalized_name, instructions

    def templates(self) -> list[LocalRoleTemplateView]:
        with self.database.locked_connection() as db:
            rows = db.execute(
                "SELECT payload_json FROM local_role_templates ORDER BY updated_at DESC, rowid DESC"
            ).fetchall()
        return [LocalRoleTemplateView.model_validate_json(row[0]) for row in rows]

    def template(self, template_id: str) -> LocalRoleTemplateView:
        with self.database.locked_connection() as db:
            row = db.execute(
                "SELECT payload_json FROM local_role_templates WHERE template_id=?", (template_id,)
            ).fetchone()
        if row is None:
            raise HubError("NOT_FOUND", "角色模板不存在")
        return LocalRoleTemplateView.model_validate_json(row[0])

    def create(self, value: CreateLocalRoleTemplateInput, key: str) -> LocalRoleTemplateView:
        request = value.model_dump(mode="json", by_alias=True)

        def create(tx: Transaction) -> dict:
            name, instructions = self._validate_text(value.name, value.instructions)
            base_role_id = str(value.base_role_id)
            if base_role_id not in BASE_ROLES:
                raise HubError("VALIDATION_FAILED", "模板基础角色不受支持")
            stamp = _now()
            view = LocalRoleTemplateView.model_validate({
                "id": _uid(),
                "name": name,
                "baseRoleId": base_role_id,
                "instructions": instructions,
                "version": 1,
                "createdAt": stamp,
                "updatedAt": stamp,
            })
            tx.connection.execute(
                "INSERT INTO local_role_templates VALUES(?,?,?,?,?,?)",
                (view.id, base_role_id, 1, view.model_dump_json(by_alias=True), stamp, stamp),
            )
            return view.model_dump(mode="json", by_alias=True)

        result, _ = self._command("role-template.create", key, request, create)
        return LocalRoleTemplateView.model_validate(result)

    def update(self, template_id: str, value: UpdateLocalRoleTemplateInput,
               key: str) -> LocalRoleTemplateView:
        request = value.model_dump(mode="json", by_alias=True)

        def update(tx: Transaction) -> dict:
            name, instructions = self._validate_text(value.name, value.instructions)
            if value.expected_version < 1:
                raise HubError("VALIDATION_FAILED", "expectedVersion必须大于等于1")
            row = tx.connection.execute(
                "SELECT version,payload_json FROM local_role_templates WHERE template_id=?",
                (template_id,),
            ).fetchone()
            if row is None:
                raise HubError("NOT_FOUND", "角色模板不存在")
            if row[0] != value.expected_version:
                raise HubError(
                    "CONFLICT", "角色模板已更新，请刷新后重试",
                    detail={"currentVersion": row[0]},
                )
            current = LocalRoleTemplateView.model_validate_json(row[1])
            stamp = _now()
            changed = current.model_copy(update={
                "name": name,
                "instructions": instructions,
                "version": row[0] + 1,
                "updated_at": stamp,
            })
            tx.connection.execute(
                "UPDATE local_role_templates SET version=?,payload_json=?,updated_at=? "
                "WHERE template_id=?",
                (changed.version, changed.model_dump_json(by_alias=True), stamp, template_id),
            )
            return changed.model_dump(mode="json", by_alias=True)

        result, _ = self._command(f"role-template.update:{template_id}", key, request, update)
        return LocalRoleTemplateView.model_validate(result)

    def validate_reference(self, connection: Any, role: Any) -> None:
        template_id = role.role_template_id
        template_version = role.role_template_version
        if (template_id is None) != (template_version is None):
            raise HubError(
                "VALIDATION_FAILED", "roleTemplateId与roleTemplateVersion必须同时提供"
            )
        if template_id is None:
            return
        if not isinstance(template_id, str) or not template_id or len(template_id) > 160:
            raise HubError("VALIDATION_FAILED", "角色模板引用无效")
        if not isinstance(template_version, int) or template_version < 1:
            raise HubError("VALIDATION_FAILED", "角色模板版本必须为正整数")
        row = connection.execute(
            "SELECT base_role_id,version FROM local_role_templates WHERE template_id=?",
            (template_id,),
        ).fetchone()
        if row is None:
            raise HubError("VALIDATION_FAILED", "引用的角色模板不存在")
        if row[0] != str(role.role_id):
            raise HubError("VALIDATION_FAILED", "角色模板基础角色与场景角色不一致")
        if template_version > row[1]:
            raise HubError(
                "VALIDATION_FAILED", "角色模板来源版本不能高于当前模板版本",
                detail={"currentVersion": row[1]},
            )
