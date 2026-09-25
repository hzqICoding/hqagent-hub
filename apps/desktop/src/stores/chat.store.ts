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
  HubEvent,
} from '@hqagent/protocol'
import { getLocalChatGateway, HubApiError } from '@/shared/api'
import { pendingOperation, completeOperation, definiteRejection } from '@/shared/api/local-pending-operation'

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
  // A reset is an explicit, one-message choice within this conversation.
  // Normal replies continue; a new conversation's first message starts fresh.
  const pendingContextReset = ref(false)
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

  const canResetContext = computed(() => Boolean(activeConversationId.value)
    && !isSending.value && !isActionLoading.value
    && !isLoadingMessages.value && !isLoadingRun.value
    && !isCurrentRunActive.value && queuedMessages.value.length === 0
    && !conversationRuns.value.some(run => ['running', 'queued', 'waiting_approval', 'paused'].includes(run.status)))

  const effectiveSessionMode = computed(() => sessionMode.value)

  function requestContextReset(): boolean {
    if (!canResetContext.value) return false
    pendingContextReset.value = true
    sessionMode.value = 'new'
    resumptionError.value = null
    return true
  }

  function cancelContextReset(): void {
    pendingContextReset.value = false
    sessionMode.value = messages.value.length > 0 || conversationRuns.value.length > 0 ? 'continue' : 'new'
    const detail = activeRun.value
    if (sessionMode.value === 'continue' && detail?.status === 'failed' && detail.error && /会话|上下文/.test(detail.error)) {
      resumptionError.value = detail.error
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
    const generation = viewGeneration
    pinnedRunId = null
    messages.value = []
    conversationRuns.value = []
    activeRun.value = null
    pendingContextReset.value = false
    sessionMode.value = 'new'
    loadError.value = null
    sendError.value = null
    resumptionError.value = null
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
      const live = runs.find(r => r.status === 'queued' || r.status === 'running' || r.status === 'waiting_approval' || r.status === 'paused')
      const conversation = conversations.value.find(c => c.id === conversationId)
      if (conversation) {
        conversation.activeRunId = live?.id
        conversation.lastRunId = runs[0]?.id
      }
      const targetRunId = pinnedRunId || live?.id || runs[0]?.id
      if (targetRunId) {
        const detail = await gateway.getLocalRun(targetRunId)
        if (generation !== viewGeneration || activeConversationId.value !== conversationId) return
        activeRun.value = detail
        // Current task progress must not wait behind unrelated historical pages.
        for (const event of detail.task?.events || []) ingestEvent(event)
        if (sessionMode.value === 'continue' && detail.status === 'failed' && detail.error && /会话|上下文/.test(detail.error)) {
          resumptionError.value = detail.error
        } else if (detail.status !== 'failed' || sessionMode.value === 'new') {
          resumptionError.value = null
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
    const gateway = getLocalChatGateway()
    if (!gateway.pickLocalDirectory) return null
    const result = await gateway.pickLocalDirectory({})
    return result.cancelled ? null : result.selectedPath || null
  }

  async function sendMessage(
    text: string,
    modeOverride?: 'new' | 'continue'
  ): Promise<void> {
    const convId = activeConversationId.value
    if (!convId || !text.trim() || isSending.value) return

    const mode = modeOverride || sessionMode.value
    if (mode === 'continue' && resumptionError.value) {
      throw new HubApiError(resumptionError.value, 'SESSION_NOT_RESUMABLE', 409)
    }
    const wasRunActive = isCurrentRunActive.value
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

      // Refresh messages and runs
      await Promise.all([fetchMessages(convId), fetchConversationRuns(convId)])

      // If was queued, remove it
      queuedMessages.value = queuedMessages.value.filter((q) => q.id !== clientMessageId)

      // Start event polling
      if (isPolling.value) scheduleNextPoll(0)
      return
    } catch (err: unknown) {
      if (definiteRejection(err)) completeOperation(identity)
      queuedMessages.value = queuedMessages.value.filter((q) => q.id !== clientMessageId)
      if (err instanceof HubApiError) {
        if (err.code === 'SESSION_NOT_RESUMABLE') {
          resumptionError.value =
            err.message || '该会话无法恢复；可新建任务，或明确重置当前任务的 Agent 上下文后发送'
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
      fetchMessages(conversationId), fetchConversationRuns(conversationId), fetchApprovals(),
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
    activitiesByTaskId.value = {}
    activitiesByRunId.value = {}
    lastEventSeq.value = 0
    loadError.value = null
    sendError.value = null
    actionError.value = null
    resumptionError.value = null
    sessionMode.value = 'new'
    pendingContextReset.value = false
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
    effectiveSessionMode,
    pendingContextReset,
    canResetContext,
    requestContextReset,
    cancelContextReset,
    queuedMessages,
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
