<script setup lang="ts">
import HqDialog from './HqDialog.vue'
import HqButton from './HqButton.vue'
defineProps<{ title: string; description?: string; confirmText?: string; cancelText?: string; danger?: boolean }>()
defineEmits<{ answer: [confirmed: boolean] }>()
</script>
<template>
  <HqDialog :open="true" :title="title" :description="description" :close-on-backdrop="!danger" initial-focus="[data-confirm-cancel]" @close="$emit('answer', false)">
    <template #footer>
      <HqButton data-confirm-cancel variant="secondary" class="min-h-[44px] min-w-[72px]" @click="$emit('answer', false)">{{ cancelText || '取消' }}</HqButton>
      <HqButton :variant="danger ? 'danger' : 'primary'" class="min-h-[44px] min-w-[72px]" @click="$emit('answer', true)">{{ confirmText || '确认' }}</HqButton>
    </template>
  </HqDialog>
</template>
