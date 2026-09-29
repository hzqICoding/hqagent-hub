import type { NativeActivity, NativeAgentType, NativeMessagePage, NativeMessagePart, RemoteLinkView, RemoteSyncSettingsView } from '@hqagent/protocol'
import { getRemoteErrorMessage } from '@/shared/i18n/remote-errors'

export const agentLabel = (agent?: NativeAgentType) => agent === 'claude' ? 'Claude Code' : agent === 'codex' ? 'Codex' : '原生 Agent'
export const activityLabel = (activity: NativeActivity) => ({ unknown: '可能仍在终端中运行', likely_active: '终端正在使用', closed_confirmed: '已确认关闭' }[activity])
export const closureText = '请先在电脑终端里退出这个会话。同时写入会损坏会话记录。确认已退出后再继续。'
export function nativeFailure(error: unknown): { message: string; requestId?: string; code?: string } {
  const value = error as { code?: string; message?: string; requestId?: string }
  const guidance: Record<string, string> = {
    NATIVE_SESSION_ACTIVE: '电脑检测到该会话仍在运行',
    NATIVE_SESSION_CHANGED: '终端中有新内容，请重新确认',
    REMOTE_QUERY_TIMEOUT: '电脑在线查询超时，可以重试',
  }
  return { code: value?.code, requestId: value?.requestId, message: guidance[value?.code || ''] || getRemoteErrorMessage(value?.code, value?.message || '操作失败，请重试') }
}
export function nativeSyncNotice(link: RemoteLinkView | null, settings: RemoteSyncSettingsView | null): string {
  if (!link || !settings) return '已在本机导入，正在核对同步条件'
  if (!settings.mirrorEnabled) return '已在本机导入，同步已关闭'
  if (link.state === 'unpaired' || link.state === 'pairing') return '已在本机导入，尚未配对手机'
  if (link.state === 'revoked') return '已在本机导入，设备连接已撤销'
  if (link.state === 'frozen') return '已在本机导入，连接正在核对，暂未同步'
  if (link.connectionStatus !== 'online') return '已在本机导入，电脑离线，等待连接后同步'
  // No negotiated revision / backfill-complete field exists in RemoteLinkView.
  return '已在本机导入，待连接支持修订 3 的服务后同步'
}

// Ephemeral assembly, scoped to one index and one source snapshot. Never render partial text.
export class NativeMessageAssembler {
  private snapshot = ''
  private source = ''
  private id = ''
  private parts = new Map<string, Map<number, NativeMessagePart>>()
  reset() { this.snapshot = ''; this.source = ''; this.id = ''; this.parts.clear() }
  async append(page: NativeMessagePage): Promise<NativeMessagePart[]> {
    if (this.snapshot && (this.snapshot !== page.snapshotCursor || this.source !== page.sourceRevision || this.id !== page.nativeSessionId)) {
      this.reset()
      throw new Error('原生会话快照已变化，请重新读取')
    }
    this.snapshot = page.snapshotCursor; this.source = page.sourceRevision; this.id = page.nativeSessionId
    if (page.hasMore && !page.before) throw new Error('原生会话分页游标缺失，请重新读取')
    for (const part of page.items) {
      if (!Number.isSafeInteger(part.segmentCount) || part.segmentCount < 1 || part.segmentIndex < 0 || part.segmentIndex >= part.segmentCount) throw new Error('会话分段无效')
      const group = this.parts.get(part.messageId) || new Map<number, NativeMessagePart>()
      const first = group.values().next().value as NativeMessagePart | undefined
      if (first && (first.contentSha256 !== part.contentSha256 || first.segmentCount !== part.segmentCount || first.totalUtf8Bytes !== part.totalUtf8Bytes || first.role !== part.role)) throw new Error('会话分段冲突，请重新读取')
      const previous = group.get(part.segmentIndex)
      if (previous && previous.text !== part.text) throw new Error('会话分段冲突，请重新读取')
      group.set(part.segmentIndex, part); this.parts.set(part.messageId, group)
    }
    if (!page.hasMore && [...this.parts.values()].some((group) => group.size !== group.values().next().value?.segmentCount)) throw new Error('会话消息片段不完整，请重新读取')
    const complete: NativeMessagePart[] = []
    for (const group of this.parts.values()) {
      const first = group.values().next().value as NativeMessagePart
      if (group.size !== first.segmentCount) continue
      const text = [...group.values()].sort((a, b) => a.segmentIndex - b.segmentIndex).map((part) => part.text).join('')
      const bytes = new TextEncoder().encode(text)
      const digest = await crypto.subtle.digest('SHA-256', bytes)
      const hash = Array.from(new Uint8Array(digest), (n) => n.toString(16).padStart(2, '0')).join('')
      if (bytes.length !== first.totalUtf8Bytes || hash !== first.contentSha256) throw new Error('会话内容校验失败，请重新读取')
      complete.push({ ...first, text })
    }
    return complete.reverse()
  }
}
