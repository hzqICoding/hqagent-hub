<script setup lang="ts">
import { computed, ref } from 'vue'
import { Copy, Check } from 'lucide-vue-next'
import HqCodeBlock from './HqCodeBlock.vue'

interface Props {
  content: string
}

const props = withDefaults(defineProps<Props>(), {
  content: '',
})

interface TableColumn {
  header: string
  align: 'left' | 'center' | 'right'
}

interface Block {
  type: 'heading' | 'section-title' | 'paragraph' | 'code' | 'list' | 'quote' | 'table' | 'hr'
  level?: number
  text?: string
  language?: string
  ordered?: boolean
  start?: number
  items?: string[]
  columns?: TableColumn[]
  rows?: string[][]
  rawMarkdown?: string
}

// State for copying table markdown
const copiedTableIdx = ref<number | null>(null)

async function copyTable(markdown: string | undefined, idx: number) {
  if (!markdown) return
  try {
    await navigator.clipboard.writeText(markdown)
    copiedTableIdx.value = idx
    setTimeout(() => {
      if (copiedTableIdx.value === idx) copiedTableIdx.value = null
    }, 2000)
  } catch (err) {
    console.error('Failed to copy table', err)
  }
}

function parseTableRowCells(line: string): string[] {
  let content = line.trim()
  if (content.startsWith('|')) content = content.slice(1)
  if (content.endsWith('|')) content = content.slice(0, -1)
  return content.split('|').map(c => c.trim())
}

function isTableDelimiter(line: string): boolean {
  const trimmed = line.trim()
  if (!trimmed.includes('-')) return false
  const parts = parseTableRowCells(trimmed)
  if (parts.length === 0) return false
  return parts.every(part => /^:?-+:?$/.test(part))
}

function getColumnAlign(cell: string | undefined): 'left' | 'center' | 'right' {
  if (!cell) return 'left'
  const trimmed = cell.trim()
  if (trimmed.startsWith(':') && trimmed.endsWith(':')) return 'center'
  if (trimmed.endsWith(':')) return 'right'
  return 'left'
}

function isHrLine(line: string): boolean {
  return /^[-*_]{3,}$/.test(line.trim())
}

function isSectionTitleLine(line: string): boolean {
  const trimmed = line.trim()
  if (trimmed.length < 2 || trimmed.length > 40) return false
  if (trimmed.startsWith('#') || trimmed.startsWith('`') || trimmed.startsWith('|')) return false
  // Chinese number section: 一、 二、 三、 ...
  if (/^[一二三四五六七八九十]+[、.][^\n]+$/.test(trimmed)) return true
  // Bracket section: 【...】
  if (/^【[^】]+】$/.test(trimmed)) return true
  // Label ending with colon (e.g. 核心文件与职责（5个）： or 门面入口与调用链：)
  if (/^[^#\n\r\t|*`]{2,35}[：:]$/.test(trimmed)) return true
  return false
}

function parseHeadingLine(line: string): { level: number; text: string } | null {
  // Matches markdown headings: 0-3 leading spaces, 1-6 '#', followed by whitespace or Chinese character
  const match = line.match(/^ {0,3}(#{1,6})(?:\s+(.*)|(?=[\u4e00-\u9fa5])(.*))$/)
  if (!match) return null
  const level = match[1].length
  const text = (match[2] !== undefined ? match[2] : match[3] || '').trim()
  return { level, text }
}

// Lightweight safe markdown block parser with zero external HTML-injection risk
const parsedBlocks = computed<Block[]>(() => {
  const normalized = props.content.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const lines = normalized.split('\n')
  const blocks: Block[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // Empty line
    if (!line.trim()) {
      i++
      continue
    }

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

    // Markdown Table (must have header line and delimiter line)
    if (i + 1 < lines.length && line.includes('|') && isTableDelimiter(lines[i + 1])) {
      const headerCells = parseTableRowCells(line)
      const delimiterCells = parseTableRowCells(lines[i + 1])
      const columns: TableColumn[] = headerCells.map((header, idx) => ({
        header,
        align: getColumnAlign(delimiterCells[idx]),
      }))

      const rawTableLines = [line, lines[i + 1]]
      i += 2
      const rows: string[][] = []

      while (i < lines.length && lines[i].trim() && lines[i].includes('|')) {
        const rowCells = parseTableRowCells(lines[i])
        const paddedRow = columns.map((_, colIdx) => rowCells[colIdx] || '')
        rows.push(paddedRow)
        rawTableLines.push(lines[i])
        i++
      }

      blocks.push({
        type: 'table',
        columns,
        rows,
        rawMarkdown: rawTableLines.join('\n'),
      })
      continue
    }

    // Horizontal rule
    if (isHrLine(line)) {
      blocks.push({ type: 'hr' })
      i++
      continue
    }

    // Headings (H1 - H6)
    const heading = parseHeadingLine(line)
    if (heading) {
      blocks.push({ type: 'heading', level: heading.level, text: heading.text })
      i++
      continue
    }

    // Blockquote
    if (line.startsWith('> ')) {
      blocks.push({ type: 'quote', text: line.slice(2) })
      i++
      continue
    }

    // Section title (e.g. "核心文件与职责（5个）：", "一、在本项目中的优化落地")
    if (isSectionTitleLine(line)) {
      blocks.push({ type: 'section-title', text: line.trim() })
      i++
      continue
    }

    // Ordered list item (e.g., 1. item, 2. item, or 1、item)
    const orderedMatch = line.trim().match(/^(\d+)[.、]\s*(.*)$/)
    if (orderedMatch) {
      const startNum = parseInt(orderedMatch[1], 10)
      const listItems: string[] = []
      let currentItemText = orderedMatch[2].trim()
      i++

      while (i < lines.length) {
        const nextLine = lines[i]
        if (!nextLine.trim()) {
          // Check if next non-empty line continues list
          let peek = i + 1
          while (peek < lines.length && !lines[peek].trim()) peek++
          if (peek < lines.length && /^\d+[.、]/.test(lines[peek].trim())) {
            i = peek
            continue
          }
          break
        }

        const nextOrderedMatch = nextLine.trim().match(/^(\d+)[.、]\s*(.*)$/)
        if (nextOrderedMatch) {
          if (currentItemText) listItems.push(currentItemText)
          currentItemText = nextOrderedMatch[2].trim()
          i++
          continue
        }

        // Stop if another structural block begins
        if (
          nextLine.trim().startsWith('```') ||
          nextLine.startsWith('#') ||
          nextLine.startsWith('> ') ||
          nextLine.trim().startsWith('- ') ||
          nextLine.trim().startsWith('* ') ||
          (nextLine.includes('|') && i + 1 < lines.length && isTableDelimiter(lines[i + 1])) ||
          isHrLine(nextLine) ||
          isSectionTitleLine(nextLine)
        ) {
          break
        }

        // Continuation line of current list item
        currentItemText = currentItemText ? `${currentItemText}\n${nextLine.trim()}` : nextLine.trim()
        i++
      }

      if (currentItemText) listItems.push(currentItemText)
      blocks.push({ type: 'list', ordered: true, start: startNum, items: listItems })
      continue
    }

    // Unordered list item (- , * , + )
    if (line.trim().startsWith('- ') || line.trim().startsWith('* ') || line.trim().startsWith('+ ')) {
      const listItems: string[] = []
      let currentItemText = line.trim().slice(2).trim()
      i++

      while (i < lines.length) {
        const nextLine = lines[i]
        if (!nextLine.trim()) {
          let peek = i + 1
          while (peek < lines.length && !lines[peek].trim()) peek++
          if (peek < lines.length && (lines[peek].trim().startsWith('- ') || lines[peek].trim().startsWith('* ') || lines[peek].trim().startsWith('+ '))) {
            i = peek
            continue
          }
          break
        }

        if (nextLine.trim().startsWith('- ') || nextLine.trim().startsWith('* ') || nextLine.trim().startsWith('+ ')) {
          if (currentItemText) listItems.push(currentItemText)
          currentItemText = nextLine.trim().slice(2).trim()
          i++
          continue
        }

        if (
          nextLine.trim().startsWith('```') ||
          nextLine.startsWith('#') ||
          nextLine.startsWith('> ') ||
          /^\d+[.、]/.test(nextLine.trim()) ||
          (nextLine.includes('|') && i + 1 < lines.length && isTableDelimiter(lines[i + 1])) ||
          isHrLine(nextLine) ||
          isSectionTitleLine(nextLine)
        ) {
          break
        }

        currentItemText = currentItemText ? `${currentItemText}\n${nextLine.trim()}` : nextLine.trim()
        i++
      }

      if (currentItemText) listItems.push(currentItemText)
      blocks.push({ type: 'list', ordered: false, items: listItems })
      continue
    }

    // Normal paragraph
    const pLines: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() &&
      !parseHeadingLine(lines[i]) &&
      !lines[i].startsWith('> ') &&
      !lines[i].trim().startsWith('- ') &&
      !lines[i].trim().startsWith('* ') &&
      !lines[i].trim().startsWith('+ ') &&
      !/^\d+[.、]/.test(lines[i].trim()) &&
      !lines[i].trim().startsWith('```') &&
      !isHrLine(lines[i]) &&
      !isSectionTitleLine(lines[i]) &&
      !(lines[i].includes('|') && i + 1 < lines.length && isTableDelimiter(lines[i + 1]))
    ) {
      pLines.push(lines[i])
      i++
    }
    if (pLines.length === 0) {
      // Must advance line if not consumed to prevent infinite loops (e.g. unsupported heading #tag or >no-space)
      pLines.push(lines[i])
      i++
    }
    blocks.push({ type: 'paragraph', text: pLines.join('\n') })
  }

  return blocks
})

// Safe inline formatter with XSS protection, token replacement for code/links, and file path highlights
function formatInline(text: string): string {
  if (!text) return ''
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

  // 1. Preserve inline code spans
  const codeTokens: string[] = []
  let replaced = escaped.replace(/`([^`]+)`/g, (_m, code) => {
    const token = `\u0000CODE_${codeTokens.length}\u0000`
    codeTokens.push(
      `<code class="px-1.5 py-0.5 rounded bg-muted/60 border border-border/60 font-mono text-[11px] text-text font-medium select-all">${code}</code>`
    )
    return token
  })

  // 2. Preserve markdown links
  const linkTokens: string[] = []
  replaced = replaced.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label: string, href: string) => {
    const token = `\u0000LINK_${linkTokens.length}\u0000`
    const decoded = href.replace(/&amp;/g, '&')
    if (
      !/^(https?:\/\/|mailto:|\/(?!\/)|#)/i.test(decoded) ||
      /[\s"'<>]/.test(decoded) ||
      Array.from(decoded).some(c => c.charCodeAt(0) <= 32)
    ) {
      linkTokens.push(label)
    } else {
      linkTokens.push(
        `<a href="${href}" target="_blank" rel="noopener noreferrer" class="text-primary underline decoration-primary/40 hover:decoration-primary font-medium transition-colors">${label}</a>`
      )
    }
    return token
  })

  // 3. Bold & Italic
  replaced = replaced
    .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-text">$1</strong>')
    .replace(/\*(.*?)\*/g, '<em class="italic text-text/90">$1</em>')

  // 4. File paths auto-detection (e.g., ua_settings/.../RtkSettingFragment.kt:12 or E:/Workspace/ua_android/build.gradle)
  const filePathRegex = /(^|[\s(（[<])([a-zA-Z0-9_\-./\\]+[/\\][a-zA-Z0-9_\-.]+\.(?:kt|java|ts|tsx|vue|js|jsx|json|yaml|yml|xml|gradle|md|go|rs|py|c|cpp|h|css|scss|html)(?::\d+)?)(?=$|[\s)）\]>，。；;：,:])/g
  replaced = replaced.replace(filePathRegex, (_m, prefix, path) => {
    return `${prefix}<code class="px-1.5 py-0.5 rounded bg-panel-hover border border-border/80 font-mono text-[11px] text-primary font-medium hover:border-primary/50 transition-colors select-all">${path}</code>`
  })

  // 5. Restore link and code tokens
  linkTokens.forEach((linkHtml, idx) => {
    replaced = replaced.replace(`\u0000LINK_${idx}\u0000`, linkHtml)
  })
  codeTokens.forEach((codeHtml, idx) => {
    replaced = replaced.replace(`\u0000CODE_${idx}\u0000`, codeHtml)
  })

  return replaced
}
</script>

<template>
  <div class="space-y-3 text-xs leading-relaxed text-text/90 select-text">
    <template v-for="(block, idx) in parsedBlocks" :key="idx">
      <!-- Headings -->
      <h1
        v-if="block.type === 'heading' && block.level === 1"
        class="text-base font-bold text-text mt-4 mb-2 pb-1.5 border-b border-border/80"
        v-html="formatInline(block.text || '')"
      />
      <h2
        v-else-if="block.type === 'heading' && block.level === 2"
        class="text-sm font-semibold text-text mt-3.5 mb-2"
        v-html="formatInline(block.text || '')"
      />
      <h3
        v-else-if="block.type === 'heading' && block.level === 3"
        class="text-xs font-semibold text-text mt-2.5 mb-1.5"
        v-html="formatInline(block.text || '')"
      />
      <h4
        v-else-if="block.type === 'heading' && (block.level === 4 || block.level === 5 || block.level === 6)"
        class="text-xs font-medium text-text mt-2 mb-1"
        v-html="formatInline(block.text || '')"
      />

      <!-- Section Title -->
      <div
        v-else-if="block.type === 'section-title'"
        class="flex items-center gap-2 pt-2.5 pb-1 text-xs font-semibold text-text"
      >
        <span class="w-1.5 h-3.5 rounded-full bg-primary shrink-0 shadow-xs" />
        <span v-html="formatInline(block.text || '')" />
      </div>

      <!-- Horizontal Rule -->
      <hr
        v-else-if="block.type === 'hr'"
        class="my-3 border-t border-border/70"
      />

      <!-- Paragraph -->
      <p
        v-else-if="block.type === 'paragraph'"
        class="leading-relaxed whitespace-pre-line text-text/90 my-1"
        v-html="formatInline(block.text || '')"
      />

      <!-- Quote -->
      <blockquote
        v-else-if="block.type === 'quote'"
        class="border-l-2 border-primary/70 pl-3 py-1 bg-muted/20 text-text-muted italic my-2 rounded-r"
        v-html="formatInline(block.text || '')"
      />

      <!-- Ordered List -->
      <ol
        v-else-if="block.type === 'list' && block.ordered && block.items"
        class="list-decimal list-outside ml-5 space-y-1.5 my-2 pl-0.5"
        :style="block.start && block.start > 1 ? { counterReset: `list-counter ${block.start - 1}` } : undefined"
      >
        <li
          v-for="(item, itemIdx) in block.items"
          :key="itemIdx"
          class="leading-relaxed text-text/90 pl-1"
          v-html="formatInline(item)"
        />
      </ol>

      <!-- Unordered List -->
      <ul
        v-else-if="block.type === 'list' && !block.ordered && block.items"
        class="list-disc list-outside ml-5 space-y-1.5 my-2 pl-0.5"
      >
        <li
          v-for="(item, itemIdx) in block.items"
          :key="itemIdx"
          class="leading-relaxed text-text/90 pl-1"
          v-html="formatInline(item)"
        />
      </ul>

      <!-- Table with PI-Desktop style toolbar -->
      <div
        v-else-if="block.type === 'table' && block.columns"
        class="my-3 rounded-xl border border-border/80 bg-panel/50 overflow-hidden shadow-xs group"
      >
        <div class="flex items-center justify-between px-3 py-1.5 bg-muted/40 border-b border-border/70 text-[11px] text-text-muted">
          <span class="font-mono text-[10px] tracking-wider uppercase">Table ({{ block.rows?.length || 0 }} rows)</span>
          <button
            type="button"
            class="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] text-text-muted hover:text-text hover:bg-panel transition-colors"
            title="复制表格 Markdown"
            @click="copyTable(block.rawMarkdown, idx)"
          >
            <Check v-if="copiedTableIdx === idx" class="w-3 h-3 text-success" />
            <Copy v-else class="w-3 h-3" />
            <span>{{ copiedTableIdx === idx ? '已复制' : '复制表格' }}</span>
          </button>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs border-collapse">
            <thead class="bg-muted/30 border-b border-border/70 text-text font-semibold">
              <tr>
                <th
                  v-for="(col, cIdx) in block.columns"
                  :key="cIdx"
                  :style="{ textAlign: col.align }"
                  class="px-3.5 py-2 text-[11px] font-semibold text-text whitespace-nowrap"
                  v-html="formatInline(col.header)"
                />
              </tr>
            </thead>
            <tbody class="divide-y divide-border/40">
              <tr
                v-for="(row, rIdx) in block.rows"
                :key="rIdx"
                class="hover:bg-panel-hover/50 transition-colors"
              >
                <td
                  v-for="(cell, cellIdx) in row"
                  :key="cellIdx"
                  :style="{ textAlign: block.columns[cellIdx]?.align || 'left' }"
                  class="px-3.5 py-2 text-text/90 align-top leading-relaxed"
                  v-html="formatInline(cell)"
                />
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Code -->
      <HqCodeBlock
        v-else-if="block.type === 'code'"
        :code="block.text || ''"
        :language="block.language"
      />
    </template>
  </div>
</template>
