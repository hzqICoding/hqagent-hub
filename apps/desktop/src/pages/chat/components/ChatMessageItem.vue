<script setup lang="ts">
import { ref, computed } from 'vue'
import type { LocalMessageView } from '@hqagent/protocol'
import { HqMarkdown } from '@/shared/ui'
import { useChatStore } from '@/stores/chat.store'
import ProcessActivityGroup from './ProcessActivityGroup.vue'
import {
  Bot,
  Terminal,
  Sparkles,
  ChevronDown,
  Copy,
  Check,
} from 'lucide-vue-next'

interface Props {
  message: LocalMessageView
}

const props = defineProps<Props>()

const chatStore = useChatStore()
const isExpanded = ref(true)
const isCopied = ref(false)

const activities = computed(() =>
  props.message.runId ? chatStore.getActivitiesForRun(props.message.runId) : []
)

function formatTime(iso: string) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return iso
  }
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    isCopied.value = true
    setTimeout(() => {
      isCopied.value = false
    }, 1800)
  } catch {
    // ignore
  }
}
</script>

<template>
  <div class="py-2.5 px-4 transition-colors">
    <!-- User Message (Clean right-aligned bubble) -->
    <div v-if="message.role === 'user'" class="flex justify-end max-w-3xl mx-auto">
      <div class="max-w-[85%] space-y-1 group">
        <div class="flex items-center justify-end gap-2 text-[11px] text-text-muted select-none">
          <button
            type="button"
            class="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-panel-hover text-text-muted hover:text-text transition-opacity flex items-center gap-1"
            title="复制输入"
            @click="copyText(message.text)"
          >
            <Check v-if="isCopied" class="w-3 h-3 text-success" />
            <Copy v-else class="w-3 h-3" />
          </button>
          <span class="font-medium text-text">你</span>
          <span>#{{ message.sequence }}</span>
          <span>{{ formatTime(message.createdAt) }}</span>
        </div>

        <div class="bg-primary/10 text-text p-3 px-4 rounded-2xl rounded-tr-xs text-xs leading-relaxed whitespace-pre-wrap break-words select-text border border-primary/20 shadow-xs">
          {{ message.text }}
        </div>
      </div>
    </div>

    <!-- System / Role Process Step (Collapsible Accordion like PI-Desktop ActivityGroup) -->
    <div
      v-else-if="message.role === 'system'"
      class="max-w-3xl mx-auto my-1"
    >
      <div class="rounded-xl border border-border/70 bg-panel/50 overflow-hidden shadow-xs transition-all">
        <!-- Header (Clickable disclosure) -->
        <button
          type="button"
          class="w-full p-2.5 px-3 flex items-center justify-between text-xs hover:bg-panel transition-colors text-left gap-2 select-none"
          @click="isExpanded = !isExpanded"
        >
          <div class="flex items-center gap-2 min-w-0">
            <div class="w-5 h-5 rounded-md bg-primary/10 text-primary flex items-center justify-center shrink-0">
              <Sparkles class="w-3 h-3" />
            </div>
            <span class="font-medium text-text text-xs shrink-0">角色执行过程</span>
            <span class="text-[10px] text-text-muted font-mono shrink-0">#{{ message.sequence }}</span>

            <!-- Compact preview when collapsed -->
            <span v-if="!isExpanded" class="text-[11px] text-text-muted truncate ml-1 font-mono">
              {{ message.text }}
            </span>
          </div>

          <div class="flex items-center gap-2 shrink-0">
            <span class="text-[10px] text-text-muted">{{ formatTime(message.createdAt) }}</span>
            <ChevronDown
              class="w-3.5 h-3.5 text-text-muted transition-transform duration-200"
              :class="isExpanded ? 'rotate-180' : ''"
            />
          </div>
        </button>

        <!-- Expanded Terminal Body -->
        <div
          v-if="isExpanded"
          class="p-3 border-t border-border/50 bg-bg-app/80 font-mono text-[11px] text-text-muted select-text space-y-1.5 leading-relaxed break-words whitespace-pre-wrap"
        >
          <div class="flex items-center gap-1.5 text-primary text-[10px] uppercase font-semibold tracking-wider select-none">
            <Terminal class="w-3 h-3" />
            <span>Agent Execution Log</span>
          </div>
          <div class="p-2.5 rounded-lg bg-panel/80 border border-border/60 text-text leading-relaxed">
            {{ message.text }}
          </div>
        </div>
      </div>
    </div>

    <!-- Assistant Final Reply (Clean typography, bot avatar, markdown body, copy button) -->
    <div v-else class="max-w-3xl mx-auto flex items-start gap-3 group">
      <div class="w-7 h-7 rounded-full bg-success/15 text-success flex items-center justify-center shrink-0 mt-0.5 border border-success/30 shadow-xs">
        <Bot class="w-4 h-4" />
      </div>

      <div class="flex-1 min-w-0 space-y-1.5">
        <div class="flex items-center justify-between text-[11px] text-text-muted select-none">
          <div class="flex items-center gap-2">
            <span class="font-semibold text-text text-xs">HQAgent 团队</span>
            <span class="font-mono text-[10px]">#{{ message.sequence }}</span>
            <span>{{ formatTime(message.createdAt) }}</span>
          </div>

          <button
            type="button"
            class="opacity-0 group-hover:opacity-100 p-1 px-1.5 rounded hover:bg-panel-hover text-text-muted hover:text-text transition-all flex items-center gap-1 text-[10px]"
            title="复制回复内容"
            @click="copyText(message.text)"
          >
            <Check v-if="isCopied" class="w-3 h-3 text-success" />
            <Copy v-else class="w-3 h-3" />
            <span>{{ isCopied ? '已复制' : '复制' }}</span>
          </button>
        </div>

        <!-- Collapsible Process Activities (matching PI-Desktop / Agent Timeline) -->
        <ProcessActivityGroup
          v-if="activities.length > 0"
          :activities="activities"
          :is-live="false"
          :initially-expanded="false"
        />

        <div class="bg-panel border border-border/80 p-4 rounded-2xl rounded-tl-xs text-xs leading-relaxed shadow-sm break-words overflow-x-auto select-text">
          <HqMarkdown :content="message.text" />
        </div>
      </div>
    </div>
  </div>
</template>
