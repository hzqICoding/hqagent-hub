import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  SessionView,
  SessionQuery,
  ResumeSessionInput,
  TaskDetailView,
  SessionStatus,
  SessionPurpose,
} from '@hqagent/protocol'
import { getUiGateway } from '@/shared/api'
import { useAppStore } from './app.store'

export const useSessionStore = defineStore('session', () => {
  const gateway = getUiGateway()
  const appStore = useAppStore()

  // State
  const sessions = ref<SessionView[]>([])
  const totalSessions = ref<number>(0)
  const currentSessionId = ref<string | null>(null)
  const isLoading = ref<boolean>(false)
  const isResuming = ref<boolean>(false)
  const error = ref<string | null>(null)
  const resumeError = ref<string | null>(null)

  // Filtering
  const filterStatus = ref<SessionStatus | 'all'>('all')
  const filterWorkspaceId = ref<string>('')
  const filterAgentId = ref<string>('')
  const filterPurpose = ref<SessionPurpose | 'all'>('all')
  const filterOnlyValid = ref<boolean>(false)
  const searchQuery = ref<string>('')

  // Computed
  const filteredSessions = computed(() => {
    return sessions.value.filter((sess) => {
      if (filterStatus.value !== 'all' && sess.status !== filterStatus.value) {
        return false
      }
      if (filterWorkspaceId.value && sess.workspaceId !== filterWorkspaceId.value) {
        return false
      }
      if (filterAgentId.value && sess.agentInstanceId !== filterAgentId.value) {
        return false
      }
      if (filterPurpose.value !== 'all' && sess.purpose !== filterPurpose.value) {
        return false
      }
      if (filterOnlyValid.value && !sess.isValid) {
        return false
      }
      if (searchQuery.value.trim()) {
        const q = searchQuery.value.toLowerCase()
        const matchesId = sess.id.toLowerCase().includes(q)
        const matchesExtId = sess.externalSessionId.toLowerCase().includes(q)
        const matchesAgent = sess.agentDisplayName.toLowerCase().includes(q)
        const matchesWorkspace = sess.workspaceName.toLowerCase().includes(q)
        const matchesSummary = sess.summary ? sess.summary.toLowerCase().includes(q) : false
        if (!matchesId && !matchesExtId && !matchesAgent && !matchesWorkspace && !matchesSummary) {
          return false
        }
      }
      return true
    })
  })

  const currentSession = computed<SessionView | null>(() => {
    if (!currentSessionId.value) return sessions.value[0] || null
    return sessions.value.find((s) => s.id === currentSessionId.value) || sessions.value[0] || null
  })

  const activeSessions = computed(() => sessions.value.filter((s) => s.status === 'active'))
  const validSessions = computed(() => sessions.value.filter((s) => s.isValid))

  // Actions
  async function fetchSessions(query: SessionQuery = {}) {
    isLoading.value = true
    error.value = null

    try {
      const pageResult = await gateway.listSessions(query)
      sessions.value = pageResult.items
      totalSessions.value = pageResult.total
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : '获取会话历史失败'
      appStore.addLog({
        level: 'error',
        source: 'SessionStore',
        message: `获取会话历史失败: ${error.value}`,
      })
    } finally {
      isLoading.value = false
    }
  }

  function selectSession(id: string) {
    currentSessionId.value = id
  }

  async function resumeSession(sessionId: string, input: ResumeSessionInput): Promise<TaskDetailView> {
    isResuming.value = true
    resumeError.value = null

    try {
      const taskDetail = await gateway.resumeSession(sessionId, input)
      appStore.addLog({
        level: 'info',
        source: 'SessionStore',
        message: `成功恢复会话 ${sessionId}，已创建新任务 ${taskDetail.id}`,
      })
      return taskDetail
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `恢复会话 ${sessionId} 失败`
      resumeError.value = msg
      appStore.addLog({
        level: 'error',
        source: 'SessionStore',
        message: msg,
      })
      throw err
    } finally {
      isResuming.value = false
    }
  }

  return {
    // State
    sessions,
    totalSessions,
    currentSessionId,
    isLoading,
    isResuming,
    error,
    resumeError,
    filterStatus,
    filterWorkspaceId,
    filterAgentId,
    filterPurpose,
    filterOnlyValid,
    searchQuery,

    // Computed
    filteredSessions,
    currentSession,
    activeSessions,
    validSessions,

    // Actions
    fetchSessions,
    selectSession,
    resumeSession,
  }
})
