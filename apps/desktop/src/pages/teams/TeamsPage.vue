<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useAppStore } from '@/stores/app.store'
import { useTeamStore, STANDARD_ROLES, DEFAULT_TEAM_POLICIES } from '@/stores/team.store'
import { useAgentStore } from '@/stores/agent.store'
import type { ResolveSource } from '@hqagent/protocol'
import {
  Plus,
  Copy,
  Trash2,
  Download,
  Upload,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  Sliders,
  Star,
  RefreshCw,
} from 'lucide-vue-next'
import {
  HqButton,
  HqBadge,
  HqInput,
  HqDialog,
  LoadingState,
  HqEmptyState,
  HqErrorState,
  OfflineState,
} from '@/shared/ui'

const appStore = useAppStore()
const teamStore = useTeamStore()
const agentStore = useAgentStore()

// Modals
const isCreateModalOpen = ref(false)
const newProfileName = ref('')
const newProfileDesc = ref('')
const createError = ref<string | null>(null)

const isImportModalOpen = ref(false)
const importJsonText = ref('')
const importError = ref<string | null>(null)

onMounted(async () => {
  await Promise.all([
    teamStore.fetchProfiles(),
    agentStore.fetchAgents(),
  ])
})

const activeProfile = computed(() => teamStore.activeProfile)

watch(
  () => activeProfile.value?.id,
  (newId) => {
    if (newId) {
      teamStore.resolveProfile(newId)
    }
  }
)

function handleSelectProfile(id: string) {
  teamStore.selectProfile(id)
}

function handleOpenCreate() {
  newProfileName.value = ''
  newProfileDesc.value = ''
  createError.value = null
  isCreateModalOpen.value = true
}

async function handleConfirmCreate() {
  if (!newProfileName.value.trim()) {
    createError.value = '请输入团队配置名称'
    return
  }

  // Initialize with standard roles and first available agent
  const defaultAgentId = agentStore.readyAgents[0]?.id || ''
  const roleBindings: Record<string, any> = {}
  STANDARD_ROLES.forEach((r) => {
    roleBindings[r.roleId] = {
      roleId: r.roleId,
      roleName: r.roleName,
      primaryAgentId: defaultAgentId,
      fallbackAgentIds: [],
    }
  })

  try {
    await teamStore.saveProfile({
      name: newProfileName.value.trim(),
      description: newProfileDesc.value.trim() || undefined,
      scope: 'global',
      roleBindings,
      policies: DEFAULT_TEAM_POLICIES,
    })
    isCreateModalOpen.value = false
  } catch (err: unknown) {
    createError.value = err instanceof Error ? err.message : '创建团队配置失败'
  }
}

async function handleDuplicateCurrent() {
  if (!activeProfile.value) return
  await teamStore.duplicateProfile(activeProfile.value.id)
}

function handleDeleteCurrent() {
  if (!activeProfile.value) return
  if (confirm(`确定要删除团队配置 "${activeProfile.value.name}" 吗？`)) {
    teamStore.deleteProfile(activeProfile.value.id)
  }
}

function handleExportCurrent() {
  if (!activeProfile.value) return
  const json = teamStore.exportProfile(activeProfile.value.id)
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `team-profile-${activeProfile.value.id}.json`
  a.click()
  URL.revokeObjectURL(url)
}

function handleOpenImport() {
  importJsonText.value = ''
  importError.value = null
  isImportModalOpen.value = true
}

async function handleConfirmImport() {
  if (!importJsonText.value.trim()) {
    importError.value = '请输入或粘贴 JSON 字符串'
    return
  }
  try {
    await teamStore.importProfile(importJsonText.value.trim())
    isImportModalOpen.value = false
  } catch (err: unknown) {
    importError.value = err instanceof Error ? err.message : '导入失败，请检查 JSON 格式'
  }
}

function handlePrimaryAgentChange(roleId: string, event: Event) {
  const target = event.target as HTMLSelectElement
  if (!activeProfile.value) return
  teamStore.updateRoleBinding(activeProfile.value.id, roleId, {
    primaryAgentId: target.value,
  })
}

function handleAddFallbackAgent(roleId: string, event: Event) {
  const target = event.target as HTMLSelectElement
  const agentId = target.value
  if (!agentId || !activeProfile.value) return

  const binding = activeProfile.value.roleBindings[roleId]
  if (binding && !binding.fallbackAgentIds.includes(agentId)) {
    teamStore.updateRoleBinding(activeProfile.value.id, roleId, {
      fallbackAgentIds: [...binding.fallbackAgentIds, agentId],
    })
  }
  target.value = ''
}

function handleRemoveFallbackAgent(roleId: string, agentId: string) {
  if (!activeProfile.value) return
  const binding = activeProfile.value.roleBindings[roleId]
  if (binding) {
    teamStore.updateRoleBinding(activeProfile.value.id, roleId, {
      fallbackAgentIds: binding.fallbackAgentIds.filter((id) => id !== agentId),
    })
  }
}

function getAgentDisplayName(agentId: string): string {
  if (!agentId) return '未指定'
  const agent = agentStore.agents.find((a) => a.id === agentId)
  return agent ? `${agent.displayName} (${agent.adapterId})` : agentId
}

// 6-value ResolveSource mapping with distinct visual representation
function getResolveSourceMeta(source: ResolveSource): {
  label: string
  description: string
  variant: 'primary' | 'secondary' | 'success' | 'warning' | 'danger' | 'neutral'
  badgeClass: string
} {
  switch (source) {
    case 'task_override':
      return {
        label: '单次任务指定',
        description: '任务启动时显式指定的临时覆盖',
        variant: 'primary',
        badgeClass: 'bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800',
      }
    case 'workspace_profile':
      return {
        label: '项目配置绑定',
        description: '当前工作区专属配置中指定',
        variant: 'primary',
        badgeClass: 'bg-cyan-50 dark:bg-cyan-950/60 text-cyan-700 dark:text-cyan-300 border-cyan-200 dark:border-cyan-800',
      }
    case 'global_profile':
      return {
        label: '全局团队配置',
        description: '默认全局 Team Profile 首选设置',
        variant: 'secondary',
        badgeClass: 'bg-purple-50 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-800',
      }
    case 'capability_match':
      return {
        label: '动态能力匹配',
        description: '根据声明硬能力自动选定最优就绪 Agent',
        variant: 'success',
        badgeClass: 'bg-teal-50 dark:bg-teal-950/60 text-teal-700 dark:text-teal-300 border-teal-200 dark:border-teal-800',
      }
    case 'fallback':
      return {
        label: '备用链故障降级',
        description: '首选离线或未登录，命中备选 Agent',
        variant: 'warning',
        badgeClass: 'bg-amber-100 dark:bg-amber-950/80 text-amber-800 dark:text-amber-200 border-amber-300 dark:border-amber-700 font-semibold ring-1 ring-amber-400/40',
      }
    case 'manual':
      return {
        label: '等待人工决策',
        description: '无可替代实例，暂停并提请用户手动干预',
        variant: 'danger',
        badgeClass: 'bg-rose-100 dark:bg-rose-950/80 text-rose-800 dark:text-rose-200 border-rose-300 dark:border-rose-700 font-semibold ring-1 ring-rose-400/40 animate-pulse',
      }
    default:
      return {
        label: source,
        description: '未知来源',
        variant: 'neutral',
        badgeClass: '',
      }
  }
}
</script>

<template>
  <div class="p-6 space-y-6 max-w-7xl mx-auto select-none">
    <!-- Top Header -->
    <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
      <div>
        <h2 class="text-base font-bold text-content-primary">团队配置 (Team Profiles)</h2>
        <p class="text-xs text-content-muted">
          解耦任务角色与物理 Agent 厂商，定义首选/备用链降级机制与能力权限约束
        </p>
      </div>

      <div class="flex items-center gap-2 flex-wrap">
        <HqButton size="sm" variant="secondary" @click="handleOpenImport">
          <template #icon>
            <Upload class="w-3.5 h-3.5" />
          </template>
          导入配置
        </HqButton>
        <HqButton size="sm" variant="primary" @click="handleOpenCreate">
          <template #icon>
            <Plus class="w-3.5 h-3.5" />
          </template>
          新建团队
        </HqButton>
      </div>
    </div>

    <!-- 4 States Handling -->
    <OfflineState
      v-if="appStore.isOffline"
      description="Local Hub 当前处于离线状态，团队配置与实时路由解析暂时无法同步"
      @retry="teamStore.fetchProfiles"
    />

    <HqErrorState
      v-else-if="teamStore.error"
      :error="teamStore.error"
      @retry="teamStore.fetchProfiles"
    />

    <LoadingState
      v-else-if="teamStore.isLoading && teamStore.profiles.length === 0"
      description="正在加载团队配置与 Agent 能力矩阵..."
    />

    <HqEmptyState
      v-else-if="teamStore.profiles.length === 0"
      title="暂无团队配置"
      description="创建第一个 Team Profile，将系统角色与本机 Agent 灵活分配"
      action-text="新建团队配置"
      @action="handleOpenCreate"
    />

    <!-- 3-Column Studio Layout -->
    <div v-else class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
      <!-- Left Column: Profile List (3 cols) -->
      <div class="lg:col-span-3 space-y-3">
        <div class="flex items-center justify-between px-1">
          <span class="text-xs font-semibold text-content-secondary uppercase tracking-wider">团队配置方案</span>
          <span class="text-2xs text-content-muted">{{ teamStore.profiles.length }} 个</span>
        </div>

        <div class="space-y-2">
          <div
            v-for="profile in teamStore.profiles"
            :key="profile.id"
            class="p-3.5 rounded-xl border cursor-pointer transition-all duration-150 relative"
            :class="teamStore.activeProfileId === profile.id
              ? 'bg-primary-50/50 dark:bg-primary-950/20 border-primary-500 shadow-sm'
              : 'bg-surface-card border-border-subtle hover:border-border-default'"
            @click="handleSelectProfile(profile.id)"
          >
            <div class="flex items-start justify-between gap-2">
              <span class="text-xs font-bold text-content-primary truncate">{{ profile.name }}</span>
              <HqBadge v-if="profile.isDefault" variant="primary" size="sm">默认</HqBadge>
            </div>

            <p class="text-2xs text-content-muted line-clamp-2 mt-1">
              {{ profile.description || '无附加描述' }}
            </p>

            <div class="flex items-center justify-between mt-3 pt-2 border-t border-border-subtle/60 text-2xs text-content-muted">
              <span>{{ profile.scope === 'global' ? '全局配置' : '工作区专属' }}</span>
              <span>{{ Object.keys(profile.roleBindings || {}).length }} 角色</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Center Column: Role Mapping & Policy Studio (5 cols) -->
      <div v-if="activeProfile" class="lg:col-span-5 space-y-4">
        <!-- Active Profile Header Card -->
        <div class="p-4 rounded-xl bg-surface-card border border-border-subtle space-y-3">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="text-sm font-bold text-content-primary">{{ activeProfile.name }}</h3>
              <p class="text-2xs text-content-muted">{{ activeProfile.description || '暂无描述' }}</p>
            </div>
            <div class="flex items-center gap-1.5">
              <HqButton
                v-if="!activeProfile.isDefault"
                size="sm"
                variant="secondary"
                title="设为默认团队配置"
                @click="teamStore.setDefaultProfile(activeProfile.id)"
              >
                <Star class="w-3 h-3 text-amber-500" />
              </HqButton>
              <HqButton
                size="sm"
                variant="secondary"
                title="创建此配置的副本"
                @click="handleDuplicateCurrent"
              >
                <Copy class="w-3 h-3" />
              </HqButton>
              <HqButton
                size="sm"
                variant="secondary"
                title="导出为 JSON 文件"
                @click="handleExportCurrent"
              >
                <Download class="w-3 h-3" />
              </HqButton>
              <HqButton
                size="sm"
                variant="ghost"
                class="text-rose-600 hover:text-rose-700"
                title="删除此配置"
                @click="handleDeleteCurrent"
              >
                <Trash2 class="w-3 h-3" />
              </HqButton>
            </div>
          </div>
        </div>

        <!-- Role Configuration List -->
        <div class="space-y-3">
          <div class="flex items-center justify-between px-1">
            <span class="text-xs font-semibold text-content-secondary uppercase tracking-wider">角色分配与备用链</span>
            <span class="text-2xs text-content-muted">按执行优先级依次尝试</span>
          </div>

          <div
            v-for="role in STANDARD_ROLES"
            :key="role.roleId"
            class="p-4 rounded-xl bg-surface-card border border-border-subtle space-y-3"
          >
            <!-- Role Info -->
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="text-xs font-bold text-content-primary">{{ role.roleName }}</span>
                <span class="text-2xs font-mono text-content-muted bg-surface-raised px-1.5 py-0.5 rounded border border-border-subtle">
                  {{ role.roleId }}
                </span>
              </div>
              <span class="text-2xs text-content-muted">{{ role.description }}</span>
            </div>

            <!-- Primary Agent Selector -->
            <div class="space-y-1">
              <label class="text-2xs font-medium text-content-secondary">首选 Agent (Primary)</label>
              <select
                class="hq-form-control w-full text-xs rounded-lg border border-border-default bg-surface-raised px-3 py-1.5 text-content-primary focus:outline-none focus:ring-1 focus:ring-primary-500"
                :value="activeProfile.roleBindings[role.roleId]?.primaryAgentId || ''"
                @change="handlePrimaryAgentChange(role.roleId, $event)"
              >
                <option value="">未指定 (由 Hub 动态能力匹配)</option>
                <option
                  v-for="agent in agentStore.agents"
                  :key="agent.id"
                  :value="agent.id"
                >
                  {{ agent.displayName }} [{{ agent.adapterId }}] - {{ agent.status === 'ready' ? '就绪' : agent.status }}
                </option>
              </select>
            </div>

            <!-- Fallback Chain -->
            <div class="space-y-1.5 pt-1">
              <label class="text-2xs font-medium text-content-secondary flex items-center justify-between">
                <span>备用链 (Fallback Chain)</span>
                <span class="text-content-muted font-normal">首选不可用时按序触发</span>
              </label>

              <!-- Current Fallbacks Tags -->
              <div class="flex items-center gap-1.5 flex-wrap">
                <div
                  v-for="fbId in (activeProfile.roleBindings[role.roleId]?.fallbackAgentIds || [])"
                  :key="fbId"
                  class="flex items-center gap-1 px-2 py-0.5 rounded bg-surface-raised border border-border-subtle text-2xs text-content-secondary"
                >
                  <span>{{ getAgentDisplayName(fbId) }}</span>
                  <button
                    class="text-content-muted hover:text-rose-600 transition-colors"
                    title="移除备用"
                    @click="handleRemoveFallbackAgent(role.roleId, fbId)"
                  >
                    ×
                  </button>
                </div>

                <!-- Add Fallback Select -->
                <select
                  class="hq-form-control text-2xs rounded border border-dashed border-border-default bg-transparent px-2 py-0.5 text-content-muted focus:outline-none"
                  @change="handleAddFallbackAgent(role.roleId, $event)"
                >
                  <option value="">+ 添加备用 Agent</option>
                  <option
                    v-for="agent in agentStore.agents"
                    :key="agent.id"
                    :value="agent.id"
                  >
                    {{ agent.displayName }} ({{ agent.adapterId }})
                  </option>
                </select>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right Column: Real-time Route Resolution Preview (4 cols) -->
      <div class="lg:col-span-4 space-y-4">
        <div class="p-4 rounded-xl bg-surface-card border border-border-subtle space-y-4 sticky top-6">
          <div class="flex items-center justify-between pb-3 border-b border-border-subtle">
            <div class="flex items-center gap-2">
              <Sliders class="w-4 h-4 text-primary-600" />
              <span class="text-xs font-bold text-content-primary">路由解析结果预览</span>
            </div>
            <HqButton
              size="sm"
              variant="ghost"
              :loading="teamStore.isResolving"
              title="重新计算路由映射"
              @click="teamStore.resolveProfile(activeProfile?.id)"
            >
              <RefreshCw class="w-3 h-3" :class="teamStore.isResolving ? 'animate-spin' : ''" />
            </HqButton>
          </div>

          <p class="text-2xs text-content-muted leading-relaxed">
            展示当前 Agent 在线状态、硬能力约束与备用链模拟求值结果。
          </p>

          <!-- Capability Gaps Alert -->
          <div
            v-if="teamStore.resolvedTeam?.hasGaps"
            class="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 space-y-2"
          >
            <div class="flex items-center gap-1.5 text-2xs font-bold text-rose-700 dark:text-rose-300">
              <AlertTriangle class="w-3.5 h-3.5" />
              <span>发现 {{ teamStore.resolvedTeam.gaps.length }} 个角色能力缺口</span>
            </div>
            <div class="space-y-1.5">
              <div
                v-for="gap in teamStore.resolvedTeam.gaps"
                :key="gap.roleId"
                class="text-2xs text-rose-600 dark:text-rose-400 pl-4 border-l-2 border-rose-300 dark:border-rose-700"
              >
                <span class="font-semibold">{{ gap.roleId }}:</span> {{ gap.reason }}
              </div>
            </div>
          </div>

          <div
            v-else-if="teamStore.resolvedTeam"
            class="p-2.5 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900 flex items-center gap-2 text-2xs text-emerald-700 dark:text-emerald-300"
          >
            <CheckCircle2 class="w-3.5 h-3.5 text-emerald-600" />
            <span>所有角色均已满足可用性与能力约束</span>
          </div>

          <!-- Role Resolution List -->
          <div class="space-y-2.5 pt-1">
            <div
              v-for="(item, roleKey) in (teamStore.resolvedTeam?.resolvedRoles || {})"
              :key="roleKey"
              class="p-3 rounded-lg bg-surface-raised border border-border-subtle space-y-2"
            >
              <div class="flex items-center justify-between">
                <span class="text-xs font-bold text-content-primary">{{ item.roleId }}</span>
                <!-- 6-value ResolveSource Badge -->
                <span
                  class="text-2xs px-2 py-0.5 rounded-full border font-medium inline-flex items-center gap-1"
                  :class="getResolveSourceMeta(item.resolveSource).badgeClass"
                  :title="getResolveSourceMeta(item.resolveSource).description"
                >
                  <AlertTriangle v-if="item.resolveSource === 'fallback'" class="w-3 h-3 text-amber-600 dark:text-amber-300" />
                  <HelpCircle v-else-if="item.resolveSource === 'manual'" class="w-3 h-3 text-rose-600 dark:text-rose-300" />
                  {{ getResolveSourceMeta(item.resolveSource).label }}
                </span>
              </div>

              <!-- Target Agent -->
              <div class="flex items-center justify-between text-2xs">
                <span class="text-content-muted">解析命中:</span>
                <span class="font-mono font-medium text-content-primary">{{ item.resolvedAgentName || item.resolvedAgentId }}</span>
              </div>

              <!-- Fallback Warning Box -->
              <div
                v-if="item.isFallback && item.fallbackReason"
                class="p-2 rounded bg-amber-50/80 dark:bg-amber-950/50 border border-amber-200 dark:border-amber-800 text-2xs text-amber-800 dark:text-amber-200"
              >
                <span class="font-semibold">降级原因:</span> {{ item.fallbackReason }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create Team Modal -->
    <HqDialog
      :open="isCreateModalOpen"
      title="新建团队配置方案"
      description="为特定任务场景或工作区创建多 Agent 协作规则"
      @close="isCreateModalOpen = false"
    >
      <div class="space-y-4 py-2">
        <div class="space-y-1.5">
          <label class="text-xs font-semibold text-content-primary">团队名称</label>
          <HqInput
            v-model="newProfileName"
            placeholder="例如: 极速全栈双 Agent 团队"
          />
        </div>

        <div class="space-y-1.5">
          <label class="text-xs font-semibold text-content-primary">方案说明 (可选)</label>
          <HqInput
            v-model="newProfileDesc"
            placeholder="例如: Claude 架构 + Codex 实现与自动化测试"
          />
        </div>

        <p v-if="createError" class="text-2xs text-rose-600 dark:text-rose-400">
          {{ createError }}
        </p>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-2">
          <HqButton size="sm" variant="secondary" @click="isCreateModalOpen = false">
            取消
          </HqButton>
          <HqButton size="sm" variant="primary" @click="handleConfirmCreate">
            创建配置
          </HqButton>
        </div>
      </template>
    </HqDialog>

    <!-- Import Modal -->
    <HqDialog
      :open="isImportModalOpen"
      title="导入团队配置"
      description="粘贴导出的 Team Profile JSON 内容进行复用"
      @close="isImportModalOpen = false"
    >
      <div class="space-y-3 py-2">
        <textarea
          v-model="importJsonText"
          class="hq-form-control w-full h-48 text-xs font-mono rounded-lg border border-border-default bg-surface-raised p-3 text-content-primary focus:outline-none focus:ring-1 focus:ring-primary-500"
          placeholder="在此粘贴 JSON 文本..."
        />
        <p v-if="importError" class="text-2xs text-rose-600 dark:text-rose-400">
          {{ importError }}
        </p>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-2">
          <HqButton size="sm" variant="secondary" @click="isImportModalOpen = false">
            取消
          </HqButton>
          <HqButton size="sm" variant="primary" @click="handleConfirmImport">
            确认导入
          </HqButton>
        </div>
      </template>
    </HqDialog>
  </div>
</template>
