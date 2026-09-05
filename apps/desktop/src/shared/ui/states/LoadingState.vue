<script setup lang="ts">
import HqSkeleton from '../HqSkeleton.vue'

interface Props {
  text?: string
  rows?: number
  delay?: number
}

withDefaults(defineProps<Props>(), {
  text: '加载数据中...',
  rows: 4,
  delay: 300,
})
</script>

<template>
  <div class="w-full space-y-3 p-4 select-none">
    <div class="flex items-center gap-3">
      <HqSkeleton width="48px" height="48px" rounded="lg" :delay="delay" />
      <div class="space-y-2 flex-1">
        <HqSkeleton width="30%" height="16px" rounded="sm" :delay="delay" />
        <HqSkeleton width="60%" height="12px" rounded="xs" :delay="delay" />
      </div>
    </div>

    <div class="space-y-2 pt-2">
      <HqSkeleton
        v-for="r in rows"
        :key="r"
        width="100%"
        height="12px"
        rounded="xs"
        :delay="delay"
      />
    </div>

    <div v-if="text" class="text-xs text-content-muted text-center pt-2">
      {{ text }}
    </div>
  </div>
</template>
