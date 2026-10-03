import type { AgentView, LocalConversationView, LocalSceneView, RuntimeGuardView, PiGuardReason, LocalBaseRoleId, RemoteV5CatalogView, RemoteConversationView } from '@hqagent/protocol'
export const PI_GUARD_BLOCKED = 'PI 安全保护未就绪，不能运行任务'
export const PI_WIRE_PENDING = '等待远程线路升级：PI 需要完成修订 5 协商，本机使用不受影响'
export const piReasonLabels: Record<PiGuardReason,string> = {
  guard_not_loaded:'安全扩展未加载',uncontrolled_extensions:'存在未受控扩展',policy_unavailable:'安全策略不可用',tool_inventory_changed:'工具清单已变化',guard_timeout:'安全保护响应超时',invalid_request:'安全请求无效',argument_mismatch:'工具参数已变化',path_outside_scope:'路径超出授权范围',unsupported_shell:'命令语法无法安全核实',approval_required:'需要操作审批',approval_rejected:'操作审批已拒绝',approval_expired:'操作审批已过期',read_only_tool:'只读任务禁止此工具',tool_not_allowed:'工具未获授权',
}
export function piGuardReady(guard?: RuntimeGuardView) { return guard?.status === 'ready' && guard.isolation === 'hub_extension_only' && Array.isArray(guard.reasons) && guard.reasons.length === 0 }
export function piGuardLabel(guard?: RuntimeGuardView) { return piGuardReady(guard) ? '安全保护已就绪' : guard?.reasons?.includes('uncontrolled_extensions') ? '存在未受控扩展' : '安全扩展不可用' }
export function piModelLabel(id: string) { const slash=id.indexOf('/');return slash>0 ? `${id.slice(0,slash)} · ${id.slice(slash+1)}` : id }
export function piSuggestion(role: LocalBaseRoleId | string) { return `1aicode/deepseek/deepseek-v4-${role==='developer'?'flash':'pro'}` }
export function piRemoteCandidates(conversation: RemoteConversationView, catalog: RemoteV5CatalogView | null) {
  const roles=catalog?.scenes.find(scene=>scene.sceneId===conversation.sceneId)?.roleImageCapabilities || []
  const ids=roles.filter(role=>role.agentType==='pi'||catalog?.runtimes?.some(runtime=>runtime.agentId===role.agentId&&runtime.agentType==='pi')).map(role=>role.agentId)
  const isPi=conversation.agentType==='pi'||ids.length>0
  const runtimes=catalog?.runtimes?.filter(runtime=>runtime.agentType==='pi'&&(conversation.conversationKind==='native'||ids.includes(runtime.agentId))) || []
  return {isPi,runtimes}
}
export function remotePiBlock(conversation: RemoteConversationView, catalog: RemoteV5CatalogView | null, revisions?: number[]) {
  const {isPi,runtimes}=piRemoteCandidates(conversation,catalog)
  if(!isPi)return ''
  if(!revisions?.includes(5))return PI_WIRE_PENDING
  return !runtimes.length || runtimes.some(runtime=>!piGuardReady(runtime.guard)) ? PI_GUARD_BLOCKED : ''
}

export function localPiAgents(conversation: LocalConversationView | null | undefined, scenes: LocalSceneView[], agents: AgentView[]) {
  if(conversation?.conversationKind==='native' && conversation.agentType==='pi')return agents.filter(agent=>agent.adapterId==='pi')
  const ids=scenes.find(scene=>scene.id===conversation?.sceneId)?.roles.filter(role=>role.enabled).map(role=>role.agentInstanceId)||[]
  return agents.filter(agent=>agent.adapterId==='pi'&&ids.includes(agent.id))
}
export function localPiBlock(conversation: LocalConversationView | null | undefined, scenes: LocalSceneView[], agents: AgentView[]) {
  const targets=localPiAgents(conversation,scenes,agents)
  return ((conversation?.agentType==='pi'&&!targets.length)||targets.some(agent=>!piGuardReady(agent.guard))) ? PI_GUARD_BLOCKED : ''
}
