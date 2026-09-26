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
      try {
        const app = await gateway.getApproval('approval_demo')
        approvals.value = [app]
      } catch {
        // ignore
      }
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

  async function pollEvents(): Promise<void> {
    if (!activeConversationId.value) return
    try {
      const gateway = getRemoteGateway()
      const page = await gateway.listEvents(serverCursor.value || undefined)
      if (page.nextServerCursor) {
        serverCursor.value = page.nextServerCursor
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
    pollEvents,
    startPolling,
    stopPolling,
    reset,
  }
})
