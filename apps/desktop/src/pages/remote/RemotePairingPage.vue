<script setup lang="ts">
import RemoteRequestNotice from './RemoteRequestNotice.vue'
import { ref, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import { useRemoteAuthStore } from '@/stores/remote-auth.store'
import { getRemoteGateway, RemoteApiError } from '@/shared/api'
import type { RemotePairingPreview } from '@hqagent/protocol'
import { HqButton, HqBadge } from '@/shared/ui'
import { Laptop, ArrowLeft, CheckCircle2, AlertCircle, ShieldCheck } from 'lucide-vue-next'

const router = useRouter()
const gateway = getRemoteGateway()
const authStore = useRemoteAuthStore()

const PairingScanner = defineAsyncComponent(() => import('./PairingScanner.vue'))
const scannerOpen = ref(false)
let successTimer: ReturnType<typeof setTimeout> | undefined
onBeforeUnmount(() => { scannerOpen.value = false; clearTimeout(successTimer) })
async function onScanned(code: string) {
  scannerOpen.value = false
  pairCode.value = code
  previewData.value = null
  await handlePreview()
}

const pairCode = ref('')
const isLoadingPreview = ref(false)
const isConfirming = ref(false)
const errorMessage = ref<string | null>(null)
const previewData = ref<RemotePairingPreview | null>(null)
const isSuccess = ref(false)

function formatCode(val: string) {
  const clean = val.replace(/[^a-zA-Z0-9]/g, '').toUpperCase().slice(0, 8)
  pairCode.value = clean
}

async function handlePreview() {
  if (pairCode.value.length !== 8) {
    errorMessage.value = '请输入电脑端显示的完整 8 位短码'
    return
  }

  isLoadingPreview.value = true
  errorMessage.value = null
  previewData.value = null

  try {
    const preview = await gateway.previewPairing({ pairCode: pairCode.value })
    previewData.value = preview
  } catch (err: unknown) {
    if (err instanceof RemoteApiError) {
      errorMessage.value = err.message
    } else {
      errorMessage.value = '获取设备信息失败，请检查短码'
    }
  } finally {
    isLoadingPreview.value = false
  }
}

onMounted(async () => {
  let code = authStore.pendingPairCode

  // Check window.location.hash if pendingPairCode is empty
  if (!code && typeof window !== 'undefined' && window.location.hash) {
    const hashStr = window.location.hash
    const match = hashStr.match(/code=([A-Za-z0-9]{8})(?:&|$)/)
    if (match) {
      code = match[1].toUpperCase()
    }
  }

  // Clear hash from address bar immediately
  if (typeof window !== 'undefined' && window.location.hash && window.history?.replaceState) {
    window.history.replaceState(null, '', window.location.pathname + window.location.search)
  }

  // If valid 8-char code, populate and trigger preview
  if (code && /^[A-Z0-9]{8}$/.test(code)) {
    pairCode.value = code
    authStore.pendingPairCode = null
    await handlePreview()
  }
})

async function handleConfirm() {
  if (!previewData.value) return

  isConfirming.value = true
  errorMessage.value = null

  try {
    await gateway.confirmPairing(previewData.value.pairRequestId, {
      pairCode: pairCode.value,
    })
    isSuccess.value = true
    successTimer = setTimeout(() => {
      router.push('/remote/devices')
    }, 1200)
  } catch (err: unknown) {
    if (err instanceof RemoteApiError) {
      errorMessage.value = err.message
    } else {
      errorMessage.value = '确认绑定失败，请重试'
    }
  } finally {
    isConfirming.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-bg-app flex flex-col justify-center px-4 py-8 select-none">
    <RemoteRequestNotice />
    <PairingScanner v-if="scannerOpen" @close="scannerOpen = false" @decoded="onScanned" />
    <div class="w-full max-w-sm mx-auto bg-panel border border-border rounded-2xl shadow-xl p-6 sm:p-8 space-y-6">
      <!-- Back Link -->
      <button
        type="button"
        class="inline-flex items-center gap-1.5 text-xs text-text-muted hover:text-text cursor-pointer transition-colors -mt-2"
        @click="router?.push ? router.push('/remote/devices') : null"
      >
        <ArrowLeft class="w-3.5 h-3.5" />
        返回设备列表
      </button>

      <!-- Header -->
      <div class="text-center space-y-2">
        <div class="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-primary/10 text-primary mb-1">
          <ShieldCheck class="w-6 h-6" />
        </div>
        <h1 class="text-xl font-bold text-text">设备配对确认</h1>
        <p class="text-xs text-text-muted">输入电脑端 HQAgent-Hub 界面上显示的 8 位短码</p>
      </div>

      <!-- Error Alert -->
      <div
        v-if="errorMessage"
        role="alert"
        class="p-3 rounded-lg bg-danger/10 border border-danger/30 flex items-start gap-2.5 text-xs text-danger"
      >
        <AlertCircle class="w-4 h-4 shrink-0 mt-0.5" />
        <span class="font-medium">{{ errorMessage }}</span>
      </div>

      <!-- Success Notification -->
      <div
        v-if="isSuccess"
        class="p-4 rounded-xl bg-success/15 border border-success/30 text-center space-y-2 text-success"
      >
        <CheckCircle2 class="w-8 h-8 mx-auto" />
        <p class="font-medium text-sm">设备绑定成功！</p>
        <p class="text-xs text-text-muted">正在前往设备列表...</p>
      </div>

      <div v-else class="space-y-5">
        <!-- Code Input -->
        <div class="space-y-2">
          <label for="pair-code" class="block text-xs font-medium text-text-secondary">
            8 位配对短码
          </label>
          <div class="flex items-center gap-2">
          <input
            id="pair-code"
            :value="pairCode"
            type="text"
            maxlength="8"
            placeholder="例如 ABCD1234"
            class="hq-form-control w-full min-w-0 text-center tracking-widest font-mono text-lg font-bold py-2.5 bg-bg-app border border-border rounded-lg text-text focus:outline-hidden focus:border-primary transition-colors uppercase"
            :disabled="isLoadingPreview || isConfirming || Boolean(previewData)"
            @input="formatCode(($event.target as HTMLInputElement).value)"
          />
          <button type="button" class="shrink-0 min-h-[44px] min-w-[44px] px-3 rounded-lg border border-border bg-panel text-text hover:bg-panel-hover focus-visible:ring-2 focus-visible:ring-ring" :disabled="isLoadingPreview || isConfirming || Boolean(previewData)" @click="scannerOpen = true">扫码</button>
          </div>
        </div>

        <!-- Preview Card -->
        <div
          v-if="previewData"
          class="p-4 rounded-xl bg-bg-app border border-border/80 space-y-3 animate-fade-in"
        >
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-panel border border-border flex items-center justify-center text-text shrink-0">
              <Laptop class="w-5 h-5" />
            </div>
            <div class="min-w-0 flex-1">
              <h3 class="text-sm font-semibold text-text truncate">
                {{ previewData.deviceName }}
              </h3>
              <p class="text-xs text-text-muted flex items-center gap-1.5 mt-0.5">
                <span>{{ previewData.platform }}</span>
                <span>•</span>
                <span>{{ previewData.architecture }}</span>
              </p>
            </div>
            <HqBadge variant="info">待绑定</HqBadge>
          </div>

          <div class="text-[11px] text-text-muted border-t border-border/40 pt-2 flex justify-between">
            <span>挑战 ID: {{ previewData.pairRequestId.slice(0, 12) }}...</span>
            <span>核对无误后请确认</span>
          </div>
        </div>

        <!-- Action Buttons -->
        <div class="space-y-2 pt-1">
          <HqButton
            v-if="!previewData"
            data-testid="preview-btn"
            type="button"
            variant="primary"
            class="w-full py-2.5 justify-center font-medium shadow-sm"
            :loading="isLoadingPreview"
            :disabled="pairCode.length !== 8 || isLoadingPreview"
            @click="handlePreview"
          >
            获取设备预览
          </HqButton>

          <template v-else>
            <HqButton
              type="button"
              variant="primary"
              class="w-full py-2.5 justify-center font-medium shadow-sm"
              :loading="isConfirming"
              :disabled="isConfirming"
              @click="handleConfirm"
            >
              确认绑定并建立连接
            </HqButton>

            <HqButton
              type="button"
              variant="ghost"
              class="w-full py-2 justify-center text-xs text-text-muted"
              :disabled="isConfirming"
              @click="previewData = null"
            >
              重新输入短码
            </HqButton>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
