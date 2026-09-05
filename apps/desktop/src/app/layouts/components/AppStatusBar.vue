<script setup lang="ts">
import { computed } from 'vue'
import { useAppStore } from '@/stores/app.store'
import { useWorkspaceStore } from '@/stores/workspace.store'
import {
  Activity,
  CloudOff,
  Download,
  CheckCircle2,
  Terminal,
  PanelRight,
  GitBranch,
  AlertCircle,
} from 'lucide-vue-next'

const appStore = useAppStore()
const workspaceStore = useWorkspaceStore()

const errorLogCount = computed(() => {
  return appStore.logs.filter((l) => l.level === 'error').length
})

const hubStatusText = computed(() => {
  if (appStore.connectionStatus === 'mock') {
    return `Mock: ${appStore.activeScenario}`
  }
  if (appStore.connectionStatus === 'connected') {
    return `Local Hub: 已连接 (v${appStore.bootstrap?.appVersion || '0.1.0'})`
  }
  if (appStore.connectionStatus === 'connecting') {
    return 'Local Hub: 连接中...'
  }
  return 'Local Hub: 未连接'
})

const hubStatusDotClass = computed(() => {
  if (appStore.connectionStatus === 'connected') return 'bg-emerald-500'
  if (appStore.connectionStatus === 'mock') return 'bg-amber-500'
  if (appStore.connectionStatus === 'connecting') return 'bg-sky-500 animate-pulse'
  return 'bg-rose-500'
})
</script>

<template>
  <footer class="h-6 bg-panel border-t border-border-subtle px-3 flex items-center justify-between text-2xs text-content-muted select-none shrink-0">
    <!-- Left: Status indicators -->
    <div class="flex items-center gap-4">
      <!-- Hub Status -->
      <div class="flex items-center gap-1.5 font-mono">
        <span class="w-2 h-2 rounded-full shrink-0" :class="hubStatusDotClass" />
        <span class="text-content-secondary">{{ hubStatusText }}</span>
      </div>

      <!-- Cloud Status -->
      <div class="flex items-center gap-1 text-content-disabled">
        <CloudOff class="w-3 h-3" />
        <span>Cloud: 未连接</span>
      </div>

      <!-- OTA Status -->
      <div class="flex items-center gap-1">
        <template v-if="appStore.bootstrap?.update?.hasUpdate">
          <Download class="w-3 h-3 text-amber-500 animate-bounce" />
          <span class="text-amber-600 dark:text-amber-400 font-medium">
            新版本 v{{ appStore.bootstrap.update.latestVersion }}
          </span>
        </template>
        <template v-else>
          <CheckCircle2 class="w-3 h-3 text-emerald-500" />
          <span>v{{ appStore.bootstrap?.appVersion || '0.1.0' }} (最新)</span>
        </template>
      </div>
    </div>

    <!-- Right: Workspace & Drawer Toggles -->
    <div class="flex items-center gap-3">
      <!-- Workspace Info -->
      <div v-if="workspaceStore.currentWorkspace" class="flex items-center gap-1 text-content-secondary font-mono">
        <GitBranch class="w-3 h-3 text-primary-500" />
        <span>{{ workspaceStore.currentWorkspace.name }}:{{ workspaceStore.currentWorkspace.branch || 'main' }}</span>
      </div>

      <!-- Log Drawer Toggle -->
      <button
        type="button"
        @click="appStore.toggleLogDrawer"
        class="flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-muted transition-colors"
        :class="appStore.isLogDrawerOpen ? 'text-primary-600 font-semibold' : 'text-content-muted'"
      >
        <Terminal class="w-3 h-3" />
        <span>日志 ({{ appStore.logs.length }})</span>
        <span
          v-if="errorLogCount > 0"
          class="flex items-center gap-0.5 text-rose-500 font-bold"
        >
          <AlertCircle class="w-2.5 h-2.5" />
          {{ errorLogCount }}
        </span>
      </button>

      <!-- Inspector Toggle -->
      <button
        type="button"
        @click="appStore.openInspector(appStore.inspector.isOpen ? null : 'task', null)"
        class="flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-muted transition-colors"
        :class="appStore.inspector.isOpen ? 'text-primary-600 font-semibold' : 'text-content-muted'"
      >
        <PanelRight class="w-3 h-3" />
        <span>检视器</span>
      </button>
    </div>
  </footer>
</template>
