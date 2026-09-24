<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useLocalAuthStore } from '@/stores/local-auth.store'
import {
  HqButton,
  HqInput,
  HqBadge,
} from '@/shared/ui'
import {
  KeyRound,
  ShieldCheck,
  AlertCircle,
  Radio,
  ExternalLink,
  RefreshCw,
  Terminal,
} from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const authStore = useLocalAuthStore()

const connectCode = ref('')

onMounted(async () => {
  const isAuthed = await authStore.checkAuthStatus()
  if (isAuthed) {
    const redirect = (route.query.redirect as string) || '/chat'
    router.replace(redirect)
  }
})

async function handleConnect() {
  if (!connectCode.value.trim()) return
  const success = await authStore.connectWithCode(connectCode.value)
  if (success) {
    const redirect = (route.query.redirect as string) || '/chat'
    router.replace(redirect)
  }
}

function handleSwitchToMock() {
  authStore.setGatewayMode('mock')
  const redirect = (route.query.redirect as string) || '/chat'
  router.replace(redirect)
}

function handleSwitchToReal() {
  authStore.setGatewayMode('real')
}
</script>

<template>
  <div class="min-h-screen bg-bg-app flex flex-col items-center justify-center p-4">
    <!-- Card Container -->
    <div class="w-full max-w-lg bg-panel border border-border rounded-[var(--radius-lg)] shadow-xl overflow-hidden">
      <!-- Header Banner -->
      <div class="p-6 bg-gradient-to-r from-primary/10 via-accent/5 to-panel border-b border-border">
        <div class="flex items-center justify-between mb-2">
          <div class="flex items-center gap-2.5">
            <div class="w-9 h-9 rounded-lg bg-primary/20 text-primary flex items-center justify-center font-bold text-lg">
              HQ
            </div>
            <div>
              <h1 class="text-base font-semibold text-text">HQAgent 本地角色对话工作台</h1>
              <p class="text-xs text-text-muted">N0 本地安全会话连接 (Local Session)</p>
            </div>
          </div>
          <HqBadge
            :variant="authStore.isMockMode ? 'warning' : authStore.authenticated ? 'success' : 'neutral'"
            class="text-[11px]"
          >
            {{ authStore.isMockMode ? '演示模式 (Mock)' : authStore.authenticated ? '已连接' : '等待连接' }}
          </HqBadge>
        </div>
      </div>

      <!-- Body Content -->
      <div class="p-6 space-y-5">
        <!-- Mode selection notification -->
        <div
          v-if="authStore.isMockMode"
          class="p-3 bg-warning/10 border border-warning/20 rounded-[var(--radius-md)] flex items-start gap-2.5 text-xs text-text"
        >
          <Radio class="w-4 h-4 text-warning shrink-0 mt-0.5" />
          <div class="space-y-1">
            <p class="font-medium text-warning">当前处于前端独立开工演示模式 (Mock)</p>
            <p class="text-text-muted">
              使用本地协议 Fixture 场景验证前端全部交互。无需后端 Worker 运行即可进行场景配置、会话管理和步骤演示。
            </p>
            <div class="pt-1">
              <button
                type="button"
                class="text-xs text-primary underline hover:text-primary-hover"
                @click="handleSwitchToReal"
              >
                切换为真实后端连接模式
              </button>
            </div>
          </div>
        </div>

        <div
          v-else
          class="p-3 bg-bg-app border border-border rounded-[var(--radius-md)] flex items-start gap-2.5 text-xs text-text"
        >
          <Terminal class="w-4 h-4 text-primary shrink-0 mt-0.5" />
          <div class="space-y-1">
            <p class="font-medium text-text">从本地 Worker 控制台获取一次性连接码</p>
            <p class="text-text-muted leading-relaxed">
              启动 HQAgent Worker 后，控制台将输出随机生成的 6-128 位一次性连接码。输入连接码后浏览器将建立安全的 HttpOnly Cookie 会话，不在前端持久化密钥。
            </p>
          </div>
        </div>

        <!-- Connection Form -->
        <form class="space-y-4" @submit.prevent="handleConnect">
          <div>
            <label class="block text-xs font-medium text-text mb-1.5 flex items-center justify-between">
              <span>本地会话连接码 <span class="text-danger">*</span></span>
              <span class="text-[11px] text-text-muted">6 ~ 128 位字符</span>
            </label>
            <div class="relative">
              <HqInput
                v-model="connectCode"
                placeholder="请输入 Worker 控制台输出的连接码..."
                :disabled="authStore.isConnecting || authStore.isChecking"
                autocomplete="off"
                spellcheck="false"
              />
            </div>
          </div>

          <!-- Error Alert -->
          <div
            v-if="authStore.authError"
            class="p-3 bg-danger/10 border border-danger/20 rounded-[var(--radius-md)] flex items-start gap-2.5 text-xs text-danger"
          >
            <AlertCircle class="w-4 h-4 shrink-0 mt-0.5" />
            <div class="space-y-1">
              <p class="font-medium">连接失败</p>
              <p class="text-text-muted leading-relaxed">{{ authStore.authError }}</p>
            </div>
          </div>

          <!-- Action Buttons -->
          <div class="space-y-2 pt-2">
            <HqButton
              type="submit"
              variant="primary"
              class="w-full justify-center"
              :disabled="!connectCode.trim() || authStore.isConnecting || authStore.isChecking"
              :loading="authStore.isConnecting"
            >
              <KeyRound class="w-4 h-4 mr-2" />
              建立本地安全会话
            </HqButton>

            <div class="flex items-center justify-between pt-2 text-xs">
              <button
                type="button"
                class="text-text-muted hover:text-text flex items-center gap-1 transition-colors"
                :disabled="authStore.isChecking"
                @click="authStore.checkAuthStatus"
              >
                <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': authStore.isChecking }" />
                刷新连接状态
              </button>

              <button
                v-if="!authStore.isMockMode"
                type="button"
                class="text-primary hover:text-primary-hover flex items-center gap-1 transition-colors font-medium"
                @click="handleSwitchToMock"
              >
                进入 Mock 演示环境
                <ExternalLink class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </form>

        <!-- Security Notice -->
        <div class="pt-4 border-t border-border flex items-center justify-between text-[11px] text-text-muted">
          <div class="flex items-center gap-1.5">
            <ShieldCheck class="w-3.5 h-3.5 text-success" />
            <span>符合 N0 本地同源与 HttpOnly 安全规范</span>
          </div>
          <span class="font-mono">v{{ authStore.protocolVersion }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
