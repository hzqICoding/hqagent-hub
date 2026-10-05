<script setup lang="ts">
import RuntimeIcon from '@/shared/runtime/RuntimeIcon.vue'
import { agentLabel } from '@/pages/native/native-utils'
import NativeSessionsPanel from '@/pages/native/NativeSessionsPanel.vue'
import { ref, computed, onMounted, inject, watch } from 'vue'
import { routerKey, type Router } from 'vue-router'
import type { LocalConversationView, LocalSceneId, TaskStatus, RuntimeNativeSessionIndex, RemoteNativeSessionView } from '@hqagent/protocol'
import { useChatStore } from '@/stores/chat.store'
import { useRemoteLinkStore } from '@/stores/remote-link.store'
import { useThemeStore } from '@/shared/theme/theme.store'
import { HqButton, HqDialog, HqDropdown, HqInput, HqSelect } from '@/shared/ui'
import {
  Archive,
  ArchiveRestore,
  Bot,
  ChevronDown,
  ChevronRight,
  Eye,
  Folder,
  FolderPlus,
  GitBranch,
  Laptop,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Settings,
  Smartphone,
  Sun,
  Moon,
  X,
} from 'lucide-vue-next'

const props = defineProps<{
  activeNativeSessionId?: string | null
}>()

const emit = defineEmits<{
  (e: 'select', id: string): void
  (e: 'close'): void
  (e: 'delete', id: string): void
  (e: 'select-native-session', session: RuntimeNativeSessionIndex | RemoteNativeSessionView): void
}>()

function handleNativeSessionSelect(session: RuntimeNativeSessionIndex | RemoteNativeSessionView) {
  emit('select-native-session', session)
  emit('close')
}

const chatStore = useChatStore()
const remoteLinkStore = useRemoteLinkStore()
const themeStore = useThemeStore()
const router = inject<Router | null>(routerKey, null)

const activeListTab = ref<'tasks' | 'native' | 'archived'>('tasks')

function setListTab(tab: 'tasks' | 'native' | 'archived') {
  activeListTab.value = tab
  if (tab === 'archived') {
    chatStore.showArchived = true
  } else if (tab === 'tasks') {
    chatStore.showArchived = false
  }
}

watch(() => chatStore.showArchived, (archived) => {
  if (archived && activeListTab.value !== 'archived') {
    activeListTab.value = 'archived'
  } else if (!archived && activeListTab.value === 'archived') {
    activeListTab.value = 'tasks'
  }
})

const isPhoneConnected = computed(() => {
  return remoteLinkStore.isPaired && remoteLinkStore.connectionStatus !== 'offline'
})

onMounted(() => {
  if (typeof remoteLinkStore.refreshLink === 'function') {
    void remoteLinkStore.refreshLink().catch(() => {})
  }
})

function navigateToRemoteLink() {
  if (router) {
    router.push({ path: '/settings', query: { tab: 'remote-link' } })
  }
}

function navigateToSettings() {
  if (router) {
    router.push('/settings')
  }
}

function toggleTheme() {
  themeStore.setMode(themeStore.settings.mode === 'dark' ? 'light' : 'dark')
}

function toggleArchivedView() {
  chatStore.showArchived = !chatStore.showArchived
  if (chatStore.showArchived) {
    activeListTab.value = 'tasks'
  }
}

// Delayed hover handlers for creating project and conversation buttons
const isProjectHeaderHovered = ref(false)
let projectHeaderTimer: ReturnType<typeof setTimeout> | null = null

function onProjectHeaderEnter() {
  if (projectHeaderTimer) clearTimeout(projectHeaderTimer)
  isProjectHeaderHovered.value = true
}

function onProjectHeaderLeave() {
  if (projectHeaderTimer) clearTimeout(projectHeaderTimer)
  projectHeaderTimer = setTimeout(() => {
    isProjectHeaderHovered.value = false
  }, 400)
}

const hoveredWorkspaceIds = ref<Record<string, boolean>>({})
const workspaceHoverTimers: Record<string, ReturnType<typeof setTimeout>> = {}

function onWorkspaceEnter(wsId: string) {
  if (workspaceHoverTimers[wsId]) clearTimeout(workspaceHoverTimers[wsId])
  hoveredWorkspaceIds.value[wsId] = true
}

function onWorkspaceLeave(wsId: string) {
  if (workspaceHoverTimers[wsId]) clearTimeout(workspaceHoverTimers[wsId])
  workspaceHoverTimers[wsId] = setTimeout(() => {
    hoveredWorkspaceIds.value[wsId] = false
  }, 400)
}

const isNewConvModalOpen = ref(false)
const newTitle = ref('')
const selectedWorkspaceId = ref('')
const selectedSceneId = ref<LocalSceneId>('analyze')
const isCreating = ref(false)
const newWorkspacePath = ref('')
const selectedFolderPath = ref('')
const projectSource = ref<'local' | 'git'>('local')
const gitRepoUrl = ref('')
const isRegistering = ref(false)
const isPicking = ref(false)
const createError = ref<string | null>(null)
const isWorkspaceLocked = ref(false)

const lockedWorkspace = computed(() => {
  return chatStore.workspaces.find((ws) => ws.id === selectedWorkspaceId.value)
})

const isRenameDialogOpen = ref(false)
const renameTarget = ref<LocalConversationView | null>(null)
const renameTitle = ref('')
const renameError = ref<string | null>(null)

const isArchiveDialogOpen = ref(false)
const archiveTarget = ref<LocalConversationView | null>(null)

const isVisibilityDialogOpen = ref(false)
const visibilityTarget = ref<LocalConversationView | null>(null)
const selectedVisibility = ref<'both' | 'pc_only' | 'mobile_only'>('both')
const visibilityError = ref<string | null>(null)

function openVisibilityDialog(conversation: LocalConversationView) {
  visibilityTarget.value = conversation
  selectedVisibility.value = conversation.visibility || 'both'
  visibilityError.value = null
  isVisibilityDialogOpen.value = true
}

async function confirmVisibility() {
  if (!visibilityTarget.value || chatStore.isMetadataUpdating) return
  visibilityError.value = null
  try {
    await chatStore.setConversationVisibility(visibilityTarget.value.id, selectedVisibility.value)
    isVisibilityDialogOpen.value = false
  } catch (error) {
    visibilityError.value = error instanceof Error ? error.message : '修改可见性失败'
  }
}

function openCreateModal(workspaceId?: string) {
  newTitle.value = ''
  isWorkspaceLocked.value = Boolean(workspaceId)
  projectSource.value = 'local'
  gitRepoUrl.value = ''
  selectedFolderPath.value = ''
  selectedWorkspaceId.value = workspaceId
    || chatStore.activeConversation?.workspaceId
    || chatStore.workspaces[0]?.id
    || ''
  selectedSceneId.value = chatStore.activeConversation?.sceneId
    || chatStore.scenes[0]?.id
    || 'analyze'
  isNewConvModalOpen.value = true
  createError.value = null
}

defineExpose({ openCreateModal })

async function handleCreateConversation() {
  const title = newTitle.value.trim() || (isWorkspaceLocked.value ? '新对话' : '新建项目')
  if (isCreating.value) return

  let wsId = selectedWorkspaceId.value
  if (!isWorkspaceLocked.value && newWorkspacePath.value.trim() && !wsId) {
    try {
      const reg = await chatStore.registerWorkspace(newWorkspacePath.value.trim())
      wsId = reg.id
      selectedWorkspaceId.value = reg.id
    } catch (e) {
      createError.value = e instanceof Error ? e.message : '项目目录登记失败'
      return
    }
  }

  if (!wsId && chatStore.workspaces[0]?.id) {
    wsId = chatStore.workspaces[0].id
  }

  if (!wsId) {
    createError.value = '请选择或登记工作区目录'
    return
  }

  isCreating.value = true
  createError.value = null
  try {
    const created = await chatStore.createConversation(title, wsId, selectedSceneId.value)
    isNewConvModalOpen.value = false
    handleConversationSelect(created.id)
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '创建失败'
  } finally {
    isCreating.value = false
  }
}

async function registerWorkspace() {
  if (!newWorkspacePath.value.trim() || isRegistering.value) return
  isRegistering.value = true
  createError.value = null
  try {
    const workspace = await chatStore.registerWorkspace(newWorkspacePath.value)
    selectedWorkspaceId.value = workspace.id
    selectedFolderPath.value = workspace.path
    newWorkspacePath.value = ''
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '项目目录登记失败'
  } finally {
    isRegistering.value = false
  }
}

async function chooseWorkspace() {
  if (isPicking.value || isRegistering.value) return
  isPicking.value = true
  createError.value = null
  try {
    const path = await chatStore.pickWorkspaceDirectory()
    if (!path) return
    newWorkspacePath.value = path
    selectedFolderPath.value = path
    if (!newTitle.value.trim()) {
      const folderName = path.split(/[\\/]/).filter(Boolean).pop()
      if (folderName) newTitle.value = folderName
    }
    await registerWorkspace()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '无法打开目录选择窗口，请手动输入目录'
  } finally {
    isPicking.value = false
  }
}

function openRenameDialog(conversation: LocalConversationView) {
  renameTarget.value = conversation
  renameTitle.value = conversation.title
  renameError.value = null
  isRenameDialogOpen.value = true
}

async function confirmRename() {
  if (!renameTarget.value || !renameTitle.value.trim() || chatStore.isMetadataUpdating) return
  try {
    await chatStore.renameConversation(renameTarget.value.id, renameTitle.value)
    isRenameDialogOpen.value = false
  } catch (error) {
    renameError.value = error instanceof Error ? error.message : '重命名失败'
  }
}

function openArchiveDialog(conversation: LocalConversationView) {
  archiveTarget.value = conversation
  isArchiveDialogOpen.value = true
}

async function confirmArchive() {
  if (!archiveTarget.value || chatStore.isMetadataUpdating) return
  try {
    await chatStore.setConversationArchived(archiveTarget.value.id, true)
    isArchiveDialogOpen.value = false
  } catch {
    // Store displays a refresh-aware metadata error above the list.
  }
}

async function restoreConversation(conversation: LocalConversationView) {
  try {
    await chatStore.setConversationArchived(conversation.id, false)
  } catch {
    // Store displays the exact error and refreshes version conflicts.
  }
}

function taskMenuItems(conversation: LocalConversationView) {
  const deletion = { id: 'delete', label: '删除对话', danger: true, action: () => emit('delete', conversation.id) }
  if (conversation.archived) {
    return [deletion, {
      id: 'restore',
      label: '恢复任务',
      icon: ArchiveRestore,
      action: () => restoreConversation(conversation),
    }]
  }
  const canArchive = chatStore.canArchiveConversation(conversation)
  return [
    deletion,
    {
      id: 'rename',
      label: '重命名',
      icon: Pencil,
      action: () => openRenameDialog(conversation),
    },
    {
      id: 'visibility',
      label: '可见性设置',
      icon: Eye,
      action: () => openVisibilityDialog(conversation),
    },
    {
      id: 'archive',
      label: canArchive ? '归档任务' : '归档任务（执行未结束）',
      icon: Archive,
      danger: true,
      disabled: !canArchive,
      action: () => openArchiveDialog(conversation),
    },
  ]
}

const statusMeta: Partial<Record<TaskStatus, { label: string; dot: string }>> = {
  draft: { label: '草稿', dot: 'bg-text-muted' },
  queued: { label: '排队', dot: 'bg-status-info' },
  running: { label: '运行中', dot: 'bg-primary animate-pulse' },
  waiting_approval: { label: '待审批', dot: 'bg-warning' },
  paused: { label: '已暂停', dot: 'bg-warning' },
  succeeded: { label: '已完成', dot: 'bg-success' },
  failed: { label: '失败', dot: 'bg-danger' },
  cancelled: { label: '已取消', dot: 'bg-text-muted' },
  unknown: { label: '未知', dot: 'bg-text-muted' },
}

function getStatusMeta(conversation: LocalConversationView) {
  const status = conversation.lastRunStatus || (conversation.activeRunId ? 'running' : undefined)
  return status ? statusMeta[status] : undefined
}

function formatTime(iso: string) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const now = new Date()
  return date.toDateString() === now.toDateString()
    ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : `${date.getMonth() + 1}/${date.getDate()}`
}

function handleConversationSelect(conversationId: string) {
  chatStore.selectConversation(conversationId)
  emit('select', conversationId)
  emit('close')
}
</script>

<template>
  <aside class="w-[85vw] max-w-[320px] md:w-72 lg:w-80 h-full border-r border-border/30 bg-panel flex flex-col shrink-0 select-none">
    <div class="p-3.5 pb-2 flex items-center justify-between gap-2">
      <div class="flex items-center gap-2 min-w-0">
        <Bot class="w-5 h-5 text-primary shrink-0" />
        <h2 class="text-sm font-semibold text-text truncate">项目任务</h2>
        <span class="text-[11px] text-text-muted bg-panel-header px-1.5 py-0.5 rounded">
          {{ chatStore.filteredConversations.length }}
        </span>
      </div>
      <div class="flex items-center gap-1 shrink-0">
        <!-- Mobile Drawer Close Button -->
        <button
          type="button"
          class="md:hidden min-w-[44px] min-h-[44px] p-2 rounded-lg hover:bg-panel-hover text-text-muted hover:text-text flex items-center justify-center cursor-pointer transition-colors"
          title="关闭任务列表"
          aria-label="关闭任务列表"
          @click="emit('close')"
        >
          <X class="w-4 h-4" />
        </button>
      </div>
    </div>

    <div class="px-3 pb-2.5 border-b border-border/30 space-y-2">
      <div class="relative">
        <Search class="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
        <input
          v-model="chatStore.searchQuery"
          type="text"
          placeholder="搜索任务或项目..."
          class="hq-form-control w-full pl-8 pr-2.5 py-1.5 text-xs bg-bg-app/70 border border-border/40 rounded-lg text-text placeholder-text-muted/60 focus:outline-none focus:border-primary transition-colors"
        />
      </div>
      <div class="grid grid-cols-2 gap-1 rounded-lg bg-bg-app/60 p-1 text-[11px]">
        <button
          type="button"
          class="rounded-md px-1.5 py-1 transition-colors cursor-pointer text-center font-medium truncate"
          :class="activeListTab !== 'native' ? 'bg-panel text-text shadow-xs' : 'text-text-muted hover:text-text'"
          @click="setListTab('tasks')"
        >
          项目任务
        </button>
        <button
          type="button"
          class="rounded-md px-1.5 py-1 transition-colors cursor-pointer text-center font-medium truncate"
          :class="activeListTab === 'native' ? 'bg-panel text-text shadow-xs' : 'text-text-muted hover:text-text'"
          @click="setListTab('native')"
        >
          原生会话
        </button>
      </div>
      <div v-if="activeListTab !== 'native'" class="flex items-center justify-between pt-0.5 px-0.5 text-[11px] text-text-muted">
        <label class="flex items-center gap-1.5 cursor-pointer select-none">
          <input
            type="checkbox"
            :checked="chatStore.includeHiddenConversations"
            class="hq-form-choice rounded border-border text-primary focus:ring-0"
            @change="chatStore.setIncludeHiddenConversations(($event.target as HTMLInputElement).checked)"
          />
          <span>显示已隐藏的对话</span>
        </label>
      </div>
      <p v-if="chatStore.metadataError" role="alert" class="text-[11px] text-danger leading-relaxed">
        {{ chatStore.metadataError }}
      </p>
    </div>

    <div class="flex-1 overflow-y-auto py-1.5">
      <!-- Native Sessions Panel (Shown only in '原生会话' tab) -->
      <NativeSessionsPanel
        v-if="activeListTab === 'native'"
        :projects="chatStore.workspaces.map((w) => ({ id: w.id, name: w.name }))"
        :search-query="chatStore.searchQuery"
        :workbench="true"
        :active-session-id="props.activeNativeSessionId"
        @select-session="handleNativeSessionSelect"
        @opened="emit('close')"
      />

      <!-- Tasks List Panel (Active Tasks & Archived Tasks) -->
      <template v-else>
        <div v-if="chatStore.showArchived" class="mx-2 mb-2 p-2 rounded-lg bg-warning/10 border border-warning/20 flex items-center justify-between text-xs text-warning">
          <span class="flex items-center gap-1.5">
            <Archive class="w-3.5 h-3.5" />
            <span>已归档任务视图</span>
          </span>
          <button type="button" class="underline text-[11px] hover:opacity-80 cursor-pointer" @click="chatStore.showArchived = false">
            退出归档
          </button>
        </div>

        <div
          v-if="chatStore.filteredConversations.length === 0"
          class="p-6 text-center text-xs text-text-muted"
        >
          <MessageSquare class="w-8 h-8 mx-auto mb-2 text-text-muted/40" />
          <p>{{ chatStore.showArchived ? '暂无已归档任务' : '暂无匹配项目或任务' }}</p>
        </div>

        <!-- 项目 Section matching Image 2 -->
        <section class="py-1">
          <div
            class="px-2.5 py-1 flex items-center justify-between text-xs text-text-muted select-none group"
            @mouseenter="onProjectHeaderEnter"
            @mouseleave="onProjectHeaderLeave"
          >
            <div class="flex items-center gap-1">
              <span class="font-medium text-text-muted">项目</span>
              <span class="text-[11px] text-text-muted/75">({{ chatStore.workspaces.length }})</span>
            </div>
            <div class="flex items-center gap-1 shrink-0">
              <button
                type="button"
                class="min-w-[44px] min-h-[44px] md:min-w-0 md:min-h-0 md:w-6 md:h-6 flex items-center justify-center rounded-md text-text-muted hover:text-primary hover:bg-muted active:scale-95 transition-all cursor-pointer"
                :class="[
                  isProjectHeaderHovered
                    ? 'opacity-100 pointer-events-auto'
                    : 'opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto',
                  'transition-opacity duration-200'
                ]"
                title="创建项目"
                aria-label="新建任务"
                @click="openCreateModal()"
              >
                <FolderPlus class="w-3.5 h-3.5" />
                <span class="sr-only">新建任务</span>
              </button>
            </div>
          </div>

          <div
            v-if="chatStore.workspaces.length === 0"
            class="mx-2 my-2 p-3 rounded-lg border border-dashed border-border/70 text-center text-xs space-y-2 select-none"
          >
            <FolderPlus class="w-6 h-6 mx-auto text-text-muted/60" />
            <div class="text-text-muted leading-relaxed">
              暂未登记项目，请先登记本地项目目录以开始任务
            </div>
            <HqButton size="sm" variant="secondary" class="w-full justify-center" @click="openCreateModal()">
              登记项目目录
            </HqButton>
          </div>

          <div
            v-for="group in chatStore.groupedConversations"
            :key="group.workspace.id"
            class="py-0.5"
          >
            <div
              class="px-2 py-1.5 rounded-lg flex items-center justify-between gap-1 text-xs text-text-muted hover:text-text select-none group"
              @mouseenter="onWorkspaceEnter(group.workspace.id)"
              @mouseleave="onWorkspaceLeave(group.workspace.id)"
            >
              <button
                type="button"
                class="flex items-center gap-1.5 min-w-0 flex-1 text-left py-1 cursor-pointer"
                :title="chatStore.collapsedWorkspaceIds[group.workspace.id] ? '展开项目' : '折叠项目'"
                @click="chatStore.toggleWorkspaceCollapsed(group.workspace.id)"
              >
                <component
                  :is="chatStore.collapsedWorkspaceIds[group.workspace.id] ? ChevronRight : ChevronDown"
                  class="w-3.5 h-3.5 shrink-0 opacity-70 transition-transform"
                />
                <Folder class="w-4 h-4 shrink-0 text-primary/80" />
                <span class="truncate font-semibold text-text text-xs">{{ group.workspace.name }}</span>
                <span class="text-[10px] text-text-muted opacity-75">({{ group.conversations.length }})</span>
              </button>
              <div class="flex items-center gap-1 shrink-0">
                <button
                  type="button"
                  class="w-6 h-6 flex items-center justify-center rounded-md text-text-muted hover:text-primary hover:bg-muted active:scale-95 transition-all cursor-pointer"
                  :class="[
                    hoveredWorkspaceIds[group.workspace.id]
                      ? 'opacity-100 pointer-events-auto'
                      : 'opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto',
                    'transition-opacity duration-200'
                  ]"
                  :aria-label="`在${group.workspace.name}新建对话`"
                  title="在此项目新建对话"
                  @click.stop="openCreateModal(group.workspace.id)"
                >
                  <Plus class="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <div v-if="!chatStore.collapsedWorkspaceIds[group.workspace.id]" class="pl-2 space-y-0.5 mb-1.5">
              <button
                v-if="group.conversations.length === 0 && !chatStore.showArchived"
                type="button"
                class="mx-1 mb-1 w-[calc(100%-0.5rem)] rounded-lg border border-dashed border-border px-3 py-2 text-left text-[11px] text-text-muted hover:border-primary/50 hover:text-primary transition-colors cursor-pointer"
                @click="openCreateModal(group.workspace.id)"
              >
                该项目暂无任务，点击新建
              </button>

              <div
                v-for="conversation in group.conversations"
                :key="conversation.id"
                role="button"
                tabindex="0"
                class="w-full text-left rounded-xl transition-all flex items-center justify-between gap-2 cursor-pointer group select-none min-h-[40px] px-2.5 py-1.5 my-0.5"
                :class="[
                  conversation.id === chatStore.activeConversationId
                    ? 'bg-muted/80 text-text font-medium'
                    : 'text-text-muted hover:text-text hover:bg-muted/30',
                ]"
                @click="handleConversationSelect(conversation.id)"
                @keydown.enter.prevent="handleConversationSelect(conversation.id)"
                @keydown.space.prevent="handleConversationSelect(conversation.id)"
              >
                <div class="min-w-0 flex-1 flex items-center gap-2">
                  <!-- Active Indicator Circle matching Image 3 -->
                  <span
                    v-if="conversation.id === chatStore.activeConversationId"
                    class="w-2.5 h-2.5 rounded-full border-2 border-text/90 shrink-0 inline-block ml-0.5"
                  />
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-1.5 flex-wrap">
                      <span
                        class="truncate text-xs leading-normal"
                        :class="conversation.id === chatStore.activeConversationId ? 'font-medium text-text' : 'text-text-muted group-hover:text-text'"
                      >
                        {{ conversation.title }}
                      </span>
                      <span v-if="conversation.conversationKind === 'native'" class="text-[10px] text-text-muted">
                        <RuntimeIcon :agent="conversation.agentType" class="inline-block w-3.5 h-3.5" />{{ agentLabel(conversation.agentType) }}
                      </span>
                      <span
                        v-if="conversation.authority === 'remote'"
                        class="shrink-0 text-[9px] px-1 py-0.2 rounded font-medium bg-primary/15 text-primary"
                      >
                        来自手机
                      </span>
                      <span
                        v-if="conversation.visibility === 'mobile_only'"
                        class="shrink-0 text-[9px] px-1 py-0.2 rounded font-medium bg-warning/15 text-warning"
                      >
                        已隐藏（仅手机）
                      </span>
                      <span
                        v-else-if="conversation.visibility === 'pc_only'"
                        class="shrink-0 text-[9px] px-1 py-0.2 rounded font-medium bg-muted text-text-muted"
                      >
                        仅电脑
                      </span>
                    </div>
                    <div class="mt-0.5 flex items-center gap-2 text-[10px] text-text-muted/70">
                      <span v-if="getStatusMeta(conversation)" class="inline-flex items-center gap-1">
                        <span class="w-1.5 h-1.5 rounded-full" :class="getStatusMeta(conversation)?.dot" />
                        {{ getStatusMeta(conversation)?.label }}
                      </span>
                      <span>{{ formatTime(conversation.updatedAt) }}</span>
                    </div>
                  </div>
                </div>

                <div class="shrink-0" @click.stop>
                  <HqDropdown :items="taskMenuItems(conversation)" placement="right">
                    <button
                      type="button"
                      class="w-6 h-6 rounded-md text-text-muted hover:text-text hover:bg-muted flex items-center justify-center transition-all cursor-pointer"
                      :class="conversation.id === chatStore.activeConversationId ? 'opacity-80 hover:opacity-100' : 'opacity-0 group-hover:opacity-80 hover:!opacity-100'"
                      title="任务操作"
                      aria-label="任务操作"
                    >
                      <MoreHorizontal class="w-3.5 h-3.5" />
                    </button>
                  </HqDropdown>
                </div>
              </div>
            </div>
          </div>
        </section>
      </template>
    </div>

    <!-- Create Project / Task Dialog (Image 1 Layout) -->
    <HqDialog
      :open="isNewConvModalOpen"
      :title="isWorkspaceLocked ? `新建对话 · ${lockedWorkspace?.name || '当前项目'}` : '创建项目'"
      :description="isWorkspaceLocked ? `在当前项目「${lockedWorkspace?.name || '当前项目'}」下创建新对话` : '创建独立任务对话并配置工作区与初始场景（不立即执行模型）'"
      @close="isNewConvModalOpen = false"
    >
      <form v-if="!isWorkspaceLocked" class="space-y-4 py-2 text-xs" @submit.prevent="handleCreateConversation">
        <span class="sr-only">新建任务</span>
        <p v-if="createError" role="alert" class="text-danger bg-danger/10 p-2 rounded">{{ createError }}</p>
        <div>
          <div class="flex items-center justify-between mb-1.5">
            <label class="block font-medium text-text">项目名称 <span class="sr-only">任务标题</span> <span class="text-danger">*</span></label>
            <span class="text-[11px] text-text-muted font-mono">{{ (newTitle || '').length }}/80</span>
          </div>
          <HqInput
            v-model="newTitle"
            placeholder="给项目起一个名字"
            maxlength="80"
            autofocus
          />
        </div>
        <div>
          <label class="block font-medium text-text mb-1.5">来源</label>
          <div class="grid grid-cols-2 gap-2">
            <button
              type="button"
              class="flex items-center justify-center gap-2 p-2 rounded-lg border text-xs font-medium transition-all cursor-pointer"
              :class="projectSource === 'local' ? 'border-primary bg-primary/10 text-primary shadow-xs' : 'border-border bg-bg-app text-text hover:bg-muted/40'"
              @click="projectSource = 'local'"
            >
              <Laptop class="w-4 h-4" />
              <span>此电脑</span>
            </button>
            <button
              type="button"
              class="flex items-center justify-center gap-2 p-2 rounded-lg border text-xs font-medium transition-all cursor-pointer"
              :class="projectSource === 'git' ? 'border-primary bg-primary/10 text-primary shadow-xs' : 'border-border bg-bg-app text-text hover:bg-muted/40'"
              @click="projectSource = 'git'"
            >
              <GitBranch class="w-4 h-4" />
              <span>Git 仓库</span>
            </button>
          </div>
        </div>

        <div v-if="projectSource === 'local'" class="space-y-2">
          <label class="block font-medium text-text mb-1">工作区 <span class="text-danger">*</span></label>
          <HqButton
            type="button"
            size="sm"
            variant="secondary"
            class="w-full justify-start font-normal h-9"
            :loading="isPicking"
            :disabled="isPicking || isRegistering"
            @click="chooseWorkspace"
          >
            <FolderPlus class="w-4 h-4 mr-1.5 text-primary" />
            <span class="truncate">{{ selectedFolderPath ? selectedFolderPath : '添加文件夹 · 选择项目目录' }}</span>
          </HqButton>

          <div v-if="chatStore.workspaces.length > 0" class="pt-1">
            <label class="block text-[11px] text-text-muted mb-1">或选择已登记工作区：</label>
            <HqSelect
              v-model="selectedWorkspaceId"
              :options="chatStore.workspaces.map((workspace) => ({ label: `${workspace.name} (${workspace.path})`, value: workspace.id }))"
              placeholder="请选择已登记的工作区"
            />
          </div>

          <details class="text-[11px]" :open="!!newWorkspacePath">
            <summary class="cursor-pointer text-text-muted hover:text-text">手动输入目录</summary>
            <div class="flex items-center gap-2 mt-1.5">
              <HqInput v-model="newWorkspacePath" placeholder="例如 E:\WorkSpace\ua_android" class="flex-1" />
              <HqButton type="button" size="sm" :disabled="!newWorkspacePath.trim() || isRegistering || isPicking" @click="registerWorkspace">登记目录</HqButton>
            </div>
          </details>
        </div>

        <div v-else class="space-y-2">
          <label class="block font-medium text-text mb-1">Git 仓库地址 <span class="text-danger">*</span></label>
          <HqInput v-model="gitRepoUrl" placeholder="https://github.com/owner/repo.git" />
          <p class="text-[11px] text-text-muted">克隆到本机工作区后将自动登记为项目。</p>
        </div>

        <div>
          <label class="block font-medium text-text mb-1.5">初始场景 <span class="text-danger">*</span></label>
          <div class="grid grid-cols-3 gap-2">
            <button
              v-for="scene in chatStore.scenes"
              :key="scene.id"
              type="button"
              class="p-2.5 rounded-[var(--radius-sm)] border text-left transition-all cursor-pointer"
              :class="selectedSceneId === scene.id ? 'border-primary bg-primary/10 text-primary shadow-sm' : 'border-border bg-bg-app text-text hover:border-border-hover'"
              @click="selectedSceneId = scene.id"
            >
              <div class="font-medium text-xs mb-0.5">{{ scene.name }}</div>
              <div class="text-[10px] text-text-muted leading-tight line-clamp-2">{{ scene.description }}</div>
            </button>
          </div>
        </div>
      </form>

      <form v-else class="space-y-4 py-2 text-xs" @submit.prevent="handleCreateConversation">
        <p v-if="createError" role="alert" class="text-danger bg-danger/10 p-2 rounded">{{ createError }}</p>
        <div>
          <label class="block font-medium text-text mb-1.5">对话标题 <span class="text-danger">*</span></label>
          <HqInput v-model="newTitle" placeholder="例如：梳理登录鉴权与连接链路..." autofocus />
        </div>
        <div>
          <label class="block font-medium text-text mb-1.5">所属项目 <span class="text-danger">*</span></label>
          <HqSelect
            v-model="selectedWorkspaceId"
            :options="chatStore.workspaces.map((workspace) => ({ label: `${workspace.name} (${workspace.path})`, value: workspace.id }))"
            placeholder="请选择已登记的工作区"
            :disabled="true"
          />
          <p class="text-[11px] text-text-muted mt-1.5 flex items-center gap-1">
            <Folder class="w-3.5 h-3.5 text-primary/80 shrink-0" />
            <span>已锁定当前项目，直接创建该项目下的新对话。</span>
          </p>
        </div>
        <div>
          <label class="block font-medium text-text mb-1.5">初始场景 <span class="text-danger">*</span></label>
          <div class="grid grid-cols-3 gap-2">
            <button
              v-for="scene in chatStore.scenes"
              :key="scene.id"
              type="button"
              class="p-2.5 rounded-[var(--radius-sm)] border text-left transition-all cursor-pointer"
              :class="selectedSceneId === scene.id ? 'border-primary bg-primary/10 text-primary shadow-sm' : 'border-border bg-bg-app text-text hover:border-border-hover'"
              @click="selectedSceneId = scene.id"
            >
              <div class="font-medium text-xs mb-0.5">{{ scene.name }}</div>
              <div class="text-[10px] text-text-muted leading-tight line-clamp-2">{{ scene.description }}</div>
            </button>
          </div>
        </div>
      </form>

      <template #footer>
        <HqButton size="sm" variant="secondary" @click="isNewConvModalOpen = false">取消</HqButton>
        <HqButton
          size="sm"
          variant="primary"
          :disabled="(!newTitle.trim() && !selectedWorkspaceId) || isCreating"
          :loading="isCreating"
          @click="handleCreateConversation"
        >
          {{ isWorkspaceLocked ? '创建对话' : '创建项目' }}
          <span class="sr-only">创建任务</span>
        </HqButton>
      </template>
    </HqDialog>

    <HqDialog
      :open="isRenameDialogOpen"
      title="重命名任务"
      description="只修改任务显示名称，不影响历史消息与 Session"
      @close="isRenameDialogOpen = false"
    >
      <div class="space-y-2 text-xs">
        <HqInput v-model="renameTitle" autofocus @keydown.enter.prevent="confirmRename" />
        <p v-if="renameError" role="alert" class="text-danger">{{ renameError }}</p>
      </div>
      <template #footer>
        <HqButton size="sm" variant="secondary" @click="isRenameDialogOpen = false">取消</HqButton>
        <HqButton size="sm" variant="primary" :disabled="!renameTitle.trim() || chatStore.isMetadataUpdating" :loading="chatStore.isMetadataUpdating" @click="confirmRename">保存名称</HqButton>
      </template>
    </HqDialog>

    <HqDialog
      :open="isArchiveDialogOpen"
      title="归档任务"
      description="归档后仍可查看全部记录"
      @close="isArchiveDialogOpen = false"
    >
      <p class="text-xs text-text leading-relaxed">
        归档「{{ archiveTarget?.title }}」后将切换为只读。需要继续发送、重试或恢复执行时，请先从“已归档”中恢复任务。
      </p>
      <template #footer>
        <HqButton size="sm" variant="secondary" @click="isArchiveDialogOpen = false">取消</HqButton>
        <HqButton size="sm" variant="danger" :disabled="chatStore.isMetadataUpdating" :loading="chatStore.isMetadataUpdating" @click="confirmArchive">确认归档</HqButton>
      </template>
    </HqDialog>

    <HqDialog
      :open="isVisibilityDialogOpen"
      title="可见性设置"
      description="选择该对话在电脑与手机端的可见范围"
      @close="isVisibilityDialogOpen = false"
    >
      <div class="space-y-3 py-2 text-xs">
        <p v-if="visibilityError" role="alert" class="text-danger bg-danger/10 p-2 rounded">{{ visibilityError }}</p>
        <div class="space-y-2">
          <label
            class="flex items-start gap-2.5 p-2.5 rounded-lg border cursor-pointer transition-colors"
            :class="selectedVisibility === 'both' ? 'border-primary bg-primary/5' : 'border-border hover:bg-bg-app'"
          >
            <input
              type="radio"
              v-model="selectedVisibility"
              value="both"
              name="visibility"
              class="hq-form-choice mt-0.5"
            />
            <div>
              <p class="font-medium text-text">两端均可见 (默认)</p>
              <p class="text-[11px] text-text-muted">电脑端与手机端均可查看并参与对话</p>
            </div>
          </label>
          <label
            class="flex items-start gap-2.5 p-2.5 rounded-lg border cursor-pointer transition-colors"
            :class="selectedVisibility === 'pc_only' ? 'border-primary bg-primary/5' : 'border-border hover:bg-bg-app'"
          >
            <input
              type="radio"
              v-model="selectedVisibility"
              value="pc_only"
              name="visibility"
              class="hq-form-choice mt-0.5"
            />
            <div>
              <p class="font-medium text-text">仅电脑可见</p>
              <p class="text-[11px] text-text-muted">手机端列表中不显示此对话</p>
            </div>
          </label>
          <label
            class="flex items-start gap-2.5 p-2.5 rounded-lg border cursor-pointer transition-colors"
            :class="selectedVisibility === 'mobile_only' ? 'border-primary bg-primary/5' : 'border-border hover:bg-bg-app'"
          >
            <input
              type="radio"
              v-model="selectedVisibility"
              value="mobile_only"
              name="visibility"
              class="hq-form-choice mt-0.5"
            />
            <div>
              <p class="font-medium text-text">仅手机可见</p>
              <p class="text-[11px] text-text-muted">电脑端默认隐藏（勾选“显示已隐藏的对话”时可见）</p>
            </div>
          </label>
        </div>
      </div>
      <template #footer>
        <HqButton size="sm" variant="secondary" @click="isVisibilityDialogOpen = false">取消</HqButton>
        <HqButton
          size="sm"
          variant="primary"
          :disabled="chatStore.isMetadataUpdating"
          :loading="chatStore.isMetadataUpdating"
          @click="confirmVisibility"
        >
          保存设置
        </HqButton>
      </template>
    </HqDialog>

    <!-- Sidebar bottom toolbar (Settings, Archive, Mobile connection, Theme toggle, Version) matching Image 4 -->
    <div class="px-3 py-2 border-t border-border/30 flex items-center justify-between text-xs shrink-0 select-none">
      <div class="flex items-center gap-1">
        <!-- Settings button -->
        <button
          type="button"
          class="w-7 h-7 rounded-lg flex items-center justify-center text-text-muted hover:text-text hover:bg-muted/60 transition-colors cursor-pointer"
          title="系统设置"
          aria-label="系统设置"
          @click="navigateToSettings"
        >
          <Settings class="w-4 h-4" />
        </button>

        <!-- Archive button matching user requirement -->
        <button
          type="button"
          data-testid="sidebar-archived-toggle"
          class="w-7 h-7 rounded-lg flex items-center justify-center transition-colors cursor-pointer"
          :class="chatStore.showArchived ? 'bg-primary/15 text-primary' : 'text-text-muted hover:text-text hover:bg-muted/60'"
          :title="chatStore.showArchived ? '已归档（点击退出归档视图）' : '查看已归档任务'"
          aria-label="已归档"
          @click="toggleArchivedView"
        >
          <Archive class="w-4 h-4" />
          <span class="sr-only">已归档</span>
        </button>

        <!-- Mobile Link button with connection dot and accessible test status -->
        <button
          type="button"
          data-testid="sidebar-mobile-link-status"
          class="relative w-7 h-7 rounded-lg flex items-center justify-center text-text-muted hover:text-text hover:bg-muted/60 transition-colors cursor-pointer"
          :title="isPhoneConnected ? '手机已连接（点击查看）' : '手机未连接（点击连接）'"
          aria-label="手机连接状态"
          @click="navigateToRemoteLink"
        >
          <Smartphone class="w-4 h-4" />
          <span
            class="absolute top-1 right-1 w-1.5 h-1.5 rounded-full transition-colors"
            :class="isPhoneConnected ? 'bg-success animate-pulse' : 'bg-text-muted/40'"
          />
          <span class="sr-only">手机连接状态 {{ isPhoneConnected ? '已连接' : '未连接' }}</span>
        </button>

        <!-- Day/Night theme toggle -->
        <button
          type="button"
          class="w-7 h-7 rounded-lg flex items-center justify-center text-text-muted hover:text-text hover:bg-muted/60 transition-colors cursor-pointer"
          :title="themeStore.settings.mode === 'dark' ? '切换亮色模式' : '切换暗色模式'"
          aria-label="切换主题模式"
          @click="toggleTheme"
        >
          <Sun v-if="themeStore.settings.mode === 'dark'" class="w-4 h-4" />
          <Moon v-else class="w-4 h-4" />
        </button>
      </div>

      <!-- Version & Indicator on right matching Image 4 -->
      <div class="flex items-center gap-1.5 text-[11px] font-mono text-text-muted/60">
        <span>v1.5.0</span>
        <span
          class="w-1.5 h-1.5 rounded-full"
          :class="isPhoneConnected ? 'bg-success' : 'bg-text-muted/40'"
          :title="isPhoneConnected ? '已连接' : '就绪'"
        />
      </div>
    </div>
  </aside>
</template>
