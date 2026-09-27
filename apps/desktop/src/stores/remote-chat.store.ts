import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  RemoteDeviceView,
  RemoteConversationView,
  RemoteMessageView,
  RemoteRunView,
  RemoteCommandView,
  RemoteApprovalView,
  RemoteCatalogView,
  RemoteQueuedReceipt,
  RemoteCreateConversationInput,
  RemoteBrowserEvent,
} from '@hqagent/protocol'
import { getRemoteGateway, RemoteApiError } from '@/shared/api'

export interface RemoteControlState {
  outcome: 'confirmed' | 'rejected' | 'unconfirmed'
  executionMayStillBeRunning: boolean
  reason: string
}

export const useRemoteChatStore = defineStore('remoteChat', () => {
  // Devices
  const devices = ref<RemoteDeviceView[]>([])
  const isLoadingDevices = ref(false)
  const deviceError = ref<string | null>(null)
  const catalog = ref<RemoteCatalogView | null>(null)

  // Conversations
  const conversations = ref<RemoteConversationView[]>([])
  const activeConversationId = ref<string | null>(null)
  const isLoadingConversations = ref(false)

  // Messages & Runs & Commands & Approvals
  const messages = ref<RemoteMessageView[]>([])
  const runs = ref<RemoteRunView[]>([])
  const commands = ref<RemoteCommandView[]>([])
  const approvals = ref<RemoteApprovalView[]>([])

  // Stream & Cursor
  const serverCursor = ref<string | null>(null)
  const isPolling = ref(false)
  let pollingTimer: ReturnType<typeof setTimeout> | null = null

  // UI & Action states
  const isSending = ref(false)
  const sendError = ref<string | null>(null)
  const isActionLoading = ref(false)
  const actionError = ref<string | null>(null)
  const isSnapshotRebuilding = ref(false)
  const lastRevocationInfo = ref<{ workerId: string; executionMayStillBeRunning: boolean } | null>(null)

  // Active getters
  const activeConversation = computed(() =>
    conversations.value.find((c) => c.conversationId === activeConversationId.value) || null
  )

  const activeDevice = computed(() => {
    if (!activeConversation.value) {
      return devices.value[0] || null
    }
    return devices.value.find((d) => d.workerId === activeConversation.value?.targetWorkerId) || null
  })

  const isWorkerOnline = computed(() => activeDevice.value?.status === 'online')

  const activeRun = computed(() => {
    if (!activeConversationId.value) return null
    return runs.value.find((r) => r.conversationId === activeConversationId.value) || null
  })

  const activeApprovals = computed(() =>
    approvals.value.filter((a) => a.status === 'pending')
  )

  // --- Devices & Catalog ---

  async function fetchDevices(): Promise<void> {
    isLoadingDevices.value = true
    deviceError.value = null
    try {
      const gateway = getRemoteGateway()
      const page = await gateway.listDevices()
      devices.value = page.items
      if (devices.value.length > 0 && !catalog.value) {
        try {
          catalog.value = await gateway.getWorkerCatalog(devices.value[0].workerId)
        } catch {
          // catalog might be offline
        }
      }
    } catch (err: unknown) {
      deviceError.value = err instanceof Error ? err.message : '获取设备列表失败'
    } finally {
      isLoadingDevices.value = false
    }
  }

  async function revokeDevice(workerId: string, reason?: string): Promise<boolean> {
    try {
      const gateway = getRemoteGateway()
      const res = await gateway.revokeDevice(workerId, { reason })
      devices.value = devices.value.filter((d) => d.workerId !== workerId)
      lastRevocationInfo.value = {
        workerId: res.workerId,
        executionMayStillBeRunning: res.executionMayStillBeRunning,
      }
      return true
    } catch (err: unknown) {
      actionError.value = err instanceof Error ? err.message : '撤销设备失败'
      return false
    }
  }

  // --- Conversations ---

  async function fetchConversations(): Promise<void> {
    isLoadingConversations.value = true
    try {
      const gateway = getRemoteGateway()
      const page = await gateway.listConversations()
      conversations.value = page.items
      if (!activeConversationId.value && page.items.length > 0) {
        await selectConversation(page.items[0].conversationId)
      }
    } catch (err: unknown) {
      actionError.value = err instanceof Error ? err.message : '获取对话列表失败'
    } finally {
      isLoadingConversations.value = false
    }
  }

  async function createConversation(input: RemoteCreateConversationInput): Promise<RemoteConversationView | null> {
    try {
      const gateway = getRemoteGateway()
      const newConv = await gateway.createConversation(input)
      conversations.value.unshift(newConv)
      await selectConversation(newConv.conversationId)
      return newConv
    } catch (err: unknown) {
      actionError.value = err instanceof Error ? err.message : '创建对话失败'
      return null
    }
  }

  async function selectConversation(conversationId: string): Promise<void> {
    activeConversationId.value = conversationId
    sendError.value = null
    actionError.value = null
    await rebuildFromSnapshot(conversationId)
  }

  // --- Snapshot & Rebuild ---

  async function rebuildFromSnapshot(conversationId: string): Promise<void> {
    isSnapshotRebuilding.value = true
    try {
      const gateway = getRemoteGateway()
      const snapshot = await gateway.getConversationSnapshot(conversationId)
      serverCursor.value = snapshot.serverCursor
      messages.value = snapshot.messages || []
      runs.value = snapshot.runs || []
      commands.value = snapshot.commands || []
      approvals.value = snapshot.approvals ?? []
    } catch (err: unknown) {
      actionError.value = err instanceof Error ? err.message : '加载会话快照失败'
    } finally {
      isSnapshotRebuilding.value = false
    }
  }

  // --- Messaging & Queueing ---

  async function sendMessage(text: string, sessionMode: 'new' | 'continue' = 'continue'): Promise<RemoteQueuedReceipt | null> {
    if (!activeConversationId.value) return null
    isSending.value = true
    sendError.value = null

    const convId = activeConversationId.value
    const clientMessageId = `cmsg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`

    // Optimistic user message in UI
    const optimisticMsg: RemoteMessageView = {
      messageId: `temp_${Date.now()}`,
      conversationId: convId,
      role: 'user',
      text,
      createdAt: new Date().toISOString(),
    }
    messages.value.push(optimisticMsg)

    try {
      const gateway = getRemoteGateway()
      const receipt = await gateway.sendMessage(convId, {
        clientMessageId,
        text,
        sessionMode,
      })

      // Update command representation in memory
      commands.value.push({
        commandId: receipt.commandId,
        conversationId: convId,
        targetWorkerId: activeConversation.value?.targetWorkerId || 'worker_demo',
        type: 'run.submit',
        conversationSeq: receipt.conversationSeq,
        status: receipt.status,
        deliveryState: receipt.deliveryState,
        withdrawalState: 'none',
        workerOnline: receipt.workerOnline,
        observedAt: new Date().toISOString(),
        createdAt: new Date().toISOString(),
        expiresAt: receipt.expiresAt,
      })

      return receipt
    } catch (err: unknown) {
      if (err instanceof RemoteApiError) {
        sendError.value = err.message
      } else {
        sendError.value = '发送消息失败，请重试'
      }
      return null
    } finally {
      isSending.value = false
    }
  }

  // --- Run Controls ---

  async function controlRun(
    runId: string,
    action: 'pause' | 'resume' | 'cancel' | 'retry'
  ): Promise<RemoteQueuedReceipt | null> {
    isActionLoading.value = true
    actionError.value = null
    try {
      const gateway = getRemoteGateway()
      const receipt = await gateway.controlRun(runId, { action })
      try {
        const cmd = await gateway.getCommand(receipt.commandId)
        commands.value.push(cmd)
      } catch {
        // ignore
      }
      if (activeRun.value && activeRun.value.runId === runId) {
        if (action === 'pause') activeRun.value.status = 'paused'
        if (action === 'resume') activeRun.value.status = 'running'
        if (action === 'cancel') activeRun.value.status = 'cancelled'
      }
      return receipt
    } catch (err: unknown) {
      if (err instanceof RemoteApiError) {
        actionError.value = err.message
      } else {
        actionError.value = `执行 ${action} 操作失败`
      }
      return null
    } finally {
      isActionLoading.value = false
    }
  }

  // --- Command Withdrawal ---

  async function withdrawCommand(commandId: string, reason?: string): Promise<boolean> {
    isActionLoading.value = true
    actionError.value = null
    try {
      const gateway = getRemoteGateway()
      const updatedCmd = await gateway.withdrawCommand(commandId, { reason })
      const idx = commands.value.findIndex((c) => c.commandId === commandId)
      if (idx >= 0) {
        commands.value[idx] = updatedCmd
      }
      return true
    } catch (err: unknown) {
      if (err instanceof RemoteApiError) {
        actionError.value = err.message
      } else {
        actionError.value = '撤回指令失败'
      }
      return false
    } finally {
      isActionLoading.value = false
    }
  }

  // --- Approvals ---

  function isHighRiskApproval(approval: RemoteApprovalView): boolean {
    const highRiskActions = ['git_push', 'deploy', 'delete', 'db_migrate']
    return highRiskActions.includes(approval.action) || !approval.remoteApprovalAllowed
  }

  async function decideApproval(
    approvalId: string,
    decision: 'approve' | 'reject'
  ): Promise<boolean> {
    const approval = approvals.value.find((a) => a.approvalId === approvalId)
    if (!approval) return false

    // Security check on client
    if (decision === 'approve' && isHighRiskApproval(approval)) {
      actionError.value = '高风险操作禁止在手机端远程批准，请回到电脑端处理'
      return false
    }

    isActionLoading.value = true
    actionError.value = null
    try {
      const gateway = getRemoteGateway()
      await gateway.decideApproval(approvalId, { decision })
      approval.status = decision === 'approve' ? 'approved' : 'rejected'
      return true
    } catch (err: unknown) {
      if (err instanceof RemoteApiError) {
        actionError.value = err.message
      } else {
        actionError.value = '处理审批失败'
      }
      return false
    } finally {
      isActionLoading.value = false
    }
  }

  // --- Polling & Event Loop ---

  async function applyEvent(event: RemoteBrowserEvent): Promise<void> {
    const activeId = activeConversationId.value
    if (!activeId) return

    // 1. Top-level conversation.updated
    if (event.type === 'conversation.updated') {
      const conv = event.payload
      const idx = conversations.value.findIndex((c) => c.conversationId === conv.conversationId)
      if (idx >= 0) {
        conversations.value[idx] = { ...conversations.value[idx], ...conv }
      }
      return
    }

    // 2. Top-level command.updated
    if (event.type === 'command.updated') {
      const cmd = event.payload
      if (cmd.conversationId !== activeId) return
      const idx = commands.value.findIndex((c) => c.commandId === cmd.commandId)
      if (idx >= 0) {
        commands.value[idx] = { ...commands.value[idx], ...cmd }
      } else {
        commands.value.push(cmd)
      }
      return
    }

    // 3. Top-level message.appended
    if (event.type === 'message.appended') {
      const msg = event.payload
      if (msg.conversationId !== activeId) return
      if (msg.role === 'user') {
        const tempIdx = messages.value.findIndex(
          (m) => m.messageId.startsWith('temp_') && m.text === msg.text
        )
        if (tempIdx >= 0) {
          messages.value[tempIdx] = msg
          return
        }
      }
      if (!messages.value.some((m) => m.messageId === msg.messageId)) {
        messages.value.push(msg)
      }
      return
    }

    // 4. worker.event
    if (event.type === 'worker.event') {
      const workerEv = event.payload
      if (!workerEv || typeof workerEv !== 'object') {
        return
      }

      // If event has conversationId and it's not the active conversation, ignore it
      if ('conversationId' in workerEv && workerEv.conversationId && workerEv.conversationId !== activeId) {
        return
      }

      switch (workerEv.type) {
        case 'command.accepted': {
          const idx = commands.value.findIndex((c) => c.commandId === workerEv.commandId)
          if (idx >= 0) {
            commands.value[idx].status = 'accepted'
            commands.value[idx].deliveryState = 'sent'
          } else {
            commands.value.push({
              commandId: workerEv.commandId,
              conversationId: workerEv.conversationId,
              targetWorkerId: workerEv.workerId,
              type: 'run.submit',
              status: 'accepted',
              deliveryState: 'sent',
              withdrawalState: 'none',
              workerOnline: true,
              observedAt: workerEv.occurredAt,
              createdAt: workerEv.receivedAt,
              expiresAt: new Date(Date.now() + 86400000).toISOString(),
            })
          }
          break
        }

        case 'command.rejected': {
          const idx = commands.value.findIndex((c) => c.commandId === workerEv.commandId)
          if (idx >= 0) {
            commands.value[idx].status = 'rejected'
            commands.value[idx].error = workerEv.error
          } else {
            commands.value.push({
              commandId: workerEv.commandId,
              conversationId: workerEv.conversationId,
              targetWorkerId: workerEv.workerId,
              type: 'run.submit',
              status: 'rejected',
              deliveryState: 'sent',
              withdrawalState: 'none',
              workerOnline: true,
              observedAt: workerEv.occurredAt,
              createdAt: workerEv.receivedAt,
              expiresAt: new Date(Date.now() + 86400000).toISOString(),
              error: workerEv.error,
            })
          }
          break
        }

        case 'command.completed': {
          const idx = commands.value.findIndex((c) => c.commandId === workerEv.commandId)
          if (idx >= 0) {
            commands.value[idx].status = 'completed'
            if (workerEv.controlResult) {
              commands.value[idx].controlResult = workerEv.controlResult
            }
          } else {
            commands.value.push({
              commandId: workerEv.commandId,
              conversationId: workerEv.conversationId,
              targetWorkerId: workerEv.workerId,
              type: 'run.submit',
              status: 'completed',
              deliveryState: 'sent',
              withdrawalState: 'none',
              workerOnline: true,
              observedAt: workerEv.occurredAt,
              createdAt: workerEv.occurredAt,
              expiresAt: new Date(Date.now() + 86400000).toISOString(),
              controlResult: workerEv.controlResult,
            })
          }
          if (workerEv.resultStatus === 'approval_consumed') {
            if (workerEv.resultRef?.runId) {
              approvals.value = approvals.value.filter((a) => a.resultRef?.runId !== workerEv.resultRef?.runId)
            }
          }
          break
        }

        case 'command.failed': {
          const idx = commands.value.findIndex((c) => c.commandId === workerEv.commandId)
          if (idx >= 0) {
            commands.value[idx].status = 'failed'
            commands.value[idx].error = workerEv.error
            if (workerEv.controlResult) {
              commands.value[idx].controlResult = workerEv.controlResult
            }
          } else {
            commands.value.push({
              commandId: workerEv.commandId,
              conversationId: workerEv.conversationId,
              targetWorkerId: workerEv.workerId,
              type: 'run.submit',
              status: 'failed',
              deliveryState: 'sent',
              withdrawalState: 'none',
              workerOnline: true,
              observedAt: workerEv.occurredAt,
              createdAt: workerEv.occurredAt,
              expiresAt: new Date(Date.now() + 86400000).toISOString(),
              error: workerEv.error,
              controlResult: workerEv.controlResult,
            })
          }
          break
        }

        case 'command.control_result': {
          const idx = commands.value.findIndex((c) => c.commandId === workerEv.commandId)
          if (idx >= 0) {
            commands.value[idx].controlResult = workerEv.controlResult
          } else {
            commands.value.push({
              commandId: workerEv.commandId,
              conversationId: workerEv.conversationId,
              targetWorkerId: workerEv.workerId,
              type: 'run.pause',
              status: 'completed',
              deliveryState: 'sent',
              withdrawalState: 'none',
              workerOnline: true,
              observedAt: workerEv.occurredAt,
              createdAt: workerEv.occurredAt,
              expiresAt: new Date(Date.now() + 86400000).toISOString(),
              controlResult: workerEv.controlResult,
            })
          }
          break
        }

        case 'run.state_changed': {
          const runPayload = workerEv.payload
          const idx = runs.value.findIndex((r) => r.runId === runPayload.runId)
          if (idx >= 0) {
            runs.value[idx].status = runPayload.status
            runs.value[idx].observedAt = runPayload.observedAt
            if (runPayload.summary) runs.value[idx].summary = runPayload.summary
            if (runPayload.executionTaskId) runs.value[idx].executionTaskId = runPayload.executionTaskId
          } else {
            runs.value.push({
              runId: runPayload.runId,
              conversationId: runPayload.conversationId,
              status: runPayload.status,
              workerOnline: true,
              observedAt: runPayload.observedAt,
              summary: runPayload.summary,
              executionTaskId: runPayload.executionTaskId,
              parentExecutionTaskId: runPayload.parentExecutionTaskId,
            })
          }
          break
        }

        case 'message.appended': {
          const msgPayload = workerEv.payload
          if (msgPayload.conversationId !== activeId) return
          if (!messages.value.some((m) => m.messageId === msgPayload.messageId)) {
            messages.value.push(msgPayload)
          }
          break
        }

        case 'approval.state_changed': {
          const appPayload = workerEv.payload
          if (appPayload.status === 'pending') {
            const idx = approvals.value.findIndex((a) => a.approvalId === appPayload.approvalId)
            if (idx >= 0) {
              approvals.value[idx] = appPayload
            } else {
              approvals.value.push(appPayload)
            }
          } else {
            // Terminal or consumed: remove from approvals
            approvals.value = approvals.value.filter((a) => a.approvalId !== appPayload.approvalId)
          }
          break
        }

        case 'run.progress': {
          if (workerEv.resultRef?.runId) {
            const run = runs.value.find((r) => r.runId === workerEv.resultRef?.runId)
            if (run) {
              run.summary = workerEv.message
            }
          }
          break
        }

        case 'capability.changed': {
          await fetchDevices()
          break
        }

        case 'conversation.skip_recorded': {
          break
        }

        default: {
          // Unknown worker event structure for current conversation -> fallback to snapshot refresh
          if ('conversationId' in workerEv && (workerEv as any).conversationId === activeId) {
            await rebuildFromSnapshot(activeId)
          }
          break
        }
      }
      return
    }

    // 5. Unknown top-level event structure for current conversation -> fallback to snapshot refresh
    const anyEvent = event as Record<string, any>
    const convId = anyEvent.conversationId || anyEvent.payload?.conversationId
    if (convId === activeId) {
      await rebuildFromSnapshot(activeId)
    }
  }

  let isPollingEvents = false

  async function pollEvents(): Promise<void> {
    if (isPollingEvents || !activeConversationId.value) return
    isPollingEvents = true
    try {
      const gateway = getRemoteGateway()
      let hasMore = true
      let pageCount = 0
      const maxPages = 50

      while (hasMore && activeConversationId.value && pageCount < maxPages) {
        pageCount++
        const page = await gateway.listEvents(serverCursor.value || undefined)
        if (page.nextServerCursor) {
          serverCursor.value = page.nextServerCursor
        }
        if (Array.isArray(page.items)) {
          for (const ev of page.items) {
            await applyEvent(ev)
          }
        }
        hasMore = Boolean(page.hasMore)
      }
    } catch (err: unknown) {
      if (err instanceof RemoteApiError) {
        // Fallback to snapshot on cursor expiration or invalid cursor
        if (err.code === 'REMOTE_CURSOR_EXPIRED' || err.code === 'REMOTE_CURSOR_INVALID') {
          if (activeConversationId.value) {
            await rebuildFromSnapshot(activeConversationId.value)
          }
        }
      }
    } finally {
      isPollingEvents = false
    }
  }

  function startPolling(intervalMs = 3000): void {
    stopPolling()
    isPolling.value = true
    const loop = async () => {
      if (!isPolling.value) return
      await pollEvents()
      if (isPolling.value) {
        pollingTimer = setTimeout(loop, intervalMs)
      }
    }
    pollingTimer = setTimeout(loop, intervalMs)
  }

  function stopPolling(): void {
    isPolling.value = false
    if (pollingTimer) {
      clearTimeout(pollingTimer)
      pollingTimer = null
    }
  }

  function reset(): void {
    stopPolling()
    devices.value = []
    catalog.value = null
    conversations.value = []
    activeConversationId.value = null
    messages.value = []
    runs.value = []
    commands.value = []
    approvals.value = []
    serverCursor.value = null
    isSending.value = false
    sendError.value = null
    isActionLoading.value = false
    actionError.value = null
    lastRevocationInfo.value = null
  }

  return {
    devices,
    isLoadingDevices,
    deviceError,
    catalog,
    conversations,
    activeConversationId,
    activeConversation,
    activeDevice,
    isWorkerOnline,
    isLoadingConversations,
    messages,
    runs,
    activeRun,
    commands,
    approvals,
    activeApprovals,
    serverCursor,
    isPolling,
    isSending,
    sendError,
    isActionLoading,
    actionError,
    isSnapshotRebuilding,
    lastRevocationInfo,
    fetchDevices,
    revokeDevice,
    fetchConversations,
    createConversation,
    selectConversation,
    rebuildFromSnapshot,
    sendMessage,
    controlRun,
    withdrawCommand,
    isHighRiskApproval,
    decideApproval,
    applyEvent,
    pollEvents,
    startPolling,
    stopPolling,
    reset,
  }
})
