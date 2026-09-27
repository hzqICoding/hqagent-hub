<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, inject, watch } from 'vue'
import { routeLocationKey, type RouteLocationNormalizedLoaded } from 'vue-router'
import QRCode from 'qrcode'
import { useRemoteLinkStore } from '@/stores/remote-link.store'
import {
  HqButton,
  HqBadge,
  HqDialog,
} from '@/shared/ui'
import {
  Smartphone,
  Globe,
  Monitor,
  ShieldCheck,
  ShieldAlert,
  Clock,
  RefreshCw,
  Unlink,
  AlertCircle,
  Copy,
  Check,
  Lock,
  ArrowRight,
  Radio,
} from 'lucide-vue-next'

const remoteLinkStore = useRemoteLinkStore()
const route = inject<RouteLocationNormalizedLoaded | null>(routeLocationKey, null)

// Unpaired Form Inputs
const inputServerOrigin = ref('https://hub.example.com')
const inputDeviceName = ref('我的电脑')
const formError = ref<string | null>(null)

// Unlink Modal State
const isUnlinkModalOpen = ref(false)
const isDisableSyncModalOpen = ref(false)

// Copy short code feedback
const isCopied = ref(false)

// QR Code State (B7)
const qrDataUrl = ref<string>('')
const qrCodeContent = computed(() => {
  if (!remoteLinkStore.isPairing || !remoteLinkStore.pairCode || !remoteLinkStore.serverOrigin) {
    return ''
  }
  const cleanOrigin = remoteLinkStore.serverOrigin.replace(/\/$/, '')
  return `${cleanOrigin}/remote/pair#code=${remoteLinkStore.pairCode}`
})

watch(
  qrCodeContent,
  async (content) => {
    if (content) {
      try {
        qrDataUrl.value = await QRCode.toDataURL(content, {
          margin: 1,
          width: 200,
          color: {
            dark: '#000000',
            light: '#ffffff',
          },
        })
      } catch {
        qrDataUrl.value = ''
      }
    } else {
      qrDataUrl.value = ''
    }
  },
  { immediate: true }
)

const isValidOrigin = computed(() => {
  const origin = inputServerOrigin.value.trim()
  return /^(?:https:\/\/(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?|\[[0-9A-Fa-f:]+\])|http:\/\/(?:127\.0\.0\.1|localhost))(?::(?:[1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?\/?$/.test(origin)
})

onMounted(async () => {
  const mockState = route?.query.mockState as string | undefined
  if (mockState) {
    if (mockState === 'pairing') {
      remoteLinkStore.linkView = {
        state: 'pairing',
        serverOrigin: 'https://hub.example.com',
        deviceName: '我的电脑',
        pairRequestId: 'pair_req_mock_1',
        pairCode: 'ABCD2345',
        expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
      }
      return
    } else if (mockState === 'paired') {
      remoteLinkStore.linkView = {
        state: 'paired',
        serverOrigin: 'https://hub.example.com',
        workerId: 'worker_local_pc',
        deviceName: '我的电脑',
        connectionStatus: 'online',
        lastConnectedAt: new Date().toISOString(),
      }
      return
    } else if (mockState === 'revoked') {
      remoteLinkStore.linkView = {
        state: 'revoked',
        serverOrigin: 'https://hub.example.com',
        workerId: 'worker_local_pc',
        deviceName: '我的电脑',
        connectionStatus: 'offline',
        lastConnectedAt: new Date().toISOString(),
        lastErrorCode: 'REMOTE_DEVICE_REVOKED',
      }
      return
    } else if (mockState === 'frozen') {
      remoteLinkStore.linkView = {
        state: 'frozen',
        serverOrigin: 'https://hub.example.com',
        workerId: 'worker_local_pc',
        deviceName: '我的电脑',
        connectionStatus: 'online',
        lastConnectedAt: new Date().toISOString(),
        lastErrorCode: 'REMOTE_EPOCH_STALE',
      }
      return
    }
  }

  try {
    await remoteLinkStore.refreshLink()
    if (remoteLinkStore.isPaired) {
      await remoteLinkStore.fetchSyncSettings()
    }
    if (remoteLinkStore.serverOrigin) {
      inputServerOrigin.value = remoteLinkStore.serverOrigin
    }
    if (remoteLinkStore.deviceName) {
      inputDeviceName.value = remoteLinkStore.deviceName
    }
  } catch {
    // Error recorded in store
  }
})

onUnmounted(() => {
  remoteLinkStore.stopPairingPolling()
})

async function handleStartPairing() {
  formError.value = null
  const origin = inputServerOrigin.value.trim()
  if (!origin) {
    formError.value = '请输入云端服务器地址'
    return
  }
  if (!isValidOrigin.value) {
    formError.value = '服务器地址格式不正确，必须以 https:// 开头（本地测试可用 localhost 或 127.0.0.1）'
    return
  }
  try {
    await remoteLinkStore.startPairing({
      serverOrigin: origin,
      deviceName: inputDeviceName.value.trim() || '我的电脑',
    })
  } catch (err: any) {
    formError.value = err.message || '发起配对失败'
  }
}

async function handleCancelPairing() {
  try {
    await remoteLinkStore.cancelPairing()
  } catch {
    // Store captures actionError
  }
}

function openUnlinkModal() {
  isUnlinkModalOpen.value = true
}

async function confirmUnlink() {
  isUnlinkModalOpen.value = false
  try {
    await remoteLinkStore.unlink()
  } catch {
    // Store captures actionError
  }
}

async function confirmDisableSync() {
  try {
    await remoteLinkStore.updateSyncSettings(false)
    isDisableSyncModalOpen.value = false
  } catch {
    // Error recorded in store
  }
}

async function copyPairCode() {
  if (!remoteLinkStore.pairCode) return
  try {
    await navigator.clipboard.writeText(remoteLinkStore.pairCode)
    isCopied.value = true
    setTimeout(() => {
      isCopied.value = false
    }, 2000)
  } catch {
    // Clipboard permission fallback
  }
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg-app overflow-y-auto select-none p-4 sm:p-6 lg:p-8">
    <div class="max-w-3xl w-full mx-auto space-y-6">
      <!-- Page Header -->
      <div class="flex items-start justify-between gap-4 border-b border-border/80 pb-5">
        <div class="space-y-1 min-w-0">
          <div class="flex items-center gap-2.5">
            <Smartphone class="w-6 h-6 text-primary shrink-0" />
            <h1 class="text-lg font-bold text-text truncate">连接手机 · 远程接入</h1>
          </div>
          <p class="text-xs text-text-muted leading-relaxed">
            将当前电脑上的 HQAgent-Hub 接入云端中转服务器，支持在手机浏览器上随时随地远程收发指令与查看进度
          </p>
        </div>

        <HqButton
          v-if="!remoteLinkStore.isUnpaired"
          size="sm"
          variant="secondary"
          :disabled="remoteLinkStore.isLoading || remoteLinkStore.isActionLoading"
          class="shrink-0"
          title="刷新远程连接状态"
          @click="remoteLinkStore.refreshLink()"
        >
          <RefreshCw
            class="w-3.5 h-3.5 mr-1"
            :class="{ 'animate-spin': remoteLinkStore.isLoading }"
          />
          刷新状态
        </HqButton>
      </div>

      <!-- Action Error Banner -->
      <div
        v-if="remoteLinkStore.actionError"
        role="alert"
        class="p-3.5 rounded-xl bg-danger/10 border border-danger/25 text-xs text-danger flex items-center justify-between gap-3 shadow-xs"
      >
        <div class="flex items-center gap-2 min-w-0">
          <AlertCircle class="w-4 h-4 shrink-0" />
          <span class="truncate">{{ remoteLinkStore.actionError }}</span>
        </div>
        <button
          type="button"
          class="text-xs text-danger/80 hover:text-danger underline shrink-0 cursor-pointer"
          @click="remoteLinkStore.clearError()"
        >
          关闭
        </button>
      </div>

      <!-- STATE 1: UNPAIRED (未配对状态) -->
      <div
        v-if="remoteLinkStore.isUnpaired"
        class="bg-panel border border-border rounded-2xl p-5 sm:p-7 shadow-xs space-y-6"
      >
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center text-primary shrink-0">
            <Radio class="w-5 h-5" />
          </div>
          <div>
            <h2 class="text-sm font-semibold text-text">发起新配对</h2>
            <p class="text-xs text-text-muted mt-0.5">配置云端中转服务器地址并获取 8 位配对短码</p>
          </div>
        </div>

        <!-- Last error notification if present -->
        <div
          v-if="remoteLinkStore.lastErrorMessage"
          class="p-3 rounded-xl bg-warning/10 border border-warning/25 text-xs text-warning flex items-start gap-2.5"
        >
          <AlertCircle class="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <p class="font-medium text-xs">上次配对提示</p>
            <p class="text-[11px] text-text-muted mt-0.5">{{ remoteLinkStore.lastErrorMessage }}</p>
          </div>
        </div>

        <form class="space-y-4" @submit.prevent="handleStartPairing">
          <div v-if="formError" class="p-2.5 rounded-lg bg-danger/10 text-danger text-xs">
            {{ formError }}
          </div>

          <div class="space-y-1.5">
            <label class="block text-xs font-medium text-text">
              云端 Hub Server 地址 <span class="text-danger">*</span>
            </label>
            <div class="relative">
              <Globe class="w-4 h-4 text-text-muted absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                v-model="inputServerOrigin"
                type="text"
                placeholder="https://hub.example.com"
                class="w-full pl-9 pr-3 py-2 text-xs bg-bg-app border border-border rounded-xl text-text placeholder-text-muted/50 focus:outline-none focus:border-primary transition-colors font-mono"
              />
            </div>
            <p class="text-[11px] text-text-muted">
              只接受 HTTPS 协议地址（本地联调支持 http://localhost 或 http://127.0.0.1）
            </p>
          </div>

          <div class="space-y-1.5">
            <label class="block text-xs font-medium text-text">
              本机设备显示名称
            </label>
            <div class="relative">
              <Monitor class="w-4 h-4 text-text-muted absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                v-model="inputDeviceName"
                type="text"
                placeholder="我的电脑"
                class="w-full pl-9 pr-3 py-2 text-xs bg-bg-app border border-border rounded-xl text-text placeholder-text-muted/50 focus:outline-none focus:border-primary transition-colors"
              />
            </div>
            <p class="text-[11px] text-text-muted">
              将在手机端设备列表与消息记录中展示，方便识别此工作站
            </p>
          </div>

          <div class="pt-2">
            <HqButton
              type="submit"
              variant="primary"
              :disabled="remoteLinkStore.isActionLoading || !inputServerOrigin.trim()"
              :loading="remoteLinkStore.isActionLoading"
              class="w-full sm:w-auto"
            >
              开始配对
              <ArrowRight class="w-3.5 h-3.5 ml-1.5" />
            </HqButton>
          </div>
        </form>

        <div class="p-3.5 rounded-xl bg-bg-app border border-border/80 flex items-start gap-2.5 text-xs text-text-muted">
          <ShieldCheck class="w-4 h-4 text-primary shrink-0 mt-0.5" />
          <div class="leading-relaxed text-[11px]">
            <p class="font-medium text-text">安全声明与凭据隔离</p>
            <p class="mt-0.5">
              远程能力仅充当通信管道。模型调用、文件读写与命令执行均在您的本机进行，云端绝不读取、不要求、亦不存储任何模型 API Key 或模型凭据。
            </p>
          </div>
        </div>
      </div>

      <!-- STATE 2: PAIRING (正在配对中) -->
      <div
        v-else-if="remoteLinkStore.isPairing"
        class="bg-panel border border-border rounded-2xl p-5 sm:p-7 shadow-xs space-y-6"
      >
        <div class="flex items-center justify-between gap-3 flex-wrap">
          <div class="flex items-center gap-2">
            <HqBadge size="md" variant="warning" class="animate-pulse">
              ● 正在等待手机输入短码
            </HqBadge>
          </div>
          <div class="flex items-center gap-1.5 text-xs text-text-muted">
            <Clock class="w-3.5 h-3.5 text-primary" />
            <span>有效剩余时间：</span>
            <span class="font-mono font-bold text-text">{{ remoteLinkStore.formattedCountdown }}</span>
          </div>
        </div>

        <div class="text-center py-4 space-y-4">
          <p class="text-xs text-text-muted">请使用手机扫描下方二维码，或手动输入 8 位配对短码：</p>

          <!-- QR Code (B7) -->
          <div>
            <div
              v-if="qrDataUrl"
              class="inline-flex flex-col items-center justify-center p-2.5 sm:p-3 bg-white rounded-2xl border border-border shadow-xs"
            >
              <img
                :src="qrDataUrl"
                alt="配对二维码"
                data-testid="pair-qrcode"
                class="w-40 h-40 sm:w-48 sm:h-48 block rounded-lg"
              />
            </div>
          </div>
          
          <div>
            <div class="inline-flex items-center gap-2.5 sm:gap-3 bg-panel-header px-4 sm:px-6 py-2.5 sm:py-3.5 rounded-2xl border border-primary/30 shadow-xs max-w-full">
              <span class="text-2xl sm:text-4xl font-mono tracking-widest text-primary font-bold select-all">
                {{ remoteLinkStore.pairCode }}
              </span>
              <button
                type="button"
                class="p-1.5 sm:p-2 rounded-lg hover:bg-panel text-text-muted hover:text-text transition-colors shrink-0"
                title="复制短码"
                @click="copyPairCode"
              >
                <Check v-if="isCopied" class="w-5 h-5 text-success" />
                <Copy v-else class="w-5 h-5" />
              </button>
            </div>
          </div>

          <p v-if="isCopied" class="text-xs text-success">已复制配对短码</p>
          <p class="text-[11px] text-text-muted max-w-md mx-auto">
            短码与二维码仅用于建立连接，有效期 5 分钟。短码过期或被取消后，本地临时配对凭据将自动擦除。
          </p>
        </div>

        <div class="p-3.5 rounded-xl bg-bg-app border border-border space-y-2 text-xs">
          <div class="flex items-center justify-between text-text-muted">
            <span>目标服务器：</span>
            <span class="font-mono text-text truncate max-w-[240px]">{{ remoteLinkStore.serverOrigin }}</span>
          </div>
          <div class="flex items-center justify-between text-text-muted">
            <span>本机设备名：</span>
            <span class="text-text">{{ remoteLinkStore.deviceName }}</span>
          </div>
        </div>

        <div class="flex items-center justify-end gap-3 pt-2">
          <HqButton
            variant="secondary"
            :disabled="remoteLinkStore.isActionLoading"
            @click="handleCancelPairing"
          >
            取消配对
          </HqButton>
        </div>
      </div>

      <!-- STATE 3: PAIRED (已配对连接) -->
      <div
        v-else-if="remoteLinkStore.isPaired"
        class="bg-panel border border-border rounded-2xl p-5 sm:p-7 shadow-xs space-y-6"
      >
        <div class="flex items-center justify-between gap-3 flex-wrap">
          <div class="flex items-center gap-2">
            <HqBadge
              v-if="remoteLinkStore.connectionStatus === 'online'"
              size="md"
              variant="success"
            >
              ● 在线 (已连接云端 Hub Server)
            </HqBadge>
            <HqBadge
              v-else-if="remoteLinkStore.connectionStatus === 'connecting'"
              size="md"
              variant="warning"
              class="animate-pulse"
            >
              ◌ 连接中...
            </HqBadge>
            <HqBadge
              v-else
              size="md"
              variant="neutral"
            >
              ○ 离线 (未连接云端)
            </HqBadge>
          </div>

          <span class="text-xs text-text-muted">
            上次连接：{{ remoteLinkStore.formattedLastConnected }}
          </span>
        </div>

        <!-- Last error notification if present -->
        <div
          v-if="remoteLinkStore.lastErrorMessage"
          class="p-3 rounded-xl bg-warning/10 border border-warning/25 text-xs text-warning flex items-start gap-2.5"
        >
          <AlertCircle class="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <p class="font-medium text-xs">连接告警</p>
            <p class="text-[11px] text-text mt-0.5">{{ remoteLinkStore.lastErrorMessage }}</p>
          </div>
        </div>

        <!-- Device Info Grid -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          <div class="p-3.5 rounded-xl bg-bg-app border border-border/80 space-y-1">
            <span class="text-text-muted text-[11px]">云端服务器地址</span>
            <p class="font-mono text-text truncate">{{ remoteLinkStore.serverOrigin }}</p>
          </div>
          <div class="p-3.5 rounded-xl bg-bg-app border border-border/80 space-y-1">
            <span class="text-text-muted text-[11px]">本机设备名称</span>
            <p class="text-text font-medium truncate">{{ remoteLinkStore.deviceName }}</p>
          </div>
          <div class="p-3.5 rounded-xl bg-bg-app border border-border/80 space-y-1 sm:col-span-2">
            <span class="text-text-muted text-[11px]">Worker 标识 (WorkerId)</span>
            <p class="font-mono text-text truncate">{{ remoteLinkStore.workerId }}</p>
          </div>
        </div>

        <!-- Sync Settings Master Switch -->
        <div class="p-4 rounded-xl bg-bg-app border border-border/80 flex items-center justify-between gap-4">
          <div>
            <div class="flex items-center gap-2">
              <span class="text-xs font-semibold text-text">同步总开关</span>
              <HqBadge size="sm" :variant="remoteLinkStore.mirrorEnabled ? 'success' : 'neutral'">
                {{ remoteLinkStore.mirrorEnabled ? '已开启' : '已关闭' }}
              </HqBadge>
            </div>
            <p class="text-[11px] text-text-muted mt-0.5">
              开启后对话内容会保存到你的服务器上
            </p>
          </div>
          <div class="flex items-center gap-2">
            <HqButton
              v-if="remoteLinkStore.mirrorEnabled"
              variant="secondary"
              size="sm"
              :disabled="remoteLinkStore.isSyncSettingsLoading"
              @click="isDisableSyncModalOpen = true"
            >
              关闭同步
            </HqButton>
            <HqButton
              v-else
              variant="primary"
              size="sm"
              :disabled="remoteLinkStore.isSyncSettingsLoading"
              :loading="remoteLinkStore.isSyncSettingsLoading"
              @click="remoteLinkStore.updateSyncSettings(true)"
            >
              开启同步
            </HqButton>
          </div>
        </div>

        <div class="flex items-center justify-between border-t border-border/80 pt-4">
          <p class="text-xs text-text-muted">
            已成功接入手机远程通道。两端可互通协作对话。
          </p>
          <HqButton
            variant="danger"
            size="sm"
            :disabled="remoteLinkStore.isActionLoading"
            @click="openUnlinkModal"
          >
            <Unlink class="w-3.5 h-3.5 mr-1" />
            解除绑定
          </HqButton>
        </div>
      </div>

      <!-- STATE 4: REVOKED (已撤销状态) -->
      <div
        v-else-if="remoteLinkStore.isRevoked"
        class="bg-panel border border-danger/30 rounded-2xl p-5 sm:p-7 shadow-xs space-y-5"
      >
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-danger/10 flex items-center justify-center text-danger shrink-0">
            <ShieldAlert class="w-5 h-5" />
          </div>
          <div>
            <div class="flex items-center gap-2">
              <h2 class="text-sm font-semibold text-text">设备连接已被撤销</h2>
              <HqBadge size="sm" variant="danger">revoked</HqBadge>
            </div>
            <p class="text-xs text-text-muted mt-0.5">云端中转服务器已撤销此电脑凭据，重连已被阻断</p>
          </div>
        </div>

        <div class="p-3.5 rounded-xl bg-bg-app border border-border text-xs text-text-muted space-y-2 leading-relaxed">
          <p class="text-text font-medium">当前状态说明：</p>
          <p>
            该电脑设备的远程连接凭据已被云端服务器撤销，本地已阻断后续重连。历史远程对话仍保持只读，现有本地任务不受任何影响。
          </p>
          <p v-if="remoteLinkStore.lastErrorMessage" class="text-danger font-medium">
            原因：{{ remoteLinkStore.lastErrorMessage }}
          </p>
        </div>

        <div class="flex items-center justify-end gap-3 pt-2">
          <HqButton
            variant="secondary"
            :disabled="remoteLinkStore.isActionLoading"
            @click="remoteLinkStore.unlink()"
          >
            清除失效绑定并重新配置
          </HqButton>
        </div>
      </div>

      <!-- STATE 5: FROZEN (状态冻结状态) -->
      <div
        v-else-if="remoteLinkStore.isFrozen"
        class="bg-panel border border-warning/40 rounded-2xl p-5 sm:p-7 shadow-xs space-y-5"
      >
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-warning/10 flex items-center justify-center text-warning shrink-0">
            <Lock class="w-5 h-5" />
          </div>
          <div>
            <div class="flex items-center gap-2">
              <h2 class="text-sm font-semibold text-text">远程连接已冻结</h2>
              <HqBadge size="sm" variant="warning">frozen</HqBadge>
            </div>
            <p class="text-xs text-text-muted mt-0.5">本地存储世代与服务器代次不一致，已暂停指令投递</p>
          </div>
        </div>

        <div class="p-3.5 rounded-xl bg-bg-app border border-border text-xs text-text-muted space-y-2 leading-relaxed">
          <p class="text-text font-medium">状态说明与下一步建议：</p>
          <p>
            检测到本地存储世代与云端服务器状态发生分歧（代次陈旧或 Worker 本地存储已迁移）。为防止状态错乱与脏数据写入，系统已强制冻结远程指令投递通道。
          </p>
          <p class="text-warning font-medium">
            提示：存储世代需要核对，请联系管理员或通过本地诊断工具进行数据校准。系统不支持直接恢复投递。
          </p>
        </div>

        <div class="flex items-center justify-end gap-3 pt-2">
          <HqButton
            variant="secondary"
            :disabled="remoteLinkStore.isActionLoading"
            @click="openUnlinkModal"
          >
            解除当前绑定
          </HqButton>
        </div>
      </div>
    </div>

    <!-- Unlink Confirmation Dialog -->
    <HqDialog
      :open="isUnlinkModalOpen"
      title="解除手机绑定二次确认"
      description="请仔细阅读解绑影响后再确认操作"
      @close="isUnlinkModalOpen = false"
    >
      <div class="space-y-3.5 py-2 text-xs text-text">
        <div class="p-3 rounded-xl bg-warning/10 border border-warning/25 text-warning flex items-start gap-2.5">
          <AlertCircle class="w-4 h-4 shrink-0 mt-0.5" />
          <div class="space-y-1.5 leading-relaxed text-[11px]">
            <p class="font-bold text-xs text-text">解绑须知与关键说明：</p>
            <p>
              1. <strong>解绑后，已有的远程对话在电脑上仍是只读，不会变回本地对话；</strong>
            </p>
            <p>
              2. <strong>服务端的撤销可能要在手机端再撤销一次设备才生效。</strong>
            </p>
          </div>
        </div>
        <p class="text-text-muted leading-relaxed">
          解除绑定后，本机将清除与该云端服务器的设备连接凭据。后续如需重新使用手机远程接入，需重新发起配对流程。
        </p>
      </div>

      <template #footer>
        <HqButton
          size="sm"
          variant="secondary"
          :disabled="remoteLinkStore.isActionLoading"
          @click="isUnlinkModalOpen = false"
        >
          取消
        </HqButton>
        <HqButton
          size="sm"
          variant="danger"
          :disabled="remoteLinkStore.isActionLoading"
          :loading="remoteLinkStore.isActionLoading"
          @click="confirmUnlink"
        >
          确认解除绑定
        </HqButton>
      </template>
    </HqDialog>

    <!-- Disable Sync Confirmation Dialog -->
    <HqDialog
      :open="isDisableSyncModalOpen"
      title="关闭同步确认"
      description="请仔细阅读关闭同步影响后再确认操作"
      @close="isDisableSyncModalOpen = false"
    >
      <div class="space-y-3.5 py-2 text-xs text-text">
        <div class="p-3 rounded-xl bg-danger/10 border border-danger/25 text-danger flex items-start gap-2.5">
          <AlertCircle class="w-4 h-4 shrink-0 mt-0.5" />
          <div class="space-y-1.5 leading-relaxed text-[11px]">
            <p class="font-bold text-xs text-danger">警告：该操作将影响手机端展示</p>
            <p>
              关闭后服务器上这台电脑的对话副本将被删除，手机上将看不到任何对话。本地数据不受影响。
            </p>
          </div>
        </div>
      </div>

      <template #footer>
        <HqButton
          size="sm"
          variant="secondary"
          :disabled="remoteLinkStore.isSyncSettingsLoading"
          @click="isDisableSyncModalOpen = false"
        >
          取消
        </HqButton>
        <HqButton
          size="sm"
          variant="danger"
          :disabled="remoteLinkStore.isSyncSettingsLoading"
          :loading="remoteLinkStore.isSyncSettingsLoading"
          @click="confirmDisableSync"
        >
          确认关闭
        </HqButton>
      </template>
    </HqDialog>
  </div>
</template>
