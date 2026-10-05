<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app.store'
import { useLocalAuthStore } from '@/stores/local-auth.store'
import {
  Bot,
  Sliders,
  FolderGit2,
  Smartphone,
  Terminal,
  ArrowLeft,
  Trash2,
  ArrowDown,
} from 'lucide-vue-next'
import { HqBadge } from '@/shared/ui'
import AgentsPage from '@/pages/agents/AgentsPage.vue'
import ScenesPage from '@/pages/scenes/ScenesPage.vue'
import AuthorizedRootsSettings from '@/pages/native/AuthorizedRootsSettings.vue'
import RemoteLinkPage from '@/pages/remote-link/RemoteLinkPage.vue'
import { useChatStore } from '@/stores/chat.store'

const props = withDefaults(
  defineProps<{
    initialTab?: string
  }>(),
  {
    initialTab: '',
  }
)

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const authStore = useLocalAuthStore()
const chatStore = useChatStore()

async function ensureWorkspacesLoaded() {
  if (chatStore.workspaces.length === 0) {
    try {
      await chatStore.init()
    } catch {
      // ignore
    }
  }
}

type TabKey = 'agents' | 'scenes' | 'workspaces' | 'remote-link' | 'about'

const tabs: { id: TabKey; label: string; icon: any; description: string }[] = [
  {
    id: 'agents',
    label: 'Agent 与模型',
    icon: Bot,
    description: '管理发现的 AI 智能体适配器、分配角色与图片能力验证',
  },
  {
    id: 'scenes',
    label: '场景与角色',
    icon: Sliders,
    description: '配置场景流程与角色模板，设定默认使用的 Agent',
  },
  {
    id: 'workspaces',
    label: '项目与授权目录',
    icon: FolderGit2,
    description: '管理本地工作区及允许手机远程访问的授权根目录',
  },
  {
    id: 'remote-link',
    label: '连接手机',
    icon: Smartphone,
    description: '管理与移动端 H5 的配对、安全同步与连接状态',
  },
  {
    id: 'about',
    label: '关于 / 日志',
    icon: Terminal,
    description: '查看系统运行状态、软件信息及实时系统事件日志流',
  },
]

function resolveCurrentTab(): TabKey {
  const queryTab = route.query.tab as string | undefined
  if (queryTab && tabs.some((t) => t.id === queryTab)) return queryTab as TabKey
  if (props.initialTab && tabs.some((t) => t.id === props.initialTab)) return props.initialTab as TabKey
  if (route.path.includes('scenes')) return 'scenes'
  if (route.path.includes('remote-link')) return 'remote-link'
  if (route.path.includes('workspaces')) return 'workspaces'
  return 'agents'
}

const activeTab = ref<TabKey>(resolveCurrentTab())

watch(
  () => [route.query.tab, props.initialTab, route.path],
  () => {
    activeTab.value = resolveCurrentTab()
  }
)

watch(
  () => activeTab.value,
  (tab) => {
    if (tab === 'workspaces') {
      void ensureWorkspacesLoaded()
    }
  },
  { immediate: true }
)

function setTab(tabId: TabKey) {
  activeTab.value = tabId
  void router.replace({
    path: '/settings',
    query: { ...route.query, tab: tabId },
  })
}

// About / Logs tab internal state
const logListRef = ref<HTMLElement | null>(null)
const selectedLogLevel = ref<'all' | 'info' | 'warn' | 'error'>('all')

const filteredLogs = computed(() => {
  if (selectedLogLevel.value === 'all') return appStore.logs
  return appStore.logs.filter((log) => log.level.toLowerCase() === selectedLogLevel.value)
})

watch(
  () => appStore.logs.length,
  () => {
    if (activeTab.value === 'about' && appStore.isAutoScrollLogs) {
      void nextTick(() => {
        if (logListRef.value) {
          logListRef.value.scrollTop = logListRef.value.scrollHeight
        }
      })
    }
  }
)

function getLevelBadgeVariant(level: string): 'neutral' | 'success' | 'warning' | 'danger' {
  switch (level.toLowerCase()) {
    case 'warn':
      return 'warning'
    case 'error':
      return 'danger'
    case 'info':
      return 'success'
    default:
      return 'neutral'
  }
}

onMounted(async () => {
  if (activeTab.value === 'about') {
    await appStore.fetchBootstrap()
  }
})
</script>

<template>
  <div class="h-full flex flex-col bg-bg-app text-content-primary overflow-hidden select-none">
    <!-- Top Navigation & Tabs Header -->
    <div class="border-b border-border/30 bg-panel px-4 sm:px-6 pt-3 shrink-0">
      <div class="flex items-center justify-between gap-3 mb-2.5">
        <div class="flex items-center gap-3">
          <router-link
            to="/chat"
            class="inline-flex items-center gap-1.5 text-xs text-text-muted hover:text-primary transition-colors py-1 px-2 rounded-md hover:bg-muted cursor-pointer"
            title="返回对话工作台"
          >
            <ArrowLeft class="w-3.5 h-3.5" />
            <span>返回对话</span>
          </router-link>
          <span class="text-border">/</span>
          <h1 class="text-sm font-bold text-text">系统设置</h1>
        </div>
      </div>

      <!-- Segmented Tab Bar -->
      <nav class="flex items-center gap-1 overflow-x-auto scrollbar-none -mb-px" aria-label="设置分项目">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          :data-testid="`settings-tab-${tab.id}`"
          class="flex items-center gap-2 px-3.5 py-2 text-xs font-medium border-b-2 transition-all cursor-pointer whitespace-nowrap shrink-0"
          :class="[
            activeTab === tab.id
              ? 'border-primary text-primary font-semibold'
              : 'border-transparent text-text-muted hover:text-text'
          ]"
          @click="setTab(tab.id)"
        >
          <component :is="tab.icon" class="w-4 h-4 shrink-0" />
          <span>{{ tab.label }}</span>
        </button>
      </nav>
    </div>

    <!-- Tab Content Area -->
    <div class="flex-1 overflow-y-auto min-h-0 bg-bg-app">
      <!-- 1. Agent 与模型 -->
      <div v-if="activeTab === 'agents'" class="py-2">
        <AgentsPage />
      </div>

      <!-- 2. 场景与角色 -->
      <div v-else-if="activeTab === 'scenes'" class="py-2">
        <ScenesPage />
      </div>

      <!-- 3. 项目与授权目录 -->
      <div v-else-if="activeTab === 'workspaces'" class="p-6 space-y-6 max-w-5xl mx-auto" data-testid="settings-workspaces-panel">
        <AuthorizedRootsSettings />

        <!-- 已登记项目（只读列表） -->
        <section class="p-5 bg-panel border border-border/40 rounded-xl space-y-4" data-testid="registered-workspaces">
          <div class="flex items-center justify-between">
            <div class="space-y-0.5">
              <h2 class="font-semibold text-sm text-text flex items-center gap-2">
                <FolderGit2 class="w-4 h-4 text-primary" />
                已登记项目
              </h2>
              <p class="text-xs text-text-muted">
                对话与任务所关联的本地项目目录
              </p>
            </div>
            <HqBadge v-if="chatStore.workspaces.length" variant="neutral" size="sm">
              {{ chatStore.workspaces.length }} 个项目
            </HqBadge>
          </div>

          <!-- 空状态 -->
          <div
            v-if="!chatStore.workspaces.length"
            class="p-6 rounded-lg bg-bg-app border border-dashed border-border/40 text-center text-xs text-text-muted"
          >
            在对话页新建任务时登记项目
          </div>

          <!-- 项目列表 -->
          <div v-else class="space-y-2">
            <div
              v-for="ws in chatStore.workspaces"
              :key="ws.id"
              class="p-2.5 bg-muted/20 hover:bg-muted/40 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs transition-colors"
            >
              <div class="flex items-center gap-2.5 min-w-0">
                <div class="w-7 h-7 rounded-lg bg-panel/80 flex items-center justify-center shrink-0 text-text-muted">
                  <FolderGit2 class="w-3.5 h-3.5" />
                </div>
                <div class="min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="font-medium text-text truncate">{{ ws.name }}</span>
                    <HqBadge v-if="ws.branch" variant="neutral" size="sm" class="font-mono text-[10px]">
                      {{ ws.branch }}
                    </HqBadge>
                    <HqBadge v-else-if="ws.vcs === 'git'" variant="neutral" size="sm" class="text-[10px]">
                      Git
                    </HqBadge>
                  </div>
                  <div class="font-mono text-[11px] text-text-muted truncate mt-0.5" :title="ws.path">
                    {{ ws.path }}
                  </div>
                </div>
              </div>

              <div class="flex items-center gap-2 shrink-0 self-end sm:self-auto text-[11px] text-text-muted">
                <span v-if="ws.isClean === false" class="text-amber-500">有未提交改动</span>
                <span v-else-if="ws.isClean === true" class="text-text-muted/70">干净分支</span>
              </div>
            </div>
          </div>
        </section>
      </div>

      <!-- 4. 连接手机 -->
      <div v-else-if="activeTab === 'remote-link'" class="py-2">
        <RemoteLinkPage />
      </div>

      <!-- 5. 关于 / 日志 -->
      <div v-else-if="activeTab === 'about'" class="p-6 space-y-6 max-w-5xl mx-auto">
        <!-- Software info card -->
        <div class="p-5 bg-panel border border-border/40 rounded-xl shadow-xs space-y-4">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <div class="w-10 h-10 rounded-xl bg-primary text-white flex items-center justify-center font-bold text-base shadow-sm">
                HQ
              </div>
              <div>
                <h3 class="text-sm font-bold text-text">HQAgent Hub</h3>
                <p class="text-xs text-text-muted">跨端多智能体协同控制中心</p>
              </div>
            </div>
            <HqBadge variant="neutral" size="sm">v1.5.0</HqBadge>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs pt-2 border-t border-border/20">
            <div class="p-2.5 rounded-xl bg-muted/20 space-y-0.5">
              <div class="text-[11px] text-text-muted">运行模式</div>
              <div class="font-medium text-text">{{ authStore.isMockMode ? '演示模式 (Mock)' : '真实 Worker 模式' }}</div>
            </div>
            <div class="p-2.5 rounded-xl bg-muted/20 space-y-0.5">
              <div class="text-[11px] text-text-muted">架构版本</div>
              <div class="font-medium text-text">Phase 1 / R1.5 Native + Remote</div>
            </div>
            <div class="p-2.5 rounded-xl bg-muted/20 space-y-0.5">
              <div class="text-[11px] text-text-muted">存储与安全规范</div>
              <div class="font-medium text-text font-mono text-[11px] truncate">%LOCALAPPDATA%\HQAgent-Hub</div>
            </div>
          </div>
        </div>

        <!-- Logs Viewer Section -->
        <div class="p-5 bg-panel border border-border/40 rounded-xl shadow-xs space-y-3">
          <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 pb-2 border-b border-border/20">
            <div class="flex items-center gap-2">
              <Terminal class="w-4 h-4 text-primary" />
              <h3 class="text-xs font-bold text-text">实时系统日志与事件流</h3>
              <span class="text-[11px] text-text-muted tabular-nums">({{ appStore.logs.length }} 条)</span>
            </div>

            <div class="flex items-center gap-2 text-xs">
              <!-- Level Filter -->
              <div class="flex items-center gap-1 bg-muted/30 p-0.5 rounded-lg text-[11px]">
                <button
                  type="button"
                  class="px-2 py-0.5 rounded-md transition-colors"
                  :class="selectedLogLevel === 'all' ? 'bg-panel text-text font-medium shadow-2xs' : 'text-text-muted hover:text-text'"
                  @click="selectedLogLevel = 'all'"
                >
                  全部
                </button>
                <button
                  type="button"
                  class="px-2 py-0.5 rounded-md transition-colors"
                  :class="selectedLogLevel === 'info' ? 'bg-panel text-text font-medium shadow-2xs' : 'text-text-muted hover:text-text'"
                  @click="selectedLogLevel = 'info'"
                >
                  INFO
                </button>
                <button
                  type="button"
                  class="px-2 py-0.5 rounded-md transition-colors"
                  :class="selectedLogLevel === 'warn' ? 'bg-panel text-text font-medium shadow-2xs' : 'text-text-muted hover:text-text'"
                  @click="selectedLogLevel = 'warn'"
                >
                  WARN
                </button>
                <button
                  type="button"
                  class="px-2 py-0.5 rounded-md transition-colors"
                  :class="selectedLogLevel === 'error' ? 'bg-panel text-text font-medium shadow-2xs' : 'text-text-muted hover:text-text'"
                  @click="selectedLogLevel = 'error'"
                >
                  ERROR
                </button>
              </div>

              <!-- Auto scroll toggle -->
              <button
                type="button"
                class="px-2 py-1 rounded-md text-[11px] hover:bg-muted/40 transition-colors flex items-center gap-1"
                :class="appStore.isAutoScrollLogs ? 'text-primary font-medium' : 'text-text-muted'"
                @click="appStore.isAutoScrollLogs = !appStore.isAutoScrollLogs"
              >
                <ArrowDown class="w-3 h-3" />
                <span>自动滚屏</span>
              </button>

              <!-- Clear logs -->
              <button
                type="button"
                class="p-1.5 rounded-md text-text-muted hover:text-danger hover:bg-muted/40 transition-colors"
                title="清空日志"
                @click="appStore.clearLogs()"
              >
                <Trash2 class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <!-- Log stream content box -->
          <div
            ref="logListRef"
            class="h-96 overflow-y-auto bg-code rounded-xl p-3 font-mono text-[11px] leading-relaxed select-text space-y-1.5 border border-border/20"
          >
            <div v-if="filteredLogs.length === 0" class="h-full flex items-center justify-center text-content-disabled select-none">
              暂无日志记录
            </div>
            <div
              v-for="log in filteredLogs"
              :key="log.id"
              class="flex items-start gap-2 hover:bg-white/5 px-1 py-0.5 rounded"
            >
              <span class="text-content-muted shrink-0 text-[10px]">{{ log.timestamp.split('T')[1]?.slice(0, 8) || log.timestamp }}</span>
              <HqBadge :variant="getLevelBadgeVariant(log.level)" size="sm" class="text-[9px] px-1 py-0 shrink-0 uppercase">
                {{ log.level }}
              </HqBadge>
              <span class="text-content-primary break-all flex-1">{{ log.message }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
