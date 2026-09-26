import { afterEach, describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useScenesStore } from './scenes.store'
import { HubApiError, mockLocalChatGateway, setLocalChatGatewayMode } from '@/shared/api'

describe('ScenesStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocalChatGatewayMode('mock')
    mockLocalChatGateway.reset()
  })
  afterEach(() => { vi.restoreAllMocks() })

  it('fetches scenes and agents properly', async () => {
    const store = useScenesStore()
    await store.fetchScenes()
    expect(store.scenes.length).toBe(3)
    expect(store.currentScene).toBeDefined()
    expect(store.availableAgents.length).toBeGreaterThan(0)
    expect(store.roleTemplates.length).toBeGreaterThan(0)
  })

  it('creates custom scenes and incrementally caches role templates', async () => {
    const store = useScenesStore()
    await store.fetchScenes()
    const template = await store.createRoleTemplate({
      name: '自定义规划者', baseRoleId: 'planner', instructions: '输出施工计划',
    })
    expect(store.roleTemplates.find(item => item.id === template.id)).toBeDefined()

    const updated = await store.updateRoleTemplate(template.id, {
      expectedVersion: template.version, name: '高级规划者', instructions: '输出计划与验收标准',
    })
    expect(store.roleTemplates.find(item => item.id === template.id)).toMatchObject({ version: 2, name: '高级规划者' })

    const scene = await store.createScene({
      name: '规划场景',
      roles: [{
        roleId: 'planner', roleName: updated.name, agentInstanceId: store.availableAgents[0].id,
        instructions: updated.instructions, enabled: true,
        roleTemplateId: updated.id, roleTemplateVersion: updated.version,
      }],
    })
    expect(scene.id).not.toBe('analyze')
    expect(store.currentScene?.id).toBe(scene.id)
  })

  it('surfaces role-template version conflicts without changing the cached base role', async () => {
    const store = useScenesStore()
    await store.fetchScenes()
    const template = store.roleTemplates[0]

    await expect(store.updateRoleTemplate(template.id, {
      expectedVersion: template.version + 10,
      name: '过期模板更新',
      instructions: 'stale',
    })).rejects.toMatchObject({ code: 'CONFLICT' })
    expect(store.templateConflictError?.currentVersion).toBe(template.version)
    expect(store.roleTemplates[0].baseRoleId).toBe(template.baseRoleId)
  })

  it('reuses idempotency keys when template creates and updates retry after network failure', async () => {
    const store = useScenesStore()
    await store.fetchScenes()
    const createSpy = vi.spyOn(mockLocalChatGateway, 'createLocalRoleTemplate')
      .mockRejectedValueOnce(new HubApiError('网络中断', 'HUB_NOT_READY', 503, undefined, true))
    const createInput = { name: '可重试模板', baseRoleId: 'analyst' as const, instructions: '分析' }
    await expect(store.createRoleTemplate(createInput)).rejects.toMatchObject({ code: 'HUB_NOT_READY' })
    const created = await store.createRoleTemplate(createInput)
    expect(createSpy.mock.calls[0][1]).toBe(createSpy.mock.calls[1][1])

    const updateSpy = vi.spyOn(mockLocalChatGateway, 'updateLocalRoleTemplate')
      .mockRejectedValueOnce(new HubApiError('网络中断', 'HUB_NOT_READY', 503, undefined, true))
    const updateInput = { expectedVersion: created.version, name: '重试后模板', instructions: '分析并复核' }
    await expect(store.updateRoleTemplate(created.id, updateInput)).rejects.toMatchObject({ code: 'HUB_NOT_READY' })
    await store.updateRoleTemplate(created.id, updateInput)
    expect(updateSpy.mock.calls[0][2]).toBe(updateSpy.mock.calls[1][2])
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
