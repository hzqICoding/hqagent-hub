<script setup lang="ts">
import type { LocalMessageView } from '@hqagent/protocol'
import {
  HqMarkdown,
} from '@/shared/ui'
import {
  User,
  Bot,
  Terminal,
} from 'lucide-vue-next'

interface Props {
  message: LocalMessageView
}

defineProps<Props>()

function formatTime(iso: string) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return iso
  }
}
</script>

<template>
  <div class="py-3 px-4 transition-colors">
    <!-- User Message -->
    <div v-if="message.role === 'user'" class="flex items-start gap-3 max-w-3xl">
      <div class="w-7 h-7 rounded-full bg-primary/20 text-primary flex items-center justify-center shrink-0 mt-0.5 text-xs font-semibold">
        <User class="w-4 h-4" />
      </div>
      <div class="flex-1 space-y-1">
        <div class="flex items-center gap-2 text-[11px] text-text-muted">
          <span class="font-medium text-text">你</span>
          <span>#{{ message.sequence }}</span>
          <span>{{ formatTime(message.createdAt) }}</span>
        </div>
        <div class="bg-primary/10 text-text p-3 rounded-[var(--radius-md)] rounded-tl-sm text-xs leading-relaxed whitespace-pre-wrap select-text border border-primary/20">
          {{ message.text }}
        </div>
      </div>
    </div>

    <!-- System / Role Process Message (Step progression, NO hidden model thoughts) -->
    <div
      v-else-if="message.role === 'system'"
      class="flex items-start gap-3 max-w-3xl my-1"
    >
      <div class="w-7 h-7 rounded-full bg-bg-app border border-border text-text-muted flex items-center justify-center shrink-0 mt-0.5">
        <Terminal class="w-3.5 h-3.5" />
      </div>
      <div class="flex-1 space-y-1">
        <div class="flex items-center gap-2 text-[11px] text-text-muted">
          <span class="font-medium text-text-muted">角色执行过程</span>
          <span>#{{ message.sequence }}</span>
          <span>{{ formatTime(message.createdAt) }}</span>
        </div>
        <div class="bg-bg-app border border-border/80 text-text-muted p-2.5 rounded-[var(--radius-sm)] text-xs font-mono leading-relaxed select-text flex items-start gap-2">
          <span class="text-primary shrink-0">&gt;</span>
          <span class="flex-1">{{ message.text }}</span>
        </div>
      </div>
    </div>

    <!-- Assistant Final Reply -->
    <div v-else class="flex items-start gap-3 max-w-3xl">
      <div class="w-7 h-7 rounded-full bg-success/15 text-success flex items-center justify-center shrink-0 mt-0.5">
        <Bot class="w-4 h-4" />
      </div>
      <div class="flex-1 space-y-1">
        <div class="flex items-center gap-2 text-[11px] text-text-muted">
          <span class="font-medium text-text">HQAgent 团队</span>
          <span>#{{ message.sequence }}</span>
          <span>{{ formatTime(message.createdAt) }}</span>
        </div>
        <div class="bg-panel border border-border p-4 rounded-[var(--radius-md)] rounded-tl-sm text-xs leading-relaxed shadow-sm">
          <HqMarkdown :content="message.text" />
        </div>
      </div>
    </div>
  </div>
</template>
