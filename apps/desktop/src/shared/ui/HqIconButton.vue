<script setup lang="ts">
import { computed } from 'vue'
import { Loader2 } from 'lucide-vue-next'

interface Props {
  label: string
  variant?: 'ghost' | 'secondary' | 'primary' | 'danger' | 'outline'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  disabled?: boolean
  type?: 'button' | 'submit'
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'ghost',
  size: 'md',
  loading: false,
  disabled: false,
  type: 'button',
})

const emit = defineEmits<{
  (e: 'click', event: MouseEvent): void
}>()

const isDisabled = computed(() => props.disabled || props.loading)

const variantClasses = computed(() => {
  switch (props.variant) {
    case 'primary':
      return 'bg-action-primary text-action-primary-text hover:bg-action-primary-hover active:bg-action-primary-active border-transparent'
    case 'secondary':
      return 'bg-muted text-content-primary hover:bg-elevated border-border'
    case 'danger':
      return 'bg-status-danger text-white hover:opacity-90 border-transparent'
    case 'outline':
      return 'bg-transparent text-content-primary hover:bg-muted border-border'
    case 'ghost':
    default:
      return 'bg-transparent text-content-secondary hover:text-content-primary hover:bg-muted border-transparent'
  }
})

const sizeClasses = computed(() => {
  switch (props.size) {
    case 'sm':
      return 'h-7 w-7 p-1 rounded-[var(--radius-xs)]'
    case 'lg':
      return 'h-10 w-10 p-2.5 rounded-[var(--radius-md)]'
    case 'md':
    default:
      return 'h-8 w-8 p-1.5 rounded-[var(--radius-sm)]'
  }
})
</script>

<template>
  <button
    :type="type"
    :aria-label="label"
    :title="label"
    :disabled="isDisabled"
    :class="[
      'inline-flex items-center justify-center border transition-colors outline-none shrink-0',
      'focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-app',
      'disabled:opacity-40 disabled:cursor-not-allowed',
      variantClasses,
      sizeClasses,
    ]"
    @click="emit('click', $event)"
  >
    <Loader2 v-if="loading" class="animate-spin h-4 w-4" />
    <slot v-else />
  </button>
</template>
