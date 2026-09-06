import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { BootstrapView, FeatureAvailability, FeatureState } from '@hqagent/protocol'
import { getUiGateway, mockGateway, MockGateway, HubApiError } from '@/shared/api'
import type { MockScenarioId } from '@/mocks/scenarios'

export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected' | 'mock'
export type HubGateType = 'maintenance' | 'feature_unavailable' | null

export interface LogEntry {
  id: string
  timestamp: string
  level: 'info' | 'warn' | 'error' | 'debug'
  source: string
  message: string
  details?: unknown
}

export type InspectorType = 'task' | 'agent' | 'approval' | 'session' | 'diagnosis' | null

export interface InspectorState {
  isOpen: boolean
  type: InspectorType
  data: unknown
}

export const useAppStore = defineStore('app', () => {
  const gateway = getUiGateway()

  // State
  const bootstrap = ref<BootstrapView | null>(null)
  const connectionStatus = ref<ConnectionStatus>(
    import.meta.env.VITE_GATEWAY_MODE === 'local' ? 'connecting' : 'mock'
  )
  const isLoading = ref<boolean>(false)
  const error = ref<string | null>(null)
  const activeScenario = ref<MockScenarioId>('happy-path')
  const hubGate = ref<HubGateType>(null)
  const hubGateReason = ref<string | null>(null)

  // UI States
  const sidebarCollapsed = ref<boolean>(false)
  const isLogDrawerOpen = ref<boolean>(false)
  const logFilterLevel = ref<'all' | 'info' | 'warn' | 'error'>('all')
  const isAutoScrollLogs = ref<boolean>(true)
  const logs = ref<LogEntry[]>([])

  const inspector = ref<InspectorState>({
    isOpen: false,
    type: null,
    data: null,
  })

  // Computed
  const isOffline = computed(() => connectionStatus.value === 'disconnected')
  const isMock = computed(() => connectionStatus.value === 'mock')
  const isTaskCreationAllowed = computed(
    () => hubGate.value === null && isFeatureAvailable('tasks')
  )

  const features = computed<FeatureAvailability | undefined>(() => {
    return bootstrap.value?.features
  })

  const filteredLogs = computed(() => {
    if (logFilterLevel.value === 'all') return logs.value
    return logs.value.filter((l) => l.level === logFilterLevel.value)
  })

  // Actions
  function isFeatureAvailable(featureKey: keyof FeatureAvailability): boolean {
    if (!bootstrap.value?.features) return true
    const state: FeatureState | undefined = bootstrap.value.features[featureKey]
    return state ? state.available : true
  }

  function getFeatureReason(featureKey: keyof FeatureAvailability): string | undefined {
    if (!bootstrap.value?.features) return undefined
    const state: FeatureState | undefined = bootstrap.value.features[featureKey]
    return state?.reason
  }

  function addLog(entry: Omit<LogEntry, 'id' | 'timestamp'>) {
    const newEntry: LogEntry = {
      id: `log_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      timestamp: new Date().toLocaleTimeString(),
      ...entry,
    }
    logs.value.push(newEntry)
    // Keep max 500 logs in memory
    if (logs.value.length > 500) {
      logs.value.shift()
    }
  }

  function clearLogs() {
    logs.value = []
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function toggleLogDrawer() {
    isLogDrawerOpen.value = !isLogDrawerOpen.value
  }

  function openInspector(type: InspectorType, data: unknown) {
    inspector.value = {
      isOpen: true,
      type,
      data,
    }
  }

  function closeInspector() {
    inspector.value = {
      isOpen: false,
      type: null,
      data: null,
    }
  }

  async function fetchBootstrap() {
    isLoading.value = true
    error.value = null

    try {
      addLog({
        level: 'info',
        source: 'AppStore',
        message: '正在获取系统引导数据 (Bootstrap)...',
      })
      const data = await gateway.getBootstrap()
      bootstrap.value = data

      if (data.maintenance) {
        hubGate.value = 'maintenance'
        hubGateReason.value = 'Local Hub 处于维护模式，暂不可创建新任务'
      } else if (data.features?.tasks?.available === false) {
        hubGate.value = 'feature_unavailable'
        hubGateReason.value = data.features?.tasks?.reason || '任务系统暂未就绪'
      } else {
        hubGate.value = null
        hubGateReason.value = null
      }

      if (connectionStatus.value !== 'mock') {
        connectionStatus.value = 'connected'
      }

      addLog({
        level: 'info',
        source: 'AppStore',
        message: `引导就绪: Hub v${data.appVersion}, ${data.agents.ready}/${data.agents.total} Agent 就绪`,
      })
    } catch (err: unknown) {
      if (err instanceof HubApiError) {
        if (err.code === 'HUB_MAINTENANCE') {
          hubGate.value = 'maintenance'
          hubGateReason.value = err.message || 'Local Hub 处于系统维护模式'
        } else if (err.code === 'FEATURE_UNAVAILABLE') {
          hubGate.value = 'feature_unavailable'
          hubGateReason.value = err.message || '功能暂不可用'
        }
      }
      const msg = err instanceof Error ? err.message : '获取系统引导数据失败'
      error.value = msg
      connectionStatus.value = 'disconnected'
      addLog({
        level: 'error',
        source: 'AppStore',
        message: `连接 Local Hub 失败: ${msg}`,
      })
    } finally {
      isLoading.value = false
    }
  }

  async function setScenario(scenarioId: MockScenarioId) {
    activeScenario.value = scenarioId
    if (gateway instanceof MockGateway) {
      gateway.setScenario(scenarioId)
    } else if (mockGateway) {
      mockGateway.setScenario(scenarioId)
    }
    addLog({
      level: 'info',
      source: 'MockGateway',
      message: `已切换调试场景: ${scenarioId}`,
    })
    await fetchBootstrap()
  }

  return {
    // State
    bootstrap,
    connectionStatus,
    isLoading,
    error,
    activeScenario,
    hubGate,
    hubGateReason,
    sidebarCollapsed,
    isLogDrawerOpen,
    logFilterLevel,
    isAutoScrollLogs,
    logs,
    inspector,

    // Computed
    isOffline,
    isMock,
    isTaskCreationAllowed,
    features,
    filteredLogs,

    // Actions
    isFeatureAvailable,
    getFeatureReason,
    addLog,
    clearLogs,
    toggleSidebar,
    toggleLogDrawer,
    openInspector,
    closeInspector,
    fetchBootstrap,
    setScenario,
  }
})
