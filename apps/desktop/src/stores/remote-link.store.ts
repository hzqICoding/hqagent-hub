import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { RemoteLinkView, RemoteLinkPairingInput, ErrorCode, RemoteSyncSettingsView } from '@hqagent/protocol'
import { getLocalChatGateway, HubApiError } from '@/shared/api'
import { getRemoteLinkErrorMessage } from '@/shared/i18n/remote-link-errors'

export const useRemoteLinkStore = defineStore('remoteLink', () => {
  // Pure in-memory state. No tokens, no secrets, no pair codes written to any storage!
  const linkView = ref<RemoteLinkView>({ state: 'unpaired' })
  const isLoading = ref(false)
  const isActionLoading = ref(false)
  const actionError = ref<string | null>(null)
  const countdownSeconds = ref<number | null>(null)
  const lastRefreshedAt = ref<string | null>(null)

  // Sync settings
  const syncSettings = ref<RemoteSyncSettingsView | null>(null)
  const isSyncSettingsLoading = ref(false)
  const syncSettingsError = ref<string | null>(null)

  let pollInterval: ReturnType<typeof setInterval> | null = null
  let countdownTimer: ReturnType<typeof setInterval> | null = null

  // Computed state
  const state = computed(() => linkView.value.state)
  const isUnpaired = computed(() => linkView.value.state === 'unpaired')
  const isPairing = computed(() => linkView.value.state === 'pairing')
  const isPaired = computed(() => linkView.value.state === 'paired')
  const isRevoked = computed(() => linkView.value.state === 'revoked')
  const isFrozen = computed(() => linkView.value.state === 'frozen')

  const serverOrigin = computed(() => (linkView.value as any).serverOrigin || '')
  const deviceName = computed(() => (linkView.value as any).deviceName || '我的电脑')
  const workerId = computed(() => (linkView.value as any).workerId || '')
  const pairCode = computed(() => linkView.value.state === 'pairing' ? linkView.value.pairCode : '')
  const pairRequestId = computed(() => linkView.value.state === 'pairing' ? linkView.value.pairRequestId : '')
  const expiresAt = computed(() => linkView.value.state === 'pairing' ? linkView.value.expiresAt : null)

  const connectionStatus = computed(() => {
    if ('connectionStatus' in linkView.value) {
      return linkView.value.connectionStatus
    }
    return null
  })

  const lastConnectedAt = computed(() => {
    if ('lastConnectedAt' in linkView.value) {
      return linkView.value.lastConnectedAt
    }
    return null
  })

  const lastErrorCode = computed<ErrorCode | undefined>(() => {
    return (linkView.value as any).lastErrorCode
  })

  const lastErrorMessage = computed(() => {
    if (!lastErrorCode.value) return null
    return getRemoteLinkErrorMessage(lastErrorCode.value)
  })

  const formattedCountdown = computed(() => {
    if (countdownSeconds.value === null || countdownSeconds.value <= 0) {
      return '00:00'
    }
    const mins = Math.floor(countdownSeconds.value / 60)
    const secs = countdownSeconds.value % 60
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  })

  const formattedLastConnected = computed(() => {
    if (!lastConnectedAt.value) return '从未连接'
    try {
      const d = new Date(lastConnectedAt.value)
      if (Number.isNaN(d.getTime())) return lastConnectedAt.value
      return d.toLocaleString()
    } catch {
      return lastConnectedAt.value
    }
  })

  function updateCountdown() {
    if (linkView.value.state !== 'pairing' || !linkView.value.expiresAt) {
      countdownSeconds.value = null
      if (countdownTimer) {
        clearInterval(countdownTimer)
        countdownTimer = null
      }
      return
    }

    const expiryTime = new Date(linkView.value.expiresAt).getTime()
    const diff = Math.max(0, Math.floor((expiryTime - Date.now()) / 1000))
    countdownSeconds.value = diff

    if (diff <= 0) {
      if (countdownTimer) {
        clearInterval(countdownTimer)
        countdownTimer = null
      }
      // Re-fetch link to trigger expired state transition
      void refreshLink(true)
    }
  }

  function startCountdownTimer() {
    if (countdownTimer) clearInterval(countdownTimer)
    updateCountdown()
    countdownTimer = setInterval(updateCountdown, 1000)
  }

  function stopCountdownTimer() {
    if (countdownTimer) {
      clearInterval(countdownTimer)
      countdownTimer = null
    }
    countdownSeconds.value = null
  }

  function startPairingPolling() {
    stopPairingPolling()
    startCountdownTimer()
    // Poll every 2 seconds in pairing state
    pollInterval = setInterval(async () => {
      if (linkView.value.state === 'pairing') {
        await refreshLink(true)
      } else {
        stopPairingPolling()
      }
    }, 2000)
  }

  function stopPairingPolling() {
    if (pollInterval) {
      clearInterval(pollInterval)
      pollInterval = null
    }
    stopCountdownTimer()
  }

  async function refreshLink(silent = false): Promise<RemoteLinkView> {
    if (!silent) isLoading.value = true
    actionError.value = null
    try {
      const gateway = getLocalChatGateway()
      const view = await gateway.getRemoteLink()
      linkView.value = view
      lastRefreshedAt.value = new Date().toISOString()

      if (view.state === 'pairing') {
        if (!pollInterval) {
          startPairingPolling()
        } else {
          updateCountdown()
        }
      } else {
        stopPairingPolling()
      }
      return view
    } catch (err) {
      const message = err instanceof HubApiError
        ? getRemoteLinkErrorMessage(err.code)
        : err instanceof Error
        ? err.message
        : '获取远程连接状态失败'
      actionError.value = message
      throw err
    } finally {
      if (!silent) isLoading.value = false
    }
  }

  async function startPairing(input: RemoteLinkPairingInput): Promise<RemoteLinkView> {
    isActionLoading.value = true
    actionError.value = null
    try {
      const gateway = getLocalChatGateway()
      const view = await gateway.startRemotePairing({
        serverOrigin: input.serverOrigin.trim(),
        deviceName: input.deviceName?.trim() || '我的电脑',
      })
      linkView.value = view
      lastRefreshedAt.value = new Date().toISOString()
      startPairingPolling()
      return view
    } catch (err) {
      const message = err instanceof HubApiError
        ? getRemoteLinkErrorMessage(err.code)
        : err instanceof Error
        ? err.message
        : '发起配对失败'
      actionError.value = message
      throw err
    } finally {
      isActionLoading.value = false
    }
  }

  async function cancelPairing(): Promise<RemoteLinkView> {
    isActionLoading.value = true
    actionError.value = null
    try {
      const gateway = getLocalChatGateway()
      const view = await gateway.cancelRemotePairing()
      linkView.value = view
      stopPairingPolling()
      return view
    } catch (err) {
      const message = err instanceof HubApiError
        ? getRemoteLinkErrorMessage(err.code)
        : err instanceof Error
        ? err.message
        : '取消配对失败'
      actionError.value = message
      throw err
    } finally {
      isActionLoading.value = false
    }
  }

  async function unlink(): Promise<RemoteLinkView> {
    isActionLoading.value = true
    actionError.value = null
    try {
      const gateway = getLocalChatGateway()
      const view = await gateway.unlinkRemote()
      linkView.value = view
      stopPairingPolling()
      return view
    } catch (err) {
      const message = err instanceof HubApiError
        ? getRemoteLinkErrorMessage(err.code)
        : err instanceof Error
        ? err.message
        : '解除设备绑定失败'
      actionError.value = message
      throw err
    } finally {
      isActionLoading.value = false
    }
  }

  const mirrorEnabled = computed(() => syncSettings.value?.mirrorEnabled ?? true)

  async function fetchSyncSettings(): Promise<RemoteSyncSettingsView | null> {
    isSyncSettingsLoading.value = true
    syncSettingsError.value = null
    try {
      const gateway = getLocalChatGateway()
      const settings = await gateway.getRemoteSyncSettings()
      syncSettings.value = settings
      return settings
    } catch (err) {
      syncSettingsError.value = err instanceof Error ? err.message : '获取同步设置失败'
      return null
    } finally {
      isSyncSettingsLoading.value = false
    }
  }

  async function updateSyncSettings(enabled: boolean): Promise<RemoteSyncSettingsView> {
    isSyncSettingsLoading.value = true
    syncSettingsError.value = null
    try {
      const gateway = getLocalChatGateway()
      const expectedVersion = syncSettings.value?.version ?? 1
      const updated = await gateway.setRemoteSyncSettings({
        mirrorEnabled: enabled,
        expectedVersion,
      })
      syncSettings.value = updated
      return updated
    } catch (err) {
      const message = err instanceof Error ? err.message : '更新同步设置失败'
      syncSettingsError.value = message
      throw err
    } finally {
      isSyncSettingsLoading.value = false
    }
  }

  function clearError() {
    actionError.value = null
    syncSettingsError.value = null
  }

  return {
    linkView,
    isLoading,
    isActionLoading,
    actionError,
    countdownSeconds,
    lastRefreshedAt,
    // Sync settings
    syncSettings,
    isSyncSettingsLoading,
    syncSettingsError,
    mirrorEnabled,
    fetchSyncSettings,
    updateSyncSettings,
    // Computed
    state,
    isUnpaired,
    isPairing,
    isPaired,
    isRevoked,
    isFrozen,
    serverOrigin,
    deviceName,
    workerId,
    pairCode,
    pairRequestId,
    expiresAt,
    connectionStatus,
    lastConnectedAt,
    lastErrorCode,
    lastErrorMessage,
    formattedCountdown,
    formattedLastConnected,
    // Actions
    refreshLink,
    startPairing,
    cancelPairing,
    unlink,
    clearError,
    startPairingPolling,
    stopPairingPolling,
  }
})
