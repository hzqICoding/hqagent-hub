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
