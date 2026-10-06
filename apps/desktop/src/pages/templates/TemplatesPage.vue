<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app.store'
import { useAgentStore } from '@/stores/agent.store'
import { useTeamStore, DEFAULT_TEAM_POLICIES } from '@/stores/team.store'
import type { CapabilityId } from '@hqagent/protocol'
import {
  LayoutTemplate,
  CheckCircle2,
  Zap,
  Search,
} from 'lucide-vue-next'
import {
  HqButton,
  HqBadge,
  HqDialog,
  LoadingState,
  HqEmptyState,
  HqErrorState,
  OfflineState,
} from '@/shared/ui'

const router = useRouter()
const appStore = useAppStore()
const agentStore = useAgentStore()
const teamStore = useTeamStore()

export interface TemplateItem {
  id: string
  name: string
  category: 'dev' | 'review' | 'prototype' | 'refactor'
  categoryLabel: string
  description: string
  requiredRoles: Array<{ roleId: string; roleName: string }>
  requiredCapabilities: CapabilityId[]
  recommendedAgents: string[]
}

const BUILTIN_TEMPLATES: TemplateItem[] = [
  {
    id: 'tpl_standard_fullstack',
    name: '标准全栈协作团队',
    category: 'dev',
    categoryLabel: '开发协作',
    description: '系统架构分析 + 前端与全栈功能实现 + 自动化测试与审查闭环，适合中大型需求交付。',
    requiredRoles: [
      { roleId: 'orchestrator', roleName: '总控调度' },
      { roleId: 'architect', roleName: '系统架构' },
      { roleId: 'frontend_implementer', roleName: '前端开发' },
      { roleId: 'general_implementer', roleName: '全栈实现' },
      { roleId: 'reviewer', roleName: '代码审查' },
      { roleId: 'tester', roleName: '自动化测试' },
    ],
    requiredCapabilities: ['coding', 'shell', 'git_worktree', 'session_resume'],
    recommendedAgents: ['Claude Code', 'Codex App Server', 'Gemini Antigravity'],
  },
  {
    id: 'tpl_code_review_security',
    name: '代码审查与质量把关',
    category: 'review',
    categoryLabel: '代码审查',
    description: '专注变更 Diff 分析、安全风险审计与测试用例覆盖度检验，不执行文件修改。',
    requiredRoles: [
      { roleId: 'architect', roleName: '系统架构' },
      { roleId: 'reviewer', roleName: '安全与规范审查' },
      { roleId: 'tester', roleName: '测试用例复核' },
    ],
    requiredCapabilities: ['review', 'git_worktree'],
    recommendedAgents: ['Claude Code'],
  },
  {
    id: 'tpl_rapid_prototype',
    name: '极速原型与敏捷构建',
    category: 'prototype',
    categoryLabel: '极速原型',
    description: '单或双 Agent 扁平化极简团队，跳过繁琐阶段性审批，实现极速迭代原型验证。',
    requiredRoles: [
      { roleId: 'orchestrator', roleName: '总控与架构' },
      { roleId: 'general_implementer', roleName: '极速全栈实现' },
    ],
    requiredCapabilities: ['coding', 'shell'],
    recommendedAgents: ['Codex App Server', 'Claude Code'],
  },
  {
    id: 'tpl_refactor_upgrade',
    name: '架构重构与平滑升级',
    category: 'refactor',
    categoryLabel: '运维重构',
    description: '专项用于框架迁移、接口重构与技术栈升迁，重点保证自动化回归与契约兼容。',
    requiredRoles: [
      { roleId: 'architect', roleName: '架构与契约设计' },
      { roleId: 'general_implementer', roleName: '重构实现' },
      { roleId: 'tester', roleName: '回归测试' },
    ],
    requiredCapabilities: ['coding', 'shell', 'git_worktree', 'session_resume'],
    recommendedAgents: ['Claude Code', 'Codex App Server'],
  },
]

const searchQuery = ref('')
const selectedCategory = ref<string>('all')

const isPreviewModalOpen = ref(false)
const activePreviewTemplate = ref<TemplateItem | null>(null)
const isApplying = ref(false)

onMounted(async () => {
  await Promise.all([
    agentStore.fetchAgents(),
    teamStore.fetchProfiles(),
  ])
})

const filteredTemplates = computed(() => {
  return BUILTIN_TEMPLATES.filter((tpl) => {
    const matchCat = selectedCategory.value === 'all' || tpl.category === selectedCategory.value
    const matchSearch =
      !searchQuery.value.trim() ||
      tpl.name.includes(searchQuery.value.trim()) ||
      tpl.description.includes(searchQuery.value.trim())
    return matchCat && matchSearch
  })
})

function getCompatibleAgentCount(requiredCaps: CapabilityId[]): number {
  return agentStore.agents.filter((a) => {
    if (a.status !== 'ready' && a.status !== 'busy') return false
    // If agent has capabilities list, check coverage
    if (!a.capabilities || a.capabilities.length === 0) return true
    return requiredCaps.every((c) => a.capabilities?.some((cap) => cap.id === c))
  }).length
}

function handleOpenPreview(template: TemplateItem) {
  activePreviewTemplate.value = template
  isPreviewModalOpen.value = true
}

async function handleApplyTemplate() {
  if (!activePreviewTemplate.value) return
  isApplying.value = true

  try {
    const tpl = activePreviewTemplate.value
    const defaultAgentId = agentStore.readyAgents[0]?.id || ''
    const roleBindings: Record<string, any> = {}

    tpl.requiredRoles.forEach((r) => {
      roleBindings[r.roleId] = {
        roleId: r.roleId,
        roleName: r.roleName,
        primaryAgentId: defaultAgentId,
        fallbackAgentIds: [],
      }
    })

    const saved = await teamStore.saveProfile({
      name: `${tpl.name}方案`,
      description: tpl.description,
      scope: 'global',
      roleBindings,
      policies: DEFAULT_TEAM_POLICIES,
    })

    isPreviewModalOpen.value = false
    appStore.addLog({
      level: 'info',
      source: 'Templates',
      message: `已基于模板创建团队配置: ${saved.name}`,
    })
    router.push('/teams')
  } catch (err: unknown) {
    appStore.addLog({
      level: 'error',
      source: 'Templates',
      message: `应用模板失败: ${err instanceof Error ? err.message : '未知错误'}`,
    })
  } finally {
    isApplying.value = false
  }
}
</script>

<template>
  <div class="p-6 space-y-6 max-w-7xl mx-auto select-none">
    <!-- Header & Search -->
    <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
      <div>
        <h2 class="text-base font-bold text-content-primary">开箱模板库 (Templates)</h2>
        <p class="text-xs text-content-muted">
          选择经过工业界验证的多 Agent 协作与研发模式，快速一键应用为团队配置
        </p>
      </div>

      <!-- Search & Filters -->
      <div class="flex items-center gap-2 flex-wrap w-full sm:w-auto">
        <div class="relative flex-1 sm:w-64">
          <Search class="w-3.5 h-3.5 absolute left-3 top-2.5 text-content-muted" />
          <input
            v-model="searchQuery"
            placeholder="搜索预设模板..."
            class="hq-form-control w-full text-xs pl-8 pr-3 py-1.5 rounded-lg border border-border-subtle bg-muted/20 text-content-primary focus:outline-none focus:ring-1 focus:ring-primary-500"
          />
        </div>

        <div class="flex items-center gap-1 bg-muted/20 p-1 rounded-xl text-2xs">
          <button
            class="px-2.5 py-1 rounded-lg transition-colors cursor-pointer"
            :class="selectedCategory === 'all' ? 'bg-primary-500 text-white font-medium' : 'text-content-secondary hover:text-content-primary'"
            @click="selectedCategory = 'all'"
          >
            全部
          </button>
          <button
            class="px-2.5 py-1 rounded-lg transition-colors cursor-pointer"
            :class="selectedCategory === 'dev' ? 'bg-primary-500 text-white font-medium' : 'text-content-secondary hover:text-content-primary'"
            @click="selectedCategory = 'dev'"
          >
            开发协作
          </button>
          <button
            class="px-2.5 py-1 rounded-lg transition-colors cursor-pointer"
            :class="selectedCategory === 'review' ? 'bg-primary-500 text-white font-medium' : 'text-content-secondary hover:text-content-primary'"
            @click="selectedCategory = 'review'"
          >
            代码审查
          </button>
          <button
            class="px-2.5 py-1 rounded-lg transition-colors cursor-pointer"
            :class="selectedCategory === 'prototype' ? 'bg-primary-500 text-white font-medium' : 'text-content-secondary hover:text-content-primary'"
            @click="selectedCategory = 'prototype'"
          >
            极速原型
          </button>
        </div>
      </div>
    </div>

    <!-- 4 States Handling -->
    <OfflineState
      v-if="appStore.isOffline"
      description="Local Hub 当前处于离线状态，兼容 Agent 探测数据无法实时更新"
      @retry="agentStore.fetchAgents"
    />

    <HqErrorState
      v-else-if="agentStore.error"
      :error="agentStore.error"
      @retry="agentStore.fetchAgents"
    />

    <LoadingState
      v-else-if="agentStore.isLoading"
      description="正在评估模板硬能力与本地 Agent 适配度..."
    />

    <HqEmptyState
      v-else-if="filteredTemplates.length === 0"
      title="未找到匹配模板"
      description="尝试清除搜索关键词或切换分类筛选"
      action-text="查看全部模板"
      @action="selectedCategory = 'all'; searchQuery = ''"
    />

    <!-- Templates Grid -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div
        v-for="tpl in filteredTemplates"
        :key="tpl.id"
        class="p-5 rounded-xl bg-panel border border-border-subtle hover:border-border transition-all duration-200 flex flex-col justify-between space-y-4 shadow-2xs hover:shadow-xs"
      >
        <div class="space-y-3">
          <!-- Card Header -->
          <div class="flex items-start justify-between gap-3">
            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <span class="text-sm font-bold text-content-primary">{{ tpl.name }}</span>
                <HqBadge variant="neutral" size="sm">{{ tpl.categoryLabel }}</HqBadge>
              </div>
              <p class="text-2xs text-content-muted leading-relaxed">
                {{ tpl.description }}
              </p>
            </div>
            <div class="w-8 h-8 rounded-xl bg-primary/10 flex items-center justify-center text-primary flex-shrink-0">
              <LayoutTemplate class="w-4 h-4" />
            </div>
          </div>

          <!-- Roles required -->
          <div class="space-y-1.5 pt-2 border-t border-border-subtle">
            <span class="text-2xs font-semibold text-content-secondary">所需协作角色 ({{ tpl.requiredRoles.length }})</span>
            <div class="flex items-center gap-1.5 flex-wrap">
              <span
                v-for="role in tpl.requiredRoles"
                :key="role.roleId"
                class="px-2 py-0.5 rounded-md bg-muted/60 text-2xs text-content-secondary"
              >
                {{ role.roleName }}
              </span>
            </div>
          </div>

          <!-- Compatibility Metric -->
          <div class="flex items-center justify-between text-2xs text-content-secondary pt-1">
            <span class="text-content-muted">本机兼容 Agent 实例:</span>
            <span class="font-semibold text-emerald-600 dark:text-emerald-400">
              {{ getCompatibleAgentCount(tpl.requiredCapabilities) }} 个已就绪
            </span>
          </div>
        </div>

        <!-- Action Button -->
        <div class="pt-3 border-t border-border-subtle flex items-center justify-between">
          <div class="text-2xs text-content-muted flex items-center gap-1">
            <CheckCircle2 class="w-3.5 h-3.5 text-emerald-500" />
            <span>支持按工作区细化覆盖</span>
          </div>
          <HqButton size="sm" variant="primary" @click="handleOpenPreview(tpl)">
            <template #icon>
              <Zap class="w-3 h-3" />
            </template>
            应用此模板
          </HqButton>
        </div>
      </div>
    </div>

    <!-- Template Application Preview Modal -->
    <HqDialog
      :open="isPreviewModalOpen"
      title="应用模板预览与缺口评估"
      description="在生成团队配置前预检查本地 Agent 匹配度与权限声明"
      @close="isPreviewModalOpen = false"
    >
      <div v-if="activePreviewTemplate" class="space-y-4 py-2">
        <div class="p-3 rounded-xl bg-muted/20 space-y-1">
          <div class="text-xs font-bold text-content-primary">{{ activePreviewTemplate.name }}</div>
          <p class="text-2xs text-content-muted">{{ activePreviewTemplate.description }}</p>
        </div>

        <!-- Role Mapping Plan -->
        <div class="space-y-2">
          <span class="text-xs font-semibold text-content-primary">生成角色分配方案</span>
          <div class="space-y-1.5 max-h-48 overflow-y-auto">
            <div
              v-for="role in activePreviewTemplate.requiredRoles"
              :key="role.roleId"
              class="flex items-center justify-between p-2.5 rounded-xl bg-muted/20 text-2xs"
            >
              <span class="font-bold text-content-primary">{{ role.roleName }}</span>
              <span class="text-content-muted">自动分配首选就绪 Agent</span>
            </div>
          </div>
        </div>

        <div class="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200/60 dark:border-emerald-900/60 flex items-center gap-2 text-2xs text-emerald-700 dark:text-emerald-300">
          <CheckCircle2 class="w-4 h-4 text-emerald-600" />
          <span>应用后将在「团队配置」中生成新方案，可进一步自定义微调</span>
        </div>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-2">
          <HqButton size="sm" variant="secondary" @click="isPreviewModalOpen = false">
            取消
          </HqButton>
          <HqButton size="sm" variant="primary" :loading="isApplying" @click="handleApplyTemplate">
            确认生成配置
          </HqButton>
        </div>
      </template>
    </HqDialog>
  </div>
</template>
