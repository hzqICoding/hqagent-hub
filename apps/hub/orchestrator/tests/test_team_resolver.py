from protocol.generated.python import TeamProfileView

from orchestrator.catalog import BuiltinCatalog
from orchestrator.role_resolver import RoleResolver
from orchestrator.team_resolver import TeamResolver
from orchestrator.tests.fakes import agent, now


def profile() -> TeamProfileView:
    bindings = {}
    for role_id in BuiltinCatalog.load().roles:
        bindings[role_id] = {
            "roleId": role_id,
            "roleName": role_id,
            "primaryAgentId": "primary",
            "fallbackAgentIds": ["fallback"],
        }
    return TeamProfileView.model_validate(
        {
            "id": "workspace-profile",
            "name": "Workspace",
            "scope": "workspace",
            "workspaceId": "workspace",
            "isDefault": True,
            "roleBindings": bindings,
            "updatedAt": now(),
        }
    )


def test_team_resolution_preserves_fallback_source_and_capability_gaps() -> None:
    catalog = BuiltinCatalog.load()
    resolver = TeamResolver(catalog, RoleResolver(catalog))
    fallback = agent(
        "fallback",
        capabilities=(
            "structured_output",
            "file_write",
            "shell",
        ),
    )

    result = resolver.resolve(
        profile(),
        (agent("primary", status="offline"), fallback),
    )

    implementer = result.resolved_roles["general_implementer"]
    assert implementer.resolve_source.value == "fallback"
    assert implementer.is_fallback is True
    assert implementer.fallback_reason
    assert result.has_gaps is True
    assert any(str(gap.role_id) == "deployer" for gap in result.gaps) is False
    assert any(str(gap.role_id) == "orchestrator" for gap in result.gaps) is False
    # reviewer requires structured_output and is resolvable, while roles whose
    # hard requirements are absent are exposed as gaps rather than fake success.
    assert all(gap.missing_capabilities for gap in result.gaps)
