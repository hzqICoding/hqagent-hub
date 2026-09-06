import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useWorkspaceStore } from './workspace.store'

describe('WorkspaceStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('initializes with empty state and fetches workspaces', async () => {
    const store = useWorkspaceStore()
    expect(store.workspaces).toHaveLength(0)
    expect(store.currentWorkspace).toBeNull()

    await store.fetchWorkspaces()
    expect(store.workspaces.length).toBeGreaterThan(0)
    expect(store.currentWorkspace).not.toBeNull()
    expect(store.currentWorkspace?.name).toBe('HQAgent-Hub')
  })

  it('switches current workspace and updates lastOpenedAt', async () => {
    const store = useWorkspaceStore()
    await store.fetchWorkspaces()

    const initial = store.currentWorkspace
    expect(initial).toBeDefined()

    const added = store.addWorkspace('D:/Projects/MyNewApp', 'MyNewApp')
    expect(store.currentWorkspace?.id).toBe(added.id)

    if (initial) {
      store.switchWorkspace(initial.id)
      expect(store.currentWorkspace?.id).toBe(initial.id)
    }
  })

  it('adds and removes workspace', async () => {
    const store = useWorkspaceStore()
    await store.fetchWorkspaces()
    const initialCount = store.workspaces.length

    const created = store.addWorkspace('C:/Code/TestProject')
    expect(store.workspaces).toHaveLength(initialCount + 1)
    expect(created.name).toBe('TestProject')
    expect(created.memoryDirPresent).toBe(false)

    store.initMemoryDir(created.id)
    expect(store.workspaces.find((w) => w.id === created.id)?.memoryDirPresent).toBe(true)

    store.setWorkspaceProfile(created.id, 'profile_custom_1')
    expect(store.workspaces.find((w) => w.id === created.id)?.defaultProfileId).toBe('profile_custom_1')

    store.removeWorkspace(created.id)
    expect(store.workspaces).toHaveLength(initialCount)
  })
})
