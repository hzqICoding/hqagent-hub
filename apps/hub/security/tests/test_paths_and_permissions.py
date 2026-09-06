import pytest
from protocol.generated.python import RoleBindingConstraints, RoleBindingView, RolePermissions

from orchestrator.catalog import BuiltinCatalog
from orchestrator.errors import ApprovalError, InvalidTaskActionError
from security.paths import PathScope, normalize_repo_path
from security.permissions import IntegratorLease, PermissionEngine


def test_role_and_task_allowed_paths_are_intersected() -> None:
    scope = PathScope.build(
        ("apps/hub/**",),
        ("apps/hub/orchestrator/**", "docs/**"),
    )

    assert scope.adapter_patterns == ("apps/hub/orchestrator/**",)
    result = scope.validate(
        (
            "apps/hub/orchestrator/runtime.py",
            "apps/hub/security/paths.py",
            "docs/施工方案.md",
        )
    )
    assert result.allowed_paths == ("apps/hub/orchestrator/runtime.py",)
    assert result.violation_paths == (
        "apps/hub/security/paths.py",
        "docs/施工方案.md",
    )


def test_traversal_and_absolute_paths_never_pass() -> None:
    scope = PathScope.build(("**",), ("**",))
    result = scope.validate(("../outside.txt", "C:\\outside.txt", "/etc/passwd"))
    assert len(result.violation_paths) == 3
    with pytest.raises(ValueError):
        normalize_repo_path("../outside.txt")


def test_read_only_role_has_empty_path_intersection() -> None:
    engine = PermissionEngine(BuiltinCatalog.load())
    reviewer = engine.role_policy("reviewer")
    scope = engine.path_scope(reviewer, ("**",))

    assert scope.adapter_patterns == ()
    assert scope.allows("README.md") is False


def test_profile_permissions_can_tighten_but_not_widen_role() -> None:
    engine = PermissionEngine(BuiltinCatalog.load())
    binding = RoleBindingView.model_validate(
        {
            "roleId": "general_implementer",
            "roleName": "通用实现",
            "primaryAgentId": "agent",
            "fallbackAgentIds": [],
            "permissions": {
                "filesystem": "read_write",
                "shell": True,
                "canApprove": False,
                "canMerge": False,
                "writablePaths": ["apps/hub/orchestrator/**"],
                "requiresApproval": ["deploy", "git_push", "delete", "db_migrate", "shell"],
            },
        }
    )
    policy = engine.role_policy("general_implementer", binding)
    assert policy.writable_paths == ("apps/hub/orchestrator/**",)
    assert "shell" in policy.default_requires_approval

    widened = binding.model_copy(
        update={
            "permissions": RolePermissions.model_validate(
                {
                    "filesystem": "read_write",
                    "shell": True,
                    "canApprove": True,
                    "canMerge": False,
                    "writablePaths": ["**"],
                    "requiresApproval": ["deploy", "git_push", "delete", "db_migrate"],
                }
            )
        }
    )
    with pytest.raises(InvalidTaskActionError):
        engine.role_policy("general_implementer", widened)


def test_all_frozen_dangerous_actions_need_explicit_approval() -> None:
    engine = PermissionEngine(BuiltinCatalog.load())
    deployer = engine.role_policy("deployer")

    with pytest.raises(ApprovalError) as error:
        engine.assert_action_allowed(deployer, "network", approved=False)
    assert error.value.code == "APPROVAL_REQUIRED"
    engine.assert_action_allowed(deployer, "network", approved=True)


def test_only_integrator_can_merge() -> None:
    engine = PermissionEngine(BuiltinCatalog.load())
    implementer = engine.role_policy("general_implementer")
    integrator = engine.role_policy("integrator")

    with pytest.raises(InvalidTaskActionError):
        engine.assert_action_allowed(implementer, "git_merge", approved=True)
    engine.assert_action_allowed(integrator, "git_merge", approved=True)


def test_only_one_integrator_lease_can_be_active() -> None:
    engine = PermissionEngine(BuiltinCatalog.load())
    lease = IntegratorLease()
    integrator = engine.role_policy("integrator")

    lease.acquire("task-1", integrator)
    with pytest.raises(InvalidTaskActionError):
        lease.acquire("task-2", integrator)
    lease.release("task-1")
    lease.acquire("task-2", integrator)
    assert lease.active_task_id == "task-2"
