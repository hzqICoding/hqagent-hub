<script setup lang="ts">
import RemoteRequestNotice from './RemoteRequestNotice.vue'
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useRemoteAuthStore } from '@/stores/remote-auth.store'
import { HqButton } from '@/shared/ui'
import { Smartphone, Lock, User, AlertCircle, Clock } from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const authStore = useRemoteAuthStore()

const loginName = ref('')
const password = ref('')

async function handleLogin() {
  if (!loginName.value.trim() || !password.value.trim()) {
    authStore.authError = '请输入用户名和口令'
    return
  }

  const success = await authStore.login({
    loginName: loginName.value.trim(),
    password: password.value,
  })

  if (success) {
    const redirect = (route.query.redirect as string) || '/remote/chat'
    router.replace(redirect)
  }
}
</script>

<template>
  <div class="min-h-screen bg-bg-app flex flex-col justify-center px-4 py-8 select-none">
    <RemoteRequestNotice />
    <div class="w-full max-w-sm mx-auto bg-panel border border-border rounded-2xl shadow-xl p-6 sm:p-8 space-y-6">
      <!-- Header -->
      <div class="text-center space-y-2">
        <div class="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-primary/10 text-primary mb-2">
          <Smartphone class="w-6 h-6" />
        </div>
        <h1 class="text-xl font-bold text-text">HQAgent 远程访问</h1>
        <p class="text-xs text-text-muted">通过云端 Hub 连接您电脑上的 Agent 会话</p>
      </div>

      <!-- Rate Limit Alert -->
      <div
        v-if="authStore.retryAfter !== null && authStore.retryAfter > 0"
        role="alert"
        class="p-3 rounded-lg bg-warning/10 border border-warning/30 flex items-start gap-2.5 text-xs text-warning"
      >
        <Clock class="w-4 h-4 shrink-0 mt-0.5" />
        <div>
          <p class="font-medium">请求过于频繁，请稍候重试</p>
          <p class="text-[11px] opacity-90 mt-0.5">
            还需等待 <span class="font-bold underline">{{ authStore.retryAfter }}</span> 秒
          </p>
        </div>
      </div>

      <!-- Error Alert -->
      <div
        v-else-if="authStore.authError"
        role="alert"
        class="p-3 rounded-lg bg-danger/10 border border-danger/30 flex items-start gap-2.5 text-xs text-danger"
      >
        <AlertCircle class="w-4 h-4 shrink-0 mt-0.5" />
        <span class="font-medium">{{ authStore.authError }}</span>
      </div>

      <!-- Form -->
      <form class="space-y-4" @submit.prevent="handleLogin">
        <div class="space-y-1.5">
          <label for="remote-login-name" class="block text-xs font-medium text-text-secondary">
            账号用户名
          </label>
          <div class="relative">
            <User class="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
            <input
              id="remote-login-name"
              v-model="loginName"
              type="text"
              autocomplete="username"
              placeholder="请输入 Hub 账号"
              class="hq-form-control w-full h-11 min-h-[44px] pl-10 pr-3 text-sm bg-bg-app border border-border rounded-xl text-text placeholder:text-text-muted focus:outline-hidden focus:border-primary transition-colors"
              :disabled="authStore.isLoading || Boolean(authStore.retryAfter)"
            />
          </div>
        </div>

        <div class="space-y-1.5">
          <label for="remote-password" class="block text-xs font-medium text-text-secondary">
            登录口令
          </label>
          <div class="relative">
            <Lock class="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
            <input
              id="remote-password"
              v-model="password"
              type="password"
              autocomplete="current-password"
              placeholder="请输入登录口令"
              class="hq-form-control w-full h-11 min-h-[44px] pl-10 pr-3 text-sm bg-bg-app border border-border rounded-xl text-text placeholder:text-text-muted focus:outline-hidden focus:border-primary transition-colors"
              :disabled="authStore.isLoading || Boolean(authStore.retryAfter)"
            />
          </div>
        </div>

        <HqButton
          type="submit"
          variant="primary"
          class="w-full h-11 min-h-[44px] mt-2 justify-center font-medium shadow-sm rounded-xl text-sm"
          :loading="authStore.isLoading"
          :disabled="authStore.isLoading || Boolean(authStore.retryAfter)"
        >
          {{ authStore.retryAfter ? `限流冷却中 (${authStore.retryAfter}s)` : '安全登录' }}
        </HqButton>
      </form>

      <!-- Footer Info -->
      <div class="pt-2 text-center text-[11px] text-text-muted border-t border-border/50">
        所有模型调用与执行均在您绑定的本地电脑完成
      </div>
    </div>
  </div>
</template>
