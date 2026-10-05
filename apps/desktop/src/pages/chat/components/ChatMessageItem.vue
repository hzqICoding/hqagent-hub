<script setup lang="ts">
import RuntimeIcon from '@/shared/runtime/RuntimeIcon.vue'
import { agentLabel } from '@/pages/native/native-utils'
import MessageAttachments from '@/shared/attachments/MessageAttachments.vue'
import { ref, computed } from 'vue'
import type { LocalMessageView } from '@hqagent/protocol'
import { HqMarkdown } from '@/shared/ui'
import { useChatStore } from '@/stores/chat.store'
import ProcessActivityGroup from './ProcessActivityGroup.vue'
import {
  Terminal,
  ChevronDown,
  Copy,
  Check,
} from 'lucide-vue-next'

interface Props {
  message: LocalMessageView
}

const props = defineProps<Props>()

const chatStore = useChatStore()
const isExpanded = ref(false)
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
  <div class="py-2.5 px-2 sm:px-4 transition-colors">
    <!-- User Message (Clean right-aligned bubble) -->
    <div v-if="message.role === 'user'" class="flex justify-end max-w-3xl mx-auto">
      <div class="min-w-0 max-w-[92%] sm:max-w-[85%] space-y-1 group">
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
          <MessageAttachments v-if="message.attachments?.length" :attachments="message.attachments" />
        </div>
      </div>
    </div>

    <!-- System / Role Process Step (Collapsible Accordion like PI-Desktop ActivityGroup) -->
    <div
      v-else-if="message.role === 'system'"
      class="max-w-3xl mx-auto my-1"
    >
      <div class="rounded-lg bg-panel/40 hover:bg-panel/70 transition-colors">
        <!-- Header (Clickable disclosure) -->
        <button
          type="button"
          class="w-full py-1.5 px-3 flex items-center justify-between text-xs hover:bg-panel transition-colors text-left gap-2 select-none cursor-pointer rounded-lg"
          @click="isExpanded = !isExpanded"
        >
          <div class="flex items-center gap-2 min-w-0">
            <div class="w-4 h-4 rounded bg-muted/60 text-text-muted flex items-center justify-center shrink-0">
              <Terminal class="w-2.5 h-2.5" />
            </div>
            <span class="text-[11px] font-medium text-text-muted shrink-0">执行记录</span>
            <span class="text-[10px] text-text-muted/60 font-mono shrink-0">#{{ message.sequence }}</span>

            <!-- Compact preview when collapsed -->
            <span v-if="!isExpanded" class="text-[11px] text-text-muted/70 truncate ml-1 font-mono">
              {{ message.text }}
            </span>
          </div>

          <div class="flex items-center gap-2 shrink-0">
            <span class="text-[10px] text-text-muted/60">{{ formatTime(message.createdAt) }}</span>
            <ChevronDown
              class="w-3.5 h-3.5 text-text-muted/60 transition-transform duration-200"
              :class="isExpanded ? 'rotate-180' : ''"
            />
          </div>
        </button>

        <!-- Expanded Terminal Body -->
        <div
          v-if="isExpanded"
          class="p-2.5 pt-0 font-mono text-[11px] text-text-muted select-text space-y-1.5 leading-relaxed break-words whitespace-pre-wrap"
        >
          <div class="p-2 rounded bg-bg-app/80 text-text leading-relaxed text-xs">
            {{ message.text }}
          </div>
        </div>
      </div>
    </div>

    <!-- Assistant Final Reply (Clean typography, bot avatar, markdown body, quick copy buttons) -->
    <div v-else class="max-w-3xl mx-auto flex items-start gap-2 sm:gap-3 group">
      <div class="w-7 h-7 rounded-full bg-success/15 text-success flex items-center justify-center shrink-0 mt-0.5 border border-success/30 shadow-xs">
        <RuntimeIcon :agent="chatStore.activeConversation?.agentType" class="w-4 h-4" />
      </div>

      <div class="flex-1 min-w-0 space-y-1.5">
        <div class="flex items-center justify-between text-[11px] text-text-muted select-none">
          <div class="flex items-center gap-2">
            <span class="font-semibold text-text text-xs">{{ chatStore.activeConversation?.agentType ? agentLabel(chatStore.activeConversation.agentType) : 'HQAgent 团队' }}</span>
            <span class="font-mono text-[10px]">#{{ message.sequence }}</span>
            <span>{{ formatTime(message.createdAt) }}</span>
          </div>

          <button
            type="button"
            class="min-h-[36px] sm:min-h-0 p-1 px-1.5 rounded hover:bg-panel-hover border border-transparent hover:border-border/60 text-text-muted hover:text-text transition-all flex items-center gap-1 text-[10px] cursor-pointer opacity-70 hover:opacity-100"
            title="复制回复内容"
            aria-label="复制回复内容"
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

        <div class="relative group/bubble bg-panel border border-border/80 p-3 sm:p-4 rounded-2xl rounded-tl-xs text-xs leading-relaxed shadow-sm break-words overflow-x-auto max-w-full select-text">
          <!-- Floating quick copy icon button at top-right corner of the bubble -->
          <button
            type="button"
            class="absolute top-2 right-2 sm:top-3 sm:right-3 min-w-[32px] min-h-[32px] p-1.5 px-2 rounded-lg bg-bg-app/90 hover:bg-panel-hover border border-border/70 text-text-muted hover:text-text transition-all flex items-center gap-1 text-[10px] shadow-xs cursor-pointer z-10 opacity-70 hover:opacity-100"
            :title="isCopied ? '已复制到剪贴板' : '一键复制整条消息'"
            aria-label="一键复制整条消息"
            @click.stop="copyText(message.text)"
          >
            <Check v-if="isCopied" class="w-3 h-3 text-success" />
            <Copy v-else class="w-3 h-3" />
            <span>{{ isCopied ? '已复制' : '复制' }}</span>
          </button>

          <HqMarkdown :content="message.text" />
        </div>

        <!-- Message footer action bar (at the bottom of response message) -->
        <div class="flex items-center justify-between pt-0.5 px-1 text-[11px] text-text-muted select-none">
          <button
            type="button"
            class="min-h-[36px] sm:min-h-0 p-1 px-2 rounded-md hover:bg-panel border border-border/40 text-text-muted hover:text-text transition-colors flex items-center gap-1.5 text-[10px] cursor-pointer"
            :title="isCopied ? '已复制到剪贴板' : '一键复制整条消息'"
            aria-label="复制全文"
            @click="copyText(message.text)"
          >
            <Check v-if="isCopied" class="w-3.5 h-3.5 text-success" />
            <Copy v-else class="w-3.5 h-3.5" />
            <span>{{ isCopied ? '已复制到剪贴板' : '复制全文' }}</span>
          </button>

          <span class="text-[10px] text-text-muted/60 font-mono">{{ formatTime(message.createdAt) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
