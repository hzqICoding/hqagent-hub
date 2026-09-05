<script setup lang="ts">
import type { Component } from 'vue'
import { Inbox } from 'lucide-vue-next'
import HqButton from './HqButton.vue'

interface Props {
  title?: string
  description?: string
  actionText?: string
  icon?: Component
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'action'): void
}>()
</script>

<template>
  <div class="flex flex-col items-center justify-center p-8 text-center select-none">
    <div class="h-12 w-12 rounded-full bg-muted flex items-center justify-center text-content-muted mb-3.5">
      <component :is="icon || Inbox" class="h-6 w-6 stroke-[1.5]" />
    </div>

    <h4 v-if="title || $slots.title" class="text-sm font-semibold text-content-primary mb-1">
      <slot name="title">{{ title }}</slot>
    </h4>

    <p v-if="description || $slots.description" class="text-xs text-content-secondary max-w-sm mb-4 leading-relaxed">
      <slot name="description">{{ description }}</slot>
    </p>

    <div v-if="actionText || $slots.action">
      <slot name="action">
        <HqButton size="sm" @click="emit('action')">
          {{ actionText }}
        </HqButton>
      </slot>
    </div>
  </div>
</template>
