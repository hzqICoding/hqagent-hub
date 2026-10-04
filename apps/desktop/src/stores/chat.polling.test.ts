import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { HubEvent, LocalEventPage } from '@hqagent/protocol'
import { HubApiError, mockLocalChatGateway, setLocalChatGatewayMode } from '@/shared/api'
import { useChatStore } from './chat.store'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

function event(seq: number): HubEvent {
  return { eventId: `poll-${seq}`, seq, type: 'agent.progress', aggregateType: 'task',
    aggregateId: 'task_run_1', occurredAt: '2026-09-25T00:00:00Z',
    protocolVersion: '0.3.0', payload: { message: '正在运行测试' } }
}

describe('chat polling lifecycle', () => {
  beforeEach(async () => {
    vi.useFakeTimers()
    setActivePinia(createPinia())
    setLocalChatGatewayMode('mock')
    mockLocalChatGateway.reset()
    await useChatStore().init()
  })

  afterEach(() => {
    useChatStore().stopPolling()
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('keeps polling after switching conversation while an event request is in flight', async () => {
    const store = useChatStore()
    const pending = deferred<LocalEventPage>()
    const list = vi.spyOn(mockLocalChatGateway, 'listLocalEvents').mockImplementationOnce(() => pending.promise)
    store.startPolling()
    await vi.advanceTimersByTimeAsync(4000)
    expect(list).toHaveBeenCalledTimes(1)
    await store.selectConversation(store.conversations.find(c => c.id !== store.activeConversationId)!.id)
    pending.resolve({ events: [], nextSeq: 0, hasMore: false })
    await vi.advanceTimersByTimeAsync(0)
    const count = list.mock.calls.length
    await vi.advanceTimersByTimeAsync(5000)
    expect(list.mock.calls.length).toBeGreaterThan(count)
  })

  it('refreshes final task state even if the event endpoint fails', async () => {
    const store = useChatStore()
    const finished = { ...store.activeRun!, status: 'succeeded' as const }
    vi.spyOn(mockLocalChatGateway, 'listConversationRuns').mockResolvedValue([finished])
    vi.spyOn(mockLocalChatGateway, 'getLocalRun').mockResolvedValue(finished)
    vi.spyOn(mockLocalChatGateway, 'listLocalMessages').mockResolvedValue([{
      id: 'new-final-reply', conversationId: store.activeConversationId!, role: 'assistant',
      sequence: 999, text: '测试完成', createdAt: '2026-09-25T00:00:00Z',
    }])
    store.activeRun = { ...store.activeRun!, status: 'running' }
    vi.spyOn(mockLocalChatGateway, 'listLocalEvents').mockRejectedValue(new Error('event endpoint unavailable'))
    store.startPolling()
    await store.pollEvents()
    expect(store.activeRun?.status).toBe('succeeded')
    expect(store.isCurrentRunActive).toBe(false)
    expect(store.messages.some(m => m.id === 'new-final-reply')).toBe(true)
  })

  it('ignores an old history request after reset', async () => {
    const store = useChatStore()
    const pending = deferred<LocalEventPage>()
    vi.spyOn(mockLocalChatGateway, 'listLocalEvents').mockImplementationOnce(() => pending.promise)
    const selection = store.selectConversation(store.conversations.find(c => c.id !== store.activeConversationId)!.id)
    store.reset()
    pending.resolve({ events: [event(100)], nextSeq: 100, hasMore: false })
    await selection
    expect(store.lastEventSeq).toBe(0)
    expect(store.activitiesByTaskId).toEqual({})
  })

  it('catches up multiple event pages without waiting a poll interval per page', async () => {
    const store = useChatStore()
    const target = store.lastEventSeq + 3
    const list = vi.spyOn(mockLocalChatGateway, 'listLocalEvents').mockImplementation(async (after = 0) => {
      const nextSeq = Math.min(after + 1, target)
      return { events: [event(nextSeq)], nextSeq, hasMore: nextSeq < target }
    })
    store.startPolling()
    await store.pollEvents()
    expect(list).toHaveBeenCalledTimes(3)
    expect(store.lastEventSeq).toBe(target)
  })

  it('does not overlap polling requests within the same lifecycle', async () => {
    const store = useChatStore()
    const pending = deferred<LocalEventPage>()
    const list = vi.spyOn(mockLocalChatGateway, 'listLocalEvents').mockImplementationOnce(() => pending.promise)
    store.startPolling()
    const first = store.pollEvents()
    await store.pollEvents()
    expect(list).toHaveBeenCalledTimes(1)
    pending.resolve({ events: [], nextSeq: store.lastEventSeq, hasMore: false })
    await first
  })

  it('ignores a stopped poll when a new polling lifecycle has already started', async () => {
    const store = useChatStore()
    const pending = deferred<LocalEventPage>()
    const list = vi.spyOn(mockLocalChatGateway, 'listLocalEvents').mockImplementationOnce(() => pending.promise)
    store.startPolling()
    const first = store.pollEvents()
    store.stopPolling()
    store.startPolling()
    await store.pollEvents()
    pending.resolve({ events: [event(999)], nextSeq: 999, hasMore: false })
    await first
    expect(store.lastEventSeq).not.toBe(999)
    const count = list.mock.calls.length
    await vi.advanceTimersByTimeAsync(5000)
    expect(list.mock.calls.length).toBeGreaterThan(count)
  })
  it.each([undefined, -1, NaN, Infinity, 1.5, '80', Number.MAX_SAFE_INTEGER + 1])(
    'rebuilds snapshots and keeps polling with invalid latestSeq %s', async (latestSeq) => {
      const store = useChatStore()
      store.lastEventSeq = 40
      const events = vi.spyOn(mockLocalChatGateway, 'listLocalEvents')
        .mockRejectedValueOnce(new HubApiError('expired', 'EVENT_CURSOR_EXPIRED', 410, { latestSeq }))
        .mockResolvedValue({ events: [], nextSeq: 81, hasMore: false })
      const conversations = vi.spyOn(mockLocalChatGateway, 'listLocalConversations')
      const messages = vi.spyOn(mockLocalChatGateway, 'listLocalMessages')
      const runs = vi.spyOn(mockLocalChatGateway, 'listConversationRuns')
      const approvals = vi.spyOn(mockLocalChatGateway, 'listLocalApprovals')
      store.startPolling()
      await store.pollEvents()
      expect(store.lastEventSeq).toBe(0)
      expect(store.loadError).toBeNull()
      expect(conversations).toHaveBeenCalledTimes(2)
      expect(messages).toHaveBeenCalledWith(store.activeConversationId, 0, 200)
      expect(runs).toHaveBeenCalledTimes(2)
      expect(approvals).toHaveBeenCalledTimes(2)
      await vi.advanceTimersByTimeAsync(999)
      expect(events).toHaveBeenCalledTimes(1)
      await vi.advanceTimersByTimeAsync(1)
      expect(events).toHaveBeenNthCalledWith(2, 0, 200)
      expect(store.lastEventSeq).toBe(81)
    },
  )

  it('backs off repeated cursor failures to 30s and recovers without restarting', async () => {
    const store = useChatStore()
    const events = vi.spyOn(mockLocalChatGateway, 'listLocalEvents')
      .mockRejectedValue(new HubApiError('expired', 'EVENT_CURSOR_EXPIRED', 410))
    store.startPolling()
    await store.pollEvents()
    for (const delay of [1000, 2000, 5000, 10000, 30000, 30000]) {
      const count = events.mock.calls.length
      await vi.advanceTimersByTimeAsync(delay - 1)
      expect(events).toHaveBeenCalledTimes(count)
      await vi.advanceTimersByTimeAsync(1)
      expect(events).toHaveBeenCalledTimes(count + 1)
    }
    expect(store.loadError).toContain('正在自动重试')
    expect(store.loadError).not.toContain('重新连接')
    events.mockResolvedValue({ events: [], nextSeq: 91, hasMore: false })
    await vi.advanceTimersByTimeAsync(30000)
    expect(store.lastEventSeq).toBe(91)
    expect(store.loadError).toBeNull()
    events.mockRejectedValueOnce(new HubApiError('expired again', 'EVENT_CURSOR_EXPIRED', 410))
    await store.pollEvents()
    const count = events.mock.calls.length
    await vi.advanceTimersByTimeAsync(1000)
    expect(events).toHaveBeenCalledTimes(count + 1)
  })

  it('does not restart a stopped lifecycle after a recovery snapshot completes', async () => {
    const store = useChatStore()
    const snapshot = deferred<Awaited<ReturnType<typeof mockLocalChatGateway.listLocalMessages>>>()
    const events = vi.spyOn(mockLocalChatGateway, 'listLocalEvents')
      .mockRejectedValue(new HubApiError('expired', 'EVENT_CURSOR_EXPIRED', 410))
    vi.spyOn(mockLocalChatGateway, 'listLocalMessages').mockReturnValueOnce(snapshot.promise)
    store.startPolling()
    const polling = store.pollEvents()
    store.stopPolling()
    snapshot.resolve([])
    await polling
    await vi.advanceTimersByTimeAsync(60000)
    expect(events).toHaveBeenCalledTimes(1)
  })

})
