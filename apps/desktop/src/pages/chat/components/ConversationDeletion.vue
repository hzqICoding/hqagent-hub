<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'
import type { LocalMaintenanceConflictDetail } from '@hqagent/protocol'
import { getLocalChatGateway, HubApiError } from '@/shared/api'
import { HqButton, HqDialog, useConfirm } from '@/shared/ui'
import { useChatStore } from '@/stores/chat.store'
import { cleanupLabels, maintenanceConflict, maintenanceError } from '@/shared/maintenance/presentation'
const emit = defineEmits<{ 'open-run': [] }>()
const chat = useChatStore(), confirm = useConfirm()
const busy = ref(false), error = ref(''), notice = ref(''), conflict = ref<LocalMaintenanceConflictDetail>(), targetId = ref('')
const intent = ref<{ id: string; version: number; key: string }>()
let alive = true
onBeforeUnmount(() => { alive = false })
async function request(id: string) {
  if (busy.value) return
  if (intent.value) { error.value = '上一次删除请求尚未确认，请先重试同次请求核对结果'; return }
  busy.value = true; error.value = ''; conflict.value = undefined; targetId.value = id
  try {
    const conversations = await getLocalChatGateway().listLocalConversations({ includeHidden:true })
    if (!alive) return
    const current = conversations.find(conversation => conversation.id === id)
    if (!current) { error.value = '对话不存在，请刷新列表核对'; return }
    const version = current.version ?? 1
    if (!await confirm({ title:'删除对话？', description:`「${current.title}」\n将删除本机对话、消息和附件，并清理已同步到云端的副本；原生会话的 CLI 原始记录不会被删除。此操作不能撤销。`, confirmText:'删除对话', danger:true })) return
    intent.value = { id, version, key:crypto.randomUUID() }
    await execute()
  } catch (err) { if (alive) error.value = maintenanceError(err) }
  finally { busy.value = false }
}
async function execute() {
  const pending = intent.value
  if (!pending) return
  busy.value = true; error.value = ''; conflict.value = undefined
  try {
    const result = await getLocalChatGateway().deleteLocalConversation(pending.id,pending.version,pending.key)
    if (!result.localDeleted || result.conversationId !== pending.id) throw new Error('删除回执不匹配')
    intent.value = undefined
    notice.value = cleanupLabels[result.remoteCleanup]
    await chat.removeDeletedConversation(result.conversationId)
  } catch (err) {
    error.value = maintenanceError(err); conflict.value = maintenanceConflict(err)
    if (err instanceof HubApiError && err.status >= 400 && err.status < 500 && err.status !== 408 && err.status !== 429) intent.value = undefined
  } finally { busy.value = false }
}
async function openRun(id: string) {
  try { await chat.openBlockingRun(targetId.value,id); error.value = ''; conflict.value = undefined; emit('open-run') }
  catch { error.value = '无法读取阻塞运行，请刷新本机状态后核对' }
}
defineExpose({ request })
</script>
<template>
  <HqDialog :open="Boolean(error)" title="删除对话未完成" @close="error = ''">
    <p role="alert" class="text-status-warning whitespace-pre-wrap">{{ error }}</p>
    <p v-if="conflict?.currentVersion" class="text-xs mt-2">当前版本：{{ conflict.currentVersion }}，再次删除需重新确认。</p>
    <div v-if="conflict?.blockingRunIds?.length" class="space-y-1 mt-3"><p>阻塞的运行：</p><button v-for="id in conflict.blockingRunIds" :key="id" type="button" class="block min-h-[44px] text-accent break-all" @click="openRun(id)">{{ id }} · 查看运行</button><p v-if="conflict.hasMoreBlockingRuns" class="text-xs">还有更多阻塞运行，请在本机继续核对。</p></div>
    <template v-if="intent" #footer><HqButton :loading="busy" @click="execute">重试同次删除请求</HqButton></template>
  </HqDialog>
  <Teleport to="body"><div v-if="notice" role="status" class="fixed bottom-4 left-1/2 -translate-x-1/2 z-[60] max-w-[90vw] w-max bg-elevated text-content-primary border border-border shadow-dialog rounded-xl px-4 py-2 flex items-center gap-3 text-sm" data-testid="deletion-result"><span>{{ notice }}</span><button type="button" class="min-w-[44px] min-h-[44px] shrink-0" aria-label="关闭删除结果" @click="notice = ''">关闭</button></div></Teleport>
</template>
