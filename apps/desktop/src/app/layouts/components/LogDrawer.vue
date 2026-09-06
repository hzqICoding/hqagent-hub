<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useAppStore } from '@/stores/app.store'
import {
  Terminal,
  Trash2,
  X,
  ArrowDown,
} from 'lucide-vue-next'
import { HqBadge } from '@/shared/ui'

const appStore = useAppStore()
const logListRef = ref<HTMLElement | null>(null)

watch(
  () => appStore.logs.length,
  () => {
    if (appStore.isAutoScrollLogs && appStore.isLogDrawerOpen) {
      nextTick(() => {
        if (logListRef.value) {
          logListRef.value.scrollTop = logListRef.value.scrollHeight
        }
      })
    }
  }
)

const filterLevels = [
  { id: 'all', label: '全部' },
  { id: 'info', label: 'INFO' },
  { id: 'warn', label: 'WARN' },
  { id: 'error', label: 'ERROR' },
] as const

function getLevelBadgeVariant(level: string): 'neutral' | 'success' | 'warning' | 'danger' {
  switch (level) {
    case 'warn':
      return 'warning'
    case 'error':
      return 'danger'
    default:
      return 'neutral'
  }
}
</script>

<template>
  <div
    v-if="appStore.isLogDrawerOpen"
    class="h-56 bg-panel border-t border-border-default flex flex-col shrink-0 transition-all duration-150 z-20 shadow-lg"
  >
    <!-- Drawer Toolbar -->
    <div class="h-9 px-3 border-b border-border-subtle flex items-center justify-between bg-muted/40 shrink-0 select-none">
      <!-- Title & Filters -->
      <div class="flex items-center gap-3">
        <div class="flex items-center gap-1.5 text-xs font-semibold text-content-primary">
          <Terminal class="w-3.5 h-3.5 text-primary-600" />
          <span>系统日志 / 事件流</span>
        </div>

        <div class="flex items-center gap-1 bg-panel border border-border-subtle rounded p-0.5">
          <button
            v-for="lvl in filterLevels"
            :key="lvl.id"
            type="button"
            @click="appStore.logFilterLevel = lvl.id"
            class="px-2 py-0.5 rounded text-2xs font-mono transition-colors"
            :class="appStore.logFilterLevel === lvl.id ? 'bg-primary-50 text-primary-700 dark:bg-primary-950 font-bold' : 'text-content-muted hover:text-content-primary'"
          >
            {{ lvl.label }}
          </button>
        </div>
      </div>

      <!-- Controls -->
      <div class="flex items-center gap-2">
        <!-- Auto Scroll Toggle -->
        <label class="flex items-center gap-1 text-2xs text-content-secondary cursor-pointer">
          <input
            type="checkbox"
            v-model="appStore.isAutoScrollLogs"
            class="rounded border-border-default text-primary-600 focus:ring-0"
          />
          <ArrowDown class="w-3 h-3" />
          <span>自动滚底</span>
        </label>

        <!-- Clear Logs -->
        <button
          type="button"
          @click="appStore.clearLogs"
          class="p-1 rounded text-content-muted hover:text-content-primary hover:bg-muted transition-colors"
          title="清空日志"
        >
          <Trash2 class="w-3.5 h-3.5" />
        </button>

        <!-- Close Drawer -->
        <button
          type="button"
          @click="appStore.toggleLogDrawer"
          class="p-1 rounded text-content-muted hover:text-content-primary hover:bg-muted transition-colors"
          title="关闭抽屉"
        >
          <X class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>

    <!-- Logs Content -->
    <div
      ref="logListRef"
      class="flex-1 overflow-y-auto p-2 font-mono text-2xs space-y-1 bg-code/50"
    >
      <div v-if="appStore.filteredLogs.length === 0" class="h-full flex items-center justify-center text-content-disabled">
        暂无日志条目
      </div>
      <div
        v-for="log in appStore.filteredLogs"
        :key="log.id"
        class="flex items-start gap-2 py-0.5 px-1.5 rounded hover:bg-panel/80 transition-colors leading-relaxed"
      >
        <span class="text-content-disabled shrink-0 select-none">[{{ log.timestamp }}]</span>
        <HqBadge :variant="getLevelBadgeVariant(log.level)" size="sm" class="shrink-0 font-bold">
          {{ log.level.toUpperCase() }}
        </HqBadge>
        <span class="text-primary-600 dark:text-primary-400 shrink-0">[{{ log.source }}]</span>
        <span
          class="flex-1 break-all"
          :class="log.level === 'error' ? 'text-rose-600 dark:text-rose-400 font-semibold' : log.level === 'warn' ? 'text-amber-600 dark:text-amber-400' : 'text-content-primary'"
        >
          {{ log.message }}
        </span>
      </div>
    </div>
  </div>
</template>
