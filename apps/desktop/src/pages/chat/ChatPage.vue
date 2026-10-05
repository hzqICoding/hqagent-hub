<script setup lang="ts">
import type { RuntimeNativeSessionIndex, RemoteNativeSessionView, NativeMessagePart } from '@hqagent/protocol'
import { getLocalChatGateway } from '@/shared/api'
import { activityLabel, closureText, NativeMessageAssembler, nativeFailure } from '@/pages/native/native-utils'
import RuntimeIcon from '@/shared/runtime/RuntimeIcon.vue'
import ConversationDeletion from './components/ConversationDeletion.vue'
import NativeSyncNotice from '@/pages/native/NativeSyncNotice.vue'
import { agentLabel } from '@/pages/native/native-utils'
import { ref, onMounted, onUnmounted, watch, nextTick, computed, inject } from 'vue'
import { routeLocationKey, type RouteLocationNormalizedLoaded } from 'vue-router'
import { useChatStore } from '@/stores/chat.store'
import { useLocalAuthStore } from '@/stores/local-auth.store'
import ChatSidebar from './components/ChatSidebar.vue'
import ChatMessageItem from './components/ChatMessageItem.vue'
import ProcessActivityGroup from './components/ProcessActivityGroup.vue'
import ChatComposer from './components/ChatComposer.vue'
import RunSnapshotDrawer from './components/RunSnapshotDrawer.vue'
import {
  HqBadge,
  HqEmptyState,
  HqDialog,
  HqButton,
  HqDropdown,
  HqMarkdown,
} from '@/shared/ui'
import {
  Bot,
  FolderGit2,
  PanelRightClose,
  PanelRightOpen,
  Radio,
  Sparkles,
  ArrowDown,
  MoreHorizontal,
  RotateCcw,
  Plus,
  ArchiveRestore,
  Menu,
  Terminal,
  AlertCircle,
} from 'lucide-vue-next'

const deletionRef = ref<InstanceType<typeof ConversationDeletion> | null>(null)
const chatStore = useChatStore()
const authStore = useLocalAuthStore()
const route = inject<RouteLocationNormalizedLoaded | null>(routeLocationKey, null)

const isMobileSidebarOpen = ref(false)
const isDrawerOpen = ref(true)
const sidebarRef = ref<{ openCreateModal: () => void } | null>(null)
const messageContainerRef = ref<HTMLElement | null>(null)
const isScrolledUp = ref(false)
const isContextResetDialogOpen = ref(false)
let mounted = false

// Native sessions state & methods for main chat workbench display
const activeNativeSession = ref<RuntimeNativeSessionIndex | RemoteNativeSessionView | null>(null)
const activeNativeSessionId = computed(() => activeNativeSession.value?.nativeSessionId || null)
const nativeMessages = ref<NativeMessagePart[]>([])
const nativeBeforeCursor = ref<string | undefined>()
const isNativeReading = ref(false)
const isNativeImporting = ref(false)
const isNativeConfirmed = ref(false)
const nativeError = ref<ReturnType<typeof nativeFailure> | null>(null)
const nativeAssembler = new NativeMessageAssembler()

function isToolMessage(msg: NativeMessagePart): boolean {
  return msg.role === 'tool_summary' || /历史调用|历史返回记录|Bash:|执行工具|工具调用/.test(msg.text)
}

function getToolsSummary(toolMsgs: NativeMessagePart[]): string {
  const names = new Set<string>()
  for (const msg of toolMsgs) {
    if (/Bash:/i.test(msg.text)) names.add('Bash')
    else if (/File|ReadFile|WriteFile/i.test(msg.text)) names.add('文件操作')
    else if (/Git/i.test(msg.text)) names.add('Git')
    else names.add('工具调用')
  }
  return Array.from(names).join(', ')
}

const groupedNativeMessages = computed(() => {
  const groups: { type: 'single' | 'tools'; message?: NativeMessagePart; toolMessages?: NativeMessagePart[] }[] = []
  let currentTools: NativeMessagePart[] = []
  for (const msg of nativeMessages.value) {
    if (isToolMessage(msg)) {
      currentTools.push(msg)
    } else {
      if (currentTools.length > 0) {
        groups.push({ type: 'tools', toolMessages: [...currentTools] })
        currentTools = []
      }
      groups.push({ type: 'single', message: msg })
    }
  }
  if (currentTools.length > 0) {
    groups.push({ type: 'tools', toolMessages: [...currentTools] })
  }
  return groups
})

async function loadNativeMessages(more = false) {
  const session = activeNativeSession.value
  if (!session || session.format.status !== 'readable') return
  isNativeReading.value = true
  nativeError.value = null
  if (!more) {
    nativeAssembler.reset()
    nativeMessages.value = []
    nativeBeforeCursor.value = undefined
  }
  try {
    const page = await getLocalChatGateway().readNativeMessages(
      session.nativeSessionId,
      more ? nativeBeforeCursor.value : undefined
    )
    if (page.nativeSessionId !== session.nativeSessionId) return
    const completed = await nativeAssembler.append(page)
    nativeMessages.value = completed
    nativeBeforeCursor.value = page.hasMore ? page.before : undefined
  } catch (err) {
    nativeError.value = nativeFailure(err)
  } finally {
    isNativeReading.value = false
  }
}

async function handleSelectNativeSession(session: RuntimeNativeSessionIndex | RemoteNativeSessionView) {
  activeNativeSession.value = session
  isNativeConfirmed.value = false
  nativeError.value = null
  if (session.format.status === 'readable') {
    await loadNativeMessages(false)
  }
}

async function importActiveNativeSession() {
  const session = activeNativeSession.value
  if (!session || !isNativeConfirmed.value || isNativeImporting.value) return
  isNativeImporting.value = true
  nativeError.value = null
  try {
    const input = {
      terminalClosedConfirmed: true as const,
      sourceRevision: session.sourceRevision,
      expectedIndexVersion: session.indexVersion,
    }
    const conversation = await getLocalChatGateway().importNativeSession(session.nativeSessionId, input)
    chatStore.conversations = [conversation, ...chatStore.conversations.filter(c => c.id !== conversation.id)]
    activeNativeSession.value = null
    await chatStore.selectConversation(conversation.id)
  } catch (err) {
    nativeError.value = nativeFailure(err)
    isNativeConfirmed.value = false
  } finally {
    isNativeImporting.value = false
  }
}

watch(
  () => chatStore.activeConversationId,
  (newId, oldId) => {
    if (newId && newId !== oldId) {
      activeNativeSession.value = null
    }
  }
)

const isContextResetDisabled = computed(() => !chatStore.canResetContext || chatStore.isActiveConversationArchived || chatStore.isRemoteConversation)

const conversationMenuItems = computed(() => [
  { id: 'delete', label: '删除对话', danger: true, action: () => { if (chatStore.activeConversationId) void deletionRef.value?.request(chatStore.activeConversationId) } },
  {
    id: 'reset-context',
    label: '重置 Agent 上下文',
    icon: RotateCcw,
    disabled: isContextResetDisabled.value,
    action: openContextResetDialog,
  },
])

function openContextResetDialog() {
  if (isContextResetDisabled.value) return
  isContextResetDialogOpen.value = true
}

function confirmContextReset() {
  if (chatStore.requestContextReset()) {
    isContextResetDialogOpen.value = false
  }
}

function refreshOnReturn() {
  if (mounted && !document.hidden) chatStore.startPolling()
}

onMounted(async () => {
  mounted = true
  window.addEventListener('focus', refreshOnReturn)
  window.addEventListener('online', refreshOnReturn)
  document.addEventListener('visibilitychange', refreshOnReturn)
  await chatStore.init()
  if (!mounted) return
  const convIdQuery = route?.query.convId as string | undefined
  if (convIdQuery && chatStore.conversations.some((c) => c.id === convIdQuery)) {
    await chatStore.selectConversation(convIdQuery)
  }
  chatStore.startPolling()
  scrollToBottom()
})

onUnmounted(() => {
  mounted = false
  window.removeEventListener('focus', refreshOnReturn)
  window.removeEventListener('online', refreshOnReturn)
  document.removeEventListener('visibilitychange', refreshOnReturn)
  chatStore.stopPolling()
})

function handleScroll() {
  if (!messageContainerRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = messageContainerRef.value
  isScrolledUp.value = scrollHeight - scrollTop - clientHeight > 100
}

function scrollToBottom(smooth = false) {
  if (messageContainerRef.value) {
    if (smooth && typeof messageContainerRef.value.scrollTo === 'function') {
      messageContainerRef.value.scrollTo({
        top: messageContainerRef.value.scrollHeight,
        behavior: 'smooth',
      })
    } else {
      messageContainerRef.value.scrollTop = messageContainerRef.value.scrollHeight
    }
  }
}

// Auto scroll on new messages if not reading history
watch(
  () => chatStore.messages.length,
  async () => {
    await nextTick()
    if (!isScrolledUp.value) {
      scrollToBottom()
    }
  }
)

// Auto scroll on new process activity if not scrolled up
watch(
  () => chatStore.activeRunActivities.length,
  async () => {
    await nextTick()
    if (!isScrolledUp.value) {
      scrollToBottom(true)
    }
  }
)

// Auto-close mobile sidebar when conversation changes
watch(
  () => chatStore.activeConversationId,
  () => {
    isMobileSidebarOpen.value = false
  }
)

function getSceneLabel(sceneId?: string) {
  const scene = chatStore.scenes.find((item) => item.id === sceneId)
  if (scene) return scene.name
  switch (sceneId) {
    case 'analyze':
      return '代码分析'
    case 'plan':
      return '需求规划'
    case 'develop':
      return '开发修复'
    default:
      return sceneId || ''
  }
}

function getStarterPrompts(sceneId?: string) {
  switch (sceneId) {
    case 'analyze':
      return [
        '梳理核心类职责、调用链与潜在架构风险',
        '分析现有代码实现，输出技术方案与依赖说明',
        '检查模块关键入口，定位逻辑调用关系',
      ]
    case 'plan':
      return [
        '基于当前工作区代码规划重构阶段与实施清单',
        '梳理需要修改的核心模块并给出任务拆分',
        '评估接口变更对现有模块的破坏性影响',
      ]
    case 'develop':
      return [
        '修复指定模块中的已知逻辑缺陷并自测验证',
        '实现目标特性并同步补齐测试用例',
        '重构指定模块代码结构并消除越界修改风险',
      ]
    default:
      return [
        '分析当前工程代码结构并提出优化建议',
        '梳理核心入口与关键调用关系',
      ]
  }
}

function applyStarterPrompt(prompt: string) {
  if (chatStore.isActiveConversationArchived || chatStore.isRemoteConversation) return
  chatStore.sendMessage(prompt)
}

async function restoreActiveConversation() {
  if (!chatStore.activeConversation) return
  await chatStore.setConversationArchived(chatStore.activeConversation.id, false)
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg-app overflow-hidden">
    <ConversationDeletion ref="deletionRef" @open-run="isDrawerOpen = true" />
    <!-- Load Error Alert -->
    <div
      v-if="chatStore.loadError"
      role="alert"
      class="px-4 py-2 text-xs text-danger bg-danger/10 border-b border-danger/20"
    >
      {{ chatStore.loadError }}
    </div>

    <!-- Mock Mode Warning Banner if active -->
    <div
      v-if="authStore.isMockMode"
      class="px-4 py-1.5 bg-warning/15 border-b border-warning/30 flex items-center justify-between text-xs text-text select-none shrink-0"
    >
      <div class="flex items-center gap-2">
        <Radio class="w-3.5 h-3.5 text-warning shrink-0 animate-pulse" />
        <span class="font-medium text-warning">演示模式 (Mock) 运行中</span>
        <span class="text-text-muted hidden sm:inline">
          — 正在使用本地场景 Fixture 进行无服务独立开发验证，数据变更在内存中有效
        </span>
      </div>

      <button
        type="button"
        class="text-[11px] text-primary underline hover:text-primary-hover font-medium cursor-pointer"
        @click="authStore.setGatewayMode('real')"
      >
        切回真实 Worker
      </button>
    </div>

    <!-- 3-Column Workbench -->
    <div class="flex-1 min-h-0 flex overflow-hidden relative">
      <!-- Mobile backdrop for Left Sidebar Drawer -->
      <div
        v-if="isMobileSidebarOpen"
        class="fixed inset-0 bg-black/50 backdrop-blur-xs z-40 md:hidden transition-opacity"
        @click="isMobileSidebarOpen = false"
      />

      <!-- Left Column: Conversations Sidebar -->
      <ChatSidebar
        ref="sidebarRef"
        class="fixed inset-y-0 left-0 z-50 md:static md:z-auto transition-transform duration-200 ease-in-out"
        :class="[
          isMobileSidebarOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full md:translate-x-0',
        ]"
        :active-native-session-id="activeNativeSessionId"
        @close="isMobileSidebarOpen = false"
        @select="activeNativeSession = null; isMobileSidebarOpen = false"
        @select-native-session="handleSelectNativeSession"
        @delete="deletionRef?.request($event)"
      />

      <!-- Center Column: Active Chat Stream & Composer -->
      <main class="flex-1 flex flex-col h-full bg-bg-app min-w-0 overflow-hidden">
        <!-- Center Header -->
        <header class="p-2.5 sm:p-3 border-b border-border bg-panel flex items-center justify-between gap-2 sm:gap-3 shrink-0 select-none">
          <div class="flex items-center gap-1.5 sm:gap-2 min-w-0">
            <!-- Mobile Sidebar Drawer Toggle Button -->
            <button
              type="button"
              class="md:hidden min-w-[44px] min-h-[44px] -ml-1 p-2 rounded-lg hover:bg-panel-hover text-text-muted hover:text-text flex items-center justify-center cursor-pointer transition-colors shrink-0"
              title="打开任务列表"
              aria-label="打开任务列表"
              @click="isMobileSidebarOpen = true"
            >
              <Menu class="w-5 h-5" />
            </button>

            <div v-if="activeNativeSession" class="flex items-center gap-2 min-w-0">
              <h1 class="text-sm font-semibold text-text truncate">
                {{ activeNativeSession.title }}
              </h1>

              <HqBadge size="sm" variant="info" class="text-[10px] shrink-0">
                <RuntimeIcon :agent="activeNativeSession.agentType" class="inline-block w-4 h-4 mr-0.5" />{{ agentLabel(activeNativeSession.agentType) }}
              </HqBadge>

              <HqBadge size="sm" variant="neutral" class="text-[10px] shrink-0 font-medium">
                终端原生会话
              </HqBadge>

              <div class="hidden md:flex items-center gap-1 text-xs text-text-muted shrink-0">
                <FolderGit2 class="w-3.5 h-3.5" />
                <span class="truncate">
                  {{ chatStore.workspaces.find((w) => w.id === activeNativeSession?.workspaceId)?.name || '未指定工作区' }}
                </span>
              </div>
            </div>

            <div v-else-if="chatStore.activeConversation" class="flex items-center gap-2 min-w-0">
              <h1 class="text-sm font-semibold text-text truncate">
                {{ chatStore.activeConversation.title }}
              </h1>

              <HqBadge size="sm" variant="info" class="text-[10px] shrink-0">
                <RuntimeIcon v-if="chatStore.activeConversation.agentType" :agent="chatStore.activeConversation.agentType" class="inline-block w-4 h-4" />{{ chatStore.activeConversation.conversationKind === 'native' ? agentLabel(chatStore.activeConversation.agentType) : getSceneLabel(chatStore.activeConversation.sceneId) }}
              </HqBadge>

              <HqBadge v-if="chatStore.activeConversation.authority === 'remote'" size="sm" variant="primary" class="text-[10px] shrink-0 font-medium">
                手机远程
              </HqBadge>

              <HqBadge v-if="chatStore.isActiveConversationArchived" size="sm" variant="neutral" class="text-[10px] shrink-0">
                已归档
              </HqBadge>

              <div class="hidden md:flex items-center gap-1 text-xs text-text-muted shrink-0">
                <FolderGit2 class="w-3.5 h-3.5" />
                <span class="truncate">
                  {{ chatStore.workspaces.find((w) => w.id === chatStore.activeConversation?.workspaceId)?.name }}
                </span>
              </div>
            </div>

            <div v-else class="text-xs text-text-muted font-medium truncate">
              未选择对话
            </div>
          </div>

          <!-- Actions & Drawer Toggle -->
          <div class="flex items-center gap-1 sm:gap-1.5 shrink-0">
            <!-- Header New Task Button: Narrow screens only (hidden on wide screen where ChatSidebar list header already has it) -->
            <button
              type="button"
              class="md:hidden min-h-[44px] min-w-[44px] p-2 rounded-xl bg-primary text-white hover:bg-primary-hover flex items-center justify-center transition-colors cursor-pointer active:scale-95 shadow-xs"
              title="新建任务"
              aria-label="新建任务"
              @click="sidebarRef?.openCreateModal()"
            >
              <Plus class="w-4 h-4" />
              <span class="sr-only">新建任务</span>
            </button>

            <HqDropdown
              v-if="!activeNativeSession && chatStore.activeConversation"
              :items="conversationMenuItems"
              placement="right"
            >
              <button
                type="button"
                class="min-w-[44px] min-h-[44px] p-2 rounded-lg hover:bg-panel-hover text-text-muted hover:text-text transition-colors flex items-center justify-center cursor-pointer"
                title="更多任务操作"
                aria-label="更多任务操作"
              >
                <MoreHorizontal class="w-4 h-4" />
              </button>
            </HqDropdown>

            <button
              type="button"
              class="min-w-[44px] min-h-[44px] p-2 px-2.5 rounded-lg hover:bg-panel-hover text-text-muted hover:text-text transition-colors flex items-center justify-center gap-1.5 text-xs cursor-pointer"
              :title="isDrawerOpen ? '收起详情抽屉' : '展开详情抽屉'"
              aria-label="执行详情"
              @click="isDrawerOpen = !isDrawerOpen"
            >
              <PanelRightClose v-if="isDrawerOpen" class="w-4 h-4 text-primary" />
              <PanelRightOpen v-else class="w-4 h-4" />
              <span class="hidden sm:inline text-xs font-medium">执行详情</span>
            </button>
          </div>
        </header>

        <!-- Message Stream View with scroll physics & Jump-to-bottom button -->
        <div class="flex-1 min-h-0 relative flex flex-col overflow-hidden">
          <div
            v-if="chatStore.isActiveConversationArchived"
            class="px-4 py-2 border-b border-border bg-muted/50 flex items-center justify-between gap-3 text-xs"
          >
            <span class="text-text-muted">此任务已归档，历史记录保持可读。恢复后才能发送消息、重试或继续执行。</span>
            <HqButton size="sm" variant="secondary" :loading="chatStore.isMetadataUpdating" @click="restoreActiveConversation">
              <ArchiveRestore class="w-3.5 h-3.5 mr-1" />
              恢复任务
            </HqButton>
          </div>

          <!-- Native Session Top Banner matching requirement 4: 确认合并进横幅 -->
          <div
            v-if="activeNativeSession"
            class="px-4 py-3 bg-panel border-b border-border/70 space-y-2.5 text-xs shrink-0 select-none"
            data-testid="native-session-workbench-banner"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="space-y-1 min-w-0 flex-1">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="font-semibold text-text text-xs">终端原生会话（只读历史）</span>
                  <span class="text-[10px] px-1.5 py-0.2 rounded bg-muted text-text-muted font-mono">
                    {{ activeNativeSession.format.cliVersion ? `CLI ${activeNativeSession.format.cliVersion}` : 'CLI' }}
                  </span>
                  <span class="text-[10px] text-text-muted">
                    {{ activityLabel(activeNativeSession.activity.activity) }}
                  </span>
                </div>
                <p class="text-text-muted text-[11px] leading-relaxed">
                  {{ closureText }}
                </p>
              </div>

              <div class="flex items-center gap-2 shrink-0">
                <HqButton
                  size="sm"
                  variant="secondary"
                  :loading="isNativeReading"
                  @click="loadNativeMessages(false)"
                >
                  重新读取
                </HqButton>
                <HqButton
                  v-if="nativeBeforeCursor"
                  size="sm"
                  variant="secondary"
                  :loading="isNativeReading"
                  @click="loadNativeMessages(true)"
                >
                  读取更早内容
                </HqButton>
              </div>
            </div>

            <!-- Confirmation & Takeover Row merged into banner -->
            <div
              v-if="activeNativeSession.format.status === 'readable'"
              class="pt-2 flex flex-wrap items-center justify-between gap-3 border-t border-border/40"
            >
              <label class="flex items-center gap-2 cursor-pointer select-none">
                <input
                  v-model="isNativeConfirmed"
                  type="checkbox"
                  class="hq-form-choice rounded border-border text-primary focus:ring-0"
                />
                <span class="text-text font-medium text-xs">我已在终端退出该会话</span>
              </label>

              <HqButton
                size="sm"
                variant="primary"
                :disabled="!isNativeConfirmed || isNativeImporting"
                :loading="isNativeImporting"
                @click="importActiveNativeSession"
              >
                接管并继续对话
              </HqButton>
            </div>

            <div
              v-else
              class="pt-2 border-t border-border/40 text-[11px] text-warning"
              data-testid="native-unavailable-explanation"
            >
              该会话由 {{ agentLabel(activeNativeSession.agentType) }} {{ activeNativeSession.format.cliVersion || '未知 CLI 版本' }} 生成，当前版本的记录格式尚未支持，无法读取或续接。原因：{{ activeNativeSession.format.reason || '当前记录格式尚未支持' }}
            </div>

            <div
              v-if="nativeError"
              role="alert"
              class="p-2 rounded bg-danger/10 text-danger text-xs flex items-center justify-between gap-2"
            >
              <span>{{ nativeError.message }}</span>
              <span v-if="nativeError.requestId" class="font-mono text-[10px] select-text">{{ nativeError.requestId }}</span>
            </div>
          </div>

          <!-- Native Session Workbench Preview Stream with merged tool lines -->
          <div
            v-if="activeNativeSession"
            class="flex-1 min-h-0 overflow-y-auto divide-y divide-border/20 py-2"
            data-testid="native-session-workbench-messages"
          >
            <!-- Loading indicator -->
            <div v-if="isNativeReading && nativeMessages.length === 0" class="p-8 text-center text-xs text-text-muted">
              正在从终端读取会话内容…
            </div>

            <!-- Unsupported format explanation -->
            <div
              v-else-if="activeNativeSession.format.status !== 'readable'"
              class="p-8 max-w-lg mx-auto text-center space-y-2 text-xs"
            >
              <div class="w-10 h-10 rounded-xl bg-warning/15 text-warning flex items-center justify-center mx-auto">
                <AlertCircle class="w-5 h-5" />
              </div>
              <p class="font-medium text-text">暂不支持此会话记录格式</p>
              <p class="text-text-muted leading-relaxed">
                原因：{{ activeNativeSession.format.reason || '当前记录格式尚未支持' }}
              </p>
            </div>

            <!-- Empty readable messages -->
            <div
              v-else-if="nativeMessages.length === 0 && !isNativeReading"
              class="p-8 text-center text-xs text-text-muted"
            >
              会话暂无可读取的历史消息
            </div>

            <!-- Native messages list with merged tool lines -->
            <div
              v-else
              class="space-y-2 p-2 sm:p-4 max-w-3xl mx-auto"
            >
              <div
                v-for="(group, gIdx) in groupedNativeMessages"
                :key="gIdx"
                class="transition-colors"
              >
                <!-- Consecutive tool calls merged into ONE line -->
                <div v-if="group.type === 'tools' && group.toolMessages" class="my-1.5" data-testid="native-merged-tool-line">
                  <details class="group/native-tool rounded-lg border border-border/60 bg-panel/50 hover:bg-panel transition-colors text-xs">
                    <summary class="cursor-pointer select-none py-1.5 px-3 flex items-center justify-between text-text-muted hover:text-text list-none font-mono text-[11px]">
                      <span class="flex items-center gap-2 truncate">
                        <Terminal class="w-3.5 h-3.5 text-primary/70 shrink-0" />
                        <span class="font-medium text-text truncate">
                          执行了 {{ group.toolMessages.length }} 个工具调用
                          <span class="text-text-muted/60 font-normal">({{ getToolsSummary(group.toolMessages) }})</span>
                        </span>
                      </span>
                      <span class="text-[10px] text-text-muted group-open/native-tool:rotate-180 transition-transform shrink-0 ml-2">▼</span>
                    </summary>
                    <div class="p-2.5 pt-1 border-t border-border/40 space-y-1.5 max-h-60 overflow-y-auto">
                      <div
                        v-for="tMsg in group.toolMessages"
                        :key="tMsg.messageId"
                        class="p-2 rounded bg-bg-app font-mono text-[11px] text-text-muted whitespace-pre-wrap break-words"
                      >
                        <HqMarkdown :content="tMsg.text" />
                      </div>
                    </div>
                  </details>
                </div>

                <!-- User message -->
                <div
                  v-else-if="group.message?.role === 'user'"
                  class="flex justify-end my-2"
                >
                  <div class="min-w-0 max-w-[92%] sm:max-w-[85%] space-y-1">
                    <div class="flex items-center justify-end gap-2 text-[11px] text-text-muted select-none">
                      <span class="font-medium text-text">你</span>
                      <span>只读历史</span>
                    </div>
                    <div class="bg-primary/10 text-text p-3 px-4 rounded-2xl rounded-tr-xs text-xs leading-relaxed whitespace-pre-wrap break-words select-text border border-primary/20 shadow-xs">
                      {{ group.message.text }}
                    </div>
                  </div>
                </div>

                <!-- Assistant message -->
                <div
                  v-else-if="group.message"
                  class="flex items-start gap-2 sm:gap-3 my-2"
                >
                  <div class="w-7 h-7 rounded-full bg-success/15 text-success flex items-center justify-center shrink-0 mt-0.5 border border-success/30 shadow-xs">
                    <RuntimeIcon :agent="activeNativeSession?.agentType" class="w-4 h-4" />
                  </div>
                  <div class="flex-1 min-w-0 space-y-1.5">
                    <div class="flex items-center gap-2 text-[11px] text-text-muted select-none">
                      <span class="font-semibold text-text text-xs">{{ activeNativeSession?.agentType ? agentLabel(activeNativeSession.agentType) : '原生 Agent' }}</span>
                      <span class="text-[10px]">只读历史</span>
                    </div>
                    <div class="bg-panel border border-border/80 p-3 sm:p-4 rounded-2xl rounded-tl-xs text-xs leading-relaxed shadow-sm break-words select-text">
                      <HqMarkdown :content="group.message.text" />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Active Normal Conversation Stream -->
          <div
            v-else-if="chatStore.activeConversation"
            ref="messageContainerRef"
            class="flex-1 min-h-0 overflow-y-auto divide-y divide-border/20 py-2"
            @scroll="handleScroll"
          >
            <NativeSyncNotice :agent-type="chatStore.activeConversation?.agentType" v-if="chatStore.activeConversation?.conversationKind === 'native'" :key="chatStore.activeConversationId || undefined" />
            <!-- Empty state with starter prompts -->
            <div
              v-if="chatStore.messages.length === 0"
              class="h-full flex flex-col items-center justify-center p-8 text-center max-w-lg mx-auto"
            >
              <div class="w-12 h-12 rounded-2xl bg-primary/10 text-primary flex items-center justify-center mb-3.5 border border-primary/20 shadow-xs">
                <Bot class="w-6 h-6" />
              </div>
              <h3 class="text-sm font-semibold text-text mb-1">
                对话已就绪，等待下发目标
              </h3>
              <p v-if="chatStore.activeConversation.conversationKind !== 'native'" class="text-xs text-text-muted leading-relaxed mb-6">
                场景「{{ getSceneLabel(chatStore.activeConversation.sceneId) }}」已锁定角色配置。您可以直接在下方输入目标，或选择以下常用方向：
              </p>

              <div v-if="!chatStore.isActiveConversationArchived" class="w-full space-y-2 text-left">
                <button
                  v-for="starter in getStarterPrompts(chatStore.activeConversation.sceneId)"
                  :key="starter"
                  type="button"
                  class="w-full p-2.5 px-3.5 rounded-xl bg-panel hover:bg-panel-hover border border-border/80 hover:border-primary/40 text-xs text-text flex items-center justify-between group transition-all shadow-xs cursor-pointer"
                  @click="applyStarterPrompt(starter)"
                >
                  <div class="flex items-center gap-2 min-w-0">
                    <Sparkles class="w-3.5 h-3.5 text-primary/70 group-hover:text-primary shrink-0" />
                    <span class="truncate">{{ starter }}</span>
                  </div>
                  <span class="text-[10px] text-text-muted group-hover:text-primary shrink-0">执行 →</span>
                </button>
              </div>
            </div>

            <!-- Message items list -->
            <ChatMessageItem
              v-for="msg in chatStore.messages"
              :key="msg.id"
              :message="msg"
            />

            <!-- Live In-Progress Execution Activity Accordion -->
            <div
              v-if="chatStore.isCurrentRunActive"
              class="max-w-3xl mx-auto px-4 py-2"
            >
              <div class="flex items-start gap-3">
                <div class="w-7 h-7 rounded-full bg-primary/15 text-primary flex items-center justify-center shrink-0 mt-0.5 border border-primary/30 shadow-xs animate-pulse">
                  <Bot class="w-4 h-4" />
                </div>
                <div class="flex-1 min-w-0 space-y-1.5">
                  <div class="flex items-center gap-2 text-[11px] text-text-muted select-none">
                    <span class="font-semibold text-text text-xs">HQAgent 团队</span>
                    <span class="text-primary font-medium animate-pulse">正在执行任务...</span>
                  </div>
                  <ProcessActivityGroup
                    :activities="chatStore.activeRunActivities"
                    :is-live="true"
                    :initially-expanded="true"
                  />
                </div>
              </div>
            </div>
          </div>

          <div v-else class="flex-1 min-h-0 flex items-center justify-center p-8">
            <HqEmptyState
              title="选择或新建一个本地对话"
              description="从左侧选择已有任务，或点击「新建任务」配置项目与角色场景开始协作"
            />
          </div>

          <!-- Floating Jump to bottom button -->
          <div
            v-if="isScrolledUp && (chatStore.activeConversation || activeNativeSession) && (chatStore.messages.length > 0 || nativeMessages.length > 0)"
            class="absolute bottom-2 left-1/2 -translate-x-1/2 z-10"
          >
            <button
              type="button"
              class="bg-panel hover:bg-panel-hover border border-border text-text text-xs px-3 py-1.5 rounded-full shadow-md flex items-center gap-1.5 cursor-pointer active:scale-95 transition-all select-none"
              @click="scrollToBottom(true)"
            >
              <ArrowDown class="w-3.5 h-3.5 text-primary" />
              <span>回到底部</span>
            </button>
          </div>
        </div>

        <!-- Floating Centered Composer Footer for Normal Conversation -->
        <ChatComposer
          v-if="chatStore.activeConversation && !chatStore.isActiveConversationArchived"
          @request-context-reset="openContextResetDialog"
        />

        <!-- Read-only footer placeholder for native preview session -->
        <div
          v-if="activeNativeSession"
          class="p-3 border-t border-border bg-panel text-center text-xs text-text-muted select-none shrink-0"
        >
          <span v-if="activeNativeSession.format.status === 'readable'">
            当前处于只读预览模式。勾选上方「我已在终端退出该会话」并点击「接管并继续对话」后，即可在此输入并继续对话。
          </span>
          <span v-else>
            当前记录格式尚未支持，无法续接对话。
          </span>
        </div>
      </main>

      <!-- Mobile backdrop for RunSnapshotDrawer -->
      <div
        v-if="isDrawerOpen"
        class="fixed inset-0 bg-black/50 backdrop-blur-xs z-40 md:hidden transition-opacity"
        @click="isDrawerOpen = false"
      />

      <!-- Right Column: Run Snapshot & Artifacts & Roles Drawer -->
      <RunSnapshotDrawer
        v-if="isDrawerOpen"
        class="fixed inset-y-0 right-0 z-50 md:static md:z-auto shadow-2xl md:shadow-none"
        @close="isDrawerOpen = false"
      />
    </div>

    <HqDialog
      :open="isContextResetDialogOpen"
      title="重置 Agent 上下文"
      description="仅影响当前任务下一条消息"
      @close="isContextResetDialogOpen = false"
    >
      <div class="space-y-3 text-xs leading-relaxed">
        <p class="text-text">
          当前任务的聊天历史会继续保留，但下一条消息将使用新的 Agent 会话。
        </p>
        <p class="text-text-muted">
          新会话不会自动携带全部历史。如有必须延续的信息，请在下一条消息中明确说明。
        </p>
      </div>
      <template #footer>
        <HqButton size="sm" variant="secondary" @click="isContextResetDialogOpen = false">
          取消
        </HqButton>
        <HqButton
          size="sm"
          variant="primary"
          :disabled="isContextResetDisabled"
          @click="confirmContextReset"
        >
          确认重置
        </HqButton>
      </template>
    </HqDialog>
  </div>
</template>
