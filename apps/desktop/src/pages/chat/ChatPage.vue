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
  Sparkles,
  ArrowDown,
} from 'lucide-vue-next'

const chatStore = useChatStore()
const authStore = useLocalAuthStore()

const isDrawerOpen = ref(true)
const messageContainerRef = ref<HTMLElement | null>(null)
const isScrolledUp = ref(false)

onMounted(async () => {
  await chatStore.init()
  chatStore.startPolling()
  scrollToBottom()
})

onUnmounted(() => {
  chatStore.stopPolling()
})

function handleScroll() {
  if (!messageContainerRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = messageContainerRef.value
  isScrolledUp.value = scrollHeight - scrollTop - clientHeight > 100
}

function scrollToBottom(smooth = false) {
  if (messageContainerRef.value) {
    if (smooth) {
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
  chatStore.sendMessage(prompt)
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg-app overflow-hidden">
    <!-- Load Error Alert -->
    <div
      v-if="'loadError' in chatStore && (chatStore as any).loadError"
      role="alert"
      class="px-4 py-2 text-xs text-danger bg-danger/10 border-b border-danger/20"
    >
      {{ (chatStore as any).loadError }}
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
    <div class="flex-1 min-h-0 flex overflow-hidden">
      <!-- Left Column: Conversations Sidebar -->
      <ChatSidebar />

      <!-- Center Column: Active Chat Stream & Composer -->
      <main class="flex-1 flex flex-col h-full bg-bg-app min-w-0 overflow-hidden">
        <!-- Center Header -->
        <header class="p-3 border-b border-border bg-panel flex items-center justify-between gap-3 shrink-0 select-none">
          <div v-if="chatStore.activeConversation" class="flex items-center gap-2.5 min-w-0">
            <h1 class="text-sm font-semibold text-text truncate">
              {{ chatStore.activeConversation.title }}
            </h1>

            <HqBadge size="sm" variant="info" class="text-[10px] shrink-0">
              {{ getSceneLabel(chatStore.activeConversation.sceneId) }}
            </HqBadge>

            <div class="hidden md:flex items-center gap-1 text-xs text-text-muted shrink-0">
              <FolderGit2 class="w-3.5 h-3.5" />
              <span class="truncate">
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
              class="p-1.5 px-2 rounded-lg hover:bg-panel-hover text-text-muted hover:text-text transition-colors flex items-center gap-1.5 text-xs cursor-pointer"
              :title="isDrawerOpen ? '收起详情抽屉' : '展开详情抽屉'"
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
            v-if="chatStore.activeConversation"
            ref="messageContainerRef"
            class="flex-1 min-h-0 overflow-y-auto divide-y divide-border/20 py-2"
            @scroll="handleScroll"
          >
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
              <p class="text-xs text-text-muted leading-relaxed mb-6">
                场景「{{ getSceneLabel(chatStore.activeConversation.sceneId) }}」已锁定角色配置。您可以直接在下方输入目标，或选择以下常用方向：
              </p>

              <div class="w-full space-y-2 text-left">
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
          </div>

          <div v-else class="flex-1 min-h-0 flex items-center justify-center p-8">
            <HqEmptyState
              title="选择或新建一个本地对话"
              description="从左侧选择已有任务，或点击「新建」配置项目与角色场景开始协作"
            />
          </div>

          <!-- Floating Jump to bottom button -->
          <div
            v-if="isScrolledUp && chatStore.activeConversation && chatStore.messages.length > 0"
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

        <!-- Floating Centered Composer Footer -->
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
