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
    const gateway = getLocalChatGateway()
    try {
      const [wsRes, scenesRes] = await Promise.all([
        gateway.listLocalWorkspaces(),
        gateway.listLocalScenes(),
      ])
      workspaces.value = wsRes
      scenes.value = scenesRes
    } catch {
      // Handled in individual views
    }
    await fetchConversations()
  }

  async function fetchConversations(): Promise<void> {
    isLoadingConversations.value = true
    try {
      const gateway = getLocalChatGateway()
      conversations.value = await gateway.listLocalConversations()
      if (!activeConversationId.value && conversations.value.length > 0) {
        await selectConversation(conversations.value[0].id)
      }
    } catch {
      // ignore
    } finally {
      isLoadingConversations.value = false
    }
  }

  async function selectConversation(conversationId: string): Promise<void> {
    if (activeConversationId.value === conversationId && messages.value.length > 0) {
      return
    }
    activeConversationId.value = conversationId
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
    isLoadingMessages.value = true
    try {
      const gateway = getLocalChatGateway()
      messages.value = await gateway.listLocalMessages(conversationId, 0, 200)
    } catch {
      // ignore
    } finally {
      isLoadingMessages.value = false
    }
  }

  async function fetchConversationRuns(conversationId: string): Promise<void> {
    isLoadingRun.value = true
    try {
      const gateway = getLocalChatGateway()
      const runs = await gateway.listConversationRuns(conversationId)
      conversationRuns.value = runs
      const conv = conversations.value.find((c) => c.id === conversationId)
      const targetRunId = conv?.activeRunId || conv?.lastRunId || runs[0]?.id
      if (targetRunId) {
        activeRun.value = await gateway.getLocalRun(targetRunId)
      } else {
        activeRun.value = null
      }
    } catch {
      // ignore
    } finally {
      isLoadingRun.value = false
    }
  }

  async function fetchApprovals(): Promise<void> {
    try {
      const gateway = getLocalChatGateway()
      approvals.value = await gateway.listLocalApprovals()
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
    const idempotencyKey = `create_conv_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
    const created = await gateway.createLocalConversation(input, idempotencyKey)
    conversations.value.unshift(created)
    await selectConversation(created.id)
    return created
  }

  async function sendMessage(
    text: string,
    modeOverride?: 'new' | 'continue'
  ): Promise<void> {
    const convId = activeConversationId.value
    if (!convId || !text.trim() || isSending.value) return

    const mode = modeOverride || sessionMode.value
    const clientMessageId = `cmsg_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
    const idempotencyKey = `idemp_msg_${clientMessageId}`

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
          text: text.trim(),
          sessionMode: mode,
        },
        idempotencyKey
      )

      // Refresh messages and runs
      await Promise.all([fetchMessages(convId), fetchConversationRuns(convId)])

      // If was queued, remove it
      queuedMessages.value = queuedMessages.value.filter((q) => q.id !== clientMessageId)

      // Start event polling
      startPolling()
      return
    } catch (err: unknown) {
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
    const idempotencyKey = `cmd_${runId}_${action}_${Date.now()}`
    try {
      const gateway = getLocalChatGateway()
      const updatedRun = await gateway.controlLocalRun(
        runId,
        { action, instruction },
        idempotencyKey
      )
      activeRun.value = updatedRun
      if (activeConversationId.value) {
        await Promise.all([
          fetchMessages(activeConversationId.value),
          fetchConversationRuns(activeConversationId.value),
        ])
      }
    } catch (err: unknown) {
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
    try {
      const gateway = getLocalChatGateway()
      await gateway.decideLocalApproval(approvalId, input)
      await fetchApprovals()
      if (activeConversationId.value) {
        await Promise.all([
          fetchMessages(activeConversationId.value),
          fetchConversationRuns(activeConversationId.value),
        ])
      }
    } catch (err: unknown) {
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
    try {
      const gateway = getLocalChatGateway()
      const page = await gateway.listLocalEvents(lastEventSeq.value, 100)
      if (page.events.length > 0) {
        lastEventSeq.value = page.nextSeq
        // If there are task events relevant to active conversation, refresh
        if (activeConversationId.value) {
          await Promise.all([
            fetchMessages(activeConversationId.value),
            fetchConversationRuns(activeConversationId.value),
            fetchApprovals(),
          ])
        }
      }
    } catch (err: unknown) {
      if (err instanceof HubApiError && (err.code === 'EVENT_CURSOR_EXPIRED' || err.status === 410)) {
        // Reset cursor to 0 and refetch
        lastEventSeq.value = 0
        if (activeConversationId.value) {
          await Promise.all([
            fetchMessages(activeConversationId.value),
            fetchConversationRuns(activeConversationId.value),
          ])
        }
      }
    } finally {
      scheduleNextPoll()
    }
  }

  function scheduleNextPoll(): void {
    if (!isPolling.value) return
    // Busy interval: 1000ms if run is active; Idle interval: 4000ms
    const interval = isCurrentRunActive.value ? 1000 : 4000
    pollingTimer = setTimeout(() => {
      pollEvents()
    }, interval)
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
    sendMessage,
    controlRun,
    respondApproval,
    startPolling,
    stopPolling,
  }
})
