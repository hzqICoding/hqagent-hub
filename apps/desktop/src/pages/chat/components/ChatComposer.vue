<script setup lang="ts">
import AttachmentDrafts from '@/shared/attachments/AttachmentDrafts.vue'
import { attachmentErrorText } from '@/shared/attachments/transport'
import { Paperclip } from 'lucide-vue-next'
import { closureText, nativeFailure, activityLabel } from '@/pages/native/native-utils'
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
  Check,
} from 'lucide-vue-next'

const chatStore = useChatStore()
const nativeConfirmed = ref(false)
const nativeError = ref<ReturnType<typeof nativeFailure> | null>(null)
watch([() => chatStore.activeConversationId, () => chatStore.activeConversation?.nativeSourceRevision], () => { nativeConfirmed.value = false; nativeError.value = null })
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
const attachmentDrafts = ref<InstanceType<typeof AttachmentDrafts> | null>(null)
const attachmentsBlocked = ref(false)
const textareaRef = ref<HTMLTextAreaElement | null>(null)

const canSend = computed(() => {
  if (chatStore.activeConversation?.conversationKind === 'native') {
    const act = chatStore.activeConversation.nativeActivity?.activity
    if (act === 'likely_active') return false
    if (act !== 'closed_confirmed' && (!nativeConfirmed.value || !chatStore.activeConversation.nativeSourceRevision)) {
      return false
    }
  }
  return (
    !chatStore.piGuardIssue &&
    !attachmentsBlocked.value &&
    !chatStore.isConversationBusy &&
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
  const newHeight = Math.min(Math.max(textareaRef.value.scrollHeight, 44), 132)
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
  const drafts = attachmentDrafts.value
  const attachmentIds = drafts?.ids() || []
  chatStore.setConversationDraft(conversationId, '')
  const clearedDraftRevision = chatStore.getConversationDraftRevision(conversationId)
  const revision = chatStore.activeConversation?.nativeSourceRevision
  const sendPromise = chatStore.sendMessage(text, undefined, nativeConfirmed.value && revision ? { terminalClosedConfirmed: true, sourceRevision: revision } : undefined, attachmentIds)
  await nextTick()
  if (chatStore.activeConversationId === conversationId) adjustHeight()

  try {
    await sendPromise
    drafts?.sent()
    nativeConfirmed.value = false
  } catch (err) {
    if (attachmentIds.length && (err as { code?: string })?.code !== 'SESSION_NOT_RESUMABLE' && chatStore.activeConversationId === conversationId) chatStore.sendError = attachmentErrorText(err)
    if (chatStore.activeConversation?.conversationKind === 'native') { nativeError.value = nativeFailure(err); nativeConfirmed.value = false }
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
  <div class="w-full shrink-0 px-2.5 sm:px-4 pb-[max(0.75rem,env(safe-area-inset-bottom,0px))] pt-1 select-none">
    <div class="max-w-3xl mx-auto w-full space-y-2">
      <div v-if="chatStore.activeConversation?.conversationKind === 'native'" class="text-xs px-3 py-2 rounded-xl bg-muted/20 text-text-muted space-y-1.5">
        <div class="flex items-center justify-between text-[11px]">
          <span class="font-medium text-text-muted/80">原生会话状态</span>
          <span
            class="text-[10px]"
            :class="chatStore.activeConversation.nativeActivity?.activity === 'closed_confirmed' ? 'text-success font-medium' : chatStore.activeConversation.nativeActivity?.activity === 'likely_active' ? 'text-warning font-medium' : 'text-text-muted/70'"
          >
            {{ chatStore.activeConversation.nativeActivity?.activity ? activityLabel(chatStore.activeConversation.nativeActivity.activity) : '未确认终端状态' }}
          </span>
        </div>
        <template v-if="chatStore.activeConversation.nativeActivity?.activity === 'likely_active'">
          <div class="text-[11px] text-warning flex items-center gap-1.5 py-0.5">
            <AlertCircle class="w-3.5 h-3.5 shrink-0" />
            <span>终端正在使用这个会话，请先在终端退出</span>
          </div>
        </template>
        <template v-else-if="chatStore.activeConversation.nativeActivity?.activity === 'closed_confirmed' && nativeError?.code !== 'NATIVE_SESSION_CHANGED'">
          <div class="text-[11px] text-success/90 py-0.5 flex items-center gap-1.5">
            <Check class="w-3.5 h-3.5 shrink-0" />
            <span>继续这个会话</span>
          </div>
        </template>
        <template v-else>
          <p class="text-[11px] leading-relaxed">{{ closureText }}</p>
          <label class="flex items-center gap-2 cursor-pointer pt-0.5 text-text">
            <input class="hq-form-choice" v-model="nativeConfirmed" type="checkbox" />
            <span>我已在终端退出该会话</span>
          </label>
        </template>
        <p v-if="nativeError" role="alert" class="text-danger text-[11px]">{{ nativeError.message }} <span class="select-text font-mono">{{ nativeError.requestId ? `requestId: ${nativeError.requestId}` : '' }}</span></p>
      </div>
      <p v-if="chatStore.piGuardIssue" role="alert" class="text-sm text-status-warning">{{ chatStore.piGuardIssue }}</p>
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
            class="min-w-[32px] min-h-[32px] p-1.5 rounded-full hover:bg-panel-hover text-text-muted hover:text-text shrink-0 transition-colors flex items-center justify-center cursor-pointer"
            title="移除该排队指令"
            aria-label="移除该排队指令"
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
            <p class="text-[11px] text-text-muted mt-0.5 break-words whitespace-pre-wrap">
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

      <!-- Busy Banner -->
      <div
        v-if="chatStore.isConversationBusy"
        class="p-2.5 rounded-xl bg-warning/10 border border-warning/25 text-xs text-warning flex items-center gap-2 shadow-xs"
      >
        <Clock class="w-4 h-4 text-warning shrink-0 animate-spin" />
        <span class="text-xs font-medium">对话正在进行，结束后再继续</span>
      </div>

      <div class="bg-panel border border-border/50 focus-within:border-primary/50 rounded-2xl overflow-hidden transition-colors shadow-xs">
        <AttachmentDrafts class="px-[12px]" v-if="chatStore.activeConversationId" :key="chatStore.activeConversationId" ref="attachmentDrafts" :conversation-id="chatStore.activeConversationId" :disabled="chatStore.isSending || chatStore.isActiveConversationArchived" @blocked="attachmentsBlocked = $event" />
        <div class="hq-composer-row px-[12px] py-3">
          <button type="button" aria-label="添加附件" class="hq-composer-icon text-content-muted" :disabled="chatStore.isSending || chatStore.isActiveConversationArchived || !chatStore.activeConversationId" @click="attachmentDrafts?.open()"><Paperclip class="w-5 h-5" /></button>
          <textarea ref="textareaRef" v-model="inputText" :maxlength="32000" rows="1" :disabled="chatStore.isConversationBusy || chatStore.isActiveConversationArchived"
            :placeholder="chatStore.isConversationBusy ? '对话正在进行，结束后再继续' : '输入任务目标或补充要求…'"
            class="hq-form-control hq-form-control--embedded hq-composer-text text-sm" @input="handleInput" @keydown="handleKeyDown" />
          <button v-if="chatStore.isCurrentRunActive && inputText.trim().length === 0" type="button" class="hq-composer-send bg-status-danger-soft text-status-danger" title="中止当前执行轮次" aria-label="中止当前执行轮次" @click="handleStopRun"><Square class="w-4 h-4 fill-current" /></button>
          <button v-else type="button" class="hq-composer-send" :class="canSend ? 'bg-action-primary text-action-primary-text hover:bg-action-primary-hover' : 'bg-muted text-content-disabled cursor-not-allowed'" :disabled="!canSend || chatStore.isSending" title="发送目标指令 (Enter)" aria-label="发送目标指令" @click="handleSend"><ArrowUp class="w-5 h-5" /></button>
        </div>

      </div>
    </div>
  </div>
</template>
