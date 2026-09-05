<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app.store'
import { useThemeStore } from '@/shared/theme/theme.store'
import {
  RefreshCw,
  Sun,
  Moon,
  PanelRight,
  Compass,
  AlertTriangle,
} from 'lucide-vue-next'
import { HqBadge, HqTooltip } from '@/shared/ui'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const themeStore = useThemeStore()

const pageTitle = computed(() => {
  return (route.meta.title as string) || 'HQAgent-Hub'
})

function toggleTheme() {
  themeStore.setMode(themeStore.settings.mode === 'dark' ? 'light' : 'dark')
}

async function handleRefresh() {
  await appStore.fetchBootstrap()
}
</script>

<template>
  <header class="h-12 border-b border-border-subtle bg-panel/60 backdrop-blur px-4 flex items-center justify-between shrink-0 select-none">
    <!-- Left: Page Title & Breadcrumb -->
    <div class="flex items-center gap-3">
      <h1 class="text-sm font-semibold text-content-primary tracking-tight">
        {{ pageTitle }}
      </h1>

      <!-- Maintenance Warning Badge -->
      <div v-if="appStore.bootstrap?.maintenance" class="flex items-center gap-1 text-amber-600 bg-amber-50 dark:bg-amber-950/50 px-2 py-0.5 rounded text-2xs font-medium border border-amber-200 dark:border-amber-800">
        <AlertTriangle class="w-3 h-3" />
        维护模式中 (禁用写任务)
      </div>
    </div>

    <!-- Right: Quick Actions -->
    <div class="flex items-center gap-2">
      <!-- Quick Onboarding Link -->
      <HqTooltip content="首次引导 (Onboarding)" placement="bottom">
        <button
          type="button"
          @click="router.push('/onboarding')"
          class="flex items-center gap-1 text-xs text-content-muted hover:text-content-primary hover:bg-muted px-2 py-1 rounded transition-colors"
        >
          <Compass class="w-3.5 h-3.5 text-primary-600" />
          <span class="text-2xs hidden sm:inline">引导</span>
        </button>
      </HqTooltip>

      <!-- Refresh Bootstrap -->
      <HqTooltip content="刷新系统状态" placement="bottom">
        <button
          type="button"
          @click="handleRefresh"
          :disabled="appStore.isLoading"
          class="p-1.5 text-content-muted hover:text-content-primary hover:bg-muted rounded transition-colors"
        >
          <RefreshCw class="w-3.5 h-3.5" :class="appStore.isLoading ? 'animate-spin text-primary-600' : ''" />
        </button>
      </HqTooltip>

      <!-- Theme Switcher -->
      <HqTooltip :content="`切换主题: 当前为${themeStore.isDark ? '深色' : '浅色'}`" placement="bottom">
        <button
          type="button"
          @click="toggleTheme"
          class="p-1.5 text-content-muted hover:text-content-primary hover:bg-muted rounded transition-colors"
        >
          <Sun v-if="themeStore.isDark" class="w-3.5 h-3.5 text-amber-400" />
          <Moon v-else class="w-3.5 h-3.5 text-content-secondary" />
        </button>
      </HqTooltip>

      <!-- Inspector Toggle -->
      <HqTooltip content="切换右侧检视器" placement="bottom">
        <button
          type="button"
          @click="appStore.openInspector(appStore.inspector.isOpen ? null : 'task', null)"
          class="p-1.5 rounded transition-colors"
          :class="appStore.inspector.isOpen ? 'bg-primary-50 text-primary-600 dark:bg-primary-950/50' : 'text-content-muted hover:text-content-primary hover:bg-muted'"
        >
          <PanelRight class="w-3.5 h-3.5" />
        </button>
      </HqTooltip>
    </div>
  </header>
</template>
