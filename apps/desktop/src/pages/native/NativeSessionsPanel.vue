<script setup lang="ts">
import RuntimeIcon from '@/shared/runtime/RuntimeIcon.vue'
import { onMounted, onBeforeUnmount, ref, watch, computed } from 'vue'
import type { RuntimeNativeSessionIndex, RemoteNativeSessionView, NativeMessagePart, RemoteResourceQueuedReceipt } from '@hqagent/protocol'
import { getLocalChatGateway, getRemoteGateway } from '@/shared/api'
import { useChatStore } from '@/stores/chat.store'
import { useRemoteChatStore } from '@/stores/remote-chat.store'
import { HqDialog, HqButton, HqMarkdown } from '@/shared/ui'
import { ChevronDown, ChevronRight, Folder } from 'lucide-vue-next'
import { overlayId } from '@/shared/ui/overlay-stack'
import { activityLabel, agentLabel, closureText, NativeMessageAssembler, nativeFailure } from './native-utils'

const props = withDefaults(defineProps<{
  remote?: boolean
  workerId?: string
  online?: boolean
  suspended?: boolean
  revisions?: number[]
  projects: { id: string; name: string }[]
  searchQuery?: string
}>(), {
  remote: false,
  online: true,
  suspended: false,
  searchQuery: '',
})
const emit = defineEmits<{ opened: [] }>()
const items = ref<(RuntimeNativeSessionIndex | RemoteNativeSessionView)[]>([])
const selected = ref<RuntimeNativeSessionIndex | RemoteNativeSessionView | null>(null)
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
const supported = computed(() => !props.remote || !props.revisions || props.revisions.some((revision) => revision === 3 || revision === 4 || revision === 5))
// UI state is ephemeral: no session metadata or disclosure preferences enter storage.
const expandedWorkspaces = ref(new Set<string>())
const collapsedWorkspaces = ref(new Set<string>())
function toggleWorkspace(workspaceId: string) {
  if (collapsedWorkspaces.value.has(workspaceId)) {
    collapsedWorkspaces.value.delete(workspaceId)
  } else {
    collapsedWorkspaces.value.add(workspaceId)
  }
}
const disclosureId = overlayId()
const selectedReadable = computed(() => selected.value?.format.status === 'readable')
const groups = computed(() => {
  const query = (props.searchQuery || '').trim().toLowerCase()
  return [...new Set(items.value.map((item) => item.workspaceId))].map((id) => {
    const sorted = items.value.filter((item) => item.workspaceId === id).sort((a, b) =>
      (Date.parse(b.updatedAt) || 0) - (Date.parse(a.updatedAt) || 0) || a.nativeSessionId.localeCompare(b.nativeSessionId))
    const projectName = props.projects.find((project) => project.id === id)?.name || id
    const filtered = query
      ? sorted.filter((item) => item.title.toLowerCase().includes(query) || projectName.toLowerCase().includes(query))
      : sorted
    return {
      id,
      name: projectName,
      readable: filtered.filter((item) => item.format.status === 'readable'),
      unavailable: filtered.filter((item) => item.format.status !== 'readable'),
    }
  }).filter((group) => !query || group.readable.length > 0 || group.unavailable.length > 0)
})
function toggleUnavailable(workspaceId: string) {
  if (expandedWorkspaces.value.has(workspaceId)) expandedWorkspaces.value.delete(workspaceId)
  else expandedWorkspaces.value.add(workspaceId)
}
function formatLabel(session: RuntimeNativeSessionIndex | RemoteNativeSessionView) {
  return `${agentLabel(session.agentType)} · CLI ${session.format.cliVersion || '版本未知'}`
}
async function list(more = false) {
  if (!supported.value || (props.remote && !props.workerId)) return
  const current = generation
  loading.value = true; error.value = null
  try {
    const page = props.remote ? await getRemoteGateway().listNativeSessions(props.workerId!, more ? cursor.value : undefined) : await getLocalChatGateway().listNativeSessions(more ? cursor.value : undefined)
    if (!alive || current !== generation) return
    if (page.hasMore && !page.nextCursor) throw new Error('原生会话索引游标缺失')
    items.value = [...new Map((more ? [...items.value, ...page.items] : page.items).map((item) => [item.nativeSessionId, item])).values()]
    const latest = items.value.find((item) => item.nativeSessionId === selected.value?.nativeSessionId)
    if (latest && selected.value && !pending.value) {
      if (latest.format.status !== 'readable') open(latest)
      else if (!selectedReadable.value) close()
    }
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
  if (!session || session.format.status !== 'readable') return
  if (props.remote && !props.online) { error.value = { message: '电脑离线，无法读取原生会话内容' }; return }
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
function open(session: RuntimeNativeSessionIndex | RemoteNativeSessionView) { close(); error.value = null; selected.value = session; confirmed.value = false; if (session.format.status === 'readable') void read() }
function close() { readGeneration++; reading.value = false; selected.value = null; messages.value = []; assembler.reset(); before.value = undefined; confirmation.value = false; confirmed.value = false }
async function prepareImport() {
  if (!selected.value || !selectedReadable.value) return
  error.value = null; confirmed.value = false
  try {
    const id = selected.value.nativeSessionId
    const current = generation
    const latest = props.remote ? await getRemoteGateway().getNativeSession(id) : await getLocalChatGateway().getNativeSession(id)
    if (alive && current === generation && selected.value?.nativeSessionId === id) {
      if (latest.format.status !== 'readable') { open(latest); return }
      selected.value = latest
      confirmation.value = true
    }
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
  if (!selected.value || !selectedReadable.value || !confirmed.value || importing.value || (props.remote && (!props.online || props.suspended))) return
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
watch(() => props.workerId, () => { generation++; close(); expandedWorkspaces.value.clear(); items.value = []; pending.value = null; clearTimeout(poll); void list() }, { immediate: true })
watch(() => props.online, (online) => { if (props.remote && !online) { readGeneration++; reading.value = false; messages.value = []; assembler.reset(); if (selectedReadable.value) error.value = { message: '电脑离线，无法读取原生会话内容' } } })
watch(supported, (available) => { if (!available) { items.value = []; close() } else void list() })
onMounted(() => { refreshTimer = setInterval(() => { if (!document.hidden && !loading.value && !reading.value && !importing.value && !pending.value && !confirmation.value && !cursor.value) void list() }, 15000) })
onBeforeUnmount(() => { clearInterval(refreshTimer); alive = false; generation++; close(); clearTimeout(poll); items.value = [] })
</script>

<template>
  <section class="p-3 text-xs space-y-2 shrink-0" data-testid="native-sessions">
    <div class="flex justify-between items-center pb-1">
      <div class="flex items-center gap-1.5 min-w-0">
        <h2 class="font-semibold text-text text-xs">原生会话</h2>
        <span class="text-[10px] text-text-muted bg-panel-header px-1.5 py-0.5 rounded font-medium">
          CLI
        </span>
      </div>
      <button type="button" class="min-h-[44px] min-w-[44px] text-primary hover:text-primary-hover px-2 py-1 rounded hover:bg-muted text-xs cursor-pointer transition-colors" :disabled="loading" @click="list()">刷新</button>
    </div>
    <p v-if="!supported" class="text-warning">电脑不支持修订 3，请升级电脑端后查看原生会话</p>
    <p v-else-if="loading" class="text-text-muted">正在读取原生会话索引…</p>
    <p v-else-if="!items.length && !error" class="text-text-muted">{{ remote ? '暂无可用的原生会话索引；请在电脑确认同步已开启、修订 3 连接已就绪。当前接口未提供同步开关状态。' : '没有已登记项目内的原生会话' }}</p>
    <p v-if="cursor" class="text-content-secondary">以下数量仅统计已加载的会话</p>
    <div v-for="(group, groupIndex) in groups" :key="group.id" class="space-y-1" :data-workspace="group.id">
      <div
        class="px-2 py-1.5 rounded-lg flex items-center justify-between gap-1 text-xs text-text-muted hover:text-text select-none cursor-pointer transition-colors hover:bg-muted/40 group"
        @click="toggleWorkspace(group.id)"
      >
        <div class="flex items-center gap-1.5 min-w-0 flex-1 text-left py-0.5">
          <component
            :is="collapsedWorkspaces.has(group.id) ? ChevronRight : ChevronDown"
            class="w-3.5 h-3.5 shrink-0 opacity-70 transition-transform"
          />
          <Folder class="w-4 h-4 shrink-0 text-primary/80" />
          <h3 class="truncate font-semibold text-text text-xs">{{ group.name }} · 可用 {{ group.readable.length }}</h3>
        </div>
      </div>
      <div v-if="!collapsedWorkspaces.has(group.id)" class="pl-2 space-y-1 mb-2">
        <p v-if="!group.readable.length" class="py-2 text-content-secondary pl-4" data-testid="native-empty-readable">暂无可读取的原生会话</p>
        <button v-for="item in group.readable" :key="item.nativeSessionId" type="button" data-testid="native-readable"
          class="block w-full min-h-[44px] text-left p-2.5 rounded-xl hover:bg-muted border border-border text-content-primary transition-all cursor-pointer group" @click="open(item)">
          <span class="block truncate font-medium text-xs text-text group-hover:text-primary transition-colors"><RuntimeIcon :agent="item.agentType" class="inline-block w-4 h-4 mr-1" />{{ item.title }}</span>
          <span class="block text-[10px] text-content-secondary mt-0.5">{{ agentLabel(item.agentType) }}{{ item.agentType === 'pi' && item.format.pi ? ' · 已保存分支' : '' }} · {{ activityLabel(item.activity.activity) }}</span>
        </button>
        <template v-if="group.unavailable.length">
          <button type="button" data-testid="native-unavailable-toggle" class="w-full min-h-[44px] flex items-center gap-1 text-left text-content-secondary rounded hover:bg-muted px-2 cursor-pointer transition-colors"
            :aria-expanded="expandedWorkspaces.has(group.id)" :aria-controls="`${disclosureId}-${groupIndex}`" @click="toggleUnavailable(group.id)">
            <component :is="expandedWorkspaces.has(group.id) ? ChevronDown : ChevronRight" class="w-4 h-4 shrink-0" />暂不支持（{{ group.unavailable.length }}）
          </button>
          <div v-if="expandedWorkspaces.has(group.id)" :id="`${disclosureId}-${groupIndex}`" class="space-y-1 pl-2">
            <button v-for="item in group.unavailable" :key="item.nativeSessionId" type="button" data-testid="native-unavailable"
              class="block w-full min-h-[44px] text-left p-2.5 rounded-xl border border-border text-content-secondary hover:bg-muted transition-all cursor-pointer" @click="open(item)">
              <span class="block truncate font-medium text-xs text-text"><RuntimeIcon :agent="item.agentType" class="inline-block w-4 h-4 mr-1" />{{ item.title }}</span>
              <span class="block text-[10px] break-words">{{ formatLabel(item) }}</span>
              <span class="block text-[10px] break-words text-text-muted">{{ item.format.reason || '当前记录格式尚未支持' }}</span>
            </button>
          </div>
        </template>
      </div>
    </div>
    <HqButton v-if="cursor" size="sm" :loading="loading" @click="list(true)">更多原生会话</HqButton>
    <p v-if="pending" role="status" class="text-primary">正在电脑上导入… 等待导入结果与对话同步</p>
    <div v-if="error" role="alert" class="text-danger break-words"><p>{{ error.message }}</p><button v-if="error.requestId" type="button" class="text-[10px] select-text" @click="copyId()">requestId: {{ error.requestId }}</button></div>
    <HqDialog :open="Boolean(selected)" :title="selectedReadable ? selected?.title : '暂不支持此会话'" @close="close">
      <div v-if="selected && !selectedReadable" class="space-y-3 text-sm" data-testid="native-unavailable-explanation">
        <p class="font-medium text-content-primary break-words">{{ selected.title }}</p>
        <p>该会话由 {{ agentLabel(selected.agentType) }} {{ selected.format.cliVersion || '未知 CLI 版本' }} 生成，当前版本的记录格式尚未支持，无法读取或续接。</p>
        <p class="text-content-secondary break-words">原因：{{ selected.format.reason || '当前记录格式尚未支持' }}</p>
      </div>
      <div v-else class="space-y-3 text-xs">
        <p v-if="selected"><RuntimeIcon :agent="selected.agentType" class="inline-block w-4 h-4 mr-1" />{{ agentLabel(selected.agentType) }}{{ selected.agentType === 'pi' && selected.format.pi ? ' · 已保存分支' : '' }} · {{ activityLabel(selected.activity.activity) }} · 只读历史</p>
        <p v-if="error" role="alert" class="text-danger">{{ error.message }} <span class="select-text">{{ error.requestId ? `requestId: ${error.requestId}` : '' }}</span></p>
        <HqButton size="sm" :loading="reading" @click="read()">重新读取</HqButton>
        <HqButton v-if="before" size="sm" :loading="reading" @click="read(true)">读取更早内容</HqButton>
        <p v-if="reading">正在从电脑读取…</p>
        <p v-if="before && !messages.length" class="text-text-muted">正在等待完整消息片段，请继续读取更早内容</p>
        <div v-for="message in messages" :key="message.messageId" class="p-3 bg-bg-app border border-border rounded text-xs select-text">
          <span class="text-text-muted text-[11px] block mb-1 font-mono uppercase">{{ message.role }}</span>
          <p v-if="message.role === 'user'" class="whitespace-pre-wrap break-words">{{ message.text }}</p>
          <HqMarkdown v-else :content="message.text" />
        </div>
        <p v-if="pending" role="status">正在电脑上导入…</p>
        <p v-if="remote && suspended" class="text-warning">这台电脑的远程操作已暂停</p>
      </div>
      <template v-if="selectedReadable" #footer><HqButton :disabled="Boolean(pending) || (remote && (!online || suspended))" :loading="importing" @click="prepareImport">接着对话</HqButton></template>
    </HqDialog>
    <HqDialog :open="confirmation" title="确认终端已退出" @close="confirmation = false; confirmed = false">
      <p class="text-sm">{{ closureText }}</p>
      <label class="flex gap-2 mt-4 text-sm"><input class="hq-form-choice" v-model="confirmed" type="checkbox" />我已在终端退出该会话</label>
      <p v-if="error" class="mt-3 text-xs text-danger">{{ error.message }} <span class="select-text">{{ error.requestId ? `requestId: ${error.requestId}` : '' }}</span></p>
      <template #footer><HqButton :disabled="!confirmed || (remote && (!online || suspended))" :loading="importing" @click="importSession">确认导入</HqButton></template>
    </HqDialog>
  </section>
</template>
