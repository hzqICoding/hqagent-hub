<script setup lang="ts">
import { ref, computed } from 'vue'
import { useChatStore } from '@/stores/chat.store'
import {
  HqButton,
  HqTooltip,
} from '@/shared/ui'
import {
  Send,
  AlertCircle,
  Clock,
  Info,
} from 'lucide-vue-next'

const chatStore = useChatStore()

const inputText = ref('')

const canSend = computed(() => {
  return inputText.value.trim().length > 0 && !chatStore.isSending
})

async function handleSend() {
  if (!canSend.value) return
  const text = inputText.value.trim()
  inputText.value = ''
  try {
    await chatStore.sendMessage(text)
  } catch {
    // If failed, restore input so user doesn't lose prompt
    inputText.value = text
  }
}

function handleKeyDown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

function switchMode(mode: 'new' | 'continue') {
  chatStore.sessionMode = mode
  chatStore.resumptionError = null
}
</script>

<template>
  <div class="p-3 bg-panel border-t border-border">
    <!-- Context mode selector & Queue status bar -->
    <div class="flex items-center justify-between gap-2 mb-2 text-xs">
      <div class="flex items-center gap-1.5">
        <span class="text-[11px] text-text-muted">会话上下文模式：</span>
        <div class="inline-flex p-0.5 rounded-[var(--radius-sm)] bg-bg-app border border-border">
          <button
            type="button"
            class="px-2 py-0.5 rounded text-[11px] transition-colors"
            :class="
              chatStore.sessionMode === 'new'
                ? 'bg-panel text-primary font-medium shadow-xs'
                : 'text-text-muted hover:text-text'
            "
            @click="switchMode('new')"
          >
            新一轮上下文 (New)
          </button>
          <button
            type="button"
            class="px-2 py-0.5 rounded text-[11px] transition-colors"
            :class="
              chatStore.sessionMode === 'continue'
                ? 'bg-panel text-primary font-medium shadow-xs'
                : 'text-text-muted hover:text-text'
            "
            @click="switchMode('continue')"
          >
            继续已有Agent会话 (Continue)
          </button>
        </div>

        <HqTooltip text="首条消息建议使用新一轮；多轮追问可选择继续。若底层 Agent 无法恢复上下文，将如实提示原因。">
          <Info class="w-3.5 h-3.5 text-text-muted/60 hover:text-text cursor-pointer" />
        </HqTooltip>
      </div>

      <!-- Active run queue badge -->
      <div v-if="chatStore.isCurrentRunActive" class="flex items-center gap-1 text-[11px] text-warning">
        <Clock class="w-3 h-3 animate-spin" />
        <span>当前轮次正在执行，新指令将自动排队</span>
      </div>
    </div>

    <!-- Resumption Error Alert -->
    <div
      v-if="chatStore.resumptionError"
      class="mb-2 p-2.5 rounded-[var(--radius-sm)] bg-danger/10 border border-danger/20 text-xs text-danger flex items-start justify-between gap-2"
    >
      <div class="flex items-start gap-2">
        <AlertCircle class="w-4 h-4 shrink-0 mt-0.5" />
        <div>
          <p class="font-medium">会话恢复失败</p>
          <p class="text-[11px] text-text-muted mt-0.5 leading-relaxed">
            {{ chatStore.resumptionError }}
          </p>
        </div>
      </div>
      <HqButton size="sm" variant="secondary" @click="switchMode('new')">
        切换为新一轮上下文
      </HqButton>
    </div>

    <!-- Generic Send Error Alert -->
    <div
      v-if="chatStore.sendError"
      class="mb-2 p-2.5 rounded-[var(--radius-sm)] bg-danger/10 border border-danger/20 text-xs text-danger flex items-center gap-2"
    >
      <AlertCircle class="w-4 h-4 shrink-0" />
      <span>{{ chatStore.sendError }}</span>
    </div>

    <!-- Textarea input & send button -->
    <div class="relative">
      <textarea
        v-model="inputText"
        :rows="3"
        placeholder="向角色团队输入任务目标或补充要求... (Enter 发送，Shift + Enter 换行)"
        class="w-full p-2.5 pr-20 text-xs bg-bg-app border border-border rounded-[var(--radius-md)] text-text placeholder-text-muted/60 focus:outline-none focus:border-primary resize-none transition-colors"
        @keydown="handleKeyDown"
      />

      <div class="absolute right-2 bottom-3 flex items-center gap-1.5">
        <HqButton
          size="sm"
          variant="primary"
          :disabled="!canSend"
          :loading="chatStore.isSending"
          @click="handleSend"
        >
          <Send class="w-3.5 h-3.5 mr-1" />
          发送
        </HqButton>
      </div>
    </div>

    <!-- Queued messages indicators -->
    <div v-if="chatStore.queuedMessages.length > 0" class="mt-2 space-y-1">
      <div
        v-for="(q, idx) in chatStore.queuedMessages"
        :key="q.id"
        class="p-2 rounded bg-bg-app border border-dashed border-border flex items-center justify-between text-xs text-text-muted"
      >
        <div class="flex items-center gap-1.5 truncate">
          <Clock class="w-3 h-3 text-warning shrink-0" />
          <span class="text-[11px] text-warning font-medium">排队中 #{{ idx + 1 }}</span>
          <span class="truncate">{{ q.text }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
