<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useRemoteChatStore } from '@/stores/remote-chat.store'
import { useRemoteAuthStore } from '@/stores/remote-auth.store'
import type { RemoteApprovalView, RemoteCommandView } from '@hqagent/protocol'
import {
  HqButton,
  HqBadge,
  HqDialog,
  HqEmptyState,
} from '@/shared/ui'
import {
  Menu,
  Plus,
  Send,
  Laptop,
  AlertTriangle,
  Pause,
  Play,
  XCircle,
  RotateCcw,
  Clock,
  ShieldAlert,
  LogOut,
  Undo2,
  MessageSquare,
} from 'lucide-vue-next'

const router = useRouter()
const chatStore = useRemoteChatStore()
const authStore = useRemoteAuthStore()

const isMobileSidebarOpen = ref(false)
const inputText = ref('')
const sessionMode = ref<'new' | 'continue'>('continue')
const messageContainerRef = ref<HTMLElement | null>(null)

// Dialog states
const isNewConversationDialogOpen = ref(false)
const newTitle = ref('')
const newSceneId = ref('analyze')
const isCreating = ref(false)

// Withdrawal dialog
const commandToWithdraw = ref<RemoteCommandView | null>(null)
const isWithdrawing = ref(false)
const withdrawReason = ref('')

onMounted(async () => {
  await chatStore.fetchDevices()
  await chatStore.fetchConversations()
  chatStore.startPolling(3000)
  scrollToBottom()
})

onUnmounted(() => {
  chatStore.stopPolling()
})

function scrollToBottom() {
  nextTick(() => {
    if (messageContainerRef.value) {
      messageContainerRef.value.scrollTop = messageContainerRef.value.scrollHeight
    }
  })
}

watch(
  () => chatStore.messages.length,
  () => {
    scrollToBottom()
  }
)

watch(
  [() => chatStore.activeRun?.runId, () => chatStore.activeRun?.status],
  ([_runId, status]) => {
    if (status === 'cancelled' || status === 'failed') {
      sessionMode.value = 'new'
    }
  },
  { immediate: true }
)

const pendingCommands = computed(() =>
  chatStore.commands.filter(
    (c) => c.status === 'queued' || c.status === 'accepted' || c.deliveryState === 'queued_offline'
  )
)

const latestControlCommand = computed(() => {
  for (let i = chatStore.commands.length - 1; i >= 0; i--) {
    if (chatStore.commands[i].controlResult) {
      return chatStore.commands[i]
    }
  }
  return null
})

async function handleSendMessage() {
  const text = inputText.value.trim()
  if (!text || chatStore.isSending) return

  inputText.value = ''
  await chatStore.sendMessage(text, sessionMode.value)
  scrollToBottom()
}

async function handleCreateConversation() {
  if (!newTitle.value.trim() || !chatStore.activeDevice) return
  isCreating.value = true
  try {
    const newConv = await chatStore.createConversation({
      targetWorkerId: chatStore.activeDevice.workerId,
      title: newTitle.value.trim(),
      workspaceId: chatStore.catalog?.workspaces[0]?.workspaceId || 'workspace_demo',
      sceneId: newSceneId.value,
      sceneVersion: 1,
      workerStoreId: chatStore.activeDevice.workerStoreId,
    })
    if (newConv) {
      isNewConversationDialogOpen.value = false
      newTitle.value = ''
      isMobileSidebarOpen.value = false
    }
  } finally {
    isCreating.value = false
  }
}

async function handleControl(action: 'pause' | 'resume' | 'cancel' | 'retry') {
  if (!chatStore.activeRun) return
  await chatStore.controlRun(chatStore.activeRun.runId, action)
}

function openWithdrawDialog(cmd: RemoteCommandView) {
  commandToWithdraw.value = cmd
  withdrawReason.value = ''
}

async function confirmWithdraw() {
  if (!commandToWithdraw.value) return
  isWithdrawing.value = true
  try {
    const success = await chatStore.withdrawCommand(
      commandToWithdraw.value.commandId,
      withdrawReason.value.trim() || undefined
    )
    if (success) {
      commandToWithdraw.value = null
    }
  } finally {
    isWithdrawing.value = false
  }
}

async function handleApproval(approval: RemoteApprovalView, decision: 'approve' | 'reject') {
  await chatStore.decideApproval(approval.approvalId, decision)
}

async function handleLogout() {
  await authStore.logout()
  chatStore.reset()
  router.replace('/remote/login')
}

function getExecutionStatusVariant(status?: string): 'neutral' | 'success' | 'warning' | 'danger' | 'info' {
  switch (status) {
    case 'running':
      return 'info'
    case 'succeeded':
      return 'success'
    case 'failed':
      return 'danger'
    case 'paused':
    case 'waiting_approval':
      return 'warning'
    default:
      return 'neutral'
  }
}

function getExecutionStatusLabel(status?: string): string {
  switch (status) {
    case 'running':
      return 'Worker 执行中'
    case 'succeeded':
      return 'Worker 执行成功'
    case 'failed':
      return 'Worker 执行失败'
    case 'paused':
      return 'Worker 已暂停'
    case 'waiting_approval':
      return 'Worker 等待审批'
    case 'queued':
      return 'Worker 排队中'
    case 'cancelled':
      return 'Worker 已取消'
    default:
      return status || '未知'
  }
}
</script>

<template>
  <div class="h-screen flex flex-col bg-bg-app select-none overflow-hidden">
    <!-- Top Bar -->
    <header class="h-14 bg-panel border-b border-border px-3 sm:px-4 flex items-center justify-between shrink-0 z-30">
      <div class="flex items-center gap-2 min-w-0">
        <!-- Drawer toggle button -->
        <button
          type="button"
          class="p-2 -ml-1 rounded-lg text-text-muted hover:text-text hover:bg-panel-hover cursor-pointer transition-colors"
          title="打开对话列表"
          aria-label="打开对话列表"
          @click="isMobileSidebarOpen = true"
        >
          <Menu class="w-5 h-5" />
        </button>

        <div class="min-w-0 flex items-center gap-2">
          <span class="font-bold text-sm text-text truncate max-w-[140px] sm:max-w-xs">
            {{ chatStore.activeConversation?.title || '远程控制台' }}
          </span>

          <!-- Layer 1: Transport Status (Worker Online/Offline badge) -->
          <HqBadge
            :variant="chatStore.isWorkerOnline ? 'success' : 'warning'"
            class="shrink-0 text-[10px]"
          >
            {{ chatStore.isWorkerOnline ? '电脑在线' : '电脑离线' }}
          </HqBadge>
        </div>
      </div>

      <div class="flex items-center gap-1.5 shrink-0">
        <HqButton
          variant="ghost"
          size="sm"
          class="text-xs p-1.5"
          title="管理设备"
          @click="router.push('/remote/devices')"
        >
          <Laptop class="w-4 h-4" />
        </HqButton>

        <button
          type="button"
          class="p-2 rounded-lg text-text-muted hover:text-danger hover:bg-panel-hover cursor-pointer transition-colors"
          title="退出登录"
          aria-label="退出登录"
          @click="handleLogout"
        >
          <LogOut class="w-4 h-4" />
        </button>
      </div>
    </header>

    <!-- Main Container with Mobile Drawer -->
    <div class="flex-1 flex overflow-hidden relative">
      <!-- Mobile Backdrop -->
      <div
        v-if="isMobileSidebarOpen"
        class="fixed inset-0 bg-black/50 backdrop-blur-xs z-40 transition-opacity"
        @click="isMobileSidebarOpen = false"
      />

      <!-- Left Sidebar Drawer -->
      <aside
        class="fixed inset-y-0 left-0 z-50 w-72 max-w-[80vw] bg-panel border-r border-border flex flex-col transition-transform duration-200 ease-in-out shadow-2xl"
        :class="[isMobileSidebarOpen ? 'translate-x-0' : '-translate-x-full']"
      >
        <div class="p-3 border-b border-border flex items-center justify-between shrink-0">
          <span class="font-bold text-xs text-text flex items-center gap-1.5">
            <MessageSquare class="w-4 h-4 text-primary" />
            远程对话列表
          </span>
          <HqButton
            variant="primary"
            size="sm"
            class="text-xs py-1 px-2"
            @click="isNewConversationDialogOpen = true"
          >
            <Plus class="w-3.5 h-3.5 mr-1" />
            新建
          </HqButton>
        </div>

        <!-- Conversation list -->
        <div class="flex-1 overflow-y-auto p-2 space-y-1">
          <div
            v-if="chatStore.conversations.length === 0"
            class="py-8 text-center text-xs text-text-muted"
          >
            暂无对话，点击上方新建
          </div>

          <button
            v-for="conv in chatStore.conversations"
            :key="conv.conversationId"
            type="button"
            class="w-full text-left p-2.5 rounded-lg text-xs transition-colors flex flex-col gap-1 cursor-pointer"
            :class="[
              conv.conversationId === chatStore.activeConversationId
                ? 'bg-primary/10 text-primary font-medium border border-primary/20'
                : 'text-text hover:bg-panel-hover border border-transparent',
            ]"
            @click="
              chatStore.selectConversation(conv.conversationId);
              isMobileSidebarOpen = false;
            "
          >
            <span class="truncate font-medium">{{ conv.title }}</span>
            <span class="text-[10px] text-text-muted truncate">
              场景: {{ conv.sceneId }}
            </span>
          </button>
        </div>

        <div class="p-3 border-t border-border flex items-center justify-between text-xs text-text-muted">
          <button
            type="button"
            class="hover:text-text cursor-pointer flex items-center gap-1"
            @click="router.push('/remote/devices')"
          >
            <Laptop class="w-3.5 h-3.5" />
            设备管理
          </button>
          <button
            type="button"
            class="hover:text-danger cursor-pointer flex items-center gap-1"
            @click="handleLogout"
          >
            <LogOut class="w-3.5 h-3.5" />
            退出登录
          </button>
        </div>
      </aside>

      <!-- Center Chat Column -->
      <main class="flex-1 flex flex-col h-full min-w-0 bg-bg-app overflow-hidden">
        <!-- Global Error Bar if any -->
        <div
          v-if="chatStore.actionError || chatStore.sendError"
          class="p-2 px-3 text-xs bg-danger/10 border-b border-danger/20 text-danger flex items-center justify-between shrink-0"
        >
          <span class="truncate">{{ chatStore.actionError || chatStore.sendError }}</span>
          <button
            type="button"
            class="text-[11px] underline ml-2 cursor-pointer shrink-0"
            @click="chatStore.actionError = null; chatStore.sendError = null"
          >
            关闭
          </button>
        </div>

        <!-- 3-LAYER STATUS DASHBOARD BANNER -->
        <section
          v-if="chatStore.activeRun || !chatStore.isWorkerOnline"
          class="p-2.5 bg-panel border-b border-border shrink-0 space-y-2 text-xs"
        >
          <!-- Three Layers Display -->
          <div class="grid grid-cols-1 gap-1.5 sm:grid-cols-3 bg-bg-app/70 p-2 rounded-lg border border-border/60">
            <!-- Layer 1: Transport State -->
            <div class="space-y-0.5">
              <span class="text-[10px] text-text-muted font-medium">1. 传输状态</span>
              <div class="flex items-center gap-1.5">
                <span
                  class="w-2 h-2 rounded-full shrink-0"
                  :class="chatStore.isWorkerOnline ? 'bg-success' : 'bg-warning animate-pulse'"
                />
                <span
                  class="font-semibold"
                  :class="chatStore.isWorkerOnline ? 'text-text' : 'text-warning'"
                >
                  {{ chatStore.isWorkerOnline ? '电脑在线' : '电脑离线，指令已排队' }}
                </span>
              </div>
            </div>

            <!-- Layer 2: Control Result -->
            <div class="space-y-0.5">
              <span class="text-[10px] text-text-muted font-medium">2. 控制结果</span>
              <div>
                <template v-if="latestControlCommand && latestControlCommand.controlResult">
                  <span
                    v-if="latestControlCommand.controlResult?.outcome === 'confirmed'"
                    class="text-success font-medium"
                  >
                    已确认生效
                  </span>
                  <span
                    v-else-if="latestControlCommand.controlResult?.outcome === 'rejected'"
                    class="text-danger font-medium"
                  >
                    已被拒绝 (执行可能仍在进行)
                  </span>
                  <span
                    v-else
                    class="text-warning font-medium"
                  >
                    未能确认 (需回电脑核对)
                  </span>
                </template>
                <span v-else class="text-text-muted">无未决控制</span>
              </div>
            </div>

            <!-- Layer 3: Execution State -->
            <div class="space-y-0.5">
              <span class="text-[10px] text-text-muted font-medium">3. 执行状态 (Worker)</span>
              <div>
                <HqBadge
                  v-if="chatStore.activeRun"
                  :variant="getExecutionStatusVariant(chatStore.activeRun.status)"
                  class="text-[10px]"
                >
                  {{ getExecutionStatusLabel(chatStore.activeRun.status) }}
                </HqBadge>
                <span v-else class="text-text-muted">就绪</span>
              </div>
            </div>
          </div>

          <!-- Run Actions Bar -->
          <div v-if="chatStore.activeRun" class="flex items-center justify-between pt-0.5">
            <span class="text-[11px] text-text-muted truncate">
              Run: {{ chatStore.activeRun.runId }}
            </span>

            <div class="flex items-center gap-1.5 shrink-0">
              <HqButton
                v-if="chatStore.activeRun.status === 'running'"
                variant="secondary"
                size="sm"
                class="text-[11px] py-1 px-2"
                :loading="chatStore.isActionLoading"
                @click="handleControl('pause')"
              >
                <Pause class="w-3 h-3 mr-1" />
                暂停
              </HqButton>

              <HqButton
                v-if="chatStore.activeRun.status === 'paused'"
                variant="secondary"
                size="sm"
                class="text-[11px] py-1 px-2"
                :loading="chatStore.isActionLoading"
                @click="handleControl('resume')"
              >
                <Play class="w-3 h-3 mr-1" />
                恢复
              </HqButton>

              <HqButton
                v-if="['running', 'paused', 'queued', 'waiting_approval'].includes(chatStore.activeRun.status)"
                variant="danger"
                size="sm"
                class="text-[11px] py-1 px-2"
                :loading="chatStore.isActionLoading"
                @click="handleControl('cancel')"
              >
                <XCircle class="w-3 h-3 mr-1" />
                取消
              </HqButton>

              <HqButton
                v-if="['failed', 'cancelled'].includes(chatStore.activeRun.status)"
                variant="secondary"
                size="sm"
                class="text-[11px] py-1 px-2"
                :loading="chatStore.isActionLoading"
                @click="handleControl('retry')"
              >
                <RotateCcw class="w-3 h-3 mr-1" />
                重试
              </HqButton>
            </div>
          </div>
        </section>

        <!-- PENDING APPROVALS BAR -->
        <section
          v-if="chatStore.activeApprovals.length > 0"
          class="p-3 bg-warning/10 border-b border-warning/30 shrink-0 space-y-2 text-xs text-text"
        >
          <div
            v-for="approval in chatStore.activeApprovals"
            :key="approval.approvalId"
            class="space-y-2 p-2.5 rounded-lg bg-panel border border-warning/40 shadow-xs"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="space-y-0.5">
                <div class="flex items-center gap-1.5 font-bold text-text">
                  <ShieldAlert class="w-4 h-4 text-warning shrink-0" />
                  <span>安全审批请求：{{ approval.action }}</span>
                </div>
                <p class="text-[11px] text-text-muted">
                  {{ approval.targetSummary }}
                </p>
              </div>

              <HqBadge :variant="approval.riskLevel === 'high' ? 'danger' : 'warning'">
                {{ approval.riskLevel === 'high' ? '高风险' : '普通风险' }}
              </HqBadge>
            </div>

            <!-- High Risk Warning and Button Restrictions -->
            <div
              v-if="chatStore.isHighRiskApproval(approval)"
              class="p-2 rounded bg-warning/15 border border-warning/30 text-[11px] text-warning flex items-center gap-1.5"
            >
              <AlertTriangle class="w-3.5 h-3.5 shrink-0" />
              <span>高风险操作，请回到电脑上处理</span>
            </div>

            <div class="flex items-center justify-end gap-2 pt-1 border-t border-border/40">
              <HqButton
                variant="danger"
                size="sm"
                class="text-xs"
                :loading="chatStore.isActionLoading"
                @click="handleApproval(approval, 'reject')"
              >
                拒绝拦截
              </HqButton>

              <!-- Approve button is HIDDEN for high risk actions! -->
              <HqButton
                v-if="!chatStore.isHighRiskApproval(approval)"
                variant="primary"
                size="sm"
                class="text-xs"
                :loading="chatStore.isActionLoading"
                @click="handleApproval(approval, 'approve')"
              >
                批准执行
              </HqButton>
            </div>
          </div>
        </section>

        <!-- Messages Stream -->
        <div
          ref="messageContainerRef"
          class="flex-1 overflow-y-auto p-3 sm:p-4 space-y-3"
        >
          <div
            v-if="chatStore.messages.length === 0"
            class="h-full flex items-center justify-center"
          >
            <HqEmptyState
              title="暂无消息"
              description="在下方输入框发送指令，与电脑上的 Agent 开启对话"
            />
          </div>

          <!-- Message Bubbles -->
          <div
            v-for="msg in chatStore.messages"
            :key="msg.messageId"
            class="flex flex-col space-y-1"
            :class="msg.role === 'user' ? 'items-end' : 'items-start'"
          >
            <div
              class="max-w-[85%] sm:max-w-md p-3 rounded-2xl text-xs sm:text-sm leading-relaxed"
              :class="[
                msg.role === 'user'
                  ? 'bg-primary text-white rounded-tr-xs'
                  : 'bg-panel border border-border text-text rounded-tl-xs shadow-xs',
              ]"
            >
              <p class="whitespace-pre-wrap break-words">{{ msg.text }}</p>
            </div>

            <span class="text-[10px] text-text-muted px-1">
              {{ msg.role === 'user' ? '你' : 'Agent' }} • {{ new Date(msg.createdAt).toLocaleTimeString() }}
            </span>
          </div>

          <!-- Pending / Queued Commands Bubble -->
          <div
            v-for="cmd in pendingCommands"
            :key="cmd.commandId"
            class="p-2.5 rounded-xl bg-panel border border-border space-y-1.5 text-xs"
          >
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-1.5">
                <Clock class="w-3.5 h-3.5 text-warning shrink-0" />
                <span class="font-medium text-text">{{ cmd.status === 'accepted' ? '指令处理中' : '指令排队中' }}</span>
              </div>

              <!-- Mandatory: display '电脑离线，指令已排队' when offline, never running -->
              <HqBadge
                :variant="cmd.deliveryState === 'queued_offline' || !chatStore.isWorkerOnline ? 'warning' : cmd.status === 'accepted' ? 'success' : 'info'"
                class="text-[10px]"
              >
                {{
                  cmd.deliveryState === 'queued_offline' || !chatStore.isWorkerOnline
                    ? '电脑离线，指令已排队'
                    : cmd.status === 'accepted'
                      ? '已接单'
                      : '已投递到云端'
                }}
              </HqBadge>
            </div>

            <div class="flex items-center justify-between text-[11px] text-text-muted pt-1 border-t border-border/40">
              <span class="truncate">ID: {{ cmd.commandId.slice(0, 10) }}...</span>

              <!-- Withdraw Button -->
              <button
                type="button"
                class="text-danger hover:underline font-medium cursor-pointer flex items-center gap-1"
                @click="openWithdrawDialog(cmd)"
              >
                <Undo2 class="w-3 h-3" />
                撤回指令
              </button>
            </div>
          </div>
        </div>

        <!-- Composer -->
        <footer class="p-2.5 sm:p-3 bg-panel border-t border-border shrink-0 space-y-2">
          <!-- Interrupted previous run alert -->
          <div
            v-if="chatStore.activeRun && (chatStore.activeRun.status === 'cancelled' || chatStore.activeRun.status === 'failed')"
            class="p-1.5 px-2 rounded bg-warning/15 border border-warning/30 text-[11px] text-warning flex items-center gap-1.5"
          >
            <AlertTriangle class="w-3.5 h-3.5 shrink-0" />
            <span>上一轮已中断，继续上下文可能失败</span>
          </div>

          <!-- SessionMode switch -->
          <div class="flex items-center justify-between text-xs text-text-muted px-1">
            <div class="flex items-center gap-3">
              <label class="flex items-center gap-1 cursor-pointer">
                <input
                  v-model="sessionMode"
                  type="radio"
                  value="continue"
                  class="accent-primary"
                />
                <span>继续上下文</span>
              </label>

              <label class="flex items-center gap-1 cursor-pointer">
                <input
                  v-model="sessionMode"
                  type="radio"
                  value="new"
                  class="accent-primary"
                />
                <span>新话题</span>
              </label>
            </div>

            <span class="text-[10px]">
              {{ chatStore.isWorkerOnline ? '电脑在线就绪' : '电脑离线 (排队投递)' }}
            </span>
          </div>

          <!-- Input + Send Button -->
          <div class="flex items-center gap-2">
            <textarea
              v-model="inputText"
              rows="1"
              placeholder="输入给电脑上 Agent 的指令..."
              class="flex-1 py-2 px-3 text-xs sm:text-sm bg-bg-app border border-border rounded-xl text-text placeholder:text-text-muted focus:outline-hidden focus:border-primary transition-colors resize-none max-h-24"
              :disabled="chatStore.isSending"
              @keydown.enter.exact.prevent="handleSendMessage"
            />

            <HqButton
              variant="primary"
              class="h-9 px-3.5 rounded-xl shrink-0"
              :loading="chatStore.isSending"
              :disabled="!inputText.trim() || chatStore.isSending"
              @click="handleSendMessage"
            >
              <Send class="w-4 h-4" />
            </HqButton>
          </div>
        </footer>
      </main>
    </div>

    <!-- Create Conversation Dialog -->
    <HqDialog
      :open="isNewConversationDialogOpen"
      title="新建远程对话"
      @close="isNewConversationDialogOpen = false"
    >
      <div class="space-y-4 text-xs text-text">
        <div class="space-y-1.5">
          <label for="new-conv-title" class="block font-medium text-text-secondary">对话标题</label>
          <input
            id="new-conv-title"
            v-model="newTitle"
            type="text"
            placeholder="例如：重构远程网关并测试"
            class="w-full py-2 px-3 bg-bg-app border border-border rounded-lg text-text focus:outline-hidden focus:border-primary"
          />
        </div>

        <div class="space-y-1.5">
          <label for="new-conv-scene" class="block font-medium text-text-secondary">工作场景</label>
          <select
            id="new-conv-scene"
            v-model="newSceneId"
            class="w-full py-2 px-3 bg-bg-app border border-border rounded-lg text-text focus:outline-hidden focus:border-primary"
          >
            <option value="analyze">代码分析</option>
            <option value="plan">需求规划</option>
            <option value="develop">代码开发</option>
          </select>
        </div>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-2">
          <HqButton
            variant="ghost"
            size="sm"
            :disabled="isCreating"
            @click="isNewConversationDialogOpen = false"
          >
            取消
          </HqButton>
          <HqButton
            variant="primary"
            size="sm"
            :loading="isCreating"
            :disabled="!newTitle.trim() || isCreating"
            @click="handleCreateConversation"
          >
            创建
          </HqButton>
        </div>
      </template>
    </HqDialog>

    <!-- Withdraw Confirmation Dialog -->
    <HqDialog
      :open="Boolean(commandToWithdraw)"
      title="确认撤回排队指令？"
      @close="commandToWithdraw = null"
    >
      <div class="space-y-3 text-xs text-text">
        <p>
          撤回将向服务端下发取消请求。注意：仅能撤回尚未投递到电脑的排队指令。
        </p>
        <div class="space-y-1.5">
          <label for="withdraw-reason" class="block font-medium text-text-secondary">撤回原因 (选填)</label>
          <input
            id="withdraw-reason"
            v-model="withdrawReason"
            type="text"
            placeholder="例如：指令输入错误"
            class="w-full py-2 px-3 bg-bg-app border border-border rounded-lg text-text focus:outline-hidden focus:border-primary"
          />
        </div>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-2">
          <HqButton
            variant="ghost"
            size="sm"
            :disabled="isWithdrawing"
            @click="commandToWithdraw = null"
          >
            取消
          </HqButton>
          <HqButton
            variant="danger"
            size="sm"
            :loading="isWithdrawing"
            @click="confirmWithdraw"
          >
            确认撤回
          </HqButton>
        </div>
      </template>
    </HqDialog>
  </div>
</template>
