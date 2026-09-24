import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useLocalAuthStore } from './local-auth.store'
import { setLocalChatGatewayMode } from '@/shared/api'

describe('LocalAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocalChatGatewayMode('mock')
  })

  it('checks authentication status successfully in mock mode', async () => {
    const store = useLocalAuthStore()
    const isAuthed = await store.checkAuthStatus()
    expect(isAuthed).toBe(true)
    expect(store.authenticated).toBe(true)
    expect(store.protocolVersion).toBe('0.3.0')
    expect(store.authError).toBeNull()
  })

  it('allows logging out and logging in with connect code', async () => {
    const store = useLocalAuthStore()
    await store.logout()
    expect(store.authenticated).toBe(false)

    // Login with invalid short code
    const failed = await store.connectWithCode('123')
    expect(failed).toBe(false)
    expect(store.authError).toBeDefined()

    // Login with valid code
    const success = await store.connectWithCode('valid-connect-code-1234')
    expect(success).toBe(true)
    expect(store.authenticated).toBe(true)
    expect(store.authError).toBeNull()
  })
})
