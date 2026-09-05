<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  variant?: 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'primary' | 'role'
  role?: string
  size?: 'sm' | 'md'
  dot?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'neutral',
  size: 'md',
  dot: false,
})

const badgeClasses = computed(() => {
  if (props.variant === 'role' && props.role) {
    return 'bg-muted text-content-primary border border-border font-medium'
  }

  switch (props.variant) {
    case 'success':
      return 'bg-status-success-soft text-status-success border-transparent'
    case 'warning':
      return 'bg-status-warning-soft text-status-warning border-transparent'
    case 'danger':
      return 'bg-status-danger-soft text-status-danger border-transparent'
    case 'info':
      return 'bg-status-info-soft text-status-info border-transparent'
    case 'primary':
      return 'bg-accent-soft text-action-primary border-transparent'
    case 'neutral':
    default:
      return 'bg-muted text-content-secondary border-border-subtle'
  }
})

const dotColor = computed(() => {
  switch (props.variant) {
    case 'success':
      return 'bg-status-success'
    case 'warning':
      return 'bg-status-warning'
    case 'danger':
      return 'bg-status-danger'
    case 'info':
      return 'bg-status-info'
    case 'primary':
      return 'bg-action-primary'
    default:
      return 'bg-content-muted'
  }
})

const sizeClasses = computed(() => {
  switch (props.size) {
    case 'sm':
      return 'px-1.5 py-0.5 text-[11px] gap-1'
    case 'md':
    default:
      return 'px-2 py-0.5 text-xs gap-1.5'
  }
})
</script>

<template>
  <span
    :class="[
      'inline-flex items-center font-medium border rounded-[var(--radius-xs)] select-none shrink-0 leading-tight',
      badgeClasses,
      sizeClasses,
    ]"
  >
    <span v-if="dot" :class="['h-1.5 w-1.5 rounded-full shrink-0', dotColor]" />
    <slot />
  </span>
</template>
