import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  ApprovalView,
  ApprovalQuery,
  ApprovalResponseInput,
  DangerousAction,
  RiskLevel,
  ApprovalStatus,
  HubEvent,
  ApprovalRequiredPayload,
  ApprovalResolvedPayload,
} from '@hqagent/protocol'
import { getUiGateway } from '@/shared/api'
import { useAppStore } from './app.store'

export const HIGH_RISK_ACTIONS: readonly DangerousAction[] = [
  'deploy',
  'git_push',
  'git_merge',
  'delete',
  'shell',
  'db_migrate',
] as const

export const useApprovalStore = defineStore('approval', () => {
  const gateway = getUiGateway()
  const appStore = useAppStore()

  // State
  const approvals = ref<ApprovalView[]>([])
  const isLoading = ref<boolean>(false)
  const isActionLoading = ref<boolean>(false)
  const error = ref<string | null>(null)
  const actionError = ref<string | null>(null)

  // Filter
  const filterStatus = ref<ApprovalStatus | 'all'>('pending')
  const filterRiskLevel = ref<RiskLevel | 'all'>('all')
  const filterAction = ref<DangerousAction | 'all'>('all')

  // Computed
  const pendingApprovals = computed(() => approvals.value.filter((a) => a.status === 'pending'))
  const decidedApprovals = computed(() => approvals.value.filter((a) => a.status !== 'pending'))

  const filteredApprovals = computed(() => {
    return approvals.value.filter((appr) => {
      if (filterStatus.value !== 'all' && appr.status !== filterStatus.value) {
        return false
      }
      if (filterRiskLevel.value !== 'all' && appr.riskLevel !== filterRiskLevel.value) {
        return false
      }
      if (filterAction.value !== 'all' && appr.action !== filterAction.value) {
        return false
      }
      return true
    })
  })

  const pendingCount = computed(() => pendingApprovals.value.length)

  // Actions
  async function fetchApprovals(query?: ApprovalQuery) {
    isLoading.value = true
    error.value = null

    try {
      const list = await gateway.listApprovals(query)
      approvals.value = list
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : '获取审批列表失败'
      appStore.addLog({
        level: 'error',
        source: 'ApprovalStore',
        message: `获取审批列表失败: ${error.value}`,
      })
    } finally {
      isLoading.value = false
    }
  }

  async function respondApproval(id: string, input: ApprovalResponseInput): Promise<ApprovalView> {
    isActionLoading.value = true
    actionError.value = null

    try {
      const updated = await gateway.respondApproval(id, input)
      const idx = approvals.value.findIndex((a) => a.id === id)
      if (idx !== -1) {
        approvals.value[idx] = updated
      } else {
        approvals.value.unshift(updated)
      }

      appStore.addLog({
        level: 'info',
        source: 'ApprovalStore',
        message: `审批决策完成: ${id} -> ${input.decision} (${input.reason || '无理由'})`,
      })
      return updated
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `审批操作失败`
      actionError.value = msg
      appStore.addLog({
        level: 'error',
        source: 'ApprovalStore',
        message: `审批操作失败: ${msg}`,
      })
      throw err
    } finally {
      isActionLoading.value = false
    }
  }

  function handleApprovalEvent(event: HubEvent) {
    if (event.type === 'approval.required') {
      const payload = event.payload as ApprovalRequiredPayload
      const existing = approvals.value.find((a) => a.id === payload.approvalId)
      if (!existing) {
        const newAppr: ApprovalView = {
          id: payload.approvalId,
          taskId: event.taskId || '',
          taskObjective: `任务 ${event.taskId || ''}`,
          nodeId: event.nodeId,
          requestAgentId: event.agentInstanceId || '',
          requestAgentName: event.agentInstanceId || '未知 Agent',
          roleId: event.roleId,
          action: payload.action,
          targetResource: payload.targetResource,
          riskLevel: payload.riskLevel,
          status: 'pending',
          requestedAt: event.occurredAt,
          expiresAt: payload.expiresAt,
        }
        approvals.value.unshift(newAppr)
      }
    } else if (event.type === 'approval.resolved') {
      const payload = event.payload as ApprovalResolvedPayload
      const existing = approvals.value.find((a) => a.id === payload.approvalId)
      if (existing) {
        existing.status = payload.decision === 'approve' ? 'approved' : 'rejected'
        existing.decision = payload.decision
        existing.reason = payload.reason
        existing.decidedAt = payload.decidedAt
      }
    }
  }

  function isHighRiskAction(action: DangerousAction): boolean {
    return HIGH_RISK_ACTIONS.includes(action)
  }

  return {
    // State
    approvals,
    isLoading,
    isActionLoading,
    error,
    actionError,
    filterStatus,
    filterRiskLevel,
    filterAction,

    // Computed
    pendingApprovals,
    decidedApprovals,
    filteredApprovals,
    pendingCount,

    // Actions
    fetchApprovals,
    respondApproval,
    handleApprovalEvent,
    isHighRiskAction,
  }
})
