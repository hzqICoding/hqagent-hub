<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app.store'
import { useTaskStore } from '@/stores/task.store'
import type { TaskStatus, NodeStatus } from '@hqagent/protocol'
import {
  ArrowLeft,
  Play,
  Pause,
  RotateCw,
  XCircle,
  PlusCircle,
  Clock,
  FolderGit2,
  GitBranch,
  ShieldAlert,
  CheckCircle2,
  AlertCircle,
  FileCode,
  Search,
  AlertTriangle,
  FileText,
  Activity,
  Terminal,
} from 'lucide-vue-next'
import {
  HqButton,
  HqBadge,
  HqDialog,
  HqInput,
  HqTextarea,
  HqTooltip,
  HqVirtualList,
  ResolveSourceBadge,
  LoadingState,
  HqErrorState,
  OfflineState,
} from '@/shared/ui'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const taskStore = useTaskStore()

const taskId = computed(() => route.params.taskId as string)

// Active Tab
const activeTab = ref<'timeline' | 'events' | 'artifacts' | 'worktree'>('timeline')

// Dialog States
const isCancelModalOpen = ref(false)
const cancelReason = ref('')
const isAppendModalOpen = ref(false)
const appendInstructionText = ref('')
const appendError = ref<string | null>(null)

// Virtual List Ref & Auto Scroll
const virtualListRef = ref<{ scrollToIndex: (index: number) => void; scrollToBottom: () => void } | null>(null)
const autoScrollEvents = ref(true)

// Expanded JSON payloads
const expandedEventIds = ref<Set<string>>(new Set())

function toggleExpandEvent(id: string) {
  if (expandedEventIds.value.has(id)) {
    expandedEventIds.value.delete(id)
  } else {
    expandedEventIds.value.add(id)
  }
}

onMounted(async () => {
  if (taskId.value) {
    await taskStore.fetchTask(taskId.value)
    taskStore.subscribeTaskEvents(taskId.value)
  }
})

onUnmounted(() => {
  taskStore.unsubscribeTaskEvents()
})

// Auto scroll on new events
watch(
  () => taskStore.events.length,
  async () => {
    if (autoScrollEvents.value && activeTab.value === 'events') {
      await nextTick()
      virtualListRef.value?.scrollToBottom()
    }
  }
)

function getStatusBadge(status: TaskStatus) {
  switch (status) {
    case 'running':
      return { label: '执行中', variant: 'primary' as const, icon: Play, class: 'animate-pulse' }
    case 'waiting_approval':
      return { label: '等待安全审批', variant: 'warning' as const, icon: ShieldAlert, class: 'bg-amber-100 text-amber-800 dark:bg-amber-950/80 dark:text-amber-200 border-amber-300' }
    case 'succeeded':
      return { label: '执行成功', variant: 'success' as const, icon: CheckCircle2, class: '' }
    case 'failed':
      return { label: '执行失败', variant: 'danger' as const, icon: AlertCircle, class: '' }
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

function getNodeStatusBadge(status: NodeStatus) {
  switch (status) {
    case 'resolving':
      return {
        label: '角色解析中',
        class: 'bg-cyan-500/15 text-cyan-700 dark:text-cyan-300 border-cyan-500/40 animate-pulse font-medium',
        dotClass: 'bg-cyan-500 animate-ping',
      }
    case 'skipped':
      return {
        label: '已跳过 (前序跳过)',
        class: 'bg-muted/30 text-text-muted border-border-subtle',
        dotClass: 'bg-text-muted/40',
      }
    case 'running':
      return {
        label: '执行中',
        class: 'bg-primary/15 text-primary border-primary/30 font-medium',
        dotClass: 'bg-primary animate-ping',
      }
    case 'waiting_approval':
      return {
        label: '等待审批',
        class: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30',
        dotClass: 'bg-amber-500',
      }
    case 'succeeded':
      return {
        label: '完成',
        class: 'bg-success/15 text-success border-success/30',
        dotClass: 'bg-success',
      }
    case 'failed':
      return {
        label: '失败',
        class: 'bg-danger/15 text-danger border-danger/30',
        dotClass: 'bg-danger',
      }
    case 'cancelled':
      return {
        label: '已取消',
        class: 'bg-panel text-text-muted border-border',
        dotClass: 'bg-text-muted',
      }
    default:
      return {
        label: '待执行',
        class: 'bg-panel text-text-muted border-border',
        dotClass: 'bg-border',
      }
  }
}

// Actions
async function handlePause() {
  if (!taskId.value) return
  await taskStore.controlTask(taskId.value, { action: 'pause' })
}

async function handleResume() {
  if (!taskId.value) return
  await taskStore.controlTask(taskId.value, { action: 'resume' })
}

async function handleRetry() {
  if (!taskId.value) return
  await taskStore.controlTask(taskId.value, { action: 'retry' })
}

async function handleCancelConfirm() {
  if (!taskId.value) return
  try {
    await taskStore.controlTask(taskId.value, {
      action: 'cancel',
      instruction: cancelReason.value || undefined,
    })
    isCancelModalOpen.value = false
  } catch {
    // Handled in store with orphanProcessIds
  }
}

function openAppendModal() {
  appendInstructionText.value = ''
  appendError.value = null
  isAppendModalOpen.value = true
}

async function handleAppendInstruction() {
  if (!appendInstructionText.value.trim()) {
    appendError.value = '请输入追加的指令内容'
    return
  }
  try {
    await taskStore.controlTask(taskId.value, {
      action: 'append_instruction',
      instruction: appendInstructionText.value.trim(),
    })
    isAppendModalOpen.value = false
  } catch (err: unknown) {
    appendError.value = err instanceof Error ? err.message : '追加指令失败'
  }
}

function formatDuration(ms?: number) {
  if (!ms) return '-'
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remSec = seconds % 60
  return `${minutes}m ${remSec}s`
}

function formatTime(timestamp?: string) {
  if (!timestamp) return '-'
  return new Date(timestamp).toLocaleTimeString()
}

const currentTask = computed(() => taskStore.currentTask)
</script>

<template>
  <div class="p-6 space-y-6 max-w-7xl mx-auto select-none">
    <!-- Back & Header -->
    <div class="flex flex-col gap-3">
      <div class="flex items-center gap-2 text-xs text-text-muted">
        <button
          class="inline-flex items-center gap-1 hover:text-text transition-colors"
          @click="router.push('/tasks')"
        >
          <ArrowLeft class="w-3.5 h-3.5" />
          返回任务列表
        </button>
        <span>/</span>
        <span class="font-mono text-text">{{ taskId }}</span>
      </div>

      <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <!-- Title & Status -->
        <div class="space-y-1.5 flex-1 min-w-0">
          <div class="flex flex-wrap items-center gap-2.5">
            <span class="font-mono text-xs text-text-muted font-semibold">{{ currentTask?.id }}</span>
            <HqBadge
              v-if="currentTask"
              :variant="getStatusBadge(currentTask.status).variant"
              size="sm"
              :class="getStatusBadge(currentTask.status).class"
              class="inline-flex items-center gap-1 shadow-xs"
            >
              <component :is="getStatusBadge(currentTask.status).icon" class="w-3 h-3 shrink-0" />
              <span>{{ getStatusBadge(currentTask.status).label }}</span>
            </HqBadge>

            <!-- Pending Approval Alert -->
            <router-link
              v-if="currentTask?.pendingApprovalId"
              to="/approvals"
              class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-xs font-semibold bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/40 hover:bg-amber-500/25 transition-colors animate-pulse"
            >
              <ShieldAlert class="w-3.5 h-3.5" />
              存在待审批敏感操作 (点击前往审批中心)
            </router-link>
          </div>

          <h1 class="text-xl font-bold text-text break-words">
            {{ currentTask?.objective || '加载中...' }}
          </h1>

          <!-- Meta Bar -->
          <div class="flex flex-wrap items-center gap-4 text-xs text-text-muted">
            <span class="inline-flex items-center gap-1">
              <FolderGit2 class="w-3.5 h-3.5" />
              {{ currentTask?.workspaceName }}
            </span>
            <span>•</span>
            <span>团队: {{ currentTask?.profileName }}</span>
            <span v-if="currentTask?.branch">•</span>
            <span v-if="currentTask?.branch" class="inline-flex items-center gap-1 text-text">
              <GitBranch class="w-3.5 h-3.5 text-primary" />
              {{ currentTask.branch }}
            </span>
            <span>•</span>
            <span class="inline-flex items-center gap-1">
              <Clock class="w-3.5 h-3.5" />
              执行耗时: {{ formatDuration(currentTask?.durationMs) }}
            </span>
          </div>
        </div>

        <!-- Action Control Buttons -->
        <div class="flex flex-wrap items-center gap-2 shrink-0">
          <!-- Pause: operates between nodes (Trap 1) -->
          <HqTooltip content="节点间暂停：当前节点执行完毕后挂起，不强杀正在执行的 Agent">
            <HqButton
              variant="secondary"
              size="sm"
              :disabled="!taskStore.canPause || taskStore.isActionLoading"
              @click="handlePause"
            >
              <Pause class="w-3.5 h-3.5 mr-1" />
              暂停执行
            </HqButton>
          </HqTooltip>

          <!-- Resume -->
          <HqButton
            v-if="currentTask?.status === 'paused'"
            variant="primary"
            size="sm"
            :disabled="!taskStore.canResume || taskStore.isActionLoading"
            @click="handleResume"
          >
            <Play class="w-3.5 h-3.5 mr-1" />
            继续执行
          </HqButton>

          <!-- Append Instruction: disabled when active node is running (Trap 1) -->
          <HqTooltip
            :content="
              taskStore.hasRunningNode
                ? '当前节点正在执行中，待节点空闲后方可追加指令'
                : '向任务追加新的指导或补充约束'
            "
          >
            <div>
              <HqButton
                variant="secondary"
                size="sm"
                :disabled="!taskStore.canAppendInstruction || taskStore.isActionLoading"
                @click="openAppendModal"
              >
                <PlusCircle class="w-3.5 h-3.5 mr-1" />
                追加指令
              </HqButton>
            </div>
          </HqTooltip>

          <!-- Retry: when failed -->
          <HqButton
            v-if="taskStore.canRetry"
            variant="secondary"
            size="sm"
            :disabled="taskStore.isActionLoading"
            @click="handleRetry"
          >
            <RotateCw class="w-3.5 h-3.5 mr-1" />
            重试任务
          </HqButton>

          <!-- Cancel: safe cancel (Trap 2) -->
          <HqButton
            v-if="taskStore.canCancel"
            variant="danger"
            size="sm"
            :disabled="taskStore.isActionLoading"
            @click="isCancelModalOpen = true"
          >
            <XCircle class="w-3.5 h-3.5 mr-1" />
            取消任务
          </HqButton>
        </div>
      </div>
    </div>

    <!-- Orphan Process Warning Banner (Trap 2: TASK_NOT_CANCELLABLE) -->
    <div
      v-if="taskStore.orphanProcessIds.length > 0"
      class="p-4 rounded-[var(--radius-md)] bg-rose-500/10 border border-rose-500/40 text-rose-800 dark:text-rose-200 flex items-start gap-3"
    >
      <AlertTriangle class="w-5 h-5 shrink-0 text-rose-600 dark:text-rose-400 mt-0.5" />
      <div class="space-y-1">
        <h4 class="text-sm font-bold">任务取消被拒绝：存在残留孤儿进程</h4>
        <p class="text-xs leading-relaxed">
          底层适配器明确上报无法强行中断当前执行会话（错误码 TASK_NOT_CANCELLABLE）。
          以下本地进程可能仍在系统后台运行，需要由管理员人工排查：
        </p>
        <div class="flex flex-wrap gap-2 pt-1">
          <span
            v-for="pid in taskStore.orphanProcessIds"
            :key="pid"
            class="px-2 py-0.5 text-xs font-mono font-bold bg-rose-500/20 rounded border border-rose-500/30"
          >
            PID: {{ pid }}
          </span>
        </div>
      </div>
    </div>

    <!-- Failure Reason Banner -->
    <div
      v-if="currentTask?.failureReason"
      class="p-4 rounded-[var(--radius-md)] bg-danger/10 border border-danger/30 text-danger flex items-start gap-3"
    >
      <AlertCircle class="w-5 h-5 shrink-0 mt-0.5" />
      <div>
        <h4 class="text-sm font-bold">任务执行失败原因</h4>
        <p class="text-xs mt-0.5 leading-relaxed">{{ currentTask.failureReason }}</p>
      </div>
    </div>

    <!-- Navigation Tabs -->
    <div class="flex items-center gap-2 border-b border-border-subtle text-xs">
      <button
        class="px-4 py-2.5 font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5"
        :class="
          activeTab === 'timeline'
            ? 'border-primary text-primary'
            : 'border-transparent text-text-muted hover:text-text'
        "
        @click="activeTab = 'timeline'"
      >
        <Activity class="w-4 h-4" />
        多 Agent 协作时间线 ({{ taskStore.currentNodes.length }})
      </button>

      <button
        class="px-4 py-2.5 font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5"
        :class="
          activeTab === 'events'
            ? 'border-primary text-primary'
            : 'border-transparent text-text-muted hover:text-text'
        "
        @click="activeTab = 'events'"
      >
        <Terminal class="w-4 h-4" />
        实时事件流 ({{ taskStore.events.length }})
      </button>

      <button
        class="px-4 py-2.5 font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5"
        :class="
          activeTab === 'artifacts'
            ? 'border-primary text-primary'
            : 'border-transparent text-text-muted hover:text-text'
        "
        @click="activeTab = 'artifacts'"
      >
        <FileText class="w-4 h-4" />
        交付产物 ({{ taskStore.currentArtifacts.length }})
      </button>

      <button
        class="px-4 py-2.5 font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5"
        :class="
          activeTab === 'worktree'
            ? 'border-primary text-primary'
            : 'border-transparent text-text-muted hover:text-text'
        "
        @click="activeTab = 'worktree'"
      >
        <FolderGit2 class="w-4 h-4" />
        工作区与约束
      </button>
    </div>

    <!-- 4 Page States -->
    <OfflineState v-if="appStore.isOffline" @retry="() => taskStore.fetchTask(taskId)" />
    <LoadingState v-else-if="taskStore.isLoading" message="正在加载任务详情与事件流..." />
    <HqErrorState
      v-else-if="taskStore.error"
      title="加载任务失败"
      :message="taskStore.error"
      @retry="() => taskStore.fetchTask(taskId)"
    />

    <!-- Tab 1: Timeline -->
    <div v-else-if="activeTab === 'timeline'" class="space-y-4">
      <div
        v-if="taskStore.currentNodes.length === 0"
        class="p-8 text-center bg-panel rounded-xl border border-border-subtle text-text-muted text-xs"
      >
        任务刚被调度，尚未产生执行节点。
      </div>

      <div v-else class="space-y-4">
        <div
          v-for="(node, index) in taskStore.currentNodes"
          :key="node.id"
          class="p-5 bg-panel rounded-xl border border-border-subtle shadow-2xs space-y-3"
        >
          <!-- Node Header -->
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border-subtle pb-3">
            <div class="flex flex-wrap items-center gap-2">
              <span class="w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center">
                {{ index + 1 }}
              </span>
              <span class="font-bold text-sm text-text capitalize">{{ node.roleId.replace('_', ' ') }}</span>

              <!-- Node Status with resolving & skipped (Trap 3) -->
              <span
                class="px-2.5 py-0.5 rounded text-xs flex items-center gap-1.5"
                :class="getNodeStatusBadge(node.status).class"
              >
                <span class="w-2 h-2 rounded-full" :class="getNodeStatusBadge(node.status).dotClass" />
                {{ getNodeStatusBadge(node.status).label }}
              </span>

              <!-- Resolve Source Badge with 6 levels & fallback reason (Trap 4) -->
              <ResolveSourceBadge
                :source="node.resolveSource"
                :is-fallback="node.isFallback"
                :fallback-reason="node.fallbackReason"
              />
            </div>

            <!-- Agent Assigned & Times -->
            <div class="flex items-center gap-3 text-xs text-text-muted">
              <span class="font-medium text-text">
                {{ node.resolvedAgentName || node.resolvedAgentId }}
              </span>
              <span>•</span>
              <span>{{ formatTime(node.startedAt) }} - {{ formatTime(node.completedAt) }}</span>
            </div>
          </div>

          <!-- Node Summary / Error -->
          <div v-if="node.outputSummary" class="text-xs text-text bg-muted/20 p-3 rounded-xl">
            <div class="font-semibold text-text-muted mb-1">执行摘要:</div>
            <p class="leading-relaxed">{{ node.outputSummary }}</p>
          </div>

          <div v-if="node.error" class="text-xs text-danger bg-danger/10 p-3 rounded-xl border border-danger/20">
            <div class="font-semibold mb-1">错误信息:</div>
            <p class="leading-relaxed font-mono">{{ node.error }}</p>
          </div>

          <!-- Violation Paths (Path violation check) -->
          <div
            v-if="node.violationPaths && node.violationPaths.length > 0"
            class="text-xs text-danger bg-rose-500/10 p-3 rounded-xl border border-rose-500/25"
          >
            <div class="font-semibold flex items-center gap-1 text-rose-700 dark:text-rose-300 mb-1">
              <AlertCircle class="w-4 h-4" />
              越界修改路径 (不允许修改的受保护文件):
            </div>
            <ul class="list-disc list-inside font-mono space-y-0.5">
              <li v-for="p in node.violationPaths" :key="p">{{ p }}</li>
            </ul>
          </div>

          <!-- Node Footer Meta -->
          <div class="flex flex-wrap items-center justify-between gap-2 text-xs text-text-muted pt-1">
            <div class="flex flex-wrap items-center gap-4">
              <span v-if="node.sessionId" class="font-mono">会话: {{ node.sessionId }}</span>
              <span v-if="node.changedFiles && node.changedFiles.length > 0" class="flex items-center gap-1 text-primary">
                <FileCode class="w-3.5 h-3.5" />
                变更文件: {{ node.changedFiles.length }} 个
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Tab 2: Virtualized Events Stream (10,000 events capable, Trap 5) -->
    <div v-else-if="activeTab === 'events'" class="space-y-3">
      <!-- Controls -->
      <div class="flex flex-wrap items-center justify-between gap-3 p-3 bg-panel rounded-xl border border-border-subtle text-xs">
        <div class="flex flex-wrap items-center gap-3">
          <div class="relative w-48">
            <Search class="absolute left-2.5 top-2 w-3.5 h-3.5 text-text-muted" />
            <input
              v-model="taskStore.eventSearch"
              type="text"
              placeholder="搜索事件与报文..."
              class="hq-form-control w-full pl-8 pr-2 py-1 bg-surface border border-border-subtle rounded-lg text-text placeholder:text-text-muted"
            />
          </div>

          <select
            v-model="taskStore.eventFilterType"
            class="hq-form-control px-2 py-1 bg-surface border border-border-subtle rounded-lg text-text"
          >
            <option value="all">全部事件类型</option>
            <option value="agent.progress">agent.progress (进度)</option>
            <option value="agent.tool_call">agent.tool_call (工具调用)</option>
            <option value="node.resolved">node.resolved (角色解析)</option>
            <option value="agent.started">agent.started (会话开始)</option>
            <option value="agent.completed">agent.completed (节点完成)</option>
            <option value="agent.failed">agent.failed (节点失败)</option>
            <option value="task.status_changed">task.status_changed (状态迁移)</option>
            <option value="approval.required">approval.required (触发审批)</option>
          </select>

          <select
            v-model="taskStore.eventFilterNodeId"
            class="hq-form-control px-2 py-1 bg-surface border border-border-subtle rounded-lg text-text"
          >
            <option value="all">全部节点</option>
            <option v-for="node in taskStore.currentNodes" :key="node.id" :value="node.id">
              {{ node.id }} ({{ node.roleId }})
            </option>
          </select>
        </div>

        <div class="flex items-center gap-3">
          <label class="inline-flex items-center gap-1.5 cursor-pointer text-text-muted hover:text-text">
            <input v-model="autoScrollEvents" type="checkbox" class="hq-form-choice rounded border-border-subtle" />
            自动滚动至最新
          </label>
          <span class="text-text-muted">共 {{ taskStore.filteredEvents.length }} 条事件</span>
        </div>
      </div>

      <!-- Virtualized Event List -->
      <HqVirtualList
        ref="virtualListRef"
        :items="taskStore.filteredEvents"
        :item-height="44"
        container-height="540px"
      >
        <template #default="{ item: evt }">
          <div
            class="px-3 py-1.5 border-b border-border-subtle hover:bg-hover/60 flex items-center justify-between text-xs font-mono transition-colors"
          >
            <div class="flex items-center gap-2.5 overflow-hidden">
              <span class="text-text-muted shrink-0 w-12 text-right">#{{ evt.seq }}</span>
              <span class="text-text-muted shrink-0 text-[11px]">{{ formatTime(evt.occurredAt) }}</span>
              <span
                class="px-1.5 py-0.5 rounded text-[11px] font-semibold shrink-0"
                :class="
                  evt.type.includes('failed') || evt.type.includes('violation')
                    ? 'bg-danger/15 text-danger'
                    : evt.type.includes('completed')
                    ? 'bg-success/15 text-success'
                    : evt.type.includes('approval')
                    ? 'bg-amber-500/15 text-amber-700 dark:text-amber-300'
                    : 'bg-primary/10 text-primary'
                "
              >
                {{ evt.type }}
              </span>

              <span v-if="evt.nodeId" class="text-text-muted shrink-0 text-[11px]">
                [{{ evt.nodeId }}]
              </span>

              <!-- Message preview -->
              <span class="text-text truncate max-w-md">
                {{
                  (evt.payload as any)?.message ||
                  (evt.payload as any)?.result?.summary ||
                  (evt.payload as any)?.targetResource ||
                  JSON.stringify(evt.payload)
                }}
              </span>
            </div>

            <button
              class="text-text-muted hover:text-primary shrink-0 ml-2 text-[11px]"
              @click="toggleExpandEvent(evt.eventId)"
            >
              {{ expandedEventIds.has(evt.eventId) ? '收起' : '详情' }}
            </button>
          </div>
        </template>
      </HqVirtualList>
    </div>

    <!-- Tab 3: Artifacts -->
    <div v-else-if="activeTab === 'artifacts'" class="space-y-4">
      <div
        v-if="taskStore.currentArtifacts.length === 0"
        class="p-12 text-center bg-panel rounded-xl border border-border-subtle text-text-muted text-xs"
      >
        该任务尚未产出报告或构建文件。
      </div>

      <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <div
          v-for="art in taskStore.currentArtifacts"
          :key="art.id"
          class="p-4 bg-panel rounded-xl border border-border-subtle shadow-2xs space-y-2"
        >
          <div class="flex items-center justify-between">
            <span class="px-2 py-0.5 text-[11px] rounded bg-primary/10 text-primary font-semibold uppercase">
              {{ art.type }}
            </span>
            <span class="text-xs text-text-muted">{{ formatDuration(art.sizeBytes) }}</span>
          </div>
          <h4 class="font-bold text-sm text-text">{{ art.title }}</h4>
          <p class="text-xs font-mono text-text-muted truncate" :title="art.path">
            {{ art.path }}
          </p>
          <div class="text-[11px] text-text-muted pt-2 border-t border-border-subtle">
            生成时间: {{ formatTime(art.createdAt) }}
          </div>
        </div>
      </div>
    </div>

    <!-- Tab 4: Worktree & Constraints -->
    <div v-else-if="activeTab === 'worktree'" class="space-y-4 text-xs">
      <div class="p-5 bg-panel rounded-xl border border-border-subtle space-y-4">
        <h3 class="font-bold text-sm text-text">工作区与独立 Worktree 隔离</h3>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div class="p-3 bg-muted/20 rounded-xl">
            <span class="text-text-muted block mb-1">主工作区路径:</span>
            <span class="font-mono text-text break-all">{{ currentTask?.worktreePath || '默认仓库根路径' }}</span>
          </div>

          <div class="p-3 bg-muted/20 rounded-xl">
            <span class="text-text-muted block mb-1">隔离工作分支:</span>
            <span class="font-mono text-text">{{ currentTask?.branch || 'work/w4-frontend' }}</span>
          </div>
        </div>

        <div>
          <span class="font-semibold text-text block mb-1.5">允许修改路径 (Allowed Paths):</span>
          <div class="p-3 bg-muted/20 rounded-xl font-mono space-y-1">
            <div v-if="!currentTask?.allowedPaths || currentTask.allowedPaths.length === 0" class="text-text-muted">
              未指定限制（默认允许角色权限内路径）
            </div>
            <div v-for="p in currentTask?.allowedPaths" :key="p" class="text-text">
              • {{ p }}
            </div>
          </div>
        </div>

        <div>
          <span class="font-semibold text-text block mb-1.5">验收自动化命令 (Acceptance):</span>
          <div class="p-3 bg-muted/20 rounded-xl font-mono space-y-1">
            <div v-if="!currentTask?.acceptance || currentTask.acceptance.length === 0" class="text-text-muted">
              未配置验收命令
            </div>
            <div v-for="cmd in currentTask?.acceptance" :key="cmd" class="text-primary font-bold">
              $ {{ cmd }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Cancel Modal (Trap 2 safe cancel confirmation) -->
    <HqDialog
      :open="isCancelModalOpen"
      title="取消任务确认"
      description="向各角色 Agent 下发优雅停止信号"
      @close="isCancelModalOpen = false"
    >
      <div class="space-y-3 py-2 text-xs">
        <p class="text-text leading-relaxed">
          取消任务将向正在执行的各角色 Agent 下发优雅停止信号。如果 Adapter 无法响应中断，任务将被标记失败并提示孤儿进程信息。
        </p>
        <div>
          <label class="block font-medium text-text mb-1">取消原因说明 (可选)</label>
          <HqInput v-model="cancelReason" placeholder="例如：需求变更或发现了新的前置依赖..." />
        </div>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-2">
          <HqButton size="sm" variant="secondary" @click="isCancelModalOpen = false">
            取消
          </HqButton>
          <HqButton
            size="sm"
            variant="danger"
            :disabled="taskStore.isActionLoading"
            @click="handleCancelConfirm"
          >
            确认取消
          </HqButton>
        </div>
      </template>
    </HqDialog>

    <!-- Append Instruction Modal (Trap 1: Only available when idle) -->
    <HqDialog
      :open="isAppendModalOpen"
      title="追加任务指令"
      description="在节点空闲间隙向任务追加后续约束或补充说明"
      @close="isAppendModalOpen = false"
    >
      <div class="space-y-3 py-2 text-xs">
        <p class="text-text-muted">
          在节点空闲间隙向任务追加后续约束或补充说明。正在运行的节点不会被打断。
        </p>
        <div>
          <label class="block font-medium text-text mb-1">
            指令内容 <span class="text-danger">*</span>
          </label>
          <HqTextarea
            v-model="appendInstructionText"
            :rows="4"
            placeholder="请在此输入补充给团队后续角色的指令..."
          />
        </div>
        <div
          v-if="appendError"
          class="p-2.5 rounded-[var(--radius-sm)] bg-danger/10 text-danger border border-danger/20 flex items-center gap-2"
        >
          <AlertCircle class="w-4 h-4 shrink-0" />
          <span>{{ appendError }}</span>
        </div>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-2">
          <HqButton size="sm" variant="secondary" @click="isAppendModalOpen = false">
            取消
          </HqButton>
          <HqButton
            size="sm"
            variant="primary"
            :disabled="!appendInstructionText.trim() || taskStore.isActionLoading"
            @click="handleAppendInstruction"
          >
            提交追加
          </HqButton>
        </div>
      </template>
    </HqDialog>
  </div>
</template>
