<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowReactive, watch } from 'vue'
import type { AttachmentLimits, LocalAttachmentView, RemoteAttachmentView } from '@hqagent/protocol'
import { getLocalChatGateway, getRemoteGateway } from '@/shared/api'
import { hashBlob } from './sha256'
import { selectedFileType, validateFileSize, formatBytes } from './validation'
import { attachmentErrorText } from './transport'

const props = defineProps<{ conversationId: string; remote?: boolean; suspended?: boolean; disabled?: boolean; offline?: boolean }>()
const emit = defineEmits<{ blocked: [blocked: boolean] }>()
// UI-only draft, never persisted. File objects are kept out of deep Vue proxies.
type Draft = { key: string; file: File; progress: number; state: 'waiting' | 'hashing' | 'uploading' | 'uploaded' | 'failed'; error?: string; sha?: string; result?: LocalAttachmentView | RemoteAttachmentView; controller?: AbortController }
const rows = shallowReactive<Draft[]>([])
const limits = ref<AttachmentLimits | null>(null)
const used = ref(0), reserved = ref(0)
const error = ref(''), choosing = ref(false), loadingLimits = ref(false)
const imagesInput = ref<HTMLInputElement | null>(null), filesInput = ref<HTMLInputElement | null>(null)
const busy = computed(() => rows.some((row) => ['waiting', 'hashing', 'uploading'].includes(row.state)))
const canUpload = computed(() => Boolean(props.conversationId) && !props.suspended && !props.disabled)
const imageAccept = computed(() => limits.value?.imageMimeTypes.join(',') || '')
const fileAccept = computed(() => limits.value?.fileExtensions.join(',') || '')
let alive = true, processing = false, selecting = false
const gateway = () => props.remote ? getRemoteGateway() : getLocalChatGateway()
const changed = () => emit('blocked', rows.some((row) => row.state !== 'uploaded'))
function change(row: Draft, values: Partial<Draft>) { const i = rows.findIndex((r) => r.key === row.key); if (i >= 0) { Object.assign(row, values); rows.splice(i, 1, row); changed() } }
async function loadLimits() {
  loadingLimits.value = true; error.value = ''
  try {
    const result = await gateway().getAttachmentLimits()
    if (!alive) return
    limits.value = 'limits' in result ? result.limits : result
    if ('usedBytes' in result) { used.value = result.usedBytes; reserved.value = result.reservedBytes }
  } catch (err) { if (alive) error.value = attachmentErrorText(err) }
  finally { if (alive) loadingLimits.value = false }
}
async function open() { choosing.value = !choosing.value; if (choosing.value) await loadLimits() }
async function choose(event: Event) {
  const input = event.target as HTMLInputElement
  const selected = Array.from(input.files || []); input.value = ''
  if (!canUpload.value || selecting || busy.value) return
  selecting = true
  try {
    await loadLimits()
    if (!alive || !limits.value || error.value) return
    for (const file of selected) {
      if (!canUpload.value || !alive) break
      if (rows.length >= limits.value.messageMaxCount) { error.value = `每条消息最多 ${limits.value.messageMaxCount} 个附件`; break }
      try {
        const mime = await selectedFileType(file, limits.value)
        validateFileSize(file.size, mime.startsWith('image/'), limits.value)
        const queued = rows.filter((row) => !row.result).reduce((sum, row) => sum + row.file.size, 0)
        if (props.remote && used.value + reserved.value + queued + file.size > limits.value.accountQuotaBytes) { error.value = '附件超过账号剩余配额'; continue }
        if (!alive || !canUpload.value) break
        rows.push(shallowReactive<Draft>({ key: crypto.randomUUID(), file, progress: 0, state: 'waiting' })); changed()
      } catch (err) { error.value = attachmentErrorText(err) }
    }
    choosing.value = false
  } finally { selecting = false }
  void uploadQueue()
}
async function uploadQueue() {
  if (processing || !canUpload.value || !alive) return
  processing = true
  try {
    while (alive && canUpload.value) {
      const row = rows.find((r) => r.state === 'waiting')
      if (!row) break
      const controller = new AbortController(); row.controller = controller
      try {
        change(row, { state: 'hashing', error: undefined })
        row.sha ||= await hashBlob(row.file, controller.signal, (fraction) => change(row, { progress: fraction }))
        if (!alive || !canUpload.value || controller.signal.aborted) throw new DOMException('已取消','AbortError')
        change(row, { state: 'uploading', progress: 0 })
        const result = await gateway().uploadAttachment(props.conversationId, row.file, { fileName: row.file.name, sha256: row.sha, idempotencyKey: row.key, signal: controller.signal, onProgress: (fraction) => change(row, { progress: fraction }) })
        if (!alive || !rows.some((r) => r.key === row.key)) continue
        if (result.conversationId !== props.conversationId || result.attachment.sha256 !== row.sha || result.attachment.sizeBytes !== row.file.size) throw Object.assign(new Error(), { code: 'ATTACHMENT_HASH_MISMATCH' })
        change(row, { result, state: 'uploaded', progress: 1 })
        used.value += row.file.size
      } catch (err) {
        if (alive && rows.some((r) => r.key === row.key)) change(row, { state: 'failed', error: controller.signal.aborted ? '上传已取消，可重试或移除' : attachmentErrorText(err) })
        // Rate limiting is never automatically retried, and stops the remaining batch.
        if ((err as { status?: number })?.status === 429 || (err as { code?: string })?.code === 'REMOTE_RATE_LIMITED') break
      }
    }
  } finally { processing = false }
}
async function remove(row: Draft) {
  if (props.disabled) return
  row.controller?.abort()
  if (row.result) {
    try { await gateway().deleteAttachment(row.result.attachment.attachmentId) }
    catch (err) { if ((err as { code?: string })?.code !== 'NOT_FOUND') { change(row, { error: attachmentErrorText(err) }); return } }
    used.value = Math.max(0, used.value - row.file.size)
  }
  const index = rows.findIndex((r) => r.key === row.key)
  if (index >= 0) rows.splice(index, 1)
  changed()
}
function retry(row: Draft) { if (!canUpload.value) return; change(row, { state: 'waiting', error: undefined }); void uploadQueue() }
function ids(): string[] { if (rows.some((row) => row.state !== 'uploaded')) throw new Error('请等待附件上传完成，或移除失败附件'); return rows.flatMap((row) => row.result ? [row.result.attachment.attachmentId] : []) }
function sent() { rows.splice(0); error.value = ''; changed() }
watch(() => props.suspended, (value) => { if (value) for (const row of rows) if (row.state === 'hashing' || row.state === 'uploading') row.controller?.abort() })
onBeforeUnmount(() => { alive = false; for (const row of rows) row.controller?.abort(); rows.splice(0); changed() })
defineExpose({ open, ids, sent })
</script>

<template>
  <div class="min-w-0 text-xs space-y-1" data-testid="attachment-drafts">
    <div v-if="choosing" class="flex flex-wrap gap-2 items-center">
      <button type="button" class="min-h-[44px] px-3 border border-border rounded-lg" :disabled="loadingLimits || !limits || !canUpload || busy" @click="imagesInput?.click()">选图片</button>
      <button type="button" class="min-h-[44px] px-3 border border-border rounded-lg" :disabled="loadingLimits || !limits || !canUpload || busy" @click="filesInput?.click()">选文件</button>
      <span v-if="loadingLimits">正在读取附件限制…</span>
      <span v-if="limits" class="text-content-muted">图片 {{ formatBytes(limits.imageMaxBytes) }}，文件 {{ formatBytes(limits.fileMaxBytes) }}，每条 {{ limits.messageMaxCount }} 个<span v-if="remote">；已用 {{ formatBytes(used) }}，预留 {{ formatBytes(reserved) }} / {{ formatBytes(limits.accountQuotaBytes) }}</span></span>
    </div>
    <input ref="imagesInput" data-testid="select-images" type="file" multiple :accept="imageAccept" class="hidden" @change="choose" />
    <input ref="filesInput" data-testid="select-files" type="file" multiple :accept="fileAccept" class="hidden" @change="choose" />
    <div v-if="rows.length" class="flex gap-2 overflow-x-auto max-w-full pb-1" aria-label="已选附件">
      <div v-for="row in rows" :key="row.key" class="shrink-0 w-56 p-2 bg-app border border-border rounded-lg text-content-primary">
        <div class="flex items-center gap-1"><span class="truncate flex-1" :title="row.file.name">{{ row.file.name }}</span><button type="button" class="min-w-[44px] min-h-[44px]" :aria-label="`移除 ${row.file.name}`" :disabled="disabled" @click="remove(row)">移除</button></div>
        <div class="flex justify-between"><span>{{ formatBytes(row.file.size) }}</span><span data-testid="attachment-status">{{ row.state === 'hashing' ? '校验中' : row.state === 'uploading' ? '上传中' : row.state === 'uploaded' ? '已上传' : row.state === 'failed' ? '上传失败' : '等待上传' }}</span></div>
        <progress v-if="row.state === 'hashing' || row.state === 'uploading'" class="w-full" :value="row.progress" max="1" :aria-label="`${row.file.name}上传进度`" />
        <p v-if="row.error" role="alert" class="text-status-danger break-words">{{ row.error }}</p>
        <button v-if="row.state === 'failed'" type="button" class="min-h-[44px] text-primary" :disabled="!canUpload" @click="retry(row)">重试上传</button>
      </div>
    </div>
    <p v-if="error" role="alert" class="text-status-danger break-words">{{ error }} <button type="button" class="min-h-[44px] underline" @click="loadLimits">重新读取限制</button></p>
    <p v-if="suspended" class="text-status-warning">这台电脑的远程操作已暂停，不能上传或发送附件；已有附件仍可下载。</p>
    <p v-if="remote && rows.length && limits" class="text-content-muted">{{ offline ? '电脑离线，发送失败。' : '' }}已上传附件保留，未发送附件将在上传后 {{ limits.unattachedTtlSeconds / 3600 }} 小时清理。</p>
  </div>
</template>
