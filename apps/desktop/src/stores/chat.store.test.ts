import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useChatStore } from './chat.store'
import { setLocalChatGatewayMode, mockLocalChatGateway } from '@/shared/api'

describe('ChatStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocalChatGatewayMode('mock')
    mockLocalChatGateway.reset()
  })

  afterEach(() => {
    const store = useChatStore()
    store.stopPolling()
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
})
