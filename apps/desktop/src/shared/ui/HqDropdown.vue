<script setup lang="ts">
import { ref, onMounted, onUnmounted, type Component } from 'vue'

export interface DropdownItem {
  id?: string
  label: string
  action?: () => void
  icon?: Component
  danger?: boolean
  disabled?: boolean
  divider?: boolean
}

interface Props {
  items: DropdownItem[]
  placement?: 'left' | 'right'
}

const _props = withDefaults(defineProps<Props>(), {
  placement: 'right',
})

const isOpen = ref(false)
const containerRef = ref<HTMLElement | null>(null)

function toggle() {
  isOpen.value = !isOpen.value
}

function handleAction(item: DropdownItem) {
  if (item.disabled || item.divider) return
  if (item.action) item.action()
  isOpen.value = false
}

function handleClickOutside(e: MouseEvent) {
  if (containerRef.value && !containerRef.value.contains(e.target as Node)) {
    isOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<template>
  <div ref="containerRef" class="relative inline-block text-left">
    <div @click="toggle">
      <slot :is-open="isOpen" />
    </div>

    <div
      v-if="isOpen"
      :class="[
        'absolute z-50 mt-1 min-w-[140px] bg-elevated border border-border rounded-[var(--radius-sm)] shadow-popover py-1 focus:outline-none',
        placement === 'right' ? 'right-0' : 'left-0',
      ]"
    >
      <template v-for="(item, idx) in items" :key="idx">
        <div v-if="item.divider" class="my-1 border-t border-border-subtle" />
        <button
          v-else
          type="button"
          :disabled="item.disabled"
          :class="[
            'w-full flex items-center px-3 py-1.5 text-xs text-left transition-colors select-none',
            item.disabled
              ? 'opacity-40 cursor-not-allowed text-content-disabled'
              : item.danger
                ? 'text-status-danger hover:bg-status-danger-soft'
                : 'text-content-primary hover:bg-muted',
          ]"
          @click="handleAction(item)"
        >
          <component :is="item.icon" v-if="item.icon" class="h-3.5 w-3.5 mr-2 shrink-0" />
          <span>{{ item.label }}</span>
        </button>
      </template>
    </div>
  </div>
</template>
