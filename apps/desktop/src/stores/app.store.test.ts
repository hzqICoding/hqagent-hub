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
})
