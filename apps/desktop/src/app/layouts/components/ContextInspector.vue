<script setup lang="ts">
import { computed } from 'vue'
import { useAppStore } from '@/stores/app.store'
import { useAgentStore } from '@/stores/agent.store'
import type { AgentView } from '@hqagent/protocol'
import {
  X,
  Bot,
  CheckCircle2,
  AlertTriangle,
  Layers,
  Info,
} from 'lucide-vue-next'
import { HqBadge, HqButton } from '@/shared/ui'

const appStore = useAppStore()
const agentStore = useAgentStore()

const agentData = computed<AgentView | null>(() => {
  if (appStore.inspector.type === 'agent' && appStore.inspector.data) {
    return appStore.inspector.data as AgentView
  }
  return null
})

function getStatusBadgeVariant(status: string): 'neutral' | 'success' | 'warning' | 'danger' {
  switch (status) {
    case 'ready':
      return 'success'
    case 'busy':
      return 'warning'
    case 'disabled':
      return 'neutral'
    case 'not_logged_in':
    case 'incompatible':
    case 'error':
    case 'offline':
      return 'danger'
    default:
      return 'neutral'
  }
}
</script>

<template>
  <aside
    v-if="appStore.inspector.isOpen"
    class="w-80 bg-panel border-l border-border-subtle flex flex-col shrink-0 transition-all duration-200 shadow-sm overflow-hidden select-none"
  >
    <!-- Inspector Header -->
    <div class="h-12 px-4 border-b border-border-subtle flex items-center justify-between shrink-0 bg-muted/20">
      <div class="flex items-center gap-2">
        <span class="text-xs font-semibold text-content-primary">上下文检视</span>
        <HqBadge v-if="appStore.inspector.type" variant="neutral" size="sm">
          {{ appStore.inspector.type }}
        </HqBadge>
      </div>

      <button
        type="button"
        @click="appStore.closeInspector"
        class="p-1 rounded text-content-muted hover:text-content-primary hover:bg-muted transition-colors"
      >
        <X class="w-4 h-4" />
      </button>
    </div>

    <!-- Inspector Body -->
    <div class="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
      <!-- 1. AGENT INSPECTOR -->
      <template v-if="agentData">
        <!-- Title & Status -->
        <div class="flex items-start justify-between gap-2 pb-3 border-b border-border-subtle">
          <div class="flex items-center gap-2.5">
            <div class="w-9 h-9 rounded-lg bg-primary-50 dark:bg-primary-950 flex items-center justify-center text-primary-600 shrink-0">
              <Bot class="w-5 h-5" />
            </div>
            <div>
              <h3 class="font-bold text-content-primary text-sm">{{ agentData.displayName }}</h3>
              <span class="text-2xs text-content-muted font-mono">{{ agentData.adapterId }}</span>
            </div>
          </div>
          <HqBadge :variant="getStatusBadgeVariant(agentData.status)" size="sm">
            {{ agentData.status }}
          </HqBadge>
        </div>

        <!-- Diagnostic Alert (if any) -->
        <div
          v-if="agentData.diagnosticMessage"
          class="p-2.5 rounded-md bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200 text-2xs space-y-1"
        >
          <div class="font-semibold flex items-center gap-1">
            <AlertTriangle class="w-3.5 h-3.5 text-amber-600" />
            <span>诊断提示</span>
          </div>
          <p class="leading-relaxed">{{ agentData.diagnosticMessage }}</p>
        </div>

        <!-- Meta info -->
        <div class="space-y-2 bg-muted/30 p-2.5 rounded-md border border-border-subtle text-2xs">
          <div class="flex justify-between">
            <span class="text-content-muted">实例 ID:</span>
            <span class="font-mono text-content-primary truncate max-w-[170px]" :title="agentData.id">
              {{ agentData.id }}
            </span>
          </div>
          <div class="flex justify-between">
            <span class="text-content-muted">版本:</span>
            <span class="font-mono text-content-primary">v{{ agentData.version }}</span>
          </div>
          <div v-if="agentData.minimumVersion" class="flex justify-between">
            <span class="text-content-muted">要求最低版本:</span>
            <span class="font-mono text-content-primary">v{{ agentData.minimumVersion }}</span>
          </div>
          <div v-if="agentData.executablePath" class="flex flex-col gap-0.5 pt-1">
            <span class="text-content-muted">可执行文件路径:</span>
            <span class="font-mono text-content-primary break-all bg-code/50 p-1 rounded">
              {{ agentData.executablePath }}
            </span>
          </div>
        </div>

        <!-- Roles Assignment -->
        <div>
          <h4 class="text-2xs font-semibold text-content-muted uppercase tracking-wider mb-1.5">承担角色</h4>
          <div v-if="agentData.assignedRoles.length === 0" class="text-2xs text-content-disabled">
            未在当前团队 Profile 中分配角色
          </div>
          <div v-else class="flex flex-wrap gap-1.5">
            <HqBadge
              v-for="role in agentData.assignedRoles"
              :key="role"
              :variant="agentData.isPrimaryFor.includes(role) ? 'success' : 'neutral'"
              size="sm"
            >
              {{ agentData.isPrimaryFor.includes(role) ? `★ ${role}` : role }}
            </HqBadge>
          </div>
        </div>

        <!-- Capabilities -->
        <div>
          <h4 class="text-2xs font-semibold text-content-muted uppercase tracking-wider mb-1.5">
            能力清单 ({{ agentData.capabilities.length }})
          </h4>
          <div class="space-y-1">
            <div
              v-for="cap in agentData.capabilities"
              :key="cap.id"
              class="flex items-center justify-between p-1.5 rounded bg-panel border border-border-subtle text-2xs"
            >
              <div class="flex items-center gap-1.5">
                <CheckCircle2 v-if="cap.supported !== false" class="w-3 h-3 text-emerald-500 shrink-0" />
                <AlertTriangle v-else class="w-3 h-3 text-amber-500 shrink-0" />
                <span class="font-medium text-content-primary">{{ cap.name }}</span>
              </div>
              <span
                class="px-1.5 py-0.2 rounded text-3xs font-semibold uppercase"
                :class="cap.hard ? 'bg-primary-50 text-primary-600 dark:bg-primary-950' : 'bg-muted text-content-muted'"
              >
                {{ cap.hard ? '硬能力' : '软能力' }}
              </span>
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="pt-2 border-t border-border-subtle flex gap-2">
          <HqButton
            size="sm"
            class="flex-1"
            :variant="agentData.status === 'disabled' ? 'primary' : 'secondary'"
            @click="agentStore.toggleAgent(agentData.id, agentData.status === 'disabled')"
          >
            {{ agentData.status === 'disabled' ? '启用该 Agent' : '停用该 Agent' }}
          </HqButton>
        </div>
      </template>

      <!-- 2. TASK INSPECTOR -->
      <template v-else-if="appStore.inspector.type === 'task'">
        <div class="space-y-3">
          <div class="flex items-center gap-2 pb-2 border-b border-border-subtle">
            <div class="w-8 h-8 rounded-lg bg-primary-50 dark:bg-primary-950 flex items-center justify-center text-primary-600">
              <Layers class="w-4 h-4" />
            </div>
            <div>
              <h3 class="font-bold text-content-primary">当前活跃任务快照</h3>
              <span class="text-2xs text-content-muted">Local Hub 调度</span>
            </div>
          </div>

          <div v-if="appStore.bootstrap?.activeTasksCount === 0" class="text-center py-6 text-content-muted">
            当前没有正在运行的任务
          </div>
          <div v-else class="p-3 rounded-md bg-muted/40 border border-border-subtle space-y-2">
            <div class="flex justify-between text-2xs">
              <span class="text-content-muted">执行状态:</span>
              <HqBadge variant="warning" size="sm">运行中</HqBadge>
            </div>
            <div class="flex justify-between text-2xs">
              <span class="text-content-muted">待审批操作:</span>
              <HqBadge :variant="appStore.bootstrap?.pendingApprovalsCount ? 'danger' : 'neutral'" size="sm">
                {{ appStore.bootstrap?.pendingApprovalsCount || 0 }} 项
              </HqBadge>
            </div>
            <div class="text-2xs text-content-secondary pt-1">
              可在任务中心查看完整多 Agent 时间线、产物与事件流。
            </div>
          </div>
        </div>
      </template>

      <!-- 3. EMPTY / DEFAULT STATE -->
      <template v-else>
        <div class="h-64 flex flex-col items-center justify-center text-center p-4 text-content-muted space-y-2">
          <Info class="w-8 h-8 text-content-disabled stroke-1" />
          <p class="text-xs font-medium text-content-secondary">暂无上下文详情</p>
          <p class="text-2xs text-content-muted">
            在 Agent 列表或总览中点击任意项目，在此处查看实时上下文与诊断信息。
          </p>
        </div>
      </template>
    </div>
  </aside>
</template>
