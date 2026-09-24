import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { HubEvent, LocalEventPage } from '@hqagent/protocol'
import { mockLocalChatGateway, setLocalChatGatewayMode } from '@/shared/api'
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
})
