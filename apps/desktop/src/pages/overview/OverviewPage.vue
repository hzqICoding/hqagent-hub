<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app.store'
import { useAgentStore } from '@/stores/agent.store'
import { useWorkspaceStore } from '@/stores/workspace.store'
import { getUiGateway } from '@/shared/api'
import type { TaskSummaryView, SessionView } from '@hqagent/protocol'
import {
  CheckSquare,
  GitBranch,
  Bot,
  Play,
  ArrowRight,
  ShieldAlert,
  Clock,
  CheckCircle2,
  RefreshCw,
  Layers,
} from 'lucide-vue-next'
import {
  HqButton,
  HqBadge,
  HqErrorState,
  OfflineState,
} from '@/shared/ui'

const router = useRouter()
const appStore = useAppStore()
const agentStore = useAgentStore()
const workspaceStore = useWorkspaceStore()
const gateway = getUiGateway()

const isLoading = ref<boolean>(false)
const error = ref<string | null>(null)
const tasks = ref<TaskSummaryView[]>([])
const sessions = ref<SessionView[]>([])

onMounted(async () => {
  await loadOverviewData()
})

async function loadOverviewData() {
  isLoading.value = true
  error.value = null

  try {
    await appStore.fetchBootstrap()
    await agentStore.fetchAgents()

    const [tasksRes, sessionsRes] = await Promise.allSettled([
      gateway.listTasks({ page: 1, pageSize: 5 }),
      gateway.listSessions({ page: 1, pageSize: 5 }),
    ])

    if (tasksRes.status === 'fulfilled') {
      tasks.value = tasksRes.value.items
    }
    if (sessionsRes.status === 'fulfilled') {
      sessions.value = sessionsRes.value.items
    }
  } catch (err: any) {
    error.value = err?.message || '加载总览数据失败'
  } finally {
    isLoading.value = false
  }
}

// Active primary task (if running or waiting approval)
const primaryTask = computed<TaskSummaryView | null>(() => {
  if (tasks.value.length === 0) return null
  return (
    tasks.value.find((t) => t.status === 'running' || t.status === 'waiting_approval') ||
    tasks.value[0]
  )
})

function getTaskBadgeVariant(status: string): 'neutral' | 'success' | 'warning' | 'danger' {
  switch (status) {
    case 'running':
      return 'warning'
    case 'waiting_approval':
      return 'danger'
    case 'succeeded':
      return 'success'
    case 'failed':
      return 'danger'
    default:
      return 'neutral'
  }
}
</script>

<template>
  <div class="p-6 space-y-6 max-w-7xl mx-auto select-none">
    <!-- 1. Offline State -->
    <div v-if="appStore.isOffline" class="py-12">
      <OfflineState
        title="Local Hub 未连接"
        description="无法连接到本地 Local Hub 守护进程 (127.0.0.1:44810)。请确认后台服务正常运行。"
        @retry="loadOverviewData"
      />
    </div>

    <!-- 2. Error State -->
    <div v-else-if="error" class="py-12">
      <HqErrorState
        title="总览数据加载异常"
        :message="error"
        @retry="loadOverviewData"
      />
    </div>

    <!-- 3. Loading State -->
    <div v-else-if="isLoading" class="space-y-6">
      <div class="h-20 rounded-xl bg-panel animate-pulse border border-border-subtle" />
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div v-for="i in 4" :key="i" class="h-24 rounded-xl bg-panel animate-pulse border border-border-subtle" />
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div class="lg:col-span-2 h-72 rounded-xl bg-panel animate-pulse border border-border-subtle" />
        <div class="h-72 rounded-xl bg-panel animate-pulse border border-border-subtle" />
      </div>
    </div>

    <!-- 4. Content State (or Empty State) -->
    <template v-else>
      <!-- Workspace & Project Header Banner -->
      <div class="p-4 rounded-xl bg-panel border border-border-subtle flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-2xs">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-lg bg-primary-50 dark:bg-primary-950 text-primary-600 flex items-center justify-center shrink-0">
            <GitBranch class="w-5 h-5" />
          </div>
          <div>
            <div class="flex items-center gap-2">
              <h2 class="text-base font-bold text-content-primary">
                {{ workspaceStore.currentWorkspace?.name || 'HQAgent-Hub' }}
              </h2>
              <HqBadge variant="primary" size="sm">
                {{ workspaceStore.currentWorkspace?.branch || 'integration/phase1' }}
              </HqBadge>
            </div>
            <p class="text-2xs text-content-muted font-mono truncate max-w-md">
              {{ workspaceStore.currentWorkspace?.path || 'E:/OtherPro/HQAgent-Hub' }}
            </p>
          </div>
        </div>

        <div class="flex items-center gap-2 self-end md:self-auto">
          <HqButton size="sm" variant="secondary" @click="loadOverviewData">
            <template #icon>
              <RefreshCw class="w-3.5 h-3.5" />
            </template>
            刷新状态
          </HqButton>
          <HqButton size="sm" variant="primary" @click="router.push('/tasks')">
            <template #icon>
              <Play class="w-3.5 h-3.5" />
            </template>
            任务中心
          </HqButton>
        </div>
      </div>

      <!-- Quick Metrics Cards (4 Columns) -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <!-- Metric 1: Active Tasks -->
        <div class="p-4 rounded-xl bg-panel border border-border-subtle flex items-center justify-between shadow-2xs">
          <div>
            <span class="text-2xs text-content-muted font-medium block">进行中任务</span>
            <span class="text-xl font-extrabold text-content-primary tracking-tight">
              {{ appStore.bootstrap?.activeTasksCount || 0 }}
            </span>
          </div>
          <div class="w-9 h-9 rounded-lg bg-amber-50 dark:bg-amber-950/40 text-amber-600 flex items-center justify-center">
            <Play class="w-4 h-4" />
          </div>
        </div>

        <!-- Metric 2: Pending Approvals -->
        <div class="p-4 rounded-xl bg-panel border border-border-subtle flex items-center justify-between shadow-2xs">
          <div>
            <span class="text-2xs text-content-muted font-medium block">待安全审批</span>
            <span
              class="text-xl font-extrabold tracking-tight"
              :class="(appStore.bootstrap?.pendingApprovalsCount || 0) > 0 ? 'text-rose-600 dark:text-rose-400' : 'text-content-primary'"
            >
              {{ appStore.bootstrap?.pendingApprovalsCount || 0 }}
            </span>
          </div>
          <div
            class="w-9 h-9 rounded-lg flex items-center justify-center"
            :class="(appStore.bootstrap?.pendingApprovalsCount || 0) > 0 ? 'bg-rose-50 text-rose-600 dark:bg-rose-950/40' : 'bg-muted text-content-muted'"
          >
            <ShieldAlert class="w-4 h-4" />
          </div>
        </div>

        <!-- Metric 3: Agents Ready Ratio -->
        <div class="p-4 rounded-xl bg-panel border border-border-subtle flex items-center justify-between shadow-2xs">
          <div>
            <span class="text-2xs text-content-muted font-medium block">就绪 Agent</span>
            <span class="text-xl font-extrabold text-content-primary tracking-tight">
              {{ agentStore.readyCount }} <span class="text-xs text-content-muted font-normal">/ {{ agentStore.totalCount }}</span>
            </span>
          </div>
          <div class="w-9 h-9 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 flex items-center justify-center">
            <Bot class="w-4 h-4" />
          </div>
        </div>

        <!-- Metric 4: App Version & Hub Status -->
        <div class="p-4 rounded-xl bg-panel border border-border-subtle flex items-center justify-between shadow-2xs">
          <div>
            <span class="text-2xs text-content-muted font-medium block">Local Hub 状态</span>
            <span class="text-xs font-bold text-emerald-600 flex items-center gap-1 mt-1">
              <CheckCircle2 class="w-3.5 h-3.5" />
              v{{ appStore.bootstrap?.appVersion || '0.1.0' }} 正常
            </span>
          </div>
          <div class="w-9 h-9 rounded-lg bg-primary-50 dark:bg-primary-950/40 text-primary-600 flex items-center justify-center">
            <CheckSquare class="w-4 h-4" />
          </div>
        </div>
      </div>

      <!-- Bento Layout: Primary Task Card (2 Cols) + Agents Fleet (1 Col) -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- Left: Primary Bento Card -->
        <div class="lg:col-span-2 p-5 rounded-xl bg-panel border border-border-subtle flex flex-col justify-between shadow-2xs">
          <div>
            <!-- Card Header -->
            <div class="flex items-center justify-between pb-3 border-b border-border-subtle">
              <div class="flex items-center gap-2">
                <Layers class="w-4 h-4 text-primary-600" />
                <h3 class="text-xs font-bold text-content-primary uppercase tracking-wider">重点协作任务</h3>
              </div>
              <HqBadge v-if="primaryTask" :variant="getTaskBadgeVariant(primaryTask.status)" size="sm">
                {{ primaryTask.status }}
              </HqBadge>
            </div>

            <!-- Task Content -->
            <div v-if="primaryTask" class="py-4 space-y-4">
              <div>
                <span class="text-2xs font-mono text-content-muted">ID: {{ primaryTask.id }}</span>
                <h4 class="text-sm font-bold text-content-primary mt-0.5 leading-snug">
                  {{ primaryTask.objective }}
                </h4>
              </div>

              <!-- Waiting Approval Warning -->
              <div
                v-if="primaryTask.status === 'waiting_approval'"
                class="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 flex items-center justify-between text-xs"
              >
                <div class="flex items-center gap-2 text-rose-700 dark:text-rose-300 font-semibold">
                  <ShieldAlert class="w-4 h-4" />
                  <span>任务触发高危命令，等待安全审批通过</span>
                </div>
                <HqButton size="sm" variant="danger" @click="router.push('/tasks')">
                  去审批
                </HqButton>
              </div>

              <!-- Pipeline / Progress placeholder -->
              <div class="space-y-1.5">
                <div class="flex justify-between text-2xs text-content-muted">
                  <span>多角色工作流阶段</span>
                  <span>协同执行中</span>
                </div>
                <div class="w-full bg-muted rounded-full h-2 overflow-hidden flex">
                  <div class="bg-emerald-500 h-2 w-1/3" title="架构设计: 完成" />
                  <div class="bg-primary-500 h-2 w-1/3 animate-pulse" title="前端实现: 进行中" />
                  <div class="bg-border-default h-2 w-1/3" title="代码审查: 等待中" />
                </div>
                <div class="flex justify-between text-3xs font-mono text-content-muted pt-0.5">
                  <span class="text-emerald-600 font-semibold">1. Architect (已完成)</span>
                  <span class="text-primary-600 font-bold">2. Implementer (进行中)</span>
                  <span>3. Reviewer (排队)</span>
                </div>
              </div>
            </div>

            <!-- Empty Task State -->
            <div v-else class="py-10 text-center space-y-2">
              <CheckCircle2 class="w-10 h-10 text-emerald-500 mx-auto stroke-1" />
              <p class="text-xs font-bold text-content-primary">当前暂无正在执行的任务</p>
              <p class="text-2xs text-content-muted">所有 AI 角色空闲，随时可创建新任务投入协作。</p>
            </div>
          </div>

          <!-- Footer Button -->
          <div class="pt-3 border-t border-border-subtle flex justify-end">
            <HqButton size="sm" variant="secondary" @click="router.push('/tasks')">
              <span>前往任务中心</span>
              <template #iconRight>
                <ArrowRight class="w-3.5 h-3.5" />
              </template>
            </HqButton>
          </div>
        </div>

        <!-- Right: Agent Fleet Quick Panel -->
        <div class="p-5 rounded-xl bg-panel border border-border-subtle flex flex-col justify-between shadow-2xs">
          <div>
            <div class="flex items-center justify-between pb-3 border-b border-border-subtle">
              <div class="flex items-center gap-2">
                <Bot class="w-4 h-4 text-primary-600" />
                <h3 class="text-xs font-bold text-content-primary uppercase tracking-wider">Agent 状态群</h3>
              </div>
              <span class="text-2xs font-mono text-content-muted">{{ agentStore.readyCount }} 就绪</span>
            </div>

            <div v-if="agentStore.agents.length === 0" class="py-8 text-center text-2xs text-content-muted">
              未探测到任何 Agent
            </div>
            <div v-else class="py-2 space-y-2 max-h-64 overflow-y-auto">
              <div
                v-for="agent in agentStore.agents"
                :key="agent.id"
                @click="agentStore.selectAgent(agent)"
                class="p-2 rounded-lg border border-border-subtle hover:border-border-default hover:bg-muted/40 cursor-pointer transition-colors flex items-center justify-between text-xs"
              >
                <div class="flex items-center gap-2.5">
                  <span
                    class="w-2 h-2 rounded-full shrink-0"
                    :class="agent.status === 'ready' ? 'bg-emerald-500' : agent.status === 'busy' ? 'bg-amber-500' : 'bg-rose-500'"
                  />
                  <div>
                    <span class="font-bold text-content-primary block leading-tight">{{ agent.displayName }}</span>
                    <span class="text-3xs text-content-muted font-mono leading-tight">v{{ agent.version }}</span>
                  </div>
                </div>
                <HqBadge :variant="agent.status === 'ready' ? 'success' : 'neutral'" size="sm">
                  {{ agent.status }}
                </HqBadge>
              </div>
            </div>
          </div>

          <div class="pt-3 border-t border-border-subtle flex justify-end">
            <HqButton size="sm" variant="secondary" @click="router.push('/agents')">
              <span>管理全部 Agent</span>
              <template #iconRight>
                <ArrowRight class="w-3.5 h-3.5" />
              </template>
            </HqButton>
          </div>
        </div>
      </div>

      <!-- Recent Sessions Panel -->
      <div class="p-5 rounded-xl bg-panel border border-border-subtle shadow-2xs space-y-3">
        <div class="flex items-center justify-between pb-2 border-b border-border-subtle">
          <div class="flex items-center gap-2">
            <Clock class="w-4 h-4 text-content-muted" />
            <h3 class="text-xs font-bold text-content-primary uppercase tracking-wider">最近活跃会话 (Sessions)</h3>
          </div>
          <span class="text-2xs text-content-muted">共 {{ sessions.length }} 条</span>
        </div>

        <div v-if="sessions.length === 0" class="py-6 text-center text-2xs text-content-muted">
          暂无历史会话记录
        </div>
        <div v-else class="space-y-1.5">
          <div
            v-for="sess in sessions"
            :key="sess.id"
            class="p-2.5 rounded-lg border border-border-subtle bg-muted/20 flex items-center justify-between text-xs hover:bg-muted/40 transition-colors"
          >
            <div class="flex items-center gap-3">
              <div class="w-7 h-7 rounded bg-primary-50 dark:bg-primary-950 text-primary-600 flex items-center justify-center text-xs font-bold shrink-0">
                S
              </div>
              <div>
                <div class="flex items-center gap-2">
                  <span class="font-bold text-content-primary">{{ sess.agentDisplayName }}</span>
                  <HqBadge variant="neutral" size="sm">{{ sess.roleId }}</HqBadge>
                  <span class="text-2xs font-mono text-content-muted truncate max-w-xs">{{ sess.externalSessionId }}</span>
                </div>
                <span class="text-3xs text-content-muted">创建时间: {{ sess.createdAt }}</span>
              </div>
            </div>

            <div class="flex items-center gap-2">
              <HqBadge :variant="sess.status === 'active' ? 'success' : 'neutral'" size="sm">
                {{ sess.status }}
              </HqBadge>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
