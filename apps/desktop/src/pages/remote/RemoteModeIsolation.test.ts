import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { getRuntimeMode, setRuntimeModeForTesting } from '@/shared/config/runtime-mode'
import { useLocalAuthStore } from '@/stores/local-auth.store'
import { useRemoteAuthStore } from '@/stores/remote-auth.store'
import { setLocalChatGatewayMode } from '@/shared/api'
import { mockRemoteGateway } from '@/shared/api/mock-remote-gateway'
import { setRemoteGatewayForTesting } from '@/shared/api/remote-provider'

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
})
