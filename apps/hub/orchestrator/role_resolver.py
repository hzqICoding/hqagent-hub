from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from protocol.generated.python import CapabilityId, ResolveSource

from .catalog import BuiltinCatalog, RoleDefinition
from .domain import (
    AgentCandidate,
    ResolutionDecision,
    ResolutionGap,
    ResolutionRequest,
    RoleBinding,
    ProfileSnapshot,
)
from .errors import RoleUnresolvedError


@dataclass(frozen=True, slots=True)
class _CandidateCheck:
    agent: AgentCandidate | None
    eligible: bool
    reason: str
    missing_capabilities: tuple[str, ...] = ()


class RoleResolver:
    """Resolve Role -> Agent Instance using the frozen six-level order."""

    def __init__(self, catalog: BuiltinCatalog) -> None:
        self.catalog = catalog

    def resolve(self, request: ResolutionRequest) -> ResolutionDecision | ResolutionGap:
        from runtime.execution_selection import primary_only_candidates
        request = primary_only_candidates(request)
        if isinstance(request, ResolutionGap):
            return request
        role = self.catalog.role(request.role_id)
        agents = {agent.instance_id: agent for agent in request.agents}
        workspace_binding = self._binding(request.workspace_profile, request.role_id)
        global_binding = self._binding(request.global_profile, request.role_id)
        required_hard = self._required_hard_capabilities(
            role,
            request,
            workspace_binding,
            global_binding,
        )
        attempted: list[str] = []
        checks: list[_CandidateCheck] = []

        # 1. Task-level override.
        decision = self._try_named(
            request.role_id,
            request.task_override_agent_id,
            ResolveSource.TASK_OVERRIDE,
            agents,
            required_hard,
            request.excluded_agent_ids,
            attempted,
            checks,
        )
        if decision:
            return decision

        # 2. Workspace profile primary.
        decision = self._try_named(
            request.role_id,
            workspace_binding.primary_agent_id if workspace_binding else None,
            ResolveSource.WORKSPACE_PROFILE,
            agents,
            required_hard,
            request.excluded_agent_ids,
            attempted,
            checks,
        )
        if decision:
            return decision

        # 3. Global profile primary.
        decision = self._try_named(
            request.role_id,
            global_binding.primary_agent_id if global_binding else None,
            ResolveSource.GLOBAL_PROFILE,
            agents,
            required_hard,
            request.excluded_agent_ids,
            attempted,
            checks,
        )
        if decision:
            return decision

        configured_ids = self._configured_ids(
            request,
            workspace_binding,
            global_binding,
        )

        # 4. Capability match. Configured fallbacks are intentionally reserved
        # for level 5 so the UI never mislabels a configured fallback as an
        # automatic capability match.
        automatic = [
            agent
            for agent in request.agents
            if agent.instance_id not in configured_ids
            and agent.instance_id not in request.excluded_agent_ids
            and agent.automatically_selectable
            and agent.integration_kind != "gui_automation"
        ]
        ranked = self._rank_automatic(role, automatic, required_hard)
        if ranked:
            agent = ranked[0]
            return ResolutionDecision(
                role_id=request.role_id,
                agent=agent,
                source=ResolveSource.CAPABILITY_MATCH,
                attempted=tuple(attempted),
            )
        for agent in automatic:
            check = self._check(agent, required_hard, request.excluded_agent_ids)
            checks.append(check)
            attempted.append(f"capability_match:{agent.instance_id}:{check.reason}")

        # 5. Workspace fallbacks first, then global fallbacks, preserving the
        # configured order and deduplicating instances.
        fallback_ids = self._fallback_ids(workspace_binding, global_binding)
        for fallback_id in fallback_ids:
            check = self._check(agents.get(fallback_id), required_hard, request.excluded_agent_ids)
            checks.append(check)
            attempted.append(f"fallback:{fallback_id}:{check.reason}")
            if check.eligible and check.agent is not None:
                return ResolutionDecision(
                    role_id=request.role_id,
                    agent=check.agent,
                    source=ResolveSource.FALLBACK,
                    is_fallback=True,
                    fallback_reason=self._fallback_reason(check.agent, attempted[:-1]),
                    attempted=tuple(attempted),
                )

        # 6. A user choice only participates here. It is excluded from level 4
        # above, otherwise a manual choice would be falsely reported as an
        # automatic match.
        if request.manual_agent_id:
            check = self._check(
                agents.get(request.manual_agent_id),
                required_hard,
                request.excluded_agent_ids,
            )
            checks.append(check)
            attempted.append(f"manual:{request.manual_agent_id}:{check.reason}")
            if check.eligible and check.agent is not None:
                return ResolutionDecision(
                    role_id=request.role_id,
                    agent=check.agent,
                    source=ResolveSource.MANUAL,
                    attempted=tuple(attempted),
                )

        missing = self._best_missing(required_hard, checks, request.agents)
        strategy = self._missing_strategy(request)
        reason = self._gap_reason(request.role_id, missing, attempted)
        return ResolutionGap(
            role_id=request.role_id,
            reason=reason,
            missing_capabilities=missing,
            attempted=tuple(attempted),
            requires_user_choice=strategy != "fallback_then_fail",
        )

    def resolve_or_raise(self, request: ResolutionRequest) -> ResolutionDecision:
        result = self.resolve(request)
        if isinstance(result, ResolutionGap):
            raise RoleUnresolvedError(
                result.role_id,
                result.reason,
                missing_capabilities=result.missing_capabilities,
                attempted=result.attempted,
            )
        return result

    @staticmethod
    def _binding(profile: ProfileSnapshot | None, role_id: str) -> RoleBinding | None:
        if profile is None:
            return None
        return profile.binding_for(role_id)

    def _required_hard_capabilities(
        self,
        role: RoleDefinition,
        request: ResolutionRequest,
        workspace_binding: RoleBinding | None,
        global_binding: RoleBinding | None,
    ) -> frozenset[str]:
        requested = set(role.required_capabilities) | set(request.required_capabilities)
        required = set(self.catalog.hard_capabilities(frozenset(requested)))
        for binding in (workspace_binding, global_binding):
            if binding:
                required.update(binding.required_hard_capabilities)
        if request.requires_approval:
            required.add(CapabilityId.TOOL_APPROVAL.value)
        return frozenset(required)

    def _try_named(
        self,
        role_id: str,
        agent_id: str | None,
        source: ResolveSource,
        agents: dict[str, AgentCandidate],
        required_hard: frozenset[str],
        excluded_agent_ids: frozenset[str],
        attempted: list[str],
        checks: list[_CandidateCheck],
    ) -> ResolutionDecision | None:
        if not agent_id:
            return None
        check = self._check(agents.get(agent_id), required_hard, excluded_agent_ids)
        checks.append(check)
        attempted.append(f"{source.value}:{agent_id}:{check.reason}")
        if not check.eligible or check.agent is None:
            return None
        return ResolutionDecision(
            role_id=role_id,
            agent=check.agent,
            source=source,
            attempted=tuple(attempted),
        )

    @staticmethod
    def _check(
        agent: AgentCandidate | None,
        required_hard: frozenset[str],
        excluded_agent_ids: frozenset[str],
    ) -> _CandidateCheck:
        if agent is None:
            return _CandidateCheck(None, False, "agent_not_found")
        if agent.instance_id in excluded_agent_ids:
            return _CandidateCheck(agent, False, "agent_excluded")
        if not agent.ready:
            return _CandidateCheck(agent, False, f"status_{agent.status}")
        missing = tuple(sorted(required_hard - agent.capabilities))
        if missing:
            return _CandidateCheck(agent, False, "capability_missing", missing)
        return _CandidateCheck(agent, True, "ready")

    def _rank_automatic(
        self,
        role: RoleDefinition,
        agents: Iterable[AgentCandidate],
        required_hard: frozenset[str],
    ) -> list[AgentCandidate]:
        eligible = [
            agent
            for agent in agents
            if self._check(agent, required_hard, frozenset()).eligible
        ]

        def score(agent: AgentCandidate) -> tuple[int, int, int, str]:
            required_soft = role.required_capabilities - required_hard
            required_score = len(required_soft & agent.capabilities)
            preferred_score = len(role.preferred_capabilities & agent.capabilities)
            return (-required_score, -preferred_score, -len(agent.capabilities), agent.instance_id)

        return sorted(eligible, key=score)

    @staticmethod
    def _configured_ids(
        request: ResolutionRequest,
        workspace_binding: RoleBinding | None,
        global_binding: RoleBinding | None,
    ) -> frozenset[str]:
        result = {
            value
            for value in (request.task_override_agent_id, request.manual_agent_id)
            if value
        }
        for binding in (workspace_binding, global_binding):
            if not binding:
                continue
            if binding.primary_agent_id:
                result.add(binding.primary_agent_id)
            result.update(binding.fallback_agent_ids)
        return frozenset(result)

    @staticmethod
    def _fallback_ids(
        workspace_binding: RoleBinding | None,
        global_binding: RoleBinding | None,
    ) -> tuple[str, ...]:
        result: list[str] = []
        for binding in (workspace_binding, global_binding):
            if not binding:
                continue
            for agent_id in binding.fallback_agent_ids:
                if agent_id not in result:
                    result.append(agent_id)
        return tuple(result)

    @staticmethod
    def _fallback_reason(agent: AgentCandidate, earlier_attempts: list[str]) -> str:
        if not earlier_attempts:
            return f"按 Team Profile 的备用链选择了 {agent.display_name}"
        failed = "；".join(earlier_attempts)
        return f"前序候选不可用（{failed}），按备用链选择了 {agent.display_name}"

    @staticmethod
    def _best_missing(
        required_hard: frozenset[str],
        checks: list[_CandidateCheck],
        agents: tuple[AgentCandidate, ...],
    ) -> tuple[str, ...]:
        missing_sets = [check.missing_capabilities for check in checks if check.missing_capabilities]
        if not missing_sets:
            missing_sets = [
                tuple(sorted(required_hard - agent.capabilities))
                for agent in agents
                if agent.ready and required_hard - agent.capabilities
            ]
        if missing_sets:
            return min(missing_sets, key=lambda item: (len(item), item))
        return tuple(sorted(required_hard)) if not any(agent.ready for agent in agents) else ()

    @staticmethod
    def _missing_strategy(request: ResolutionRequest) -> str:
        for profile in (request.workspace_profile, request.global_profile):
            if profile is not None:
                return profile.missing_agent_strategy
        return "fallback_then_ask"

    @staticmethod
    def _gap_reason(role_id: str, missing: tuple[str, ...], attempted: list[str]) -> str:
        if missing:
            return f"角色 {role_id} 没有可用 Agent；缺少硬能力：{', '.join(missing)}"
        if attempted:
            return f"角色 {role_id} 的候选 Agent 均不可用，请选择其他 Agent 或暂停节点"
        return f"角色 {role_id} 尚未配置可用 Agent，请选择 Agent 或暂停节点"
