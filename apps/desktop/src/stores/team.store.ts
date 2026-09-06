import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  TeamProfileView,
  SaveTeamProfileInput,
  ResolvedTeamView,
  RoleBindingView,
  TeamProfilePolicies,
} from '@hqagent/protocol'
import { getUiGateway } from '@/shared/api'
import { useAppStore } from './app.store'

export const DEFAULT_TEAM_POLICIES: TeamProfilePolicies = {
  missingAgentStrategy: 'fallback_then_ask',
  allowOneAgentMultipleRoles: true,
  preferCrossAgentReview: true,
  sameAgentReviewStrategy: 'isolated_session',
}

export const STANDARD_ROLES: Array<{ roleId: string; roleName: string; description: string }> = [
  { roleId: 'orchestrator', roleName: '总控调度', description: '负责任务拆解、流程流转与跨角色协作编排' },
  { roleId: 'architect', roleName: '系统架构', description: '负责方案设计、模块切分与技术选型' },
  { roleId: 'frontend_implementer', roleName: '前端开发', description: '负责 UI/UX 实现、组件构建与交互逻辑' },
  { roleId: 'general_implementer', roleName: '全栈实现', description: '负责核心功能、后端业务逻辑与数据存储' },
  { roleId: 'reviewer', roleName: '代码审查', description: '负责验收标准核对、代码质量把控与安全性分析' },
  { roleId: 'tester', roleName: '测试验证', description: '负责自动化测试编写、执行与回归验收' },
]

export const useTeamStore = defineStore('team', () => {
  const gateway = getUiGateway()
  const appStore = useAppStore()

  // State
  const profiles = ref<TeamProfileView[]>([])
  const activeProfileId = ref<string | null>(null)
  const resolvedTeam = ref<ResolvedTeamView | null>(null)
  const isResolving = ref<boolean>(false)
  const isLoading = ref<boolean>(false)
  const error = ref<string | null>(null)

  // Getters
  const activeProfile = computed<TeamProfileView | null>(() => {
    if (!activeProfileId.value) return profiles.value[0] || null
    return profiles.value.find((p) => p.id === activeProfileId.value) || profiles.value[0] || null
  })

  const defaultProfile = computed<TeamProfileView | null>(() => {
    return profiles.value.find((p) => p.isDefault) || profiles.value[0] || null
  })

  const globalProfiles = computed<TeamProfileView[]>(() => {
    return profiles.value.filter((p) => p.scope === 'global')
  })

  const workspaceProfiles = computed<TeamProfileView[]>(() => {
    return profiles.value.filter((p) => p.scope === 'workspace')
  })

  // Actions
  async function fetchProfiles() {
    isLoading.value = true
    error.value = null

    try {
      const data = await gateway.listTeamProfiles()
      profiles.value = data
      if (!activeProfileId.value && data.length > 0) {
        const def = data.find((p) => p.isDefault) || data[0]
        activeProfileId.value = def.id
      }
      if (activeProfileId.value) {
        await resolveProfile(activeProfileId.value)
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '获取团队配置列表失败'
      error.value = msg
      appStore.addLog({
        level: 'error',
        source: 'TeamStore',
        message: `获取团队配置列表失败: ${msg}`,
      })
    } finally {
      isLoading.value = false
    }
  }

  async function selectProfile(id: string, workspaceId?: string) {
    activeProfileId.value = id
    await resolveProfile(id, workspaceId)
  }

  async function resolveProfile(profileId?: string, workspaceId?: string) {
    const targetId = profileId || activeProfileId.value
    if (!targetId) return

    isResolving.value = true
    try {
      const res = await gateway.resolveTeamProfile({
        profileId: targetId,
        workspaceId,
      })
      resolvedTeam.value = res
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '团队路由解析失败'
      appStore.addLog({
        level: 'warn',
        source: 'TeamStore',
        message: `团队路由解析失败: ${msg}`,
      })
    } finally {
      isResolving.value = false
    }
  }

  async function saveProfile(input: SaveTeamProfileInput): Promise<TeamProfileView> {
    isLoading.value = true
    try {
      const saved = await gateway.saveTeamProfile(input)
      const index = profiles.value.findIndex((p) => p.id === saved.id)
      if (index !== -1) {
        profiles.value[index] = saved
      } else {
        profiles.value.push(saved)
      }
      activeProfileId.value = saved.id
      await resolveProfile(saved.id, input.workspaceId)
      appStore.addLog({
        level: 'info',
        source: 'TeamStore',
        message: `已保存团队配置: ${saved.name}`,
      })
      return saved
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '保存团队配置失败'
      error.value = msg
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function duplicateProfile(id: string, newName?: string): Promise<TeamProfileView> {
    const source = profiles.value.find((p) => p.id === id)
    if (!source) throw new Error(`Profile ${id} not found`)

    const clonedInput: SaveTeamProfileInput = {
      name: newName || `${source.name} (副本)`,
      description: source.description,
      scope: source.scope,
      workspaceId: source.workspaceId,
      isDefault: false,
      roleBindings: JSON.parse(JSON.stringify(source.roleBindings)),
      policies: source.policies ? JSON.parse(JSON.stringify(source.policies)) : DEFAULT_TEAM_POLICIES,
    }

    return await saveProfile(clonedInput)
  }

  function deleteProfile(id: string) {
    const index = profiles.value.findIndex((p) => p.id === id)
    if (index !== -1) {
      const removed = profiles.value.splice(index, 1)[0]
      if (activeProfileId.value === id) {
        activeProfileId.value = profiles.value[0]?.id || null
      }
      appStore.addLog({
        level: 'info',
        source: 'TeamStore',
        message: `已删除团队配置: ${removed.name}`,
      })
      if (activeProfileId.value) {
        resolveProfile(activeProfileId.value)
      } else {
        resolvedTeam.value = null
      }
    }
  }

  function setDefaultProfile(id: string) {
    profiles.value.forEach((p) => {
      p.isDefault = p.id === id
    })
    appStore.addLog({
      level: 'info',
      source: 'TeamStore',
      message: `已设为默认团队配置: ${id}`,
    })
  }

  function updateRoleBinding(
    profileId: string,
    roleId: string,
    binding: Partial<RoleBindingView>
  ) {
    const p = profiles.value.find((prof) => prof.id === profileId)
    if (p && p.roleBindings[roleId]) {
      p.roleBindings[roleId] = {
        ...p.roleBindings[roleId],
        ...binding,
      }
      p.updatedAt = new Date().toISOString()
      resolveProfile(profileId)
    }
  }

  function exportProfile(id: string): string {
    const p = profiles.value.find((prof) => prof.id === id)
    if (!p) throw new Error(`Profile ${id} not found`)
    return JSON.stringify(p, null, 2)
  }

  async function importProfile(jsonStr: string): Promise<TeamProfileView> {
    const parsed = JSON.parse(jsonStr) as Partial<TeamProfileView>
    if (!parsed.name || !parsed.roleBindings) {
      throw new Error('无效的团队配置文件格式')
    }

    const input: SaveTeamProfileInput = {
      name: `${parsed.name} (导入)`,
      description: parsed.description,
      scope: parsed.scope || 'global',
      workspaceId: parsed.workspaceId,
      isDefault: false,
      roleBindings: parsed.roleBindings,
      policies: parsed.policies || DEFAULT_TEAM_POLICIES,
    }

    return await saveProfile(input)
  }

  return {
    profiles,
    activeProfileId,
    activeProfile,
    defaultProfile,
    globalProfiles,
    workspaceProfiles,
    resolvedTeam,
    isResolving,
    isLoading,
    error,
    fetchProfiles,
    selectProfile,
    resolveProfile,
    saveProfile,
    duplicateProfile,
    deleteProfile,
    setDefaultProfile,
    updateRoleBinding,
    exportProfile,
    importProfile,
  }
})
