<script setup lang="ts">
import { ref } from 'vue'
import { useChatStore } from '@/stores/chat.store'
import type { LocalSceneId } from '@hqagent/protocol'
import {
  HqButton,
  HqInput,
  HqBadge,
  HqDialog,
  HqSelect,
} from '@/shared/ui'
import {
  Plus,
  Search,
  MessageSquare,
  Bot,
  FolderGit2,
} from 'lucide-vue-next'

const chatStore = useChatStore()

// New conversation dialog state
const isNewConvModalOpen = ref(false)
const newTitle = ref('')
const selectedWorkspaceId = ref('')
const selectedSceneId = ref<LocalSceneId>('analyze')
const isCreating = ref(false)
const newWorkspacePath = ref('')
const isRegistering = ref(false)
const createError = ref<string | null>(null)

function openCreateModal() {
  newTitle.value = ''
  selectedWorkspaceId.value = chatStore.workspaces[0]?.id || ''
  selectedSceneId.value = 'analyze'
  isNewConvModalOpen.value = true
  createError.value = null
}

async function handleCreateConversation() {
  if (!newTitle.value.trim() || !selectedWorkspaceId.value || isCreating.value) return
  isCreating.value = true
  try {
    await chatStore.createConversation(
      newTitle.value,
      selectedWorkspaceId.value,
      selectedSceneId.value
    )
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

function getSceneBadge(sceneId: string) {
  switch (sceneId) {
    case 'analyze':
      return { label: '代码分析', variant: 'info' as const }
    case 'plan':
      return { label: '需求规划', variant: 'primary' as const }
    case 'develop':
      return { label: '开发修复', variant: 'success' as const }
    default:
      return { label: sceneId, variant: 'neutral' as const }
  }
}


function formatTime(iso: string) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    const now = new Date()
    const isToday = d.toDateString() === now.toDateString()
    if (isToday) {
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
    return `${d.getMonth() + 1}/${d.getDate()}`
  } catch {
    return iso
  }
}
</script>

<template>
  <aside class="w-80 h-full border-r border-border bg-panel flex flex-col shrink-0 select-none">
    <!-- Header: Title & New button -->
    <div class="p-3.5 border-b border-border flex items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <Bot class="w-5 h-5 text-primary" />
        <h2 class="text-sm font-semibold text-text">本地对话</h2>
        <span class="text-[11px] text-text-muted bg-panel-header px-1.5 py-0.5 rounded">
          {{ chatStore.conversations.length }}
        </span>
      </div>

      <HqButton size="sm" variant="primary" @click="openCreateModal">
        <Plus class="w-3.5 h-3.5 mr-1" />
        新建
      </HqButton>
    </div>

    <!-- Search box -->
    <div class="p-3 border-b border-border">
      <div class="relative">
        <Search class="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
        <input
          v-model="chatStore.searchQuery"
          type="text"
          placeholder="搜索对话、项目或场景..."
          class="w-full pl-8 pr-2.5 py-1.5 text-xs bg-bg-app border border-border rounded-[var(--radius-sm)] text-text placeholder-text-muted/60 focus:outline-none focus:border-primary transition-colors"
        />
      </div>
    </div>

    <!-- Conversations list -->
    <div class="flex-1 overflow-y-auto divide-y divide-border/50">
      <div
        v-if="chatStore.filteredConversations.length === 0"
        class="p-6 text-center text-xs text-text-muted"
      >
        <MessageSquare class="w-8 h-8 mx-auto mb-2 text-text-muted/40" />
        <p>暂无匹配对话</p>
        <button
          type="button"
          class="mt-2 text-primary hover:underline"
          @click="openCreateModal"
        >
          创建首个对话
        </button>
      </div>

      <div
        v-for="conv in chatStore.filteredConversations"
        :key="conv.id"
        class="p-3 cursor-pointer transition-colors hover:bg-panel-hover"
        :class="{
          'bg-primary/5 border-l-2 border-primary': chatStore.activeConversationId === conv.id,
        }"
        @click="chatStore.selectConversation(conv.id)"
      >
        <div class="flex items-start justify-between gap-2 mb-1">
          <h3 class="text-xs font-medium text-text truncate leading-tight flex-1">
            {{ conv.title }}
          </h3>
          <span class="text-[10px] text-text-muted shrink-0">
            {{ formatTime(conv.updatedAt) }}
          </span>
        </div>

        <div class="flex items-center gap-1.5 text-[11px] text-text-muted mb-1.5 truncate">
          <FolderGit2 class="w-3 h-3 shrink-0" />
          <span class="truncate">
            {{ chatStore.workspaces.find((w) => w.id === conv.workspaceId)?.name || '未指定工作区' }}
          </span>
        </div>

        <div class="flex items-center justify-between gap-1.5">
          <HqBadge
            :variant="getSceneBadge(conv.sceneId).variant"
            size="sm"
            class="text-[10px]"
          >
            {{ getSceneBadge(conv.sceneId).label }}
          </HqBadge>

          <span
            v-if="conv.activeRunId"
            class="inline-flex items-center gap-1 text-[10px] text-primary animate-pulse font-medium"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-primary animate-ping" />
            执行中
          </span>
        </div>
      </div>
    </div>

    <!-- New Conversation Modal (Does NOT immediately run model, only registers config) -->
    <HqDialog
      :open="isNewConvModalOpen"
      title="新建对话"
      description="配置对话目标、授权工作区与初始场景（不立即执行模型）"
      @close="isNewConvModalOpen = false"
    >
      <form class="space-y-4 py-2 text-xs" @submit.prevent="handleCreateConversation">
        <p v-if="createError" role="alert" class="text-danger bg-danger/10 p-2 rounded">{{ createError }}</p>
        <div>
          <label class="block font-medium text-text mb-1.5">
            对话标题 <span class="text-danger">*</span>
          </label>
          <HqInput
            v-model="newTitle"
            placeholder="例如：梳理登录鉴权与连接链路..."
            autofocus
          />
        </div>

        <div>
          <label class="block font-medium text-text mb-1.5">
            目标项目 / 工作区 <span class="text-danger">*</span>
          </label>
          <HqSelect
            v-model="selectedWorkspaceId"
            :options="
              chatStore.workspaces.map((w) => ({
                label: `${w.name} (${w.path})`,
                value: w.id,
              }))
            "
            placeholder="请选择已登记的工作区"
          />
          <details class="mt-2" :open="chatStore.workspaces.length === 0">
            <summary class="cursor-pointer text-primary">登记本机已有项目目录</summary>
            <div class="flex items-center gap-2 mt-2">
              <HqInput v-model="newWorkspacePath" placeholder="例如 E:\WorkSpace\ua_android" class="flex-1" />
              <HqButton type="button" size="sm" :disabled="!newWorkspacePath.trim() || isRegistering" @click="registerWorkspace">登记目录</HqButton>
            </div>
          </details>
        </div>

        <div>
          <label class="block font-medium text-text mb-1.5">
            初始场景 <span class="text-danger">*</span>
          </label>
          <div class="grid grid-cols-3 gap-2">
            <button
              type="button"
              class="p-2.5 rounded-[var(--radius-sm)] border text-left transition-all"
              :class="
                selectedSceneId === 'analyze'
                  ? 'border-primary bg-primary/10 text-primary font-medium shadow-sm'
                  : 'border-border bg-bg-app text-text hover:border-border-hover'
              "
              @click="selectedSceneId = 'analyze'"
            >
              <div class="font-medium text-xs mb-0.5">代码分析</div>
              <div class="text-[10px] text-text-muted leading-tight">只读梳理代码与依赖</div>
            </button>

            <button
              type="button"
              class="p-2.5 rounded-[var(--radius-sm)] border text-left transition-all"
              :class="
                selectedSceneId === 'plan'
                  ? 'border-primary bg-primary/10 text-primary font-medium shadow-sm'
                  : 'border-border bg-bg-app text-text hover:border-border-hover'
              "
              @click="selectedSceneId = 'plan'"
            >
              <div class="font-medium text-xs mb-0.5">需求规划</div>
              <div class="text-[10px] text-text-muted leading-tight">分析需求输出落地方案</div>
            </button>

            <button
              type="button"
              class="p-2.5 rounded-[var(--radius-sm)] border text-left transition-all"
              :class="
                selectedSceneId === 'develop'
                  ? 'border-primary bg-primary/10 text-primary font-medium shadow-sm'
                  : 'border-border bg-bg-app text-text hover:border-border-hover'
              "
              @click="selectedSceneId = 'develop'"
            >
              <div class="font-medium text-xs mb-0.5">开发修复</div>
              <div class="text-[10px] text-text-muted leading-tight">隔离工作树编码与验证</div>
            </button>
          </div>
        </div>
      </form>

      <template #footer>
        <div class="flex items-center justify-end gap-2">
          <HqButton size="sm" variant="secondary" @click="isNewConvModalOpen = false">
            取消
          </HqButton>
          <HqButton
            size="sm"
            variant="primary"
            :disabled="!newTitle.trim() || !selectedWorkspaceId || isCreating"
            :loading="isCreating"
            @click="handleCreateConversation"
          >
            创建对话
          </HqButton>
        </div>
      </template>
    </HqDialog>
  </aside>
</template>
