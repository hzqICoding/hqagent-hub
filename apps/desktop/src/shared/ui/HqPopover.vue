<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

interface Props {
  placement?: 'bottom-start' | 'bottom-end' | 'top-start' | 'top-end'
  width?: string
}

const _props = withDefaults(defineProps<Props>(), {
  placement: 'bottom-start',
  width: 'auto',
})

const isOpen = ref(false)
const containerRef = ref<HTMLElement | null>(null)

function toggle() {
  isOpen.value = !isOpen.value
}

function close() {
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

defineExpose({ open: () => (isOpen.value = true), close, toggle })
</script>

<template>
  <div ref="containerRef" class="relative inline-block">
    <div @click="toggle">
      <slot name="trigger" :is-open="isOpen" />
    </div>

    <div
      v-if="isOpen"
      :class="[
        'absolute z-50 mt-1 bg-elevated border border-border rounded-[var(--radius-md)] shadow-popover p-3',
        placement === 'bottom-start' ? 'top-full left-0' : '',
        placement === 'bottom-end' ? 'top-full right-0' : '',
        placement === 'top-start' ? 'bottom-full left-0 mb-1' : '',
        placement === 'top-end' ? 'bottom-full right-0 mb-1' : '',
      ]"
      :style="{ width }"
    >
      <slot :close="close" />
    </div>
  </div>
</template>
