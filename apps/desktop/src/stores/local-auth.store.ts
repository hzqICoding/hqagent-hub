import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getLocalChatGateway,
  getLocalChatGatewayMode,
  setLocalChatGatewayMode,
  type LocalChatGatewayMode,
  HubApiError,
} from '@/shared/api'

export const useLocalAuthStore = defineStore('localAuth', () => {
  const authenticated = ref(false)
  const protocolVersion = ref('0.3.0')
  const isChecking = ref(false)
  const isConnecting = ref(false)
  const authError = ref<string | null>(null)
  const currentMode = ref<LocalChatGatewayMode>(getLocalChatGatewayMode())

  const isMockMode = computed(() => currentMode.value === 'mock')

  async function checkAuthStatus(): Promise<boolean> {
    isChecking.value = true
    authError.value = null
    try {
      const gateway = getLocalChatGateway()
      const status = await gateway.getLocalAuthStatus()
      authenticated.value = status.authenticated
      protocolVersion.value = status.protocolVersion
      return status.authenticated
    } catch (err: unknown) {
      authenticated.value = false
      if (err instanceof HubApiError) {
        if (err.code === 'HUB_NOT_READY' || err.status === 503) {
          authError.value = 'Local Hub / Worker 尚未就绪或未启动，请检查后台服务'
        } else if (err.code === 'UNAUTHORIZED' || err.status === 401) {
          authError.value = '会话已过期或未授权，请输入一次性连接码连接'
        } else {
          authError.value = err.message
        }
      } else {
        authError.value = '无法连接到本地服务，请确认服务已启动'
      }
      return false
    } finally {
      isChecking.value = false
    }
  }

  async function connectWithCode(code: string): Promise<boolean> {
    isConnecting.value = true
    authError.value = null
    try {
      const gateway = getLocalChatGateway()
      const res = await gateway.openLocalSession({ code: code.trim() })
      authenticated.value = res.authenticated
      protocolVersion.value = res.protocolVersion
      return res.authenticated
    } catch (err: unknown) {
      authenticated.value = false
      if (err instanceof HubApiError) {
        if (err.status === 401 || err.code === 'UNAUTHORIZED') {
          authError.value = '连接码已失效或已过期，请在控制台获取最新连接码'
        } else if (err.status === 422 || err.code === 'VALIDATION_FAILED') {
          authError.value = '连接码格式不正确，至少需要 6 个字符'
        } else {
          authError.value = err.message
        }
      } else {
        authError.value = err instanceof Error ? err.message : '连接请求失败'
      }
      return false
    } finally {
      isConnecting.value = false
    }
  }

  async function logout(): Promise<void> {
    try {
      const gateway = getLocalChatGateway()
      await gateway.logoutLocalSession()
    } catch {
      // ignore
    } finally {
      authenticated.value = false
    }
  }

  function setGatewayMode(mode: LocalChatGatewayMode): void {
    setLocalChatGatewayMode(mode)
    currentMode.value = mode
    checkAuthStatus()
  }

  return {
    authenticated,
    protocolVersion,
    isChecking,
    isConnecting,
    authError,
    currentMode,
    isMockMode,
    checkAuthStatus,
    connectWithCode,
    logout,
    setGatewayMode,
  }
})
