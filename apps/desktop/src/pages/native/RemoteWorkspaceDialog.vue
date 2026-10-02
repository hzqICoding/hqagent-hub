<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { DirectoryEntry, DirectoryListingPage, RemoteResourceQueuedReceipt } from '@hqagent/protocol'
import { getRemoteGateway } from '@/shared/api'
import { useRemoteChatStore } from '@/stores/remote-chat.store'
import { HqDialog, HqButton } from '@/shared/ui'
import { nativeFailure } from './native-utils'

const emit = defineEmits<{ close: []; selected: [workspaceId: string] }>()
const store = useRemoteChatStore()
const roots = computed(() => store.catalog?.authorizedRoots || [])
const rootId = ref('')
const root = computed(() => roots.value.find((r) => r.rootId === rootId.value))
const stack = ref<DirectoryEntry[]>([])
const listing = ref<DirectoryListingPage | null>(null)
const selection = ref<DirectoryEntry | null>(null)
const error = ref<ReturnType<typeof nativeFailure> | null>(null)
const loading = ref(false)
const registering = ref(false)
const pending = ref<RemoteResourceQueuedReceipt | null>(null)
const workerId = store.selectedDevice?.workerId
const blocked = computed(() => !store.isWorkerOnline || store.isRemoteSuspended || !root.value || store.selectedDevice?.workerId !== workerId)
let request = 0
let alive = true
let poll: ReturnType<typeof setTimeout> | undefined
async function browse(more = false) {
  if (blocked.value || !workerId || !root.value) return
  const current = ++request
  loading.value = true; error.value = null
  if (!more) { listing.value = null; selection.value = null }
  try {
    const page = await getRemoteGateway().listDirectory(workerId, { rootId: root.value.rootId, rootVersion: root.value.version,
      directoryToken: stack.value.at(-1)?.directoryToken, cursor: more ? listing.value?.nextCursor : undefined, limit: 50 })
    if (!alive || request !== current) return
    if (page.rootId !== root.value?.rootId || page.rootVersion !== root.value.version) throw new Error('根目录授权已变化，请重新选择')
    if (page.hasMore && !page.nextCursor) throw new Error('目录分页游标缺失，请重新读取')
    listing.value = more && listing.value ? { ...page, entries: [...listing.value.entries, ...page.entries] } : page
  } catch (err) {
    if (alive && current === request) {
      error.value = nativeFailure(err)
      if (['REMOTE_DIRECTORY_CHANGED', 'REMOTE_ROOT_NOT_AUTHORIZED', 'REMOTE_PATH_OUTSIDE_ROOT'].includes(error.value.code || '')) {
        stack.value = []; selection.value = null; listing.value = null
        await store.fetchCatalog()
      }
      if (error.value.code === 'REMOTE_DEVICE_SUSPENDED') await store.refreshActiveDevice()
    }
  } finally { if (current === request) loading.value = false }
}
function enter(entry: DirectoryEntry) { stack.value.push(entry); void browse() }
function back(index: number) { stack.value = stack.value.slice(0, index); void browse() }
async function reconcile() {
  if (!alive || !pending.value || !workerId) return
  try {
    const command = await getRemoteGateway().getCommand(pending.value.commandId)
    if (!alive) return
    if (command.status === 'failed' || command.status === 'rejected') {
      error.value = nativeFailure(command.error || new Error('添加项目失败')); pending.value = null; return
    }
    if (command.status === 'completed' && command.resourceRef?.workspaceId) {
      await store.fetchCatalog()
      if (!alive) return
      const id = command.resourceRef.workspaceId
      if (store.catalog?.workspaces.some((w) => w.workspaceId === id)) { pending.value = null; emit('selected', id); emit('close'); return }
    }
  } catch (err) { if (alive) error.value = nativeFailure(err) }
  if (alive && pending.value) poll = setTimeout(() => { void reconcile() }, 2000)
}
async function register() {
  if (blocked.value || !root.value || !workerId || !selection.value || pending.value || registering.value) return
  registering.value = true; error.value = null
  try {
    const receipt = await getRemoteGateway().registerWorkspace(workerId, { rootId: root.value.rootId, rootVersion: root.value.version, directoryToken: selection.value.directoryToken, name: selection.value.name })
    if (!alive) return
    pending.value = receipt
    poll = setTimeout(() => { void reconcile() }, 1000)
  } catch (err) {
    if (alive) {
      error.value = nativeFailure(err)
      if (['REMOTE_DIRECTORY_CHANGED', 'REMOTE_ROOT_NOT_AUTHORIZED', 'REMOTE_PATH_OUTSIDE_ROOT'].includes(error.value.code || '')) { stack.value = []; selection.value = null; listing.value = null; await store.fetchCatalog() }
      if (error.value.code === 'REMOTE_DEVICE_SUSPENDED') await store.refreshActiveDevice()
    }
  } finally { registering.value = false }
}
function copyId() { if (error.value?.requestId) void navigator.clipboard.writeText(error.value.requestId).catch(() => {}) }
watch(rootId, () => { stack.value = []; void browse() })
onBeforeUnmount(() => { alive = false; request++; clearTimeout(poll); stack.value = []; selection.value = null; listing.value = null })
</script>

<template>
  <HqDialog :open="true" title="添加项目" @close="emit('close')">
    <div class="space-y-3 text-xs">
      <p>只浏览电脑已授权的目录，不创建文件夹。</p>
      <label class="block">授权根目录<select v-model="rootId" aria-label="授权根目录" :disabled="Boolean(pending)" class="hq-form-control block w-full border border-border rounded p-2 bg-bg-app mt-1"><option value="">请选择根目录</option><option v-for="item in roots" :key="item.rootId" :value="item.rootId">{{ item.displayName }}</option></select></label>
      <p v-if="!roots.length">电脑未开放远程添加项目</p>
      <p v-if="!store.isWorkerOnline" class="text-warning">电脑离线，无法浏览目录</p>
      <p v-if="store.isRemoteSuspended" class="text-warning">这台电脑的远程操作已暂停</p>
      <nav v-if="root" aria-label="目录层级" class="flex flex-wrap gap-2"><button type="button" :disabled="loading || Boolean(pending)" @click="back(0)">{{ root.displayName }}</button><button v-for="(entry, index) in stack" :key="entry.directoryToken" type="button" :disabled="loading || Boolean(pending)" @click="back(index + 1)">› {{ entry.name }}</button></nav>
      <HqButton v-if="stack.length" size="sm" variant="secondary" :disabled="loading || Boolean(pending)" @click="back(stack.length - 1)">返回上一层</HqButton>
      <div v-if="error" role="alert" class="text-danger"><p>{{ error.message }}</p><button v-if="error.requestId" class="select-text text-[10px]" @click="copyId">requestId: {{ error.requestId }}</button><HqButton size="sm" :disabled="blocked" @click="browse()">重新读取根目录</HqButton></div>
      <p v-if="loading">正在读取目录…</p>
      <div v-for="entry in listing?.entries" :key="entry.directoryToken" class="flex items-center justify-between gap-2 p-2 border border-border rounded" :class="selection?.directoryToken === entry.directoryToken ? 'bg-primary/10' : ''">
        <button type="button" class="min-w-0 text-left break-words" :disabled="Boolean(pending)" @click="selection = entry">{{ entry.name }} <span v-if="entry.isGitRepository" class="text-success">Git 仓库</span></button>
        <HqButton size="sm" variant="ghost" :disabled="loading || blocked || Boolean(pending)" @click="enter(entry)">进入</HqButton>
      </div>
      <HqButton v-if="stack.length && listing" size="sm" variant="secondary" :disabled="Boolean(pending)" @click="selection = stack[stack.length - 1]">选择当前文件夹</HqButton>
      <HqButton v-if="listing?.hasMore" size="sm" :loading="loading" :disabled="blocked || Boolean(pending)" @click="browse(true)">加载更多目录</HqButton>
      <p v-if="selection">已选择：{{ selection.name }}</p>
      <p v-if="selection && !selection.isGitRepository" class="text-warning">非 Git 仓库只能运行只读任务</p>
      <p v-if="pending" role="status" class="text-primary">正在电脑上添加项目… 等待项目目录同步</p>
    </div>
    <template #footer><HqButton :disabled="blocked || !selection || Boolean(pending)" :loading="registering" @click="register">添加为项目</HqButton></template>
  </HqDialog>
</template>
