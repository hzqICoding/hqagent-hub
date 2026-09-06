<script setup lang="ts">
import { ref } from 'vue'
import { ChevronRight, Folder, FileText } from 'lucide-vue-next'

export interface TreeNode {
  id: string
  label: string
  children?: TreeNode[]
  icon?: any
  disabled?: boolean
}

interface Props {
  nodes: TreeNode[]
  selectedId?: string
}

const _props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'select', node: TreeNode): void
}>()

const expandedIds = ref<Set<string>>(new Set())

function toggle(node: TreeNode) {
  if (expandedIds.value.has(node.id)) {
    expandedIds.value.delete(node.id)
  } else {
    expandedIds.value.add(node.id)
  }
}

function select(node: TreeNode) {
  if (node.disabled) return
  emit('select', node)
  if (node.children && node.children.length > 0) {
    toggle(node)
  }
}
</script>

<template>
  <div class="text-xs select-none">
    <ul class="space-y-0.5">
      <li v-for="node in nodes" :key="node.id">
        <div
          :class="[
            'flex items-center gap-1.5 px-2 py-1 rounded cursor-pointer transition-colors',
            node.id === selectedId
              ? 'bg-accent-soft/40 text-action-primary font-medium'
              : 'text-content-secondary hover:text-content-primary hover:bg-muted',
            node.disabled ? 'opacity-40 cursor-not-allowed' : '',
          ]"
          @click="select(node)"
        >
          <!-- Expand Arrow -->
          <button
            v-if="node.children && node.children.length > 0"
            type="button"
            class="p-0.5 text-content-muted hover:text-content-primary"
            @click.stop="toggle(node)"
          >
            <ChevronRight
              :class="[
                'h-3.5 w-3.5 transition-transform duration-150',
                expandedIds.has(node.id) ? 'rotate-90' : '',
              ]"
            />
          </button>
          <span v-else class="w-4.5" />

          <!-- Icon -->
          <Folder
            v-if="node.children && node.children.length > 0"
            class="h-3.5 w-3.5 text-accent shrink-0"
          />
          <FileText v-else class="h-3.5 w-3.5 text-content-muted shrink-0" />

          <span class="truncate">{{ node.label }}</span>
        </div>

        <!-- Recursive Children -->
        <div v-if="node.children && expandedIds.has(node.id)" class="pl-4 border-l border-border-subtle ml-3 mt-0.5">
          <HqTree :nodes="node.children" :selected-id="selectedId" @select="emit('select', $event)" />
        </div>
      </li>
    </ul>
  </div>
</template>
