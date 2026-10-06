<script setup lang="ts">
import { ref, computed } from 'vue'
import { Copy, Check } from 'lucide-vue-next'

interface Props {
  code: string
  language?: string
  title?: string
  showLineNumbers?: boolean
  copyable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  language: 'text',
  showLineNumbers: true,
  copyable: true,
})

const copied = ref(false)

const lines = computed(() => props.code.split('\n'))

async function copyToClipboard() {
  try {
    await navigator.clipboard.writeText(props.code)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch (err) {
    console.error('Failed to copy', err)
  }
}
</script>

<template>
  <div class="rounded-xl overflow-hidden bg-code text-content-primary text-xs font-mono">
    <!-- Header -->
    <div
      v-if="title || language || copyable"
      class="flex items-center justify-between px-3 py-1.5 bg-muted/40 border-b border-border-subtle text-[11px] text-content-secondary select-none"
    >
      <div class="flex items-center gap-2 truncate">
        <span v-if="title" class="font-medium text-content-primary truncate">{{ title }}</span>
        <span v-if="language" class="px-1 py-0.5 rounded bg-app text-content-muted uppercase text-[10px]">
          {{ language }}
        </span>
      </div>

      <button
        v-if="copyable"
        type="button"
        class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-panel text-content-muted hover:text-content-primary transition-colors"
        @click="copyToClipboard"
      >
        <Check v-if="copied" class="h-3 w-3 text-status-success" />
        <Copy v-else class="h-3 w-3" />
        <span>{{ copied ? '已复制' : '复制' }}</span>
      </button>
    </div>

    <!-- Code Content -->
    <div class="overflow-x-auto p-3 leading-relaxed">
      <div v-for="(line, idx) in lines" :key="idx" class="flex items-baseline">
        <span
          v-if="showLineNumbers"
          class="inline-block w-8 text-right pr-3 select-none text-content-disabled shrink-0"
        >
          {{ idx + 1 }}
        </span>
        <span class="whitespace-pre flex-1 text-content-primary">{{ line || ' ' }}</span>
      </div>
    </div>
  </div>
</template>
