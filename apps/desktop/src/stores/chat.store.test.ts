import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useChatStore } from './chat.store'
import { setLocalChatGatewayMode, mockLocalChatGateway, HubApiError } from '@/shared/api'
import type { LocalMessageView } from '@hqagent/protocol'

describe('ChatStore', () => {
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

  it('initializes conversations and workspaces', async () => {
    const store = useChatStore()
    await store.init()
    expect(store.conversations.length).toBeGreaterThan(0)
    expect(store.workspaces.length).toBeGreaterThan(0)
    expect(store.scenes.length).toBe(3)
    expect(store.activeConversationId).toBeDefined()
    expect(store.messages.length).toBeGreaterThan(0)
  })

  it('creates conversation and automatically switches active conversation', async () => {
    const store = useChatStore()
    await store.init()
    const newConv = await store.createConversation(
      '分析架构设计与扩展性',
      store.workspaces[0].id,
      'analyze'
    )
    expect(newConv.title).toBe('分析架构设计与扩展性')
    expect(store.activeConversationId).toBe(newConv.id)
    expect(store.sessionMode).toBe('new') // first message is new
  })

  it('registers a project when the local workspace list is initially empty', async () => {
    const store = useChatStore()
    store.workspaces = []
    const workspace = await store.registerWorkspace('E:/tmp/local-test-project')
    expect(store.workspaces).toHaveLength(1)
    expect(store.workspaces[0].id).toBe(workspace.id)
  })

  it('sends message, updates message stream, and triggers run update', async () => {
    const store = useChatStore()
    await store.init()

    const initialLen = store.messages.length
    await store.sendMessage('请分析当前目录结构')
    expect(store.messages.length).toBeGreaterThan(initialLen)
    expect(store.activeRun).toBeDefined()
  })

  it('controls run actions (pause, resume, cancel)', async () => {
    const store = useChatStore()
    await store.init()

    // Select conv with running task
    await store.selectConversation('conv_develop_ui')
    expect(store.activeRun?.status).toBe('running')

    await store.controlRun(store.activeRun!.id, 'pause')
    expect(store.activeRun?.status).toBe('paused')

    await store.controlRun(store.activeRun!.id, 'resume')
    expect(store.activeRun?.status).toBe('running')

    await store.controlRun(store.activeRun!.id, 'cancel')
    expect(store.activeRun?.status).toBe('cancelled')
  })

  it('handles session non-resumable failure', async () => {
    const store = useChatStore()
    await store.init()
    mockLocalChatGateway.simulateSessionNotResumable = true

    try {
      await store.sendMessage('继续上下文', 'continue')
      expect.unreachable('Should throw non resumable')
    } catch {
      expect(store.resumptionError).toContain('会话无法恢复')
    }
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
