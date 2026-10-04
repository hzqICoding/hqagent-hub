"""Shared local-scene execution inputs and exact native instance selection."""
from protocol.generated.python import SaveTeamProfileInput
from core.errors import HubError


def scene_execution(scene, profile_id):
    roles = [role for role in scene.roles if role.enabled]
    profile = SaveTeamProfileInput.model_validate({
        'id': profile_id, 'name': f'{scene.name} · 本轮快照', 'scope': 'global', 'isDefault': False,
        'roleBindings': {r.role_id: {'roleId': r.role_id, 'roleName': r.role_name or r.role_id,
            'primaryAgentId': r.agent_instance_id, 'fallbackAgentIds': []} for r in roles},
    })
    overrides = {r.role_id: r.agent_instance_id for r in roles if r.agent_instance_id}
    options = {r.role_id: {'modelId': r.model_id_ or None, 'reasoningEffort': r.reasoning_effort,
                         'instructions': r.instructions} for r in roles}
    return profile, overrides, options


def native_execution_candidate(candidates, runtime_id, runtime):
    matches = [candidate for candidate in candidates if candidate.instance_id == runtime_id]
    if len(matches) != 1 or not matches[0].ready or 'session_resume' not in matches[0].capabilities:
        raise HubError('SESSION_NOT_RESUMABLE', '绑定的原生Runtime不可用、不唯一或未声明精确续接能力')
    from orchestrator.domain import ResolutionRequest, ResolutionGap
    decision, _, _ = runtime.resolve_agent(ResolutionRequest(
        role_id='analyst', agents=(matches[0],), task_override_agent_id=runtime_id, requires_approval=None))
    if isinstance(decision, ResolutionGap):
        raise HubError('SESSION_NOT_RESUMABLE', '绑定的原生Runtime不满足当前执行策略')
    return decision.agent


PI_FALLBACK_REASON = 'PI 暂不支持作为后备 Agent'


def reject_pi_fallbacks(value, identifiers):
    """Validate structured configurations, never instruction/body strings."""
    if isinstance(value, list):
        for item in value:
            reject_pi_fallbacks(item, identifiers)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in {'fallbackAgentIds', 'fallback_agent_ids'} and isinstance(item, list):
                if any(isinstance(identifier, str) and identifier in identifiers for identifier in item):
                    raise HubError('VALIDATION_FAILED', PI_FALLBACK_REASON)
            if isinstance(item, (dict, list)):
                reject_pi_fallbacks(item, identifiers)


def pi_instances(manager, values=()):
    identifiers = {value.id for value in values if str(value.adapter_id) == 'pi'}
    if callable(getattr(type(manager), 'runtime_instances', None)):
        identifiers.update(manager.runtime_instances('pi'))
    return identifiers


def primary_agent(request):
    if request.task_override_agent_id:
        return request.task_override_agent_id
    for profile in (request.workspace_profile, request.global_profile):
        binding = profile.binding_for(request.role_id) if profile else None
        if binding and binding.primary_agent_id:
            return binding.primary_agent_id
    return None


def primary_only_candidates(request):
    """One rule for actual dispatch, team resolution and image previews.

    Invalid historical fallback settings remain intact and resolve to a gap.
    PI is never an automatic/manual fallback; an explicit PI primary is pinned
    even while unavailable, instead of silently switching runtime families.
    """
    from dataclasses import replace
    from orchestrator.domain import ResolutionGap
    identifiers = {a.instance_id for a in request.agents if str(a.adapter_id) == 'pi'}
    for profile in (request.workspace_profile, request.global_profile):
        if profile and any(identifier in identifiers for binding in profile.bindings.values()
                           for identifier in binding.fallback_agent_ids):
            return ResolutionGap(request.role_id, PI_FALLBACK_REASON)
    selected = primary_agent(request)
    if selected in identifiers:
        candidates = tuple(a for a in request.agents if a.instance_id == selected)
    else:
        candidates = tuple(a for a in request.agents if a.instance_id not in identifiers)
    return replace(request, agents=candidates)
