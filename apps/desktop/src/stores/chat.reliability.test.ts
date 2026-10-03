import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useChatStore } from './chat.store'
import { setLocalChatGatewayMode, mockLocalChatGateway, HubApiError } from '@/shared/api'
import type { LocalMessageView } from '@hqagent/protocol'

describe('ChatStore preserved reliability', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocalChatGatewayMode('mock')
    mockLocalChatGateway.reset()
  })

  afterEach(() => {
    const store = useChatStore()
    store.stopPolling()
    vi.restoreAllMocks()
  })

  it('registers a project when the local workspace list is initially empty', async () => {
    const store = useChatStore()
    store.workspaces = []
    const workspace = await store.registerWorkspace('E:/tmp/local-test-project')
    expect(store.workspaces).toHaveLength(1)
    expect(store.workspaces[0].id).toBe(workspace.id)
  })

  it('does not submit another run after a known resume rejection and permits explicit new context', async () => {
    const store = useChatStore()
    await store.init()
    store.sessionMode = 'continue'
    store.resumptionError = '无法接着上一轮继续，请点右上角 + 开启新话题'
    const send = vi.spyOn(mockLocalChatGateway, 'sendLocalMessage')
    await expect(store.sendMessage('请用中文')).rejects.toThrow('无法接着上一轮继续')
    expect(send).not.toHaveBeenCalled()
    await store.sendMessage('请用中文', 'new')
    expect(send).toHaveBeenCalledTimes(1)
    expect(send.mock.calls[0][1].sessionMode).toBe('new')
  })

  it('reuses message identity after the server accepted but response was lost', async () => {
    const store = useChatStore()
    await store.init()
    const original = mockLocalChatGateway.sendLocalMessage.bind(mockLocalChatGateway)
    const spy = vi.spyOn(mockLocalChatGateway, 'sendLocalMessage')
    spy.mockImplementationOnce(async (...args) => {
      await original(...args)
      throw new HubApiError('response lost', 'HUB_NOT_READY', 503, undefined, true)
    })
    await expect(store.sendMessage('NETWORK_RETRY_MARKER', 'new')).rejects.toThrow('response lost')
    await store.sendMessage('NETWORK_RETRY_MARKER', 'new')
    expect(spy.mock.calls[0][1].clientMessageId).toBe(spy.mock.calls[1][1].clientMessageId)
    expect(spy.mock.calls[0][2]).toBe(spy.mock.calls[1][2])
    expect(store.messages.filter(m => m.text === 'NETWORK_RETRY_MARKER')).toHaveLength(1)
  })

  it('advances to latestSeq after cursor expiry instead of repeatedly requesting zero', async () => {
    const store = useChatStore()
    await store.init()
    const spy = vi.spyOn(mockLocalChatGateway, 'listLocalEvents')
    spy.mockRejectedValueOnce(new HubApiError('expired', 'EVENT_CURSOR_EXPIRED', 410, { latestSeq: 80 }))
    spy.mockResolvedValue({ events: [], nextSeq: 80, hasMore: false })
    store.startPolling()
    await store.pollEvents()
    expect(store.lastEventSeq).toBe(80)
    await store.pollEvents()
    expect(spy.mock.calls[1][0]).toBe(80)
  })

  it('refreshes replies even when no new task event was published', async () => {
    const store = useChatStore()
    await store.init()
    vi.spyOn(mockLocalChatGateway, 'listLocalEvents').mockResolvedValue({ events: [], nextSeq: 0, hasMore: false })
    const messages = vi.spyOn(mockLocalChatGateway, 'listLocalMessages')
    store.startPolling()
    await store.pollEvents()
    expect(messages).toHaveBeenCalled()
  })

  it('loads all message pages instead of silently stopping at 200', async () => {
    const store = useChatStore()
    await store.init()
    const conversationId = store.activeConversationId!
    const all: LocalMessageView[] = Array.from({ length: 450 }, (_, i) => ({
      id: `long-${i}`, conversationId, sequence: i + 1, role: 'user', text: `line-${i}`, createdAt: '2026-09-24T00:00:00Z',
    }))
    store.messages = []
    vi.spyOn(mockLocalChatGateway, 'listLocalMessages').mockImplementation(async (_id, after = 0) => all.filter(m => m.sequence > after).slice(0, 200))
    await store.fetchMessages(conversationId)
    expect(store.messages).toHaveLength(450)
    expect(store.messages[449].text).toBe('line-449')
  })

  it('discards a late response from a conversation that is no longer selected', async () => {
    const store = useChatStore()
    await store.init()
    const oldId = store.activeConversationId!
    const otherId = store.conversations.find(c => c.id !== oldId)!.id
    let release!: (value: LocalMessageView[]) => void
    const pending = new Promise<LocalMessageView[]>(resolve => { release = resolve })
    vi.spyOn(mockLocalChatGateway, 'listLocalMessages').mockImplementationOnce(() => pending)
    const oldRequest = store.fetchMessages(oldId)
    await store.selectConversation(otherId)
    release([{ id: 'stale', conversationId: oldId, sequence: 100, role: 'assistant', text: 'stale', createdAt: '2026-09-24T00:00:00Z' }])
    await oldRequest
    expect(store.messages.some(m => m.id === 'stale')).toBe(false)
    expect(store.activeConversationId).toBe(otherId)
  })
})
