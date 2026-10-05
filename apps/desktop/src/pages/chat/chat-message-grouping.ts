export interface GenericMessage {
  id?: string
  messageId?: string
  role: string
  text: string
  createdAt?: string
  [key: string]: any
}

export type MessageGroup<T extends GenericMessage> =
  | { type: 'single'; message: T }
  | { type: 'system_group'; systemMessages: T[]; title: string }

/**
 * Formats a list of consecutive system messages into:
 * 🔧 工具调用 ×N（Bash ×14、Read ×4）
 *
 * Rules:
 * - Tool name extracted from text before colon: `^([^:：\n\r]+)[:：]`
 * - Placeholder messages containing '历史调用' / '历史返回记录' (e.g. from terminal import):
 *   A pair of '调用 + 返回' counts as 1 tool call.
 * - Non-placeholder messages: each message counts as 1 tool call.
 */
export function formatSystemGroupTitle(systemMessages: Array<{ text: string }>): string {
  if (systemMessages.length === 0) {
    return '🔧 工具调用 ×0'
  }

  // Preserve insertion order of tools
  const toolStatsMap = new Map<string, { calls: number; returns: number; others: number }>()

  for (const msg of systemMessages) {
    const text = msg.text || ''
    // Extract tool name before colon (halfwidth or fullwidth)
    const match = text.match(/^([^:：\n\r]+)[:：]/)
    const toolName = match && match[1].trim() ? match[1].trim() : '工具'

    let stats = toolStatsMap.get(toolName)
    if (!stats) {
      stats = { calls: 0, returns: 0, others: 0 }
      toolStatsMap.set(toolName, stats)
    }

    const isCallPlaceholder = text.includes('历史调用')
    const isReturnPlaceholder = text.includes('历史返回记录')

    if (isCallPlaceholder) {
      stats.calls++
    } else if (isReturnPlaceholder) {
      stats.returns++
    } else {
      stats.others++
    }
  }

  let totalN = 0
  const breakdownParts: string[] = []

  for (const [name, stats] of toolStatsMap.entries()) {
    let toolCount = 0
    if (stats.calls > 0 || stats.returns > 0) {
      // A pair of call + return counts as 1 tool call
      const pairCount = Math.max(stats.calls, stats.returns, Math.ceil((stats.calls + stats.returns) / 2))
      toolCount = pairCount + stats.others
    } else {
      toolCount = stats.others
    }

    totalN += toolCount
    breakdownParts.push(`${name} ×${toolCount}`)
  }

  const breakdown = breakdownParts.join('、')
  return breakdown
    ? `🔧 工具调用 ×${totalN}（${breakdown}）`
    : `🔧 工具调用 ×${totalN}`
}

/**
 * Groups adjacent system messages together.
 * - If group has only 1 system message, keep it as 'single'.
 * - If group has 2 or more system messages, group them into 'system_group' with calculated title.
 * - Non-system messages are always 'single'.
 */
export function groupConsecutiveSystemMessages<T extends GenericMessage>(messages: T[]): MessageGroup<T>[] {
  const groups: MessageGroup<T>[] = []
  let currentSystem: T[] = []

  function flushSystem() {
    if (currentSystem.length === 0) return
    if (currentSystem.length === 1) {
      groups.push({ type: 'single', message: currentSystem[0] })
    } else {
      groups.push({
        type: 'system_group',
        systemMessages: [...currentSystem],
        title: formatSystemGroupTitle(currentSystem),
      })
    }
    currentSystem = []
  }

  for (const msg of messages) {
    if (msg.role === 'system') {
      currentSystem.push(msg)
    } else {
      flushSystem()
      groups.push({ type: 'single', message: msg })
    }
  }

  flushSystem()
  return groups
}
