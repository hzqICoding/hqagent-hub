<script setup lang="ts">
import { WifiOff, RefreshCw } from 'lucide-vue-next'
import HqButton from '../HqButton.vue'

interface Props {
  title?: string
  message?: string
}

withDefaults(defineProps<Props>(), {
  title: 'Local Hub 已断开连接',
  message: '无法与本地 Agent Hub 服务建立通信。请确认 hqagent-core.exe 服务是否正常运行。',
})

const emit = defineEmits<{
  (e: 'reconnect'): void
}>()
</script>

<template>
  <div class="flex flex-col items-center justify-center p-8 text-center border border-border bg-panel rounded-[var(--radius-md)] select-none">
    <div class="h-12 w-12 rounded-full bg-status-neutral-soft flex items-center justify-center text-status-neutral mb-3">
      <WifiOff class="h-6 w-6 stroke-[1.5]" />
    </div>

    <h4 class="text-sm font-semibold text-content-primary mb-1">
      {{ title }}
    </h4>

    <p class="text-xs text-content-secondary max-w-sm mb-4 leading-relaxed">
      {{ message }}
    </p>

    <HqButton variant="secondary" size="sm" @click="emit('reconnect')">
      <template #icon>
        <RefreshCw class="h-3.5 w-3.5 mr-1" />
      </template>
      尝试重新连接
    </HqButton>
  </div>
</template>
