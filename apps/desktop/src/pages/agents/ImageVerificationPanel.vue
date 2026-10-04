<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import type { AgentView, LocalImageVerificationState } from '@hqagent/protocol'
import { piModelLabel, piGuardReady, PI_GUARD_BLOCKED } from '@/shared/runtime/pi'
import { getLocalChatGateway } from '@/shared/api'
import { HqButton, HqBadge, useConfirm } from '@/shared/ui'
import { useImageVerificationStore } from '@/stores/image-verification.store'
import { probeLabels, progressLabels, jobLabels, invalidationLabels, jobNeedsCancellation, targetKey } from '@/shared/maintenance/presentation'
import SafeVerificationDiagnostics from '@/shared/maintenance/SafeVerificationDiagnostics.vue'
const props = defineProps<{ agents?: AgentView[] }>()
const store = useImageVerificationStore(), confirm = useConfirm(), confirming = ref(false)
const localAgents = ref<AgentView[]>([])
const job = computed(() => store.jobs[store.selectedJobId])
function piBlocked(target: LocalImageVerificationState['target']) { const agent=localAgents.value.find(agent=>agent.id===target.agentId); return (target.agentType==='pi'||agent?.adapterId==='pi') && !piGuardReady(agent?.guard) }
function modelLabel(target: LocalImageVerificationState['target']) { return target.modelId === undefined ? '默认模型' : target.agentType === 'pi' ? piModelLabel(target.modelId) : target.modelId }
function agentName(id: string) { return localAgents.value.find(agent => agent.id === id)?.displayName || props.agents?.find(agent => agent.id === id)?.displayName || id }
function status(row: LocalImageVerificationState) { return row.status === 'passed' && row.passed && !row.invalidated ? '已验证' : row.invalidated || row.status === 'stale' ? '已失效' : ({ unverified:'未验证',failed:'验证未通过',unavailable:'当前不可用',passed:'当前无效' }[row.status] || '未验证') }
async function start(row: LocalImageVerificationState) {
  if (confirming.value || store.locked(row.target) || piBlocked(row.target)) return
  const target = { ...row.target }; confirming.value = true
  try {
    if (await confirm({ title:'验证图片能力？', description:`${agentName(target.agentId)}（${target.agentId}） · ${modelLabel(target)}\n这会真实调用模型多次，可能产生费用或消耗订阅额度。仅验证本次选定实例和模型。`, confirmText:'确认并开始验证' })) await store.start(target)
  } finally { confirming.value = false }
}
async function cancel() {
  const id = job.value?.jobId
  if (!id || confirming.value) return
  confirming.value = true
  try { if (await confirm({ title:'取消图片验证？', description:'只停止此验证作业，已产生的用量无法撤回。取消请求不代表执行已停止，请核对清理结果。', confirmText:'请求取消', danger:true })) await store.cancel(id) }
  finally { confirming.value = false }
}
onMounted(async () => { store.activate(); try { localAgents.value = await getLocalChatGateway().listLocalAgents() } catch { /* Exact target ID stays visible when names are unavailable. */ } }); onBeforeUnmount(store.stop)
</script>
<template>
  <section class="space-y-3" data-testid="image-verifications">
    <div class="flex items-center justify-between gap-3 flex-wrap"><div><h2 class="font-semibold text-content-primary">图片能力</h2><p class="text-xs text-content-secondary">按实例和模型分别验证；历史通过不代表当前有效。</p></div><div class="flex items-center gap-3"><label class="text-xs flex gap-2 items-center min-h-[44px]"><input v-model="store.includeInactiveModels" type="checkbox" class="hq-form-choice" @change="store.load()" />显示历史模型</label><HqButton variant="secondary" :loading="store.loading" @click="store.load()">刷新状态</HqButton></div></div>
    <p v-if="store.error" role="alert" class="text-status-danger text-sm break-words">{{ store.error }}</p>
    <div v-if="job" class="bg-panel border border-border rounded-xl p-4 space-y-2" data-testid="verification-progress">
      <div class="flex justify-between items-center gap-3"><div><h3 class="font-medium text-sm">{{ agentName(job.target.agentId) }} · {{ modelLabel(job.target) }}</h3><p class="text-xs text-content-secondary">{{ jobLabels[job.status] }} · CLI {{ job.target.cliVersion ?? '版本未知' }}</p></div><HqButton v-if="jobNeedsCancellation(job)" variant="danger" :disabled="confirming" :loading="store.busy[job.jobId]" @click="cancel">{{ job.status === 'interrupted' || job.cleanupState === 'unconfirmed' ? '再次请求取消' : '取消验证' }}</HqButton></div>
      <p v-if="job.status === 'interrupted' || job.cleanupState === 'unconfirmed' || job.executionMayStillBeRunning && job.status !== 'running'" class="text-status-warning text-sm">执行或清理尚需核对，可能仍在运行；占用未释放时不能重复发起。</p>
      <div class="grid grid-cols-5 gap-2"><div v-for="(label, key) in probeLabels" :key="key" class="rounded-lg bg-muted p-2 text-xs"><p>{{ label }}</p><p :class="job.probes[key].state === 'passed' ? 'text-status-success' : job.probes[key].state === 'failed' ? 'text-status-danger' : 'text-content-secondary'">{{ progressLabels[job.probes[key].state] }}</p></div></div>
      <p class="text-xs text-content-secondary">清理：{{ ({not_started:'未开始',pending:'待确认',confirmed:'已确认',unconfirmed:'未确认'})[job.cleanupState] }} · {{ job.appliedToCurrentTarget ? '结果已应用于当前目标' : '尚未应用于当前目标' }}</p>
      <SafeVerificationDiagnostics :diagnostics="job.diagnostics" /><button type="button" class="min-h-[44px] text-xs text-accent" @click="store.openJob(job.jobId)">核对作业状态</button>
    </div>
    <div class="border border-border rounded-xl overflow-hidden bg-panel">
      <div v-for="row in store.items" :key="targetKey(row.target)" class="p-4 border-b last:border-b-0 border-border grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto] gap-4 items-center" data-testid="verification-row">
        <div class="min-w-0"><p class="text-sm font-medium break-words">{{ agentName(row.target.agentId) }}</p><p v-if="agentName(row.target.agentId) !== row.target.agentId" class="text-xs text-content-secondary break-all">{{ row.target.agentId }}</p><p class="text-sm break-words">{{ modelLabel(row.target) }}</p><p class="text-xs text-content-secondary">CLI {{ row.target.cliVersion ?? '版本未知' }}{{ row.inUse ? '' : ' · 历史模型' }}</p></div>
        <div class="text-xs space-y-1"><HqBadge :variant="row.status === 'passed' && row.passed && !row.invalidated ? 'success' : row.invalidated ? 'warning' : 'neutral'">{{ status(row) }}</HqBadge><p v-for="reason in row.invalidationReasons" :key="reason" class="text-content-secondary">{{ invalidationLabels[reason] }}</p><p v-if="row.lastRecord" class="text-content-secondary">{{ row.lastRecord.passed && (!row.passed || row.invalidated || row.status !== 'passed') ? '历史通过但当前无效' : row.lastRecord.passed ? '验证通过' : '历史验证未通过' }} · {{ row.lastRecord.observedAt }} · CLI {{ row.lastRecord.target.cliVersion ?? '版本未知' }}</p></div>
        <div class="flex flex-col gap-1"><span v-if="piBlocked(row.target)" class="text-xs text-status-warning">{{ PI_GUARD_BLOCKED }}</span><HqButton :disabled="piBlocked(row.target) || confirming || store.locked(row.target) || row.status === 'unavailable'" @click="start(row)">验证</HqButton><HqButton v-if="store.intents[targetKey(row.target)]" variant="secondary" :loading="store.busy[targetKey(row.target)]" @click="store.retry(targetKey(row.target))">重试同次请求</HqButton><HqButton v-if="row.activeJobId || row.lastJobId" variant="ghost" @click="store.openJob((row.activeJobId || row.lastJobId)!)">查看进度</HqButton></div>
      </div><p v-if="!store.items.length" class="p-4 text-sm text-content-secondary">{{ store.loading ? '正在读取图片能力…' : '暂无可验证的 Agent 目标' }}</p>
    </div><HqButton v-if="store.cursor" variant="secondary" :loading="store.loading" @click="store.load(true)">更多目标</HqButton>
  </section>
</template>
