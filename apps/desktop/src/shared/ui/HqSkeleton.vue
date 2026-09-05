<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

interface Props {
  width?: string
  height?: string
  rounded?: 'xs' | 'sm' | 'md' | 'lg' | 'full'
  delay?: number
}

const props = withDefaults(defineProps<Props>(), {
  width: '100%',
  height: '1rem',
  rounded: 'sm',
  delay: 300,
})

const isVisible = ref(props.delay <= 0)
let timer: ReturnType<typeof setTimeout> | null = null

onMounted(() => {
  if (props.delay > 0) {
    timer = setTimeout(() => {
      isVisible.value = true
    }, props.delay)
  }
})

onUnmounted(() => {
  if (timer) clearTimeout(timer)
})
</script>

<template>
  <div
    v-if="isVisible"
    :class="[
      'bg-muted animate-pulse',
      rounded === 'full'
        ? 'rounded-full'
        : rounded === 'lg'
          ? 'rounded-[var(--radius-lg)]'
          : rounded === 'md'
            ? 'rounded-[var(--radius-md)]'
            : rounded === 'xs'
              ? 'rounded-[var(--radius-xs)]'
              : 'rounded-[var(--radius-sm)]',
    ]"
    :style="{ width, height }"
  />
</template>
