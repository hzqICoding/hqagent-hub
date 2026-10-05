<script setup lang="ts">
import { piRemoteCandidates, PI_WIRE_PENDING } from '@/shared/runtime/pi'
import RuntimeIcon from '@/shared/runtime/RuntimeIcon.vue'
import { getRemoteErrorMessage } from '@/shared/i18n/remote-errors'
import AttachmentDrafts from '@/shared/attachments/AttachmentDrafts.vue'
import MessageAttachments from '@/shared/attachments/MessageAttachments.vue'
import { Paperclip } from 'lucide-vue-next'
import NativeSessionsPanel from '@/pages/native/NativeSessionsPanel.vue'
import RemoteWorkspaceDialog from '@/pages/native/RemoteWorkspaceDialog.vue'
import { agentLabel, closureText } from '@/pages/native/native-utils'
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import RemoteRequestNotice from './RemoteRequestNotice.vue'
import { useRemoteChatStore } from '@/stores/remote-chat.store'
import { useRemoteAuthStore } from '@/stores/remote-auth.store'
import type { RemoteApprovalView, RemoteCommandView, RemoteConversationView } from '@hqagent/protocol'
import {
  HqButton,
  HqBadge,
  HqDialog,
  HqEmptyState,
  HqSelect,
  useConfirm,
} from '@/shared/ui'
import {
  Menu,
  Plus,
  Send,
  Laptop,
  AlertTriangle,
  AlertCircle,
  Pause,
  Play,
  XCircle,
  X,
  RotateCcw,
  Clock,
  ShieldAlert,
  LogOut,
  Undo2,
  MessageSquare,
  MoreHorizontal,
} from 'lucide-vue-next'

const router = useRouter()
const confirm = useConfirm()
const chatStore = useRemoteChatStore()
const authStore = useRemoteAuthStore()
const piScenario = computed(() => chatStore.activeConversation && !chatStore.activeConversation.agentType && piRemoteCandidates(chatStore.activeConversation, chatStore.catalog).isPi)

const isMobileSidebarOpen = ref(false)
const attachmentDrafts = ref<InstanceType<typeof AttachmentDrafts> | null>(null)
const attachmentsBlocked = ref(false)
const inputText = ref('')
const nextMessageNew = ref(false)
const messageContainerRef = ref<HTMLElement | null>(null)

// Dialog states
const isNewConversationDialogOpen = ref(false)
const addingWorkspace = ref(false)
const nativeConfirmed = ref(false)
const nativeCanSend = computed(() => chatStore.activeConversation?.conversationKind !== 'native' || chatStore.activeConversation.nativeActivity?.activity === 'closed_confirmed' || (nativeConfirmed.value && Boolean(chatStore.activeConversation.nativeSourceRevision)))
watch(() => chatStore.activeConversation?.nativeSourceRevision, () => { nativeConfirmed.value = false })
const newTitle = ref('')
const newSceneId = ref('')
const newWorkspaceId = ref('')
const composerRef = ref<HTMLTextAreaElement | null>(null)
const isCreating = ref(false)

const selectedScene = computed(() => chatStore.catalog?.scenes.find((scene) => scene.sceneId === newSceneId.value))
const canCreate = computed(() => !chatStore.isRemoteSuspended && !isCreating.value && !chatStore.isLoadingCatalog && !chatStore.catalogError &&
  chatStore.catalog?.workerId === chatStore.selectedDevice?.workerId &&
  chatStore.catalog?.workspaces.some((ws) => ws.workspaceId === newWorkspaceId.value) && Boolean(selectedScene.value))
const catalogHint = computed(() => chatStore.catalogError || (chatStore.isLoadingCatalog || !chatStore.catalog
  ? '正在读取电脑的项目列表…' : '电脑尚未提供可用的项目或场景'))

function setCatalogDefaults(workspaceId?: string) {
  const catalog = chatStore.catalog
  newWorkspaceId.value = catalog
    ? catalog.workspaces.find((ws) => ws.workspaceId === workspaceId)?.workspaceId || catalog.workspaces[0]?.workspaceId || ''
    : workspaceId || ''
  newSceneId.value = catalog?.scenes[0]?.sceneId || ''
}

async function openCreateDialog(workspaceId?: string) {
  if (chatStore.isRemoteSuspended) return
  newTitle.value = ''
  isNewConversationDialogOpen.value = true
  if (!chatStore.catalog && !chatStore.isLoadingCatalog) await chatStore.fetchCatalog()
  setCatalogDefaults(workspaceId)
}

async function retryCatalog() {
  const workspaceId = newWorkspaceId.value
  await chatStore.fetchCatalog()
  setCatalogDefaults(workspaceId)
}

watch(() => chatStore.catalog, () => {
  if (isNewConversationDialogOpen.value) setCatalogDefaults(newWorkspaceId.value)
})

watch(() => chatStore.deviceRemovalNotice, (notice) => {
  if (notice && !chatStore.selectedWorkerId) void router?.replace('/remote/devices')
})

watch(() => chatStore.lastRevocationInfo, (info) => {
  if (info && !chatStore.selectedWorkerId) void router?.replace('/remote/devices')
})

watch([() => chatStore.createdConversationToFocus, isNewConversationDialogOpen], async ([id, dialogOpen]) => {
  if (!id || dialogOpen) return
  isMobileSidebarOpen.value = false
  await nextTick()
  composerRef.value?.focus()
  chatStore.createdConversationToFocus = null
})

// Conversation Settings State
const isConvSettingsOpen = ref(false)
const isPcOnlyConfirmOpen = ref(false)
const settingsTarget = ref<RemoteConversationView | null>(null)
const settingsTitle = ref('')
const settingsArchived = ref(false)
const settingsVisibility = ref<'both' | 'pc_only' | 'mobile_only'>('both')
const isSavingSettings = ref(false)

function openConversationSettings(conv: RemoteConversationView) {
  settingsTarget.value = conv
  settingsTitle.value = conv.title
  settingsArchived.value = conv.archived ?? false
  settingsVisibility.value = conv.visibility || 'both'
  isConvSettingsOpen.value = true
}

async function handleSaveSettings() {
  if (!settingsTarget.value) return
  if (settingsVisibility.value === 'pc_only' && settingsTarget.value.visibility !== 'pc_only') {
    isPcOnlyConfirmOpen.value = true
    return
  }
  await executeSaveSettings()
}

async function executeSaveSettings() {
  if (!settingsTarget.value) return
  isSavingSettings.value = true
  try {
    await chatStore.updateConversationSettings(settingsTarget.value.conversationId, {
      title: settingsTitle.value.trim(),
      archived: settingsArchived.value,
      visibility: settingsVisibility.value,
    })
    isConvSettingsOpen.value = false
    isPcOnlyConfirmOpen.value = false
  } catch {
    // Error captured in chatStore.actionError
  } finally {
    isSavingSettings.value = false
  }
}

// Withdrawal dialog
const commandToWithdraw = ref<RemoteCommandView | null>(null)
const isWithdrawing = ref(false)
const withdrawReason = ref('')

function handleVisibilityChange() {
  if (typeof document === 'undefined') return
  if (document.visibilityState === 'visible') {
    chatStore.refreshActiveDevice()
    chatStore.startDevicePolling(15000)
  } else {
    chatStore.stopDevicePolling()
  }
}

async function loadMoreMessages() {
  if (!messageContainerRef.value || chatStore.isLoadingEarlierMessages || !chatStore.hasMoreMessages) return
  const container = messageContainerRef.value
  const previousScrollHeight = container.scrollHeight
  const previousScrollTop = container.scrollTop

  await chatStore.loadEarlierMessages()
  await nextTick()

  const heightDiff = container.scrollHeight - previousScrollHeight
  container.scrollTop = previousScrollTop + heightDiff
}

function handleScroll() {
  if (!messageContainerRef.value) return
  if (messageContainerRef.value.scrollTop <= 40 && chatStore.hasMoreMessages && !chatStore.isLoadingEarlierMessages) {
    void loadMoreMessages()
  }
}

onMounted(async () => {
  await chatStore.fetchDevices()
  const workerIdQuery = (router?.currentRoute?.value?.query?.workerId as string | undefined) || chatStore.selectedDevice?.workerId
  if (workerIdQuery) {
    await chatStore.selectDevice(workerIdQuery)
  } else {
    await chatStore.fetchConversations()
  }
  if (chatStore.lastRevocationInfo && !chatStore.selectedWorkerId) {
    void router?.replace('/remote/devices')
    return
  }
  chatStore.startPolling(3000)
  chatStore.startDevicePolling(15000)
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('keydown', handleSidebarKeydown)
  }
  scrollToBottom()
})

function handleSidebarKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && isMobileSidebarOpen.value) {
    isMobileSidebarOpen.value = false
  }
}

onUnmounted(() => {
  chatStore.stopPolling()
  chatStore.stopDevicePolling()
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    window.removeEventListener('keydown', handleSidebarKeydown)
  }
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

watch(() => chatStore.activeConversationId, () => { nativeConfirmed.value = false; nextMessageNew.value = false })
const newTopicDisabledReason = computed(() => {
  if (!chatStore.activeConversation) return '请先选择对话'
  if (chatStore.activeConversation.conversationKind === 'native') return '原生会话固定继续上下文，不支持新话题'
  if (chatStore.piGuardIssue) return chatStore.piGuardIssue
  if (chatStore.isRemoteSuspended) return '这台电脑的远程操作已暂停'
  if (!chatStore.isWorkerOnline) return '电脑离线，暂不能开启新话题'
  if (chatStore.isConversationBusy) return '对话正在进行，结束后再开启新话题'
  if (chatStore.isSending) return '消息正在发送'
  return ''
})
const connectionLabel = computed(() => {
  const device = chatStore.activeDevice
  if (!device) return { text: '未连接', variant: 'neutral' as const }
  if (device.status === 'reconciliation_required') return { text: '未就绪', variant: 'neutral' as const }
  if (!chatStore.isWorkerOnline) return { text: '电脑离线', variant: 'warning' as const }
  if (device.busySnapshotFresh === false) return { text: '未就绪', variant: 'neutral' as const }
  return { text: '电脑在线', variant: 'success' as const }
})
function newTopic() { if (!newTopicDisabledReason.value) nextMessageNew.value = true }
function resizeComposer() {
  if (!composerRef.value) return
  composerRef.value.style.height = '44px'
  composerRef.value.style.height = `${Math.min(132, Math.max(44, composerRef.value.scrollHeight))}px`
}
watch(inputText, () => { void nextTick(resizeComposer) })

const pendingCommands = computed(() =>
  chatStore.commands.filter(
    (c) => c.status === 'queued' || c.status === 'accepted'
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

const statusExpanded = ref(false)
watch(() => chatStore.activeConversationId, () => { statusExpanded.value = false })
const deliveryFailure = computed(() => [...chatStore.commands].reverse().find((cmd) =>
  cmd.status === 'failed' || cmd.error?.code === 'REMOTE_DELIVERY_EXPIRED'))
const statusNeedsAttention = computed(() => latestControlCommand.value?.controlResult?.outcome === 'unconfirmed' ||
  Boolean(deliveryFailure.value) || chatStore.activeRun?.status === 'failed')
const statusLabel = computed(() => {
  switch (chatStore.activeRun?.status) {
    case 'waiting_approval': return '等待审批'
    case 'succeeded': return '已完成'
    case 'failed': return '已失败'
    case 'cancelled': return '已取消'
    case 'paused': return '已暂停'
    default: return '运行中'
  }
})
watch([statusNeedsAttention, () => chatStore.activeConversationId,
  () => latestControlCommand.value?.commandId, () => deliveryFailure.value?.commandId,
  () => chatStore.activeRun?.runId], ([attention]) => {
  if (attention) statusExpanded.value = true
}, { immediate: true })

function canWithdraw(cmd: RemoteCommandView): boolean {
  return cmd.type === 'run.submit' && !cmd.resultRef && cmd.withdrawalState === 'none' &&
    (cmd.status === 'queued' || cmd.status === 'accepted')
}

async function handleSendMessage() {
  if (chatStore.isRemoteSuspended) { chatStore.sendError = '这台电脑的远程操作已暂停'; return }
  if (!chatStore.activeConversationId) {
    chatStore.sendError = '请先选择或新建对话'
    return
  }
  const text = inputText.value.trim()
  if (!text || chatStore.isSending || attachmentsBlocked.value || !nativeCanSend.value) return

  if (!chatStore.isWorkerOnline) {
    chatStore.sendError = '设备离线，发送失败'
    return
  }
  if (chatStore.isConversationBusy) {
    chatStore.sendError = '当前电脑正在执行，请等待完成'
    return
  }

  try {
    const conversationId = chatStore.activeConversationId
    const drafts = attachmentDrafts.value
    await chatStore.sendMessage(text, nextMessageNew.value && chatStore.activeConversation?.conversationKind !== 'native' ? 'new' : 'continue', nativeConfirmed.value && chatStore.activeConversation?.nativeSourceRevision ? { terminalClosedConfirmed: true, sourceRevision: chatStore.activeConversation.nativeSourceRevision } : undefined, drafts?.ids() || [])
    drafts?.sent()
    if (chatStore.activeConversationId !== conversationId) return
    nativeConfirmed.value = false
    nextMessageNew.value = false
    inputText.value = ''
    scrollToBottom()
  } catch {
    nativeConfirmed.value = false
    // Input retained on failure
  }
}

async function handleCreateConversation() {
  if (chatStore.isRemoteSuspended) { chatStore.actionError = '这台电脑的远程操作已暂停'; return }
  if (!chatStore.isWorkerOnline) {
    chatStore.actionError = '设备离线，发送失败'
    return
  }
  if (!canCreate.value || !chatStore.selectedDevice || !selectedScene.value) return
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  const title = newTitle.value.trim() || `新任务 ${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`
  isCreating.value = true
  try {
    const res = await chatStore.createConversation({
      targetWorkerId: chatStore.selectedDevice.workerId,
      title,
      workspaceId: newWorkspaceId.value,
      sceneId: selectedScene.value.sceneId,
      sceneVersion: selectedScene.value.version,
      workerStoreId: chatStore.selectedDevice.workerStoreId,
    })
    if (res) {
      isNewConversationDialogOpen.value = false
      newTitle.value = ''
      // Keep the creation placeholder visible until the real conversation arrives.
      isMobileSidebarOpen.value = Boolean(chatStore.pendingConversation)
    }
  } catch {
    // Handled in store
  } finally {
    isCreating.value = false
  }
}

async function handleControl(action: 'pause' | 'resume' | 'cancel' | 'retry') {
  if (!chatStore.activeRun) return
  if (!chatStore.isWorkerOnline) {
    chatStore.actionError = '设备离线，发送失败'
    return
  }
  try {
    await chatStore.controlRun(chatStore.activeRun.runId, action)
  } catch {
    // Handled in store
  }
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
  if (!chatStore.isWorkerOnline) {
    chatStore.actionError = '设备离线，发送失败'
    return
  }
  if (decision === 'approve') {
    const ok = await confirm({
      title: '确认批准执行操作？',
      description: `操作: ${approval.action}\n目标: ${approval.targetSummary || '当前任务'}\n风险级别: ${approval.riskLevel === 'high' ? '高风险' : '普通风险'}`,
      confirmText: '确认批准',
    })
    if (!ok) return
  }
  try {
    await chatStore.decideApproval(approval.approvalId, decision)
  } catch {
    // Handled in store
  }
}

async function handleLogout() {
  if (!await confirm({ title: '确定退出登录？', confirmText: '退出' })) return
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
  <div class="h-dvh flex flex-col bg-bg-app select-none overflow-hidden">
    <!-- Top Bar -->
    <header class="h-16 bg-panel border-b border-border px-[12px] flex items-center justify-between gap-2 shrink-0 z-30">
      <div class="flex items-center gap-1 min-w-0 flex-1">
        <button type="button" class="min-w-[44px] min-h-[44px] shrink-0 rounded-xl flex items-center justify-center text-content-muted hover:bg-muted" title="打开对话列表" aria-label="打开对话列表" @click="isMobileSidebarOpen = true"><Menu class="w-5 h-5" /></button>
        <div class="min-w-0 flex-1 space-y-1">
          <button type="button" class="block w-full text-left text-xs font-semibold text-content-primary truncate" title="切换电脑" @click="router.push('/remote/devices')">{{ chatStore.selectedDevice?.displayName || chatStore.selectedDevice?.deviceName || '我的电脑' }} / {{ chatStore.activeConversation?.title || '对话' }}</button>
          <div class="flex items-center gap-1 min-w-0">
            <HqBadge :variant="connectionLabel.variant" class="text-[10px] shrink-0" data-testid="connection-status">{{ connectionLabel.text }}</HqBadge>
            <span v-if="chatStore.activeConversation?.conversationKind === 'native'" class="text-[10px] text-content-secondary"><RuntimeIcon :agent="chatStore.activeConversation.agentType" class="inline-block w-4 h-4" /> {{ agentLabel(chatStore.activeConversation.agentType) }}</span>
            <button v-if="chatStore.activeRun" type="button" data-testid="run-status-toggle" class="shrink-0 rounded px-1 py-0.5 text-[10px]" :class="statusNeedsAttention ? 'text-status-warning bg-status-warning-soft' : 'text-content-muted bg-muted'" :aria-expanded="statusExpanded" aria-controls="remote-status-details" @click="statusExpanded = !statusExpanded">{{ statusLabel }}{{ statusNeedsAttention ? ' !' : '' }}</button>
          </div>
        </div>
      </div>
      <div class="flex items-center gap-[8px] shrink-0" data-testid="chat-header-actions">
        <button type="button" aria-label="新话题" :aria-description="newTopicDisabledReason || '下一条消息开启新话题'" :title="newTopicDisabledReason || '新话题'" :disabled="Boolean(newTopicDisabledReason)" class="w-[44px] h-[44px] rounded-xl flex items-center justify-center text-content-muted hover:bg-muted disabled:opacity-50" @click="newTopic"><Plus class="w-5 h-5" /></button>
        <button type="button" aria-label="管理设备" title="管理设备" class="w-[44px] h-[44px] rounded-xl flex items-center justify-center text-content-muted hover:bg-muted" @click="router.push('/remote/devices')"><Laptop class="w-5 h-5" /></button>
        <button type="button" aria-label="退出登录" title="退出登录" class="w-[44px] h-[44px] rounded-xl flex items-center justify-center text-content-muted hover:bg-muted" @click="handleLogout"><LogOut class="w-5 h-5" /></button>
      </div>
    </header>
    <RemoteRequestNotice />

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
        role="dialog"
        aria-modal="true"
        aria-label="远程对话列表"
        :inert="!isMobileSidebarOpen"
        tabindex="-1"
        class="fixed inset-y-0 left-0 z-50 w-72 max-w-[80vw] bg-panel border-r border-border flex flex-col transition-transform duration-200 ease-in-out shadow-2xl outline-none"
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
            :disabled="chatStore.isRemoteSuspended"
            @click="openCreateDialog()"
          >
            <Plus class="w-3.5 h-3.5 mr-1" />
            新建任务
          </HqButton>
        </div>

        <!-- Workspace-grouped conversation list -->
        <div class="flex-1 overflow-y-auto p-2 space-y-3">
          <!-- Pending Creation Placeholder (F1) -->
          <div
            v-if="chatStore.pendingConversation"
            class="p-2.5 rounded-lg text-xs border border-dashed transition-all"
            :class="[
              chatStore.pendingConversation.status === 'creating'
                ? 'bg-primary/5 border-primary/30 text-text-muted opacity-80 cursor-not-allowed select-none'
                : 'bg-danger/10 border-danger/30 text-danger'
            ]"
          >
            <div v-if="chatStore.pendingConversation.status === 'creating'" class="flex items-center gap-2">
              <Clock class="w-3.5 h-3.5 animate-spin text-primary shrink-0" />
              <div class="min-w-0 flex-1">
                <div class="font-medium text-text truncate">{{ chatStore.pendingConversation.title }}</div>
                <div class="text-[11px] text-primary/80">正在电脑上创建…</div>
              </div>
            </div>
            <div v-else class="flex items-center justify-between gap-2 w-full">
              <div class="flex items-center gap-1.5 min-w-0">
                <AlertCircle class="w-3.5 h-3.5 text-danger shrink-0" />
                <span class="truncate">创建失败，请重试</span>
              </div>
              <button
                type="button"
                class="p-1 text-danger hover:opacity-80 shrink-0 cursor-pointer"
                title="关闭"
                @click="chatStore.clearPendingConversation()"
              >
                <X class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <div
            v-if="chatStore.conversations.length === 0 && !chatStore.pendingConversation"
            class="py-8 text-center text-xs text-text-muted"
          >
            暂无对话，点击上方新建
          </div>

          <div
            v-for="group in chatStore.conversationsByWorkspace"
            :key="group.workspaceId"
            class="space-y-1"
          >
            <div class="px-2 py-1 text-[11px] font-medium text-text-muted flex items-center justify-between">
              <span class="truncate">{{ group.workspaceName }}</span>
              <div class="flex items-center gap-2">
                <span class="text-[10px] tabular-nums">{{ group.conversations.length }}</span>
                <button type="button" class="p-1 text-primary" :disabled="chatStore.isRemoteSuspended" :aria-label="`在${group.workspaceName}新建任务`" @click="openCreateDialog(group.workspaceId)">
                  <Plus class="w-4 h-4" />
                </button>
              </div>
            </div>

            <div
              v-for="conv in group.conversations"
              :key="conv.conversationId"
              class="w-full text-left p-3 min-h-[48px] rounded-xl text-xs transition-colors flex items-center justify-between gap-2 cursor-pointer group"
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
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-1.5 flex-wrap">
                  <span class="truncate font-medium">{{ conv.title }}</span>
                  <span
                    v-if="conv.visibility === 'mobile_only'"
                    class="shrink-0 text-[9px] px-1 py-0.5 rounded bg-warning/15 text-warning border border-warning/25"
                  >
                    仅手机
                  </span>
                  <span
                    v-else-if="conv.visibility === 'pc_only'"
                    class="shrink-0 text-[9px] px-1 py-0.5 rounded bg-muted text-text-muted border border-border"
                  >
                    仅电脑
                  </span>
                  <span
                    v-if="conv.busy"
                    class="shrink-0 text-[9px] px-1 py-0.5 rounded bg-warning/15 text-warning"
                  >
                    忙碌
                  </span>
                </div>
                <div class="flex items-center gap-2 text-[10px] text-text-muted mt-0.5">
                  <span>{{ conv.conversationKind === 'native' ? agentLabel(conv.agentType) : `场景: ${conv.sceneId}` }}</span>
                  <span v-if="conv.archived">(已归档)</span>
                </div>
              </div>

              <!-- Conversation Settings Button -->
              <button
                type="button"
                class="min-w-[40px] min-h-[40px] rounded-lg text-text-muted hover:text-text hover:bg-panel flex items-center justify-center transition-colors shrink-0 -mr-1"
                :disabled="chatStore.isRemoteSuspended"
                title="对话设置"
                @click.stop="openConversationSettings(conv)"
              >
                <MoreHorizontal class="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        <NativeSessionsPanel remote :worker-id="chatStore.selectedDevice?.workerId" :online="chatStore.isWorkerOnline" :suspended="chatStore.isRemoteSuspended" :revisions="chatStore.selectedDevice?.supportedWireRevisions"
          :projects="(chatStore.catalog?.workspaces || []).map((w) => ({ id: w.workspaceId, name: w.name }))" @opened="isMobileSidebarOpen = false" />
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
        <div v-if="chatStore.isRemoteSuspended" class="p-3 shrink-0 bg-warning/10 border-b border-warning/30 text-xs text-warning space-y-2">
          <div class="flex items-center justify-between gap-2">
            <span>这台电脑的远程操作已暂停</span>
            <HqButton size="sm" :loading="chatStore.isDeviceActionLoading" @click="chatStore.activeDevice && chatStore.patchDevice(chatStore.activeDevice.workerId, { remoteAccess: 'enabled' })">恢复远程</HqButton>
          </div>
          <p class="text-[11px]">历史与同步仍可用；取消运行和拒绝审批仍可操作。</p>
          <p v-if="chatStore.deviceActionError" role="alert" class="text-danger">{{ chatStore.deviceActionError }}</p>
        </div>
        <!-- Global Error Bar if any -->
        <div
          v-if="chatStore.actionError || chatStore.sendError"
          class="p-2 px-3 text-xs bg-danger/10 border-b border-danger/20 text-danger flex items-center justify-between shrink-0"
        >
          <span class="min-w-0 break-words whitespace-pre-wrap">{{ chatStore.actionError || chatStore.sendError }}</span>
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
          v-if="statusExpanded"
          id="remote-status-details"
          class="p-2.5 bg-panel border-b border-border shrink-0 space-y-2 text-xs max-h-[30dvh] overflow-y-auto"
        >
          <p v-if="deliveryFailure" class="text-danger">{{ deliveryFailure.error?.code === 'REMOTE_REVISION_REQUIRED' && (piScenario || chatStore.activeConversation?.agentType === 'pi') ? PI_WIRE_PENDING : deliveryFailure.error?.code?.startsWith('PI_') ? getRemoteErrorMessage(deliveryFailure.error.code) : deliveryFailure.error?.code === 'SESSION_NOT_RESUMABLE' ? getRemoteErrorMessage(deliveryFailure.error.code, deliveryFailure.error.message, chatStore.activeConversation?.conversationKind) : deliveryFailure.error?.message || '送达失败或过期，请核对后重试' }}</p>
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
                  {{ chatStore.isWorkerOnline ? '电脑在线' : '电脑离线' }}
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
                :disabled="chatStore.isRemoteSuspended"
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
                :disabled="chatStore.isRemoteSuspended"
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
                :disabled="chatStore.isRemoteSuspended"
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
                  <span><RuntimeIcon v-if="chatStore.activeConversation?.agentType" :agent="chatStore.activeConversation.agentType" class="inline-block w-4 h-4" />{{ chatStore.activeConversation?.agentType ? agentLabel(chatStore.activeConversation.agentType) : '' }}<template v-if="piScenario"><RuntimeIcon agent="pi" class="inline-block w-4 h-4" />含 PI 的场景 · </template> 安全审批请求：{{ approval.action }}</span>
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
                :disabled="chatStore.isRemoteSuspended"
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
          @scroll="handleScroll"
        >
          <!-- Earlier messages loader -->
          <div v-if="chatStore.hasMoreMessages" class="py-2 text-center text-xs text-text-muted">
            <button
              v-if="!chatStore.isLoadingEarlierMessages"
              type="button"
              class="text-primary hover:underline cursor-pointer"
              @click="loadMoreMessages"
            >
              加载更早的消息
            </button>
            <span v-else>正在加载更早的消息...</span>
          </div>

          <div
            v-if="!chatStore.activeConversationId"
            class="h-full flex items-center justify-center p-6 text-center"
          >
            <HqEmptyState
              title="未选择对话"
              description="请从左侧列表选择对话，或创建新任务与电脑上的 Agent 沟通"
            >
              <template #action>
                <div class="flex items-center gap-2 justify-center mt-3">
                  <HqButton size="sm" variant="secondary" @click="isMobileSidebarOpen = true">
                    <MessageSquare class="w-3.5 h-3.5 mr-1" />
                    查看对话列表
                  </HqButton>
                  <HqButton size="sm" variant="primary" :disabled="chatStore.isRemoteSuspended || !chatStore.isWorkerOnline" @click="openCreateDialog()">
                    <Plus class="w-3.5 h-3.5 mr-1" />
                    新建任务
                  </HqButton>
                </div>
              </template>
            </HqEmptyState>
          </div>

          <div
            v-else-if="chatStore.messages.length === 0"
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
              <MessageAttachments v-if="msg.attachments?.length" :attachments="msg.attachments" remote />
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
                <span class="font-medium text-text">{{ cmd.status === 'accepted' ? '指令处理中' : '等待电脑确认（送达期限内）' }}</span>
              </div>

              <HqBadge
                :variant="!chatStore.isWorkerOnline ? 'warning' : cmd.status === 'accepted' ? 'success' : 'info'"
                class="text-[10px]"
              >
                {{
                  !chatStore.isWorkerOnline
                    ? '电脑离线'
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
                v-if="canWithdraw(cmd)"
                type="button"
                class="text-danger hover:underline font-medium cursor-pointer flex items-center gap-1"
                :disabled="chatStore.isRemoteSuspended"
                @click="openWithdrawDialog(cmd)"
              >
                <Undo2 class="w-3 h-3" />
                撤回指令
              </button>
            </div>
          </div>
        </div>

        <!-- Composer -->
        <footer class="px-[12px] py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] bg-panel border-t border-border shrink-0 space-y-2">
          <!-- Busy lock banner -->
          <div
            v-if="chatStore.isConversationBusy"
            class="p-1.5 px-2 rounded bg-warning/15 border border-warning/30 text-[11px] text-warning flex items-center gap-1.5"
          >
            <Clock class="w-3.5 h-3.5 shrink-0 animate-spin" />
            <span>当前电脑正在执行，请等待完成</span>
          </div>

          <!-- Interrupted previous run alert -->
          <div
            v-if="chatStore.activeRun && (chatStore.activeRun.status === 'cancelled' || chatStore.activeRun.status === 'failed')"
            class="p-1.5 px-2 rounded bg-warning/15 border border-warning/30 text-[11px] text-warning flex items-center gap-1.5"
          >
            <AlertTriangle class="w-3.5 h-3.5 shrink-0" />
            <span>上一轮已中断，继续上下文可能失败</span>
          </div>

          <div v-if="chatStore.activeConversation?.conversationKind === 'native'" class="text-[11px] space-y-1">
            <p>{{ agentLabel(chatStore.activeConversation.agentType) }} · 固定继续原生会话</p>
            <template v-if="chatStore.activeConversation.nativeActivity?.activity !== 'closed_confirmed'">
              <p>{{ closureText }}</p><label class="flex gap-2"><input class="hq-form-choice" v-model="nativeConfirmed" type="checkbox" />我已在终端退出该会话</label>
            </template>
          </div>
          <p v-if="chatStore.piGuardIssue" role="alert" class="text-sm text-status-warning">{{ chatStore.piGuardIssue }}</p>
          <div v-if="nextMessageNew" class="flex items-center w-fit rounded-lg bg-accent-soft text-content-primary" data-testid="new-topic-tag"><span class="pl-3 text-xs">新话题</span><button type="button" aria-label="取消新话题" :disabled="chatStore.isSending" class="min-w-[44px] min-h-[44px] rounded-r-lg text-content-primary" @click="nextMessageNew = false">×</button></div>
          <AttachmentDrafts v-if="chatStore.activeConversationId" :key="chatStore.activeConversationId" ref="attachmentDrafts" remote :conversation-id="chatStore.activeConversationId" :suspended="chatStore.isRemoteSuspended" :disabled="chatStore.isSending" :offline="!chatStore.isWorkerOnline" @blocked="attachmentsBlocked = $event" />
          <!-- Input + Send Button -->
          <div class="hq-composer-row">
            <button type="button" aria-label="添加附件" class="hq-composer-icon text-content-muted" :disabled="!chatStore.activeConversationId || chatStore.isRemoteSuspended || chatStore.isSending" @click="attachmentDrafts?.open()"><Paperclip class="w-5 h-5" /></button>
            <textarea
              ref="composerRef"
              v-model="inputText"
              rows="1"
              :placeholder="chatStore.activeConversationId ? '输入给电脑上 Agent 的指令...' : '请先在左侧选择或新建对话...'"
              class="hq-form-control hq-composer-text text-sm border border-border"
              :disabled="!chatStore.activeConversationId || chatStore.isRemoteSuspended || chatStore.isSending || chatStore.isConversationBusy"
              @keydown.enter.exact.prevent="handleSendMessage"
            />

            <HqButton
              variant="primary"
              aria-label="发送消息"
              class="hq-composer-send"
              :loading="chatStore.isSending"
              :disabled="!chatStore.activeConversationId || Boolean(chatStore.piGuardIssue) || attachmentsBlocked || !nativeCanSend || chatStore.isRemoteSuspended || !inputText.trim() || chatStore.isSending || chatStore.isConversationBusy"
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
      title="新建任务"
      @close="isNewConversationDialogOpen = false"
    >
      <div class="space-y-4 text-xs text-text">
        <p v-if="chatStore.actionError" role="alert" class="text-danger">{{ chatStore.actionError }}</p>
        <div class="space-y-1.5">
          <div class="flex items-center justify-between"><label for="new-conv-workspace" class="block font-medium text-text-secondary">项目</label>
            <HqButton size="sm" variant="ghost" :disabled="!chatStore.catalog?.authorizedRoots?.length || chatStore.isRemoteSuspended || !chatStore.isWorkerOnline" @click="addingWorkspace = true">添加项目</HqButton>
          </div>
          <p v-if="!chatStore.catalog?.authorizedRoots?.length" class="text-[11px] text-text-muted">电脑未开放远程添加项目</p>
          <HqSelect id="new-conv-workspace" v-model="newWorkspaceId" label="项目" :placeholder="catalogHint" :disabled="!chatStore.catalog || chatStore.isLoadingCatalog" :options="(chatStore.catalog?.workspaces || []).map((ws) => ({ value: ws.workspaceId, label: ws.name }))" />
        </div>
        <div class="space-y-1.5">
          <label for="new-conv-title" class="block font-medium text-text-secondary">标题（选填）</label>
          <input
            id="new-conv-title"
            v-model="newTitle"
            type="text"
            placeholder="例如：重构远程网关并测试"
            class="hq-form-control w-full py-2 px-3 bg-bg-app border border-border rounded-lg text-text focus:outline-hidden focus:border-primary"
          />
        </div>

        <div class="space-y-1.5">
          <label for="new-conv-scene" class="block font-medium text-text-secondary">工作场景</label>
          <HqSelect id="new-conv-scene" v-model="newSceneId" label="工作场景" :placeholder="catalogHint" :disabled="!chatStore.catalog || chatStore.isLoadingCatalog" :options="(chatStore.catalog?.scenes || []).map((scene) => ({ value: scene.sceneId, label: scene.name }))" />
        </div>
        <div v-if="!chatStore.catalog || chatStore.catalogError || !chatStore.catalog.workspaces.length || !chatStore.catalog.scenes.length" role="status" class="space-y-2">
          <p>{{ catalogHint }}</p>
          <HqButton size="sm" :disabled="chatStore.isLoadingCatalog" @click="retryCatalog">重试</HqButton>
        </div>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-2 w-full">
          <HqButton
            variant="ghost"
            size="md"
            class="min-h-[38px]"
            :disabled="isCreating"
            @click="isNewConversationDialogOpen = false"
          >
            取消
          </HqButton>
          <HqButton
            variant="primary"
            size="md"
            class="min-h-[38px]"
            :loading="isCreating"
            :disabled="!canCreate"
            @click="handleCreateConversation"
          >
            创建
          </HqButton>
        </div>
      </template>
    </HqDialog>

    <RemoteWorkspaceDialog v-if="addingWorkspace" @close="addingWorkspace = false" @selected="newWorkspaceId = $event" />

    <!-- Withdraw Confirmation Dialog -->
    <HqDialog
      :open="Boolean(commandToWithdraw)"
      title="确认撤回待确认指令？"
      @close="commandToWithdraw = null"
    >
      <div class="space-y-3 text-xs text-text">
        <p class="leading-relaxed">
          在线提交最多等待 30 秒送达。撤回需要电脑确认，不代表已经停止；已产生运行结果时请使用取消运行。
        </p>
        <div class="space-y-1.5">
          <label for="withdraw-reason" class="block font-medium text-text-secondary">撤回原因 (选填)</label>
          <input
            id="withdraw-reason"
            v-model="withdrawReason"
            type="text"
            placeholder="例如：指令输入错误"
            class="hq-form-control w-full py-2.5 px-3 bg-bg-app border border-border rounded-lg text-sm text-text focus:outline-hidden focus:border-primary"
          />
        </div>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-2 w-full">
          <HqButton
            variant="ghost"
            size="md"
            class="min-h-[38px]"
            :disabled="isWithdrawing"
            @click="commandToWithdraw = null"
          >
            取消
          </HqButton>
          <HqButton
            variant="danger"
            size="md"
            class="min-h-[38px]"
            :loading="isWithdrawing"
            :disabled="chatStore.isRemoteSuspended"
            @click="confirmWithdraw"
          >
            确认撤回
          </HqButton>
        </div>
      </template>
    </HqDialog>

    <!-- Conversation Settings Dialog -->
    <HqDialog
      :open="isConvSettingsOpen"
      title="对话设置"
      @close="isConvSettingsOpen = false"
    >
      <div class="space-y-4 text-xs text-text">
        <div class="space-y-1.5">
          <label for="settings-title" class="block font-medium text-text-secondary">对话标题</label>
          <input
            id="settings-title"
            v-model="settingsTitle"
            type="text"
            class="hq-form-control w-full py-2.5 px-3 bg-bg-app border border-border rounded-lg text-sm text-text focus:outline-hidden focus:border-primary"
          />
        </div>

        <div class="space-y-1.5">
          <label class="block font-medium text-text-secondary">可见性</label>
          <div class="space-y-2">
            <label class="flex items-center gap-3 p-2.5 rounded-lg border border-border bg-bg-app hover:bg-muted/40 cursor-pointer min-h-[44px]">
              <input type="radio" v-model="settingsVisibility" value="both" class="hq-form-choice accent-primary shrink-0" />
              <span class="font-medium text-text">两端均可见 (默认)</span>
            </label>
            <label class="flex items-center gap-3 p-2.5 rounded-lg border border-border bg-bg-app hover:bg-muted/40 cursor-pointer min-h-[44px]">
              <input type="radio" v-model="settingsVisibility" value="pc_only" class="hq-form-choice accent-primary shrink-0" />
              <span class="font-medium text-text">仅电脑可见</span>
            </label>
            <label class="flex items-center gap-3 p-2.5 rounded-lg border border-border bg-bg-app hover:bg-muted/40 cursor-pointer min-h-[44px]">
              <input type="radio" v-model="settingsVisibility" value="mobile_only" class="hq-form-choice accent-primary shrink-0" />
              <span class="font-medium text-text">仅手机可见</span>
            </label>
          </div>
        </div>

        <div class="pt-2 border-t border-border">
          <label class="flex items-center gap-3 p-2.5 rounded-lg border border-border bg-bg-app hover:bg-muted/40 cursor-pointer min-h-[44px]">
            <input type="checkbox" v-model="settingsArchived" class="hq-form-choice accent-primary shrink-0" />
            <span class="font-medium text-text">归档此对话</span>
          </label>
        </div>

        <div v-if="chatStore.settingsNotice" class="text-xs text-primary/80 bg-primary/10 p-2.5 rounded-lg">
          {{ chatStore.settingsNotice }}
        </div>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-2 w-full">
          <HqButton
            variant="ghost"
            size="md"
            class="min-h-[38px]"
            :disabled="isSavingSettings"
            @click="isConvSettingsOpen = false"
          >
            取消
          </HqButton>
          <HqButton
            variant="primary"
            size="md"
            class="min-h-[38px]"
            :loading="isSavingSettings"
            :disabled="chatStore.isRemoteSuspended"
            @click="handleSaveSettings"
          >
            保存
          </HqButton>
        </div>
      </template>
    </HqDialog>

    <!-- PC Only Confirmation Dialog -->
    <HqDialog
      :open="isPcOnlyConfirmOpen"
      title="设置为仅电脑可见确认"
      @close="isPcOnlyConfirmOpen = false"
    >
      <div class="space-y-3 text-xs text-text">
        <p class="leading-relaxed">
          设置为『仅电脑』后，该对话将从手机端列表中移除，只能在电脑端查看和继续。确认设置？
        </p>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-2 w-full">
          <HqButton
            variant="ghost"
            size="md"
            class="min-h-[38px]"
            :disabled="isSavingSettings"
            @click="isPcOnlyConfirmOpen = false"
          >
            取消
          </HqButton>
          <HqButton
            variant="danger"
            size="md"
            class="min-h-[38px]"
            :loading="isSavingSettings"
            :disabled="chatStore.isRemoteSuspended"
            @click="executeSaveSettings"
          >
            确认设置
          </HqButton>
        </div>
      </template>
    </HqDialog>
  </div>
</template>
