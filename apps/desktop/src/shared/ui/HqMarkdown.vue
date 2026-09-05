<script setup lang="ts">
import { computed } from 'vue'
import HqCodeBlock from './HqCodeBlock.vue'

interface Props {
  content: string
}

const props = withDefaults(defineProps<Props>(), {
  content: '',
})

interface Block {
  type: 'heading' | 'paragraph' | 'code' | 'list' | 'quote'
  level?: number
  text?: string
  language?: string
  items?: string[]
}

// Lightweight safe markdown block parser with zero external HTML-injection risk
const parsedBlocks = computed<Block[]>(() => {
  const lines = props.content.split('\n')
  const blocks: Block[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // Code blocks
    if (line.trim().startsWith('```')) {
      const language = line.trim().slice(3).trim() || 'text'
      const codeLines: string[] = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i])
        i++
      }
      blocks.push({
        type: 'code',
        language,
        text: codeLines.join('\n'),
      })
      i++
      continue
    }

    // Headings
    if (line.startsWith('### ')) {
      blocks.push({ type: 'heading', level: 3, text: line.slice(4) })
      i++
      continue
    }
    if (line.startsWith('## ')) {
      blocks.push({ type: 'heading', level: 2, text: line.slice(3) })
      i++
      continue
    }
    if (line.startsWith('# ')) {
      blocks.push({ type: 'heading', level: 1, text: line.slice(2) })
      i++
      continue
    }

    // Blockquote
    if (line.startsWith('> ')) {
      blocks.push({ type: 'quote', text: line.slice(2) })
      i++
      continue
    }

    // Unordered list item
    if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
      const listItems: string[] = []
      while (i < lines.length && (lines[i].trim().startsWith('- ') || lines[i].trim().startsWith('* '))) {
        listItems.push(lines[i].trim().slice(2))
        i++
      }
      blocks.push({ type: 'list', items: listItems })
      continue
    }

    // Empty line
    if (!line.trim()) {
      i++
      continue
    }

    // Normal paragraph
    const pLines: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() &&
      !lines[i].startsWith('#') &&
      !lines[i].startsWith('> ') &&
      !lines[i].trim().startsWith('- ') &&
      !lines[i].trim().startsWith('```')
    ) {
      pLines.push(lines[i])
      i++
    }
    blocks.push({ type: 'paragraph', text: pLines.join(' ') })
  }

  return blocks
})

// Escape HTML and format bold, code, and links safely
function formatInline(text: string): string {
  if (!text) return ''
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  return escaped
    .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-content-primary">$1</strong>')
    .replace(/\*(.*?)\*/g, '<em class="italic">$1</em>')
    .replace(/`([^`]+)`/g, '<code class="px-1 py-0.5 rounded bg-muted font-mono text-[11px] text-content-primary">$1</code>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-action-primary hover:underline">$1</a>')
}
</script>

<template>
  <div class="space-y-3 text-xs leading-relaxed text-content-secondary select-text">
    <template v-for="(block, idx) in parsedBlocks" :key="idx">
      <!-- Headings -->
      <h1
        v-if="block.type === 'heading' && block.level === 1"
        class="text-base font-bold text-content-primary mt-4 mb-2 pb-1 border-b border-border"
        v-html="formatInline(block.text || '')"
      />
      <h2
        v-else-if="block.type === 'heading' && block.level === 2"
        class="text-sm font-semibold text-content-primary mt-3 mb-1.5"
        v-html="formatInline(block.text || '')"
      />
      <h3
        v-else-if="block.type === 'heading' && block.level === 3"
        class="text-xs font-semibold text-content-primary mt-2 mb-1"
        v-html="formatInline(block.text || '')"
      />

      <!-- Paragraph -->
      <p
        v-else-if="block.type === 'paragraph'"
        class="leading-normal"
        v-html="formatInline(block.text || '')"
      />

      <!-- Quote -->
      <blockquote
        v-else-if="block.type === 'quote'"
        class="border-l-2 border-accent pl-3 py-1 bg-muted/30 text-content-muted italic my-2 rounded-r"
        v-html="formatInline(block.text || '')"
      />

      <!-- List -->
      <ul
        v-else-if="block.type === 'list' && block.items"
        class="list-disc list-inside space-y-1 pl-1"
      >
        <li
          v-for="(item, itemIdx) in block.items"
          :key="itemIdx"
          v-html="formatInline(item)"
        />
      </ul>

      <!-- Code -->
      <HqCodeBlock
        v-else-if="block.type === 'code'"
        :code="block.text || ''"
        :language="block.language"
      />
    </template>
  </div>
</template>
