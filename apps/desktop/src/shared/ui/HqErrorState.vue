<script setup lang="ts">
import { AlertCircle, RefreshCw } from 'lucide-vue-next'
import HqButton from './HqButton.vue'

interface Props {
  code?: string
  title?: string
  message?: string
  retryable?: boolean
  retryText?: string
  diagnosticId?: string
}

withDefaults(defineProps<Props>(), {
  title: '操作出现异常',
  message: '无法完成当前请求，请检查日志或重试。',
  retryable: true,
  retryText: '重试',
})

const emit = defineEmits<{
  (e: 'retry'): void
}>()
</script>

<template>
  <div class="flex flex-col items-center justify-center p-8 text-center border border-status-danger/30 bg-status-danger-soft/10 rounded-[var(--radius-md)] select-none">
    <div class="h-11 w-11 rounded-full bg-status-danger-soft flex items-center justify-center text-status-danger mb-3">
      <AlertCircle class="h-6 w-6 stroke-[1.5]" />
    </div>

    <div v-if="code" class="text-[11px] font-mono font-semibold text-status-danger uppercase tracking-wider mb-1">
      [{{ code }}]
    </div>

    <h4 class="text-sm font-semibold text-content-primary mb-1">
      {{ title }}
    </h4>

    <p class="text-xs text-content-secondary max-w-md mb-4 leading-relaxed">
      {{ message }}
    </p>

    <div v-if="diagnosticId" class="text-[10px] font-mono text-content-muted mb-3">
      诊断追溯号: {{ diagnosticId }}
    </div>

    <div class="flex items-center gap-2">
      <HqButton v-if="retryable" variant="primary" size="sm" @click="emit('retry')">
        <template #icon>
          <RefreshCw class="h-3.5 w-3.5 mr-1" />
        </template>
        {{ retryText }}
      </HqButton>
      <slot name="extra" />
    </div>
  </div>
</template>
