import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { LocalImageVerificationState, LocalImageVerificationJobView, StartLocalImageVerificationInput } from '@hqagent/protocol'
import { getLocalChatGateway, HubApiError } from '@/shared/api'
import { isJobTerminal, maintenanceConflict, maintenanceError, targetKey } from '@/shared/maintenance/presentation'

export const useImageVerificationStore = defineStore('image-verifications', () => {
  const items = ref<LocalImageVerificationState[]>([])
  const jobs = ref<Record<string, LocalImageVerificationJobView>>({})
  const includeInactiveModels = ref(false), loading = ref(false), error = ref(''), selectedJobId = ref(''), cursor = ref<string>()
  const busy = ref<Record<string, boolean>>({})
  // One explicit confirmation = one exact target/revision and one immutable paid intent.
  const intents = ref<Record<string, { input: StartLocalImageVerificationInput; key: string }>>({})
  const cancelKeys = new Map<string, string>(), timers = new Map<string, ReturnType<typeof setTimeout>>()
  const querying = new Set<string>()
  const jobEpochs = new Map<string, number>()
  let active = false, generation = 0
  function locked(target: LocalImageVerificationState['target']) {
    const key = targetKey(target)
    const row = items.value.find(item => targetKey(item.target) === key)
    return Boolean(busy.value[key] || intents.value[key] || (row?.activeJobId && (!jobs.value[row.activeJobId] || jobs.value[row.activeJobId].slotHeld)) || Object.values(jobs.value).some(job => targetKey(job.target) === key && (job.slotHeld || !isJobTerminal(job) || job.executionMayStillBeRunning || job.cleanupState === 'unconfirmed')))
  }
  function receive(job: LocalImageVerificationJobView) {
    jobs.value[job.jobId] = job
    clearTimeout(timers.get(job.jobId)); timers.delete(job.jobId)
    if (active && !isJobTerminal(job)) timers.set(job.jobId, setTimeout(() => { void refreshJob(job.jobId) }, 1000))
  }
  async function refreshJob(id: string) {
    if (querying.has(id)) return
    querying.add(id)
    const epoch = jobEpochs.get(id) || 0
    try {
      const job = await getLocalChatGateway().getImageVerificationJob(id)
      if (epoch !== (jobEpochs.get(id) || 0)) return
      receive(job)
      if (active && isJobTerminal(job)) await load(false, false)
    } catch (err) { if (epoch === (jobEpochs.get(id) || 0)) error.value = maintenanceError(err) }
    finally {
      querying.delete(id)
      if (epoch !== (jobEpochs.get(id) || 0) && jobs.value[id]) receive(jobs.value[id])
    }
  }
  async function openJob(id: string) { selectedJobId.value = id; error.value = ''; await refreshJob(id) }
  async function load(more = false, restore = true) {
    const current = ++generation
    loading.value = true; error.value = ''
    try {
      const page = await getLocalChatGateway().listImageVerifications({ includeInactiveModels: includeInactiveModels.value, ...(more && cursor.value ? { cursor: cursor.value } : {}) })
      if (current !== generation) return
      if (page.hasMore && !page.nextCursor) throw new Error('Missing cursor')
      items.value = more ? [...new Map([...items.value, ...page.items].map(item => [targetKey(item.target), item])).values()] : page.items
      cursor.value = page.hasMore ? page.nextCursor : undefined
      if (restore) for (const item of page.items) if (item.activeJobId) {
        if (!selectedJobId.value) selectedJobId.value = item.activeJobId
        await refreshJob(item.activeJobId)
        if (current !== generation) break
      }
    } catch (err) { if (current === generation) error.value = maintenanceError(err) }
    finally { if (current === generation) loading.value = false }
  }
  async function retry(key: string) {
    const intent = intents.value[key]
    if (!intent || busy.value[key]) return
    busy.value[key] = true; error.value = ''
    try {
      const job = await getLocalChatGateway().startImageVerification(intent.input, intent.key)
      delete intents.value[key]; selectedJobId.value = job.jobId; receive(job)
      const row = items.value.find(item => targetKey(item.target) === key)
      if (row) { row.activeJobId = job.slotHeld ? job.jobId : undefined; row.lastJobId = job.jobId }
    } catch (err) {
      error.value = maintenanceError(err)
      const conflict = maintenanceConflict(err)
      // Definite client rejection needs a fresh confirmation after refresh. Transport/5xx retries retain the paid intent.
      if (err instanceof HubApiError && err.status >= 400 && err.status < 500 && err.status !== 408 && err.status !== 429) delete intents.value[key]
      if (conflict?.reason === 'verification_in_progress' && conflict.activeJobId) {
        const row = items.value.find(item => targetKey(item.target) === key)
        if (row) row.activeJobId = conflict.activeJobId
        await openJob(conflict.activeJobId)
      } else if (conflict) { await load(false, false); error.value = maintenanceError(err) }
    } finally { busy.value[key] = false }
  }
  async function start(target: LocalImageVerificationState['target']) {
    if (locked(target)) return
    const key = targetKey(target)
    intents.value[key] = { input: { agentId: target.agentId, ...(target.modelId === undefined ? {} : { modelId: target.modelId }), expectedTargetRevision: target.targetRevision, acknowledgeModelUsage: true }, key: crypto.randomUUID() }
    await retry(key)
  }
  async function cancel(id: string) {
    if (busy.value[id]) return
    busy.value[id] = true; error.value = ''
    jobEpochs.set(id, (jobEpochs.get(id) || 0) + 1)
    clearTimeout(timers.get(id)); timers.delete(id)
    const key = cancelKeys.get(id) || crypto.randomUUID(); cancelKeys.set(id, key)
    try {
      const job = await getLocalChatGateway().cancelImageVerification(id, key)
      cancelKeys.delete(id); receive(job)
      if (isJobTerminal(job)) await load(false, false)
    } catch (err) { error.value = maintenanceError(err) }
    finally { busy.value[id] = false }
  }
  function activate() { active = true; void load() }
  function stop() { active = false; generation++; loading.value = false; for (const timer of timers.values()) clearTimeout(timer); timers.clear() }
  return { items, jobs, includeInactiveModels, loading, error, selectedJobId, cursor, busy, intents, locked, load, openJob, refreshJob, start, retry, cancel, activate, stop }
})
