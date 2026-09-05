<script setup lang="ts">
import { computed } from 'vue'
import { Check, Minus } from 'lucide-vue-next'

interface Props {
  modelValue?: boolean
  label?: string
  disabled?: boolean
  indeterminate?: boolean
  error?: string | boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: false,
  label: '',
  disabled: false,
  indeterminate: false,
  error: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'change', value: boolean): void
}>()

const isChecked = computed(() => props.modelValue)

function toggle() {
  if (props.disabled) return
  const next = !props.modelValue
  emit('update:modelValue', next)
  emit('change', next)
}
</script>

<template>
  <label
    :class="[
      'inline-flex items-center gap-2 select-none',
      disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
    ]"
  >
    <div
      :class="[
        'h-4 w-4 rounded-[var(--radius-xs)] border flex items-center justify-center transition-colors outline-none shrink-0',
        'focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-app',
        isChecked || indeterminate
          ? 'bg-action-primary border-action-primary text-action-primary-text'
          : 'bg-panel border-border hover:border-border-strong',
        error ? 'border-status-danger' : '',
      ]"
      tabindex="0"
      role="checkbox"
      :aria-checked="indeterminate ? 'mixed' : isChecked"
      :aria-disabled="disabled"
      @keydown.space.prevent="toggle"
      @click.prevent="toggle"
    >
      <Minus v-if="indeterminate" class="h-3 w-3 stroke-[3]" />
      <Check v-else-if="isChecked" class="h-3 w-3 stroke-[3]" />
    </div>

    <span v-if="label || $slots.default" class="text-sm text-content-primary">
      <slot>{{ label }}</slot>
    </span>
  </label>
</template>
