import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useChatStore } from './chat.store'
import { HubApiError, mockLocalChatGateway, setLocalChatGatewayMode } from '@/shared/api'

describe('automatic conversation context', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocalChatGatewayMode('mock')
    mockLocalChatGateway.reset()
  })
  afterEach(() => {
    useChatStore().stopPolling()
    vi.restoreAllMocks()
  })

  it('starts a new task once, then sends follow-ups with continue automatically', async () => {
    const store = useChatStore()
    await store.init()
    await store.createConversation('new-context-test', store.workspaces[0].id, 'analyze')
    const send = vi.spyOn(mockLocalChatGateway, 'sendLocalMessage')
    await store.sendMessage('first-context-message')
    await store.sendMessage('second-context-message')
    expect(send.mock.calls.map(call => call[1].sessionMode)).toEqual(['new', 'continue'])
  })

  it('defaults existing conversations to continue and does not silently reset a failed session', async () => {
    const store = useChatStore()
    await store.init()
    expect(store.effectiveSessionMode).toBe('continue')
    store.resumptionError = '原会话无法恢复'
    const send = vi.spyOn(mockLocalChatGateway, 'sendLocalMessage')
    await expect(store.sendMessage('keep-original-context')).rejects.toThrow('原会话无法恢复')
    expect(send).not.toHaveBeenCalled()
    expect(store.pendingContextReset).toBe(false)
  })

  it('uses an explicit reset for exactly one accepted message', async () => {
    const store = useChatStore()
    await store.init()
    store.activeRun = null
    store.conversationRuns = []
    expect(store.requestContextReset()).toBe(true)
    expect(store.pendingContextReset).toBe(true)
    const send = vi.spyOn(mockLocalChatGateway, 'sendLocalMessage')
    await store.sendMessage('explicit-context-reset')
    expect(send.mock.calls[0][1].sessionMode).toBe('new')
    expect(store.pendingContextReset).toBe(false)
    await store.sendMessage('follow-reset-context')
    expect(send.mock.calls[1][1].sessionMode).toBe('continue')
  })

  it('preserves the one-shot reset when sending fails and permits undo', async () => {
    const store = useChatStore()
    await store.init()
    store.activeRun = null
    store.conversationRuns = []
    store.requestContextReset()
    vi.spyOn(mockLocalChatGateway, 'sendLocalMessage').mockRejectedValueOnce(new HubApiError('未接收', 'VALIDATION_FAILED', 422))
    await expect(store.sendMessage('reset-failed-send')).rejects.toThrow('未接收')
    expect(store.pendingContextReset).toBe(true)
    expect(store.effectiveSessionMode).toBe('new')
    store.cancelContextReset()
    expect(store.pendingContextReset).toBe(false)
    expect(store.effectiveSessionMode).toBe('continue')
  })

  it('does not transfer a pending reset to another conversation', async () => {
    const store = useChatStore()
    await store.init()
    store.activeRun = null
    store.conversationRuns = []
    store.requestContextReset()
    await store.createConversation('separate-context-task', store.workspaces[0].id, 'analyze')
    expect(store.pendingContextReset).toBe(false)
    expect(store.effectiveSessionMode).toBe('new')
  })

  it('keeps a late non-resumable error with its original conversation', async () => {
    const store = useChatStore()
    await store.init()
    await store.selectConversation('conv_analyze_auth')
    let rejectSend!: (reason: unknown) => void
    const pending = new Promise<any>((_resolve, reject) => { rejectSend = reject })
    vi.spyOn(mockLocalChatGateway, 'sendLocalMessage').mockReturnValueOnce(pending)

    const send = store.sendMessage('继续任务 A', 'continue')
    await store.selectConversation('conv_plan_security')
    rejectSend(new HubApiError('任务 A 的原生会话无法恢复', 'SESSION_NOT_RESUMABLE', 409))
    await expect(send).rejects.toMatchObject({ code: 'SESSION_NOT_RESUMABLE' })
    expect(store.resumptionError).toBeNull()

    await store.selectConversation('conv_analyze_auth')
    expect(store.resumptionError).toContain('任务 A')
    expect(store.canResetContext).toBe(true)
  })

  it('refuses reset while a run is active, paused, or a send is in flight', async () => {
    const store = useChatStore()
    await store.init()
    await store.selectConversation('conv_develop_ui')
    expect(store.requestContextReset()).toBe(false)
    await store.controlRun(store.activeRun!.id, 'pause')
    expect(store.requestContextReset()).toBe(false)
    store.activeRun = null
    store.conversationRuns = []
    let release!: (value: any) => void
    const pending = new Promise<any>((resolve) => { release = resolve })
    vi.spyOn(mockLocalChatGateway, 'sendLocalMessage').mockReturnValueOnce(pending)
    const send = store.sendMessage('正在发送的消息', 'new')
    expect(store.requestContextReset()).toBe(false)
    release({
      commandId: 'command-in-flight',
      conversationId: store.activeConversationId!,
      messageId: 'message-in-flight',
      runId: 'run_develop_2',
      status: 'accepted',
      duplicate: false,
    })
    await send
  })
})
