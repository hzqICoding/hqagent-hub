<script setup lang="ts">
import { computed } from 'vue'
import type { ResolveSource } from '@hqagent/protocol'
import { HqBadge, HqTooltip } from '@/shared/ui'
import { AlertTriangle, UserCheck, ShieldCheck, Cpu, Layers, GitBranch } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{
    source: ResolveSource
    isFallback?: boolean
    fallbackReason?: string
    size?: 'sm' | 'md'
  }>(),
  {
    isFallback: false,
    size: 'sm',
  }
)

interface SourceMeta {
  label: string
  description: string
  variant: 'primary' | 'info' | 'success' | 'warning' | 'danger' | 'neutral'
  badgeClass: string
  icon: any
}

const meta = computed<SourceMeta>(() => {
  switch (props.source) {
    case 'task_override':
      return {
        label: '单次任务指定',
        description: '任务启动时显式指定的临时覆盖',
        variant: 'primary',
        badgeClass: 'bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border-transparent',
        icon: GitBranch,
      }
    case 'workspace_profile':
      return {
        label: '项目配置绑定',
        description: '当前工作区专属配置中指定',
        variant: 'primary',
        badgeClass: 'bg-cyan-50 dark:bg-cyan-950/60 text-cyan-700 dark:text-cyan-300 border-transparent',
        icon: ShieldCheck,
      }
    case 'global_profile':
      return {
        label: '全局团队配置',
        description: '默认全局 Team Profile 首选设置',
        variant: 'info',
        badgeClass: 'bg-purple-50 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 border-transparent',
        icon: Layers,
      }
    case 'capability_match':
      return {
        label: '动态能力匹配',
        description: '根据声明硬能力自动选定最优就绪 Agent',
        variant: 'success',
        badgeClass: 'bg-teal-50 dark:bg-teal-950/60 text-teal-700 dark:text-teal-300 border-transparent',
        icon: Cpu,
      }
    case 'fallback':
      return {
        label: '备用链降级',
        description: props.fallbackReason || '首选离线或未登录，命中备选 Agent',
        variant: 'warning',
        badgeClass: 'bg-amber-100 dark:bg-amber-950/80 text-amber-800 dark:text-amber-200 border-amber-300 dark:border-amber-700 font-semibold ring-1 ring-amber-400/40',
        icon: AlertTriangle,
      }
    case 'manual':
      return {
        label: '等待人工决策',
        description: '无可替代实例，暂停并提请用户手动干预',
        variant: 'danger',
        badgeClass: 'bg-rose-100 dark:bg-rose-950/80 text-rose-800 dark:text-rose-200 border-rose-300 dark:border-rose-700 font-semibold ring-1 ring-rose-400/40 animate-pulse',
        icon: UserCheck,
      }
    default:
      return {
        label: props.source,
        description: '未知角色来源',
        variant: 'neutral',
        badgeClass: '',
        icon: Layers,
      }
  }
})
</script>

<template>
  <div class="inline-flex items-center gap-1.5">
    <HqTooltip :content="props.fallbackReason ? `${meta.description} (${props.fallbackReason})` : meta.description">
      <HqBadge
        :variant="meta.variant"
        :size="props.size"
        class="inline-flex items-center gap-1 border shadow-xs"
        :class="meta.badgeClass"
      >
        <component :is="meta.icon" class="w-3 h-3 shrink-0" />
        <span>{{ meta.label }}</span>
      </HqBadge>
    </HqTooltip>

    <!-- Detailed Fallback Reason callout if fallback -->
    <span
      v-if="props.isFallback && props.fallbackReason"
      class="text-xs text-amber-600 dark:text-amber-400 italic max-w-xs truncate"
      :title="props.fallbackReason"
    >
      ↳ {{ props.fallbackReason }}
    </span>
  </div>
</template>
