import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useScenesStore } from './scenes.store'
import { setLocalChatGatewayMode } from '@/shared/api'

describe('ScenesStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocalChatGatewayMode('mock')
  })

  it('fetches scenes and agents properly', async () => {
    const store = useScenesStore()
    await store.fetchScenes()
    expect(store.scenes.length).toBe(3)
    expect(store.currentScene).toBeDefined()
    expect(store.availableAgents.length).toBeGreaterThan(0)
  })

  it('fetches and caches agent models', async () => {
    const store = useScenesStore()
    const models = await store.fetchAgentModels('claude-code-local')
    expect(models?.verified).toBe(true)
    expect(models?.models.length).toBeGreaterThan(0)

    // Cached check
    const cached = await store.fetchAgentModels('claude-code-local')
    expect(cached).toStrictEqual(models)
  })

  it('catches version conflict on saveScene', async () => {
    const store = useScenesStore()
    await store.fetchScenes()
    const scene = store.scenes[0]

    try {
      await store.saveScene(scene.id, {
        roles: scene.roles,
        expectedVersion: scene.version + 99,
      })
      expect.unreachable('Should fail with conflict')
    } catch {
      expect(store.conflictError).toBeDefined()
      expect(store.conflictError?.currentVersion).toBeDefined()
    }
  })
})
