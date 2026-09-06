from __future__ import annotations

from dataclasses import dataclass, replace
from threading import Lock
from typing import Iterable

from protocol.generated.python import DangerousAction, RoleBindingView, RolePermissions

from orchestrator.catalog import BuiltinCatalog, RoleDefinition
from orchestrator.errors import ApprovalError, InvalidTaskActionError

from .paths import PathScope, pattern_is_subset


def _text(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


@dataclass(frozen=True, slots=True)
class RolePolicy:
    role_id: str
    filesystem: str
    shell: bool
    can_approve: bool
    can_merge: bool
    writable_paths: tuple[str, ...]
    default_requires_approval: tuple[str, ...]

    @property
    def read_only(self) -> bool:
        return self.filesystem == "read_only"


class PermissionEngine:
    def __init__(self, catalog: BuiltinCatalog) -> None:
        self.catalog = catalog

    def role_policy(
        self,
        role_id: str,
        binding: RoleBindingView | None = None,
    ) -> RolePolicy:
        role = self.catalog.role(role_id)
        policy = self._from_definition(role)
        if binding and binding.permissions:
            policy = self._tighten_with_permissions(policy, binding.permissions)
        if binding and binding.constraints:
            constraints = binding.constraints
            if constraints.allow_shell is False:
                policy = replace(policy, shell=False)
            elif constraints.allow_shell is True and not policy.shell:
                raise InvalidTaskActionError(
                    "RoleBinding 不能把角色的 shell 权限从 false 放宽为 true",
                    roleId=role_id,
                )
            if constraints.read_only_fs is True:
                policy = replace(policy, filesystem="read_only", writable_paths=())
            elif constraints.read_only_fs is False and policy.read_only:
                raise InvalidTaskActionError(
                    "RoleBinding 不能把只读角色放宽为可写",
                    roleId=role_id,
                )
        return policy

    def path_scope(
        self,
        policy: RolePolicy,
        task_allowed_paths: Iterable[str],
    ) -> PathScope:
        role_paths = () if policy.read_only else policy.writable_paths
        return PathScope.build(role_paths, task_allowed_paths)

    def effective_requires_approval(
        self,
        policy: RolePolicy,
        task_requires_approval: Iterable[str] | None,
    ) -> tuple[str, ...]:
        values = (
            policy.default_requires_approval
            if task_requires_approval is None
            else tuple(_text(item) for item in task_requires_approval)
        )
        invalid = sorted(set(values) - self.catalog.dangerous_actions)
        if invalid:
            raise InvalidTaskActionError("任务包含未知危险动作", actions=invalid)
        return tuple(dict.fromkeys(values))

    def assert_role_can_approve(self, policy: RolePolicy) -> None:
        if not policy.can_approve:
            raise ApprovalError(
                "APPROVAL_REQUIRED",
                f"角色 {policy.role_id} 没有审批权限",
                {"roleId": policy.role_id},
            )

    def assert_action_allowed(
        self,
        policy: RolePolicy,
        action: str | DangerousAction,
        *,
        approved: bool,
    ) -> None:
        action_value = _text(action)
        if action_value not in self.catalog.dangerous_actions:
            raise InvalidTaskActionError("未知危险动作", action=action_value)
        if action_value == DangerousAction.SHELL.value and not policy.shell:
            raise InvalidTaskActionError(
                f"角色 {policy.role_id} 禁止执行 shell",
                roleId=policy.role_id,
                action=action_value,
            )
        if action_value == DangerousAction.GIT_MERGE.value and not policy.can_merge:
            raise InvalidTaskActionError(
                f"角色 {policy.role_id} 禁止执行 git_merge",
                roleId=policy.role_id,
                action=action_value,
            )
        if not approved:
            raise ApprovalError(
                "APPROVAL_REQUIRED",
                f"危险动作 {action_value} 尚未审批",
                {"roleId": policy.role_id, "action": action_value},
            )

    @staticmethod
    def _from_definition(role: RoleDefinition) -> RolePolicy:
        permissions = role.permissions
        return RolePolicy(
            role_id=role.role_id,
            filesystem=permissions.filesystem,
            shell=permissions.shell,
            can_approve=permissions.can_approve,
            can_merge=permissions.can_merge,
            writable_paths=permissions.writable_paths,
            default_requires_approval=permissions.requires_approval,
        )

    def _tighten_with_permissions(
        self,
        base: RolePolicy,
        override: RolePermissions,
    ) -> RolePolicy:
        filesystem = _text(override.filesystem)
        if base.read_only and filesystem != "read_only":
            raise InvalidTaskActionError("RoleBinding 不能放宽文件权限", roleId=base.role_id)
        if override.shell and not base.shell:
            raise InvalidTaskActionError("RoleBinding 不能放宽 shell 权限", roleId=base.role_id)
        if override.can_approve and not base.can_approve:
            raise InvalidTaskActionError("RoleBinding 不能放宽审批权限", roleId=base.role_id)
        if override.can_merge and not base.can_merge:
            raise InvalidTaskActionError("RoleBinding 不能放宽合并权限", roleId=base.role_id)

        override_paths = tuple(override.writable_paths)
        for path in override_paths:
            if not any(pattern_is_subset(path, allowed) for allowed in base.writable_paths):
                raise InvalidTaskActionError(
                    "RoleBinding writablePaths 超出角色默认范围",
                    roleId=base.role_id,
                    path=path,
                )
        approvals = tuple(_text(item) for item in override.requires_approval)
        if not set(approvals).issuperset(base.default_requires_approval):
            raise InvalidTaskActionError(
                "RoleBinding 不能减少角色默认审批动作",
                roleId=base.role_id,
            )
        return RolePolicy(
            role_id=base.role_id,
            filesystem=filesystem,
            shell=override.shell,
            can_approve=override.can_approve,
            can_merge=override.can_merge,
            writable_paths=() if filesystem == "read_only" else override_paths,
            default_requires_approval=approvals,
        )


class IntegratorLease:
    """Single-Hub-process lease enforcing one active integrator at a time."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._task_id: str | None = None

    @property
    def active_task_id(self) -> str | None:
        with self._lock:
            return self._task_id

    def acquire(self, task_id: str, policy: RolePolicy) -> None:
        if not policy.can_merge or policy.role_id != "integrator":
            raise InvalidTaskActionError(
                "只有 integrator 角色可以取得合并租约",
                roleId=policy.role_id,
            )
        with self._lock:
            if self._task_id and self._task_id != task_id:
                raise InvalidTaskActionError(
                    "已有 integrator 正在执行最终合并",
                    activeTaskId=self._task_id,
                    requestedTaskId=task_id,
                )
            self._task_id = task_id

    def release(self, task_id: str) -> None:
        with self._lock:
            if self._task_id == task_id:
                self._task_id = None
