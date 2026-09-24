import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  LocalConversationView,
  CreateLocalConversationInput,
  LocalMessageView,
  LocalRunView,
  TaskActionInput,
  WorkspaceView,
  LocalSceneView,
  ApprovalView,
  ApprovalResponseInput,
  LocalSceneId,
} from '@hqagent/protocol'
import { getLocalChatGateway, HubApiError } from '@/shared/api'
import { pendingOperation, completeOperation, definiteRejection } from '@/shared/api/local-pending-operation'

export const useChatStore = defineStore('chat', () => {
  // Conversations
  const conversations = ref<LocalConversationView[]>([])
  const activeConversationId = ref<string | null>(null)
  const searchQuery = ref('')
  const isLoadingConversations = ref(false)

  // Messages & Runs
  const messages = ref<LocalMessageView[]>([])
  const isLoadingMessages = ref(false)
  const activeRun = ref<LocalRunView | null>(null)
  const conversationRuns = ref<LocalRunView[]>([])
  const isLoadingRun = ref(false)

  // Workspaces & Scenes
  const workspaces = ref<WorkspaceView[]>([])
  const scenes = ref<LocalSceneView[]>([])

  // Sending state
  const isSending = ref(false)
  const sessionMode = ref<'new' | 'continue'>('new')
  const queuedMessages = ref<{ id: string; text: string }[]>([])
  const sendError = ref<string | null>(null)
  const resumptionError = ref<string | null>(null)
  const loadError = ref<string | null>(null)
  let viewGeneration = 0
  let pinnedRunId: string | null = null

  // Action controls
  const isActionLoading = ref(false)
  const actionError = ref<string | null>(null)

  // Approvals
  const approvals = ref<ApprovalView[]>([])

  // Events & Polling
  const lastEventSeq = ref(0)
  let pollingTimer: ReturnType<typeof setTimeout> | null = null
  const isPolling = ref(false)

  // Computed
  const activeConversation = computed(() =>
    conversations.value.find((c) => c.id === activeConversationId.value) || null
  )

  const filteredConversations = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return conversations.value
    return conversations.value.filter(
      (c) =>
        c.title.toLowerCase().includes(q) ||
        c.sceneId.toLowerCase().includes(q) ||
        (workspaces.value.find((w) => w.id === c.workspaceId)?.name || '')
          .toLowerCase()
          .includes(q)
    )
  })

  const pendingApproval = computed(() => {
    if (!activeRun.value?.taskId) return null
    return (
      approvals.value.find(
        (a) => a.taskId === activeRun.value?.taskId && a.status === 'pending'
      ) || null
    )
  })

  const isCurrentRunActive = computed(() => {
    const st = activeRun.value?.status
    return st === 'running' || st === 'queued' || st === 'waiting_approval'
  })

  // Initial load
  async function init(): Promise<void> {
    const generation = viewGeneration
    loadError.value = null
    const gateway = getLocalChatGateway()
    try {
      const [wsRes, scenesRes] = await Promise.all([
        gateway.listLocalWorkspaces(),
        gateway.listLocalScenes(),
      ])
      if (generation !== viewGeneration) return
      workspaces.value = wsRes
      scenes.value = scenesRes
    } catch (error) {
      loadError.value = error instanceof Error ? error.message : '加载项目与场景失败'
    }
    await fetchConversations()
  }

  async function fetchConversations(): Promise<void> {
    const generation = viewGeneration
    isLoadingConversations.value = true
    try {
      const gateway = getLocalChatGateway()
      const items = await gateway.listLocalConversations()
      if (generation !== viewGeneration) return
      conversations.value = items
      if (!activeConversationId.value && conversations.value.length > 0) {
        await selectConversation(conversations.value[0].id)
      }
    } catch (error) {
      loadError.value = error instanceof Error ? error.message : '加载对话失败'
    } finally {
      isLoadingConversations.value = false
    }
  }

  async function selectConversation(conversationId: string): Promise<void> {
    if (activeConversationId.value === conversationId && messages.value.length > 0) {
      return
    }
    activeConversationId.value = conversationId
    viewGeneration++
    pinnedRunId = null
    messages.value = []
    conversationRuns.value = []
    activeRun.value = null
    loadError.value = null
    sendError.value = null
    resumptionError.value = null
    actionError.value = null

    await Promise.all([
      fetchMessages(conversationId),
      fetchConversationRuns(conversationId),
      fetchApprovals(),
    ])

    // If conversation already has completed messages, default next message to continue
    if (messages.value.length > 0) {
      sessionMode.value = 'continue'
    } else {
      sessionMode.value = 'new'
    }
  }

  async function fetchMessages(conversationId: string): Promise<void> {
    const generation = viewGeneration
    isLoadingMessages.value = true
    try {
      const gateway = getLocalChatGateway()
      let after = messages.value.filter(m => m.conversationId === conversationId).reduce((n, m) => Math.max(n, m.sequence), 0)
      for (let pageIndex = 0; pageIndex < 50; pageIndex++) {
        const page = await gateway.listLocalMessages(conversationId, after, 200)
        if (generation !== viewGeneration || activeConversationId.value !== conversationId) return
        const merged = new Map(messages.value.map(m => [m.id, m]))
        for (const message of page) merged.set(message.id, message)
        messages.value = [...merged.values()].sort((a, b) => a.sequence - b.sequence)
        const next = page.reduce((n, m) => Math.max(n, m.sequence), after)
        if (page.length < 200 || next <= after) break
        after = next
      }
    } catch (error) {
      if (generation === viewGeneration) loadError.value = error instanceof Error ? error.message : '读取消息失败'
    } finally {
      isLoadingMessages.value = false
    }
  }

  async function fetchConversationRuns(conversationId: string): Promise<void> {
    const generation = viewGeneration
    isLoadingRun.value = true
    try {
      const gateway = getLocalChatGateway()
      const runs = await gateway.listConversationRuns(conversationId)
      if (generation !== viewGeneration || activeConversationId.value !== conversationId) return
      conversationRuns.value = runs
      const live = runs.find(r => r.status === 'running' || r.status === 'waiting_approval' || r.status === 'paused')
      const targetRunId = pinnedRunId || live?.id || runs[0]?.id
      if (targetRunId) {
        const detail = await gateway.getLocalRun(targetRunId)
        if (generation !== viewGeneration || activeConversationId.value !== conversationId) return
        activeRun.value = detail
        if (detail.status === 'failed' && detail.error && /会话|上下文/.test(detail.error)) {
          resumptionError.value = detail.error
        }
      } else {
        activeRun.value = null
      }
    } catch (error) {
      if (generation === viewGeneration) loadError.value = error instanceof Error ? error.message : '读取执行状态失败'
    } finally {
      isLoadingRun.value = false
    }
  }

  async function fetchApprovals(): Promise<void> {
    const generation = viewGeneration
    try {
      const gateway = getLocalChatGateway()
      const items = await gateway.listLocalApprovals()
      if (generation === viewGeneration) approvals.value = items
    } catch {
      // ignore
    }
  }

  async function createConversation(
    title: string,
    workspaceId: string,
    sceneId: LocalSceneId
  ): Promise<LocalConversationView> {
    const gateway = getLocalChatGateway()
    const input: CreateLocalConversationInput = {
      title: title.trim(),
      workspaceId,
      sceneId,
    }
    const identity = `create:${JSON.stringify(input)}`
    const operation = pendingOperation(identity, input)
    try {
      const created = await gateway.createLocalConversation(operation.payload, operation.id)
      completeOperation(identity)
      conversations.value = [created, ...conversations.value.filter(c => c.id !== created.id)]
      await selectConversation(created.id)
      return created
    } catch (error) {
      if (definiteRejection(error)) completeOperation(identity)
      throw error
    }
  }

  async function registerWorkspace(path: string): Promise<WorkspaceView> {
    const workspace = await getLocalChatGateway().addLocalWorkspace({ path: path.trim() })
    workspaces.value = [workspace, ...workspaces.value.filter(w => w.id !== workspace.id)]
    return workspace
  }

  async function pickWorkspaceDirectory(): Promise<string | null> {
    const result = await getLocalChatGateway().pickLocalDirectory({})
    return result.cancelled ? null : result.selectedPath || null
  }

  async function sendMessage(
    text: string,
    modeOverride?: 'new' | 'continue'
  ): Promise<void> {
    const convId = activeConversationId.value
    if (!convId || !text.trim() || isSending.value) return

    const mode = modeOverride || sessionMode.value
    const identity = `send:${convId}:${text.trim()}`
    const operation = pendingOperation(identity, { text: text.trim(), sessionMode: mode })
    const clientMessageId = operation.id
    const idempotencyKey = operation.id

    // If currently running, queue it
    if (isCurrentRunActive.value) {
      queuedMessages.value.push({ id: clientMessageId, text: text.trim() })
    }

    isSending.value = true
    sendError.value = null
    resumptionError.value = null

    try {
      const gateway = getLocalChatGateway()
      await gateway.sendLocalMessage(
        convId,
        {
          clientMessageId,
          ...operation.payload,
        },
        idempotencyKey
      )
      completeOperation(identity)
      if (activeConversationId.value === convId) sessionMode.value = 'continue'
      pinnedRunId = null

      // Refresh messages and runs
      await Promise.all([fetchMessages(convId), fetchConversationRuns(convId)])

      // If was queued, remove it
      queuedMessages.value = queuedMessages.value.filter((q) => q.id !== clientMessageId)

      // Start event polling
      startPolling()
      return
    } catch (err: unknown) {
      if (definiteRejection(err)) completeOperation(identity)
      queuedMessages.value = queuedMessages.value.filter((q) => q.id !== clientMessageId)
      if (err instanceof HubApiError) {
        if (err.code === 'SESSION_NOT_RESUMABLE') {
          resumptionError.value =
            err.message || '该会话无法继续上下文，请选择「新一轮上下文」发送'
        } else {
          sendError.value = err.message
        }
      } else {
        sendError.value = err instanceof Error ? err.message : '发送消息失败'
      }
      throw err
    } finally {
      isSending.value = false
    }
  }

  async function controlRun(
    runId: string,
    action: TaskActionInput['action'],
    instruction?: string
  ): Promise<void> {
    isActionLoading.value = true
    actionError.value = null
    const identity = `control:${runId}:${action}:${instruction || ''}`
    const operation = pendingOperation(identity, { action, instruction })
    const idempotencyKey = operation.id
    try {
      const gateway = getLocalChatGateway()
      const updatedRun = await gateway.controlLocalRun(
        runId,
        operation.payload,
        idempotencyKey
      )
      completeOperation(identity)
      activeRun.value = updatedRun
      pinnedRunId = updatedRun.id
      if (activeConversationId.value) {
        await Promise.all([
          fetchMessages(activeConversationId.value),
          fetchConversationRuns(activeConversationId.value),
        ])
      }
    } catch (err: unknown) {
      if (definiteRejection(err)) completeOperation(identity)
      actionError.value = err instanceof Error ? err.message : '执行操作失败'
      throw err
    } finally {
      isActionLoading.value = false
    }
  }

  async function respondApproval(
    approvalId: string,
    input: ApprovalResponseInput
  ): Promise<void> {
    const identity = `approval:${approvalId}:${input.decision}`
    const operation = pendingOperation(identity, input)
    try {
      const gateway = getLocalChatGateway()
      await gateway.decideLocalApproval(approvalId, operation.payload, operation.id)
      completeOperation(identity)
      await fetchApprovals()
      if (activeConversationId.value) {
        await Promise.all([
          fetchMessages(activeConversationId.value),
          fetchConversationRuns(activeConversationId.value),
        ])
      }
    } catch (err: unknown) {
      if (definiteRejection(err)) completeOperation(identity)
      actionError.value = err instanceof Error ? err.message : '审批提交失败'
      throw err
    }
  }

  // Event Polling Loop
  function startPolling(): void {
    if (isPolling.value) return
    isPolling.value = true
    scheduleNextPoll()
  }

  function stopPolling(): void {
    isPolling.value = false
    if (pollingTimer) {
      clearTimeout(pollingTimer)
      pollingTimer = null
    }
  }

  async function pollEvents(): Promise<void> {
    if (!isPolling.value) return
    const generation = viewGeneration
    try {
      const gateway = getLocalChatGateway()
      const page = await gateway.listLocalEvents(lastEventSeq.value, 100)
      if (generation !== viewGeneration) return
      loadError.value = null
      lastEventSeq.value = page.nextSeq
      // Replies may commit after the last task event. Refresh even on an empty page.
      if (activeConversationId.value) {
        await Promise.all([
          fetchMessages(activeConversationId.value),
          fetchConversationRuns(activeConversationId.value),
          fetchApprovals(),
        ])
      }
    } catch (err: unknown) {
      if (err instanceof HubApiError && (err.code === 'EVENT_CURSOR_EXPIRED' || err.status === 410)) {
        const latest = err.detail?.latestSeq
        if (typeof latest !== 'number' || latest < 0) {
          loadError.value = '事件游标已失效，请重新连接本机服务'
          stopPolling()
          return
        }
        lastEventSeq.value = latest
        if (activeConversationId.value) {
          await Promise.all([
            fetchMessages(activeConversationId.value),
            fetchConversationRuns(activeConversationId.value),
          ])
        }
      } else {
        loadError.value = err instanceof Error ? err.message : '服务连接中断，正在重连'
      }
    } finally {
      if (generation === viewGeneration) scheduleNextPoll()
    }
  }

  function scheduleNextPoll(): void {
    if (!isPolling.value) return
    if (pollingTimer) clearTimeout(pollingTimer)
    // Busy interval: 1000ms if run is active; Idle interval: 4000ms
    const interval = isCurrentRunActive.value ? 1000 : 4000
    pollingTimer = setTimeout(() => {
      pollEvents()
    }, interval)
  }

  function reset(): void {
    stopPolling()
    viewGeneration++
    pinnedRunId = null
    conversations.value = []
    activeConversationId.value = null
    messages.value = []
    conversationRuns.value = []
    activeRun.value = null
    workspaces.value = []
    scenes.value = []
    approvals.value = []
    queuedMessages.value = []
    lastEventSeq.value = 0
    loadError.value = null
    sendError.value = null
    actionError.value = null
    resumptionError.value = null
    sessionMode.value = 'new'
  }

  return {
    conversations,
    activeConversationId,
    activeConversation,
    searchQuery,
    filteredConversations,
    messages,
    isLoadingMessages,
    activeRun,
    conversationRuns,
    isLoadingRun,
    workspaces,
    scenes,
    isSending,
    sessionMode,
    queuedMessages,
    sendError,
    resumptionError,
    loadError,
    isActionLoading,
    actionError,
    approvals,
    pendingApproval,
    isCurrentRunActive,
    init,
    fetchConversations,
    selectConversation,
    fetchMessages,
    fetchConversationRuns,
    fetchApprovals,
    createConversation,
    registerWorkspace,
    pickWorkspaceDirectory,
    sendMessage,
    controlRun,
    respondApproval,
    startPolling,
    stopPolling,
    reset,
    pollEvents,
    lastEventSeq,
  }
})
