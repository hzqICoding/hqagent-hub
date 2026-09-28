<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import type { RemoteDeviceView } from '@hqagent/protocol'
import { useRemoteChatStore } from '@/stores/remote-chat.store'
import { useRemoteAuthStore } from '@/stores/remote-auth.store'
import { HqButton, HqBadge, HqDialog, HqEmptyState } from '@/shared/ui'
import { Laptop, Plus, MoreHorizontal, LogOut, KeyRound } from 'lucide-vue-next'
import RemoteRequestNotice from './RemoteRequestNotice.vue'

const router = useRouter()
const chatStore = useRemoteChatStore()
const authStore = useRemoteAuthStore()
const showRevoked = ref(false)
const menuWorkerId = ref<string | null>(null)
const menuDevice = computed(() => chatStore.devices.find((d) => d.workerId === menuWorkerId.value))
const displayName = ref('')
const deviceToDelete = ref<RemoteDeviceView | null>(null)
const onlineFilter = ref('all')
const accessFilter = ref('all')
const filteredDevices = computed(() => chatStore.availableDevices.filter((d) =>
  (onlineFilter.value === 'all' || String(d.online ?? d.status === 'online') === onlineFilter.value) &&
  (accessFilter.value === 'all' || (d.remoteAccess ?? 'enabled') === accessFilter.value)))
let pollTimer: ReturnType<typeof setInterval> | null = null
let mounted = true

async function refresh() {
  await chatStore.fetchDevices()
  if (showRevoked.value) await chatStore.fetchRevokedDevices()
}
function onVisibility() { if (!document.hidden) void refresh() }
onMounted(async () => {
  await refresh()
  if (!mounted) return
  pollTimer = setInterval(() => { if (!document.hidden) void refresh() }, 15000)
  document.addEventListener('visibilitychange', onVisibility)
})
onUnmounted(() => {
  mounted = false
  if (pollTimer) clearInterval(pollTimer)
  document.removeEventListener('visibilitychange', onVisibility)
})
async function toggleRevoked() {
  showRevoked.value = !showRevoked.value
  if (showRevoked.value) await chatStore.fetchRevokedDevices()
}
function selectDevice(device: RemoteDeviceView) {
  if (device.status === 'revoked') return
  void router.push({ path: '/remote/chat', query: { workerId: device.workerId } })
}
async function openMenu(device: RemoteDeviceView) {
  menuWorkerId.value = device.workerId
  displayName.value = device.displayName || ''
  chatStore.deviceActionError = null
  try {
    await chatStore.refreshDevice(device.workerId)
    if (menuWorkerId.value === device.workerId) displayName.value = menuDevice.value?.displayName || ''
  } catch { chatStore.deviceActionError = '读取设备状态失败，请刷新后重试' }
}
async function changeAccess() {
  if (!menuDevice.value) return
  await chatStore.patchDevice(menuDevice.value.workerId, { remoteAccess: menuDevice.value.remoteAccess === 'suspended' ? 'enabled' : 'suspended' })
}
async function saveName() {
  if (!menuDevice.value) return
  if (await chatStore.patchDevice(menuDevice.value.workerId, { displayName: displayName.value.trim() })) {
    displayName.value = menuDevice.value.displayName || ''
  }
}
function confirmDeletion(device: RemoteDeviceView) {
  chatStore.deviceActionError = null
  deviceToDelete.value = device
  menuWorkerId.value = null
}
async function deleteDevice() {
  if (deviceToDelete.value && await chatStore.deleteDevice(deviceToDelete.value.workerId, showRevoked.value)) deviceToDelete.value = null
}
async function logout() {
  await authStore.logout()
  chatStore.reset()
  void router.replace('/remote/login')
}
</script>

<template>
  <div class="h-dvh bg-bg-app text-text flex flex-col overflow-hidden">
    <header class="h-14 bg-panel border-b border-border px-4 flex items-center justify-between shrink-0">
      <div><h1 class="font-bold text-sm">我的电脑</h1><p class="text-[10px] text-text-muted">设备管理</p></div>
      <div class="flex items-center gap-2">
        <HqButton variant="secondary" size="sm" @click="router.push('/remote/tokens')"><KeyRound class="w-3.5 h-3.5" />API 令牌</HqButton>
        <button type="button" aria-label="退出登录" class="p-2" @click="logout"><LogOut class="w-4 h-4" /></button>
      </div>
    </header>
    <RemoteRequestNotice />
    <main class="flex-1 min-h-0 overflow-y-auto max-w-lg w-full mx-auto p-4 space-y-4">
      <div class="flex items-center justify-between gap-2 p-3 rounded-xl bg-panel border border-border">
        <div><h2 class="text-xs font-semibold">添加电脑设备</h2><p class="text-[11px] text-text-muted">在电脑端生成二维码或短码</p></div>
        <HqButton size="sm" @click="router.push('/remote/pair')"><Plus class="w-3.5 h-3.5" />输入短码配对</HqButton>
      </div>
      <p v-if="chatStore.deviceRemovalNotice || chatStore.lastRevocationInfo" class="text-xs text-warning">
        {{ chatStore.deviceRemovalNotice || '该电脑已撤销' }}。电脑上的任务可能仍在继续，请到电脑端核对。
      </p>
      <div class="flex gap-2 text-xs">
        <label class="flex-1">连接状态
          <select v-model="onlineFilter" class="block w-full p-2 mt-1 bg-panel border border-border rounded-lg"><option value="all">全部连接状态</option><option value="true">在线</option><option value="false">离线</option></select>
        </label>
        <label class="flex-1">远程操作
          <select v-model="accessFilter" class="block w-full p-2 mt-1 bg-panel border border-border rounded-lg"><option value="all">全部远程状态</option><option value="enabled">远程可用</option><option value="suspended">已暂停</option></select>
        </label>
      </div>
      <div v-if="chatStore.deviceError" role="alert" class="text-xs text-danger">
        {{ chatStore.deviceError }} <button type="button" class="underline" @click="refresh">重试</button>
      </div>
      <p v-if="chatStore.isLoadingDevices" class="text-xs text-text-muted">正在获取设备列表…</p>
      <HqEmptyState v-else-if="!filteredDevices.length" title="暂无匹配电脑" description="调整筛选，或在电脑端生成配对码添加电脑" />
      <div v-else class="space-y-3">
        <div v-for="device in filteredDevices" :key="device.workerId" class="p-4 bg-panel border border-border rounded-xl cursor-pointer" @click="selectDevice(device)">
          <div class="flex justify-between items-start gap-2">
            <button type="button" class="min-w-0 text-left flex items-center gap-2" @click.stop="selectDevice(device)">
              <Laptop class="w-5 h-5 shrink-0" /><span class="text-sm font-semibold truncate">{{ device.displayName || device.deviceName }}</span>
            </button>
            <button type="button" :aria-label="`${device.displayName || device.deviceName}的更多操作`" class="shrink-0 p-1" @click.stop="openMenu(device)"><MoreHorizontal class="w-5 h-5" /></button>
          </div>
          <p class="text-[11px] text-text-muted my-2">{{ device.platform }} · {{ device.architecture }}</p>
          <div class="flex flex-wrap gap-2">
            <HqBadge :variant="(device.online ?? device.status === 'online') ? 'success' : 'neutral'">{{ (device.online ?? device.status === 'online') ? '电脑在线' : '电脑离线' }}</HqBadge>
            <HqBadge :variant="device.remoteAccess === 'suspended' ? 'warning' : 'info'">{{ device.remoteAccess === 'suspended' ? '远程操作已暂停' : '远程可用' }}</HqBadge>
            <HqBadge v-if="device.supportedWireRevisions?.includes(2)" variant="primary">支持互通 (v2)</HqBadge>
          </div>
        </div>
      </div>
      <section class="border-t border-border pt-3">
        <button type="button" class="text-xs text-text-muted py-2" :aria-expanded="showRevoked" @click="toggleRevoked">
          {{ chatStore.revokedDevicesLoaded ? `已撤销（${chatStore.revokedDevices.length}）` : '已撤销（展开查看）' }}
        </button>
        <div v-if="showRevoked" class="space-y-2">
          <p v-if="chatStore.isLoadingRevokedDevices" class="text-xs text-text-muted">正在读取历史记录…</p>
          <p v-else-if="!chatStore.revokedDevices.length" class="text-xs text-text-muted">没有已撤销的设备</p>
          <div v-for="device in chatStore.revokedDevices" :key="device.workerId" class="p-3 bg-panel rounded-lg flex justify-between gap-2 text-xs">
            <span class="min-w-0 break-words">{{ device.displayName || device.deviceName }} · 已撤销</span>
            <HqButton variant="danger" size="sm" @click="confirmDeletion(device)">删除</HqButton>
          </div>
        </div>
      </section>
    </main>
    <HqDialog :open="Boolean(menuDevice)" :title="menuDevice?.displayName || menuDevice?.deviceName" @close="menuWorkerId = null">
      <div v-if="menuDevice" class="space-y-4 text-sm">
        <p class="text-xs text-text-muted">暂停只限制远程操作，历史与同步保留，不停止电脑上的任务。</p>
        <HqButton :loading="chatStore.isDeviceActionLoading" :variant="menuDevice.remoteAccess === 'suspended' ? 'primary' : 'secondary'" @click="changeAccess">{{ menuDevice.remoteAccess === 'suspended' ? '恢复远程' : '暂停远程' }}</HqButton>
        <label class="block text-xs">修改显示名（留空恢复电脑名称）
          <input v-model="displayName" maxlength="120" aria-label="显示名" class="block w-full p-2 mt-1 rounded border border-border bg-bg-app" />
        </label>
        <HqButton size="sm" :loading="chatStore.isDeviceActionLoading" @click="saveName">保存显示名</HqButton>
        <div class="border-t border-border pt-3"><HqButton variant="danger" :disabled="chatStore.isDeviceActionLoading" @click="confirmDeletion(menuDevice)">删除设备</HqButton></div>
        <p v-if="chatStore.deviceActionError" role="alert" class="text-xs text-danger">{{ chatStore.deviceActionError }}</p>
        <RemoteRequestNotice />
      </div>
    </HqDialog>
    <HqDialog :open="Boolean(deviceToDelete)" title="确认删除设备？" @close="deviceToDelete = null">
      <div class="space-y-3 text-xs">
        <p>这台电脑在服务器上的对话副本会被删除，电脑本地不受影响。</p>
        <p>电脑上正在执行的任务可能仍在继续。</p>
        <p>以后要再连接，只能在电脑端重新扫码。</p>
        <p v-if="chatStore.deviceActionError" role="alert" class="text-danger">{{ chatStore.deviceActionError }}</p>
        <RemoteRequestNotice />
      </div>
      <template #footer><HqButton variant="ghost" :disabled="chatStore.isDeviceActionLoading" @click="deviceToDelete = null">取消</HqButton><HqButton variant="danger" :loading="chatStore.isDeviceActionLoading" @click="deleteDevice">确认删除</HqButton></template>
    </HqDialog>
  </div>
</template>
