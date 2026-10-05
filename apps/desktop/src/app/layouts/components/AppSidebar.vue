<script setup lang="ts">
import { computed, inject, ref, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app.store'
import { useWorkspaceStore } from '@/stores/workspace.store'
import type { FeatureAvailability } from '@hqagent/protocol'
import type { MockScenarioId } from '@/mocks/scenarios'
import {
  LayoutDashboard,
  FolderGit2,
  Users,
  CheckSquare,
  MessageSquare,
  Bot,
  Layers,
  Download,
  Settings,
  Sliders,
  ChevronLeft,
  ChevronRight,
  Lock,
  GitBranch,
  Radio,
  ShieldAlert,
  Smartphone,
  X,
} from 'lucide-vue-next'
import { HqBadge, HqTooltip } from '@/shared/ui'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const workspaceStore = useWorkspaceStore()
const isMobileNavOpen = inject<Ref<boolean>>('isMobileNavOpen', ref(false))
const closeMobileNav = inject<() => void>('closeMobileNav', () => {})

interface NavItem {
  id: string
  label: string
  path: string
  icon: any
  featureKey?: keyof FeatureAvailability
  badge?: () => string | number | null
  badgeVariant?: 'neutral' | 'success' | 'warning' | 'danger'
}

const hiddenLegacyItemIds = new Set([
  'overview',
  'workspaces',
  'teams',
  'tasks',
  'approvals',
  'sessions',
  'templates',
  'updates',
])

const allNavItems = computed<NavItem[]>(() => [
  {
    id: 'chat',
    label: '角色对话',
    path: '/chat',
    icon: MessageSquare,
  },
  {
    id: 'agents',
    label: 'Agent 管理',
    path: '/agents',
    icon: Bot,
    featureKey: 'agents',
    badge: () => {
      const issues = appStore.bootstrap?.agents.issues || 0
      return issues > 0 ? `${issues} 异常` : (appStore.bootstrap?.agents.ready ?? null)
    },
    badgeVariant: (appStore.bootstrap?.agents.issues || 0) > 0 ? 'danger' : 'success',
  },
  {
    id: 'scenes',
    label: '场景配置',
    path: '/scenes',
    icon: Sliders,
  },
  {
    id: 'overview',
    label: '总览',
    path: '/overview',
    icon: LayoutDashboard,
  },
  {
    id: 'workspaces',
    label: '工作区',
    path: '/workspaces',
    icon: FolderGit2,
    badge: () => workspaceStore.workspaces.length || null,
  },
  {
    id: 'teams',
    label: '团队配置',
    path: '/teams',
    icon: Users,
    featureKey: 'teamProfiles',
  },
  {
    id: 'tasks',
    label: '任务中心',
    path: '/tasks',
    icon: CheckSquare,
    featureKey: 'tasks',
    badge: () => appStore.bootstrap?.activeTasksCount || null,
    badgeVariant: 'warning',
  },
  {
    id: 'approvals',
    label: '安全审批',
    path: '/approvals',
    icon: ShieldAlert,
    featureKey: 'approvals',
    badge: () => appStore.bootstrap?.pendingApprovalsCount || null,
    badgeVariant: 'warning',
  },
  {
    id: 'sessions',
    label: '会话记录',
    path: '/sessions',
    icon: MessageSquare,
    featureKey: 'sessions',
  },
  {
    id: 'templates',
    label: '任务模板',
    path: '/templates',
    icon: Layers,
  },
  {
    id: 'updates',
    label: '软件更新',
    path: '/updates',
    icon: Download,
    featureKey: 'updates',
  },
  {
    id: 'remote-link',
    label: '连接手机',
    path: '/remote-link',
    icon: Smartphone,
  },
  {
    id: 'settings',
    label: '系统设置',
    path: '/settings',
    icon: Settings,
  },
])

const navItems = computed<NavItem[]>(() =>
  allNavItems.value.filter((item) => !hiddenLegacyItemIds.has(item.id))
)

const isDev = import.meta.env.DEV

const scenarios: { id: MockScenarioId; name: string }[] = [
  { id: 'happy-path', name: '全链路就绪 (Happy Path)' },
  { id: 'first-run-no-agent', name: '首次运行无 Agent' },
  { id: 'task-running', name: '协作执行中 (Running)' },
  { id: 'task-waiting-approval', name: '等待安全审批 (Approval)' },
  { id: 'update-downloading', name: 'OTA 升级中 (Update)' },
  { id: 'hub-disconnected', name: 'Local Hub 断开连接' },
]

function handleNavClick(item: NavItem) {
  if (item.featureKey && !appStore.isFeatureAvailable(item.featureKey)) {
    return
  }
  closeMobileNav()
  router.push(item.path)
}

function onScenarioChange(event: Event) {
  const target = event.target as HTMLSelectElement
  appStore.setScenario(target.value as MockScenarioId)
}
</script>

<template>
  <aside
    class="flex flex-col bg-sidebar border-r border-border-subtle select-none transition-all duration-200 z-50 md:z-auto"
    :class="[
      appStore.sidebarCollapsed ? 'w-16' : 'w-[220px]',
      'fixed inset-y-0 left-0 md:static',
      isMobileNavOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full md:translate-x-0',
    ]"
  >
    <!-- Brand / Header -->
    <div class="h-14 flex items-center px-4 gap-3 border-b border-border-subtle shrink-0">
      <div class="w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center text-white font-bold shrink-0 shadow-sm">
        HQ
      </div>
      <div v-if="!appStore.sidebarCollapsed" class="flex flex-col overflow-hidden">
        <span class="font-bold text-sm text-content-primary leading-tight truncate">HQAgent-Hub</span>
        <span class="text-2xs text-content-muted leading-tight truncate">AI 团队控制中心</span>
      </div>

      <!-- Mobile Close Button -->
      <button
        type="button"
        class="md:hidden ml-auto min-w-[44px] min-h-[44px] p-2 text-content-muted hover:text-content-primary rounded-lg flex items-center justify-center cursor-pointer"
        title="关闭菜单"
        aria-label="关闭菜单"
        @click="closeMobileNav()"
      >
        <X class="w-4 h-4" />
      </button>
    </div>

    <!-- Active Workspace Quick Switcher -->
    <div v-if="!appStore.sidebarCollapsed" class="p-2 border-b border-border-subtle bg-panel/30 shrink-0">
      <div class="px-2 py-1.5 rounded-md bg-panel border border-border-subtle flex flex-col gap-1">
        <div class="flex items-center justify-between text-2xs text-content-muted gap-2">
          <span class="shrink-0 whitespace-nowrap">当前工作区</span>
          <span class="flex items-center gap-1 text-primary-600 font-mono truncate min-w-0" :title="workspaceStore.currentWorkspace?.branch || 'main'">
            <GitBranch class="w-3 h-3 shrink-0" />
            <span class="truncate">{{ workspaceStore.currentWorkspace?.branch || 'main' }}</span>
          </span>
        </div>
        <div class="text-xs font-semibold text-content-primary truncate" :title="workspaceStore.currentWorkspace?.path">
          {{ workspaceStore.currentWorkspace?.name || 'HQAgent-Hub' }}
        </div>
      </div>
    </div>

    <!-- Main Navigation List -->
    <nav class="flex-1 overflow-y-auto py-2 px-2 space-y-1">
      <template v-for="item in navItems" :key="item.id">
        <!-- Disabled by Feature Gate -->
        <div
          v-if="item.featureKey && !appStore.isFeatureAvailable(item.featureKey)"
          class="relative group"
        >
          <HqTooltip :content="appStore.getFeatureReason(item.featureKey) || '该功能当前不可用'" placement="right">
            <div
              class="flex items-center gap-3 px-3 py-2 rounded-md text-content-disabled cursor-not-allowed opacity-60 bg-transparent"
              :class="appStore.sidebarCollapsed ? 'justify-center' : ''"
            >
              <component :is="item.icon" class="w-4 h-4 shrink-0" />
              <span v-if="!appStore.sidebarCollapsed" class="text-xs flex-1 truncate">{{ item.label }}</span>
              <Lock v-if="!appStore.sidebarCollapsed" class="w-3 h-3 text-content-disabled shrink-0" />
            </div>
          </HqTooltip>
        </div>

        <!-- Normal Nav Item -->
        <button
          v-else
          type="button"
          @click="handleNavClick(item)"
          class="w-full flex items-center gap-3 px-3 py-2 rounded-md text-xs font-medium transition-colors text-left"
          :class="[
            route.path.startsWith(item.path)
              ? 'bg-primary-50 text-primary-700 dark:bg-primary-950/40 dark:text-primary-300 shadow-2xs'
              : 'text-content-secondary hover:bg-panel hover:text-content-primary',
            appStore.sidebarCollapsed ? 'justify-center' : '',
          ]"
        >
          <component :is="item.icon" class="w-4 h-4 shrink-0" />
          <span v-if="!appStore.sidebarCollapsed" class="flex-1 truncate">{{ item.label }}</span>
          <HqBadge
            v-if="!appStore.sidebarCollapsed && item.badge && item.badge() !== null"
            :variant="item.badgeVariant || 'neutral'"
            size="sm"
          >
            {{ item.badge() }}
          </HqBadge>
        </button>
      </template>

      <!-- Dev: UI Kit -->
      <div v-if="isDev" class="pt-2 mt-2 border-t border-border-subtle">
        <button
          type="button"
          @click="router.push('/dev/ui-kit')"
          class="w-full flex items-center gap-3 px-3 py-2 rounded-md text-xs font-medium text-content-muted hover:text-primary-600 hover:bg-panel transition-colors"
          :class="[
            route.path === '/dev/ui-kit' ? 'bg-panel text-primary-600' : '',
            appStore.sidebarCollapsed ? 'justify-center' : '',
          ]"
        >
          <Sliders class="w-4 h-4 shrink-0 text-amber-500" />
          <span v-if="!appStore.sidebarCollapsed" class="flex-1 truncate">UI Kit 预览</span>
        </button>
      </div>
    </nav>

    <!-- Dev Mock Scenario Switcher (Available in Mock Gateway mode) -->
    <div v-if="appStore.isMock && !appStore.sidebarCollapsed" class="p-2 border-t border-border-subtle bg-panel/20 shrink-0">
      <label class="block text-2xs font-semibold text-content-muted mb-1 flex items-center gap-1">
        <Radio class="w-3 h-3 text-amber-500" />
        Mock 场景切换
      </label>
      <select
        :value="appStore.activeScenario"
        @change="onScenarioChange"
        class="hq-form-control w-full text-2xs bg-panel border border-border-default rounded px-2 py-1 text-content-primary focus:outline-none focus:ring-1 focus:ring-primary-500"
      >
        <option v-for="s in scenarios" :key="s.id" :value="s.id">
          {{ s.name }}
        </option>
      </select>
    </div>

    <!-- Collapse Toggle Footer -->
    <div class="h-10 border-t border-border-subtle flex items-center justify-end px-3 shrink-0">
      <button
        type="button"
        @click="appStore.toggleSidebar"
        class="p-1 rounded text-content-muted hover:text-content-primary hover:bg-panel transition-colors"
        :title="appStore.sidebarCollapsed ? '展开导航' : '收起导航'"
      >
        <ChevronRight v-if="appStore.sidebarCollapsed" class="w-4 h-4" />
        <ChevronLeft v-else class="w-4 h-4" />
      </button>
    </div>
  </aside>
</template>
