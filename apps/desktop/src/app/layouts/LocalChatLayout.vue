<script setup lang="ts">
import { watch, onMounted, onUnmounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLocalAuthStore } from '@/stores/local-auth.store'
import { useThemeStore } from '@/shared/theme/theme.store'
import { isDesktopShell } from '@/shared/api/desktop-endpoint'
import { Settings, Sun, Moon } from 'lucide-vue-next'

const auth = useLocalAuthStore()
const themeStore = useThemeStore()
const route = useRoute()
const router = useRouter()
let timer: ReturnType<typeof setInterval> | undefined

const isSettingsActive = computed(() => {
  return route.path.startsWith('/settings') || ['/agents', '/scenes', '/remote-link'].includes(route.path)
})

onMounted(() => {
  if (!isDesktopShell()) timer = setInterval(() => { if (!auth.isMockMode) void auth.checkAuthStatus() }, 15000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })

watch(() => [auth.authenticated, auth.isChecking, auth.isMockMode], () => {
  if (!isDesktopShell() && !auth.authenticated && !auth.isChecking && !auth.isMockMode) {
    void router.replace({ path: '/connect', query: { redirect: route.fullPath } })
  }
})
watch(() => auth.currentMode, () => {
  if (isDesktopShell()) return
  void router.replace({ path: '/connect', query: { redirect: route.fullPath } })
})

async function disconnect() {
  await auth.logout()
  await router.push('/connect')
}

function toggleTheme() {
  themeStore.setMode(themeStore.settings.mode === 'dark' ? 'light' : 'dark')
}
</script>

<template>
  <div class="h-full flex flex-col bg-app text-content-primary overflow-hidden">
    <header class="shrink-0 border-b border-border bg-panel px-4 py-2.5 flex items-center justify-between gap-3 z-20">
      <div class="flex items-center gap-3">
        <router-link to="/chat" class="font-bold text-sm text-content-primary hover:text-primary transition-colors flex items-center gap-2">
          <div class="w-6 h-6 rounded-md bg-primary flex items-center justify-center text-white font-bold text-xs shadow-xs">
            HQ
          </div>
          <span>HQAgent Hub</span>
        </router-link>
      </div>

      <div class="flex items-center gap-3 shrink-0">
        <span class="text-xs" :class="auth.isMockMode ? 'text-warning font-medium' : 'text-text-muted'">
          {{ auth.isMockMode ? '演示数据 · 不会执行真实任务' : '本机 Worker' }}
        </span>

        <!-- Theme toggle -->
        <button
          type="button"
          class="w-8 h-8 rounded-lg flex items-center justify-center text-content-muted hover:text-content-primary hover:bg-muted transition-colors cursor-pointer"
          :title="themeStore.settings.mode === 'dark' ? '切换亮色模式' : '切换暗色模式'"
          aria-label="切换主题"
          @click="toggleTheme"
        >
          <Sun v-if="themeStore.settings.mode === 'dark'" class="w-4 h-4" />
          <Moon v-else class="w-4 h-4" />
        </button>

        <!-- Right-side Settings button -->
        <router-link
          to="/settings"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all border cursor-pointer"
          :class="[
            isSettingsActive
              ? 'bg-primary/10 text-primary border-primary/30 font-semibold shadow-xs'
              : 'text-content-secondary hover:text-content-primary hover:bg-muted border-border/60'
          ]"
          title="系统与功能设置"
          aria-label="系统与功能设置"
        >
          <Settings class="w-3.5 h-3.5" />
          <span>设置</span>
        </router-link>

        <button v-if="!isDesktopShell()" type="button" class="text-xs text-primary hover:underline ml-1" @click="disconnect">退出连接</button>
      </div>
    </header>
    <main class="flex-1 min-h-0 overflow-hidden flex flex-col"><router-view /></main>
  </div>
</template>
