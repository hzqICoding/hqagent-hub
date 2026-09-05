<script setup lang="ts" generic="T">
import { ref, computed, onMounted } from 'vue'

interface Props {
  items: T[]
  itemHeight?: number
  containerHeight?: string
  buffer?: number
}

const props = withDefaults(defineProps<Props>(), {
  itemHeight: 32,
  containerHeight: '360px',
  buffer: 6,
})

const containerRef = ref<HTMLElement | null>(null)
const scrollTop = ref(0)
const viewportHeight = ref(360)

const totalHeight = computed(() => props.items.length * props.itemHeight)

const startIndex = computed(() => {
  const idx = Math.floor(scrollTop.value / props.itemHeight) - props.buffer
  return Math.max(0, idx)
})

const visibleCount = computed(() => {
  return Math.ceil(viewportHeight.value / props.itemHeight) + props.buffer * 2
})

const endIndex = computed(() => {
  return Math.min(props.items.length, startIndex.value + visibleCount.value)
})

const visibleItems = computed(() => {
  return props.items.slice(startIndex.value, endIndex.value).map((item, i) => ({
    item,
    index: startIndex.value + i,
    top: (startIndex.value + i) * props.itemHeight,
  }))
})

function onScroll() {
  if (containerRef.value) {
    scrollTop.value = containerRef.value.scrollTop
  }
}

function scrollToIndex(index: number) {
  if (containerRef.value) {
    containerRef.value.scrollTop = index * props.itemHeight
  }
}

function scrollToBottom() {
  if (containerRef.value) {
    containerRef.value.scrollTop = totalHeight.value
  }
}

onMounted(() => {
  if (containerRef.value) {
    viewportHeight.value = containerRef.value.clientHeight
  }
})

defineExpose({ scrollToIndex, scrollToBottom })
</script>

<template>
  <div
    ref="containerRef"
    class="relative overflow-y-auto border border-border rounded-[var(--radius-sm)] bg-panel focus:outline-none"
    :style="{ height: containerHeight }"
    @scroll="onScroll"
  >
    <!-- Ghost element ensuring full scrollable height -->
    <div :style="{ height: totalHeight + 'px', width: '100%', position: 'relative' }">
      <div
        v-for="entry in visibleItems"
        :key="entry.index"
        class="absolute left-0 right-0 w-full"
        :style="{
          top: entry.top + 'px',
          height: itemHeight + 'px',
        }"
      >
        <slot :item="entry.item" :index="entry.index" />
      </div>
    </div>
  </div>
</template>
