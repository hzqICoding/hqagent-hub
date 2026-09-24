from orchestrator.catalog import BuiltinCatalog


def test_frozen_registry_counts_and_role_permissions() -> None:
    catalog = BuiltinCatalog.load()

    assert len(catalog.roles) == 11
    assert len(catalog.capabilities) == 14
    assert len(catalog.dangerous_actions) == 7
    assert catalog.role("integrator").permissions.can_merge is True
    assert catalog.role("reviewer").permissions.can_approve is True
    assert catalog.capabilities["tool_approval"].hard is True
    assert catalog.capabilities["coding"].hard is False
