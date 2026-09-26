<script setup lang="ts">
import { ref, computed } from 'vue'
import { useChatStore } from '@/stores/chat.store'
import {
  HqButton,
  HqBadge,
  HqDialog,
  HqMarkdown,
  ResolveSourceBadge,
} from '@/shared/ui'
import {
  Layers,
  FileCode2,
  Play,
  Pause,
  RotateCcw,
  XCircle,
  ShieldAlert,
  Package,
  X,
} from 'lucide-vue-next'

const emit = defineEmits<{ (e: 'close'): void }>()

const chatStore = useChatStore()

// Cancel modal state
const isCancelModalOpen = ref(false)
const cancelReason = ref('')

const activeRun = computed(() => chatStore.activeRun)
const task = computed(() => activeRun.value?.task)
const scene = computed(() => activeRun.value?.sceneSnapshot)

const allChangedFiles = computed(() => {
  const set = new Set<string>()
  task.value?.nodes?.forEach((n) => n.changedFiles?.forEach((f) => set.add(f)))
  return Array.from(set)
})

const allViolationPaths = computed(() => {
  const set = new Set<string>()
  task.value?.nodes?.forEach((n) => n.violationPaths?.forEach((p) => set.add(p)))
  return Array.from(set)
})

function handleCancelClick() {
  cancelReason.value = ''
  isCancelModalOpen.value = true
}

async function confirmCancel() {
  if (!activeRun.value) return
  isCancelModalOpen.value = false
  await chatStore.controlRun(activeRun.value.id, 'cancel', cancelReason.value)
}

function handlePauseClick() {
  if (!activeRun.value) return
  chatStore.controlRun(activeRun.value.id, 'pause')
}

function handleResumeClick() {
  if (!activeRun.value) return
  chatStore.controlRun(activeRun.value.id, 'resume')
}

function handleRetryClick() {
  if (!activeRun.value) return
  chatStore.controlRun(activeRun.value.id, 'retry')
}

async function handleApprove(decision: 'approve' | 'reject') {
  if (!chatStore.pendingApproval) return
  await chatStore.respondApproval(chatStore.pendingApproval.id, { decision })
}

function getNodeStatusBadge(status: string) {
  switch (status) {
    case 'resolving':
      return { label: '解析中', class: 'bg-cyan-500/15 text-cyan-700 dark:text-cyan-300 border-cyan-500/40 animate-pulse' }
    case 'running':
      return { label: '执行中', class: 'bg-primary/15 text-primary border-primary/30 animate-pulse' }
    case 'waiting_approval':
      return { label: '等待审批', class: 'bg-warning/15 text-warning border-warning/30' }
    case 'succeeded':
      return { label: '完成', class: 'bg-success/15 text-success border-success/30' }
    case 'failed':
      return { label: '失败', class: 'bg-danger/15 text-danger border-danger/30' }
    case 'skipped':
      return { label: '已跳过', class: 'bg-panel text-text-muted border-dashed border-border' }
    default:
      return { label: status, class: 'bg-panel text-text-muted border-border' }
  }
}

function getNodeTitle(node: NonNullable<typeof task.value>['nodes'][number]) {
  if (node.phase === 'acceptance' && node.roleId === 'planner') {
    const reviewer = scene.value?.roles.find((role) => role.roleId === 'reviewer')
    return reviewer?.roleName ? `${reviewer.roleName}（原规划者验收）` : '原规划者验收'
  }
  return scene.value?.roles.find((role) => role.roleId === node.roleId)?.roleName || node.roleId
}

function hasCustomNodeName(node: NonNullable<typeof task.value>['nodes'][number]) {
  return getNodeTitle(node) !== node.roleId
}

function getReviewVerdictMeta(verdict: string) {
  switch (verdict) {
    case 'passed':
      return { label: '验收通过', class: 'bg-success/10 text-success border-success/30' }
    case 'changes_requested':
      return { label: '验收不通过：需要修改', class: 'bg-danger/10 text-danger border-danger/30' }
    case 'insufficient_evidence':
      return { label: '证据不足', class: 'bg-warning/10 text-warning border-warning/30' }
    default:
      return { label: verdict, class: 'bg-panel text-text-muted border-border' }
  }
}
</script>

<template>
  <aside class="w-full sm:w-[380px] md:w-[360px] lg:w-[400px] h-full border-l border-border bg-panel flex flex-col shrink-0 overflow-y-auto overflow-x-hidden select-none">
    <!-- Header -->
    <div class="p-3.5 border-b border-border flex items-center justify-between shrink-0">
      <div class="flex items-center gap-2 min-w-0">
        <Layers class="w-4 h-4 text-primary shrink-0" />
        <h3 class="text-xs font-semibold text-text truncate">本轮场景与执行详情</h3>
      </div>

      <div class="flex items-center gap-1.5 shrink-0">
        <HqBadge
          v-if="activeRun"
          :variant="
            activeRun.status === 'succeeded'
              ? 'success'
              : activeRun.status === 'running'
              ? 'primary'
              : activeRun.status === 'waiting_approval'
              ? 'warning'
              : activeRun.status === 'failed'
              ? 'danger'
              : 'neutral'
          "
          size="sm"
        >
          {{ activeRun.status }}
        </HqBadge>

        <button
          type="button"
          class="min-w-[44px] min-h-[44px] p-2 rounded-lg hover:bg-panel-hover text-text-muted hover:text-text transition-colors flex items-center justify-center cursor-pointer"
          title="关闭执行详情"
          aria-label="关闭执行详情"
          @click="emit('close')"
        >
          <X class="w-4 h-4" />
        </button>
      </div>
    </div>

    <!-- Empty State -->
    <div v-if="!activeRun" class="flex-1 p-6 text-center text-xs text-text-muted flex flex-col items-center justify-center">
      <Layers class="w-8 h-8 text-text-muted/40 mb-2" />
      <p>当前无激活或已完成的 Run 轮次</p>
      <p class="text-[11px] text-text-muted/60 mt-1">在下方输入指令发送后将生成本轮详情</p>
    </div>

    <div v-else class="p-3.5 space-y-4 text-xs">
      <!-- Approval Alert if pending -->
      <div
        v-if="chatStore.pendingApproval"
        class="p-3 rounded-[var(--radius-md)] bg-warning/10 border border-warning/30 space-y-2"
      >
        <div class="flex items-start gap-2">
          <ShieldAlert class="w-4 h-4 text-warning shrink-0 mt-0.5" />
          <div>
            <p class="font-medium text-warning text-xs">高危操作审批申请</p>
            <p class="text-[11px] text-text mt-0.5">
              动作：<span class="font-mono font-medium">{{ chatStore.pendingApproval.action }}</span>
            </p>
            <p class="text-[11px] text-text-muted">
              目标：<span class="font-mono">{{ chatStore.pendingApproval.targetResource }}</span>
            </p>
          </div>
        </div>

        <div class="flex items-center gap-2 pt-1">
          <HqButton size="sm" variant="primary" @click="handleApprove('approve')">
            批准放行
          </HqButton>
          <HqButton size="sm" variant="danger" @click="handleApprove('reject')">
            拒绝拦截
          </HqButton>
        </div>
      </div>

      <!-- Action Control Buttons -->
      <div class="p-2.5 rounded-[var(--radius-sm)] bg-bg-app border border-border flex items-center justify-between gap-1.5">
        <HqButton
          v-if="activeRun.status === 'running'"
          size="sm"
          variant="secondary"
          :disabled="chatStore.isActionLoading || chatStore.isActiveConversationArchived"
          :title="chatStore.isActiveConversationArchived ? '请先恢复任务' : undefined"
          @click="handlePauseClick"
        >
          <Pause class="w-3 h-3 mr-1 text-warning" />
          节点间暂停
        </HqButton>

        <HqButton
          v-else-if="activeRun.status === 'paused'"
          size="sm"
          variant="secondary"
          :disabled="chatStore.isActionLoading || chatStore.isActiveConversationArchived"
          :title="chatStore.isActiveConversationArchived ? '请先恢复任务' : undefined"
          @click="handleResumeClick"
        >
          <Play class="w-3 h-3 mr-1 text-success" />
          继续执行
        </HqButton>

        <HqButton
          v-if="activeRun.status === 'failed'"
          size="sm"
          variant="secondary"
          :disabled="chatStore.isActionLoading || chatStore.isActiveConversationArchived"
          :title="chatStore.isActiveConversationArchived ? '请先恢复任务' : undefined"
          @click="handleRetryClick"
        >
          <RotateCcw class="w-3 h-3 mr-1" />
          重试
        </HqButton>

        <HqButton
          v-if="activeRun.status === 'running' || activeRun.status === 'paused' || activeRun.status === 'waiting_approval'"
          size="sm"
          variant="danger"
          :disabled="chatStore.isActionLoading"
          @click="handleCancelClick"
        >
          <XCircle class="w-3 h-3 mr-1" />
          取消任务
        </HqButton>
      </div>

      <!-- Scene Snapshot Info (Immutable config for this run) -->
      <div class="space-y-2">
        <div class="flex items-center justify-between text-[11px] text-text-muted">
          <span class="font-medium text-text">本轮场景快照 (SceneSnapshot)</span>
          <span class="font-mono">v{{ scene?.version }}</span>
        </div>

        <div class="p-2.5 rounded-[var(--radius-sm)] bg-bg-app border border-border space-y-2">
          <div class="flex items-center justify-between">
            <span class="font-medium text-text">{{ scene?.name }}</span>
            <HqBadge size="sm" variant="neutral">{{ scene?.id }}</HqBadge>
          </div>
          <p class="text-[11px] text-text-muted leading-relaxed break-words">
            {{ scene?.description }}
          </p>
          <div class="flex items-center justify-between gap-2 text-[11px]">
            <span class="text-text-muted">验收方式</span>
            <HqBadge size="sm" :variant="(scene?.reviewMode ?? 'independent') === 'original_planner' ? 'info' : 'neutral'">
              {{ (scene?.reviewMode ?? 'independent') === 'original_planner' ? '原规划者验收' : '独立 Reviewer' }}
            </HqBadge>
          </div>

          <!-- Roles in Snapshot -->
          <div class="pt-2 border-t border-border space-y-1.5">
            <span class="text-[10px] text-text-muted uppercase tracking-wider block">参与角色分配</span>
            <div
              v-for="role in scene?.roles"
              :key="role.roleId"
              class="p-1.5 rounded bg-panel border border-border/80 text-[11px] space-y-0.5"
            >
              <div class="flex items-center justify-between gap-1 min-w-0">
                <span class="font-medium text-text truncate">{{ role.roleName || role.roleId }}</span>
                <span class="text-[10px] text-text-muted font-mono truncate">{{ role.modelId || '默认模型' }}</span>
              </div>
              <div class="flex items-center justify-between gap-1 text-[10px] text-text-muted min-w-0">
                <span class="truncate">{{ role.roleId }} · Agent: {{ role.agentInstanceId }}</span>
                <span v-if="role.reasoningEffort" class="shrink-0">effort: {{ role.reasoningEffort }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Steps & Task Nodes -->
      <div v-if="task?.nodes && task.nodes.length > 0" class="space-y-2">
        <span class="font-medium text-text text-[11px] block">执行步骤 (Nodes)</span>
        <div class="space-y-1.5">
          <div
            v-for="node in task.nodes"
            :key="node.id"
            class="p-2 rounded-[var(--radius-sm)] bg-bg-app border border-border space-y-1.5"
          >
            <div class="flex items-center justify-between gap-1">
              <span class="font-medium text-text text-xs truncate">
                {{ getNodeTitle(node) }}
                <span v-if="hasCustomNodeName(node)" class="ml-1 text-[10px] font-mono text-text-muted">{{ node.roleId }}</span>
              </span>
              <span
                class="px-1.5 py-0.5 rounded text-[10px] font-medium border shrink-0"
                :class="getNodeStatusBadge(node.status).class"
              >
                {{ getNodeStatusBadge(node.status).label }}
              </span>
            </div>

            <div class="flex items-center justify-between text-[10px] gap-1 min-w-0">
              <span class="text-text-muted truncate">{{ node.resolvedAgentName }}</span>
              <ResolveSourceBadge
                :source="node.resolveSource"
                :is-fallback="node.isFallback"
                :fallback-reason="node.fallbackReason"
                class="shrink-0"
              />
            </div>

            <div
              v-if="node.sessionId || node.externalSessionId"
              class="p-1.5 rounded bg-panel border border-border/80 text-[10px] font-mono text-text-muted space-y-1 break-all"
            >
              <div v-if="node.sessionId">Hub Session: {{ node.sessionId }}</div>
              <div v-if="node.externalSessionId">原生 Session: {{ node.externalSessionId }}</div>
            </div>

            <div v-if="node.phase === 'acceptance'" class="space-y-1 text-[10px]">
              <div v-if="node.reviewEvidenceId" class="font-mono text-text-muted break-all">
                验收证据: {{ node.reviewEvidenceId }}
              </div>
              <div v-if="node.reviewSourceNodeId" class="font-mono text-text-muted break-all">
                来源节点: {{ node.reviewSourceNodeId }}
              </div>
              <div
                v-if="node.reviewVerdict"
                class="px-2 py-1.5 rounded border font-medium"
                :class="getReviewVerdictMeta(node.reviewVerdict).class"
              >
                {{ getReviewVerdictMeta(node.reviewVerdict).label }}
              </div>
              <div
                v-else-if="node.status === 'failed' || node.error"
                class="px-2 py-1.5 rounded border bg-danger/10 text-danger border-danger/30"
              >
                验收执行出错，未产生有效审核结论<span v-if="node.error">：{{ node.error }}</span>
              </div>
              <div v-else class="text-text-muted">尚未产生验收结论</div>
            </div>

            <div v-if="node.outputSummary" class="mt-1.5 p-2 rounded-lg bg-bg-app/60 border border-border/50 text-[11px] leading-relaxed break-words">
              <HqMarkdown :content="node.outputSummary" />
            </div>
          </div>
        </div>
      </div>

      <!-- Changed Files -->
      <div v-if="allChangedFiles.length > 0" class="space-y-2">
        <div class="flex items-center justify-between text-[11px]">
          <span class="font-medium text-text">真实变更文件</span>
          <span class="text-text-muted">{{ allChangedFiles.length }} 个文件</span>
        </div>
        <div class="p-2 rounded-[var(--radius-sm)] bg-bg-app border border-border max-h-36 overflow-y-auto space-y-1 font-mono text-[11px]">
          <div
            v-for="file in allChangedFiles"
            :key="file"
            class="flex items-center gap-1.5 text-text min-w-0"
          >
            <FileCode2 class="w-3 h-3 text-primary shrink-0" />
            <span class="truncate" :title="file">{{ file }}</span>
          </div>
        </div>
      </div>

      <!-- Violation Paths (Security alert) -->
      <div v-if="allViolationPaths.length > 0" class="space-y-2">
        <div class="flex items-center justify-between text-[11px] text-danger">
          <span class="font-medium">越界修改路径 (违规)</span>
          <span>{{ allViolationPaths.length }} 处</span>
        </div>
        <div class="p-2 rounded-[var(--radius-sm)] bg-danger/10 border border-danger/30 text-danger text-[11px] font-mono space-y-1 overflow-x-auto">
          <div v-for="vp in allViolationPaths" :key="vp" class="break-all">
            {{ vp }}
          </div>
        </div>
      </div>

      <!-- Artifacts -->
      <div v-if="task?.artifacts && task.artifacts.length > 0" class="space-y-2">
        <span class="font-medium text-text text-[11px] block">产物清单 (Artifacts)</span>
        <div class="space-y-1">
          <div
            v-for="art in task.artifacts"
            :key="art.id"
            class="p-2 rounded-[var(--radius-sm)] bg-bg-app border border-border flex items-center justify-between text-xs min-w-0 gap-2"
          >
            <div class="flex items-center gap-1.5 truncate min-w-0">
              <Package class="w-3.5 h-3.5 text-primary shrink-0" />
              <span class="font-medium text-text truncate" :title="art.title">{{ art.title }}</span>
            </div>
            <span class="text-[10px] text-text-muted font-mono shrink-0">
              {{ (art.sizeBytes / 1024).toFixed(1) }} KB
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Cancel Secondary Confirmation Dialog (Trap 2 / Safe Cancel) -->
    <HqDialog
      :open="isCancelModalOpen"
      title="取消任务确认"
      description="向执行中的角色 Agent 下发取消信号"
      @close="isCancelModalOpen = false"
    >
      <div class="space-y-3 py-2 text-xs">
        <p class="text-text leading-relaxed">
          取消任务将下发优雅停止信号。如果 Adapter 无法响应中断，任务将被标记失败并提示未退出的进程。
        </p>
        <div>
          <label class="block font-medium text-text mb-1">取消原因说明 (可选)</label>
          <input
            v-model="cancelReason"
            type="text"
            placeholder="例如：输入参数有误或目标变更..."
            class="w-full px-2.5 py-1.5 text-xs bg-bg-app border border-border rounded text-text focus:outline-none focus:border-primary"
          />
        </div>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-2">
          <HqButton size="sm" variant="secondary" @click="isCancelModalOpen = false">
            再等等
          </HqButton>
          <HqButton size="sm" variant="danger" @click="confirmCancel">
            确认取消
          </HqButton>
        </div>
      </template>
    </HqDialog>
  </aside>
</template>
