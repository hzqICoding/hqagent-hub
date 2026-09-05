<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

interface Props {
  direction?: 'horizontal' | 'vertical'
  initialRatio?: number
  minRatio?: number
  maxRatio?: number
}

const props = withDefaults(defineProps<Props>(), {
  direction: 'horizontal',
  initialRatio: 0.5,
  minRatio: 0.15,
  maxRatio: 0.85,
})

const ratio = ref(props.initialRatio)
const isDragging = ref(false)
const containerRef = ref<HTMLElement | null>(null)

function onMouseDown(e: MouseEvent) {
  isDragging.value = true
  e.preventDefault()
}

function onMouseMove(e: MouseEvent) {
  if (!isDragging.value || !containerRef.value) return
  const rect = containerRef.value.getBoundingClientRect()
  let newRatio = ratio.value
  if (props.direction === 'horizontal') {
    newRatio = (e.clientX - rect.left) / rect.width
  } else {
    newRatio = (e.clientY - rect.top) / rect.height
  }
  ratio.value = Math.max(props.minRatio, Math.min(props.maxRatio, newRatio))
}

function onMouseUp() {
  isDragging.value = false
}

onMounted(() => {
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
})

onUnmounted(() => {
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
})
</script>

<template>
  <div
    ref="containerRef"
    :class="[
      'w-full h-full flex overflow-hidden select-none',
      direction === 'horizontal' ? 'flex-row' : 'flex-col',
    ]"
  >
    <!-- First Pane -->
    <div
      class="overflow-auto"
      :style="
        direction === 'horizontal'
          ? { width: `${ratio * 100}%` }
          : { height: `${ratio * 100}%` }
      "
    >
      <slot name="first" />
    </div>

    <!-- Divider Handle -->
    <div
      :class="[
        'shrink-0 bg-border hover:bg-action-primary transition-colors flex items-center justify-center',
        direction === 'horizontal'
          ? 'w-1 cursor-col-resize hover:w-1.5'
          : 'h-1 cursor-row-resize hover:h-1.5',
        isDragging ? 'bg-action-primary' : '',
      ]"
      @mousedown="onMouseDown"
    />

    <!-- Second Pane -->
    <div
      class="overflow-auto flex-1"
      :style="
        direction === 'horizontal'
          ? { width: `${(1 - ratio) * 100}%` }
          : { height: `${(1 - ratio) * 100}%` }
      "
    >
      <slot name="second" />
    </div>
  </div>
</template>
