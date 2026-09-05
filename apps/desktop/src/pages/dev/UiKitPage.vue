<script setup lang="ts">
import { ref, computed } from 'vue'
import { useThemeStore } from '@/shared/theme/theme.store'
import { PALETTES_META } from '@/shared/theme/theme.types'
import { useScenarioRunner } from '@/mocks/scenario-runner'
import { useToast } from '@/shared/ui/useToast'
import {
  HqButton,
  HqIconButton,
  HqInput,
  HqTextarea,
  HqSelect,
  HqCombobox,
  HqCheckbox,
  HqRadioGroup,
  HqSwitch,
  HqTabs,
  HqBadge,
  HqTooltip,
  HqPopover,
  HqDropdown,
  HqDialog,
  HqDrawer,
  HqToast,
  HqTable,
  HqVirtualList,
  HqTree,
  HqSplitPane,
  HqProgress,
  HqSkeleton,
  HqEmptyState,
  HqErrorState,
  HqCodeBlock,
  HqMarkdown,
  LoadingState,
  OfflineState,
} from '@/shared/ui'

import {
  Sun,
  Moon,
  Monitor,
  Sparkles,
  Sliders,
  Play,
  Square,
  AlertCircle,
  FileCode,
  Layers,
  Terminal,
  RefreshCw,
  FolderGit2,
  Cpu,
  CheckCircle2,
} from 'lucide-vue-next'

const theme = useThemeStore()
const scenarioRunner = useScenarioRunner()
const toast = useToast()

// Dialog & Drawer state
const dialogOpen = ref(false)
const drawerOpen = ref(false)

// Form states
const sampleInput = ref('HQAgent-Hub 桌面端')
const sampleTextarea = ref('这是一个支持多行的配置说明内容...')
const sampleSelect = ref('codex')
const sampleCombobox = ref('architect')
const sampleCheckbox = ref(true)
const sampleRadio = ref('comfortable')
const sampleSwitch = ref(true)
const activeTab = ref('buttons')

const selectOptions = [
  { label: 'Claude Code 2.1.261', value: 'claude', description: '需求、架构与审核' },
  { label: 'Codex App Server 0.147.0', value: 'codex', description: '通用实现与测试' },
  { label: 'Antigravity 2.11.0', value: 'antigravity', description: '前端组件工程' },
]

const comboboxOptions = [
  { label: 'orchestrator (总控调度)', value: 'orchestrator' },
  { label: 'architect (系统架构)', value: 'architect' },
  { label: 'frontend_implementer (前端实现)', value: 'frontend' },
  { label: 'general_implementer (全栈实现)', value: 'implementer' },
  { label: 'reviewer (代码审查)', value: 'reviewer' },
  { label: 'tester (测试验证)', value: 'tester' },
]

const radioOptions = [
  { label: '舒适模式 (Comfortable)', value: 'comfortable', description: '适合日常开发与宽裕排版' },
  { label: '紧凑模式 (Compact)', value: 'compact', description: '高密度日志与长表格' },
]

const tabs = [
  { id: 'buttons', label: '按钮与表单', count: 9 },
  { id: 'feedback', label: '反馈与浮层', count: 6 },
  { id: 'data', label: '数据与大列表', count: 6 },
  { id: 'theme-colors', label: '主题与角色色阶', count: 12 },
  { id: 'four-states', label: '四态页面模板', count: 4 },
]

// Table sample data
const tableColumns = [
  { key: 'role', label: '分配角色', width: '140px' },
  { key: 'agent', label: '当前指派 Agent', width: '180px' },
  { key: 'source', label: '路由来源', width: '130px' },
  { key: 'status', label: '状态', width: '110px' },
  { key: 'action', label: '操作', align: 'right' as const },
]

const tableData = [
  { id: '1', role: 'architect', agent: 'Claude Code (2.1.261)', source: 'workspace_profile', status: 'ready' },
  { id: '2', role: 'frontend_implementer', agent: 'Codex App Server', source: 'fallback (降级命中)', status: 'ready' },
  { id: '3', role: 'general_implementer', agent: 'Codex App Server', source: 'workspace_profile', status: 'busy' },
  { id: '4', role: 'reviewer', agent: 'Claude Code (2.1.261)', source: 'workspace_profile', status: 'ready' },
]

// 10,000 items virtual list sample
const virtualItemsCount = 10000
const largeEventList = computed(() => {
  return Array.from({ length: virtualItemsCount }, (_, i) => ({
    id: i + 1,
    seq: 1000 + i,
    timestamp: new Date(Date.now() - (virtualItemsCount - i) * 1000).toLocaleTimeString(),
    type: i % 5 === 0 ? 'agent.progress' : i % 7 === 0 ? 'task.approval_needed' : 'agent.tool_called',
    text: `[seq #${1000 + i}] 事件流载荷数据项 #${i + 1}：节点状态同步完成，worktree 路径 hash: a8b${i % 99}c`,
  }))
})

// Tree sample
const treeNodes = [
  {
    id: '1',
    label: 'apps',
    children: [
      {
        id: '1-1',
        label: 'desktop',
        children: [
          { id: '1-1-1', label: 'src/shared/theme' },
          { id: '1-1-2', label: 'src/shared/ui' },
          { id: '1-1-3', label: 'src/shared/api' },
        ],
      },
      { id: '1-2', label: 'hub' },
    ],
  },
  {
    id: '2',
    label: 'packages',
    children: [
      { id: '2-1', label: 'protocol/generated/ts' },
      { id: '2-2', label: 'protocol/fixtures' },
    ],
  },
]

// Dropdown items
const dropdownItems = [
  { label: '查看详情', action: () => toast.info('点击了查看详情') },
  { label: '复制任务ID', action: () => toast.success('已复制到剪贴板') },
  { divider: true, label: '' },
  { label: '终止执行', danger: true, action: () => toast.danger('已发送终止指令') },
]

const sampleMarkdown = `
# HQAgent-Hub 协作规范草案
这是一个用于验证 **Markdown** 渲染器安全性的样本。

### 核心特性：
- 严格遵循语义 **Design Token**，严禁硬编码颜色
- 所有代码均在独立的 \`git worktree\` 中执行
- 支持 [点击查看文档](https://github.com) 安全外链

> 提示：当首选 Agent 离线时，自动无缝命中备用链并提示降级原因。

\`\`\`typescript
export interface HubEvent<T = unknown> {
  eventId: string
  seq: number
  occurredAt: string
  type: string
  payload: T
}
\`\`\`
`
</script>

<template>
  <div class="h-screen w-screen flex flex-col bg-app text-content-primary overflow-hidden">
    <!-- Top Control Bar: Theme & Scenario Matrix -->
    <header class="h-14 border-b border-border bg-panel px-4 flex items-center justify-between shrink-0 shadow-subtle select-none z-20">
      <div class="flex items-center gap-3">
        <div class="h-8 w-8 rounded-[var(--radius-sm)] bg-action-primary flex items-center justify-center text-action-primary-text font-bold shadow-sm">
          HQ
        </div>
        <div>
          <h1 class="text-sm font-bold tracking-tight">HQAgent-Hub UI Kit</h1>
          <p class="text-[11px] text-content-muted">F0 Design System & Component Matrix</p>
        </div>
      </div>

      <!-- Real-Time Theme Controls -->
      <div class="flex items-center gap-2 text-xs">
        <!-- Mode Switcher -->
        <div class="flex items-center bg-muted p-0.5 rounded-[var(--radius-xs)] border border-border-subtle">
          <button
            type="button"
            :class="['px-2 py-1 rounded-[var(--radius-xs)] flex items-center gap-1 transition-colors', theme.mode === 'system' ? 'bg-panel text-content-primary font-medium shadow-sm' : 'text-content-secondary hover:text-content-primary']"
            @click="theme.setMode('system')"
          >
            <Monitor class="h-3.5 w-3.5" />
            <span>系统 ({{ theme.resolvedMode }})</span>
          </button>
          <button
            type="button"
            :class="['px-2 py-1 rounded-[var(--radius-xs)] flex items-center gap-1 transition-colors', theme.mode === 'light' ? 'bg-panel text-content-primary font-medium shadow-sm' : 'text-content-secondary hover:text-content-primary']"
            @click="theme.setMode('light')"
          >
            <Sun class="h-3.5 w-3.5" />
            <span>浅色</span>
          </button>
          <button
            type="button"
            :class="['px-2 py-1 rounded-[var(--radius-xs)] flex items-center gap-1 transition-colors', theme.mode === 'dark' ? 'bg-panel text-content-primary font-medium shadow-sm' : 'text-content-secondary hover:text-content-primary']"
            @click="theme.setMode('dark')"
          >
            <Moon class="h-3.5 w-3.5" />
            <span>深色</span>
          </button>
        </div>

        <!-- Palette Selector -->
        <div class="flex items-center bg-muted p-0.5 rounded-[var(--radius-xs)] border border-border-subtle">
          <button
            v-for="(meta, pKey) in PALETTES_META"
            :key="pKey"
            type="button"
            :title="meta.description"
            :class="[
              'px-2 py-1 rounded-[var(--radius-xs)] flex items-center gap-1.5 transition-colors',
              theme.palette === pKey ? 'bg-panel text-content-primary font-semibold shadow-sm' : 'text-content-secondary hover:text-content-primary'
            ]"
            @click="theme.setPalette(pKey as any)"
          >
            <span class="h-2.5 w-2.5 rounded-full" :style="{ backgroundColor: meta.primaryHex }" />
            <span>{{ meta.name.split(' ')[0] }}</span>
          </button>
        </div>

        <!-- Density Toggle -->
        <div class="flex items-center bg-muted p-0.5 rounded-[var(--radius-xs)] border border-border-subtle">
          <button
            type="button"
            :class="['px-2 py-1 rounded-[var(--radius-xs)]', theme.density === 'comfortable' ? 'bg-panel text-content-primary font-semibold shadow-sm' : 'text-content-secondary']"
            @click="theme.setDensity('comfortable')"
          >
            舒适
          </button>
          <button
            type="button"
            :class="['px-2 py-1 rounded-[var(--radius-xs)]', theme.density === 'compact' ? 'bg-panel text-content-primary font-semibold shadow-sm' : 'text-content-secondary']"
            @click="theme.setDensity('compact')"
          >
            紧凑
          </button>
        </div>

        <!-- Contrast Toggle -->
        <div class="flex items-center bg-muted p-0.5 rounded-[var(--radius-xs)] border border-border-subtle">
          <button
            type="button"
            :class="['px-2 py-1 rounded-[var(--radius-xs)]', theme.contrast === 'normal' ? 'bg-panel text-content-primary font-semibold shadow-sm' : 'text-content-secondary']"
            @click="theme.setContrast('normal')"
          >
            正常对比
          </button>
          <button
            type="button"
            :class="['px-2 py-1 rounded-[var(--radius-xs)]', theme.contrast === 'high' ? 'bg-panel text-content-primary font-semibold shadow-sm' : 'text-content-secondary']"
            @click="theme.setContrast('high')"
          >
            高对比
          </button>
        </div>
      </div>
    </header>

    <!-- Subheader: Mock Scenario Runner -->
    <div class="h-10 bg-muted/60 border-b border-border px-4 flex items-center justify-between text-xs shrink-0 select-none">
      <div class="flex items-center gap-2">
        <span class="text-content-muted flex items-center gap-1 font-medium">
          <Sliders class="h-3.5 w-3.5" />
          Mock 场景模拟器:
        </span>
        <select
          :value="scenarioRunner.currentScenario.value"
          class="bg-panel border border-border text-content-primary px-2 py-1 rounded text-xs outline-none"
          @change="scenarioRunner.switchScenario(($event.target as HTMLSelectElement).value as any)"
        >
          <option
            v-for="s in scenarioRunner.availableScenarios"
            :key="s.id"
            :value="s.id"
          >
            {{ s.name }}
          </option>
        </select>

        <span class="text-content-muted ml-2">
          说明: {{ scenarioRunner.availableScenarios.find(s => s.id === scenarioRunner.currentScenario.value)?.description }}
        </span>
      </div>

      <div class="flex items-center gap-2">
        <HqButton
          size="sm"
          :variant="scenarioRunner.isStreaming.value ? 'danger' : 'secondary'"
          @click="scenarioRunner.isStreaming.value ? scenarioRunner.stopEventStream() : scenarioRunner.startEventStream()"
        >
          <template #icon>
            <Square v-if="scenarioRunner.isStreaming.value" class="h-3 w-3 mr-1" />
            <Play v-else class="h-3 w-3 mr-1" />
          </template>
          {{ scenarioRunner.isStreaming.value ? '停止模拟事件流' : '发射模拟事件流' }}
        </HqButton>

        <HqButton size="sm" variant="outline" @click="toast.success('已触发快速通知')">
          弹出 Toast
        </HqButton>
      </div>
    </div>

    <!-- Main Workspace with Tabs -->
    <div class="flex-1 flex flex-col overflow-hidden">
      <div class="px-6 pt-3 bg-panel border-b border-border shrink-0">
        <HqTabs v-model="activeTab" :tabs="tabs" variant="line" />
      </div>

      <div class="flex-1 overflow-y-auto p-6 space-y-8">
        <!-- ==================== TAB 1: Buttons & Forms ==================== -->
        <section v-if="activeTab === 'buttons'" class="space-y-6">
          <!-- Buttons -->
          <div class="bg-panel border border-border rounded-[var(--radius-md)] p-5 space-y-4">
            <h3 class="text-sm font-semibold text-content-primary border-b border-border-subtle pb-2 flex items-center gap-2">
              <Sparkles class="h-4 w-4 text-accent" />
              1. HqButton & HqIconButton (所有状态变体)
            </h3>

            <div class="flex flex-wrap items-center gap-3">
              <HqButton variant="primary">Primary</HqButton>
              <HqButton variant="secondary">Secondary</HqButton>
              <HqButton variant="danger">Danger</HqButton>
              <HqButton variant="outline">Outline</HqButton>
              <HqButton variant="ghost">Ghost</HqButton>
              <HqButton variant="primary" :loading="true">Loading 态</HqButton>
              <HqButton variant="secondary" :disabled="true">Disabled 态</HqButton>
            </div>

            <div class="flex items-center gap-3 pt-2">
              <span class="text-xs text-content-muted">尺寸档位:</span>
              <HqButton size="sm" variant="secondary">Small (28px)</HqButton>
              <HqButton size="md" variant="secondary">Medium (36px)</HqButton>
              <HqButton size="lg" variant="secondary">Large (44px)</HqButton>
              <span class="text-xs text-content-muted ml-4">图标按钮:</span>
              <HqIconButton label="刷新" variant="secondary">
                <RefreshCw class="h-4 w-4" />
              </HqIconButton>
              <HqIconButton label="警告" variant="danger">
                <AlertCircle class="h-4 w-4" />
              </HqIconButton>
              <HqIconButton label="加载中" :loading="true" />
              <HqIconButton label="禁用" :disabled="true">
                <CheckCircle2 class="h-4 w-4" />
              </HqIconButton>
            </div>
          </div>

          <!-- Inputs & Controls -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <!-- Left Form Controls -->
            <div class="bg-panel border border-border rounded-[var(--radius-md)] p-5 space-y-4">
              <h3 class="text-sm font-semibold text-content-primary border-b border-border-subtle pb-2">
                2. 输入框与下拉选择
              </h3>

              <div class="space-y-3">
                <div>
                  <label class="block text-xs font-medium text-content-secondary mb-1">HqInput (标准输入 + 清除)</label>
                  <HqInput v-model="sampleInput" placeholder="请输入内容..." :clearable="true" />
                </div>

                <div>
                  <label class="block text-xs font-medium text-content-secondary mb-1">HqInput (错误校验态)</label>
                  <HqInput model-value="invalid_path/../*" error="不允许包含非法父目录路径" />
                </div>

                <div>
                  <label class="block text-xs font-medium text-content-secondary mb-1">HqSelect (自定义下拉)</label>
                  <HqSelect v-model="sampleSelect" :options="selectOptions" />
                </div>

                <div>
                  <label class="block text-xs font-medium text-content-secondary mb-1">HqCombobox (可搜索下拉)</label>
                  <HqCombobox v-model="sampleCombobox" :options="comboboxOptions" />
                </div>
              </div>
            </div>

            <!-- Right Form Controls -->
            <div class="bg-panel border border-border rounded-[var(--radius-md)] p-5 space-y-4">
              <h3 class="text-sm font-semibold text-content-primary border-b border-border-subtle pb-2">
                3. 多行文本、开关与选择器
              </h3>

              <div class="space-y-4">
                <div>
                  <label class="block text-xs font-medium text-content-secondary mb-1">HqTextarea (等宽代码/指令模式)</label>
                  <HqTextarea v-model="sampleTextarea" :rows="3" :mono="true" :show-count="true" :maxlength="200" />
                </div>

                <div class="flex items-center justify-between pt-1">
                  <span class="text-xs font-medium text-content-secondary">HqSwitch (实时开关)</span>
                  <HqSwitch v-model="sampleSwitch" label="开启 Worktree 路径隔离" />
                </div>

                <div class="flex items-center justify-between">
                  <span class="text-xs font-medium text-content-secondary">HqCheckbox (复选与半选)</span>
                  <div class="flex items-center gap-4">
                    <HqCheckbox v-model="sampleCheckbox" label="启用自动回滚" />
                    <HqCheckbox :indeterminate="true" label="部分选中" />
                  </div>
                </div>

                <div>
                  <label class="block text-xs font-medium text-content-secondary mb-2">HqRadioGroup (单选组合)</label>
                  <HqRadioGroup v-model="sampleRadio" :options="radioOptions" direction="horizontal" />
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- ==================== TAB 2: Feedback & Overlays ==================== -->
        <section v-if="activeTab === 'feedback'" class="space-y-6">
          <div class="bg-panel border border-border rounded-[var(--radius-md)] p-5 space-y-4">
            <h3 class="text-sm font-semibold text-content-primary border-b border-border-subtle pb-2">
              弹窗、抽屉与浮层菜单
            </h3>

            <div class="flex flex-wrap items-center gap-3">
              <HqButton variant="primary" @click="dialogOpen = true">打开 HqDialog 模态弹窗</HqButton>
              <HqButton variant="secondary" @click="drawerOpen = true">打开 HqDrawer 侧边抽屉</HqButton>

              <!-- Popover -->
              <HqPopover>
                <template #trigger="{ isOpen }">
                  <HqButton variant="outline">
                    HqPopover 点击浮层 ({{ isOpen ? '展开' : '收起' }})
                  </HqButton>
                </template>
                <template #default="{ close }">
                  <div class="w-64 text-xs space-y-2">
                    <div class="font-semibold text-content-primary">快速任务过滤器</div>
                    <p class="text-content-secondary">按角色、状态或时间快速筛选本地任务。</p>
                    <div class="pt-2 flex justify-end">
                      <HqButton size="sm" @click="close">确定</HqButton>
                    </div>
                  </div>
                </template>
              </HqPopover>

              <!-- Dropdown -->
              <HqDropdown :items="dropdownItems">
                <HqButton variant="secondary">操作下拉菜单 ▾</HqButton>
              </HqDropdown>

              <!-- Tooltips -->
              <HqTooltip content="这是一个悬浮快捷提示 (Tooltip)">
                <HqButton variant="ghost">悬浮提示 Tooltip</HqButton>
              </HqTooltip>
            </div>
          </div>

          <!-- Badges & Progress -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="bg-panel border border-border rounded-[var(--radius-md)] p-5 space-y-4">
              <h3 class="text-sm font-semibold text-content-primary border-b border-border-subtle pb-2">
                徽标 Badge (状态与尺寸)
              </h3>
              <div class="flex flex-wrap items-center gap-2">
                <HqBadge variant="success" :dot="true">Ready / 就绪</HqBadge>
                <HqBadge variant="warning" :dot="true">Waiting / 等待审批</HqBadge>
                <HqBadge variant="danger" :dot="true">Failed / 拦截失败</HqBadge>
                <HqBadge variant="info" :dot="true">Running / 执行中</HqBadge>
                <HqBadge variant="neutral" :dot="true">Offline / 离线</HqBadge>
                <HqBadge variant="primary">Primary 强调</HqBadge>
              </div>
            </div>

            <div class="bg-panel border border-border rounded-[var(--radius-md)] p-5 space-y-4">
              <h3 class="text-sm font-semibold text-content-primary border-b border-border-subtle pb-2">
                进度条 Progress
              </h3>
              <div class="space-y-3">
                <div>
                  <div class="text-xs text-content-muted mb-1">下载进度 (68%)</div>
                  <HqProgress :value="68" :show-text="true" />
                </div>
                <div>
                  <div class="text-xs text-content-muted mb-1">不确定脉冲状态 (Task Drain)</div>
                  <HqProgress :indeterminate="true" variant="warning" />
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- ==================== TAB 3: Data & Virtual List ==================== -->
        <section v-if="activeTab === 'data'" class="space-y-6">
          <!-- Table -->
          <div class="bg-panel border border-border rounded-[var(--radius-md)] p-5 space-y-3">
            <h3 class="text-sm font-semibold text-content-primary border-b border-border-subtle pb-2 flex items-center justify-between">
              <span>HqTable 数据表格</span>
              <span class="text-xs font-normal text-content-muted">支持紧凑与舒适两种行高排版</span>
            </h3>
            <HqTable :columns="tableColumns" :data="tableData">
              <template #cell-role="{ row }">
                <HqBadge variant="role" :role="row.role">{{ row.role }}</HqBadge>
              </template>
              <template #cell-status="{ row }">
                <HqBadge :variant="row.status === 'ready' ? 'success' : 'info'" :dot="true">
                  {{ row.status }}
                </HqBadge>
              </template>
              <template #cell-action>
                <HqButton size="sm" variant="ghost">配置</HqButton>
              </template>
            </HqTable>
          </div>

          <!-- SplitPane with Virtual List & Tree -->
          <div class="bg-panel border border-border rounded-[var(--radius-md)] p-5 space-y-3">
            <h3 class="text-sm font-semibold text-content-primary border-b border-border-subtle pb-2 flex items-center justify-between">
              <span>HqSplitPane + 虚拟列表 (10,000 条事件流 60fps 平滑滚动) + HqTree</span>
              <span class="text-xs text-accent font-mono">Total: {{ virtualItemsCount.toLocaleString() }} Items</span>
            </h3>

            <div class="h-[340px] border border-border rounded-[var(--radius-sm)]">
              <HqSplitPane :initial-ratio="0.35">
                <template #first>
                  <div class="p-3 bg-muted/20 h-full overflow-y-auto">
                    <div class="text-xs font-semibold text-content-secondary mb-2 flex items-center gap-1.5">
                      <FolderGit2 class="h-3.5 w-3.5" />
                      代码结构与事件总线树
                    </div>
                    <HqTree :nodes="treeNodes" />
                  </div>
                </template>
                <template #second>
                  <div class="h-full flex flex-col p-2 bg-panel">
                    <div class="text-xs font-mono text-content-muted mb-1 px-1">
                      高性能虚拟列表渲染 (DOM 节点仅按需复用):
                    </div>
                    <HqVirtualList
                      :items="largeEventList"
                      :item-height="30"
                      container-height="300px"
                    >
                      <template #default="{ item }">
                        <div class="flex items-center justify-between px-2.5 py-1 text-xs border-b border-border-subtle/60 hover:bg-muted/50 transition-colors font-mono">
                          <span class="text-content-muted text-[10px] w-14 shrink-0">#{{ item.seq }}</span>
                          <span class="text-content-primary truncate flex-1">{{ item.text }}</span>
                          <span class="text-[10px] text-content-muted ml-2 shrink-0">{{ item.timestamp }}</span>
                        </div>
                      </template>
                    </HqVirtualList>
                  </div>
                </template>
              </HqSplitPane>
            </div>
          </div>

          <!-- Markdown & CodeBlock -->
          <div class="bg-panel border border-border rounded-[var(--radius-md)] p-5 space-y-3">
            <h3 class="text-sm font-semibold text-content-primary border-b border-border-subtle pb-2 flex items-center gap-2">
              <FileCode class="h-4 w-4 text-accent" />
              HqMarkdown 安全解析渲染器
            </h3>
            <div class="p-4 bg-muted/20 border border-border rounded-[var(--radius-sm)]">
              <HqMarkdown :content="sampleMarkdown" />
            </div>
          </div>
        </section>

        <!-- ==================== TAB 4: Theme & Role Swatches ==================== -->
        <section v-if="activeTab === 'theme-colors'" class="space-y-6">
          <!-- 4 Palettes Comparison -->
          <div class="bg-panel border border-border rounded-[var(--radius-md)] p-5 space-y-4">
            <h3 class="text-sm font-semibold text-content-primary border-b border-border-subtle pb-2">
              四套品牌 Palette 对照 (当前激活: {{ theme.palette }})
            </h3>
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div
                v-for="(meta, pKey) in PALETTES_META"
                :key="pKey"
                :class="[
                  'p-4 rounded-[var(--radius-md)] border transition-all cursor-pointer select-none',
                  theme.palette === pKey ? 'border-action-primary ring-2 ring-ring bg-accent-soft/10' : 'border-border bg-panel hover:border-border-strong'
                ]"
                @click="theme.setPalette(pKey as any)"
              >
                <div class="flex items-center justify-between mb-2">
                  <span class="text-xs font-bold text-content-primary">{{ meta.name }}</span>
                  <span class="h-3 w-3 rounded-full" :style="{ backgroundColor: meta.primaryHex }" />
                </div>
                <p class="text-[11px] text-content-muted leading-relaxed mb-3">{{ meta.description }}</p>
                <div class="flex items-center gap-1.5 font-mono text-[10px] text-content-secondary">
                  <span class="px-1.5 py-0.5 rounded bg-muted">{{ meta.primaryHex }}</span>
                  <span class="px-1.5 py-0.5 rounded bg-muted">{{ meta.darkAccentHex }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 8 Built-in Role Colors -->
          <div class="bg-panel border border-border rounded-[var(--radius-md)] p-5 space-y-4">
            <h3 class="text-sm font-semibold text-content-primary border-b border-border-subtle pb-2">
              8 个内置角色色阶与标签 (独立于厂商与运行状态)
            </h3>
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div class="p-2.5 rounded border border-border bg-panel flex items-center justify-between">
                <div>
                  <div class="font-medium text-content-primary">orchestrator</div>
                  <div class="text-[10px] text-content-muted">总控调度</div>
                </div>
                <HqBadge variant="role" role="orchestrator">Violet</HqBadge>
              </div>

              <div class="p-2.5 rounded border border-border bg-panel flex items-center justify-between">
                <div>
                  <div class="font-medium text-content-primary">architect</div>
                  <div class="text-[10px] text-content-muted">系统架构</div>
                </div>
                <HqBadge variant="role" role="architect">Indigo</HqBadge>
              </div>

              <div class="p-2.5 rounded border border-border bg-panel flex items-center justify-between">
                <div>
                  <div class="font-medium text-content-primary">frontend_implementer</div>
                  <div class="text-[10px] text-content-muted">前端实现</div>
                </div>
                <HqBadge variant="role" role="frontend">Cyan</HqBadge>
              </div>

              <div class="p-2.5 rounded border border-border bg-panel flex items-center justify-between">
                <div>
                  <div class="font-medium text-content-primary">general_implementer</div>
                  <div class="text-[10px] text-content-muted">全栈实现</div>
                </div>
                <HqBadge variant="role" role="implementer">Blue</HqBadge>
              </div>

              <div class="p-2.5 rounded border border-border bg-panel flex items-center justify-between">
                <div>
                  <div class="font-medium text-content-primary">reviewer</div>
                  <div class="text-[10px] text-content-muted">代码审查</div>
                </div>
                <HqBadge variant="role" role="reviewer">Amber</HqBadge>
              </div>

              <div class="p-2.5 rounded border border-border bg-panel flex items-center justify-between">
                <div>
                  <div class="font-medium text-content-primary">tester</div>
                  <div class="text-[10px] text-content-muted">测试验证</div>
                </div>
                <HqBadge variant="role" role="tester">Emerald</HqBadge>
              </div>

              <div class="p-2.5 rounded border border-border bg-panel flex items-center justify-between">
                <div>
                  <div class="font-medium text-content-primary">deployer</div>
                  <div class="text-[10px] text-content-muted">构建部署</div>
                </div>
                <HqBadge variant="role" role="deployer">Orange</HqBadge>
              </div>

              <div class="p-2.5 rounded border border-border bg-panel flex items-center justify-between">
                <div>
                  <div class="font-medium text-content-primary">integrator</div>
                  <div class="text-[10px] text-content-muted">分支集成</div>
                </div>
                <HqBadge variant="role" role="integrator">Slate</HqBadge>
              </div>
            </div>
          </div>
        </section>

        <!-- ==================== TAB 5: Four States Templates ==================== -->
        <section v-if="activeTab === 'four-states'" class="space-y-6">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <!-- Loading State -->
            <div class="bg-panel border border-border rounded-[var(--radius-md)] p-4 space-y-2">
              <div class="text-xs font-bold text-content-primary mb-1">[态 1] Loading (300ms 防抖骨架屏)</div>
              <LoadingState text="正在探测本机已安装的 Agent 与能力标签..." :delay="0" />
            </div>

            <!-- Empty State -->
            <div class="bg-panel border border-border rounded-[var(--radius-md)] p-4 space-y-2">
              <div class="text-xs font-bold text-content-primary mb-1">[态 2] Empty (空状态与引导操作)</div>
              <HqEmptyState
                title="当前工作区暂无历史任务"
                description="点击下方按钮提交一条新需求，Orchestrator 将自动为您指派最佳角色与执行 Agent。"
                action-text="创建首个任务"
                @action="toast.info('点击了创建首个任务')"
              />
            </div>

            <!-- Error State -->
            <div class="bg-panel border border-border rounded-[var(--radius-md)] p-4 space-y-2">
              <div class="text-xs font-bold text-content-primary mb-1">[态 3] Error (错误原因与诊断追溯)</div>
              <HqErrorState
                code="ERR_PATH_OUT_OF_BOUNDS"
                title="Git Worktree 目录越界检查被拦截"
                message="角色 frontend_implementer 试图写入 apps/hub/core/server.py，违反当前角色的 allowed_paths 授权。"
                diagnostic-id="diag_20260905_4481_x8"
                @retry="toast.info('触发重试动作')"
              />
            </div>

            <!-- Offline State -->
            <div class="bg-panel border border-border rounded-[var(--radius-md)] p-4 space-y-2">
              <div class="text-xs font-bold text-content-primary mb-1">[态 4] Offline (Local Hub 断开连接)</div>
              <OfflineState @reconnect="toast.info('正在尝试重新连接 Local Hub...')" />
            </div>
          </div>
        </section>
      </div>
    </div>

    <!-- Dialog -->
    <HqDialog
      v-model:open="dialogOpen"
      title="高风险命令审批确认"
      description="危险操作二次确认：此操作将直接影响远程或本地仓库。"
    >
      <div class="space-y-3">
        <div class="p-3 bg-status-danger-soft/20 border border-status-danger/30 rounded text-xs">
          <div class="font-semibold text-status-danger mb-1">即将执行敏感指令:</div>
          <div class="font-mono bg-code p-1.5 rounded text-content-primary">git push origin feat/f0-desktop-skeleton</div>
        </div>
        <p class="text-xs text-content-secondary">
          请求 Agent: <strong class="text-content-primary">Codex App Server</strong> (承担 deployer 角色)。
        </p>
      </div>
      <template #footer="{ close }">
        <HqButton variant="secondary" size="sm" @click="close">拒绝</HqButton>
        <HqButton variant="danger" size="sm" @click="toast.success('已批准此危险操作'); close()">
          批准本次命令
        </HqButton>
      </template>
    </HqDialog>

    <!-- Drawer -->
    <HqDrawer v-model:open="drawerOpen" title="Context Inspector 抽屉详情" width="380px">
      <div class="space-y-4 text-xs">
        <div>
          <div class="font-semibold text-content-primary mb-1">当前会话信息</div>
          <div class="font-mono text-content-muted bg-muted p-2 rounded break-all">
            session-claude-uuid-7718-20260905
          </div>
        </div>
        <div>
          <div class="font-semibold text-content-primary mb-1">权限策略约束</div>
          <ul class="list-disc list-inside space-y-1 text-content-secondary">
            <li>允许写入: apps/desktop/src/**</li>
            <li>禁止 Shell 提权</li>
            <li>危险操作强制拦截审批</li>
          </ul>
        </div>
      </div>
      <template #footer="{ close }">
        <HqButton size="sm" variant="secondary" @click="close">关闭</HqButton>
      </template>
    </HqDrawer>

    <!-- Toast Container -->
    <HqToast />
  </div>
</template>
