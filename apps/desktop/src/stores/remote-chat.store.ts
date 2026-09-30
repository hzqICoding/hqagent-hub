import { preflightAttachments } from '@/shared/attachments/preflight'
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  NativeContinuationConfirmationInput,
  RemoteDeviceView,
  RemoteDevicePatchInput,
  RemoteConversationView,
  RemoteMessageView,
  RemoteRunView,
  RemoteCommandView,
  RemoteApprovalView,
  RemoteV4CatalogView,
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

export interface PendingConversationPlaceholder {
  conversationId: string
  title: string
  status: 'creating' | 'failed'
  createdAt: number
  timerId?: ReturnType<typeof setTimeout>
}

export function mergeRemoteMessages(
  existingMessages: RemoteMessageView[],
  incomingMessages: RemoteMessageView[]
): RemoteMessageView[] {
  const map = new Map<string, RemoteMessageView>()
  const tempMessages: RemoteMessageView[] = []

  for (const msg of existingMessages) {
    if (msg.messageId.startsWith('temp_')) {
      tempMessages.push(msg)
    } else {
      map.set(msg.messageId, msg)
    }
  }

  for (const incoming of incomingMessages) {
    if (incoming.messageId.startsWith('temp_')) {
      if (!tempMessages.some((t) => t.messageId === incoming.messageId)) {
        tempMessages.push(incoming)
      }
      continue
    }

    if (incoming.role === 'user') {
      const tempIdx = tempMessages.findIndex((t) => t.text === incoming.text)
      if (tempIdx >= 0) {
        tempMessages.splice(tempIdx, 1)
      }
    }

    const existing = map.get(incoming.messageId)
    if (!existing) {
      map.set(incoming.messageId, incoming)
    } else {
      const incomingRev = incoming.messageRevision ?? 0
      const existingRev = existing.messageRevision ?? 0
      if (incomingRev >= existingRev) {
        map.set(incoming.messageId, incoming)
      }
    }
  }

  const combined = [...map.values(), ...tempMessages]

  combined.sort((a, b) => {
    if (typeof a.messageSequence === 'number' && typeof b.messageSequence === 'number') {
      if (a.messageSequence !== b.messageSequence) {
        return a.messageSequence - b.messageSequence
      }
    } else if (typeof a.messageSequence === 'number') {
      return -1
    } else if (typeof b.messageSequence === 'number') {
      return 1
    }
    return new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()
  })

  return combined
}

export const useRemoteChatStore = defineStore('remoteChat', () => {
  const attachmentSendIntents = new Map<string, string>()
  // Devices
  const devices = ref<RemoteDeviceView[]>([])
  const selectedWorkerId = ref<string | null>(null)
  const isLoadingDevices = ref(false)
  const deviceError = ref<string | null>(null)
  const catalog = ref<RemoteV4CatalogView | null>(null)
  const isLoadingCatalog = ref(false)
  const catalogError = ref<string | null>(null)
  let catalogRequest = 0
  let deviceGeneration = 0
  let deviceListRequest = 0
  let revokedListRequest = 0
  const availableDevices = computed(() => devices.value.filter((d) => d.status !== 'revoked'))
  const revokedDevices = ref<RemoteDeviceView[]>([])
  const revokedDevicesLoaded = ref(false)
  const isLoadingRevokedDevices = ref(false)
  const isDeviceActionLoading = ref(false)
  const deviceActionError = ref<string | null>(null)
  const deviceRemovalNotice = ref<string | null>(null)
  const isRemoteSuspended = computed(() => activeDevice.value?.remoteAccess === 'suspended')
  const createdConversationToFocus = ref<string | null>(null)

  // Conversations
  const conversations = ref<RemoteConversationView[]>([])
  const activeConversationId = ref<string | null>(null)
  const isLoadingConversations = ref(false)
  const pendingConversation = ref<PendingConversationPlaceholder | null>(null)
  const settingsNotice = ref<string | null>(null)

  // Messages & Pagination
  const messages = ref<RemoteMessageView[]>([])
  const beforeCursor = ref<string | null>(null)
  const hasMoreMessages = ref(false)
  const isLoadingEarlierMessages = ref(false)

  // Runs & Commands & Approvals
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

  const selectedDevice = computed(() => {
    if (selectedWorkerId.value) {
      return devices.value.find((d) => d.workerId === selectedWorkerId.value) || null
    }
    return availableDevices.value[0] || null
  })

  const activeDevice = computed(() => {
    if (activeConversation.value?.targetWorkerId) {
      return devices.value.find((d) => d.workerId === activeConversation.value?.targetWorkerId) || null
    }
    return selectedDevice.value
  })

  const isWorkerOnline = computed(() => {
    const d = activeDevice.value
    if (!d || d.status === 'revoked') return false
    if (typeof d.online === 'boolean') return d.online
    return d.status === 'online'
  })

  const isDeviceSendReady = computed(() => {
    const d = activeDevice.value
    if (!d || d.status === 'revoked' || d.remoteAccess === 'suspended') return false
    if (d.online !== true && d.status !== 'online') return false
    if (d.status === 'reconciliation_required') return false
    if (d.supportedWireRevisions && !d.supportedWireRevisions.some((revision) => revision === 2 || revision === 3 || revision === 4)) return false
    if (d.busySnapshotFresh === false) return false
    return true
  })

  const isConversationBusy = computed(() => {
    if (!activeConversation.value) return false
    if (activeConversation.value.busy) return true
    const run = activeRun.value
    if (run && ['queued', 'running', 'waiting_approval'].includes(run.status)) return true
    return false
  })

  const conversationsByWorkspace = computed(() => {
    const map = new Map<string, { workspaceId: string; workspaceName: string; conversations: RemoteConversationView[] }>()
    if (catalog.value?.workspaces) {
      for (const ws of catalog.value.workspaces) {
        map.set(ws.workspaceId, {
          workspaceId: ws.workspaceId,
          workspaceName: ws.name,
          conversations: [],
        })
      }
    }
    for (const conv of conversations.value) {
      const wsId = conv.workspaceId || 'default'
      if (!map.has(wsId)) {
        map.set(wsId, {
          workspaceId: wsId,
          workspaceName: wsId === 'default' ? '默认项目' : wsId,
          conversations: [],
        })
      }
      map.get(wsId)!.conversations.push(conv)
    }
    return Array.from(map.values())
  })

  const activeRun = computed(() => {
    if (!activeConversationId.value) return null
    for (let i = runs.value.length - 1; i >= 0; i--) {
      if (runs.value[i].conversationId === activeConversationId.value) {
        return runs.value[i]
      }
    }
    return null
  })

  const activeApprovals = computed(() =>
    approvals.value.filter((a) => a.status === 'pending')
  )

  // --- Devices & Catalog ---

  async function fetchDevices(): Promise<boolean> {
    const request = ++deviceListRequest
    isLoadingDevices.value = true
    deviceError.value = null
    try {
      const gateway = getRemoteGateway()
      const items: RemoteDeviceView[] = []
      let cursor: string | undefined
      do {
        const page = await gateway.listDevices(cursor, 100, { includeRevoked: false })
        items.push(...page.items)
        if (page.hasMore && (!page.nextCursor || page.nextCursor === cursor)) throw new Error('设备分页游标无效，请重试')
        cursor = page.hasMore ? page.nextCursor : undefined
      } while (cursor)
      if (request !== deviceListRequest) return false
      const selected = selectedWorkerId.value || activeConversation.value?.targetWorkerId
      devices.value = items
      if (selected && !items.some((d) => d.workerId === selected)) await refreshDevice(selected)
      if (checkSelectedDeviceRevoked() || (selected && !selectedWorkerId.value && (lastRevocationInfo.value || deviceRemovalNotice.value))) return true
      if (selectedDevice.value && !catalog.value) await fetchCatalog()
      return true
    } catch (err: unknown) {
      deviceError.value = err instanceof Error ? err.message : '获取设备列表失败'
      return false
    } finally {
      isLoadingDevices.value = false
    }
  }

  async function fetchRevokedDevices(): Promise<boolean> {
    const request = ++revokedListRequest
    isLoadingRevokedDevices.value = true
    deviceError.value = null
    try {
      const items: RemoteDeviceView[] = []
      let cursor: string | undefined
      do {
        const page = await getRemoteGateway().listDevices(cursor, 100, { includeRevoked: true })
        items.push(...page.items.filter((d) => d.status === 'revoked'))
        if (page.hasMore && (!page.nextCursor || page.nextCursor === cursor)) throw new Error('设备分页游标无效，请重试')
        cursor = page.hasMore ? page.nextCursor : undefined
      } while (cursor)
      if (request !== revokedListRequest) return false
      revokedDevices.value = items
      revokedDevicesLoaded.value = true
      return true
    } catch (err: unknown) {
      deviceError.value = err instanceof Error ? err.message : '读取已撤销设备失败'
      return false
    } finally { isLoadingRevokedDevices.value = false }
  }

  async function refreshDevice(workerId: string): Promise<void> {
    try {
      const updated = await getRemoteGateway().getDevice(workerId)
      deviceListRequest++
      const idx = devices.value.findIndex((d) => d.workerId === workerId)
      if (idx >= 0) devices.value[idx] = updated
      else devices.value.push(updated)
      checkSelectedDeviceRevoked()
    } catch (err: unknown) {
      if (err instanceof RemoteApiError && err.status === 404 && getRemoteGateway().supportsDeviceManagement) {
        if (selectedWorkerId.value === workerId || activeConversation.value?.targetWorkerId === workerId) {
          clearDeviceContent()
          selectedWorkerId.value = null
          deviceRemovalNotice.value = '该电脑已删除'
          stopPolling()
          stopDevicePolling()
        }
      }
      throw err
    }
  }

  async function patchDevice(workerId: string, patch: Omit<RemoteDevicePatchInput, 'expectedVersion'>): Promise<boolean> {
    if (isDeviceActionLoading.value) return false
    deviceListRequest++
    isDeviceActionLoading.value = true
    deviceActionError.value = null
    try {
      const device = devices.value.find((d) => d.workerId === workerId)
      if (!device) throw new Error('设备状态未知，请刷新后重试')
      await getRemoteGateway().patchDevice(workerId, { ...patch, expectedVersion: device.version ?? 1 })
      await refreshDevice(workerId)
      return true
    } catch (err: unknown) {
      if (err instanceof RemoteApiError && err.code === 'CONFLICT') {
        try { await refreshDevice(workerId) } catch { /* Keep the original conflict visible. */ }
        deviceActionError.value = '设备状态已变化，请确认后重试'
      } else {
        deviceActionError.value = err instanceof Error ? err.message : '设备操作失败'
      }
      return false
    } finally { isDeviceActionLoading.value = false }
  }

  async function deleteDevice(workerId: string, refreshRevoked = false): Promise<boolean> {
    if (isDeviceActionLoading.value) return false
    isDeviceActionLoading.value = true
    deviceActionError.value = null
    try {
      try { await getRemoteGateway().deleteDevice(workerId) } catch (err: unknown) {
        if (!(err instanceof RemoteApiError) || err.status !== 404) throw err
        if (!getRemoteGateway().supportsDeviceManagement) throw new Error('服务端未确认支持设备删除，请升级到 0.8.0 或更新版本后重试', { cause: err })
      }
      if (selectedWorkerId.value === workerId || activeConversation.value?.targetWorkerId === workerId) {
        clearDeviceContent()
        selectedWorkerId.value = null
        deviceRemovalNotice.value = '该电脑已删除'
      }
      if (!await fetchDevices()) throw new Error('删除已提交，设备列表刷新失败，请重试刷新')
      if (refreshRevoked && !await fetchRevokedDevices()) throw new Error('删除已提交，历史记录刷新失败，请重试刷新')
      return true
    } catch (err: unknown) {
      deviceActionError.value = err instanceof Error ? err.message : '删除设备失败'
      return false
    } finally { isDeviceActionLoading.value = false }
  }

  function assertRemoteAllowed(safeAction = false, sending = false): void {
    if (safeAction || !isRemoteSuspended.value) return
    const message = '这台电脑的远程操作已暂停'
    if (sending) sendError.value = message
    else actionError.value = message
    throw new RemoteApiError({ message, code: 'REMOTE_DEVICE_SUSPENDED', status: 409 })
  }

  async function refreshOnSuspended(err: unknown): Promise<void> {
    if (err instanceof RemoteApiError && err.code === 'REMOTE_DEVICE_SUSPENDED') {
      await refreshActiveDevice()
    }
  }

  async function revokeDevice(workerId: string, reason?: string): Promise<boolean> {
    try {
      const gateway = getRemoteGateway()
      const res = await gateway.revokeDevice(workerId, { reason })
      const device = devices.value.find((d) => d.workerId === workerId)
      if (device) { device.status = 'revoked'; device.online = false }
      checkSelectedDeviceRevoked()
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

  let devicePollingTimer: ReturnType<typeof setInterval> | null = null

  async function refreshActiveDevice(): Promise<void> {
    const targetWorkerId = activeDevice.value?.workerId
    if (!targetWorkerId) return
    try { await refreshDevice(targetWorkerId) } catch { /* Retry on the next poll. */ }
  }

  function startDevicePolling(intervalMs = 15000): void {
    stopDevicePolling()
    devicePollingTimer = setInterval(async () => {
      await refreshActiveDevice()
    }, intervalMs)
  }

  function stopDevicePolling(): void {
    if (devicePollingTimer) {
      clearInterval(devicePollingTimer)
      devicePollingTimer = null
    }
  }

  // --- Conversations ---

  function clearDeviceContent(): void {
    deviceGeneration++
    catalogRequest++
    catalog.value = null
    catalogError.value = null
    isLoadingCatalog.value = false
    clearPendingConversation()
    createdConversationToFocus.value = null
    activeConversationId.value = null
    conversations.value = []
    messages.value = []
    runs.value = []
    commands.value = []
    approvals.value = []
    serverCursor.value = null
    beforeCursor.value = null
    hasMoreMessages.value = false
  }

  function checkSelectedDeviceRevoked(): boolean {
    const device = devices.value.find((d) => d.workerId === (selectedWorkerId.value || activeConversation.value?.targetWorkerId))
    if (device?.status !== 'revoked') return false
    lastRevocationInfo.value = { workerId: device.workerId, executionMayStillBeRunning: true }
    clearDeviceContent()
    selectedWorkerId.value = null
    stopPolling()
    stopDevicePolling()
    return true
  }

  async function fetchCatalog(): Promise<void> {
    const device = selectedDevice.value
    if (!device || device.status === 'revoked') return
    const request = ++catalogRequest
    isLoadingCatalog.value = true
    catalogError.value = null
    catalog.value = null
    try {
      const result = await getRemoteGateway().getWorkerCatalog(device.workerId)
      if (request !== catalogRequest) return
      if (result.workerId !== device.workerId || result.workerStoreId !== device.workerStoreId) {
        throw new Error('电脑目录已变更，请重试')
      }
      catalog.value = result
    } catch (err: unknown) {
      if (request === catalogRequest) catalogError.value = err instanceof Error ? err.message : '读取电脑目录失败，请重试'
    } finally {
      if (request === catalogRequest) isLoadingCatalog.value = false
    }
  }

  async function selectDevice(workerId: string): Promise<void> {
    selectedWorkerId.value = workerId
    if (checkSelectedDeviceRevoked()) return
    clearDeviceContent()
    lastRevocationInfo.value = null
    deviceRemovalNotice.value = null
    await Promise.all([fetchConversations(workerId), fetchCatalog()])
  }

  async function fetchConversations(workerId?: string, workspaceId?: string): Promise<void> {
    isLoadingConversations.value = true
    const generation = deviceGeneration
    try {
      const gateway = getRemoteGateway()
      const targetWId = workerId || selectedWorkerId.value || undefined
      const page = await gateway.listConversations({
        workerId: targetWId,
        workspaceId,
      })
      if (generation !== deviceGeneration) return
      if (targetWId && (selectedWorkerId.value || selectedDevice.value?.workerId) !== targetWId) return
      conversations.value = page.items
      if (!activeConversationId.value && page.items.length > 0) {
        await selectConversation(page.items[0].conversationId)
      }
      // F1: 下一次列表刷新拿到与占位相同的真实对话后，移除占位并自动选中
      if (pendingConversation.value?.status === 'creating') {
        const found = conversations.value.find((c) => c.conversationId === pendingConversation.value?.conversationId)
        if (found) {
          clearPendingConversation()
          await selectConversation(found.conversationId)
          createdConversationToFocus.value = found.conversationId
        }
      }
    } catch (err: unknown) {
      actionError.value = err instanceof Error ? err.message : '获取对话列表失败'
    } finally {
      isLoadingConversations.value = false
    }
  }

  async function createConversation(input: RemoteCreateConversationInput): Promise<string | null> {
    assertRemoteAllowed()
    if (!isWorkerOnline.value) {
      actionError.value = '设备离线，发送失败'
      throw new RemoteApiError({
        message: '设备离线，发送失败',
        code: 'REMOTE_DEVICE_OFFLINE',
        status: 409,
      })
    }

    const currentCatalog = catalog.value
    if (!currentCatalog || isLoadingCatalog.value || catalogError.value ||
        selectedDevice.value?.workerId !== input.targetWorkerId ||
        currentCatalog.workerId !== input.targetWorkerId ||
        currentCatalog.workerStoreId !== input.workerStoreId ||
        !currentCatalog.workspaces.some((w) => w.workspaceId === input.workspaceId) ||
        !currentCatalog.scenes.some((scene) => scene.sceneId === input.sceneId && scene.version === input.sceneVersion)) {
      actionError.value = '请先读取电脑的项目和场景列表'
      return null
    }
    actionError.value = null
    createdConversationToFocus.value = null
    try {
      const gateway = getRemoteGateway()
      const receipt = await gateway.createConversation(input)
      if (selectedDevice.value?.workerId !== input.targetWorkerId) return null
      await fetchConversations(input.targetWorkerId)
      const found = conversations.value.find((c) => c.conversationId === receipt.conversationId)
      if (found) {
        await selectConversation(found.conversationId)
        createdConversationToFocus.value = found.conversationId
        return receipt.conversationId
      }

      // F1: 202 后显示待创建占位（UI状态，不是 RemoteConversationView，不能选中/发送）
      clearPendingConversation()
      const placeholderId = receipt.conversationId
      const timer = setTimeout(() => {
        if (pendingConversation.value?.conversationId === placeholderId && pendingConversation.value.status === 'creating') {
          pendingConversation.value.status = 'failed'
        }
      }, 30000)

      pendingConversation.value = {
        conversationId: placeholderId,
        title: input.title,
        status: 'creating',
        createdAt: Date.now(),
        timerId: timer,
      }
      return receipt.conversationId
    } catch (err: unknown) {
      await refreshOnSuspended(err)
      actionError.value = err instanceof Error ? err.message : '创建对话失败'
      return null
    }
  }

  function clearPendingConversation(): void {
    if (pendingConversation.value?.timerId) {
      clearTimeout(pendingConversation.value.timerId)
    }
    pendingConversation.value = null
  }

  async function updateConversationSettings(
    conversationId: string,
    patch: { title?: string; archived?: boolean; visibility?: 'both' | 'pc_only' | 'mobile_only' }
  ): Promise<boolean> {
    const conv = conversations.value.find((c) => c.conversationId === conversationId)
    if (!conv) return false

    // Offline check: immediate failure
    assertRemoteAllowed()
    if (!isWorkerOnline.value) {
      actionError.value = '设备离线，发送失败'
      throw new RemoteApiError({
        message: '设备离线，发送失败',
        code: 'REMOTE_DEVICE_OFFLINE',
        status: 409,
      })
    }

    isActionLoading.value = true
    actionError.value = null
    settingsNotice.value = null
    try {
      const gateway = getRemoteGateway()
      await gateway.updateConversation(conversationId, {
        expectedVersion: conv.metadataVersion ?? 1,
        ...patch,
      })
      // F2: 202 后不改本地数据，只显示「等待电脑确认」
      settingsNotice.value = '等待电脑确认'
      return true
    } catch (err: unknown) {
      await refreshOnSuspended(err)
      if (err instanceof RemoteApiError && err.code === 'REMOTE_SYNC_CONFLICT') {
        // F2: 收到 REMOTE_SYNC_CONFLICT 时重新拉取该对话，并提示「同步冲突，请刷新」
        await fetchConversations(selectedWorkerId.value || activeDevice.value?.workerId)
        actionError.value = '同步冲突，请刷新'
        throw err
      }
      actionError.value = err instanceof Error ? err.message : '更新对话设置失败'
      throw err
    } finally {
      isActionLoading.value = false
    }
  }

  async function selectConversation(conversationId: string): Promise<void> {
    activeConversationId.value = conversationId
    sendError.value = null
    actionError.value = null
    await rebuildFromSnapshot(conversationId)
    await loadInitialMessages(conversationId)
  }

  // --- Messages & Pagination ---

  async function loadInitialMessages(conversationId: string): Promise<void> {
    try {
      const gateway = getRemoteGateway()
      const page = await gateway.listMessages(conversationId)
      if (activeConversationId.value !== conversationId) return
      if (page && Array.isArray(page.items)) {
        messages.value = mergeRemoteMessages([], page.items)
        hasMoreMessages.value = Boolean(page.hasMore)
        beforeCursor.value = page.before || null
      }
    } catch {
      // fallback to snapshot messages
    }
  }

  async function loadEarlierMessages(conversationId?: string): Promise<boolean> {
    const targetId = conversationId || activeConversationId.value
    if (!targetId || !hasMoreMessages.value || !beforeCursor.value || isLoadingEarlierMessages.value) {
      return false
    }
    isLoadingEarlierMessages.value = true
    try {
      const gateway = getRemoteGateway()
      const page = await gateway.listMessages(targetId, beforeCursor.value)
      if (activeConversationId.value !== targetId) return false
      if (page && Array.isArray(page.items) && page.items.length > 0) {
        messages.value = mergeRemoteMessages(messages.value, page.items)
        hasMoreMessages.value = Boolean(page.hasMore)
        beforeCursor.value = page.before || null
        return true
      }
      hasMoreMessages.value = false
      return false
    } catch (err: unknown) {
      actionError.value = err instanceof Error ? err.message : '加载更早消息失败'
      return false
    } finally {
      isLoadingEarlierMessages.value = false
    }
  }

  // --- Snapshot & Rebuild ---

  async function rebuildFromSnapshot(conversationId: string): Promise<void> {
    isSnapshotRebuilding.value = true
    try {
      const gateway = getRemoteGateway()
      const snapshot = await gateway.getConversationSnapshot(conversationId)
      if (activeConversationId.value !== conversationId) return
      serverCursor.value = snapshot.serverCursor
      messages.value = mergeRemoteMessages([], snapshot.messages || [])
      runs.value = snapshot.runs || []
      commands.value = snapshot.commands || []
      approvals.value = snapshot.approvals ?? []
      hasMoreMessages.value = Boolean(snapshot.hasMore)
    } catch (err: unknown) {
      actionError.value = err instanceof Error ? err.message : '加载会话快照失败'
    } finally {
      isSnapshotRebuilding.value = false
    }
  }

  // --- Messaging & Queueing ---

  async function sendMessage(text: string, sessionMode: 'new' | 'continue' = 'continue', nativeConfirmation?: NativeContinuationConfirmationInput, attachmentIds: string[] = []): Promise<RemoteQueuedReceipt | null> {
    if (!activeConversationId.value) return null

    // R1.5 Offline check: immediate failure, no queuing
    assertRemoteAllowed(false, true)
    if (!isWorkerOnline.value) {
      sendError.value = '设备离线，发送失败'
      throw new RemoteApiError({
        message: '设备离线，发送失败',
        code: 'REMOTE_DEVICE_OFFLINE',
        status: 409,
      })
    }

    const d = activeDevice.value
    // F5: 电脑端版本过旧提示
    if (d?.supportedWireRevisions && !(activeConversation.value?.conversationKind === 'native' ? d.supportedWireRevisions.some((revision) => revision === 3 || revision === 4) : d.supportedWireRevisions.some((revision) => revision === 2 || revision === 3 || revision === 4))) {
      sendError.value = '电脑端版本过旧，请升级 HQAgent'
      throw new RemoteApiError({
        message: '电脑端版本过旧，请升级 HQAgent',
        code: 'REMOTE_REVISION_REQUIRED',
        status: 409,
      })
    }

    // F5: 状态未就绪提示
    if (d?.busySnapshotFresh === false || d?.status === 'reconciliation_required') {
      sendError.value = '正在同步电脑状态，请稍后再试'
      throw new RemoteApiError({
        message: '正在同步电脑状态，请稍后再试',
        code: 'REMOTE_STATE_NOT_READY',
        status: 409,
      })
    }

    if (isConversationBusy.value) {
      sendError.value = '电脑上正在进行，结束后再继续'
      throw new RemoteApiError({
        message: '电脑上正在进行，结束后再继续',
        code: 'REMOTE_CONVERSATION_BUSY',
        status: 409,
      })
    }

    isSending.value = true
    sendError.value = null

    const convId = activeConversationId.value
    const intent = JSON.stringify([convId, text, attachmentIds, nativeConfirmation])
    const clientMessageId = attachmentIds.length ? (attachmentSendIntents.get(intent) || crypto.randomUUID()) : `cmsg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    if (attachmentIds.length) attachmentSendIntents.set(intent, clientMessageId)

    // Optimistic user message in UI
    const optimisticMsg: RemoteMessageView = {
      messageId: `temp_${Date.now()}`,
      conversationId: convId,
      role: 'user',
      text,
      createdAt: new Date().toISOString(),
    }
    messages.value = mergeRemoteMessages(messages.value, [optimisticMsg])

    try {
      const gateway = getRemoteGateway()
      if (attachmentIds.length && !d?.supportedWireRevisions?.includes(4)) throw new RemoteApiError({ code: 'REMOTE_REVISION_REQUIRED', status: 409, message: '电脑端不支持附件，请升级并等待修订 4 连接就绪' })
      if (attachmentIds.length) {
        await preflightAttachments(true, convId, attachmentIds, activeConversation.value || undefined)
        if (activeConversationId.value !== convId) throw new Error('对话已切换，请返回原对话重试')
        assertRemoteAllowed(false, true)
        if (!isWorkerOnline.value) throw new RemoteApiError({ code: 'REMOTE_DEVICE_OFFLINE', status: 409, message: '设备离线，发送失败' })
      }
      const receipt = await gateway.sendMessage(convId, {
        clientMessageId,
        text,
        sessionMode: activeConversation.value?.conversationKind === 'native' ? 'continue' : sessionMode,
        ...(nativeConfirmation ? { nativeConfirmation } : {}),
        ...(attachmentIds.length ? { attachmentIds } : {}),
      }, ...(attachmentIds.length ? [clientMessageId] : []))
      attachmentSendIntents.delete(intent)

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
      if (err instanceof RemoteApiError && err.status >= 400 && err.status < 500 && err.status !== 408 && err.status !== 429) attachmentSendIntents.delete(intent)
      await refreshOnSuspended(err)
      if (err instanceof RemoteApiError && err.code === 'NATIVE_SESSION_CHANGED') await fetchConversations(selectedWorkerId.value || undefined)
      // Remove optimistic message on failure
      const tempIdx = messages.value.findIndex((m) => m.messageId === optimisticMsg.messageId)
      if (tempIdx >= 0) {
        messages.value.splice(tempIdx, 1)
      }
      if (err instanceof RemoteApiError) {
        sendError.value = err.message
      } else {
        sendError.value = '发送消息失败，请重试'
      }
      throw err
    } finally {
      isSending.value = false
    }
  }

  // --- Run Controls ---

  async function controlRun(
    runId: string,
    action: 'pause' | 'resume' | 'cancel' | 'retry'
  ): Promise<RemoteQueuedReceipt | null> {
    assertRemoteAllowed(action === 'cancel')
    if (!isWorkerOnline.value) {
      actionError.value = '设备离线，发送失败'
      throw new RemoteApiError({
        message: '设备离线，发送失败',
        code: 'REMOTE_DEVICE_OFFLINE',
        status: 409,
      })
    }

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
      await refreshOnSuspended(err)
      if (err instanceof RemoteApiError) {
        actionError.value = err.message
      } else {
        actionError.value = `执行 ${action} 操作失败`
      }
      throw err
    } finally {
      isActionLoading.value = false
    }
  }

  // --- Command Withdrawal ---

  async function withdrawCommand(commandId: string, reason?: string): Promise<boolean> {
    assertRemoteAllowed()
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
      await refreshOnSuspended(err)
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

    assertRemoteAllowed(decision === 'reject')
    if (!isWorkerOnline.value) {
      actionError.value = '设备离线，发送失败'
      throw new RemoteApiError({
        message: '设备离线，发送失败',
        code: 'REMOTE_DEVICE_OFFLINE',
        status: 409,
      })
    }

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
      await refreshOnSuspended(err)
      if (err instanceof RemoteApiError) {
        actionError.value = err.message
      } else {
        actionError.value = '处理审批失败'
      }
      throw err
    } finally {
      isActionLoading.value = false
    }
  }

  // --- Polling & Event Loop ---

  async function applyEvent(event: RemoteBrowserEvent): Promise<void> {
    const activeId = activeConversationId.value

    // Handle conversation.deleted (F7: no as any)
    if (event.type === 'conversation.deleted') {
      const deletedId = event.conversationId
      conversations.value = conversations.value.filter((c) => c.conversationId !== deletedId)
      if (activeConversationId.value === deletedId) {
        activeConversationId.value = null
        messages.value = []
        runs.value = []
        commands.value = []
        approvals.value = []
      }
      return
    }

    // Handle store.reset (F7: no as any)
    if (event.type === 'store.reset') {
      if (activeDevice.value?.workerId === event.workerId || activeDevice.value?.workerStoreId === event.workerStoreId) {
        conversations.value = []
        activeConversationId.value = null
        messages.value = []
        runs.value = []
        commands.value = []
        approvals.value = []
        serverCursor.value = null
      }
      return
    }

    // F3: conversation.updated 处理移到 if (!activeId) return 之前
    if (event.type === 'conversation.updated') {
      const conv = event.payload
      // F3: 只处理 workerId 等于当前选中电脑的事件
      const currentWorkerId = selectedWorkerId.value || activeDevice.value?.workerId
      const convWorkerId = conv.workerId || conv.targetWorkerId
      if (currentWorkerId && convWorkerId && convWorkerId !== currentWorkerId) {
        return
      }

      // F3: pc_only 的对话从手机列表移除；如果它是当前对话，就清空当前对话
      if (conv.visibility === 'pc_only') {
        conversations.value = conversations.value.filter((c) => c.conversationId !== conv.conversationId)
        if (activeConversationId.value === conv.conversationId) {
          activeConversationId.value = null
          messages.value = []
          runs.value = []
          commands.value = []
          approvals.value = []
        }
        return
      }

      // F3: 不存在就插入，存在就按 metadataVersion 取新值替换，不能用旧值覆盖新值
      const idx = conversations.value.findIndex((c) => c.conversationId === conv.conversationId)
      if (idx >= 0) {
        const existing = conversations.value[idx]
        if ((conv.metadataVersion ?? 0) >= (existing.metadataVersion ?? 0)) {
          conversations.value[idx] = { ...existing, ...conv }
        }
      } else {
        conversations.value.unshift(conv)
      }

      // F1: 通过 conversation.updated 事件拿到真实对话后，移除占位并自动选中
      if (pendingConversation.value?.conversationId === conv.conversationId) {
        clearPendingConversation()
        await selectConversation(conv.conversationId)
        createdConversationToFocus.value = conv.conversationId
      }
      return
    }

    if (event.type === 'command.updated' && event.payload.error?.code === 'REMOTE_DEVICE_SUSPENDED' &&
        event.payload.targetWorkerId === (selectedWorkerId.value || activeDevice.value?.workerId)) {
      actionError.value = '这台电脑的远程操作已暂停'
      await refreshActiveDevice()
    }

    if (!activeId) return

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
      if (typeof cmd.workerOnline === 'boolean') {
        const targetWorkerId = cmd.targetWorkerId || activeConversation.value?.targetWorkerId
        if (targetWorkerId) {
          const devIdx = devices.value.findIndex((d) => d.workerId === targetWorkerId)
          if (devIdx >= 0) {
            devices.value[devIdx] = {
              ...devices.value[devIdx],
              online: cmd.workerOnline,
              status: cmd.workerOnline ? 'online' : 'offline',
            }
          } else {
            devices.value.push({
              workerId: targetWorkerId,
              deviceName: 'Computer',
              platform: 'windows',
              architecture: 'x86_64',
              online: cmd.workerOnline,
              status: cmd.workerOnline ? 'online' : 'offline',
              workerStoreId: 'store_demo',
              capabilityRevision: 1,
              observedAt: new Date().toISOString(),
              pairedAt: new Date().toISOString(),
            })
          }
        }
      }
      return
    }

    // 3. Top-level message.appended (F4: use mergeRemoteMessages)
    if (event.type === 'message.appended') {
      const msg = event.payload
      if (msg.conversationId !== activeId) return
      messages.value = mergeRemoteMessages(messages.value, [msg])
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
          messages.value = mergeRemoteMessages(messages.value, [msgPayload])
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
    if (isPollingEvents || (!activeConversationId.value && !pendingConversation.value)) return
    isPollingEvents = true
    const generation = deviceGeneration
    try {
      const gateway = getRemoteGateway()
      let hasMore = true
      let pageCount = 0
      const maxPages = 50

      while (hasMore && (activeConversationId.value || pendingConversation.value) && pageCount < maxPages) {
        pageCount++
        const page = await gateway.listEvents(serverCursor.value || undefined)
        if (generation !== deviceGeneration) return
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
    attachmentSendIntents.clear()
    deviceListRequest++
    revokedListRequest++
    stopPolling()
    stopDevicePolling()
    clearDeviceContent()
    devices.value = []
    revokedDevices.value = []
    revokedDevicesLoaded.value = false
    isLoadingRevokedDevices.value = false
    deviceActionError.value = null
    deviceRemovalNotice.value = null
    selectedWorkerId.value = null
    catalog.value = null
    conversations.value = []
    activeConversationId.value = null
    messages.value = []
    beforeCursor.value = null
    hasMoreMessages.value = false
    isLoadingEarlierMessages.value = false
    runs.value = []
    commands.value = []
    approvals.value = []
    serverCursor.value = null
    isSending.value = false
    sendError.value = null
    isActionLoading.value = false
    actionError.value = null
    lastRevocationInfo.value = null
    clearPendingConversation()
    settingsNotice.value = null
  }

  return {
    devices,
    availableDevices,
    revokedDevices,
    revokedDevicesLoaded,
    isLoadingRevokedDevices,
    isDeviceActionLoading,
    deviceActionError,
    deviceRemovalNotice,
    isRemoteSuspended,
    fetchRevokedDevices,
    refreshDevice,
    patchDevice,
    deleteDevice,
    isLoadingCatalog,
    catalogError,
    fetchCatalog,
    createdConversationToFocus,
    selectedWorkerId,
    selectedDevice,
    isLoadingDevices,
    deviceError,
    catalog,
    conversations,
    conversationsByWorkspace,
    activeConversationId,
    activeConversation,
    activeDevice,
    isWorkerOnline,
    isDeviceSendReady,
    isConversationBusy,
    isLoadingConversations,
    pendingConversation,
    clearPendingConversation,
    settingsNotice,
    messages,
    beforeCursor,
    hasMoreMessages,
    isLoadingEarlierMessages,
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
    refreshActiveDevice,
    startDevicePolling,
    stopDevicePolling,
    revokeDevice,
    selectDevice,
    fetchConversations,
    createConversation,
    updateConversationSettings,
    selectConversation,
    rebuildFromSnapshot,
    loadInitialMessages,
    loadEarlierMessages,
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
