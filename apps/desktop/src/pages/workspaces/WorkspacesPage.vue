<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useAppStore } from '@/stores/app.store'
import { useWorkspaceStore } from '@/stores/workspace.store'
import { useTeamStore } from '@/stores/team.store'
import {
  FolderGit2,
  Plus,
  GitBranch,
  CheckCircle2,
  AlertTriangle,
  Database,
  Trash2,
  Copy,
  Users,
} from 'lucide-vue-next'
import {
  HqButton,
  HqBadge,
  HqInput,
  HqDialog,
  LoadingState,
  HqEmptyState,
  HqErrorState,
  OfflineState,
} from '@/shared/ui'

const appStore = useAppStore()
const workspaceStore = useWorkspaceStore()
const teamStore = useTeamStore()

const isAddModalOpen = ref(false)
const newPath = ref('')
const newName = ref('')
const addError = ref<string | null>(null)

onMounted(async () => {
  await Promise.all([
    workspaceStore.fetchWorkspaces(),
    teamStore.fetchProfiles(),
  ])
})

const stats = computed(() => {
  const list = workspaceStore.workspaces
  return {
    total: list.length,
    gitCount: list.filter((w) => w.vcs === 'git').length,
    memoryCount: list.filter((w) => w.memoryDirPresent).length,
  }
})

function handleOpenAdd() {
  newPath.value = ''
  newName.value = ''
  addError.value = null
  isAddModalOpen.value = true
}

function handleConfirmAdd() {
  if (!newPath.value.trim()) {
    addError.value = '请输入目录绝对路径'
    return
  }
  try {
    workspaceStore.addWorkspace(newPath.value.trim(), newName.value.trim() || undefined)
    isAddModalOpen.value = false
  } catch (err: unknown) {
    addError.value = err instanceof Error ? err.message : '添加工作区失败'
  }
}

function copyPath(path: string) {
  navigator.clipboard.writeText(path)
  appStore.addLog({
    level: 'info',
    source: 'Workspaces',
    message: `已复制路径: ${path}`,
  })
}

function getTeamProfileName(profileId?: string): string {
  if (!profileId) return '全局默认'
  const found = teamStore.profiles.find((p) => p.id === profileId)
  return found ? found.name : profileId
}

function formatRelativeTime(isoStr: string): string {
  try {
    const diffMs = Date.now() - new Date(isoStr).getTime()
    const mins = Math.floor(diffMs / 60000)
    if (mins < 1) return '刚刚'
    if (mins < 60) return `${mins} 分钟前`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours} 小时前`
    const days = Math.floor(hours / 24)
    return `${days} 天前`
  } catch {
    return isoStr
  }
}
</script>

<template>
  <div class="p-6 space-y-6 max-w-7xl mx-auto select-none">
    <!-- Header & Actions -->
    <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
      <div>
        <h2 class="text-base font-bold text-content-primary">工作区与项目管理</h2>
        <p class="text-xs text-content-muted">
          管理本地开发目录、Git 隔离环境与 .hqagent/ 共享记忆上下文
        </p>
      </div>

      <div class="flex items-center gap-2">
        <HqButton size="sm" variant="primary" @click="handleOpenAdd">
          <template #icon>
            <Plus class="w-3.5 h-3.5" />
          </template>
          添加目录
        </HqButton>
      </div>
    </div>

    <!-- 4 States Handling -->
    <OfflineState
      v-if="appStore.isOffline"
      description="Local Hub 当前处于离线状态，工作区列表与 Git 状态暂时无法实时同步"
      @retry="workspaceStore.fetchWorkspaces"
    />

    <HqErrorState
      v-else-if="workspaceStore.error"
      :error="workspaceStore.error"
      @retry="workspaceStore.fetchWorkspaces"
    />

    <LoadingState
      v-else-if="workspaceStore.isLoading"
      description="正在扫描工作区元数据与版本控制状态..."
    />

    <HqEmptyState
      v-else-if="workspaceStore.workspaces.length === 0"
      title="未添加任何工作区"
      description="添加本地代码仓库目录，开启多 Agent 协同开发与代码审查"
      action-text="添加工作区目录"
      @action="handleOpenAdd"
    />

    <!-- Main Content -->
    <div v-else class="space-y-6">
      <!-- Summary KPI Bento -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div class="p-4 rounded-xl bg-surface-card border border-border-subtle flex items-center gap-3">
          <div class="w-10 h-10 rounded-lg bg-surface-raised border border-border-subtle flex items-center justify-center text-primary-600">
            <FolderGit2 class="w-5 h-5" />
          </div>
          <div>
            <div class="text-2xs text-content-muted font-medium">受管工作区总数</div>
            <div class="text-lg font-bold text-content-primary">{{ stats.total }} <span class="text-xs font-normal text-content-muted">个</span></div>
          </div>
        </div>

        <div class="p-4 rounded-xl bg-surface-card border border-border-subtle flex items-center gap-3">
          <div class="w-10 h-10 rounded-lg bg-surface-raised border border-border-subtle flex items-center justify-center text-primary-600">
            <GitBranch class="w-5 h-5" />
          </div>
          <div>
            <div class="text-2xs text-content-muted font-medium">Git 版本控制支持</div>
            <div class="text-lg font-bold text-content-primary">{{ stats.gitCount }} <span class="text-xs font-normal text-content-muted">/ {{ stats.total }}</span></div>
          </div>
        </div>

        <div class="p-4 rounded-xl bg-surface-card border border-border-subtle flex items-center gap-3">
          <div class="w-10 h-10 rounded-lg bg-surface-raised border border-border-subtle flex items-center justify-center text-primary-600">
            <Database class="w-5 h-5" />
          </div>
          <div>
            <div class="text-2xs text-content-muted font-medium">共享记忆就绪 (.hqagent/)</div>
            <div class="text-lg font-bold text-content-primary">{{ stats.memoryCount }} <span class="text-xs font-normal text-content-muted">/ {{ stats.total }}</span></div>
          </div>
        </div>
      </div>

      <!-- Workspace List Cards -->
      <div class="space-y-3">
        <div
          v-for="ws in workspaceStore.recentWorkspaces"
          :key="ws.id"
          class="p-4 rounded-xl bg-surface-card border transition-all duration-200"
          :class="workspaceStore.currentWorkspace?.id === ws.id ? 'border-primary-500 shadow-sm' : 'border-border-subtle hover:border-border-default'"
        >
          <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <!-- Left Info -->
            <div class="space-y-2 flex-1 min-w-0">
              <div class="flex items-center gap-2.5 flex-wrap">
                <span class="text-sm font-bold text-content-primary truncate">{{ ws.name }}</span>
                <HqBadge v-if="workspaceStore.currentWorkspace?.id === ws.id" variant="primary" size="sm">
                  当前工作区
                </HqBadge>

                <!-- Git status -->
                <HqBadge v-if="ws.vcs === 'git'" variant="neutral" size="sm">
                  <GitBranch class="w-3 h-3 mr-1" />
                  {{ ws.branch || 'main' }}
                </HqBadge>
                <HqBadge v-if="ws.isClean" variant="success" size="sm">
                  <CheckCircle2 class="w-3 h-3 mr-1" />
                  工作区干净
                </HqBadge>
                <HqBadge v-else-if="ws.isClean === false" variant="warning" size="sm">
                  <AlertTriangle class="w-3 h-3 mr-1" />
                  有未提交改动
                </HqBadge>

                <!-- Memory status -->
                <HqBadge v-if="ws.memoryDirPresent" variant="success" size="sm">
                  <Database class="w-3 h-3 mr-1" />
                  .hqagent 记忆已就绪
                </HqBadge>
                <HqBadge v-else variant="neutral" size="sm">
                  <Database class="w-3 h-3 mr-1" />
                  记忆未初始化
                </HqBadge>
              </div>

              <!-- Path with copy -->
              <div class="flex items-center gap-2 text-2xs text-content-muted font-mono">
                <span class="truncate">{{ ws.path }}</span>
                <button
                  class="p-0.5 hover:text-content-primary rounded transition-colors"
                  title="复制路径"
                  @click="copyPath(ws.path)"
                >
                  <Copy class="w-3 h-3" />
                </button>
              </div>

              <!-- Extra Meta & Team Profile -->
              <div class="flex items-center gap-4 text-2xs text-content-secondary flex-wrap pt-1">
                <div class="flex items-center gap-1.5">
                  <Users class="w-3.5 h-3.5 text-content-muted" />
                  <span>团队配置:</span>
                  <span class="font-medium text-content-primary">{{ getTeamProfileName(ws.defaultProfileId) }}</span>
                </div>
                <div>
                  <span class="text-content-muted">最近打开: </span>
                  <span>{{ formatRelativeTime(ws.lastOpenedAt) }}</span>
                </div>
              </div>
            </div>

            <!-- Actions -->
            <div class="flex items-center gap-2 self-end md:self-center flex-shrink-0">
              <HqButton
                v-if="!ws.memoryDirPresent"
                size="sm"
                variant="secondary"
                @click="workspaceStore.initMemoryDir(ws.id)"
              >
                <template #icon>
                  <Database class="w-3 h-3 text-primary-600" />
                </template>
                初始化记忆
              </HqButton>

              <HqButton
                v-if="workspaceStore.currentWorkspace?.id !== ws.id"
                size="sm"
                variant="secondary"
                @click="workspaceStore.switchWorkspace(ws.id)"
              >
                切换为此项目
              </HqButton>

              <HqButton
                size="sm"
                variant="ghost"
                class="text-rose-600 hover:text-rose-700 hover:bg-rose-50 dark:hover:bg-rose-950/40"
                title="从列表移除工作区"
                @click="workspaceStore.removeWorkspace(ws.id)"
              >
                <Trash2 class="w-3.5 h-3.5" />
              </HqButton>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Add Workspace Modal -->
    <HqDialog
      :open="isAddModalOpen"
      title="添加工作区目录"
      description="添加本机已有的代码目录，支持 Git 仓库及多工作树隔离"
      @close="isAddModalOpen = false"
    >
      <div class="space-y-4 py-2">
        <div class="space-y-1.5">
          <label class="text-xs font-semibold text-content-primary">目录绝对路径</label>
          <HqInput
            v-model="newPath"
            placeholder="例如: E:/Projects/MyAwesomeApp"
          />
        </div>

        <div class="space-y-1.5">
          <label class="text-xs font-semibold text-content-primary">项目显示名称 (可选)</label>
          <HqInput
            v-model="newName"
            placeholder="留空则自动取路径最后一级文件夹名"
          />
        </div>

        <p v-if="addError" class="text-2xs text-rose-600 dark:text-rose-400">
          {{ addError }}
        </p>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-2">
          <HqButton size="sm" variant="secondary" @click="isAddModalOpen = false">
            取消
          </HqButton>
          <HqButton size="sm" variant="primary" @click="handleConfirmAdd">
            确认添加
          </HqButton>
        </div>
      </template>
    </HqDialog>
  </div>
</template>
