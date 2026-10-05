import { describe, expect, it } from 'vitest'
import {
  formatSystemGroupTitle,
  groupConsecutiveSystemMessages,
} from './chat-message-grouping'

describe('chat-message-grouping', () => {
  it('formats placeholder tool calls where call + return pair counts as 1', () => {
    // 14 pairs of Bash (28 messages) + 4 pairs of Read (8 messages)
    const messages: Array<{ text: string }> = []
    for (let i = 0; i < 14; i++) {
      messages.push({ text: 'Bash：历史调用' })
      messages.push({ text: 'Bash：历史返回记录' })
    }
    for (let i = 0; i < 4; i++) {
      messages.push({ text: 'Read: 历史调用' })
      messages.push({ text: 'Read: 历史返回记录' })
    }

    const title = formatSystemGroupTitle(messages)
    expect(title).toBe('🔧 工具调用 ×18（Bash ×14、Read ×4）')
  })

  it('formats non-placeholder tool calls where each counts as 1', () => {
    const messages = [
      { text: 'Bash: npm run test' },
      { text: 'Bash: ls -la' },
      { text: 'ReadFile: package.json' },
    ]
    const title = formatSystemGroupTitle(messages)
    expect(title).toBe('🔧 工具调用 ×3（Bash ×2、ReadFile ×1）')
  })

  it('handles message text without colon gracefully', () => {
    const messages = [
      { text: 'Running automated checks' },
      { text: 'Checks completed' },
    ]
    const title = formatSystemGroupTitle(messages)
    expect(title).toBe('🔧 工具调用 ×2（工具 ×2）')
  })

  it('keeps single system message as single, not grouped', () => {
    const messages = [
      { id: '1', role: 'system', text: 'Bash: git status' },
    ]
    const groups = groupConsecutiveSystemMessages(messages)
    expect(groups).toHaveLength(1)
    expect(groups[0].type).toBe('single')
    if (groups[0].type === 'single') {
      expect(groups[0].message.id).toBe('1')
    }
  })

  it('groups 20 consecutive system messages into 1 row', () => {
    const messages = Array.from({ length: 20 }, (_, i) => ({
      id: `sys_${i}`,
      role: 'system',
      text: `Bash: echo ${i}`,
    }))

    const groups = groupConsecutiveSystemMessages(messages)
    expect(groups).toHaveLength(1)
    expect(groups[0].type).toBe('system_group')
    if (groups[0].type === 'system_group') {
      expect(groups[0].systemMessages).toHaveLength(20)
      expect(groups[0].title).toBe('🔧 工具调用 ×20（Bash ×20）')
    }
  })

  it('does not interfere between groups separated by user and assistant messages', () => {
    const messages = [
      { id: 'u1', role: 'user', text: '你好' },
      // Group 1: 3 system messages
      { id: 's1', role: 'system', text: 'Bash: pwd' },
      { id: 's2', role: 'system', text: 'Bash: ls' },
      { id: 's3', role: 'system', text: 'Read: file.txt' },
      { id: 'a1', role: 'assistant', text: '第一阶段完成' },
      // Group 2: 2 system messages
      { id: 's4', role: 'system', text: 'Git: status' },
      { id: 's5', role: 'system', text: 'Git: diff' },
      { id: 'u2', role: 'user', text: '继续' },
      // Single system message (should NOT be grouped)
      { id: 's6', role: 'system', text: 'Bash: done' },
      { id: 'a2', role: 'assistant', text: '完成' },
    ]

    const groups = groupConsecutiveSystemMessages(messages)
    expect(groups).toHaveLength(7)
    expect(groups[0]).toEqual({ type: 'single', message: messages[0] })

    expect(groups[1].type).toBe('system_group')
    if (groups[1].type === 'system_group') {
      expect(groups[1].systemMessages).toHaveLength(3)
      expect(groups[1].title).toBe('🔧 工具调用 ×3（Bash ×2、Read ×1）')
    }

    expect(groups[2]).toEqual({ type: 'single', message: messages[4] })

    expect(groups[3].type).toBe('system_group')
    if (groups[3].type === 'system_group') {
      expect(groups[3].systemMessages).toHaveLength(2)
      expect(groups[3].title).toBe('🔧 工具调用 ×2（Git ×2）')
    }

    expect(groups[4]).toEqual({ type: 'single', message: messages[7] })
    // Single system message stays single!
    expect(groups[5]).toEqual({ type: 'single', message: messages[8] })
    expect(groups[6]).toEqual({ type: 'single', message: messages[9] })
  })
})
