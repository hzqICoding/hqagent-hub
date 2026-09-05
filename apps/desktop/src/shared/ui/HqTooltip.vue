<script setup lang="ts">
import { ref } from 'vue'

interface Props {
  content?: string
  placement?: 'top' | 'bottom' | 'left' | 'right'
  delay?: number
}

const props = withDefaults(defineProps<Props>(), {
  content: '',
  placement: 'top',
  delay: 200,
})

const isVisible = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null

function show() {
  timer = setTimeout(() => {
    isVisible.value = true
  }, props.delay)
}

function hide() {
  if (timer) clearTimeout(timer)
  isVisible.value = false
}
</script>

<template>
  <div
    class="relative inline-flex"
    @mouseenter="show"
    @mouseleave="hide"
    @focusin="show"
    @focusout="hide"
  >
    <slot />

    <div
      v-if="isVisible && (content || $slots.content)"
      role="tooltip"
      :class="[
        'absolute z-50 px-2 py-1 text-xs text-white bg-slate-900 rounded-[var(--radius-xs)] shadow-popover pointer-events-none whitespace-nowrap transition-opacity duration-150',
        placement === 'top' ? 'bottom-full left-1/2 -translate-x-1/2 mb-1.5' : '',
        placement === 'bottom' ? 'top-full left-1/2 -translate-x-1/2 mt-1.5' : '',
        placement === 'left' ? 'right-full top-1/2 -translate-y-1/2 mr-1.5' : '',
        placement === 'right' ? 'left-full top-1/2 -translate-y-1/2 ml-1.5' : '',
      ]"
    >
      <slot name="content">{{ content }}</slot>
    </div>
  </div>
</template>
