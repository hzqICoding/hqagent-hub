<script setup lang="ts">
import type { Component } from 'vue'

export interface SegmentedOption<T = string | number> {
  label: string
  value: T
  icon?: Component
  disabled?: boolean
  badge?: string | number
}

interface Props {
  modelValue: string | number
  options: SegmentedOption[]
  size?: 'sm' | 'md'
  block?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  size: 'md',
  block: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | number): void
  (e: 'change', value: string | number): void
}>()

function select(option: SegmentedOption) {
  if (option.disabled || option.value === props.modelValue) return
  emit('update:modelValue', option.value)
  emit('change', option.value)
}
</script>

<template>
  <div
    role="radiogroup"
    :class="[
      'inline-flex items-center p-1 bg-muted/80 rounded-[var(--radius-sm)] border border-border-subtle select-none',
      block ? 'w-full' : '',
    ]"
  >
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      role="radio"
      :aria-checked="opt.value === modelValue"
      :disabled="opt.disabled"
      :class="[
        'flex items-center justify-center font-medium transition-all duration-150 outline-none rounded-[var(--radius-xs)]',
        'focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
        block ? 'flex-1' : '',
        size === 'sm' ? 'px-2.5 py-1 text-xs gap-1.5' : 'px-3.5 py-1.5 text-sm gap-2',
        opt.disabled
          ? 'opacity-40 cursor-not-allowed'
          : 'cursor-pointer',
        opt.value === modelValue
          ? 'bg-panel text-content-primary shadow-xs font-semibold'
          : 'text-content-secondary hover:text-content-primary hover:bg-panel/40',
      ]"
      @click="select(opt)"
    >
      <component :is="opt.icon" v-if="opt.icon" class="h-3.5 w-3.5 shrink-0" />
      <span>{{ opt.label }}</span>
      <span
        v-if="opt.badge !== undefined"
        class="ml-1 px-1.5 py-0.2 rounded-full text-[10px] bg-muted text-content-muted"
      >
        {{ opt.badge }}
      </span>
    </button>
  </div>
</template>
