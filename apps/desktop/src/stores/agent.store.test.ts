import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAgentStore } from './agent.store'
import { useAppStore } from './app.store'

describe('useAgentStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('fetches and filters agents', async () => {
    const appStore = useAppStore()
    await appStore.setScenario('happy-path')

    const agentStore = useAgentStore()
    await agentStore.fetchAgents()

    expect(agentStore.agents.length).toBeGreaterThan(0)
    expect(agentStore.totalCount).toBe(agentStore.agents.length)

    // Test search filter
    agentStore.searchQuery = 'claude'
    expect(agentStore.filteredAgents.every((a) => a.displayName.toLowerCase().includes('claude') || a.adapterId.includes('claude'))).toBe(true)

    // Reset search
    agentStore.searchQuery = ''
    agentStore.statusFilter = 'ready'
    expect(agentStore.filteredAgents.every((a) => a.status === 'ready')).toBe(true)
  })

  it('toggles agent status', async () => {
    const agentStore = useAgentStore()
    await agentStore.fetchAgents()

    const first = agentStore.agents[0]
    expect(first).toBeDefined()
    const originalStatus = first.status

    agentStore.toggleAgent(first.id, false)
    expect(first.status).toBe('disabled')

    agentStore.toggleAgent(first.id, true)
    expect(first.status).toBe('ready')
  })

  it('handles empty state in first-run scenario', async () => {
    const appStore = useAppStore()
    await appStore.setScenario('first-run-no-agent')

    const agentStore = useAgentStore()
    await agentStore.fetchAgents()

    expect(agentStore.agents.length).toBe(0)
    expect(agentStore.totalCount).toBe(0)
  })
})
