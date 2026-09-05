<script setup lang="ts">
import type { Component } from 'vue'

export interface TabItem {
  id: string | number
  label: string
  count?: number
  icon?: Component
  disabled?: boolean
}

interface Props {
  modelValue: string | number
  tabs: TabItem[]
  variant?: 'line' | 'pill'
  size?: 'sm' | 'md'
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'line',
  size: 'md',
})

const emit = defineEmits<{
  (e: 'update:modelValue', id: string | number): void
  (e: 'change', id: string | number): void
}>()

function select(tab: TabItem) {
  if (tab.disabled) return
  emit('update:modelValue', tab.id)
  emit('change', tab.id)
}
</script>

<template>
  <div
    role="tablist"
    :class="[
      'flex items-center',
      variant === 'line'
        ? 'border-b border-border gap-6'
        : 'p-1 bg-muted rounded-[var(--radius-sm)] gap-1',
    ]"
  >
    <button
      v-for="tab in tabs"
      :key="tab.id"
      type="button"
      role="tab"
      :aria-selected="tab.id === modelValue"
      :disabled="tab.disabled"
      :class="[
        'flex items-center font-medium transition-colors outline-none select-none relative',
        'focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
        tab.disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer',
        size === 'sm' ? 'text-xs py-1.5' : 'text-sm py-2',
        variant === 'line'
          ? [
              '-mb-px border-b-2',
              tab.id === modelValue
                ? 'border-action-primary text-action-primary'
                : 'border-transparent text-content-secondary hover:text-content-primary',
            ]
          : [
              'px-3 rounded-[var(--radius-xs)]',
              tab.id === modelValue
                ? 'bg-panel text-content-primary shadow-sm font-semibold'
                : 'text-content-secondary hover:text-content-primary',
            ],
      ]"
      @click="select(tab)"
    >
      <component :is="tab.icon" v-if="tab.icon" class="h-4 w-4 mr-1.5" />
      <span>{{ tab.label }}</span>
      <span
        v-if="typeof tab.count === 'number'"
        :class="[
          'ml-1.5 px-1.5 py-0.2 rounded-full text-[10px] font-mono leading-tight',
          tab.id === modelValue
            ? 'bg-action-primary text-action-primary-text'
            : 'bg-muted text-content-muted',
        ]"
      >
        {{ tab.count }}
      </span>
    </button>
  </div>
</template>
