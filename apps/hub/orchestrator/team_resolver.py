from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from protocol.generated.python import ResolvedTeamView, TeamProfileView

from .catalog import BuiltinCatalog
from .domain import AgentCandidate, ProfileSnapshot, ResolutionGap, ResolutionRequest
from .role_resolver import RoleResolver


class TeamResolver:
    def __init__(self, catalog: BuiltinCatalog, role_resolver: RoleResolver) -> None:
        self.catalog = catalog
        self.role_resolver = role_resolver

    def resolve(
        self,
        profile: TeamProfileView,
        agents: Iterable[AgentCandidate],
        *,
        global_profile: TeamProfileView | None = None,
        workspace_id: str | None = None,
    ) -> ResolvedTeamView:
        agent_values = tuple(agents)
        selected = ProfileSnapshot.from_view(profile)
        global_snapshot = ProfileSnapshot.from_view(global_profile) if global_profile else None
        workspace_snapshot = selected if profile.scope == "workspace" else None
        if profile.scope == "global":
            global_snapshot = selected

        resolved_roles: dict[str, object] = {}
        gaps: list[dict[str, object]] = []
        for role_id in self.catalog.roles:
            result = self.role_resolver.resolve(
                ResolutionRequest(
                    role_id=role_id,
                    agents=agent_values,
                    workspace_profile=workspace_snapshot,
                    global_profile=global_snapshot,
                )
            )
            if isinstance(result, ResolutionGap):
                gap: dict[str, object] = {"roleId": role_id, "reason": result.reason}
                if result.missing_capabilities:
                    gap["missingCapabilities"] = list(result.missing_capabilities)
                gaps.append(gap)
                continue
            resolved_roles[role_id] = {
                "roleId": role_id,
                "resolvedAgentId": result.agent.instance_id,
                "resolvedAgentName": result.agent.display_name,
                "resolveSource": result.source.value,
                "isFallback": result.is_fallback,
                "fallbackReason": result.fallback_reason,
                "missingCapabilities": list(result.missing_capabilities) or None,
            }

        return ResolvedTeamView.model_validate(
            {
                "profileId": profile.id,
                "workspaceId": workspace_id or profile.workspace_id,
                "resolvedRoles": resolved_roles,
                "hasGaps": bool(gaps),
                "gaps": gaps,
                "resolvedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        )
