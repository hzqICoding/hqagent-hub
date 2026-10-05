<script setup lang="ts">
import { watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLocalAuthStore } from '@/stores/local-auth.store'
import { isDesktopShell } from '@/shared/api/desktop-endpoint'

const auth = useLocalAuthStore()
const route = useRoute()
const router = useRouter()
let timer: ReturnType<typeof setInterval> | undefined

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
</script>

<template>
  <div class="h-full flex flex-col bg-app text-content-primary overflow-hidden">
    <header class="shrink-0 border-b border-border/30 bg-panel px-4 py-2 flex items-center justify-between gap-3 z-20">
      <div class="flex items-center gap-3">
        <router-link to="/chat" class="font-bold text-sm text-content-primary hover:text-primary transition-colors flex items-center gap-2">
          <div class="w-6 h-6 rounded-md bg-primary flex items-center justify-center text-white font-bold text-xs shadow-xs">
            HQ
          </div>
          <span>HQAgent Hub</span>
        </router-link>
      </div>
    </header>
    <main class="flex-1 min-h-0 overflow-hidden flex flex-col"><router-view /></main>
  </div>
</template>
