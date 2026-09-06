<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app.store'
import { useSessionStore } from '@/stores/session.store'
import type { SessionStatus } from '@hqagent/protocol'
import {
  MessageSquare,
  Search,
  RotateCcw,
  UserCheck,
  FolderGit2,
  Copy,
} from 'lucide-vue-next'
import {
  HqButton,
  HqBadge,
  HqInput,
  HqTextarea,
  HqDialog,
  HqTooltip,
  LoadingState,
  HqEmptyState,
  HqErrorState,
  OfflineState,
  useToast,
} from '@/shared/ui'

const router = useRouter()
const appStore = useAppStore()
const sessionStore = useSessionStore()
const toast = useToast()

// Resume Modal State
const isResumeModalOpen = ref(false)
const resumingSessionId = ref<string | null>(null)
const resumeInstruction = ref('')
const resumeAcceptance = ref('')
const resumeError = ref<string | null>(null)

onMounted(async () => {
  await sessionStore.fetchSessions()
})

const statusFilters: { label: string; value: SessionStatus | 'all' }[] = [
  { label: '全部', value: 'all' },
  { label: '活跃中 (Active)', value: 'active' },
  { label: '空闲可续接 (Idle)', value: 'idle' },
  { label: '已结束 (Closed)', value: 'closed' },
  { label: '已失效 (Invalid)', value: 'invalid' },
]

function getStatusBadge(status: SessionStatus, isValid: boolean) {
  if (!isValid || status === 'invalid') {
    return {
      label: '已失效 (不可续接)',
      variant: 'danger' as const,
      class: 'bg-danger/15 text-danger border-danger/30',
    }
  }
  switch (status) {
    case 'active':
      return {
        label: '执行中 (Active)',
        variant: 'primary' as const,
        class: 'bg-primary/15 text-primary border-primary/30 animate-pulse',
      }
    case 'idle':
      return {
        label: '空闲可续接 (Idle)',
        variant: 'success' as const,
        class: 'bg-success/15 text-success border-success/30',
      }
    case 'closed':
      return {
        label: '已结束 (Closed)',
        variant: 'neutral' as const,
        class: 'bg-panel text-text-muted border-border',
      }
    default:
      return { label: status, variant: 'neutral' as const, class: '' }
  }
}

function openResumeModal(sessionId: string) {
  resumingSessionId.value = sessionId
  resumeInstruction.value = ''
  resumeAcceptance.value = ''
  resumeError.value = null
  isResumeModalOpen.value = true
}

async function handleConfirmResume() {
  if (!resumingSessionId.value) return
  if (!resumeInstruction.value.trim()) {
    resumeError.value = '请输入继续执行该会话的明确指令'
    return
  }

  const acceptance = resumeAcceptance.value
    ? resumeAcceptance.value.split('\n').map((s) => s.trim()).filter(Boolean)
    : undefined

  try {
    const newTask = await sessionStore.resumeSession(resumingSessionId.value, {
      instruction: resumeInstruction.value.trim(),
      acceptance,
    })
    isResumeModalOpen.value = false
    router.push(`/tasks/${newTask.id}`)
  } catch (err: unknown) {
    resumeError.value = err instanceof Error ? err.message : '恢复会话失败'
  }
}

function copyToClipboard(text: string) {
  navigator.clipboard?.writeText(text)
  toast.success('已复制到剪贴板')
}

function formatTime(timestamp?: string) {
  if (!timestamp) return '-'
  return new Date(timestamp).toLocaleString()
}
</script>

<template>
  <div class="p-6 space-y-6 max-w-7xl mx-auto select-none">
    <!-- Top Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <div class="p-2 bg-primary/10 text-primary rounded-[var(--radius-md)]">
          <MessageSquare class="w-6 h-6" />
        </div>
        <div>
          <h1 class="text-xl font-bold text-text">会话历史</h1>
          <p class="text-sm text-text-muted">
            管理与续接 Agent 底层会话上下文，按谱系查看与显式恢复执行
          </p>
        </div>
      </div>

      <div class="flex items-center gap-2 text-xs text-text-muted">
        <span>共 {{ sessionStore.totalSessions }} 个会话记录</span>
      </div>
    </div>

    <!-- Filter Toolbar -->
    <div class="flex flex-wrap items-center justify-between gap-4 p-4 bg-panel rounded-[var(--radius-md)] border border-border">
      <!-- Status Tabs -->
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="tab in statusFilters"
          :key="tab.value"
          class="px-3 py-1.5 rounded-[var(--radius-sm)] text-xs font-medium transition-colors"
          :class="
            sessionStore.filterStatus === tab.value
              ? 'bg-primary text-white shadow-xs'
              : 'text-text-muted hover:bg-hover hover:text-text'
          "
          @click="sessionStore.filterStatus = tab.value"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- Search & Options -->
      <div class="flex items-center gap-3 w-full sm:w-auto">
        <div class="relative flex-1 sm:w-64">
          <Search class="absolute left-3 top-2.5 w-4 h-4 text-text-muted" />
          <input
            v-model="sessionStore.searchQuery"
            type="text"
            placeholder="搜索会话 ID 或 Agent..."
            class="w-full pl-9 pr-3 py-1.5 text-xs bg-surface border border-border rounded-[var(--radius-sm)] focus:outline-none focus:ring-1 focus:ring-primary text-text placeholder:text-text-muted"
          />
        </div>

        <label class="inline-flex items-center gap-1.5 text-xs text-text-muted hover:text-text cursor-pointer">
          <input v-model="sessionStore.filterOnlyValid" type="checkbox" class="rounded border-border" />
          仅显示有效会话
        </label>
      </div>
    </div>

    <!-- 4 Page States -->
    <OfflineState v-if="appStore.isOffline" @retry="sessionStore.fetchSessions" />
    <LoadingState v-else-if="sessionStore.isLoading" message="正在加载会话列表..." />
    <HqErrorState
      v-else-if="sessionStore.error"
      title="获取会话列表失败"
      :message="sessionStore.error"
      @retry="sessionStore.fetchSessions"
    />
    <HqEmptyState
      v-else-if="sessionStore.filteredSessions.length === 0"
      title="暂无会话记录"
      message="当前没有匹配筛选条件的会话。在任务执行时将自动建立各角色的会话。"
    />

    <!-- Sessions List -->
    <div v-else class="space-y-3">
      <div
        v-for="sess in sessionStore.filteredSessions"
        :key="sess.id"
        class="p-5 bg-panel rounded-[var(--radius-md)] border border-border shadow-xs hover:border-primary/40 transition-colors space-y-3"
      >
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-3">
          <div class="flex flex-wrap items-center gap-2">
            <span class="font-mono text-xs font-bold text-text">{{ sess.id }}</span>
            <HqBadge
              :variant="getStatusBadge(sess.status, sess.isValid).variant"
              size="sm"
              :class="getStatusBadge(sess.status, sess.isValid).class"
            >
              {{ getStatusBadge(sess.status, sess.isValid).label }}
            </HqBadge>

            <span class="px-2 py-0.5 text-[11px] rounded bg-secondary/10 text-secondary border border-secondary/20 font-medium">
              {{ sess.purpose }}
            </span>
          </div>

          <!-- Actions -->
          <div class="flex items-center gap-2">
            <HqTooltip
              :content="
                !sess.isValid
                  ? '外部会话已失效或不支持续接 (SESSION_NOT_RESUMABLE)，请重新新建任务'
                  : '恢复该会话的记忆上下文并启动新一轮任务'
              "
            >
              <div>
                <HqButton
                  variant="primary"
                  size="sm"
                  :disabled="!sess.isValid || sessionStore.isResuming"
                  @click="openResumeModal(sess.id)"
                >
                  <RotateCcw class="w-3.5 h-3.5 mr-1" />
                  恢复会话
                </HqButton>
              </div>
            </HqTooltip>
          </div>
        </div>

        <!-- Session Details Row -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
          <div>
            <span class="text-text-muted block mb-1">执行 Agent:</span>
            <span class="font-medium text-text flex items-center gap-1">
              <UserCheck class="w-3.5 h-3.5 text-primary" />
              {{ sess.agentDisplayName }}
            </span>
          </div>

          <div>
            <span class="text-text-muted block mb-1">所属工作区:</span>
            <span class="font-medium text-text flex items-center gap-1">
              <FolderGit2 class="w-3.5 h-3.5" />
              {{ sess.workspaceName }}
            </span>
          </div>

          <div>
            <span class="text-text-muted block mb-1">外部底层会话 ID:</span>
            <!--
              裁决 D28：externalSessionId 可缺省。缺省不等于"数据没加载出来"，
              而是这个 Agent 本身不支持会话恢复——要如实说出来，
              否则用户会以为是 bug，也看不懂为什么"继续"按钮是灰的。
            -->
            <div
              v-if="sess.externalSessionId"
              class="flex items-center gap-1.5 font-mono text-[11px] text-text-muted"
            >
              <span class="truncate max-w-[140px]" :title="sess.externalSessionId">
                {{ sess.externalSessionId }}
              </span>
              <button
                class="hover:text-text transition-colors"
                title="复制外部会话 ID"
                @click="copyToClipboard(sess.externalSessionId)"
              >
                <Copy class="w-3.5 h-3.5" />
              </button>
            </div>
            <div v-else class="text-[11px] text-text-muted italic">
              该 Agent 不支持会话恢复
            </div>
          </div>

          <div>
            <span class="text-text-muted block mb-1">最后活跃时间:</span>
            <span class="text-text">{{ formatTime(sess.lastUsedAt) }}</span>
          </div>
        </div>

        <div v-if="sess.summary" class="text-xs bg-surface p-3 rounded-[var(--radius-sm)] border border-border text-text">
          <span class="font-semibold text-text-muted mr-1">会话概要:</span>
          {{ sess.summary }}
        </div>
      </div>
    </div>

    <!-- Resume Session Modal -->
    <HqDialog
      :open="isResumeModalOpen"
      title="恢复并续接会话"
      description="恢复该会话将保留该 Agent 之前的历史上下文与记忆"
      @close="isResumeModalOpen = false"
    >
      <div class="space-y-4 py-2 text-xs">
        <p class="text-text leading-relaxed">
          恢复该会话将保留该 Agent 之前的历史上下文与记忆，并开启一个以本指令为核心的新任务。
        </p>

        <div>
          <label class="block font-medium text-text mb-1">
            续接执行指令 <span class="text-danger">*</span>
          </label>
          <HqTextarea
            v-model="resumeInstruction"
            :rows="3"
            placeholder="例如：请继续按照上次的架构设计方案补充端到端测试用例..."
          />
        </div>

        <div>
          <label class="block font-medium text-text mb-1">
            验收验证命令 (可选，每行一条)
          </label>
          <HqInput
            v-model="resumeAcceptance"
            placeholder="npm test"
          />
        </div>

        <div
          v-if="resumeError"
          class="p-2.5 rounded-[var(--radius-sm)] bg-danger/10 text-danger border border-danger/20"
        >
          {{ resumeError }}
        </div>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-2">
          <HqButton size="sm" variant="secondary" @click="isResumeModalOpen = false">
            取消
          </HqButton>
          <HqButton
            size="sm"
            variant="primary"
            :disabled="!resumeInstruction.trim() || sessionStore.isResuming"
            @click="handleConfirmResume"
          >
            确认恢复
          </HqButton>
        </div>
      </template>
    </HqDialog>
  </div>
</template>
