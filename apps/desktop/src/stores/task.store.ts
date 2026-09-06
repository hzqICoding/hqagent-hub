import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  TaskSummaryView,
  TaskDetailView,
  TaskNodeView,
  TaskArtifactView,
  TaskQuery,
  CreateTaskInput,
  TaskActionInput,
  HubEvent,
  TaskStatus,
  NodeResolvedPayload,
  TaskStatusChangedPayload,
  AgentStartedPayload,
  AgentProgressPayload,
  AgentCompletedPayload,
  AgentFailedPayload,
  PathViolationPayload,
  ApprovalRequiredPayload,
  ApprovalResolvedPayload,
} from '@hqagent/protocol'
import { getUiGateway, HubApiError, type EventSubscription } from '@/shared/api'
import { useAppStore } from './app.store'

export const useTaskStore = defineStore('task', () => {
  const gateway = getUiGateway()
  const appStore = useAppStore()

  // State
  const tasks = ref<TaskSummaryView[]>([])
  const totalTasks = ref<number>(0)
  const currentTask = ref<TaskDetailView | null>(null)
  const isLoading = ref<boolean>(false)
  const isActionLoading = ref<boolean>(false)
  const error = ref<string | null>(null)
  const actionError = ref<string | null>(null)
  const orphanProcessIds = ref<number[]>([])

  // Filtering
  const filterStatus = ref<TaskStatus | 'all'>('all')
  const filterWorkspaceId = ref<string>('')
  const filterSearch = ref<string>('')

  // Event stream for current task
  const events = ref<HubEvent[]>([])
  const eventSeenIds = ref<Set<string>>(new Set())
  const lastEventSeq = ref<number>(0)
  const isSubscribed = ref<boolean>(false)
  let activeSubscription: EventSubscription | null = null

  // Event stream filters
  const eventFilterType = ref<string>('all')
  const eventFilterNodeId = ref<string>('all')
  const eventSearch = ref<string>('')

  // Computed
  const filteredTasks = computed(() => {
    return tasks.value.filter((task) => {
      if (filterStatus.value !== 'all' && task.status !== filterStatus.value) {
        return false
      }
      if (filterWorkspaceId.value && task.workspaceId !== filterWorkspaceId.value) {
        return false
      }
      if (filterSearch.value.trim()) {
        const q = filterSearch.value.toLowerCase()
        const matchesObjective = task.objective.toLowerCase().includes(q)
        const matchesId = task.id.toLowerCase().includes(q)
        const matchesAgent = task.currentAgent?.toLowerCase().includes(q)
        if (!matchesObjective && !matchesId && !matchesAgent) return false
      }
      return true
    })
  })

  const runningTasks = computed(() => tasks.value.filter((t) => t.status === 'running'))
  const waitingApprovalTasks = computed(() => tasks.value.filter((t) => t.status === 'waiting_approval'))

  const currentNodes = computed<TaskNodeView[]>(() => currentTask.value?.nodes || [])
  const currentArtifacts = computed<TaskArtifactView[]>(() => currentTask.value?.artifacts || [])

  // Trap 1: Has any node currently executing or resolving
  const hasRunningNode = computed(() => {
    return currentNodes.value.some((n) => n.status === 'running' || n.status === 'resolving')
  })

  // Action constraints adhering to protocol and W0 rulings
  const canPause = computed(() => currentTask.value?.status === 'running')
  const canResume = computed(() => currentTask.value?.status === 'paused')
  const canCancel = computed(() => {
    if (!currentTask.value) return false
    return ['queued', 'running', 'waiting_approval', 'paused'].includes(currentTask.value.status)
  })
  const canRetry = computed(() => currentTask.value?.status === 'failed')

  // Trap 1: append_instruction only allowed when all nodes are idle
  const canAppendInstruction = computed(() => {
    if (!currentTask.value) return false
    if (['succeeded', 'failed', 'cancelled'].includes(currentTask.value.status)) return false
    return !hasRunningNode.value
  })

  // Event stream filtered list
  const filteredEvents = computed(() => {
    let list = events.value
    if (eventFilterType.value !== 'all') {
      list = list.filter((e) => e.type === eventFilterType.value)
    }
    if (eventFilterNodeId.value !== 'all') {
      list = list.filter((e) => e.nodeId === eventFilterNodeId.value)
    }
    if (eventSearch.value.trim()) {
      const q = eventSearch.value.toLowerCase()
      list = list.filter((e) => {
        const matchType = e.type.toLowerCase().includes(q)
        const matchAgent = e.agentInstanceId?.toLowerCase().includes(q)
        const matchPayload = JSON.stringify(e.payload).toLowerCase().includes(q)
        return matchType || matchAgent || matchPayload
      })
    }
    return list
  })

  // Actions
  async function fetchTasks(query: TaskQuery = {}) {
    isLoading.value = true
    error.value = null

    try {
      const pageResult = await gateway.listTasks(query)
      tasks.value = pageResult.items
      totalTasks.value = pageResult.total
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : '获取任务列表失败'
      appStore.addLog({
        level: 'error',
        source: 'TaskStore',
        message: `获取任务列表失败: ${error.value}`,
      })
    } finally {
      isLoading.value = false
    }
  }

  async function fetchTask(id: string) {
    isLoading.value = true
    error.value = null
    actionError.value = null
    orphanProcessIds.value = []

    try {
      const detail = await gateway.getTask(id)
      currentTask.value = detail

      // Initialize events from detail snapshot
      eventSeenIds.value.clear()
      events.value = []
      if (detail.events && detail.events.length > 0) {
        for (const evt of detail.events) {
          if (!eventSeenIds.value.has(evt.eventId)) {
            eventSeenIds.value.add(evt.eventId)
            events.value.push(evt)
            if (evt.seq > lastEventSeq.value) {
              lastEventSeq.value = evt.seq
            }
          }
        }
      }

      if (detail.lastEventSeq && detail.lastEventSeq > lastEventSeq.value) {
        lastEventSeq.value = detail.lastEventSeq
      }
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : `获取任务 ${id} 详情失败`
      appStore.addLog({
        level: 'error',
        source: 'TaskStore',
        message: `获取任务 ${id} 详情失败: ${error.value}`,
      })
    } finally {
      isLoading.value = false
    }
  }

  async function createTask(input: CreateTaskInput): Promise<TaskDetailView> {
    if (!appStore.isTaskCreationAllowed) {
      const reason = appStore.hubGateReason || 'Local Hub 当前不允许新建任务'
      throw new Error(reason)
    }

    isActionLoading.value = true
    actionError.value = null

    try {
      const newTask = await gateway.createTask(input)
      tasks.value.unshift(newTask)
      totalTasks.value++
      currentTask.value = newTask
      appStore.addLog({
        level: 'info',
        source: 'TaskStore',
        message: `创建任务成功: ${newTask.id} (${newTask.objective})`,
      })
      return newTask
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '创建任务失败'
      actionError.value = msg
      appStore.addLog({
        level: 'error',
        source: 'TaskStore',
        message: `创建任务失败: ${msg}`,
      })
      throw err
    } finally {
      isActionLoading.value = false
    }
  }

  async function controlTask(id: string, action: TaskActionInput): Promise<TaskDetailView> {
    // Trap 1 validation: append_instruction when not idle
    if (action.action === 'append_instruction' && !canAppendInstruction.value) {
      const msg = '节点正在运行中，待节点空闲后方可追加指令'
      actionError.value = msg
      throw new Error(msg)
    }

    isActionLoading.value = true
    actionError.value = null
    orphanProcessIds.value = []

    try {
      const updated = await gateway.controlTask(id, action)
      currentTask.value = updated

      const inList = tasks.value.find((t) => t.id === id)
      if (inList) {
        inList.status = updated.status
        inList.updatedAt = updated.updatedAt
      }

      appStore.addLog({
        level: 'info',
        source: 'TaskStore',
        message: `执行任务操作 ${action.action} 成功: ${id}`,
      })
      return updated
    } catch (err: unknown) {
      let msg = err instanceof Error ? err.message : `操作 ${action.action} 失败`

      // Trap 2: Handle cancel refusal (TASK_NOT_CANCELLABLE)
      if (err instanceof HubApiError && err.code === 'TASK_NOT_CANCELLABLE') {
        const detailOrphans = (err.detail?.orphanProcessIds as number[]) || []
        orphanProcessIds.value = detailOrphans
        msg = `取消请求已被底层 Adapter 拒绝：Agent 不支持中止。孤儿进程 PID: ${
          detailOrphans.length > 0 ? detailOrphans.join(', ') : '未知'
        }`
      }

      actionError.value = msg
      appStore.addLog({
        level: 'error',
        source: 'TaskStore',
        message: `任务操作失败: ${msg}`,
      })
      throw err
    } finally {
      isActionLoading.value = false
    }
  }

  function handleHubEvent(event: HubEvent) {
    // Idempotent duplicate check
    if (eventSeenIds.value.has(event.eventId)) {
      return
    }
    eventSeenIds.value.add(event.eventId)

    if (event.seq > lastEventSeq.value) {
      lastEventSeq.value = event.seq
    }

    // Append to event list
    events.value.push(event)

    // Update current task if matches
    if (currentTask.value && currentTask.value.id === event.taskId) {
      switch (event.type) {
        case 'task.status_changed': {
          const payload = event.payload as TaskStatusChangedPayload
          currentTask.value.status = payload.to
          break
        }
        case 'task.completed': {
          currentTask.value.status = 'succeeded'
          break
        }
        case 'task.failed': {
          const payload = event.payload as TaskStatusChangedPayload
          currentTask.value.status = 'failed'
          if (payload.reason) currentTask.value.failureReason = payload.reason
          break
        }
        case 'node.resolved': {
          const payload = event.payload as NodeResolvedPayload
          const node = currentTask.value.nodes.find((n) => n.id === event.nodeId || n.roleId === payload.roleId)
          if (node) {
            node.resolvedAgentId = payload.resolvedAgentId
            if (payload.resolvedAgentName) node.resolvedAgentName = payload.resolvedAgentName
            node.resolveSource = payload.resolveSource
            node.isFallback = payload.isFallback
            node.fallbackReason = payload.fallbackReason
            if (node.status === 'resolving' || node.status === 'pending') {
              node.status = 'pending'
            }
          }
          break
        }
        case 'agent.started': {
          const payload = event.payload as AgentStartedPayload
          const node = currentTask.value.nodes.find((n) => n.id === event.nodeId)
          if (node) {
            node.status = 'running'
            node.startedAt = event.occurredAt
            node.sessionId = payload.sessionId
            node.externalSessionId = payload.externalSessionId
          }
          currentTask.value.status = 'running'
          break
        }
        case 'agent.progress': {
          const payload = event.payload as AgentProgressPayload
          const node = currentTask.value.nodes.find((n) => n.id === event.nodeId)
          if (node && payload.message) {
            node.outputSummary = payload.message
          }
          break
        }
        case 'agent.tool_call': {
          // Logged in event list, no direct node status change
          break
        }
        case 'agent.completed': {
          const payload = event.payload as AgentCompletedPayload
          const node = currentTask.value.nodes.find((n) => n.id === event.nodeId)
          if (node) {
            node.status = 'succeeded'
            node.completedAt = event.occurredAt
            if (payload.result?.summary) node.outputSummary = payload.result.summary
            if (payload.result?.changedFiles) {
              node.changedFiles = payload.result.changedFiles.map((f) => f.path)
            }
          }
          break
        }
        case 'agent.failed': {
          const payload = event.payload as AgentFailedPayload
          const node = currentTask.value.nodes.find((n) => n.id === event.nodeId)
          if (node) {
            node.status = 'failed'
            node.completedAt = event.occurredAt
            node.error = payload.message
          }
          currentTask.value.status = 'failed'
          break
        }
        case 'task.path_violation': {
          const payload = event.payload as PathViolationPayload
          const node = currentTask.value.nodes.find((n) => n.id === event.nodeId)
          if (node) {
            node.violationPaths = payload.violationPaths
            node.status = 'failed'
          }
          currentTask.value.status = 'failed'
          currentTask.value.failureReason = `越界写入被拦截: ${payload.violationPaths.join(', ')}`
          break
        }
        case 'approval.required': {
          const payload = event.payload as ApprovalRequiredPayload
          const node = currentTask.value.nodes.find((n) => n.id === event.nodeId)
          if (node) {
            node.status = 'waiting_approval'
          }
          currentTask.value.status = 'waiting_approval'
          currentTask.value.pendingApprovalId = payload.approvalId
          break
        }
        case 'approval.resolved': {
          const payload = event.payload as ApprovalResolvedPayload
          const node = currentTask.value.nodes.find((n) => n.id === event.nodeId)
          if (payload.decision === 'approve') {
            if (node) node.status = 'running'
            currentTask.value.status = 'running'
            currentTask.value.pendingApprovalId = undefined
          } else {
            if (node) node.status = 'failed'
            currentTask.value.status = 'failed'
            currentTask.value.pendingApprovalId = undefined
          }
          break
        }
      }
    }

    // Also update matching item in tasks list
    const inList = tasks.value.find((t) => t.id === event.taskId)
    if (inList) {
      if (event.type === 'task.status_changed') {
        inList.status = (event.payload as TaskStatusChangedPayload).to
      } else if (event.type === 'task.completed') {
        inList.status = 'succeeded'
      } else if (event.type === 'task.failed') {
        inList.status = 'failed'
      } else if (event.type === 'approval.required') {
        inList.status = 'waiting_approval'
        inList.pendingApprovalId = (event.payload as ApprovalRequiredPayload).approvalId
      } else if (event.type === 'approval.resolved') {
        inList.pendingApprovalId = undefined
      }
    }
  }

  function subscribeTaskEvents(taskId?: string) {
    if (activeSubscription) {
      activeSubscription.unsubscribe()
      activeSubscription = null
    }

    isSubscribed.value = true
    activeSubscription = gateway.subscribeEvents(
      { afterSeq: lastEventSeq.value, taskId },
      (event) => {
        handleHubEvent(event)
      },
      (err) => {
        console.error('[TaskStore] Event subscription error', err)
      }
    )

    return activeSubscription
  }

  function unsubscribeTaskEvents() {
    if (activeSubscription) {
      activeSubscription.unsubscribe()
      activeSubscription = null
    }
    isSubscribed.value = false
  }

  return {
    // State
    tasks,
    totalTasks,
    currentTask,
    isLoading,
    isActionLoading,
    error,
    actionError,
    orphanProcessIds,
    filterStatus,
    filterWorkspaceId,
    filterSearch,
    events,
    lastEventSeq,
    isSubscribed,
    eventFilterType,
    eventFilterNodeId,
    eventSearch,

    // Computed
    filteredTasks,
    runningTasks,
    waitingApprovalTasks,
    currentNodes,
    currentArtifacts,
    hasRunningNode,
    canPause,
    canResume,
    canCancel,
    canRetry,
    canAppendInstruction,
    filteredEvents,

    // Actions
    fetchTasks,
    fetchTask,
    createTask,
    controlTask,
    handleHubEvent,
    subscribeTaskEvents,
    unsubscribeTaskEvents,
  }
})
