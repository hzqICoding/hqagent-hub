import type { LocalMaintenanceConflictDetail, LocalImageVerificationState, LocalImageVerificationJobView, LocalImageProbeProgressSet, LocalConversationDeletionView } from '@hqagent/protocol'
import { HubApiError } from '@/shared/api/local-hub-gateway'
export const probeLabels: Record<keyof LocalImageProbeProgressSet, string> = { new: '新建', resume: '续接', mixedFive: '五项混合输入', cancel: '取消探测', error: '错误处理' }
export const progressLabels = { not_run: '未执行', running: '运行中', passed: '通过', failed: '失败' }
export const jobLabels: Record<LocalImageVerificationJobView['status'], string> = { queued: '排队中', running: '运行中', cancel_requested: '已请求取消', succeeded: '已完成', failed: '失败', cancelled: '已取消', interrupted: '已中断，需核对' }
export const invalidationLabels: Record<LocalImageVerificationState['invalidationReasons'][number], string> = { cli_version_changed: 'CLI 版本已变化', model_changed: '模型选择已变化', runtime_changed: '运行环境已变化', configuration_changed: '输入通道或默认模型配置已变化', legacy_unbound: '历史记录未绑定当前实例', target_unavailable: '当前目标不可用' }
export const conflictLabels: Record<LocalMaintenanceConflictDetail['reason'], string> = { verification_in_progress: '该实例和模型已有验证作业，请查看进行中的作业', target_changed: '目标配置已变化，请刷新后重新确认', agent_unavailable: 'Agent 不可用或无法隔离验证，请在本机核对', version_mismatch: '对话版本已变化，请刷新后重新确认删除', active_runs: '对话仍有未结束的运行，请先处理运行', recovery_required: '存在需要恢复核对的运行，请先在本机核对', cancellation_unconfirmed: '运行取消尚未确认，请先核对执行是否停止', deleting: '对话正在删除，请核对原删除请求' }
export const cleanupLabels: Record<LocalConversationDeletionView['remoteCleanup'], string> = { not_required: '本机对话已删除，无需清理云端副本', pending: '本机对话已删除，云端副本待清理，将在连接后继续清理', confirmed: '本机对话已删除，云端副本已确认清理', unconfirmed: '本机对话已删除，云端副本是否清理尚未确认，请在电脑上核对连接状态' }
export function maintenanceConflict(error: unknown): LocalMaintenanceConflictDetail | undefined {
  if (!(error instanceof HubApiError) || error.code !== 'CONFLICT') return
  const detail = error.detail as LocalMaintenanceConflictDetail | undefined
  return detail && Object.hasOwn(conflictLabels, detail.reason) ? detail : undefined
}
export function maintenanceError(error: unknown) {
  const conflict = maintenanceConflict(error)
  if (conflict) return conflictLabels[conflict.reason]
  return error instanceof HubApiError && error.code === 'NOT_FOUND' ? '记录不存在，请刷新并核对原操作结果' : '本机请求未确认，请重试同次请求或刷新核对；不会自动重新发起付费验证'
}
export function isJobTerminal(job: LocalImageVerificationJobView) { return ['succeeded','failed','cancelled','interrupted'].includes(job.status) }
export function jobNeedsCancellation(job: LocalImageVerificationJobView) { return !isJobTerminal(job) || job.slotHeld || job.executionMayStillBeRunning || job.cleanupState === 'unconfirmed' }
export function targetKey(target: LocalImageVerificationState['target']) { return JSON.stringify([target.agentId, target.modelId ?? null]) }
