import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useSessionStore } from './session.store'

describe('useSessionStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('fetches sessions and filters properly', async () => {
    const store = useSessionStore()
    await store.fetchSessions()

    expect(store.sessions.length).toBeGreaterThan(0)
    expect(store.totalSessions).toBeGreaterThan(0)

    store.searchQuery = 'Claude'
    expect(store.filteredSessions.every((s) => s.agentDisplayName.includes('Claude'))).toBe(true)

    store.searchQuery = ''
    store.filterStatus = 'active'
    expect(store.filteredSessions.every((s) => s.status === 'active')).toBe(true)
  })

  it('resumes a valid session and returns created task', async () => {
    const store = useSessionStore()
    await store.fetchSessions()

    const session = store.sessions[0]
    expect(session).toBeDefined()

    const resumedTask = await store.resumeSession(session.id, {
      instruction: '继续进行单元测试补充',
    })

    expect(resumedTask).toBeDefined()
    expect(resumedTask.id).toContain('task_resumed_')
    expect(resumedTask.status).toBe('running')
  })
})
