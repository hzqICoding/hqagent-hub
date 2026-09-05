<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useAppStore } from '@/stores/app.store'
import { useAgentStore } from '@/stores/agent.store'
import type { AgentView, AgentStatus } from '@hqagent/protocol'
import {
  Bot,
  RefreshCw,
  Search,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  Terminal,
  Cpu,
  Power,
  Stethoscope,
  ChevronRight,
  ShieldCheck,
  ShieldAlert,
} from 'lucide-vue-next'
import {
  HqButton,
  HqBadge,
  HqInput,
  HqSwitch,
  HqDialog,
  LoadingState,
  HqEmptyState,
  HqErrorState,
  OfflineState,
} from '@/shared/ui'

const appStore = useAppStore()
const agentStore = useAgentStore()

const isDiagnosing = ref<boolean>(false)
const diagnosticModalAgent = ref<AgentView | null>(null)

onMounted(async () => {
  await agentStore.fetchAgents()
})

function getStatusBadge(status: AgentStatus): {
  variant: 'neutral' | 'success' | 'warning' | 'danger'
  label: string
} {
  switch (status) {
    case 'ready':
      return { variant: 'success', label: '就绪' }
    case 'busy':
      return { variant: 'warning', label: '执行中' }
    case 'not_logged_in':
      return { variant: 'danger', label: '未登录' }
    case 'incompatible':
      return { variant: 'danger', label: '版本不兼容' }
    case 'disabled':
      return { variant: 'neutral', label: '已停用' }
    case 'offline':
      return { variant: 'danger', label: '离线' }
    case 'error':
      return { variant: 'danger', label: '异常' }
    case 'discovering':
      return { variant: 'warning', label: '探测中' }
    default:
      return { variant: 'neutral', label: status }
  }
}

function handleOpenDiagnosis(agent: AgentView) {
  diagnosticModalAgent.value = agent
}

function handleCloseDiagnosis() {
  diagnosticModalAgent.value = null
}
</script>

<template>
  <div class="p-6 space-y-6 max-w-7xl mx-auto select-none">
    <!-- Header & Action Bar -->
    <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
      <div>
        <h2 class="text-base font-bold text-content-primary">Agent 实例管理与诊断</h2>
        <p class="text-xs text-content-muted">
          管理本机发现的 AI 智能体适配器、分配角色与硬能力约束
        </p>
      </div>

      <div class="flex items-center gap-2">
        <HqButton
          size="sm"
          variant="secondary"
          :loading="agentStore.isRefreshing"
          @click="agentStore.refreshDiscovery"
        >
          <template #icon>
            <RefreshCw class="w-3.5 h-3.5" :class="agentStore.isRefreshing ? 'animate-spin' : ''" />
          </template>
          刷新探测
        </HqButton>
      </div>
    </div>

    <!-- Status Filter Tabs & Search Bar -->
    <div class="p-3 bg-panel border border-border-subtle rounded-xl flex flex-col md:flex-row items-center justify-between gap-3 shadow-2xs">
      <!-- Status Tabs -->
      <div class="flex items-center gap-1 overflow-x-auto w-full md:w-auto">
        <button
          type="button"
          @click="agentStore.statusFilter = 'all'"
          class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
          :class="agentStore.statusFilter === 'all' ? 'bg-primary-50 text-primary-700 dark:bg-primary-950 font-bold' : 'text-content-secondary hover:bg-muted'"
        >
          全部 ({{ agentStore.totalCount }})
        </button>
        <button
          type="button"
          @click="agentStore.statusFilter = 'ready'"
          class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
          :class="agentStore.statusFilter === 'ready' ? 'bg-primary-50 text-primary-700 dark:bg-primary-950 font-bold' : 'text-content-secondary hover:bg-muted'"
        >
          就绪 ({{ agentStore.readyCount }})
        </button>
        <button
          type="button"
          @click="agentStore.statusFilter = 'busy'"
          class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
          :class="agentStore.statusFilter === 'busy' ? 'bg-primary-50 text-primary-700 dark:bg-primary-950 font-bold' : 'text-content-secondary hover:bg-muted'"
        >
          执行中 ({{ agentStore.busyCount }})
        </button>
        <button
          type="button"
          @click="agentStore.statusFilter = 'issues'"
          class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
          :class="agentStore.statusFilter === 'issues' ? 'bg-rose-50 text-rose-700 dark:bg-rose-950 font-bold' : 'text-content-secondary hover:bg-muted'"
        >
          异常 ({{ agentStore.issuesCount }})
        </button>
        <button
          type="button"
          @click="agentStore.statusFilter = 'disabled'"
          class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
          :class="agentStore.statusFilter === 'disabled' ? 'bg-primary-50 text-primary-700 dark:bg-primary-950 font-bold' : 'text-content-secondary hover:bg-muted'"
        >
          已停用 ({{ agentStore.disabledCount }})
        </button>
      </div>

      <!-- Search Input -->
      <div class="relative w-full md:w-64">
        <Search class="w-3.5 h-3.5 absolute left-3 top-2.5 text-content-muted" />
        <input
          v-model="agentStore.searchQuery"
          type="text"
          placeholder="搜索名称 / 适配器 / 能力..."
          class="w-full text-xs pl-8 pr-3 py-1.5 rounded-lg bg-muted/40 border border-border-default text-content-primary focus:outline-none focus:ring-1 focus:ring-primary-500"
        />
      </div>
    </div>

    <!-- 1. Offline State -->
    <div v-if="appStore.isOffline" class="py-12">
      <OfflineState
        title="Local Hub 未连接"
        description="无法连接到本地 Local Hub 守护进程进行 Agent 探测。请检查后台服务是否已启动。"
        @retry="agentStore.fetchAgents"
      />
    </div>

    <!-- 2. Error State -->
    <div v-else-if="agentStore.error" class="py-12">
      <HqErrorState
        title="获取 Agent 列表失败"
        :message="agentStore.error"
        @retry="agentStore.fetchAgents"
      />
    </div>

    <!-- 3. Loading State -->
    <div v-else-if="agentStore.isLoading" class="space-y-4">
      <LoadingState description="正在获取 Agent 列表..." />
    </div>

    <!-- 4. Empty State -->
    <div v-else-if="agentStore.filteredAgents.length === 0" class="py-12">
      <HqEmptyState
        :title="agentStore.agents.length === 0 ? '未发现任何本地 Agent' : '没有匹配的 Agent'"
        :description="agentStore.agents.length === 0 ? '未扫描到已安装的 CLI 工具。请在终端安装并登录后再试。' : '尝试调整筛选条件或清空搜索关键字。'"
      >
        <template #actions>
          <HqButton
            size="sm"
            variant="primary"
            :loading="agentStore.isRefreshing"
            @click="agentStore.refreshDiscovery"
          >
            重新探测本地 Agent
          </HqButton>
        </template>
      </HqEmptyState>
    </div>

    <!-- 5. Content Grid Cards -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
      <div
        v-for="agent in agentStore.filteredAgents"
        :key="agent.id"
        class="p-5 rounded-xl bg-panel border transition-all duration-150 flex flex-col justify-between shadow-2xs hover:shadow-xs"
        :class="agentStore.selectedAgent?.id === agent.id ? 'border-primary-500 ring-2 ring-primary-500/20' : 'border-border-subtle hover:border-border-default'"
      >
        <div class="space-y-3">
          <!-- Card Header -->
          <div class="flex items-start justify-between gap-3">
            <div class="flex items-center gap-3">
              <div
                class="w-10 h-10 rounded-xl flex items-center justify-center font-bold text-sm shrink-0"
                :class="agent.status === 'ready' ? 'bg-primary-50 text-primary-600 dark:bg-primary-950' : agent.status === 'disabled' ? 'bg-muted text-content-disabled' : 'bg-rose-50 text-rose-600 dark:bg-rose-950'"
              >
                <Bot class="w-5 h-5" />
              </div>
              <div>
                <h3 class="text-sm font-bold text-content-primary leading-tight">{{ agent.displayName }}</h3>
                <span class="text-2xs font-mono text-content-muted leading-tight block mt-0.5">
                  {{ agent.adapterId }} · v{{ agent.version }}
                </span>
              </div>
            </div>

            <!-- Status Badge -->
            <HqBadge :variant="getStatusBadge(agent.status).variant" size="sm">
              {{ getStatusBadge(agent.status).label }}
            </HqBadge>
          </div>

          <!-- Diagnostic Warning if any -->
          <div
            v-if="agent.diagnosticMessage"
            class="p-2.5 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-2xs text-amber-800 dark:text-amber-200 space-y-1"
          >
            <div class="flex items-center gap-1 font-semibold">
              <AlertTriangle class="w-3.5 h-3.5 text-amber-600" />
              <span>诊断建议</span>
            </div>
            <p class="leading-relaxed">{{ agent.diagnosticMessage }}</p>
          </div>

          <!-- Roles Assignment -->
          <div>
            <span class="text-3xs font-semibold text-content-muted uppercase tracking-wider block mb-1">
              绑定角色
            </span>
            <div v-if="agent.assignedRoles.length === 0" class="text-2xs text-content-disabled">
              未分配任何职责
            </div>
            <div v-else class="flex flex-wrap gap-1">
              <HqBadge
                v-for="role in agent.assignedRoles"
                :key="role"
                :variant="agent.isPrimaryFor.includes(role) ? 'success' : 'neutral'"
                size="sm"
              >
                {{ agent.isPrimaryFor.includes(role) ? `★ 主选: ${role}` : `备选: ${role}` }}
              </HqBadge>
            </div>
          </div>

          <!-- Hard Capabilities Chips -->
          <div>
            <span class="text-3xs font-semibold text-content-muted uppercase tracking-wider block mb-1">
              硬能力支撑 ({{ agent.capabilities.filter((c) => c.hard).length }})
            </span>
            <div class="flex flex-wrap gap-1 max-h-16 overflow-y-auto">
              <span
                v-for="cap in agent.capabilities.filter((c) => c.hard)"
                :key="cap.id"
                class="px-1.5 py-0.5 rounded text-3xs font-medium bg-muted text-content-secondary border border-border-subtle"
              >
                {{ cap.name }}
              </span>
            </div>
          </div>
        </div>

        <!-- Footer Actions -->
        <div class="pt-4 mt-4 border-t border-border-subtle flex items-center justify-between text-xs">
          <div class="flex items-center gap-2">
            <!-- Toggle enable/disable switch -->
            <label class="flex items-center gap-1.5 cursor-pointer text-2xs text-content-secondary">
              <input
                type="checkbox"
                :checked="agent.status !== 'disabled'"
                @change="(e) => agentStore.toggleAgent(agent.id, (e.target as HTMLInputElement).checked)"
                class="rounded border-border-default text-primary-600 focus:ring-0"
              />
              <span>{{ agent.status === 'disabled' ? '已停用' : '启用' }}</span>
            </label>
          </div>

          <div class="flex items-center gap-2">
            <HqButton size="sm" variant="secondary" @click="handleOpenDiagnosis(agent)">
              <template #icon>
                <Stethoscope class="w-3 h-3" />
              </template>
              诊断
            </HqButton>
            <HqButton size="sm" variant="secondary" @click="agentStore.selectAgent(agent)">
              检视
              <template #iconRight>
                <ChevronRight class="w-3 h-3" />
              </template>
            </HqButton>
          </div>
        </div>
      </div>
    </div>

    <!-- Diagnostic Modal Dialog -->
    <HqDialog
      :open="diagnosticModalAgent !== null"
      @update:open="(val: boolean) => { if (!val) handleCloseDiagnosis() }"
      title="Agent 运行诊断报告"
      width="540px"
    >
      <div v-if="diagnosticModalAgent" class="space-y-4 text-xs">
        <div class="flex items-center justify-between p-3 rounded-lg bg-muted/40 border border-border-subtle">
          <div class="flex items-center gap-2.5">
            <Bot class="w-5 h-5 text-primary-600" />
            <div>
              <span class="font-bold text-content-primary">{{ diagnosticModalAgent.displayName }}</span>
              <span class="text-2xs text-content-muted font-mono block">{{ diagnosticModalAgent.id }}</span>
            </div>
          </div>
          <HqBadge :variant="getStatusBadge(diagnosticModalAgent.status).variant">
            {{ getStatusBadge(diagnosticModalAgent.status).label }}
          </HqBadge>
        </div>

        <div class="space-y-2">
          <h4 class="font-semibold text-content-primary">系统健康检查项</h4>
          <div class="space-y-1.5">
            <div class="flex items-center justify-between p-2 rounded bg-panel border border-border-subtle">
              <span class="text-content-secondary">可执行文件探测</span>
              <span class="text-emerald-600 font-mono font-medium flex items-center gap-1">
                <CheckCircle2 class="w-3.5 h-3.5" />
                就绪 ({{ diagnosticModalAgent.executablePath || '已定位' }})
              </span>
            </div>
            <div class="flex items-center justify-between p-2 rounded bg-panel border border-border-subtle">
              <span class="text-content-secondary">版本兼容性</span>
              <span
                class="font-mono font-medium flex items-center gap-1"
                :class="diagnosticModalAgent.status === 'incompatible' ? 'text-rose-600' : 'text-emerald-600'"
              >
                <CheckCircle2 v-if="diagnosticModalAgent.status !== 'incompatible'" class="w-3.5 h-3.5" />
                <XCircle v-else class="w-3.5 h-3.5" />
                v{{ diagnosticModalAgent.version }} (最低要求: v{{ diagnosticModalAgent.minimumVersion || '1.0.0' }})
              </span>
            </div>
            <div class="flex items-center justify-between p-2 rounded bg-panel border border-border-subtle">
              <span class="text-content-secondary">登录与授权凭证</span>
              <span
                class="font-medium flex items-center gap-1"
                :class="diagnosticModalAgent.status === 'not_logged_in' ? 'text-rose-600' : 'text-emerald-600'"
              >
                <CheckCircle2 v-if="diagnosticModalAgent.status !== 'not_logged_in'" class="w-3.5 h-3.5" />
                <XCircle v-else class="w-3.5 h-3.5" />
                {{ diagnosticModalAgent.status === 'not_logged_in' ? '未登录 (需终端授权)' : '已登录有效' }}
              </span>
            </div>
          </div>
        </div>

        <div v-if="diagnosticModalAgent.diagnosticMessage" class="p-3 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200 text-2xs space-y-1">
          <span class="font-bold flex items-center gap-1">
            <AlertTriangle class="w-3.5 h-3.5 text-amber-600" />
            处理建议
          </span>
          <p class="leading-relaxed">{{ diagnosticModalAgent.diagnosticMessage }}</p>
        </div>
      </div>

      <template #footer>
        <div class="flex justify-end gap-2">
          <HqButton size="sm" variant="secondary" @click="handleCloseDiagnosis">
            关闭
          </HqButton>
        </div>
      </template>
    </HqDialog>
  </div>
</template>
