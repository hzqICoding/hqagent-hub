from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from protocol.generated.python import (
    AgentStatus,
    AgentView,
    CapabilityId,
    NodeResolvedPayload,
    ResolveSource,
    RoleBindingView,
    RoleId,
    TeamProfileView,
    SaveTeamProfileInput,
)


def _text(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


@dataclass(frozen=True, slots=True)
class AgentCandidate:
    instance_id: str
    adapter_id: str
    display_name: str
    status: str
    capabilities: frozenset[str]
    automatically_selectable: bool = True
    integration_kind: str | None = None

    @classmethod
    def from_view(cls, value: AgentView) -> "AgentCandidate":
        capabilities: set[str] = set()
        for item in value.capabilities:
            # A hard capability can only originate from Adapter detection. A user
            # preference must never manufacture shell/file/approval support.
            if item.supported is False:
                continue
            if item.hard and _text(item.source) == "user":
                continue
            capabilities.add(_text(item.id))
        return cls(
            instance_id=value.id,
            adapter_id=value.adapter_id,
            display_name=value.display_name,
            status=_text(value.status),
            capabilities=frozenset(capabilities),
        )

    @property
    def ready(self) -> bool:
        return self.status == AgentStatus.READY.value


@dataclass(frozen=True, slots=True)
class RoleBinding:
    primary_agent_id: str | None = None
    fallback_agent_ids: tuple[str, ...] = ()
    required_hard_capabilities: frozenset[str] = frozenset()
    allow_shell: bool | None = None
    read_only_fs: bool | None = None

    @classmethod
    def from_view(cls, value: RoleBindingView | None) -> "RoleBinding | None":
        if value is None:
            return None
        constraints = value.constraints
        return cls(
            primary_agent_id=value.primary_agent_id or None,
            fallback_agent_ids=tuple(value.fallback_agent_ids),
            required_hard_capabilities=frozenset(
                _text(item) for item in (constraints.require_hard_capabilities or [])
            )
            if constraints
            else frozenset(),
            allow_shell=constraints.allow_shell if constraints else None,
            read_only_fs=constraints.read_only_fs if constraints else None,
        )


@dataclass(frozen=True, slots=True)
class ProfileSnapshot:
    profile_id: str
    scope: str
    bindings: Mapping[str, RoleBinding]
    missing_agent_strategy: str = "fallback_then_ask"

    @classmethod
    def from_view(cls, value: TeamProfileView | SaveTeamProfileInput) -> "ProfileSnapshot":
        bindings = {
            role_id: binding
            for role_id, raw in value.role_bindings.items()
            if (binding := RoleBinding.from_view(raw)) is not None
        }
        strategy = (
            value.policies.missing_agent_strategy
            if value.policies is not None
            else "fallback_then_ask"
        )
        return cls(
            profile_id=value.id,
            scope=value.scope,
            bindings=bindings,
            missing_agent_strategy=strategy,
        )

    def binding_for(self, role_id: str) -> RoleBinding | None:
        return self.bindings.get(role_id)


@dataclass(frozen=True, slots=True)
class ResolutionRequest:
    role_id: str
    agents: tuple[AgentCandidate, ...]
    task_override_agent_id: str | None = None
    workspace_profile: ProfileSnapshot | None = None
    global_profile: ProfileSnapshot | None = None
    manual_agent_id: str | None = None
    required_capabilities: frozenset[str] = frozenset()
    requires_approval: tuple[str, ...] = ()
    excluded_agent_ids: frozenset[str] = frozenset()

    @classmethod
    def build(
        cls,
        role_id: str | RoleId,
        agents: Iterable[AgentCandidate],
        **kwargs: object,
    ) -> "ResolutionRequest":
        return cls(role_id=_text(role_id), agents=tuple(agents), **kwargs)


@dataclass(frozen=True, slots=True)
class ResolutionDecision:
    role_id: str
    agent: AgentCandidate
    source: ResolveSource
    is_fallback: bool = False
    fallback_reason: str | None = None
    missing_capabilities: tuple[str, ...] = ()
    attempted: tuple[str, ...] = ()

    def to_payload(self) -> NodeResolvedPayload:
        return NodeResolvedPayload.model_validate(
            {
                "roleId": self.role_id,
                "resolvedAgentId": self.agent.instance_id,
                "resolvedAgentName": self.agent.display_name,
                "resolveSource": self.source.value,
                "isFallback": self.is_fallback,
                "fallbackReason": self.fallback_reason,
                "missingCapabilities": list(self.missing_capabilities) or None,
            }
        )


@dataclass(frozen=True, slots=True)
class ResolutionGap:
    role_id: str
    reason: str
    missing_capabilities: tuple[str, ...] = ()
    attempted: tuple[str, ...] = ()
    requires_user_choice: bool = True


@dataclass(frozen=True, slots=True)
class RuntimeEventDraft:
    type: str
    aggregate_type: str
    aggregate_id: str
    payload: object
    task_id: str | None = None
    node_id: str | None = None
    role_id: str | None = None
    agent_instance_id: str | None = None
    adapter_id: str | None = None


@dataclass(slots=True)
class NodeRuntimeState:
    node_id: str
    role_id: str | None = None
    status: str = "pending"
    resolved_agent_id: str | None = None
    resolved_agent_name: str | None = None
    resolve_source: str | None = None
    is_fallback: bool = False
    fallback_reason: str | None = None
    missing_capabilities: tuple[str, ...] = ()
    session_id: str | None = None
    external_session_id: str | None = None
    error: str | None = None
    changed_files: tuple[str, ...] = ()
    violation_paths: tuple[str, ...] = ()


@dataclass(slots=True)
class TaskRuntimeState:
    task_id: str
    status: str = "draft"
    objective: str | None = None
    workspace_id: str | None = None
    profile_id: str | None = None
    last_seq: int = 0
    seen_event_ids: set[str] = field(default_factory=set)
    nodes: dict[str, NodeRuntimeState] = field(default_factory=dict)
    pending_approval_id: str | None = None
    failure_reason: str | None = None
