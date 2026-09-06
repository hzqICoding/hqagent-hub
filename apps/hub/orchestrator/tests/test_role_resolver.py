import pytest
from protocol.generated.python import ResolveSource

from orchestrator.catalog import BuiltinCatalog
from orchestrator.domain import ProfileSnapshot, ResolutionDecision, ResolutionGap, ResolutionRequest, RoleBinding
from orchestrator.role_resolver import RoleResolver
from orchestrator.tests.fakes import agent


@pytest.fixture
def resolver() -> RoleResolver:
    return RoleResolver(BuiltinCatalog.load())


def profile(profile_id: str, primary: str | None = None, fallbacks: tuple[str, ...] = ()) -> ProfileSnapshot:
    return ProfileSnapshot(
        profile_id=profile_id,
        scope="workspace" if profile_id.startswith("workspace") else "global",
        bindings={
            "general_implementer": RoleBinding(
                primary_agent_id=primary,
                fallback_agent_ids=fallbacks,
            )
        },
    )


def decide(resolver: RoleResolver, **kwargs: object) -> ResolutionDecision:
    result = resolver.resolve(
        ResolutionRequest(
            role_id="general_implementer",
            agents=kwargs.pop("agents"),  # type: ignore[arg-type]
            **kwargs,
        )
    )
    assert isinstance(result, ResolutionDecision)
    return result


def test_level_1_task_override_wins(resolver: RoleResolver) -> None:
    result = decide(
        resolver,
        agents=(agent("override"), agent("workspace"), agent("auto")),
        task_override_agent_id="override",
        workspace_profile=profile("workspace", "workspace"),
    )
    assert result.agent.instance_id == "override"
    assert result.source == ResolveSource.TASK_OVERRIDE


def test_level_2_workspace_profile_wins(resolver: RoleResolver) -> None:
    result = decide(
        resolver,
        agents=(agent("workspace"), agent("global"), agent("auto")),
        workspace_profile=profile("workspace", "workspace"),
        global_profile=profile("global", "global"),
    )
    assert result.agent.instance_id == "workspace"
    assert result.source == ResolveSource.WORKSPACE_PROFILE


def test_level_3_global_profile_wins(resolver: RoleResolver) -> None:
    result = decide(
        resolver,
        agents=(agent("global"), agent("auto")),
        global_profile=profile("global", "global"),
    )
    assert result.agent.instance_id == "global"
    assert result.source == ResolveSource.GLOBAL_PROFILE


def test_level_4_capability_match_wins_before_fallback(resolver: RoleResolver) -> None:
    result = decide(
        resolver,
        agents=(agent("primary", status="offline"), agent("configured-fallback"), agent("auto")),
        workspace_profile=profile("workspace", "primary", ("configured-fallback",)),
    )
    assert result.agent.instance_id == "auto"
    assert result.source == ResolveSource.CAPABILITY_MATCH
    assert result.is_fallback is False


def test_level_5_fallback_is_truthfully_marked(resolver: RoleResolver) -> None:
    result = decide(
        resolver,
        agents=(agent("primary", status="offline"), agent("fallback")),
        workspace_profile=profile("workspace", "primary", ("fallback",)),
    )
    assert result.agent.instance_id == "fallback"
    assert result.source == ResolveSource.FALLBACK
    assert result.is_fallback is True
    assert "前序候选不可用" in (result.fallback_reason or "")
    payload = result.to_payload()
    assert payload.resolve_source == ResolveSource.FALLBACK
    assert payload.is_fallback is True
    assert payload.fallback_reason


def test_level_6_manual_choice_is_not_mislabeled_as_automatic(resolver: RoleResolver) -> None:
    result = decide(
        resolver,
        agents=(agent("manual"),),
        manual_agent_id="manual",
    )
    assert result.agent.instance_id == "manual"
    assert result.source == ResolveSource.MANUAL
    assert result.is_fallback is False


def test_failed_override_continues_to_capability_match(resolver: RoleResolver) -> None:
    result = decide(
        resolver,
        agents=(agent("override", status="offline"), agent("auto")),
        task_override_agent_id="override",
    )
    assert result.agent.instance_id == "auto"
    assert result.source == ResolveSource.CAPABILITY_MATCH


def test_hard_capability_gap_is_reported_without_silent_degrade(resolver: RoleResolver) -> None:
    result = resolver.resolve(
        ResolutionRequest(
            role_id="general_implementer",
            agents=(agent("read-only", capabilities=("structured_output",)),),
        )
    )
    assert isinstance(result, ResolutionGap)
    assert result.missing_capabilities == ("file_write",)
    assert "缺少硬能力" in result.reason


def test_requires_approval_needs_tool_approval_before_dispatch(resolver: RoleResolver) -> None:
    result = resolver.resolve(
        ResolutionRequest(
            role_id="general_implementer",
            agents=(agent("no-approval"),),
            requires_approval=("git_push",),
        )
    )
    assert isinstance(result, ResolutionGap)
    assert result.missing_capabilities == ("tool_approval",)
