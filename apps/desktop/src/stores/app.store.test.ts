import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAppStore } from './app.store'

describe('useAppStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('initializes with default state', () => {
    const store = useAppStore()
    expect(store.bootstrap).toBeNull()
    expect(store.isLogDrawerOpen).toBe(false)
    expect(store.sidebarCollapsed).toBe(false)
    expect(store.inspector.isOpen).toBe(false)
  })

  it('fetches bootstrap successfully', async () => {
    const store = useAppStore()
    await store.fetchBootstrap()

    expect(store.bootstrap).not.toBeNull()
    expect(store.bootstrap?.appVersion).toBe('0.1.0')
    expect(store.bootstrap?.agents.total).toBe(2)
    expect(store.logs.length).toBeGreaterThan(0)
  })

  it('manages logs properly', () => {
    const store = useAppStore()
    store.addLog({
      level: 'info',
      source: 'Test',
      message: 'Hello log',
    })
    expect(store.logs.length).toBe(1)
    expect(store.logs[0].message).toBe('Hello log')

    store.logFilterLevel = 'error'
    expect(store.filteredLogs.length).toBe(0)

    store.logFilterLevel = 'info'
    expect(store.filteredLogs.length).toBe(1)

    store.clearLogs()
    expect(store.logs.length).toBe(0)
  })

  it('handles feature availability check', async () => {
    const store = useAppStore()
    await store.fetchBootstrap()

    expect(store.isFeatureAvailable('tasks')).toBe(true)
  })

  it('switches mock scenarios', async () => {
    const store = useAppStore()
    await store.setScenario('first-run-no-agent')

    expect(store.activeScenario).toBe('first-run-no-agent')
    expect(store.bootstrap?.agents.total).toBe(0)
  })

  it('F2-R1: sets hubGate to maintenance and blocks task creation when bootstrap maintenance is true', async () => {
    const store = useAppStore()
    await store.setScenario('update-draining')

    expect(store.bootstrap?.maintenance).toBe(true)
    expect(store.hubGate).toBe('maintenance')
    expect(store.isTaskCreationAllowed).toBe(false)
  })

  it('F2-R1: handles HubApiError with HUB_MAINTENANCE', async () => {
    const { getUiGateway, HubApiError } = await import('@/shared/api')
    const gateway = getUiGateway()
    const orig = gateway.getBootstrap
    gateway.getBootstrap = async () => {
      throw new HubApiError('Hub under maintenance', 'HUB_MAINTENANCE', 503)
    }

    const store = useAppStore()
    await store.fetchBootstrap()

    expect(store.hubGate).toBe('maintenance')
    expect(store.hubGateReason).toBe('Hub under maintenance')
    expect(store.isTaskCreationAllowed).toBe(false)

    gateway.getBootstrap = orig
  })

  it('F2-R1: handles HubApiError with FEATURE_UNAVAILABLE', async () => {
    const { getUiGateway, HubApiError } = await import('@/shared/api')
    const gateway = getUiGateway()
    const orig = gateway.getBootstrap
    gateway.getBootstrap = async () => {
      throw new HubApiError('Tasks module not available', 'FEATURE_UNAVAILABLE', 503)
    }

    const store = useAppStore()
    await store.fetchBootstrap()

    expect(store.hubGate).toBe('feature_unavailable')
    expect(store.hubGateReason).toBe('Tasks module not available')
    expect(store.isTaskCreationAllowed).toBe(false)

    gateway.getBootstrap = orig
  })
})
