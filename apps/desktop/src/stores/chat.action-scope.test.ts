import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { LocalRunView } from '@hqagent/protocol'
import { mockLocalChatGateway, setLocalChatGatewayMode } from '@/shared/api'
import { useChatStore } from './chat.store'

describe('task controls stay bound to their original conversation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocalChatGatewayMode('mock')
    mockLocalChatGateway.reset()
  })
  afterEach(() => {
    useChatStore().stopPolling()
    vi.restoreAllMocks()
  })

  it('does not pin task A in task B after a delayed cancel response', async () => {
    const store = useChatStore()
    await store.init()
    await store.selectConversation('conv_develop_ui')
    const original = store.activeRun!
    let resolve!: (run: LocalRunView) => void
    vi.spyOn(mockLocalChatGateway, 'controlLocalRun').mockImplementationOnce(() =>
      new Promise<LocalRunView>((done) => { resolve = done }))
    const pending = store.controlRun(original.id, 'cancel')
    await store.selectConversation('conv_analyze_auth')
    const currentId = store.activeRun!.id
    resolve({ ...original, status: 'cancelled' })
    await pending
    expect(store.activeRun!.id).toBe(currentId)
    await store.fetchConversationRuns('conv_analyze_auth')
    expect(store.activeRun!.id).toBe(currentId)
    expect(store.activeRun!.conversationId).toBe('conv_analyze_auth')
  })

  it('does not display task A control errors in task B', async () => {
    const store = useChatStore()
    await store.init()
    await store.selectConversation('conv_develop_ui')
    let reject!: (error: Error) => void
    vi.spyOn(mockLocalChatGateway, 'controlLocalRun').mockImplementationOnce(() =>
      new Promise<LocalRunView>((_resolve, fail) => { reject = fail }))
    const pending = store.controlRun(store.activeRun!.id, 'cancel')
    const failed = expect(pending).rejects.toThrow('A control failed')
    await store.selectConversation('conv_analyze_auth')
    reject(new Error('A control failed'))
    await failed
    expect(store.actionError).toBeNull()
  })
})
