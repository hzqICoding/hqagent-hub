<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { LocalAttachmentView, MessageAttachmentView, AttachmentManifestItem } from '@hqagent/protocol'
import { getLocalChatGateway, getRemoteGateway } from '@/shared/api'
import { File, Download } from 'lucide-vue-next'
import { hashBlob } from './sha256'
import { formatBytes } from './validation'
import { attachmentErrorText } from './transport'
import { getRemoteErrorMessage } from '@/shared/i18n/remote-errors'

const props = defineProps<{ attachment: MessageAttachmentView | AttachmentManifestItem; remote?: boolean }>()
const preview = ref(''), error = ref(''), downloading = ref(false)
const local = ref<LocalAttachmentView | null>(null)
let controller: AbortController | undefined
let generation = 0
const gateway = () => props.remote ? getRemoteGateway() : getLocalChatGateway()
const remoteAvailability = computed(() => 'availability' in props.attachment ? props.attachment.availability : undefined)
const thumbnailStatus = computed(() => 'thumbnailStatus' in props.attachment ? props.attachment.thumbnailStatus : undefined)
const remoteError = computed(() => 'errorCode' in props.attachment ? props.attachment.errorCode : undefined)
const available = computed(() => props.remote ? remoteAvailability.value === 'available' : Boolean(local.value))
const syncLabel = computed(() => local.value ? ({ not_synced: '本机可用 · 尚未同步', pending_upload: '本机可用 · 同步待上传', available: '本机可用 · 已同步', unavailable: '本机可用 · 同步失败' }[local.value.syncStatus || 'not_synced']) : '')
function release() { if (preview.value) URL.revokeObjectURL(preview.value); preview.value = '' }
function previewFailed() { release(); error.value = getRemoteErrorMessage('ATTACHMENT_THUMBNAIL_UNAVAILABLE') }
async function refresh() {
  controller?.abort(); controller = new AbortController(); const signal = controller.signal
  const request = ++generation
  release(); error.value = ''; local.value = null; downloading.value = false
  try {
    if (!props.remote) {
      const meta = await getLocalChatGateway().getAttachment(props.attachment.attachmentId)
      if (request !== generation) return
      local.value = meta
    }
    if (!available.value || props.attachment.kind !== 'image') return
    if (props.remote ? thumbnailStatus.value !== 'ready' : local.value?.syncStatus !== 'available') return
    const blob = await gateway().getAttachmentThumbnail(props.attachment.attachmentId, signal)
    if (request !== generation || signal.aborted) return
    // Validate even Mock/proxy responses: previews must be generated PNG, never originals.
    const signature = new Uint8Array(await blob.slice(0,8).arrayBuffer())
    if (request !== generation || signal.aborted) return
    if (blob.type !== 'image/png' || signature.join(',') !== '137,80,78,71,13,10,26,10') throw new Error('Invalid thumbnail')
    preview.value = URL.createObjectURL(blob)
  } catch (err) { if (request === generation && !signal.aborted) error.value = attachmentErrorText(err) }
}
async function download() {
  if (!available.value || downloading.value) return
  const request = generation
  const item = props.attachment
  downloading.value = true; error.value = ''
  let url = ''
  try {
    const blob = await gateway().getAttachmentContent(item.attachmentId, controller?.signal)
    if (blob.size !== item.sizeBytes || await hashBlob(blob, controller?.signal) !== item.sha256) throw Object.assign(new Error(), { code: 'ATTACHMENT_HASH_MISMATCH' })
    if (request !== generation) return
    // Even image/HTML-like originals are octet-stream downloads; no img/iframe/innerHTML.
    url = URL.createObjectURL(new Blob([blob], { type: 'application/octet-stream' }))
    const link = document.createElement('a'); link.href = url; link.download = item.fileName; link.style.display = 'none'; document.body.append(link); link.click(); link.remove()
    await new Promise((resolve) => setTimeout(resolve, 1000))
  } catch (err) { if (request === generation) error.value = attachmentErrorText(err) }
  finally { if (url) URL.revokeObjectURL(url); if (request === generation) downloading.value = false }
}
watch(() => props.attachment, refresh, { immediate: true, deep: true })
onBeforeUnmount(() => { generation++; controller?.abort(); release() })
</script>

<template>
  <div class="min-w-0 rounded-lg border border-border bg-panel p-2 text-content-primary text-xs space-y-1" data-testid="message-attachment">
    <img v-if="preview" :src="preview" @error="previewFailed" :alt="attachment.fileName" class="h-20 w-full object-contain rounded" />
    <div class="flex items-center gap-1 min-w-0"><File v-if="!preview" class="w-5 h-5 shrink-0" /><span class="truncate flex-1" :title="attachment.fileName">{{ attachment.fileName }}</span>
      <button v-if="available" type="button" class="min-w-[44px] min-h-[44px] flex items-center justify-center text-primary shrink-0" :disabled="downloading" :aria-label="`下载 ${attachment.fileName}`" @click="download"><Download class="w-4 h-4" /><span>{{ downloading ? '下载中' : '下载' }}</span></button>
    </div>
    <p class="text-content-muted">{{ formatBytes(attachment.sizeBytes) }}</p>
    <p v-if="remote && remoteAvailability === 'pending_upload'" class="text-status-warning">附件待上传</p>
    <p v-if="remote && remoteAvailability === 'unavailable'" class="text-status-danger">附件不可用：{{ remoteError ? getRemoteErrorMessage(remoteError) : '内容不可用' }}</p>
    <p v-if="remote && attachment.kind === 'image' && !preview" class="text-content-muted">{{ thumbnailStatus === 'pending' ? '缩略图生成中' : '缩略图不可用' }}</p>
    <p v-if="!remote" class="text-content-muted">{{ syncLabel || '正在核对本机附件' }}</p>
    <p v-if="local?.syncError" class="text-status-warning">{{ getRemoteErrorMessage(local.syncError) }}（不影响本机使用）</p>
    <p v-if="error" role="alert" class="text-status-danger break-all">{{ error }}</p>
    <button v-if="!remote || error || thumbnailStatus === 'pending'" type="button" class="min-h-[44px] text-primary" @click="refresh">刷新附件</button>
  </div>
</template>
