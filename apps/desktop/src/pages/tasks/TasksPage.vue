<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app.store'
import { useTaskStore } from '@/stores/task.store'
import { useWorkspaceStore } from '@/stores/workspace.store'
import { useTeamStore } from '@/stores/team.store'
import type { TaskStatus, CreateTaskInput } from '@hqagent/protocol'
import {
  CheckSquare,
  Plus,
  Search,
  FolderGit2,
  Clock,
  UserCheck,
  AlertCircle,
  Play,
  XCircle,
  Pause,
  AlertTriangle,
  ArrowRight,
  ShieldAlert,
} from 'lucide-vue-next'
import {
  HqButton,
  HqBadge,
  HqInput,
  HqTextarea,
  HqDialog,
  HqTooltip,
  LoadingState,
  HqEmptyState,
  HqErrorState,
  OfflineState,
} from '@/shared/ui'

const router = useRouter()
const appStore = useAppStore()
const taskStore = useTaskStore()
const workspaceStore = useWorkspaceStore()
const teamStore = useTeamStore()

// Create Task Modal state
const isCreateModalOpen = ref(false)
const formObjective = ref('')
const formWorkspaceId = ref('')
const formProfileId = ref('')
const formAllowedPaths = ref('')
const formAcceptance = ref('')
const formError = ref<string | null>(null)

onMounted(async () => {
  await Promise.all([
    taskStore.fetchTasks(),
    workspaceStore.fetchWorkspaces(),
    teamStore.fetchProfiles(),
  ])
  if (workspaceStore.workspaces.length > 0 && !formWorkspaceId.value) {
    formWorkspaceId.value = workspaceStore.workspaces[0].id
  }
  if (teamStore.profiles.length > 0 && !formProfileId.value) {
    formProfileId.value = teamStore.defaultProfile?.id || teamStore.profiles[0].id
  }
})

const statusFilters: { label: string; value: TaskStatus | 'all'; count?: number }[] = [
  { label: '全部', value: 'all' },
  { label: '运行中', value: 'running' },
  { label: '等待审批', value: 'waiting_approval' },
  { label: '已完成', value: 'succeeded' },
  { label: '已失败', value: 'failed' },
  { label: '已取消', value: 'cancelled' },
]

function getStatusBadge(status: TaskStatus) {
  switch (status) {
    case 'running':
      return { label: '运行中', variant: 'primary' as const, icon: Play, class: 'animate-pulse' }
    case 'waiting_approval':
      return { label: '等待审批', variant: 'warning' as const, icon: ShieldAlert, class: 'bg-amber-100 text-amber-800 dark:bg-amber-950/80 dark:text-amber-200 border-amber-300' }
    case 'succeeded':
      return { label: '已完成', variant: 'success' as const, icon: CheckSquare, class: '' }
    case 'failed':
      return { label: '已失败', variant: 'danger' as const, icon: AlertCircle, class: '' }
    case 'cancelled':
      return { label: '已取消', variant: 'neutral' as const, icon: XCircle, class: '' }
    case 'paused':
      return { label: '节点间暂停', variant: 'warning' as const, icon: Pause, class: '' }
    case 'queued':
      return { label: '排队中', variant: 'info' as const, icon: Clock, class: '' }
    default:
      return { label: status, variant: 'neutral' as const, icon: Clock, class: '' }
  }
}

function openCreateModal() {
  formObjective.value = ''
  formAllowedPaths.value = ''
  formAcceptance.value = ''
  formError.value = null
  if (workspaceStore.workspaces.length > 0 && !formWorkspaceId.value) {
    formWorkspaceId.value = workspaceStore.workspaces[0].id
  }
  if (teamStore.profiles.length > 0 && !formProfileId.value) {
    formProfileId.value = teamStore.defaultProfile?.id || teamStore.profiles[0].id
  }
  isCreateModalOpen.value = true
}

async function handleCreateTask() {
  if (!formObjective.value.trim()) {
    formError.value = '请输入任务目标'
    return
  }
  if (!formWorkspaceId.value) {
    formError.value = '请选择工作区'
    return
  }

  const allowedPaths = formAllowedPaths.value
    ? formAllowedPaths.value.split('\n').map((s) => s.trim()).filter(Boolean)
    : undefined

  const acceptance = formAcceptance.value
    ? formAcceptance.value.split('\n').map((s) => s.trim()).filter(Boolean)
    : undefined

  const input: CreateTaskInput = {
    objective: formObjective.value.trim(),
    workspaceId: formWorkspaceId.value,
    profileId: formProfileId.value || undefined,
    allowedPaths,
    acceptance,
  }

  try {
    const newTask = await taskStore.createTask(input)
    isCreateModalOpen.value = false
    router.push(`/tasks/${newTask.id}`)
  } catch (err: unknown) {
    formError.value = err instanceof Error ? err.message : '创建任务失败'
  }
}

function navigateToTask(taskId: string) {
  router.push(`/tasks/${taskId}`)
}

function formatDuration(ms?: number) {
  if (!ms) return '-'
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return `${seconds}秒`
  const minutes = Math.floor(seconds / 60)
  const remSec = seconds % 60
  return `${minutes}分${remSec}秒`
}

const isCreateDisabled = computed(() => !appStore.isTaskCreationAllowed)
const createDisabledReason = computed(() => {
  if (appStore.hubGate === 'maintenance') return 'Local Hub 处于系统维护模式，新建任务暂时锁定'
  if (appStore.hubGate === 'feature_unavailable') return appStore.hubGateReason || '任务功能未开放'
  if (!appStore.isFeatureAvailable('tasks')) return appStore.getFeatureReason('tasks') || '任务模块暂不可用'
  return ''
})
</script>

<template>
  <div class="p-6 space-y-6 max-w-7xl mx-auto select-none">
    <!-- Top Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <div class="p-2 bg-primary/10 text-primary rounded-[var(--radius-md)]">
          <CheckSquare class="w-6 h-6" />
        </div>
        <div>
          <h1 class="text-xl font-bold text-text">任务中心</h1>
          <p class="text-sm text-text-muted">
            查看与管理多 Agent 协作流转、节点状态、产物与执行控制
          </p>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <HqTooltip :content="createDisabledReason" :disabled="!isCreateDisabled">
          <div>
            <HqButton
              variant="primary"
              :disabled="isCreateDisabled"
              @click="openCreateModal"
            >
              <Plus class="w-4 h-4 mr-1.5" />
              新建任务
            </HqButton>
          </div>
        </HqTooltip>
      </div>
    </div>

    <!-- Hub Gate Maintenance Alert -->
    <div
      v-if="appStore.hubGate"
      class="p-4 rounded-[var(--radius-md)] border flex items-start gap-3"
      :class="
        appStore.hubGate === 'maintenance'
          ? 'bg-amber-500/10 border-amber-500/30 text-amber-900 dark:text-amber-200'
          : 'bg-rose-500/10 border-rose-500/30 text-rose-900 dark:text-rose-200'
      "
    >
      <AlertTriangle class="w-5 h-5 shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" />
      <div>
        <h4 class="font-semibold text-sm">
          {{ appStore.hubGate === 'maintenance' ? '系统维护 Gate 保护中' : '功能限制' }}
        </h4>
        <p class="text-xs mt-0.5 opacity-90">
          {{ appStore.hubGateReason || 'Local Hub 正在进行系统维护，新任务派发已自动熔断。' }}
        </p>
      </div>
    </div>

    <!-- Filter Toolbar -->
    <div class="flex flex-wrap items-center justify-between gap-4 p-4 bg-panel rounded-[var(--radius-md)] border border-border">
      <!-- Status Tabs -->
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="tab in statusFilters"
          :key="tab.value"
          class="px-3 py-1.5 rounded-[var(--radius-sm)] text-xs font-medium transition-colors"
          :class="
            taskStore.filterStatus === tab.value
              ? 'bg-primary text-white shadow-xs'
              : 'text-text-muted hover:bg-hover hover:text-text'
          "
          @click="taskStore.filterStatus = tab.value"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- Search & Workspace Filter -->
      <div class="flex items-center gap-3 w-full sm:w-auto">
        <div class="relative flex-1 sm:w-64">
          <Search class="absolute left-3 top-2.5 w-4 h-4 text-text-muted" />
          <input
            v-model="taskStore.filterSearch"
            type="text"
            placeholder="搜索目标、ID 或 Agent..."
            class="hq-form-control w-full pl-9 pr-3 py-1.5 text-xs bg-surface border border-border rounded-[var(--radius-sm)] focus:outline-none focus:ring-1 focus:ring-primary text-text placeholder:text-text-muted"
          />
        </div>

        <select
          v-model="taskStore.filterWorkspaceId"
          class="hq-form-control px-3 py-1.5 text-xs bg-surface border border-border rounded-[var(--radius-sm)] text-text focus:outline-none focus:ring-1 focus:ring-primary"
        >
          <option value="">全部工作区</option>
          <option v-for="ws in workspaceStore.workspaces" :key="ws.id" :value="ws.id">
            {{ ws.name }}
          </option>
        </select>
      </div>
    </div>

    <!-- 4 Page States -->
    <OfflineState v-if="appStore.isOffline" @retry="taskStore.fetchTasks" />
    <LoadingState v-else-if="taskStore.isLoading" message="正在加载任务列表..." />
    <HqErrorState
      v-else-if="taskStore.error"
      title="获取任务列表失败"
      :message="taskStore.error"
      @retry="taskStore.fetchTasks"
    />
    <HqEmptyState
      v-else-if="taskStore.filteredTasks.length === 0"
      title="暂无相关任务"
      message="当前没有匹配筛选条件的任务，您可以发起一个新任务。"
    >
      <template #action>
        <HqButton
          v-if="!isCreateDisabled"
          variant="primary"
          size="sm"
          @click="openCreateModal"
        >
          <Plus class="w-4 h-4 mr-1.5" />
          立即创建任务
        </HqButton>
      </template>
    </HqEmptyState>

    <!-- Task Cards List -->
    <div v-else class="space-y-3">
      <div
        v-for="task in taskStore.filteredTasks"
        :key="task.id"
        class="p-4 bg-panel hover:bg-hover/50 rounded-[var(--radius-md)] border border-border transition-all cursor-pointer group shadow-xs hover:shadow-sm"
        @click="navigateToTask(task.id)"
      >
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <!-- Left Main Info -->
          <div class="space-y-1.5 flex-1 min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-mono text-xs text-text-muted font-medium">{{ task.id }}</span>
              <HqBadge
                :variant="getStatusBadge(task.status).variant"
                size="sm"
                :class="getStatusBadge(task.status).class"
                class="inline-flex items-center gap-1"
              >
                <component :is="getStatusBadge(task.status).icon" class="w-3 h-3 shrink-0" />
                <span>{{ getStatusBadge(task.status).label }}</span>
              </HqBadge>

              <span
                v-if="task.pendingApprovalId"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30 animate-pulse"
              >
                <ShieldAlert class="w-3 h-3" />
                待审批
              </span>
            </div>

            <h3 class="text-sm font-semibold text-text group-hover:text-primary transition-colors truncate">
              {{ task.objective }}
            </h3>

            <!-- Metadata Row -->
            <div class="flex flex-wrap items-center gap-4 text-xs text-text-muted">
              <span class="inline-flex items-center gap-1">
                <FolderGit2 class="w-3.5 h-3.5 shrink-0" />
                {{ task.workspaceName }}
              </span>
              <span>•</span>
              <span>团队: {{ task.profileName }}</span>
              <span v-if="task.currentAgent">•</span>
              <span v-if="task.currentAgent" class="inline-flex items-center gap-1 text-text">
                <UserCheck class="w-3.5 h-3.5 text-primary" />
                {{ task.currentAgent }} ({{ task.currentRole || '执行中' }})
              </span>
            </div>
          </div>

          <!-- Right Meta & Action -->
          <div class="flex items-center sm:flex-col sm:items-end justify-between gap-2 text-xs text-text-muted shrink-0">
            <div class="flex items-center gap-2">
              <Clock class="w-3.5 h-3.5" />
              <span>耗时: {{ formatDuration(task.durationMs) }}</span>
            </div>
            <div class="inline-flex items-center text-primary font-medium group-hover:translate-x-0.5 transition-transform">
              详情
              <ArrowRight class="w-3.5 h-3.5 ml-1" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create Task Dialog -->
    <HqDialog
      :open="isCreateModalOpen"
      title="新建协作任务"
      description="配置目标、工作区与团队配置，向 Local Hub 派发新任务"
      @close="isCreateModalOpen = false"
    >
      <div class="space-y-4 py-2 text-xs">
        <div>
          <label class="block font-medium text-text mb-1">
            任务目标与需求描述 <span class="text-danger">*</span>
          </label>
          <HqTextarea
            v-model="formObjective"
            :rows="3"
            placeholder="请详细描述该任务的目标，如：实现用户登录界面的双因子验证并增加单元测试..."
          />
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label class="block font-medium text-text mb-1">
              执行工作区 <span class="text-danger">*</span>
            </label>
            <select
              v-model="formWorkspaceId"
              class="hq-form-control w-full px-3 py-2 text-xs bg-surface border border-border rounded-[var(--radius-sm)] text-text focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option v-for="ws in workspaceStore.workspaces" :key="ws.id" :value="ws.id">
                {{ ws.name }} ({{ ws.path }})
              </option>
            </select>
          </div>

          <div>
            <label class="block font-medium text-text mb-1">团队配置 Profile</label>
            <select
              v-model="formProfileId"
              class="hq-form-control w-full px-3 py-2 text-xs bg-surface border border-border rounded-[var(--radius-sm)] text-text focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option v-for="p in teamStore.profiles" :key="p.id" :value="p.id">
                {{ p.name }} {{ p.isDefault ? '(默认)' : '' }}
              </option>
            </select>
          </div>
        </div>

        <div>
          <label class="block font-medium text-text mb-1">
            允许修改路径 (Allowed Paths，每行一个 glob 规则，缺省默认遵循角色权限)
          </label>
          <HqTextarea
            v-model="formAllowedPaths"
            :rows="2"
            placeholder="apps/desktop/src/**&#10;tests/**"
          />
        </div>

        <div>
          <label class="block font-medium text-text mb-1">
            验收验证命令 (Acceptance Commands，每行一条)
          </label>
          <HqInput
            v-model="formAcceptance"
            placeholder="pnpm test:unit"
          />
        </div>

        <div
          v-if="formError"
          class="p-2.5 rounded-[var(--radius-sm)] bg-danger/10 text-danger border border-danger/20 flex items-center gap-2"
        >
          <AlertCircle class="w-4 h-4 shrink-0" />
          <span>{{ formError }}</span>
        </div>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-2">
          <HqButton size="sm" variant="secondary" @click="isCreateModalOpen = false">
            取消
          </HqButton>
          <HqButton
            size="sm"
            variant="primary"
            :disabled="!formObjective.trim() || !formWorkspaceId || taskStore.isActionLoading"
            @click="handleCreateTask"
          >
            确认创建
          </HqButton>
        </div>
      </template>
    </HqDialog>
  </div>
</template>
