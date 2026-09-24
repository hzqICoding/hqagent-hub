<script setup lang="ts">
import { watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLocalAuthStore } from '@/stores/local-auth.store'

const auth = useLocalAuthStore()
const route = useRoute()
const router = useRouter()
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  timer = setInterval(() => { if (!auth.isMockMode) void auth.checkAuthStatus() }, 15000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })

watch(() => [auth.authenticated, auth.isChecking, auth.isMockMode], () => {
  if (!auth.authenticated && !auth.isChecking && !auth.isMockMode) {
    void router.replace({ path: '/connect', query: { redirect: route.fullPath } })
  }
})
watch(() => auth.currentMode, () => {
  void router.replace({ path: '/connect', query: { redirect: route.fullPath } })
})

async function disconnect() {
  await auth.logout()
  await router.push('/connect')
}
</script>

<template>
  <div class="h-full flex flex-col bg-app text-content-primary overflow-hidden">
    <header class="shrink-0 border-b border-border bg-panel px-4 py-3 flex items-center gap-5">
      <router-link to="/chat" class="font-semibold text-sm">HQAgent Hub</router-link>
      <nav class="flex items-center gap-4 text-xs">
        <router-link to="/chat" active-class="text-primary font-semibold">本地对话</router-link>
        <router-link to="/scenes" active-class="text-primary font-semibold">场景与角色</router-link>
      </nav>
      <span class="ml-auto text-xs" :class="auth.isMockMode ? 'text-warning' : 'text-text-muted'">
        {{ auth.isMockMode ? '演示数据 · 不会执行真实任务' : '本机 Worker' }}
      </span>
      <button type="button" class="text-xs text-primary hover:underline" @click="disconnect">退出连接</button>
    </header>
    <main class="flex-1 min-h-0 overflow-auto"><router-view /></main>
  </div>
</template>
