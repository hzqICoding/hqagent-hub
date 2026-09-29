import type { NativeSessionIndex, NativeMessagePage } from '@hqagent/protocol'

export const nativeExampleText = '这是用于界面验收的合成会话内容，不来自真实终端历史。'

// Synthetic UI-only examples; never read user CLI files.
export function nativeExamples(workspaceId: string): NativeSessionIndex[] {
  return ['unknown', 'likely_active', 'closed_confirmed'].map((activity, i) => ({
    nativeSessionId: `native_example_${i}`, workspaceId, agentType: i === 1 ? 'codex' : 'claude',
    title: ['示例：梳理项目结构', '示例：检查测试覆盖', '示例：讨论接口设计'][i],
    createdAt: '2026-09-28T10:00:00Z', updatedAt: '2026-09-29T10:00:00Z', indexVersion: 1,
    sourceRevision: 'example_source_revision', format: { status: 'readable', readerId: 'synthetic' },
    activity: { activity: activity as NativeSessionIndex['activity']['activity'], observedAt: '2026-09-29T10:00:00Z', processMatch: i === 1 ? 'present' : 'unknown', recentlyModified: i === 1 },
  }))
}
export async function nativeExampleMessages(id: string): Promise<NativeMessagePage> {
  const text = nativeExampleText
  const bytes = new TextEncoder().encode(text)
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return { nativeSessionId: id, sourceRevision: 'example_source_revision', snapshotCursor: 'example_snapshot', hasMore: false,
    items: [{ messageId: 'example_message', role: 'assistant', text, segmentIndex: 0, segmentCount: 1,
      totalUtf8Bytes: bytes.length, contentSha256: Array.from(new Uint8Array(digest), (n) => n.toString(16).padStart(2, '0')).join('') }] }
}
