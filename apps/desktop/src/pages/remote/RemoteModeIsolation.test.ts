import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { getRuntimeMode, setRuntimeModeForTesting } from '@/shared/config/runtime-mode'
import { useLocalAuthStore } from '@/stores/local-auth.store'
import { useRemoteAuthStore } from '@/stores/remote-auth.store'
import { setLocalChatGatewayMode } from '@/shared/api'
import { mockRemoteGateway } from '@/shared/api/mock-remote-gateway'
import { setRemoteGatewayForTesting } from '@/shared/api/remote-provider'
import { router } from '@/app/router'

describe('Runtime Mode Isolation & Credential Security', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    sessionStorage.clear()
    setRuntimeModeForTesting(null)
    setLocalChatGatewayMode('mock')
    setRemoteGatewayForTesting(mockRemoteGateway)
  })

  afterEach(() => {
    setRuntimeModeForTesting(null)
    setRemoteGatewayForTesting(null)
  })

  it('determines local desktop mode vs remote H5 mode cleanly', () => {
    // Default mode is local
    setRuntimeModeForTesting(null)
    expect(getRuntimeMode()).toBe('local')

    // Test remote mode override
    setRuntimeModeForTesting('remote')
    expect(getRuntimeMode()).toBe('remote')

    setRuntimeModeForTesting('local')
    expect(getRuntimeMode()).toBe('local')
  })

  it('preserves existing local desktop auth behavior completely unchanged', async () => {
    const localStore = useLocalAuthStore()
    expect(localStore.isMockMode).toBe(true)

    const isAuthed = await localStore.checkAuthStatus()
    expect(isAuthed).toBe(true)
    expect(localStore.authenticated).toBe(true)
  })

  it('maintains strict credential isolation: remote authentication does not touch local tokens or write to storage', async () => {
    const remoteStore = useRemoteAuthStore()

    // Login via remote auth
    const loggedIn = await remoteStore.login({ loginName: 'remote_user', password: 'secretpassword' })
    expect(loggedIn).toBe(true)

    // Verify NO remote session credentials leaked into storage
    expect(localStorage.getItem('hqagent_hub_token')).toBeNull()
    expect(localStorage.getItem('__Host-hqremote')).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('csrfToken')).toBeNull()
    expect(sessionStorage.length).toBe(0)

    // Local auth remains unaffected
    const localStore = useLocalAuthStore()
    expect(localStore.currentMode).toBe('mock')
  })

  it('B3: strictly isolates /remote-link as local mode and /remote or /remote/* as remote mode without prefix collision', async () => {
    const originalPathname = window.location.pathname

    try {
      // 1. /remote-link must resolve to local mode
      window.history.replaceState({}, '', '/remote-link')
      setRuntimeModeForTesting(null)
      expect(getRuntimeMode()).toBe('local')

      // 2. /remote/chat and /remote must resolve to remote mode
      window.history.replaceState({}, '', '/remote/chat')
      setRuntimeModeForTesting(null)
      expect(getRuntimeMode()).toBe('remote')

      window.history.replaceState({}, '', '/remote')
      setRuntimeModeForTesting(null)
      expect(getRuntimeMode()).toBe('remote')

      // 3. Router navigation guard check: /remote-link does NOT trigger remote login redirect
      const remoteAuthStore = useRemoteAuthStore()
      remoteAuthStore.isAuthenticated = false

      await router.push('/remote-link')
      expect(router.currentRoute.value.path).toBe('/remote-link')

      // 4. Navigating to /remote/chat while unauthenticated triggers redirect to /remote/login
      mockRemoteGateway.authenticated = false
      await router.push('/remote/chat')
      expect(router.currentRoute.value.path).toBe('/remote/login')
    } finally {
      window.history.replaceState({}, '', originalPathname)
    }
  })
})
