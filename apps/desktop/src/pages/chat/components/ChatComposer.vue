<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { useChatStore } from '@/stores/chat.store'
import {
  HqButton,
} from '@/shared/ui'
import {
  ArrowUp,
  AlertCircle,
  Clock,
  X,
  Square,
  RotateCcw,
  Smartphone,
} from 'lucide-vue-next'

const chatStore = useChatStore()
const emit = defineEmits<{ (e: 'request-context-reset'): void }>()

const inputText = computed({
  get: () => chatStore.activeConversationId
    ? chatStore.getConversationDraft(chatStore.activeConversationId)
    : '',
  set: (value: string) => {
    if (chatStore.activeConversationId) {
      chatStore.setConversationDraft(chatStore.activeConversationId, value)
    }
  },
})
const textareaRef = ref<HTMLTextAreaElement | null>(null)

const canSend = computed(() => {
  return (
    !chatStore.isRemoteConversation &&
    inputText.value.trim().length > 0 &&
    !chatStore.isActiveConversationArchived &&
    !chatStore.isSending &&
    !chatStore.isLoadingMessages &&
    !chatStore.isLoadingRun
  )
})
const canRequestContextReset = computed(() => chatStore.canResetContext)

function adjustHeight() {
  if (!textareaRef.value) return
  textareaRef.value.style.height = 'auto'
  const newHeight = Math.min(Math.max(textareaRef.value.scrollHeight, 44), 180)
  textareaRef.value.style.height = `${newHeight}px`
}

function handleInput() {
  adjustHeight()
}

async function handleSend() {
  if (!canSend.value) return
  const conversationId = chatStore.activeConversationId
  if (!conversationId) return
  const text = inputText.value.trim()
  chatStore.setConversationDraft(conversationId, '')
  const clearedDraftRevision = chatStore.getConversationDraftRevision(conversationId)
  const sendPromise = chatStore.sendMessage(text)
  await nextTick()
  if (chatStore.activeConversationId === conversationId) adjustHeight()

  try {
    await sendPromise
  } catch {
    // Restore only the original conversation's still-empty draft. A newer draft wins.
    if (chatStore.getConversationDraftRevision(conversationId) === clearedDraftRevision) {
      chatStore.setConversationDraft(conversationId, text)
    }
    await nextTick()
    if (chatStore.activeConversationId === conversationId) adjustHeight()
  }
}

watch(
  () => chatStore.activeConversationId,
  async () => {
    await nextTick()
    adjustHeight()
  }
)

function handleKeyDown(e: KeyboardEvent) {
  if (e.isComposing) return
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

function removeQueuedMessage(messageId: string) {
  chatStore.removeQueuedMessage(messageId)
}

function handleStopRun() {
  if (chatStore.activeRun) {
    chatStore.controlRun(chatStore.activeRun.id, 'cancel', '用户从输入栏停止任务')
  }
}
</script>

<template>
  <div class="w-full shrink-0 px-4 pb-4 pt-1 select-none">
    <div class="max-w-3xl mx-auto w-full space-y-2">
      <!-- 1. Floating Queued Messages Deck -->
      <div v-if="chatStore.queuedMessages.length > 0" class="space-y-1.5">
        <div
          v-for="(q, idx) in chatStore.queuedMessages"
          :key="q.id"
          class="p-2 px-3 rounded-xl bg-panel/95 backdrop-blur border border-border/80 shadow-xs flex items-center justify-between text-xs text-text-muted gap-2"
        >
          <div class="flex items-center gap-2 min-w-0">
            <Clock class="w-3.5 h-3.5 text-warning shrink-0 animate-pulse" />
            <span class="text-[11px] font-medium text-warning bg-warning/15 px-1.5 py-0.5 rounded-full shrink-0">
              排队中 #{{ idx + 1 }}
            </span>
            <span class="truncate text-text text-xs">{{ q.text }}</span>
          </div>

          <button
            type="button"
            class="p-1 rounded-full hover:bg-panel-hover text-text-muted hover:text-text shrink-0 transition-colors"
            title="移除该排队指令"
            @click="removeQueuedMessage(q.id)"
          >
            <X class="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <!-- 2. One-shot explicit context reset -->
      <div
        v-if="chatStore.pendingContextReset"
        class="p-2.5 rounded-xl bg-primary/10 border border-primary/25 text-xs text-text flex items-center justify-between gap-3 shadow-xs"
      >
        <div class="flex items-center gap-2 min-w-0">
          <RotateCcw class="w-4 h-4 text-primary shrink-0" />
          <span class="text-[11px]">下一条消息将使用新的 Agent 会话，不自动携带全部历史。</span>
        </div>
        <HqButton size="sm" variant="ghost" class="shrink-0" @click="chatStore.cancelContextReset()">
          撤销重置
        </HqButton>
      </div>

      <!-- 3. Resumption Error Alert -->
      <div
        v-if="chatStore.resumptionError"
        class="p-3 rounded-xl bg-danger/10 border border-danger/25 text-xs text-danger flex items-center justify-between gap-3 shadow-xs"
      >
        <div class="flex items-center gap-2.5 min-w-0">
          <AlertCircle class="w-4 h-4 shrink-0" />
          <div class="min-w-0">
            <p class="font-medium text-xs">会话恢复失败</p>
            <p class="text-[11px] text-text-muted mt-0.5 truncate">
              {{ chatStore.resumptionError }}
            </p>
          </div>
        </div>
        <HqButton
          size="sm"
          variant="secondary"
          class="shrink-0"
          :disabled="!canRequestContextReset"
          @click="emit('request-context-reset')"
        >
          重置 Agent 上下文
        </HqButton>
      </div>

      <!-- 4. Generic Send Error Alert -->
      <div
        v-if="chatStore.sendError"
        class="p-2.5 rounded-xl bg-danger/10 border border-danger/25 text-xs text-danger flex items-center justify-between gap-2 shadow-xs"
      >
        <div class="flex items-center gap-2 min-w-0">
          <AlertCircle class="w-4 h-4 shrink-0" />
          <span class="truncate text-xs">{{ chatStore.sendError }}</span>
        </div>
        <button
          type="button"
          class="p-1 rounded text-danger/80 hover:text-danger"
          @click="chatStore.clearSendError()"
        >
          <X class="w-3.5 h-3.5" />
        </button>
      </div>

      <!-- Remote Conversation Read-only Alert -->
      <div
        v-if="chatStore.isRemoteConversation"
        class="p-2.5 rounded-xl bg-primary/10 border border-primary/25 text-xs text-text flex items-center gap-2 shadow-xs"
      >
        <Smartphone class="w-4 h-4 text-primary shrink-0" />
        <span class="text-xs font-medium">这是手机远程对话，电脑端仅供只读查看，请在手机上继续操作。</span>
      </div>

      <!-- 5. Floating Modern Composer Card (PI-Desktop / Codex style) -->
      <div
        class="bg-panel border border-border/80 focus-within:border-primary/60 rounded-2xl shadow-sm focus-within:shadow-md transition-all duration-200 overflow-hidden"
      >
        <!-- Textarea input -->
        <div class="px-3.5 pt-3 pb-1">
          <textarea
            ref="textareaRef"
            v-model="inputText"
            :maxlength="32000"
            rows="1"
            :disabled="chatStore.isRemoteConversation || chatStore.isActiveConversationArchived"
            :placeholder="chatStore.isRemoteConversation ? '这是手机远程对话，请在手机上继续' : '向角色团队输入任务目标或补充要求... (Enter 发送，Shift + Enter 换行)'"
            class="w-full bg-transparent text-xs text-text placeholder-text-muted/50 resize-none outline-none focus:ring-0 leading-relaxed max-h-44 min-h-[44px] disabled:opacity-60 disabled:cursor-not-allowed"
            @input="handleInput"
            @keydown="handleKeyDown"
          />
        </div>

        <!-- Integrated Action Toolbar -->
        <div class="px-3 pb-2.5 pt-1.5 flex items-center justify-between gap-2 border-t border-border/30 select-none flex-wrap">
          <!-- Left: continuous task context hint -->
          <div class="flex items-center gap-2 min-w-0 flex-wrap">
            <span class="text-[11px] text-text-muted">当前任务连续对话</span>
          </div>

          <!-- Right: Running indicator & Action Button -->
          <div class="flex items-center gap-2 shrink-0 ml-auto">
            <!-- Active run status badge -->
            <div
              v-if="chatStore.isCurrentRunActive"
              class="hidden sm:flex items-center gap-1.5 text-[11px] text-warning bg-warning/10 px-2.5 py-0.5 rounded-full border border-warning/20 shrink-0"
            >
              <Clock class="w-3 h-3 animate-spin text-warning" />
              <span>执行中 · 新指令自动排队</span>
            </div>

            <!-- Stop Button if running and input is empty -->
            <button
              v-if="chatStore.isCurrentRunActive && inputText.trim().length === 0 && !chatStore.isRemoteConversation"
              type="button"
              class="w-7 h-7 rounded-full flex items-center justify-center transition-all bg-danger/15 text-danger hover:bg-danger/25 active:scale-95 cursor-pointer shadow-xs"
              title="中止当前执行轮次"
              @click="handleStopRun"
            >
              <Square class="w-3.5 h-3.5 fill-current" />
            </button>

            <!-- Send button (Circle button) -->
            <button
              v-else
              type="button"
              class="w-7 h-7 rounded-full flex items-center justify-center transition-all shadow-xs"
              :class="
                canSend
                  ? 'bg-primary text-white hover:bg-primary-hover active:scale-95 cursor-pointer'
                  : 'bg-muted text-text-muted/40 cursor-not-allowed'
              "
              :disabled="!canSend || chatStore.isSending"
              title="发送目标指令 (Enter)"
              @click="handleSend"
            >
              <ArrowUp class="w-4 h-4 stroke-[2.5]" />
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
