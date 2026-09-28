import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useRemoteAuthStore } from '@/stores/remote-auth.store'
import { mockRemoteGateway } from '@/shared/api/mock-remote-gateway'
import { setRemoteGatewayForTesting } from '@/shared/api/remote-provider'

describe('RemoteAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    sessionStorage.clear()
    setRemoteGatewayForTesting(mockRemoteGateway)
    mockRemoteGateway.authenticated = true
    mockRemoteGateway.rateLimited = false
    mockRemoteGateway.rateLimitSeconds = 30
  })

  afterEach(() => {
    setRemoteGatewayForTesting(null)
    vi.restoreAllMocks()
  })

  it('logs in successfully and does not store credentials in localStorage or sessionStorage', async () => {
    const store = useRemoteAuthStore()
    const success = await store.login({ loginName: 'alex', password: 'validpassword' })

    expect(success).toBe(true)
    expect(store.isAuthenticated).toBe(true)
    expect(store.user?.loginName).toBe('alex')
    expect(store.authError).toBeNull()

    // Storage audit: credentials must never be in client storage
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('csrfToken')).toBeNull()
    expect(localStorage.getItem('password')).toBeNull()
    expect(sessionStorage.length).toBe(0)
  })

  it('provides generalized error message on failure without leaking user existence', async () => {
    const store = useRemoteAuthStore()
    const success = await store.login({ loginName: 'wrong', password: 'wrong' })

    expect(success).toBe(false)
    expect(store.isAuthenticated).toBe(false)
    expect(store.user).toBeNull()
    // Generalized error message
    expect(store.authError).toBe('用户名或口令错误')
  })

  it('handles rate limiting and initiates Retry-After countdown timer', async () => {
    vi.useFakeTimers()
    const store = useRemoteAuthStore()

    mockRemoteGateway.rateLimited = true
    mockRemoteGateway.rateLimitSeconds = 15

    const success = await store.login({ loginName: 'alex', password: 'any' })
    expect(success).toBe(false)
    expect(store.retryAfter).toBe(15)
    expect(store.authError).toContain('请求过于频繁，已被限速')

    // While in countdown, new login attempts are blocked immediately
    const blockedAttempt = await store.login({ loginName: 'alex', password: 'any' })
    expect(blockedAttempt).toBe(false)
    expect(store.authError).toContain('请等待 15 秒后重试')

    // Advance 5 seconds
    vi.advanceTimersByTime(5000)
    expect(store.retryAfter).toBe(10)

    // Advance remaining 10 seconds
    vi.advanceTimersByTime(10000)
    expect(store.retryAfter).toBeNull()

    vi.useRealTimers()
  })

  it('restores authenticated state on checkSession and clears state on logout', async () => {
    const store = useRemoteAuthStore()
    mockRemoteGateway.authenticated = true

    const isAuthed = await store.checkSession()
    expect(isAuthed).toBe(true)
    expect(store.isAuthenticated).toBe(true)
    expect(store.user).toBeDefined()

    await store.logout()
    expect(store.isAuthenticated).toBe(false)
    expect(store.user).toBeNull()
  })
})
