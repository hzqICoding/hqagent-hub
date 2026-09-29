<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch, computed } from 'vue'
import type { NativeSessionIndex, RemoteNativeSessionView, NativeMessagePart, RemoteResourceQueuedReceipt } from '@hqagent/protocol'
import { getLocalChatGateway, getRemoteGateway } from '@/shared/api'
import { useChatStore } from '@/stores/chat.store'
import { useRemoteChatStore } from '@/stores/remote-chat.store'
import { HqDialog, HqButton } from '@/shared/ui'
import { activityLabel, agentLabel, closureText, NativeMessageAssembler, nativeFailure } from './native-utils'

const props = withDefaults(defineProps<{ remote?: boolean; workerId?: string; online?: boolean; suspended?: boolean; revisions?: number[]; projects: { id: string; name: string }[] }>(), { remote: false, online: true, suspended: false })
const emit = defineEmits<{ opened: [] }>()
const items = ref<(NativeSessionIndex | RemoteNativeSessionView)[]>([])
const selected = ref<NativeSessionIndex | RemoteNativeSessionView | null>(null)
const messages = ref<NativeMessagePart[]>([])
const before = ref<string>()
const cursor = ref<string>()
const loading = ref(false)
const reading = ref(false)
const importing = ref(false)
const confirmation = ref(false)
const confirmed = ref(false)
const error = ref<ReturnType<typeof nativeFailure> | null>(null)
const pending = ref<RemoteResourceQueuedReceipt | null>(null)
const assembler = new NativeMessageAssembler()
let generation = 0
let readGeneration = 0
let poll: ReturnType<typeof setTimeout> | undefined
let alive = true
let refreshTimer: ReturnType<typeof setInterval> | undefined
const supported = computed(() => !props.remote || !props.revisions || props.revisions.includes(3))
const groups = computed(() => [...new Set(items.value.map((item) => item.workspaceId))].map((id) => ({ id, name: props.projects.find((p) => p.id === id)?.name || id, items: items.value.filter((item) => item.workspaceId === id) })))
async function list(more = false) {
  if (!supported.value || (props.remote && !props.workerId)) return
  const current = generation
  loading.value = true; error.value = null
  try {
    const page = props.remote ? await getRemoteGateway().listNativeSessions(props.workerId!, more ? cursor.value : undefined) : await getLocalChatGateway().listNativeSessions(more ? cursor.value : undefined)
    if (!alive || current !== generation) return
    if (page.hasMore && !page.nextCursor) throw new Error('原生会话索引游标缺失')
    items.value = more ? [...items.value, ...page.items] : page.items
    cursor.value = page.hasMore ? page.nextCursor : undefined
    if (!more && !page.hasMore && selected.value && !pending.value && !items.value.some((item) => item.nativeSessionId === selected.value?.nativeSessionId)) close()
  } catch (err) {
    if (current === generation) {
      error.value = nativeFailure(err)
      if (['REMOTE_SYNC_DISABLED', 'REMOTE_REVISION_REQUIRED'].includes(error.value.code || '')) { items.value = []; close() }
    }
  }
  finally { if (current === generation) loading.value = false }
}
async function read(more = false) {
  const session = selected.value
  if (!session) return
  if (props.remote && !props.online) { error.value = { message: '电脑离线，无法读取原生会话内容' }; return }
  if (session.format.status === 'unsupported') { error.value = { message: session.format.reason || '无法读取该版本的会话' }; return }
  const current = ++readGeneration
  reading.value = true; error.value = null
  if (!more) { assembler.reset(); messages.value = []; before.value = undefined }
  try {
    const page = props.remote ? await getRemoteGateway().readNativeMessages(session.nativeSessionId, more ? before.value : undefined) : await getLocalChatGateway().readNativeMessages(session.nativeSessionId, more ? before.value : undefined)
    if (!alive || current !== readGeneration || (props.remote && !props.online)) return
    if (page.nativeSessionId !== session.nativeSessionId) throw new Error('会话身份已变化，请重新读取')
    const completed = await assembler.append(page)
    if (!alive || current !== readGeneration) return
    messages.value = completed
    before.value = page.hasMore ? page.before : undefined
  } catch (err) { if (current === readGeneration) { error.value = nativeFailure(err); assembler.reset(); messages.value = []; before.value = undefined } }
  finally { if (current === readGeneration) reading.value = false }
}
function open(session: NativeSessionIndex | RemoteNativeSessionView) { close(); error.value = null; selected.value = session; confirmed.value = false; void read() }
function close() { readGeneration++; reading.value = false; selected.value = null; messages.value = []; assembler.reset(); before.value = undefined; confirmation.value = false; confirmed.value = false }
async function prepareImport() {
  if (!selected.value) return
  error.value = null; confirmed.value = false
  try {
    const id = selected.value.nativeSessionId
    const current = generation
    const latest = props.remote ? await getRemoteGateway().getNativeSession(id) : await getLocalChatGateway().getNativeSession(id)
    if (alive && current === generation && selected.value?.nativeSessionId === id) { selected.value = latest; confirmation.value = true }
  } catch (err) { error.value = nativeFailure(err) }
}
async function reconcile() {
  const receipt = pending.value
  if (!receipt || !alive) return
  const current = generation
  try {
    const command = await getRemoteGateway().getCommand(receipt.commandId)
    if (!alive || generation !== current || pending.value !== receipt) return
    if (command.status === 'failed' || command.status === 'rejected') {
      error.value = nativeFailure(command.error || new Error('导入失败，请重新确认后重试')); pending.value = null; await list(); return
    }
    if (command.status === 'completed' && command.resourceRef?.conversationId) {
      const store = useRemoteChatStore()
      await store.fetchConversations(props.workerId)
      if (!alive || generation !== current) return
      const id = command.resourceRef.conversationId
      if (store.conversations.some((c) => c.conversationId === id)) {
        await store.selectConversation(id)
        if (!alive || generation !== current) return
        pending.value = null; close(); await list(); emit('opened'); return
      }
    }
    // Grant/accepted is NOT a failed import merely because expiresAt passed.
  } catch (err) { if (alive && generation === current) error.value = nativeFailure(err) }
  if (alive && generation === current && pending.value) poll = setTimeout(() => { void reconcile() }, 2000)
}
async function importSession() {
  if (!selected.value || !confirmed.value || importing.value || (props.remote && (!props.online || props.suspended))) return
  const session = selected.value; const current = generation
  importing.value = true; error.value = null
  const input = { terminalClosedConfirmed: true as const, sourceRevision: session.sourceRevision, expectedIndexVersion: session.indexVersion }
  try {
    if (props.remote) {
      const receipt = await getRemoteGateway().importNativeSession(session.nativeSessionId, input)
      if (!alive || generation !== current) return
      pending.value = receipt; confirmation.value = false; confirmed.value = false
      poll = setTimeout(() => { void reconcile() }, 1000)
    } else {
      const conversation = await getLocalChatGateway().importNativeSession(session.nativeSessionId, input)
      if (!alive || generation !== current) return
      const store = useChatStore()
      store.conversations = [conversation, ...store.conversations.filter((c) => c.id !== conversation.id)]
      await store.selectConversation(conversation.id)
      close(); await list(); emit('opened')
    }
  } catch (err) {
    if (generation === current) {
      error.value = nativeFailure(err); confirmed.value = false
      if (props.remote && error.value.code === 'REMOTE_DEVICE_SUSPENDED') await useRemoteChatStore().refreshActiveDevice()
      if (error.value.code === 'NATIVE_SESSION_CHANGED') confirmation.value = false
    }
  } finally { if (generation === current) importing.value = false }
}
function copyId() { if (error.value?.requestId) void navigator.clipboard.writeText(error.value.requestId).catch(() => {}) }
watch(() => props.workerId, () => { generation++; close(); items.value = []; pending.value = null; clearTimeout(poll); void list() }, { immediate: true })
watch(() => props.online, (online) => { if (props.remote && !online) { readGeneration++; reading.value = false; messages.value = []; assembler.reset(); if (selected.value) error.value = { message: '电脑离线，无法读取原生会话内容' } } })
watch(supported, (available) => { if (!available) { items.value = []; close() } else void list() })
onMounted(() => { refreshTimer = setInterval(() => { if (!document.hidden && !loading.value && !reading.value && !importing.value && !pending.value && !confirmation.value && !cursor.value) void list() }, 15000) })
onBeforeUnmount(() => { clearInterval(refreshTimer); alive = false; generation++; close(); clearTimeout(poll); items.value = [] })
</script>

<template>
  <section class="p-3 border-t border-border text-xs space-y-2 max-h-[40vh] overflow-y-auto shrink-0" data-testid="native-sessions">
    <div class="flex justify-between items-center"><h2 class="font-semibold">原生会话</h2><button type="button" class="text-primary" :disabled="loading" @click="list()">刷新</button></div>
    <p v-if="!supported" class="text-warning">电脑不支持修订 3，请升级电脑端后查看原生会话</p>
    <p v-else-if="loading" class="text-text-muted">正在读取原生会话索引…</p>
    <p v-else-if="!items.length && !error" class="text-text-muted">{{ remote ? '暂无可用的原生会话索引；请在电脑确认同步已开启、修订 3 连接已就绪。当前接口未提供同步开关状态。' : '没有已登记项目内的原生会话' }}</p>
    <div v-for="group in groups" :key="group.id" class="space-y-1">
      <h3 class="text-text-muted">{{ group.name }}</h3>
      <button v-for="item in group.items" :key="item.nativeSessionId" type="button" class="block w-full text-left p-2 rounded hover:bg-panel-hover border border-border" @click="open(item)">
        <span class="block truncate">{{ item.title }}</span><span class="block text-[10px] text-text-muted">{{ agentLabel(item.agentType) }} · {{ activityLabel(item.activity.activity) }}</span>
        <span v-if="item.format.status === 'unsupported'" class="text-warning">{{ item.format.reason || '无法读取该版本的会话' }}</span>
      </button>
    </div>
    <HqButton v-if="cursor" size="sm" :loading="loading" @click="list(true)">更多原生会话</HqButton>
    <p v-if="pending" role="status" class="text-primary">正在电脑上导入… 等待导入结果与对话同步</p>
    <div v-if="error" role="alert" class="text-danger break-words"><p>{{ error.message }}</p><button v-if="error.requestId" type="button" class="text-[10px] select-text" @click="copyId()">requestId: {{ error.requestId }}</button></div>
    <HqDialog :open="Boolean(selected)" :title="selected?.title" @close="close">
      <div class="space-y-3 text-xs">
        <p v-if="selected">{{ agentLabel(selected.agentType) }} · {{ activityLabel(selected.activity.activity) }} · 只读历史</p>
        <p v-if="error" role="alert" class="text-danger">{{ error.message }} <span class="select-text">{{ error.requestId ? `requestId: ${error.requestId}` : '' }}</span></p>
        <HqButton size="sm" :loading="reading" @click="read()">重新读取</HqButton>
        <HqButton v-if="before" size="sm" :loading="reading" @click="read(true)">读取更早内容</HqButton>
        <p v-if="reading">正在从电脑读取…</p>
        <p v-if="before && !messages.length" class="text-text-muted">正在等待完整消息片段，请继续读取更早内容</p>
        <div v-for="message in messages" :key="message.messageId" class="p-3 bg-bg-app border border-border rounded"><span class="text-text-muted">{{ message.role }}</span><p class="whitespace-pre-wrap break-words">{{ message.text }}</p></div>
        <p v-if="pending" role="status">正在电脑上导入…</p>
        <p v-if="remote && suspended" class="text-warning">这台电脑的远程操作已暂停</p>
      </div>
      <template #footer><HqButton :disabled="Boolean(pending) || selected?.format.status === 'unsupported' || (remote && (!online || suspended))" :loading="importing" @click="prepareImport">接着对话</HqButton></template>
    </HqDialog>
    <HqDialog :open="confirmation" title="确认终端已退出" @close="confirmation = false; confirmed = false">
      <p class="text-sm">{{ closureText }}</p>
      <label class="flex gap-2 mt-4 text-sm"><input v-model="confirmed" type="checkbox" />我已在终端退出该会话</label>
      <p v-if="error" class="mt-3 text-xs text-danger">{{ error.message }} <span class="select-text">{{ error.requestId ? `requestId: ${error.requestId}` : '' }}</span></p>
      <template #footer><HqButton :disabled="!confirmed || (remote && (!online || suspended))" :loading="importing" @click="importSession">确认导入</HqButton></template>
    </HqDialog>
  </section>
</template>
