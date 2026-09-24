<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useChatStore } from '@/stores/chat.store'
import { useLocalAuthStore } from '@/stores/local-auth.store'
import ChatSidebar from './components/ChatSidebar.vue'
import ChatMessageItem from './components/ChatMessageItem.vue'
import ChatComposer from './components/ChatComposer.vue'
import RunSnapshotDrawer from './components/RunSnapshotDrawer.vue'
import {
  HqBadge,
  HqEmptyState,
} from '@/shared/ui'
import {
  Bot,
  FolderGit2,
  PanelRightClose,
  PanelRightOpen,
  Radio,
} from 'lucide-vue-next'

const chatStore = useChatStore()
const authStore = useLocalAuthStore()

const isDrawerOpen = ref(true)
const messageContainerRef = ref<HTMLElement | null>(null)

onMounted(async () => {
  await chatStore.init()
  chatStore.startPolling()
  scrollToBottom()
})

onUnmounted(() => {
  chatStore.stopPolling()
})

// Auto scroll on new messages
watch(
  () => chatStore.messages.length,
  async () => {
    await nextTick()
    scrollToBottom()
  }
)

function scrollToBottom() {
  if (messageContainerRef.value) {
    messageContainerRef.value.scrollTop = messageContainerRef.value.scrollHeight
  }
}

function getSceneLabel(sceneId?: string) {
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
</script>

<template>
  <div class="h-full flex flex-col bg-bg-app overflow-hidden">
    <!-- Mock Mode Warning Banner if active -->
    <div
      v-if="authStore.isMockMode"
      class="px-4 py-1.5 bg-warning/15 border-b border-warning/30 flex items-center justify-between text-xs text-text"
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
        class="text-[11px] text-primary underline hover:text-primary-hover font-medium"
        @click="authStore.setGatewayMode('real')"
      >
        切回真实 Worker
      </button>
    </div>

    <!-- 3-Column Workbench -->
    <div class="flex-1 min-h-0 flex overflow-hidden">
      <!-- Left Column: Conversations Sidebar -->
      <ChatSidebar />

      <!-- Center Column: Active Chat Stream & Composer -->
      <main class="flex-1 flex flex-col h-full bg-bg-app min-w-0 overflow-hidden">
        <!-- Center Header -->
        <header class="p-3 border-b border-border bg-panel flex items-center justify-between gap-3 shrink-0">
          <div v-if="chatStore.activeConversation" class="flex items-center gap-2.5 min-w-0">
            <h1 class="text-sm font-semibold text-text truncate">
              {{ chatStore.activeConversation.title }}
            </h1>

            <HqBadge size="sm" variant="info" class="text-[10px] shrink-0">
              {{ getSceneLabel(chatStore.activeConversation.sceneId) }}
            </HqBadge>

            <div class="hidden md:flex items-center gap-1 text-xs text-text-muted shrink-0">
              <FolderGit2 class="w-3.5 h-3.5" />
              <span>
                {{ chatStore.workspaces.find((w) => w.id === chatStore.activeConversation?.workspaceId)?.name }}
              </span>
            </div>
          </div>

          <div v-else class="text-xs text-text-muted font-medium">
            未选择对话
          </div>

          <!-- Drawer Toggle -->
          <div class="flex items-center gap-1.5 shrink-0">
            <button
              type="button"
              class="p-1.5 rounded hover:bg-panel-hover text-text-muted hover:text-text transition-colors flex items-center gap-1 text-xs"
              :title="isDrawerOpen ? '收起详情抽屉' : '展开详情抽屉'"
              @click="isDrawerOpen = !isDrawerOpen"
            >
              <PanelRightClose v-if="isDrawerOpen" class="w-4 h-4 text-primary" />
              <PanelRightOpen v-else class="w-4 h-4" />
              <span class="hidden sm:inline text-[11px] text-text-muted">执行详情</span>
            </button>
          </div>
        </header>

        <!-- Message Stream View -->
        <div
          v-if="chatStore.activeConversation"
          ref="messageContainerRef"
          class="flex-1 min-h-0 overflow-y-auto divide-y divide-border/30"
        >
          <div
            v-if="chatStore.messages.length === 0"
            class="h-full flex flex-col items-center justify-center p-8 text-center"
          >
            <Bot class="w-10 h-10 text-primary/40 mb-3" />
            <h3 class="text-sm font-medium text-text mb-1">
              对话已就绪，等待下发目标
            </h3>
            <p class="text-xs text-text-muted max-w-sm leading-relaxed mb-4">
              场景「{{ getSceneLabel(chatStore.activeConversation.sceneId) }}」已锁定角色配置。在下方输入框中描述您的任务即可开始执行。
            </p>
          </div>

          <ChatMessageItem
            v-for="msg in chatStore.messages"
            :key="msg.id"
            :message="msg"
          />
        </div>

        <div v-else class="flex-1 min-h-0 flex items-center justify-center p-8">
          <HqEmptyState
            title="选择或新建一个本地对话"
            description="从左侧选择已有任务，或点击「新建」配置项目与角色场景开始协作"
          />
        </div>

        <!-- Composer Footer -->
        <ChatComposer v-if="chatStore.activeConversation" />
      </main>

      <!-- Right Column: Run Snapshot & Artifacts & Roles Drawer -->
      <RunSnapshotDrawer
        v-if="isDrawerOpen"
        @close="isDrawerOpen = false"
      />
    </div>
  </div>
</template>
