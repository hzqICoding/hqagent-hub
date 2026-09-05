<script setup lang="ts">
import { computed } from 'vue'
import { Loader2 } from 'lucide-vue-next'

interface Props {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'outline'
  size?: 'sm' | 'md' | 'lg'
  type?: 'button' | 'submit' | 'reset'
  loading?: boolean
  disabled?: boolean
  block?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'primary',
  size: 'md',
  type: 'button',
  loading: false,
  disabled: false,
  block: false,
})

const emit = defineEmits<{
  (e: 'click', event: MouseEvent): void
}>()

const isDisabled = computed(() => props.disabled || props.loading)

const variantClasses = computed(() => {
  switch (props.variant) {
    case 'primary':
      return 'bg-action-primary hover:bg-action-primary-hover active:bg-action-primary-active text-action-primary-text border-transparent shadow-sm'
    case 'secondary':
      return 'bg-muted hover:bg-elevated active:bg-app text-content-primary border-border hover:border-border-strong'
    case 'danger':
      return 'bg-status-danger hover:opacity-90 active:opacity-80 text-white border-transparent'
    case 'outline':
      return 'bg-transparent hover:bg-muted active:bg-app text-content-primary border-border hover:border-action-primary'
    case 'ghost':
      return 'bg-transparent hover:bg-muted active:bg-app text-content-secondary hover:text-content-primary border-transparent'
    default:
      return 'bg-action-primary text-action-primary-text border-transparent'
  }
})

const sizeClasses = computed(() => {
  switch (props.size) {
    case 'sm':
      return 'h-7 px-2.5 text-xs gap-1.5 rounded-[var(--radius-sm)]'
    case 'lg':
      return 'h-11 px-5 text-base gap-2.5 rounded-[var(--radius-md)]'
    case 'md':
    default:
      return 'h-9 px-3.5 text-sm gap-2 rounded-[var(--radius-sm)]'
  }
})

function handleClick(event: MouseEvent) {
  if (!isDisabled.value) {
    emit('click', event)
  }
}
</script>

<template>
  <button
    :type="type"
    :disabled="isDisabled"
    :class="[
      'inline-flex items-center justify-center font-medium border transition-colors select-none outline-none',
      'focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-app',
      'disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none',
      variantClasses,
      sizeClasses,
      block ? 'w-full' : '',
    ]"
    @click="handleClick"
  >
    <Loader2 v-if="loading" class="animate-spin shrink-0 h-4 w-4" />
    <slot name="icon" v-if="!loading" />
    <slot />
  </button>
</template>
