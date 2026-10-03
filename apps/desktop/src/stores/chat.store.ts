import { getRemoteErrorMessage } from '@/shared/i18n/remote-errors'
import { preflightAttachments } from '@/shared/attachments/preflight'
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  NativeContinuationConfirmationInput,
  LocalConversationView,
  CreateLocalConversationInput,
  UpdateLocalConversationInput,
  LocalMessageView,
  LocalRunView,
  TaskActionInput,
  WorkspaceView,
  LocalSceneView,
  ApprovalView,
  ApprovalResponseInput,
  LocalSceneId,
  HubEvent,
  TaskStatus,
} from '@hqagent/protocol'
import { getLocalChatGateway, HubApiError } from '@/shared/api'
import { pendingOperation, completeOperation, definiteRejection, clearVolatileOperations, forgetConversationOperations } from '@/shared/api/local-pending-operation'

export interface ActivityItem {
  id: string
  type: 'file' | 'command' | 'thought' | 'tool' | 'progress'
  verb: string
  target: string
  fileName?: string
  dirPath?: string
  rawArgs?: string
  detail?: string
  status: 'running' | 'done' | 'failed'
  durationMs?: number
  timestamp: string
}

export const useChatStore = defineStore('chat', () => {
  // Conversations
  const conversations = ref<LocalConversationView[]>([])
  const activeConversationId = ref<string | null>(null)
  const searchQuery = ref('')
  const showArchived = ref(false)
  const collapsedWorkspaceIds = ref<Record<string, boolean>>({})
  const includeHiddenConversations = ref(false)
  const isLoadingConversations = ref(false)
  const isMetadataUpdating = ref(false)
  const metadataError = ref<string | null>(null)
  const conversationDrafts = ref<Record<string, string>>({})
  const conversationDraftRevisions = ref<Record<string, number>>({})

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
  const sendingConversationIds = ref<string[]>([])
  const isSending = computed(() => Boolean(
    activeConversationId.value
      && sendingConversationIds.value.includes(activeConversationId.value)
  ))
  const sessionMode = ref<'new' | 'continue'>('new')
  // A reset is an explicit, one-message choice within this conversation.
  // Normal replies continue; a new conversation's first message starts fresh.
  const pendingContextReset = ref(false)
  const allQueuedMessages = ref<{ id: string; conversationId: string; text: string }[]>([])
  const queuedMessages = computed(() => allQueuedMessages.value.filter(
    (message) => message.conversationId === activeConversationId.value
  ))
  const sendError = ref<string | null>(null)
  const resumptionError = ref<string | null>(null)
  const sendErrorsByConversation = ref<Record<string, string>>({})
  const resumptionErrorsByConversation = ref<Record<string, string>>({})
  const loadError = ref<string | null>(null)
  const deletedConversationIds = new Set<string>()
  let viewGeneration = 0
  let pinnedRunId: string | null = null

  // Action controls
  const isActionLoading = ref(false)
  const actionError = ref<string | null>(null)

  // Approvals
  const approvals = ref<ApprovalView[]>([])

  // Process activities
  const activitiesByTaskId = ref<Record<string, ActivityItem[]>>({})
  const activitiesByRunId = ref<Record<string, ActivityItem[]>>({})

  // Events & Polling
  const lastEventSeq = ref(0)
  let pollingTimer: ReturnType<typeof setTimeout> | null = null
  const isPolling = ref(false)
  let pollingEpoch = 0
  let activePollEpoch: number | null = null

  // Computed
  const activeConversation = computed(() =>
    conversations.value.find((c) => c.id === activeConversationId.value) || null
  )

  const filteredConversations = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    return conversations.value.filter(
      (c) => {
        if (!includeHiddenConversations.value && c.visibility === 'mobile_only') return false
        if (Boolean(c.archived) !== showArchived.value) return false
        if (!q) return true
        const workspace = workspaces.value.find((w) => w.id === c.workspaceId)
        return c.title.toLowerCase().includes(q)
          || (workspace?.name || '').toLowerCase().includes(q)
          || (workspace?.path || '').toLowerCase().includes(q)
      }
    )
  })

  const groupedConversations = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    return workspaces.value
      .map((workspace) => {
        const workspaceMatches = !q
          || workspace.name.toLowerCase().includes(q)
          || workspace.path.toLowerCase().includes(q)
        const items = conversations.value.filter((conversation) => {
          if (conversation.workspaceId !== workspace.id) return false
          if (!includeHiddenConversations.value && conversation.visibility === 'mobile_only') return false
          if (Boolean(conversation.archived) !== showArchived.value) return false
          return workspaceMatches || conversation.title.toLowerCase().includes(q)
        })
        return { workspace, conversations: items, workspaceMatches }
      })
      .filter((group) => !q || group.workspaceMatches || group.conversations.length > 0)
  })

  const isActiveConversationArchived = computed(() => Boolean(activeConversation.value?.archived))
  const isRemoteConversation = computed(() => activeConversation.value?.authority === 'remote')
  const isConversationBusy = computed(() => Boolean(activeConversation.value?.busy))

  const nonArchivableStatuses: TaskStatus[] = ['queued', 'running', 'waiting_approval', 'paused']

  function canArchiveConversation(conversation: LocalConversationView): boolean {
    const status = conversation.lastRunStatus
    return !conversation.archived
      && !(status && nonArchivableStatuses.includes(status))
      && !conversation.activeRunId
      && !conversation.busy
  }

  function getConversationDraft(conversationId: string): string {
    return conversationDrafts.value[conversationId] || ''
  }

  function setConversationDraft(conversationId: string, value: string): void {
    conversationDrafts.value = { ...conversationDrafts.value, [conversationId]: value }
    conversationDraftRevisions.value = {
      ...conversationDraftRevisions.value,
      [conversationId]: (conversationDraftRevisions.value[conversationId] || 0) + 1,
    }
  }

  function getConversationDraftRevision(conversationId: string): number {
    return conversationDraftRevisions.value[conversationId] || 0
  }

  function toggleWorkspaceCollapsed(workspaceId: string): void {
    collapsedWorkspaceIds.value = {
      ...collapsedWorkspaceIds.value,
      [workspaceId]: !collapsedWorkspaceIds.value[workspaceId],
    }
  }

  function removeQueuedMessage(messageId: string): void {
    allQueuedMessages.value = allQueuedMessages.value.filter((message) => message.id !== messageId)
  }

  function clearSendError(): void {
    if (activeConversationId.value) {
      const remaining = { ...sendErrorsByConversation.value }
      delete remaining[activeConversationId.value]
      sendErrorsByConversation.value = remaining
    }
    sendError.value = null
  }

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

  const canResetContext = computed(() => Boolean(activeConversationId.value)
    && activeConversation.value?.conversationKind !== 'native'
    && !isActiveConversationArchived.value
    && !isSending.value && !isActionLoading.value
    && !isLoadingMessages.value && !isLoadingRun.value
    && !isCurrentRunActive.value && queuedMessages.value.length === 0
    && !conversationRuns.value.some(run => ['running', 'queued', 'waiting_approval', 'paused'].includes(run.status)))

  const effectiveSessionMode = computed(() => activeConversation.value?.conversationKind === 'native' ? 'continue' : sessionMode.value)

  function requestContextReset(): boolean {
    if (!canResetContext.value) return false
    pendingContextReset.value = true
    sessionMode.value = 'new'
    resumptionError.value = null
    if (activeConversationId.value) {
      const remaining = { ...resumptionErrorsByConversation.value }
      delete remaining[activeConversationId.value]
      resumptionErrorsByConversation.value = remaining
    }
    return true
  }

  function cancelContextReset(): void {
    pendingContextReset.value = false
    sessionMode.value = messages.value.length > 0 || conversationRuns.value.length > 0 ? 'continue' : 'new'
    const detail = activeRun.value
    if (sessionMode.value === 'continue' && detail?.status === 'failed' && detail.error && /会话|上下文/.test(detail.error)) {
      resumptionError.value = detail.error
      if (activeConversationId.value) {
        resumptionErrorsByConversation.value = {
          ...resumptionErrorsByConversation.value,
          [activeConversationId.value]: detail.error,
        }
      }
    }
  }

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
      const items = await gateway.listLocalConversations({
        includeHidden: includeHiddenConversations.value,
      })
      if (generation !== viewGeneration) return
      conversations.value = items.filter(conversation => !deletedConversationIds.has(conversation.id)).map((conversation) => {
        const normalized = {
          ...conversation,
          version: conversation.version ?? 1,
          archived: conversation.archived ?? false,
        }
        const current = conversations.value.find((item) => item.id === normalized.id)
        if ((current?.version ?? 1) > normalized.version) {
          return {
            ...normalized,
            title: current!.title,
            archived: current!.archived ?? false,
            version: current!.version ?? 1,
            updatedAt: current!.updatedAt,
          }
        }
        return normalized
      })
      if (!activeConversationId.value && conversations.value.length > 0) {
        const firstVisible = conversations.value.find((conversation) => !conversation.archived)
          || conversations.value[0]
        isLoadingConversations.value = false
        await selectConversation(firstVisible.id)
      }
    } catch (error) {
      loadError.value = error instanceof Error ? error.message : '加载对话失败'
    } finally {
      if (generation === viewGeneration) isLoadingConversations.value = false
    }
  }

  async function selectConversation(conversationId: string): Promise<void> {
    if (activeConversationId.value === conversationId && messages.value.length > 0) {
      return
    }
    activeConversationId.value = conversationId
    viewGeneration++
    const generation = viewGeneration
    pinnedRunId = null
    messages.value = []
    conversationRuns.value = []
    activeRun.value = null
    pendingContextReset.value = false
    sessionMode.value = 'new'
    loadError.value = null
    sendError.value = sendErrorsByConversation.value[conversationId] || null
    resumptionError.value = resumptionErrorsByConversation.value[conversationId] || null
    actionError.value = null

    await Promise.all([
      fetchMessages(conversationId),
      fetchConversationRuns(conversationId),
      fetchApprovals(),
      backfillEvents(),
    ])

    if (generation !== viewGeneration) return
    if (isPolling.value) scheduleNextPoll(0)

    // If conversation already has completed messages, default next message to continue
    if (messages.value.length > 0 || conversationRuns.value.length > 0) {
      sessionMode.value = 'continue'
    } else {
      sessionMode.value = 'new'
    }
  }

  async function fetchMessages(conversationId: string): Promise<void> {
    if (activeConversationId.value !== conversationId) return
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
      if (generation === viewGeneration && activeConversationId.value === conversationId) {
        isLoadingMessages.value = false
      }
    }
  }

  async function fetchConversationRuns(conversationId: string): Promise<void> {
    if (activeConversationId.value !== conversationId) return
    const generation = viewGeneration
    isLoadingRun.value = true
    try {
      const gateway = getLocalChatGateway()
      const runs = await gateway.listConversationRuns(conversationId)
      if (generation !== viewGeneration || activeConversationId.value !== conversationId) return
      conversationRuns.value = runs
      const live = runs.find(r => r.status === 'queued' || r.status === 'running' || r.status === 'waiting_approval' || r.status === 'paused')
      const conversation = conversations.value.find(c => c.id === conversationId)
      if (conversation) {
        conversation.activeRunId = live?.id
        conversation.lastRunId = runs[0]?.id
        conversation.lastRunStatus = runs[0]?.status
      }
      const targetRunId = pinnedRunId || live?.id || runs[0]?.id
      if (targetRunId) {
        const detail = await gateway.getLocalRun(targetRunId)
        if (generation !== viewGeneration || activeConversationId.value !== conversationId) return
        activeRun.value = detail
        // Current task progress must not wait behind unrelated historical pages.
        for (const event of detail.task?.events || []) ingestEvent(event)
        if (sessionMode.value === 'continue' && detail.status === 'failed' && detail.error && /会话|上下文/.test(detail.error)) {
          resumptionErrorsByConversation.value = {
            ...resumptionErrorsByConversation.value,
            [conversationId]: detail.error,
          }
          resumptionError.value = detail.error
        }
      } else {
        activeRun.value = null
      }
    } catch (error) {
      if (generation === viewGeneration) loadError.value = error instanceof Error ? error.message : '读取执行状态失败'
    } finally {
      if (generation === viewGeneration && activeConversationId.value === conversationId) {
        isLoadingRun.value = false
      }
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

  async function removeDeletedConversation(id: string): Promise<void> {
    deletedConversationIds.add(id)
    conversations.value = conversations.value.filter(conversation => conversation.id !== id)
    delete conversationDrafts.value[id]; delete conversationDraftRevisions.value[id]
    delete sendErrorsByConversation.value[id]; delete resumptionErrorsByConversation.value[id]
    allQueuedMessages.value = allQueuedMessages.value.filter(message => message.conversationId !== id)
    forgetConversationOperations(id)
    if (activeConversationId.value !== id) return
    viewGeneration++; pinnedRunId = null; activeConversationId.value = null
    messages.value = []; conversationRuns.value = []; activeRun.value = null; approvals.value = []
    activitiesByTaskId.value = {}; activitiesByRunId.value = {}; pendingContextReset.value = false
    sendError.value = null; resumptionError.value = null; loadError.value = null; actionError.value = null
    isLoadingMessages.value = false; isLoadingRun.value = false; isLoadingConversations.value = false
    const next = conversations.value.find(conversation => !conversation.archived) || conversations.value[0]
    if (next) await selectConversation(next.id)
  }
  async function openBlockingRun(conversationId: string, runId: string): Promise<void> {
    const run = await getLocalChatGateway().getLocalRun(runId)
    if (run.conversationId !== conversationId) throw new Error('运行不属于该对话')
    await selectConversation(conversationId)
    pinnedRunId = runId; activeRun.value = run
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
      const normalized = { ...created, version: created.version ?? 1, archived: created.archived ?? false }
      conversations.value = [normalized, ...conversations.value.filter(c => c.id !== created.id)]
      showArchived.value = false
      collapsedWorkspaceIds.value = { ...collapsedWorkspaceIds.value, [workspaceId]: false }
      await selectConversation(created.id)
      return normalized
    } catch (error) {
      if (definiteRejection(error)) completeOperation(identity)
      throw error
    }
  }

  async function updateConversationMetadata(
    conversationId: string,
    patch: Omit<UpdateLocalConversationInput, 'expectedVersion'>
  ): Promise<LocalConversationView> {
    const conversation = conversations.value.find((item) => item.id === conversationId)
    if (!conversation) throw new HubApiError('任务不存在', 'NOT_FOUND', 404)
    const input: UpdateLocalConversationInput = {
      expectedVersion: conversation.version ?? 1,
      ...patch,
    }
    const identity = `conversation-metadata:${conversationId}:${JSON.stringify(input)}`
    const operation = pendingOperation(identity, input, conversation.conversationKind === 'native')
    isMetadataUpdating.value = true
    metadataError.value = null
    try {
      const updated = await getLocalChatGateway().updateLocalConversation(
        conversationId,
        operation.payload,
        operation.id
      )
      completeOperation(identity)
      const normalized = { ...updated, version: updated.version ?? 1, archived: updated.archived ?? false }
      let applied: LocalConversationView = normalized
      conversations.value = conversations.value.map((item) =>
        item.id === conversationId
          ? ((item.version ?? 1) > normalized.version ? (applied = item) : normalized)
          : item
      )
      if (patch.archived !== undefined && activeConversationId.value === conversationId) {
        showArchived.value = Boolean(applied.archived)
      }
      return applied
    } catch (error) {
      if (definiteRejection(error)) completeOperation(identity)
      const isConflict = error instanceof HubApiError
        && (error.code === 'CONFLICT' || error.status === 409)
      metadataError.value = isConflict
        ? '任务信息已发生变化，已刷新列表，请确认后重试'
        : error instanceof Error ? error.message : '更新任务信息失败'
      if (isConflict) await fetchConversations()
      throw error
    } finally {
      isMetadataUpdating.value = false
    }
  }

  async function renameConversation(conversationId: string, title: string): Promise<LocalConversationView> {
    return updateConversationMetadata(conversationId, { title: title.trim() })
  }

  async function setConversationArchived(
    conversationId: string,
    archived: boolean
  ): Promise<LocalConversationView> {
    const conversation = conversations.value.find((item) => item.id === conversationId)
    if (!conversation) throw new HubApiError('任务不存在', 'NOT_FOUND', 404)
    if (archived && !canArchiveConversation(conversation)) {
      throw new HubApiError('运行、排队、等待审批或暂停中的任务不能归档', 'CONFLICT', 409)
    }
    return updateConversationMetadata(conversationId, { archived })
  }

  async function setConversationVisibility(
    conversationId: string,
    visibility: 'both' | 'pc_only' | 'mobile_only'
  ): Promise<LocalConversationView> {
    return updateConversationMetadata(conversationId, { visibility })
  }

  async function setIncludeHiddenConversations(value: boolean): Promise<void> {
    includeHiddenConversations.value = value
    await fetchConversations()
  }

  async function registerWorkspace(path: string): Promise<WorkspaceView> {
    const workspace = await getLocalChatGateway().addLocalWorkspace({ path: path.trim() })
    workspaces.value = [workspace, ...workspaces.value.filter(w => w.id !== workspace.id)]
    return workspace
  }

  async function pickWorkspaceDirectory(): Promise<string | null> {
    const gateway = getLocalChatGateway()
    if (!gateway.pickLocalDirectory) return null
    const result = await gateway.pickLocalDirectory({})
    return result.cancelled ? null : result.selectedPath || null
  }

  async function sendMessage(
    text: string,
    modeOverride?: 'new' | 'continue',
    nativeConfirmation?: NativeContinuationConfirmationInput,
    attachmentIds: string[] = []
  ): Promise<void> {
    const convId = activeConversationId.value
    if (!convId || !text.trim() || sendingConversationIds.value.includes(convId)) return
    const conversation = conversations.value.find((item) => item.id === convId)
    if (isConversationBusy.value) {
      sendError.value = '对话正在进行，结束后再继续'
      throw new HubApiError('对话正在进行，结束后再继续', 'REMOTE_CONVERSATION_BUSY', 409)
    }
    if (conversation?.archived) {
      throw new HubApiError('请先恢复已归档任务，再发送消息', 'CONFLICT', 409)
    }

    const mode = conversation?.conversationKind === 'native' ? 'continue' : modeOverride || sessionMode.value
    if (mode === 'continue' && resumptionError.value) {
      throw new HubApiError(resumptionError.value, 'SESSION_NOT_RESUMABLE', 409)
    }
    const wasRunActive = isCurrentRunActive.value
    const identity = `send:${convId}:${text.trim()}:${attachmentIds.join(',')}${conversation?.conversationKind === 'native' ? `:${nativeConfirmation?.sourceRevision || 'confirmed'}` : ''}`
    const operation = pendingOperation(identity, { text: text.trim(), sessionMode: mode, ...(nativeConfirmation ? { nativeConfirmation } : {}), ...(attachmentIds.length ? { attachmentIds } : {}) }, conversation?.conversationKind === 'native' || attachmentIds.length > 0)
    const clientMessageId = operation.id
    const idempotencyKey = operation.id

    // If currently running, queue it
    if (isCurrentRunActive.value) {
      allQueuedMessages.value.push({ id: clientMessageId, conversationId: convId, text: text.trim() })
    }

    sendingConversationIds.value = [...sendingConversationIds.value, convId]
    const remainingSendErrors = { ...sendErrorsByConversation.value }
    delete remainingSendErrors[convId]
    sendErrorsByConversation.value = remainingSendErrors
    if (activeConversationId.value === convId) {
      sendError.value = null
    }

    try {
      const gateway = getLocalChatGateway()
      if (attachmentIds.length) {
        await preflightAttachments(false, convId, attachmentIds)
        if (activeConversationId.value !== convId) throw new Error('对话已切换，请返回原对话重试')
      }
      const receipt = await gateway.sendLocalMessage(
        convId,
        {
          clientMessageId,
          ...operation.payload,
        },
        idempotencyKey
      )
      completeOperation(identity)
      if (activeConversationId.value === convId) {
        pendingContextReset.value = false
        sessionMode.value = 'continue'
        pinnedRunId = wasRunActive ? null : receipt.runId
      }
      const remainingResumptionErrors = { ...resumptionErrorsByConversation.value }
      delete remainingResumptionErrors[convId]
      resumptionErrorsByConversation.value = remainingResumptionErrors
      if (activeConversationId.value === convId) resumptionError.value = null

      // Refresh messages and runs
      await Promise.all([fetchMessages(convId), fetchConversationRuns(convId)])

      // If was queued, remove it
      removeQueuedMessage(clientMessageId)

      // Start event polling
      if (isPolling.value) scheduleNextPoll(0)
      return
    } catch (err: unknown) {
      if (conversation?.conversationKind === 'native' && err instanceof HubApiError && err.code === 'NATIVE_SESSION_CHANGED') await fetchConversations()
      if (definiteRejection(err)) completeOperation(identity)
      removeQueuedMessage(clientMessageId)
      if (activeConversationId.value === convId && err instanceof HubApiError) {
        if (err.code === 'SESSION_NOT_RESUMABLE') {
          const message = getRemoteErrorMessage(err.code, err.message, conversation?.conversationKind)
          resumptionErrorsByConversation.value = {
            ...resumptionErrorsByConversation.value,
            [convId]: message,
          }
          resumptionError.value = message
        } else {
          sendErrorsByConversation.value = {
            ...sendErrorsByConversation.value,
            [convId]: err.message,
          }
          sendError.value = err.message
        }
      } else if (err instanceof HubApiError && err.code === 'SESSION_NOT_RESUMABLE') {
        resumptionErrorsByConversation.value = {
          ...resumptionErrorsByConversation.value,
          [convId]: getRemoteErrorMessage(err.code, err.message, conversation?.conversationKind),
        }
      } else {
        const message = err instanceof Error ? err.message : '发送消息失败'
        sendErrorsByConversation.value = { ...sendErrorsByConversation.value, [convId]: message }
        if (activeConversationId.value === convId) sendError.value = message
      }
      throw err
    } finally {
      sendingConversationIds.value = sendingConversationIds.value.filter((id) => id !== convId)
    }
  }

  async function controlRun(
    runId: string,
    action: TaskActionInput['action'],
    instruction?: string
  ): Promise<void> {
    const conversationId = activeConversationId.value
    const generation = viewGeneration
    if (isConversationBusy.value && action !== 'cancel') {
      actionError.value = '对话正在进行，结束后再继续'
      throw new HubApiError('对话正在进行，结束后再继续', 'REMOTE_CONVERSATION_BUSY', 409)
    }
    if (isActiveConversationArchived.value && (action === 'resume' || action === 'retry')) {
      throw new HubApiError('请先恢复已归档任务，再继续或重试', 'CONFLICT', 409)
    }
    isActionLoading.value = true
    actionError.value = null
    const identity = `control:${runId}:${action}:${instruction || ''}`
    const operation = pendingOperation(identity, { action, instruction }, activeConversation.value?.conversationKind === 'native')
    const idempotencyKey = operation.id
    try {
      const gateway = getLocalChatGateway()
      const updatedRun = await gateway.controlLocalRun(
        runId,
        operation.payload,
        idempotencyKey
      )
      completeOperation(identity)
      if (generation === viewGeneration && activeConversationId.value === conversationId
        && updatedRun.conversationId === conversationId) {
        activeRun.value = updatedRun
        pinnedRunId = updatedRun.id
        await Promise.all([
          fetchMessages(conversationId),
          fetchConversationRuns(conversationId),
        ])
      }
    } catch (err: unknown) {
      if (definiteRejection(err)) completeOperation(identity)
      if (generation === viewGeneration && activeConversationId.value === conversationId) {
        actionError.value = err instanceof Error ? err.message : '执行操作失败'
      }
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
    if (!isPolling.value) {
      isPolling.value = true
      pollingEpoch++
    }
    // Also repairs an enabled poller whose timer is no longer scheduled.
    scheduleNextPoll(0)
  }

  function stopPolling(): void {
    isPolling.value = false
    pollingEpoch++
    viewGeneration++
    if (pollingTimer) {
      clearTimeout(pollingTimer)
      pollingTimer = null
    }
  }

  function splitPath(fullPath: string): { fileName: string; dirPath: string } {
    const normalized = fullPath.replace(/\\/g, '/')
    const lastSlash = normalized.lastIndexOf('/')
    if (lastSlash === -1) {
      return { fileName: fullPath, dirPath: '' }
    }
    const fileName = normalized.slice(lastSlash + 1)
    const dirPath = normalized.slice(0, lastSlash)
    return { fileName: fileName || fullPath, dirPath }
  }

  function parseToolArgs(toolName: string, rawArgs: string): {
    target: string
    fileName?: string
    dirPath?: string
    rawArgs?: string
  } {
    const trimmed = rawArgs.trim()
    if (!trimmed) {
      return { target: toolName }
    }

    let parsed: Record<string, unknown> | null = null
    if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
      try {
        parsed = JSON.parse(trimmed)
      } catch {
        // ignore JSON parse error, treat as raw string
      }
    }

    if (parsed && typeof parsed === 'object') {
      const pathKeys = ['file_path', 'filePath', 'path', 'targetFile', 'TargetFile', 'file', 'target']
      let foundPath: string | null = null
      for (const k of pathKeys) {
        if (typeof parsed[k] === 'string' && parsed[k]) {
          foundPath = parsed[k] as string
          break
        }
      }

      const patternKeys = ['pattern', 'query', 'regex', 'search_text']
      let foundPattern: string | null = null
      for (const k of patternKeys) {
        if (typeof parsed[k] === 'string' && parsed[k]) {
          foundPattern = parsed[k] as string
          break
        }
      }

      const cmdKeys = ['command', 'cmd', 'CommandLine', 'commandLine', 'exec']
      let foundCmd: string | null = null
      for (const k of cmdKeys) {
        if (typeof parsed[k] === 'string' && parsed[k]) {
          foundCmd = parsed[k] as string
          break
        }
      }

      if (foundPattern) {
        let target = `"${foundPattern}"`
        let dirPath = foundPath || undefined
        let fileName: string | undefined = undefined
        if (foundPath) {
          const s = splitPath(foundPath)
          fileName = s.fileName
          dirPath = s.dirPath
          target = `"${foundPattern}" in ${fileName || foundPath}`
        }
        return {
          target,
          fileName,
          dirPath,
          rawArgs: trimmed,
        }
      }

      if (foundCmd) {
        return {
          target: foundCmd,
          rawArgs: trimmed,
        }
      }

      if (foundPath) {
        const { fileName, dirPath } = splitPath(foundPath)
        return {
          target: foundPath,
          fileName,
          dirPath,
          rawArgs: trimmed,
        }
      }

      const entries = Object.entries(parsed)
      if (entries.length === 1 && typeof entries[0][1] === 'string') {
        return {
          target: entries[0][1] as string,
          rawArgs: trimmed,
        }
      }
    }

    if (trimmed.includes('/') || trimmed.includes('\\')) {
      const { fileName, dirPath } = splitPath(trimmed)
      return {
        target: trimmed,
        fileName,
        dirPath,
        rawArgs: trimmed,
      }
    }

    return {
      target: trimmed,
      rawArgs: trimmed,
    }
  }

  function parseEventToActivity(event: HubEvent): ActivityItem | null {
    const p = (event.payload || {}) as Record<string, unknown>
    const eventId = event.eventId || `evt_${event.seq}`
    const timestamp = event.occurredAt || new Date().toISOString()

    if (event.type === 'agent.tool_call') {
      const rawToolName = String(p.toolName || '')
      const args = String(p.argumentsExcerpt || '')
      const result = p.resultSummary ? String(p.resultSummary) : undefined
      const failed = Boolean(p.failed)
      const duration = typeof p.durationMs === 'number' ? p.durationMs : undefined

      const normName = rawToolName.toLowerCase().replace(/[^a-z0-9]/g, '')
      const parsed = parseToolArgs(rawToolName, args)

      if (
        normName === 'commandexecution' ||
        normName === 'bash' ||
        normName === 'sh' ||
        normName === 'exec' ||
        normName === 'shell' ||
        normName === 'terminal' ||
        normName === 'runcommand'
      ) {
        return {
          id: eventId,
          type: 'command',
          verb: 'Ran',
          target: parsed.target || 'command',
          detail: result,
          status: failed ? 'failed' : 'done',
          durationMs: duration,
          timestamp,
          rawArgs: parsed.rawArgs,
        }
      }

      if (
        normName === 'filechange' ||
        normName === 'edit' ||
        normName === 'write' ||
        normName === 'replacefilecontent' ||
        normName === 'writetofile' ||
        normName === 'createfile' ||
        normName === 'patch'
      ) {
        return {
          id: eventId,
          type: 'file',
          verb: normName.includes('write') || normName.includes('create') ? 'Created' : 'Edited',
          target: parsed.target || 'file',
          fileName: parsed.fileName,
          dirPath: parsed.dirPath,
          detail: result,
          status: failed ? 'failed' : 'done',
          durationMs: duration,
          timestamp,
          rawArgs: parsed.rawArgs,
        }
      }

      if (
        normName === 'viewfile' ||
        normName === 'readfile' ||
        normName === 'read' ||
        normName === 'cat' ||
        normName === 'grep' ||
        normName === 'search' ||
        normName === 'glob' ||
        normName === 'find' ||
        normName === 'list'
      ) {
        const isSearch = normName === 'grep' || normName === 'search'
        return {
          id: eventId,
          type: 'file',
          verb: isSearch ? 'Search' : 'Read',
          target: parsed.target || 'file',
          fileName: parsed.fileName,
          dirPath: parsed.dirPath,
          detail: result,
          status: failed ? 'failed' : 'done',
          durationMs: duration,
          timestamp,
          rawArgs: parsed.rawArgs,
        }
      }

      return {
        id: eventId,
        type: 'tool',
        verb: rawToolName || 'Tool',
        target: parsed.target || rawToolName,
        fileName: parsed.fileName,
        dirPath: parsed.dirPath,
        detail: result,
        status: failed ? 'failed' : 'done',
        durationMs: duration,
        timestamp,
        rawArgs: parsed.rawArgs,
      }
    }

    if (event.type === 'agent.progress') {
      const message = String(p.message || '')
      if (!message) return null
      if (
        message.toLowerCase().includes('thought') ||
        message.toLowerCase().includes('think') ||
        message.includes('思考')
      ) {
        return {
          id: eventId,
          type: 'thought',
          verb: 'Thought',
          target: message,
          detail: typeof p.raw === 'object' ? JSON.stringify(p.raw, null, 2) : undefined,
          status: 'done',
          timestamp,
        }
      }
      return {
        id: eventId,
        type: 'progress',
        verb: 'Step',
        target: message,
        detail: typeof p.raw === 'object' ? JSON.stringify(p.raw, null, 2) : undefined,
        status: 'done',
        timestamp,
      }
    }

    if (event.type === 'node.resolved') {
      return {
        id: eventId,
        type: 'progress',
        verb: 'Assigned',
        target: `角色 ${event.roleId || ''} 由 ${event.agentInstanceId || 'Agent'} 承接`,
        status: 'done',
        timestamp,
      }
    }

    return null
  }

  function ingestEvent(event: HubEvent): void {
    const taskId = event.taskId || (event.aggregateType === 'task' ? event.aggregateId : undefined)
    if (!taskId) return

    const p = (event.payload || {}) as Record<string, unknown>
    const toolName = String(p.toolName || '')

    // Merge tool_result events into preceding tool call
    if (event.type === 'agent.tool_call' && toolName === 'tool_result') {
      const taskList = activitiesByTaskId.value[taskId] || []
      for (let i = taskList.length - 1; i >= 0; i--) {
        const item = taskList[i]
        if (item.type === 'file' || item.type === 'command' || item.type === 'tool') {
          const updatedItem: ActivityItem = {
            ...item,
            detail: p.resultSummary ? String(p.resultSummary) : item.detail,
            status: p.failed ? 'failed' : 'done',
            durationMs: typeof p.durationMs === 'number' ? p.durationMs : item.durationMs,
          }
          const updatedTaskList = [...taskList]
          updatedTaskList[i] = updatedItem
          activitiesByTaskId.value = {
            ...activitiesByTaskId.value,
            [taskId]: updatedTaskList,
          }

          const run =
            conversationRuns.value.find((r) => r.taskId === taskId) ||
            (activeRun.value?.taskId === taskId ? activeRun.value : null)
          if (run?.id && activitiesByRunId.value[run.id]) {
            const runList = activitiesByRunId.value[run.id]
            const rIdx = runList.findIndex((a) => a.id === item.id)
            if (rIdx !== -1) {
              const updatedRunList = [...runList]
              updatedRunList[rIdx] = updatedItem
              activitiesByRunId.value = {
                ...activitiesByRunId.value,
                [run.id]: updatedRunList,
              }
            }
          }
          return
        }
      }
    }

    const activity = parseEventToActivity(event)
    if (!activity) return

    const run =
      conversationRuns.value.find((r) => r.taskId === taskId) ||
      (activeRun.value?.taskId === taskId ? activeRun.value : null)
    const runId = run?.id

    const taskList = activitiesByTaskId.value[taskId] || []
    if (!taskList.some((a) => a.id === activity.id)) {
      activitiesByTaskId.value = {
        ...activitiesByTaskId.value,
        [taskId]: [...taskList, activity],
      }
    }

    if (runId) {
      const runList = activitiesByRunId.value[runId] || []
      if (!runList.some((a) => a.id === activity.id)) {
        activitiesByRunId.value = {
          ...activitiesByRunId.value,
          [runId]: [...runList, activity],
        }
      }
    }
  }

  function getActivitiesForRun(runId: string): ActivityItem[] {
    const run =
      conversationRuns.value.find((r) => r.id === runId) ||
      (activeRun.value?.id === runId ? activeRun.value : null)
    if (run?.taskId && activitiesByTaskId.value[run.taskId]?.length) {
      return activitiesByTaskId.value[run.taskId]
    }
    if (activitiesByRunId.value[runId]?.length) {
      return activitiesByRunId.value[runId]
    }
    if (run?.task?.nodes?.length) {
      return run.task.nodes
        .filter((n) => n.outputSummary || n.status === 'succeeded' || n.status === 'running')
        .map((n) => ({
          id: `node_act_${n.id}`,
          type: 'file' as const,
          verb: 'Analyzed',
          target: `${n.resolvedAgentName || n.roleId} 角色执行`,
          detail: n.outputSummary,
          status: n.status === 'running' ? ('running' as const) : ('done' as const),
          timestamp: run.updatedAt,
        }))
    }
    return []
  }

  const activeRunActivities = computed<ActivityItem[]>(() => {
    if (!activeRun.value) return []
    return getActivitiesForRun(activeRun.value.id)
  })

  async function backfillEvents(): Promise<void> {
    const generation = viewGeneration
    try {
      const gateway = getLocalChatGateway()
      const page = await gateway.listLocalEvents(lastEventSeq.value, 200)
      if (generation !== viewGeneration) return
      if (page.events?.length) {
        for (const evt of page.events) {
          ingestEvent(evt)
        }
      }
      if (page.nextSeq > lastEventSeq.value) {
        lastEventSeq.value = page.nextSeq
      }
    } catch {
      // ignore backfill errors
    }
  }

  async function pollEvents(): Promise<void> {
    if (!isPolling.value || activePollEpoch === pollingEpoch) return
    const epoch = pollingEpoch
    activePollEpoch = epoch
    if (pollingTimer) clearTimeout(pollingTimer)
    pollingTimer = null
    const generation = viewGeneration
    let hasMore = false
    loadError.value = null
    // Snapshot reads proceed even when the event request is slow or fails.
    const conversationId = activeConversationId.value
    const snapshot = conversationId ? Promise.all([
      fetchConversations(), fetchMessages(conversationId), fetchConversationRuns(conversationId), fetchApprovals(),
    ]) : Promise.resolve()
    try {
      const gateway = getLocalChatGateway()
      // Bound each batch, then yield to rendering before catching up more pages.
      for (let count = 0; count < 5; count++) {
        const after = lastEventSeq.value
        const page = await gateway.listLocalEvents(after, 200)
        if (generation !== viewGeneration || epoch !== pollingEpoch) return
        for (const evt of page.events || []) ingestEvent(evt)
        lastEventSeq.value = Math.max(lastEventSeq.value, page.nextSeq)
        hasMore = page.hasMore && page.nextSeq > after
        if (!hasMore) break
      }
    } catch (err: unknown) {
      if (generation !== viewGeneration || epoch !== pollingEpoch) return
      hasMore = false
      if (err instanceof HubApiError && (err.code === 'EVENT_CURSOR_EXPIRED' || err.status === 410)) {
        const latest = err.detail?.latestSeq
        if (typeof latest !== 'number' || latest < 0) {
          loadError.value = '事件游标已失效，请重新连接本机服务'
          stopPolling()
          return
        }
        lastEventSeq.value = latest
      } else {
        loadError.value = err instanceof Error ? err.message : '服务连接中断，正在重连'
      }
    } finally {
      await snapshot
      if (activePollEpoch === epoch) activePollEpoch = null
      // View changes invalidate response data, not the page's polling lifecycle.
      if (epoch === pollingEpoch) scheduleNextPoll(hasMore || generation !== viewGeneration ? 25 : undefined)
    }
  }

  function scheduleNextPoll(delayMs?: number): void {
    if (!isPolling.value || activePollEpoch === pollingEpoch) return
    if (pollingTimer) clearTimeout(pollingTimer)
    // Busy interval: 1000ms if run is active; Idle interval: 4000ms
    const interval = isCurrentRunActive.value ? 1000 : 4000
    pollingTimer = setTimeout(() => {
      pollingTimer = null
      void pollEvents()
    }, delayMs ?? interval)
  }

  function reset(): void {
    clearVolatileOperations()
    deletedConversationIds.clear()
    stopPolling()
    viewGeneration++
    pinnedRunId = null
    conversations.value = []
    activeConversationId.value = null
    searchQuery.value = ''
    showArchived.value = false
    collapsedWorkspaceIds.value = {}
    conversationDrafts.value = {}
    conversationDraftRevisions.value = {}
    messages.value = []
    conversationRuns.value = []
    activeRun.value = null
    workspaces.value = []
    scenes.value = []
    approvals.value = []
    allQueuedMessages.value = []
    sendingConversationIds.value = []
    activitiesByTaskId.value = {}
    activitiesByRunId.value = {}
    lastEventSeq.value = 0
    loadError.value = null
    sendError.value = null
    actionError.value = null
    resumptionError.value = null
    sendErrorsByConversation.value = {}
    resumptionErrorsByConversation.value = {}
    metadataError.value = null
    sessionMode.value = 'new'
    pendingContextReset.value = false
    includeHiddenConversations.value = false
  }

  return {
    conversations,
    activeConversationId,
    activeConversation,
    searchQuery,
    showArchived,
    collapsedWorkspaceIds,
    filteredConversations,
    groupedConversations,
    isActiveConversationArchived,
    isRemoteConversation,
    isConversationBusy,
    isBusyFromOtherEnd: isConversationBusy,
    includeHiddenConversations,
    canArchiveConversation,
    toggleWorkspaceCollapsed,
    conversationDrafts,
    getConversationDraft,
    setConversationDraft,
    getConversationDraftRevision,
    isMetadataUpdating,
    metadataError,
    messages,
    isLoadingMessages,
    activeRun,
    conversationRuns,
    isLoadingRun,
    workspaces,
    scenes,
    isSending,
    sessionMode,
    effectiveSessionMode,
    pendingContextReset,
    canResetContext,
    requestContextReset,
    cancelContextReset,
    queuedMessages,
    removeQueuedMessage,
    clearSendError,
    sendError,
    resumptionError,
    loadError,
    isActionLoading,
    actionError,
    approvals,
    pendingApproval,
    isCurrentRunActive,
    activitiesByTaskId,
    activitiesByRunId,
    getActivitiesForRun,
    activeRunActivities,
    ingestEvent,
    init,
    fetchConversations,
    setIncludeHiddenConversations,
    setConversationVisibility,
    selectConversation,
    removeDeletedConversation,
    openBlockingRun,
    fetchMessages,
    fetchConversationRuns,
    fetchApprovals,
    createConversation,
    updateConversationMetadata,
    renameConversation,
    setConversationArchived,
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
