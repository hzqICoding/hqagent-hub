<script setup lang="ts">
import type { MessageAttachmentView, AttachmentManifestItem } from '@hqagent/protocol'
import AttachmentItem from './AttachmentItem.vue'
defineProps<{ attachments: (MessageAttachmentView | AttachmentManifestItem)[]; remote?: boolean }>()
</script>
<template>
  <div class="min-w-0 max-w-full space-y-2 mt-2 whitespace-normal text-content-primary" aria-label="消息附件">
    <div class="grid grid-cols-2 sm:grid-cols-3 gap-2 min-w-0"><AttachmentItem v-for="item in attachments.filter((a) => a.kind === 'image').slice(0,5)" :key="item.attachmentId" :attachment="item" :remote="remote" /></div>
    <AttachmentItem v-for="item in attachments.filter((a) => a.kind !== 'image')" :key="item.attachmentId" :attachment="item" :remote="remote" />
  </div>
</template>
