<script setup lang="ts">
import { computed, inject } from 'vue'
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
  Menu,
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const themeStore = useThemeStore()
const toggleMobileNav = inject<() => void>('toggleMobileNav', () => {})

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
  <header class="w-full h-12 border-b border-border-subtle bg-panel/60 backdrop-blur px-2 sm:px-4 flex items-center justify-between shrink-0 select-none z-10">
    <!-- Left: Page Title & Breadcrumb -->
    <div class="flex items-center gap-1.5 sm:gap-3 min-w-0">
      <!-- Mobile Main Navigation Toggle -->
      <button
        type="button"
        class="md:hidden min-w-[44px] min-h-[44px] -ml-1 p-2 rounded-lg text-content-secondary hover:text-content-primary hover:bg-muted flex items-center justify-center cursor-pointer shrink-0"
        title="打开主菜单"
        aria-label="打开主菜单"
        @click="toggleMobileNav"
      >
        <Menu class="w-4 h-4" />
      </button>

      <h1 class="text-sm font-bold text-content-primary tracking-tight truncate">
        {{ pageTitle }}
      </h1>

      <!-- Maintenance Warning Badge -->
      <div v-if="appStore.bootstrap?.maintenance" class="flex items-center gap-1 text-amber-600 bg-amber-50 dark:bg-amber-950/50 px-2 py-0.5 rounded text-2xs font-medium border border-amber-200 dark:border-amber-800 shrink-0">
        <AlertTriangle class="w-3 h-3" />
        <span class="hidden sm:inline">维护模式中 (禁用写任务)</span>
        <span class="sm:hidden">维护中</span>
      </div>
    </div>

    <!-- Right: Quick Actions -->
    <div class="flex items-center gap-1 sm:gap-2 shrink-0">
      <!-- Quick Onboarding Link -->
      <button
        type="button"
        @click="router.push('/onboarding')"
        class="hidden sm:flex items-center gap-1.5 text-xs text-content-secondary hover:text-primary-600 hover:bg-muted/60 px-2.5 py-1.5 rounded-lg transition-colors cursor-pointer"
        title="首次引导 (Onboarding)"
      >
        <Compass class="w-3.5 h-3.5 text-primary-600" />
        <span class="text-2xs font-medium">配置向导</span>
      </button>

      <!-- Refresh Bootstrap -->
      <button
        type="button"
        @click="handleRefresh"
        :disabled="appStore.isLoading"
        class="min-w-[44px] min-h-[44px] sm:min-w-0 sm:min-h-0 p-2 sm:p-1.5 text-content-secondary hover:text-primary-600 hover:bg-muted/60 rounded-lg transition-colors flex items-center justify-center cursor-pointer"
        title="刷新系统状态"
      >
        <RefreshCw class="w-3.5 h-3.5" :class="appStore.isLoading ? 'animate-spin text-primary-600' : ''" />
      </button>

      <!-- Theme Switcher -->
      <button
        type="button"
        @click="toggleTheme"
        class="min-w-[44px] min-h-[44px] sm:min-w-0 sm:min-h-0 p-2 sm:p-1.5 text-content-secondary hover:text-primary-600 hover:bg-muted/60 rounded-lg transition-colors flex items-center justify-center cursor-pointer"
        :title="`切换主题: 当前为${themeStore.isDark ? '深色' : '浅色'}`"
      >
        <Sun v-if="themeStore.isDark" class="w-3.5 h-3.5 text-amber-500" />
        <Moon v-else class="w-3.5 h-3.5 text-content-secondary" />
      </button>

      <!-- Inspector Toggle -->
      <button
        type="button"
        @click="appStore.openInspector(appStore.inspector.isOpen ? null : 'task', null)"
        class="hidden sm:flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg transition-colors cursor-pointer"
        :class="appStore.inspector.isOpen ? 'bg-primary-50 text-primary-600 dark:bg-primary-950/50 font-semibold' : 'text-content-secondary hover:text-primary-600 hover:bg-muted/60'"
        title="切换右侧检视器"
      >
        <PanelRight class="w-3.5 h-3.5" />
        <span class="text-2xs font-medium">检视器</span>
      </button>
    </div>
  </header>
</template>
