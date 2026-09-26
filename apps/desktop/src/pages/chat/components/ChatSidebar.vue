<script setup lang="ts">
import { ref } from 'vue'
import type { LocalConversationView, LocalSceneId, TaskStatus } from '@hqagent/protocol'
import { useChatStore } from '@/stores/chat.store'
import { HqButton, HqDialog, HqDropdown, HqInput, HqSelect } from '@/shared/ui'
import {
  Archive,
  ArchiveRestore,
  Bot,
  ChevronDown,
  ChevronRight,
  FolderGit2,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  X,
} from 'lucide-vue-next'

const emit = defineEmits<{
  (e: 'select', id: string): void
  (e: 'close'): void
}>()

const chatStore = useChatStore()

const isNewConvModalOpen = ref(false)
const newTitle = ref('')
const selectedWorkspaceId = ref('')
const selectedSceneId = ref<LocalSceneId>('analyze')
const isCreating = ref(false)
const newWorkspacePath = ref('')
const isRegistering = ref(false)
const isPicking = ref(false)
const createError = ref<string | null>(null)

const isRenameDialogOpen = ref(false)
const renameTarget = ref<LocalConversationView | null>(null)
const renameTitle = ref('')
const renameError = ref<string | null>(null)

const isArchiveDialogOpen = ref(false)
const archiveTarget = ref<LocalConversationView | null>(null)

function openCreateModal(workspaceId?: string) {
  newTitle.value = ''
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
  if (!newTitle.value.trim() || !selectedWorkspaceId.value || isCreating.value) return
  isCreating.value = true
  createError.value = null
  try {
    await chatStore.createConversation(newTitle.value, selectedWorkspaceId.value, selectedSceneId.value)
    isNewConvModalOpen.value = false
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '创建对话失败'
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
  if (conversation.archived) {
    return [{
      id: 'restore',
      label: '恢复任务',
      icon: ArchiveRestore,
      action: () => restoreConversation(conversation),
    }]
  }
  const canArchive = chatStore.canArchiveConversation(conversation)
  return [
    {
      id: 'rename',
      label: '重命名',
      icon: Pencil,
      action: () => openRenameDialog(conversation),
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
  <aside class="w-[85vw] max-w-[320px] md:w-72 lg:w-80 h-full border-r border-border bg-panel flex flex-col shrink-0 select-none">
    <div class="p-3.5 border-b border-border flex items-center justify-between gap-2">
      <div class="flex items-center gap-2 min-w-0">
        <Bot class="w-5 h-5 text-primary shrink-0" />
        <h2 class="text-sm font-semibold text-text truncate">项目任务</h2>
        <span class="text-[11px] text-text-muted bg-panel-header px-1.5 py-0.5 rounded">
          {{ chatStore.filteredConversations.length }}
        </span>
      </div>
      <div class="flex items-center gap-1 shrink-0">
        <HqButton size="sm" variant="primary" class="min-h-[44px] min-w-[44px]" @click="openCreateModal()">
          <Plus class="w-3.5 h-3.5 mr-1" />
          新建任务
        </HqButton>

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

    <div class="p-3 pb-2 border-b border-border space-y-2">
      <div class="relative">
        <Search class="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
        <input
          v-model="chatStore.searchQuery"
          type="text"
          placeholder="搜索任务或项目..."
          class="w-full pl-8 pr-2.5 py-1.5 text-xs bg-bg-app border border-border rounded-[var(--radius-sm)] text-text placeholder-text-muted/60 focus:outline-none focus:border-primary transition-colors"
        />
      </div>
      <div class="grid grid-cols-2 gap-1 rounded-lg bg-bg-app p-1 text-[11px]">
        <button
          type="button"
          class="rounded-md px-2 py-1 transition-colors"
          :class="!chatStore.showArchived ? 'bg-panel text-text shadow-xs' : 'text-text-muted hover:text-text'"
          @click="chatStore.showArchived = false"
        >
          当前任务
        </button>
        <button
          type="button"
          class="rounded-md px-2 py-1 transition-colors"
          :class="chatStore.showArchived ? 'bg-panel text-text shadow-xs' : 'text-text-muted hover:text-text'"
          @click="chatStore.showArchived = true"
        >
          已归档
        </button>
      </div>
      <p v-if="chatStore.metadataError" role="alert" class="text-[11px] text-danger leading-relaxed">
        {{ chatStore.metadataError }}
      </p>
    </div>

    <div class="flex-1 overflow-y-auto py-1.5">
      <div
        v-if="chatStore.groupedConversations.length === 0"
        class="p-6 text-center text-xs text-text-muted"
      >
        <MessageSquare class="w-8 h-8 mx-auto mb-2 text-text-muted/40" />
        <p>暂无匹配项目或任务</p>
      </div>

      <section
        v-for="group in chatStore.groupedConversations"
        :key="group.workspace.id"
        class="border-b border-border/50 last:border-b-0"
      >
        <div class="flex items-center gap-1.5 px-2.5 py-2 text-xs text-text-muted hover:bg-panel-hover/60">
          <button
            type="button"
            class="p-0.5 rounded hover:bg-bg-app shrink-0"
            :title="chatStore.collapsedWorkspaceIds[group.workspace.id] ? '展开项目' : '折叠项目'"
            @click="chatStore.toggleWorkspaceCollapsed(group.workspace.id)"
          >
            <ChevronRight v-if="chatStore.collapsedWorkspaceIds[group.workspace.id]" class="w-3.5 h-3.5" />
            <ChevronDown v-else class="w-3.5 h-3.5" />
          </button>
          <FolderGit2 class="w-3.5 h-3.5 shrink-0 text-primary/80" />
          <div class="min-w-0 flex-1" :title="group.workspace.path">
            <p class="font-medium text-text truncate">{{ group.workspace.name }}</p>
            <p class="text-[10px] truncate opacity-70">{{ group.workspace.path }}</p>
          </div>
          <span class="text-[10px] tabular-nums">{{ group.conversations.length }}</span>
          <button
            type="button"
            class="p-1 rounded hover:bg-bg-app hover:text-primary"
            title="在此项目新建任务"
            @click="openCreateModal(group.workspace.id)"
          >
            <Plus class="w-3.5 h-3.5" />
          </button>
        </div>

        <div v-if="!chatStore.collapsedWorkspaceIds[group.workspace.id]" class="pb-1.5">
          <button
            v-if="group.conversations.length === 0 && !chatStore.showArchived"
            type="button"
            class="mx-3 mb-1 w-[calc(100%-1.5rem)] rounded-lg border border-dashed border-border px-3 py-2 text-left text-[11px] text-text-muted hover:border-primary/50 hover:text-primary transition-colors"
            @click="openCreateModal(group.workspace.id)"
          >
            该项目暂无任务，点击新建
          </button>

          <div
            v-for="conversation in group.conversations"
            :key="conversation.id"
            role="button"
            tabindex="0"
            class="group mx-1.5 rounded-lg px-2.5 py-2 cursor-pointer transition-colors hover:bg-panel-hover min-h-[44px] flex flex-col justify-center"
            :class="chatStore.activeConversationId === conversation.id ? 'bg-primary/10 text-text' : ''"
            @click="handleConversationSelect(conversation.id)"
            @keydown.enter.prevent="handleConversationSelect(conversation.id)"
            @keydown.space.prevent="handleConversationSelect(conversation.id)"
          >
            <div class="flex items-start gap-2">
              <div class="min-w-0 flex-1">
                <p class="text-xs font-medium text-text truncate leading-tight">{{ conversation.title }}</p>
                <div class="mt-1.5 flex items-center gap-2 text-[10px] text-text-muted">
                  <span v-if="getStatusMeta(conversation)" class="inline-flex items-center gap-1">
                    <span class="w-1.5 h-1.5 rounded-full" :class="getStatusMeta(conversation)?.dot" />
                    {{ getStatusMeta(conversation)?.label }}
                  </span>
                  <span>{{ formatTime(conversation.updatedAt) }}</span>
                </div>
              </div>
              <div class="shrink-0" @click.stop>
                <HqDropdown :items="taskMenuItems(conversation)" placement="right">
                  <button
                    type="button"
                    class="min-w-[44px] min-h-[44px] -m-1.5 p-2 rounded-lg text-text-muted opacity-60 group-hover:opacity-100 hover:bg-bg-app hover:text-text flex items-center justify-center cursor-pointer transition-colors"
                    title="任务操作"
                    aria-label="任务操作"
                  >
                    <MoreHorizontal class="w-4 h-4" />
                  </button>
                </HqDropdown>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>

    <HqDialog
      :open="isNewConvModalOpen"
      title="新建任务"
      description="创建独立任务对话并配置工作区与初始场景（不立即执行模型）"
      @close="isNewConvModalOpen = false"
    >
      <form class="space-y-4 py-2 text-xs" @submit.prevent="handleCreateConversation">
        <p v-if="createError" role="alert" class="text-danger bg-danger/10 p-2 rounded">{{ createError }}</p>
        <div>
          <label class="block font-medium text-text mb-1.5">任务标题 <span class="text-danger">*</span></label>
          <HqInput v-model="newTitle" placeholder="例如：梳理登录鉴权与连接链路..." autofocus />
        </div>
        <div>
          <label class="block font-medium text-text mb-1.5">目标项目 / 工作区 <span class="text-danger">*</span></label>
          <HqSelect
            v-model="selectedWorkspaceId"
            :options="chatStore.workspaces.map((workspace) => ({ label: `${workspace.name} (${workspace.path})`, value: workspace.id }))"
            placeholder="请选择已登记的工作区"
          />
          <HqButton type="button" size="sm" class="mt-2" :loading="isPicking" :disabled="isPicking || isRegistering" @click="chooseWorkspace">
            <FolderGit2 class="w-3.5 h-3.5 mr-1" />
            {{ isPicking ? '请在本机窗口中选择…' : '选择项目目录' }}
          </HqButton>
          <details class="mt-2" :open="!!newWorkspacePath">
            <summary class="cursor-pointer text-text-muted">手动输入目录</summary>
            <div class="flex items-center gap-2 mt-2">
              <HqInput v-model="newWorkspacePath" placeholder="例如 E:\WorkSpace\ua_android" class="flex-1" />
              <HqButton type="button" size="sm" :disabled="!newWorkspacePath.trim() || isRegistering || isPicking" @click="registerWorkspace">登记目录</HqButton>
            </div>
          </details>
        </div>
        <div>
          <label class="block font-medium text-text mb-1.5">初始场景 <span class="text-danger">*</span></label>
          <div class="grid grid-cols-3 gap-2">
            <button
              v-for="scene in chatStore.scenes"
              :key="scene.id"
              type="button"
              class="p-2.5 rounded-[var(--radius-sm)] border text-left transition-all"
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
        <HqButton size="sm" variant="primary" :disabled="!newTitle.trim() || !selectedWorkspaceId || isCreating" :loading="isCreating" @click="handleCreateConversation">创建任务</HqButton>
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
  </aside>
</template>
