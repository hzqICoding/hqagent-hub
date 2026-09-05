<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  value?: number
  indeterminate?: boolean
  size?: 'sm' | 'md' | 'lg'
  variant?: 'primary' | 'success' | 'warning' | 'danger'
  showText?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  value: 0,
  indeterminate: false,
  size: 'md',
  variant: 'primary',
  showText: false,
})

const clampedValue = computed(() => Math.max(0, Math.min(100, props.value)))

const heightClasses = computed(() => {
  switch (props.size) {
    case 'sm':
      return 'h-1.5'
    case 'lg':
      return 'h-3'
    case 'md':
    default:
      return 'h-2'
  }
})

const barColor = computed(() => {
  switch (props.variant) {
    case 'success':
      return 'bg-status-success'
    case 'warning':
      return 'bg-status-warning'
    case 'danger':
      return 'bg-status-danger'
    case 'primary':
    default:
      return 'bg-action-primary'
  }
})
</script>

<template>
  <div class="w-full flex items-center gap-2">
    <div
      role="progressbar"
      :aria-valuenow="indeterminate ? undefined : clampedValue"
      aria-valuemin="0"
      aria-valuemax="100"
      :class="[
        'w-full bg-muted rounded-full overflow-hidden relative',
        heightClasses,
      ]"
    >
      <div
        v-if="indeterminate"
        :class="['h-full w-1/3 rounded-full animate-pulse', barColor]"
      />
      <div
        v-else
        :class="['h-full rounded-full transition-all duration-300 ease-out', barColor]"
        :style="{ width: `${clampedValue}%` }"
      />
    </div>

    <span
      v-if="showText && !indeterminate"
      class="text-xs font-mono text-content-secondary shrink-0"
    >
      {{ Math.round(clampedValue) }}%
    </span>
  </div>
</template>
