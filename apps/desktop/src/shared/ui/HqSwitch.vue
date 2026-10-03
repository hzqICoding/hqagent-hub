<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  modelValue?: boolean
  label?: string
  disabled?: boolean
  size?: 'sm' | 'md'
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: false,
  label: '',
  disabled: false,
  size: 'md',
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
    :data-disabled="disabled || undefined"
    :class="[
      'hq-choice-field inline-flex items-center gap-2.5 select-none',
      disabled ? 'cursor-not-allowed' : 'cursor-pointer',
    ]"
  >
    <button
      type="button"
      role="switch"
      :aria-checked="isChecked"
      :disabled="disabled"
      :class="[
        'relative inline-flex shrink-0 transition-colors duration-200 ease-in-out rounded-full outline-none',
        'focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-app',
        isChecked ? 'bg-action-primary' : 'bg-muted border border-border',
        size === 'sm' ? 'h-4 w-7' : 'h-5 w-9',
      ]"
      @click="toggle"
    >
      <span
        :class="[
          'pointer-events-none inline-block rounded-full bg-white shadow transform ring-0 transition duration-200 ease-in-out',
          size === 'sm' ? 'h-3 w-3 mt-0.5' : 'h-4 w-4 mt-0.5',
          isChecked
            ? size === 'sm'
              ? 'translate-x-3.5'
              : 'translate-x-4.5'
            : 'translate-x-0.5',
        ]"
      />
    </button>

    <span v-if="label || $slots.default" class="hq-choice-label text-sm text-content-primary">
      <slot>{{ label }}</slot>
    </span>
  </label>
</template>
