import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useTeamStore } from './team.store'

describe('TeamStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('fetches team profiles and resolves active profile', async () => {
    const store = useTeamStore()
    expect(store.profiles).toHaveLength(0)

    await store.fetchProfiles()
    expect(store.profiles.length).toBeGreaterThan(0)
    expect(store.activeProfile).not.toBeNull()
    expect(store.resolvedTeam).not.toBeNull()
    expect(store.resolvedTeam?.resolvedRoles).toBeDefined()
  })

  it('duplicates existing team profile', async () => {
    const store = useTeamStore()
    await store.fetchProfiles()
    const initialCount = store.profiles.length

    const active = store.activeProfile!
    const cloned = await store.duplicateProfile(active.id, 'My Cloned Team')
    expect(store.profiles).toHaveLength(initialCount + 1)
    expect(cloned.name).toBe('My Cloned Team')
    expect(cloned.isDefault).toBe(false)
  })

  it('deletes team profile and switches active profile', async () => {
    const store = useTeamStore()
    await store.fetchProfiles()
    const active = store.activeProfile!

    const cloned = await store.duplicateProfile(active.id, 'Team To Delete')
    expect(store.activeProfileId).toBe(cloned.id)

    store.deleteProfile(cloned.id)
    expect(store.profiles.find((p) => p.id === cloned.id)).toBeUndefined()
    expect(store.activeProfileId).not.toBe(cloned.id)
  })

  it('exports and imports team profile', async () => {
    const store = useTeamStore()
    await store.fetchProfiles()
    const active = store.activeProfile!

    const json = store.exportProfile(active.id)
    expect(json).toContain(active.name)

    const imported = await store.importProfile(json)
    expect(imported.name).toBe(`${active.name} (导入)`)
  })

  it('updates role binding and re-resolves', async () => {
    const store = useTeamStore()
    await store.fetchProfiles()
    const active = store.activeProfile!

    store.updateRoleBinding(active.id, 'orchestrator', {
      primaryAgentId: 'agent_custom_override',
    })

    expect(store.activeProfile?.roleBindings.orchestrator.primaryAgentId).toBe('agent_custom_override')
  })
})
