import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { AgentView, AgentDiscoveryResult, AgentStatus } from '@hqagent/protocol'
import { getUiGateway } from '@/shared/api'
import { useAppStore } from './app.store'

export const useAgentStore = defineStore('agent', () => {
  const gateway = getUiGateway()
  const appStore = useAppStore()

  // State
  const agents = ref<AgentView[]>([])
  const discovery = ref<AgentDiscoveryResult | null>(null)
  const isLoading = ref<boolean>(false)
  const isRefreshing = ref<boolean>(false)
  const error = ref<string | null>(null)

  const searchQuery = ref<string>('')
  const statusFilter = ref<string>('all') // 'all' | 'ready' | 'busy' | 'issues' | 'disabled'
  const selectedAgent = ref<AgentView | null>(null)

  // Computed Counts
  const totalCount = computed(() => agents.value.length)
  const readyAgents = computed(() => agents.value.filter((a) => a.status === 'ready'))
  const readyCount = computed(() => agents.value.filter((a) => a.status === 'ready').length)
  const busyCount = computed(() => agents.value.filter((a) => a.status === 'busy').length)
  const disabledCount = computed(() => agents.value.filter((a) => a.status === 'disabled').length)
  const issuesCount = computed(() =>
    agents.value.filter((a) =>
      ['not_logged_in', 'incompatible', 'error', 'offline'].includes(a.status)
    ).length
  )

  // Filtered list
  const filteredAgents = computed(() => {
    let result = agents.value

    // Status filter
    if (statusFilter.value === 'ready') {
      result = result.filter((a) => a.status === 'ready')
    } else if (statusFilter.value === 'busy') {
      result = result.filter((a) => a.status === 'busy')
    } else if (statusFilter.value === 'disabled') {
      result = result.filter((a) => a.status === 'disabled')
    } else if (statusFilter.value === 'issues') {
      result = result.filter((a) =>
        ['not_logged_in', 'incompatible', 'error', 'offline'].includes(a.status)
      )
    }

    // Search filter
    if (searchQuery.value.trim()) {
      const q = searchQuery.value.toLowerCase().trim()
      result = result.filter(
        (a) =>
          a.displayName.toLowerCase().includes(q) ||
          a.adapterId.toLowerCase().includes(q) ||
          a.id.toLowerCase().includes(q) ||
          a.capabilities.some((c) => c.name.toLowerCase().includes(q))
      )
    }

    return result
  })

  // Actions
  async function fetchAgents() {
    isLoading.value = true
    error.value = null

    try {
      const data = await gateway.listAgents()
      agents.value = data
      appStore.addLog({
        level: 'info',
        source: 'AgentStore',
        message: `成功获取 Agent 列表，共 ${data.length} 个实例`,
      })
    } catch (err: any) {
      const msg = err?.message || '获取 Agent 列表失败'
      error.value = msg
      appStore.addLog({
        level: 'error',
        source: 'AgentStore',
        message: `获取 Agent 列表失败: ${msg}`,
      })
    } finally {
      isLoading.value = false
    }
  }

  async function refreshDiscovery() {
    isRefreshing.value = true
    error.value = null

    try {
      appStore.addLog({
        level: 'info',
        source: 'AgentStore',
        message: '正在扫描本地已安装的 Agent (Discovery)...',
      })
      const result = await gateway.refreshAgents()
      discovery.value = result
      agents.value = result.discovered

      const readyNum = result.discovered.filter((a) => a.status === 'ready').length
      const errorCount = result.errors?.length || 0
      appStore.addLog({
        level: errorCount > 0 ? 'warn' : 'info',
        source: 'AgentStore',
        message: `Agent 探测完成: 发现 ${result.total} 个, 就绪 ${readyNum} 个${
          errorCount > 0 ? `, 异常 ${errorCount} 个` : ''
        }`,
      })
    } catch (err: any) {
      const msg = err?.message || '刷新 Agent 探测失败'
      error.value = msg
      appStore.addLog({
        level: 'error',
        source: 'AgentStore',
        message: `探测失败: ${msg}`,
      })
    } finally {
      isRefreshing.value = false
    }
  }

  function toggleAgent(id: string, enabled: boolean) {
    const agent = agents.value.find((a) => a.id === id)
    if (agent) {
      agent.status = (enabled ? 'ready' : 'disabled') as AgentStatus
      appStore.addLog({
        level: 'info',
        source: 'AgentStore',
        message: `Agent [${agent.displayName}] 状态已变更为: ${agent.status}`,
      })
    }
  }

  function selectAgent(agent: AgentView | null) {
    selectedAgent.value = agent
    if (agent) {
      appStore.openInspector('agent', agent)
    }
  }

  return {
    // State
    agents,
    discovery,
    isLoading,
    isRefreshing,
    error,
    searchQuery,
    statusFilter,
    selectedAgent,

    // Computed
    totalCount,
    readyAgents,
    readyCount,
    busyCount,
    disabledCount,
    issuesCount,
    filteredAgents,

    // Actions
    fetchAgents,
    refreshDiscovery,
    toggleAgent,
    selectAgent,
  }
})
