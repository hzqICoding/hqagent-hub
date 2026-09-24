<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ActivityItem } from '@/stores/chat.store'
import {
  ChevronDown,
  ChevronRight,
  FileCode2,
  Terminal,
  Sparkles,
  Wrench,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
} from 'lucide-vue-next'

interface Props {
  activities: ActivityItem[]
  isLive?: boolean
  initiallyExpanded?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  activities: () => [],
  isLive: false,
  initiallyExpanded: false,
})

const isExpanded = ref(props.initiallyExpanded ?? props.isLive)
const expandedItemIds = ref<Set<string>>(new Set())
const copiedItemId = ref<string | null>(null)

function toggleItemDetail(id: string) {
  if (expandedItemIds.value.has(id)) {
    expandedItemIds.value.delete(id)
  } else {
    expandedItemIds.value.add(id)
  }
}

async function copyDetail(text: string, id: string) {
  try {
    await navigator.clipboard.writeText(text)
    copiedItemId.value = id
    setTimeout(() => {
      if (copiedItemId.value === id) copiedItemId.value = null
    }, 1800)
  } catch {
    // ignore
  }
}

// Counts
const fileCount = computed(() => props.activities.filter((a) => a.type === 'file').length)
const commandCount = computed(() => props.activities.filter((a) => a.type === 'command').length)
const hasFailures = computed(() => props.activities.some((a) => a.status === 'failed'))

// Summary title matching screenshot: "Exploring 13 files, running 1 command"
const summaryTitle = computed(() => {
  if (props.isLive && props.activities.length === 0) {
    return '正在分析任务并准备执行环境...'
  }
  const parts: string[] = []
  if (fileCount.value > 0) {
    parts.push(props.isLive ? `探索 ${fileCount.value} 个文件` : `已探索 ${fileCount.value} 个文件`)
  }
  if (commandCount.value > 0) {
    parts.push(props.isLive ? `运行 ${commandCount.value} 条命令` : `已运行 ${commandCount.value} 条命令`)
  }
  if (parts.length > 0) {
    return props.isLive ? `正在 ${parts.join('，')}...` : parts.join('，')
  }
  if (props.activities.length > 0) {
    return props.isLive
      ? `正在执行 (${props.activities.length} 个步骤)...`
      : `执行了 ${props.activities.length} 个步骤`
  }
  return props.isLive ? '正在执行任务...' : '执行过程记录'
})
</script>

<template>
  <div class="my-2 rounded-xl border border-border/70 bg-panel/40 overflow-hidden shadow-xs transition-all">
    <!-- Header button -->
    <button
      type="button"
      class="w-full p-2.5 px-3 flex items-center justify-between text-xs hover:bg-panel transition-colors text-left gap-2 select-none cursor-pointer"
      @click="isExpanded = !isExpanded"
    >
      <div class="flex items-center gap-2 min-w-0">
        <!-- Live spinner or status icon -->
        <div v-if="isLive" class="w-4 h-4 flex items-center justify-center shrink-0 text-primary">
          <span class="inline-flex items-center justify-center animate-spin spin-indicator">
            <Loader2 class="w-3.5 h-3.5" />
          </span>
        </div>
        <div v-else-if="hasFailures" class="w-4 h-4 flex items-center justify-center shrink-0 text-danger">
          <AlertCircle class="w-3.5 h-3.5" />
        </div>
        <div v-else class="w-4 h-4 flex items-center justify-center shrink-0 text-success">
          <CheckCircle2 class="w-3.5 h-3.5" />
        </div>

        <span class="font-medium text-text text-xs truncate">
          {{ summaryTitle }}
        </span>

        <!-- Step count pill -->
        <span
          v-if="activities.length > 0"
          class="px-1.5 py-0.5 rounded-full bg-panel-hover border border-border/60 text-[10px] text-text-muted font-mono shrink-0"
        >
          {{ activities.length }} 步
        </span>
      </div>

      <div class="flex items-center gap-1.5 shrink-0 text-text-muted">
        <span class="text-[10px] hidden sm:inline">
          {{ isExpanded ? '收起详情' : '展开详情' }}
        </span>
        <ChevronDown
          class="w-3.5 h-3.5 transition-transform duration-200"
          :class="isExpanded ? 'rotate-180' : ''"
        />
      </div>
    </button>

    <!-- Body timeline -->
    <div
      v-if="isExpanded && activities.length > 0"
      class="p-2.5 px-3 border-t border-border/50 bg-bg-app/50 max-h-72 overflow-y-auto space-y-1.5"
    >
      <div
        v-for="item in activities"
        :key="item.id"
        class="group/item rounded-lg p-1.5 px-2 hover:bg-panel/70 transition-colors text-xs"
      >
        <div class="flex items-center justify-between gap-2 min-w-0">
          <div class="flex items-center gap-2 min-w-0 flex-1">
            <!-- Icon by type -->
            <FileCode2
              v-if="item.type === 'file'"
              class="w-3.5 h-3.5 text-info shrink-0"
            />
            <Terminal
              v-else-if="item.type === 'command'"
              class="w-3.5 h-3.5 text-warning shrink-0"
            />
            <Sparkles
              v-else-if="item.type === 'thought'"
              class="w-3.5 h-3.5 text-primary/70 shrink-0"
            />
            <Wrench
              v-else
              class="w-3.5 h-3.5 text-text-muted shrink-0"
            />

            <!-- Verb (dim label) -->
            <span class="text-[11px] text-text-muted shrink-0 font-medium">
              {{ item.verb }}
            </span>

            <!-- Target (mono code or text) -->
            <span
              class="text-[11px] font-mono text-text truncate select-all"
              :title="item.target"
            >
              {{ item.target }}
            </span>
          </div>

          <!-- Right side: duration / expand toggle -->
          <div class="flex items-center gap-1.5 shrink-0">
            <span
              v-if="item.durationMs"
              class="text-[10px] text-text-muted font-mono"
            >
              {{ Math.round(item.durationMs / 100) / 10 }}s
            </span>

            <!-- Detail toggle chevron -->
            <button
              v-if="item.detail"
              type="button"
              class="p-0.5 rounded hover:bg-panel text-text-muted hover:text-text transition-colors flex items-center cursor-pointer"
              :title="expandedItemIds.has(item.id) ? '收起输出' : '展开输出'"
              @click.stop="toggleItemDetail(item.id)"
            >
              <ChevronRight
                class="w-3 h-3 transition-transform duration-150"
                :class="expandedItemIds.has(item.id) ? 'rotate-90' : ''"
              />
            </button>
          </div>
        </div>

        <!-- Collapsible detail / output preview -->
        <div
          v-if="item.detail && expandedItemIds.has(item.id)"
          class="mt-1.5 p-2 rounded-md bg-panel border border-border/60 text-[10px] font-mono text-text/85 relative group/detail"
        >
          <button
            type="button"
            class="absolute top-1.5 right-1.5 p-1 rounded bg-bg-app hover:bg-panel-hover border border-border/60 text-text-muted hover:text-text transition-all text-[9px] flex items-center gap-1 opacity-0 group-hover/detail:opacity-100"
            @click.stop="copyDetail(item.detail, item.id)"
          >
            <Check v-if="copiedItemId === item.id" class="w-2.5 h-2.5 text-success" />
            <Copy v-else class="w-2.5 h-2.5" />
            <span>{{ copiedItemId === item.id ? '已复制' : '复制' }}</span>
          </button>
          <pre class="overflow-x-auto whitespace-pre-wrap select-text max-h-36 leading-relaxed">{{ item.detail }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.spin-indicator {
  display: inline-flex;
  transform-origin: center center;
  animation: hq-spin-rotate 1s linear infinite !important;
}

@keyframes hq-spin-rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>

