import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { RemoteAccountView, RemoteLoginInput } from '@hqagent/protocol'
import { getRemoteGateway, RemoteApiError } from '@/shared/api'

export const useRemoteAuthStore = defineStore('remoteAuth', () => {
  // Purely in-memory state. NO tokens, passwords, or credentials stored in localStorage/sessionStorage/IndexedDB!
  const isAuthenticated = ref(false)
  const user = ref<RemoteAccountView | null>(null)
  const isLoading = ref(false)
  const authError = ref<string | null>(null)
  const retryAfter = ref<number | null>(null)

  let countdownInterval: ReturnType<typeof setInterval> | null = null

  function startCountdown(seconds: number) {
    if (countdownInterval) {
      clearInterval(countdownInterval)
      countdownInterval = null
    }
    retryAfter.value = seconds
    countdownInterval = setInterval(() => {
      if (retryAfter.value !== null && retryAfter.value > 1) {
        retryAfter.value -= 1
      } else {
        retryAfter.value = null
        if (countdownInterval) {
          clearInterval(countdownInterval)
          countdownInterval = null
        }
      }
    }, 1000)
  }

  async function checkSession(): Promise<boolean> {
    isLoading.value = true
    authError.value = null
    try {
      const gateway = getRemoteGateway()
      const session = await gateway.getSession()
      if (session.authenticated) {
        isAuthenticated.value = true
        user.value = session.account
        return true
      }
      isAuthenticated.value = false
      user.value = null
      return false
    } catch {
      isAuthenticated.value = false
      user.value = null
      return false
    } finally {
      isLoading.value = false
    }
  }

  async function login(input: RemoteLoginInput): Promise<boolean> {
    if (retryAfter.value && retryAfter.value > 0) {
      authError.value = `请求被限流，请等待 ${retryAfter.value} 秒后重试`
      return false
    }

    isLoading.value = true
    authError.value = null
    try {
      const gateway = getRemoteGateway()
      const session = await gateway.login(input)
      isAuthenticated.value = true
      user.value = session.account
      authError.value = null
      retryAfter.value = null
      if (countdownInterval) {
        clearInterval(countdownInterval)
        countdownInterval = null
      }
      return true
    } catch (err: unknown) {
      isAuthenticated.value = false
      user.value = null

      if (err instanceof RemoteApiError) {
        if (err.code === 'REMOTE_RATE_LIMITED' || err.status === 429) {
          const waitTime = err.retryAfter || 30
          startCountdown(waitTime)
          authError.value = `请求过于频繁，已被限速，请等待 ${waitTime} 秒后重试`
          return false
        }
      }

      // Security requirement: generalized error message, do not distinguish whether user exists or password was wrong
      authError.value = '用户名或口令错误'
      return false
    } finally {
      isLoading.value = false
    }
  }

  async function logout(): Promise<void> {
    try {
      const gateway = getRemoteGateway()
      await gateway.logout()
    } catch {
      // ignore
    } finally {
      isAuthenticated.value = false
      user.value = null
      authError.value = null
      retryAfter.value = null
      if (countdownInterval) {
        clearInterval(countdownInterval)
        countdownInterval = null
      }
    }
  }

  function reset(): void {
    isAuthenticated.value = false
    user.value = null
    isLoading.value = false
    authError.value = null
    retryAfter.value = null
    if (countdownInterval) {
      clearInterval(countdownInterval)
      countdownInterval = null
    }
  }

  return {
    isAuthenticated,
    user,
    isLoading,
    authError,
    retryAfter,
    checkSession,
    login,
    logout,
    reset,
  }
})
