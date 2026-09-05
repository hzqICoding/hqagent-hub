<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app.store'
import { useAgentStore } from '@/stores/agent.store'
import { useWorkspaceStore } from '@/stores/workspace.store'
import { useThemeStore } from '@/shared/theme/theme.store'
import { PALETTES_META, type ThemePalette } from '@/shared/theme/theme.types'
import {
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  FolderGit2,
  Bot,
  Palette,
  ArrowRight,
  ArrowLeft,
  Server,
  Terminal,
  Cpu,
  Sparkles,
  WifiOff,
} from 'lucide-vue-next'
import {
  HqButton,
  HqBadge,
  HqInput,
  LoadingState,
  HqEmptyState,
  HqErrorState,
  OfflineState,
} from '@/shared/ui'

const router = useRouter()
const appStore = useAppStore()
const agentStore = useAgentStore()
const workspaceStore = useWorkspaceStore()
const themeStore = useThemeStore()

const currentStep = ref<number>(1)
const totalSteps = 6

const isTestingHub = ref<boolean>(false)
const hubConnected = ref<boolean>(true)
const workspacePath = ref<string>('E:/OtherPro/HQAgent-Hub')

onMounted(async () => {
  await runHubCheck()
})

async function runHubCheck() {
  isTestingHub.value = true
  try {
    await appStore.fetchBootstrap()
    hubConnected.value = !appStore.isOffline
  } catch {
    hubConnected.value = false
  } finally {
    isTestingHub.value = false
  }
}

async function handleStartScan() {
  await agentStore.refreshDiscovery()
}

function selectPalette(id: ThemePalette) {
  themeStore.setPalette(id)
}

function handleFinish() {
  router.push('/overview')
}

const steps = [
  { step: 1, title: '欢迎与说明' },
  { step: 2, title: 'Local Hub 检测' },
  { step: 3, title: '扫描 Agent' },
  { step: 4, title: '工作区配置' },
  { step: 5, title: '外观风格' },
  { step: 6, title: '完成与就绪' },
]
</script>

<template>
  <div class="min-h-screen w-full bg-app flex flex-col justify-between p-6 select-none overflow-y-auto">
    <!-- Header -->
    <header class="max-w-4xl w-full mx-auto flex items-center justify-between pb-6 border-b border-border-subtle">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-primary-600 flex items-center justify-center text-white font-bold shadow">
          HQ
        </div>
        <div>
          <h1 class="text-base font-bold text-content-primary">HQAgent-Hub 快速配置向导</h1>
          <p class="text-xs text-content-muted">初始化本地环境、Agent 探测与控制台设置</p>
        </div>
      </div>

      <!-- Step Progress Indicator -->
      <div class="flex items-center gap-2 text-xs font-medium">
        <span class="text-primary-600 font-bold">第 {{ currentStep }} 步</span>
        <span class="text-content-disabled">/</span>
        <span class="text-content-muted">共 {{ totalSteps }} 步</span>
      </div>
    </header>

    <!-- Main Step Card -->
    <main class="max-w-4xl w-full mx-auto my-8 bg-panel border border-border-default rounded-xl shadow-sm p-8 flex-1 flex flex-col justify-between min-h-[460px]">
      <!-- STEP 1: WELCOME & LOCAL FIRST -->
      <div v-if="currentStep === 1" class="space-y-6 max-w-2xl mx-auto py-4">
        <div class="text-center space-y-2">
          <div class="w-14 h-14 rounded-2xl bg-primary-50 dark:bg-primary-950 text-primary-600 flex items-center justify-center mx-auto mb-4">
            <ShieldCheck class="w-8 h-8" />
          </div>
          <h2 class="text-xl font-bold text-content-primary">本地优先，多 Agent 协同控制中心</h2>
          <p class="text-xs text-content-secondary leading-relaxed">
            HQAgent-Hub 是运行在您本地机器上的 AI 研发团队协作平台。代码、上下文记忆与执行权限全部驻留本机，未经审批绝不外泄。
          </p>
        </div>

        <div class="grid grid-cols-3 gap-4 pt-4 text-xs">
          <div class="p-4 rounded-lg bg-muted/40 border border-border-subtle space-y-1.5">
            <h4 class="font-bold text-content-primary flex items-center gap-1.5">
              <Server class="w-4 h-4 text-primary-500" />
              Local Hub 架构
            </h4>
            <p class="text-2xs text-content-muted leading-relaxed">
              常驻本机后台调度，提供本地事件总线、Git Worktree 隔离与高风险安全栅栏。
            </p>
          </div>
          <div class="p-4 rounded-lg bg-muted/40 border border-border-subtle space-y-1.5">
            <h4 class="font-bold text-content-primary flex items-center gap-1.5">
              <Cpu class="w-4 h-4 text-emerald-500" />
              统一适配器 (Adapters)
            </h4>
            <p class="text-2xs text-content-muted leading-relaxed">
              无缝编排 Claude Code、Codex、Antigravity CLI 等多种终端 Agent，职责完全解耦。
            </p>
          </div>
          <div class="p-4 rounded-lg bg-muted/40 border border-border-subtle space-y-1.5">
            <h4 class="font-bold text-content-primary flex items-center gap-1.5">
              <ShieldCheck class="w-4 h-4 text-amber-500" />
              安全双人确认
            </h4>
            <p class="text-2xs text-content-muted leading-relaxed">
              对于 git_push、部署、网络等高危动作强制弹窗二次审批，确保操作安全受控。
            </p>
          </div>
        </div>
      </div>

      <!-- STEP 2: LOCAL HUB CHECK -->
      <div v-else-if="currentStep === 2" class="space-y-6 max-w-xl mx-auto py-6">
        <div class="text-center space-y-2">
          <h2 class="text-lg font-bold text-content-primary">检测 Local Hub 服务</h2>
          <p class="text-xs text-content-muted">
            验证位于 127.0.0.1:44810 的 Local Hub 后台核心进程是否正常响应
          </p>
        </div>

        <!-- Offline state if unreachable -->
        <div v-if="appStore.isOffline" class="p-4 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 space-y-3">
          <div class="flex items-center gap-2 text-rose-700 dark:text-rose-300 font-semibold text-xs">
            <WifiOff class="w-4 h-4" />
            <span>无法连接到 Local Hub 守护进程</span>
          </div>
          <p class="text-2xs text-rose-600 dark:text-rose-400 leading-relaxed">
            请确认后台服务已启动，或者在开发环境中切换到其他 Mock 场景以继续预览。
          </p>
          <HqButton size="sm" variant="secondary" @click="runHubCheck" :loading="isTestingHub">
            重试连接
          </HqButton>
        </div>

        <!-- Connected or Mock state -->
        <div v-else class="p-5 rounded-xl bg-muted/30 border border-border-subtle space-y-4">
          <div class="flex items-center justify-between pb-3 border-b border-border-subtle">
            <span class="text-xs text-content-secondary">服务端口</span>
            <span class="text-xs font-mono font-bold text-content-primary">127.0.0.1:44810</span>
          </div>
          <div class="flex items-center justify-between pb-3 border-b border-border-subtle">
            <span class="text-xs text-content-secondary">运行协议版本</span>
            <span class="text-xs font-mono font-bold text-primary-600">v{{ appStore.bootstrap?.protocolVersion || '1.0.0' }}</span>
          </div>
          <div class="flex items-center justify-between pb-3 border-b border-border-subtle">
            <span class="text-xs text-content-secondary">应用版本</span>
            <span class="text-xs font-mono font-bold text-content-primary">v{{ appStore.bootstrap?.appVersion || '0.1.0' }}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-xs text-content-secondary">安全通信通道</span>
            <span class="flex items-center gap-1.5 text-xs text-emerald-600 font-medium">
              <CheckCircle2 class="w-4 h-4" />
              WS Ticket 动态鉴权正常
            </span>
          </div>
        </div>
      </div>

      <!-- STEP 3: SCAN AGENTS -->
      <div v-else-if="currentStep === 3" class="space-y-4 max-w-2xl mx-auto py-2">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-lg font-bold text-content-primary">扫描本地 Agent 环境</h2>
            <p class="text-xs text-content-muted">探测本机已安装并登录的 AI 适配器与命令行工具</p>
          </div>
          <HqButton size="sm" variant="secondary" @click="handleStartScan" :loading="agentStore.isRefreshing">
            <template #icon>
              <RefreshCw class="w-3.5 h-3.5" :class="agentStore.isRefreshing ? 'animate-spin' : ''" />
            </template>
            重新扫描
          </HqButton>
        </div>

        <!-- Loading State -->
        <LoadingState v-if="agentStore.isLoading || agentStore.isRefreshing" description="正在探测本机 Agent CLI 工具与状态..." />

        <!-- Empty State -->
        <HqEmptyState
          v-else-if="agentStore.agents.length === 0"
          title="未扫描到任何已安装的 Agent"
          description="系统未检测到 Claude Code、Codex 等 CLI 工具。请在终端安装并登录后重试。"
        >
          <template #actions>
            <HqButton size="sm" variant="primary" @click="handleStartScan">
              重新探测
            </HqButton>
          </template>
        </HqEmptyState>

        <!-- Discovered Agents List -->
        <div v-else class="space-y-2.5 max-h-72 overflow-y-auto pr-1">
          <div
            v-for="agent in agentStore.agents"
            :key="agent.id"
            class="p-3 rounded-lg border border-border-subtle bg-panel flex items-center justify-between text-xs"
          >
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg bg-primary-50 dark:bg-primary-950 flex items-center justify-center text-primary-600">
                <Bot class="w-4 h-4" />
              </div>
              <div>
                <div class="flex items-center gap-2">
                  <span class="font-bold text-content-primary">{{ agent.displayName }}</span>
                  <span class="text-2xs font-mono text-content-muted">v{{ agent.version }}</span>
                </div>
                <div class="text-2xs text-content-muted font-mono truncate max-w-xs">
                  {{ agent.executablePath || agent.adapterId }}
                </div>
              </div>
            </div>

            <div class="flex items-center gap-2">
              <HqBadge
                :variant="agent.status === 'ready' ? 'success' : agent.status === 'busy' ? 'warning' : 'danger'"
                size="sm"
              >
                {{ agent.status }}
              </HqBadge>
            </div>
          </div>
        </div>
      </div>

      <!-- STEP 4: WORKSPACE SELECTION -->
      <div v-else-if="currentStep === 4" class="space-y-6 max-w-xl mx-auto py-6">
        <div class="text-center space-y-2">
          <h2 class="text-lg font-bold text-content-primary">设置默认工作区与团队配置</h2>
          <p class="text-xs text-content-muted">指定 AI 协同开发的目标代码仓库根目录</p>
        </div>

        <div class="space-y-4">
          <div class="space-y-1.5">
            <label class="block text-xs font-semibold text-content-primary">项目工作区路径</label>
            <div class="flex gap-2">
              <input
                v-model="workspacePath"
                type="text"
                class="flex-1 text-xs font-mono bg-panel border border-border-default rounded-md px-3 py-2 text-content-primary focus:outline-none focus:ring-1 focus:ring-primary-500"
              />
            </div>
            <p class="text-2xs text-content-muted">Git 仓库将自动启用 Worktree 隔离机制，保护您的主分支。</p>
          </div>

          <div class="p-4 rounded-lg bg-muted/30 border border-border-subtle space-y-2">
            <div class="flex items-center justify-between text-xs">
              <span class="text-content-muted">默认团队 Profile</span>
              <span class="font-semibold text-content-primary">标准全栈三角色协作 (Fullstack Trio)</span>
            </div>
            <div class="flex items-center justify-between text-xs">
              <span class="text-content-muted">核心角色分配</span>
              <span class="text-2xs text-content-secondary">架构师 + 前端实现 + 代码审查</span>
            </div>
          </div>
        </div>
      </div>

      <!-- STEP 5: APPEARANCE & PALETTES -->
      <div v-else-if="currentStep === 5" class="space-y-6 max-w-2xl mx-auto py-4">
        <div class="text-center space-y-2">
          <h2 class="text-lg font-bold text-content-primary">个性化控制台外观</h2>
          <p class="text-xs text-content-muted">选择最符合您偏好的明暗模式与主题色调</p>
        </div>

        <!-- Mode Buttons -->
        <div class="flex justify-center gap-3">
          <button
            v-for="m in [
              { id: 'system', label: '跟随系统' },
              { id: 'light', label: '浅色模式' },
              { id: 'dark', label: '深色模式' },
            ]"
            :key="m.id"
            type="button"
            @click="themeStore.setMode(m.id as any)"
            class="px-4 py-2 rounded-lg text-xs font-medium border transition-colors"
            :class="themeStore.settings.mode === m.id ? 'border-primary-600 bg-primary-50 text-primary-700 dark:bg-primary-950 font-bold' : 'border-border-default hover:bg-muted text-content-secondary'"
          >
            {{ m.label }}
          </button>
        </div>

        <!-- Palette Grid -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
          <button
            v-for="pal in PALETTES_META"
            :key="pal.id"
            type="button"
            @click="selectPalette(pal.id as ThemePalette)"
            class="p-3 rounded-lg border text-left flex flex-col gap-2 transition-all"
            :class="themeStore.settings.palette === pal.id ? 'border-primary-600 ring-2 ring-primary-500/20 shadow-xs' : 'border-border-subtle hover:border-border-default bg-panel'"
          >
            <div class="w-full h-8 rounded-md flex items-center justify-center text-white text-xs font-bold" :style="{ backgroundColor: pal.primaryHex }">
              {{ pal.name }}
            </div>
            <div class="text-2xs text-content-muted leading-tight truncate">
              {{ pal.description }}
            </div>
          </button>
        </div>
      </div>

      <!-- STEP 6: DIAGNOSTIC SUMMARY & COMPLETE -->
      <div v-else-if="currentStep === 6" class="space-y-6 max-w-xl mx-auto py-6">
        <div class="text-center space-y-2">
          <div class="w-12 h-12 rounded-full bg-emerald-50 dark:bg-emerald-950 text-emerald-600 flex items-center justify-center mx-auto mb-2">
            <CheckCircle2 class="w-7 h-7" />
          </div>
          <h2 class="text-lg font-bold text-content-primary">配置就绪，环境诊断通过</h2>
          <p class="text-xs text-content-muted">HQAgent-Hub 已就绪，您可以立即开启多 Agent 协同任务</p>
        </div>

        <div class="p-4 rounded-xl bg-muted/40 border border-border-subtle space-y-2.5 text-xs">
          <div class="flex items-center justify-between">
            <span class="text-content-muted">Local Hub 连接</span>
            <span class="text-emerald-600 font-semibold flex items-center gap-1">
              <CheckCircle2 class="w-3.5 h-3.5" />
              正常 (127.0.0.1:44810)
            </span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-content-muted">可用 Agent 数量</span>
            <span class="font-bold text-content-primary">{{ agentStore.readyCount }} 就绪 / {{ agentStore.totalCount }} 发现</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-content-muted">工作区目录</span>
            <span class="font-mono text-content-primary truncate max-w-xs">{{ workspacePath }}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-content-muted">当前主题配色</span>
            <span class="text-primary-600 font-semibold uppercase">{{ themeStore.settings.palette }}</span>
          </div>
        </div>
      </div>

      <!-- Footer Navigation Buttons -->
      <footer class="flex items-center justify-between pt-6 border-t border-border-subtle mt-6">
        <HqButton
          v-if="currentStep > 1"
          size="sm"
          variant="secondary"
          @click="currentStep--"
        >
          <template #icon>
            <ArrowLeft class="w-3.5 h-3.5" />
          </template>
          上一步
        </HqButton>
        <div v-else></div>

        <div class="flex items-center gap-3">
          <HqButton
            v-if="currentStep < totalSteps"
            size="sm"
            variant="primary"
            @click="currentStep++"
          >
            下一步
            <template #iconRight>
              <ArrowRight class="w-3.5 h-3.5" />
            </template>
          </HqButton>
          <HqButton
            v-else
            size="sm"
            variant="primary"
            @click="handleFinish"
          >
            进入总览控制台
            <template #iconRight>
              <ArrowRight class="w-3.5 h-3.5" />
            </template>
          </HqButton>
        </div>
      </footer>
    </main>
  </div>
</template>
