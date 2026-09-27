<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useRemoteChatStore } from '@/stores/remote-chat.store'
import { useRemoteAuthStore } from '@/stores/remote-auth.store'
import type { RemoteDeviceView } from '@hqagent/protocol'
import {
  HqButton,
  HqBadge,
  HqDialog,
  HqEmptyState,
} from '@/shared/ui'
import {
  Laptop,
  Plus,
  Trash2,
  MessageSquare,
  LogOut,
  AlertTriangle,
  Radio,
  ChevronRight,
} from 'lucide-vue-next'
import { onUnmounted } from 'vue'

const router = useRouter()
const chatStore = useRemoteChatStore()
const authStore = useRemoteAuthStore()

const deviceToRevoke = ref<RemoteDeviceView | null>(null)
const isRevoking = ref(false)

let pollTimer: ReturnType<typeof setInterval> | null = null

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    if (!document.hidden) {
      await chatStore.fetchDevices()
    }
  }, 15000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function handleVisibilityChange() {
  if (!document.hidden) {
    void chatStore.fetchDevices()
  }
}

onMounted(async () => {
  await chatStore.fetchDevices()
  startPolling()
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onUnmounted(() => {
  stopPolling()
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})

function selectDevice(device: RemoteDeviceView) {
  chatStore.selectDevice(device.workerId)
  router.push({ path: '/remote/chat', query: { workerId: device.workerId } })
}

function openRevokeDialog(device: RemoteDeviceView) {
  deviceToRevoke.value = device
}

async function confirmRevoke() {
  if (!deviceToRevoke.value) return
  isRevoking.value = true
  try {
    await chatStore.revokeDevice(deviceToRevoke.value.workerId)
    deviceToRevoke.value = null
  } finally {
    isRevoking.value = false
  }
}

async function handleLogout() {
  await authStore.logout()
  chatStore.reset()
  router.replace('/remote/login')
}
</script>

<template>
  <div class="min-h-screen bg-bg-app flex flex-col select-none">
    <!-- Top Bar -->
    <header class="h-14 bg-panel border-b border-border px-4 flex items-center justify-between shrink-0">
      <div class="flex items-center gap-2">
        <Radio class="w-4 h-4 text-primary animate-pulse" />
        <span class="font-bold text-sm text-text">我的电脑</span>
      </div>

      <div class="flex items-center gap-2">
        <HqButton
          variant="secondary"
          size="sm"
          class="text-xs"
          @click="router.push('/remote/chat')"
        >
          <MessageSquare class="w-3.5 h-3.5 mr-1" />
          工作台
        </HqButton>

        <button
          type="button"
          class="p-2 rounded-lg text-text-muted hover:text-danger hover:bg-panel-hover cursor-pointer transition-colors"
          title="退出登录"
          aria-label="退出登录"
          @click="handleLogout"
        >
          <LogOut class="w-4 h-4" />
        </button>
      </div>
    </header>

    <!-- Main Content -->
    <main class="flex-1 max-w-lg w-full mx-auto p-4 space-y-4">
      <!-- Pair New Device Banner -->
      <div class="flex items-center justify-between p-3 rounded-xl bg-panel border border-border">
        <div>
          <h2 class="text-xs font-semibold text-text">添加电脑设备</h2>
          <p class="text-[11px] text-text-muted">输入电脑端生成的 8 位短码配对</p>
        </div>
        <HqButton
          variant="primary"
          size="sm"
          class="text-xs"
          @click="router.push('/remote/pair')"
        >
          <Plus class="w-3.5 h-3.5 mr-1" />
          输入短码配对
        </HqButton>
      </div>

      <!-- Revocation Notice Alert -->
      <div
        v-if="chatStore.lastRevocationInfo"
        class="p-3 rounded-lg bg-warning/10 border border-warning/30 text-xs text-warning space-y-1"
      >
        <p class="font-medium flex items-center gap-1.5">
          <AlertTriangle class="w-3.5 h-3.5 shrink-0" />
          设备已撤销
        </p>
        <p class="text-[11px] opacity-90">
          注意：撤销不是停止操作，当前电脑上可能仍在继续执行任务。如需核对请回到电脑端检查。
        </p>
      </div>

      <!-- Device List -->
      <div v-if="chatStore.isLoadingDevices" class="py-12 text-center text-xs text-text-muted">
        正在获取设备列表...
      </div>

      <div v-else-if="chatStore.devices.length === 0" class="py-8">
        <HqEmptyState
          title="暂无已绑定电脑"
          description="在电脑端打开 HQAgent-Hub，点击『连接手机』获取配对码"
        />
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="device in chatStore.devices"
          :key="device.workerId"
          class="p-4 rounded-xl bg-panel border border-border space-y-3 shadow-xs cursor-pointer hover:border-primary/50 transition-colors"
          @click="selectDevice(device)"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="flex items-center gap-3 min-w-0">
              <div class="w-10 h-10 rounded-lg bg-bg-app border border-border flex items-center justify-center text-text shrink-0">
                <Laptop class="w-5 h-5" />
              </div>
              <div class="min-w-0">
                <h3 class="text-sm font-semibold text-text truncate">
                  {{ device.deviceName }}
                </h3>
                <p class="text-xs text-text-muted flex items-center gap-1.5 mt-0.5">
                  <span>{{ device.platform }}</span>
                  <span>•</span>
                  <span>{{ device.architecture }}</span>
                </p>
                <div class="flex items-center gap-1.5 flex-wrap mt-1">
                  <HqBadge v-if="device.supportedWireRevisions?.includes(2)" size="sm" variant="primary">
                    支持互通 (v2)
                  </HqBadge>
                  <span v-else class="text-[10px] text-text-muted">协议 v1</span>
                </div>
              </div>
            </div>

            <!-- Online / Offline Badge -->
            <HqBadge :variant="device.status === 'online' ? 'success' : 'neutral'">
              {{ device.status === 'online' ? '电脑在线' : '电脑离线' }}
            </HqBadge>
          </div>

          <div class="flex items-center justify-between text-[11px] text-text-muted border-t border-border/50 pt-2.5">
            <span class="truncate">Worker: {{ device.workerId }}</span>
            <div class="flex items-center gap-2">
              <button
                type="button"
                class="text-danger hover:text-danger-hover cursor-pointer font-medium flex items-center gap-1 transition-colors"
                @click.stop="openRevokeDialog(device)"
              >
                <Trash2 class="w-3.5 h-3.5" />
                撤销设备
              </button>
              <ChevronRight class="w-4 h-4 text-text-muted" />
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- Revoke Confirmation Dialog -->
    <HqDialog
      :open="Boolean(deviceToRevoke)"
      title="确认撤销设备连接？"
      @close="deviceToRevoke = null"
    >
      <div class="space-y-3 text-xs text-text">
        <p>
          撤销后将废止该设备凭据，手机端将无法再向电脑派发任何指令。
        </p>
        <div class="p-3 rounded-lg bg-warning/10 border border-warning/30 text-warning space-y-1">
          <p class="font-bold flex items-center gap-1.5">
            <AlertTriangle class="w-4 h-4 shrink-0" />
            重要说明
          </p>
          <p class="text-[11px] leading-relaxed">
            撤销不是停止操作，电脑端已接单的任务可能仍在继续运行 (<code>executionMayStillBeRunning=true</code>)。如需核对执行事实，请回到电脑端处理。
          </p>
        </div>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-2">
          <HqButton
            variant="ghost"
            size="sm"
            :disabled="isRevoking"
            @click="deviceToRevoke = null"
          >
            取消
          </HqButton>
          <HqButton
            variant="danger"
            size="sm"
            :loading="isRevoking"
            @click="confirmRevoke"
          >
            确认撤销
          </HqButton>
        </div>
      </template>
    </HqDialog>
  </div>
</template>
