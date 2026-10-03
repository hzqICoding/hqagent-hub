<script setup lang="ts">
import RuntimeIcon from '@/shared/runtime/RuntimeIcon.vue'
import { getLocalChatGateway } from '@/shared/api'
import type { AgentView } from '@hqagent/protocol'
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app.store'
import { useApprovalStore } from '@/stores/approval.store'
import type { ApprovalView, DangerousAction, RiskLevel } from '@hqagent/protocol'
import {
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  Terminal,
  UserCheck,
  ExternalLink,
} from 'lucide-vue-next'
import {
  HqButton,
  HqInput,
  HqDialog,
  LoadingState,
  HqEmptyState,
  HqErrorState,
  OfflineState,
  useToast,
} from '@/shared/ui'

const router = useRouter()
const appStore = useAppStore()
const approvalStore = useApprovalStore()
const toast = useToast()
const agents = ref<AgentView[]>([])

// Confirmation modal states
const isConfirmModalOpen = ref(false)
const selectedApproval = ref<ApprovalView | null>(null)
const confirmRiskAcknowledged = ref(false)
const confirmReason = ref('')

// Rejection modal states
const isRejectModalOpen = ref(false)
const rejectReason = ref('')

onMounted(async () => {
  await approvalStore.fetchApprovals()
  try { agents.value = await getLocalChatGateway().listLocalAgents() } catch { /* Runtime stays unknown if the index is unavailable. */ }
})

function getRiskBadge(level: RiskLevel) {
  switch (level) {
    case 'critical':
      return { label: '极高风险 (Critical)', class: 'bg-rose-500/20 text-rose-700 dark:text-rose-300 border-rose-500/40 font-bold animate-pulse' }
    case 'high':
      return { label: '高风险 (High)', class: 'bg-amber-500/20 text-amber-800 dark:text-amber-200 border-amber-500/40 font-semibold' }
    case 'medium':
      return { label: '中等风险 (Medium)', class: 'bg-yellow-500/15 text-yellow-800 dark:text-yellow-200 border-yellow-500/30' }
    default:
      return { label: '低风险 (Low)', class: 'bg-panel text-text-muted border-border' }
  }
}

function getActionLabel(action: DangerousAction) {
  switch (action) {
    case 'git_push':
      return '远程仓库推送 (git push)'
    case 'git_merge':
      return '分支代码合并 (git merge)'
    case 'delete':
      return '文件或目录删除 (delete)'
    case 'shell':
      return '终端 Shell 执行 (shell)'
    case 'deploy':
      return '生产环境发布 (deploy)'
    case 'db_migrate':
      return '数据库结构迁移 (db_migrate)'
    case 'network':
      return '外网网络访问 (network)'
    default:
      return action
  }
}

function openApproveDialog(appr: ApprovalView) {
  selectedApproval.value = appr
  confirmRiskAcknowledged.value = false
  confirmReason.value = ''
  isConfirmModalOpen.value = true
}

function openRejectDialog(appr: ApprovalView) {
  selectedApproval.value = appr
  rejectReason.value = ''
  isRejectModalOpen.value = true
}

async function handleConfirmApprove() {
  if (!selectedApproval.value) return
  try {
    await approvalStore.respondApproval(selectedApproval.value.id, {
      decision: 'approve',
      reason: confirmReason.value || undefined,
    })
    isConfirmModalOpen.value = false
    toast.success(`已批准操作：${getActionLabel(selectedApproval.value.action)}`)
  } catch (err: unknown) {
    toast.danger(err instanceof Error ? err.message : '审批失败')
  }
}

async function handleConfirmReject() {
  if (!selectedApproval.value) return
  try {
    await approvalStore.respondApproval(selectedApproval.value.id, {
      decision: 'reject',
      reason: rejectReason.value || '人工拒绝该操作',
    })
    isRejectModalOpen.value = false
    toast.info(`已拒绝操作：${getActionLabel(selectedApproval.value.action)}`)
  } catch (err: unknown) {
    toast.danger(err instanceof Error ? err.message : '拒绝失败')
  }
}

function formatTime(timestamp?: string) {
  if (!timestamp) return '-'
  return new Date(timestamp).toLocaleString()
}
</script>

<template>
  <div class="p-6 space-y-6 max-w-7xl mx-auto select-none">
    <!-- Top Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <div class="p-2 bg-amber-500/10 text-amber-600 dark:text-amber-400 rounded-[var(--radius-md)]">
          <ShieldAlert class="w-6 h-6" />
        </div>
        <div>
          <h1 class="text-xl font-bold text-text">安全审批中心</h1>
          <p class="text-sm text-text-muted">
            对 Agent 触发的代码推送、Shell 运行、文件删除等高风险行为进行人工二次审核
          </p>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <span
          v-if="approvalStore.pendingCount > 0"
          class="px-3 py-1 text-xs font-bold rounded-full bg-amber-500/20 text-amber-800 dark:text-amber-200 border border-amber-500/40 animate-pulse"
        >
          {{ approvalStore.pendingCount }} 个待处理审批
        </span>
      </div>
    </div>

    <!-- Filter Tabs -->
    <div class="flex items-center gap-2 border-b border-border text-xs">
      <button
        class="px-4 py-2 font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5"
        :class="
          approvalStore.filterStatus === 'pending'
            ? 'border-primary text-primary'
            : 'border-transparent text-text-muted hover:text-text'
        "
        @click="approvalStore.filterStatus = 'pending'"
      >
        <ShieldAlert class="w-4 h-4" />
        待处理审批 ({{ approvalStore.pendingApprovals.length }})
      </button>

      <button
        class="px-4 py-2 font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5"
        :class="
          approvalStore.filterStatus === 'all'
            ? 'border-primary text-primary'
            : 'border-transparent text-text-muted hover:text-text'
        "
        @click="approvalStore.filterStatus = 'all'"
      >
        <Clock class="w-4 h-4" />
        所有审批记录 ({{ approvalStore.approvals.length }})
      </button>
    </div>

    <!-- 4 Page States -->
    <OfflineState v-if="appStore.isOffline" @retry="approvalStore.fetchApprovals" />
    <LoadingState v-else-if="approvalStore.isLoading" message="正在加载审批项..." />
    <HqErrorState
      v-else-if="approvalStore.error"
      title="获取审批列表失败"
      :message="approvalStore.error"
      @retry="approvalStore.fetchApprovals"
    />
    <HqEmptyState
      v-else-if="approvalStore.filteredApprovals.length === 0"
      title="暂无待处理审批"
      message="目前没有任何需要人工授权的危险操作。"
    />

    <!-- Approvals List -->
    <div v-else class="space-y-4">
      <div
        v-for="appr in approvalStore.filteredApprovals"
        :key="appr.id"
        class="p-5 bg-panel rounded-[var(--radius-md)] border shadow-xs space-y-3 transition-colors"
        :class="
          appr.status === 'pending'
            ? 'border-amber-500/40 hover:border-amber-500/70'
            : 'border-border'
        "
      >
        <!-- Item Header -->
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-3">
          <div class="flex flex-wrap items-center gap-2">
            <span class="font-mono text-xs text-text-muted font-bold">{{ appr.id }}</span>
            <span
              class="px-2 py-0.5 text-xs rounded border"
              :class="getRiskBadge(appr.riskLevel).class"
            >
              {{ getRiskBadge(appr.riskLevel).label }}
            </span>

            <span class="font-semibold text-xs text-text">
              {{ getActionLabel(appr.action) }}
            </span>
          </div>

          <!-- Status badge -->
          <div class="flex items-center gap-2">
            <span
              v-if="appr.status === 'pending'"
              class="px-2 py-0.5 text-xs rounded bg-amber-500/15 text-amber-700 dark:text-amber-300 font-semibold"
            >
              等待审批
            </span>
            <span
              v-else-if="appr.status === 'approved'"
              class="px-2 py-0.5 text-xs rounded bg-success/15 text-success font-semibold"
            >
              已批准
            </span>
            <span
              v-else-if="appr.status === 'rejected'"
              class="px-2 py-0.5 text-xs rounded bg-danger/15 text-danger font-semibold"
            >
              已拒绝
            </span>
            <span
              v-else-if="appr.status === 'expired'"
              class="px-2 py-0.5 text-xs rounded bg-panel text-text-muted font-semibold"
            >
              已过期 (APPROVAL_EXPIRED)
            </span>
          </div>
        </div>

        <!-- Target Resource Box -->
        <div class="p-3 bg-surface rounded-[var(--radius-sm)] border border-border space-y-1">
          <div class="text-xs text-text-muted font-semibold flex items-center gap-1">
            <Terminal class="w-3.5 h-3.5" />
            将要作用的受控资源或执行命令 (Target Resource):
          </div>
          <div class="font-mono text-xs text-text font-bold break-all">
            {{ appr.targetResource }}
          </div>
        </div>

        <!-- Task & Agent Meta -->
        <div class="flex flex-wrap items-center justify-between gap-4 text-xs text-text-muted">
          <div class="flex flex-wrap items-center gap-4">
            <span class="inline-flex items-center gap-1">
              <UserCheck class="w-3.5 h-3.5 text-primary" />
              <RuntimeIcon :agent="agents.find(agent=>agent.id===appr.requestAgentId)?.adapterId" class="inline-block w-4 h-4" />请求 Agent: {{ appr.requestAgentName }}
            </span>
            <span>•</span>
            <span>发起时间: {{ formatTime(appr.requestedAt) }}</span>
            <span v-if="appr.taskId">•</span>
            <button
              v-if="appr.taskId"
              class="inline-flex items-center gap-1 text-primary hover:underline"
              @click="router.push(`/tasks/${appr.taskId}`)"
            >
              关联任务: {{ appr.taskObjective || appr.taskId }}
              <ExternalLink class="w-3 h-3" />
            </button>
          </div>

          <!-- Pending Action Buttons -->
          <div v-if="appr.status === 'pending'" class="flex items-center gap-2">
            <HqButton
              variant="danger"
              size="sm"
              :disabled="approvalStore.isActionLoading"
              @click="openRejectDialog(appr)"
            >
              <XCircle class="w-3.5 h-3.5 mr-1" />
              拒绝
            </HqButton>

            <HqButton
              variant="primary"
              size="sm"
              :disabled="approvalStore.isActionLoading"
              @click="openApproveDialog(appr)"
            >
              <CheckCircle2 class="w-3.5 h-3.5 mr-1" />
              批准执行
            </HqButton>
          </div>
        </div>
      </div>
    </div>

    <!-- Secondary Confirmation Dialog for Dangerous Action (Safety Redline) -->
    <HqDialog
      :open="isConfirmModalOpen"
      title="高危操作二次确认"
      description="敏感操作需要人工知晓风险并二次核准"
      @close="isConfirmModalOpen = false"
    >
      <div class="space-y-4 py-2 text-xs">
        <div class="p-3 rounded-[var(--radius-sm)] bg-danger/10 border border-danger/30 text-danger space-y-1">
          <div class="flex items-center gap-2 font-bold text-sm">
            <AlertTriangle class="w-4 h-4 shrink-0" />
            敏感风险警告
          </div>
          <p class="leading-relaxed">
            该动作涉及对本地系统、Git 远程仓库或工作目录的写操作。请核验下列命令是否符合预期：
          </p>
        </div>

        <div class="p-3 bg-surface rounded-[var(--radius-sm)] border border-border">
          <span class="text-text-muted block mb-1">受影响资源 / 命令:</span>
          <span class="font-mono font-bold text-text break-all">
            {{ selectedApproval?.targetResource }}
          </span>
        </div>

        <div>
          <label class="block font-medium text-text mb-1">审核批注意见 (可选)</label>
          <HqInput v-model="confirmReason" placeholder="例如：经审查代码无误，允许推送" />
        </div>

        <!-- Mandatory risk checkbox for high-risk actions -->
        <div
          v-if="approvalStore.isHighRiskAction(selectedApproval?.action || 'deploy')"
          class="p-3 rounded-[var(--radius-sm)] bg-surface border border-border flex items-start gap-2.5 cursor-pointer"
          @click="confirmRiskAcknowledged = !confirmRiskAcknowledged"
        >
          <input
            v-model="confirmRiskAcknowledged"
            type="checkbox"
            class="hq-form-choice mt-0.5 rounded border-border"
            @click.stop
          />
          <div class="text-xs text-text leading-tight">
            <span class="font-bold text-danger">我已人工核验并完全知晓风险</span>，确认允许 Agent 执行该高危动作。
          </div>
        </div>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-2">
          <HqButton size="sm" variant="secondary" @click="isConfirmModalOpen = false">
            取消
          </HqButton>
          <HqButton
            size="sm"
            variant="danger"
            :disabled="
              approvalStore.isHighRiskAction(selectedApproval?.action || 'deploy') &&
              !confirmRiskAcknowledged
            "
            @click="handleConfirmApprove"
          >
            确认授权放行
          </HqButton>
        </div>
      </template>
    </HqDialog>

    <!-- Reject Dialog -->
    <HqDialog
      :open="isRejectModalOpen"
      title="拒绝审批"
      description="拒绝后将中止该节点的敏感动作"
      @close="isRejectModalOpen = false"
    >
      <div class="space-y-3 py-2 text-xs">
        <p class="text-text">
          拒绝此操作后，当前节点将被中止并标记失败，任务将停止继续执行该敏感操作。
        </p>
        <div>
          <label class="block font-medium text-text mb-1">拒绝原因说明</label>
          <HqInput v-model="rejectReason" placeholder="例如：命令参数越界，不允许直接推送到 main 分支" />
        </div>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-2">
          <HqButton size="sm" variant="secondary" @click="isRejectModalOpen = false">
            取消
          </HqButton>
          <HqButton size="sm" variant="danger" @click="handleConfirmReject">
            确认拒绝
          </HqButton>
        </div>
      </template>
    </HqDialog>
  </div>
</template>
