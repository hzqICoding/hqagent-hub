import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ChatComposer from './ChatComposer.vue'
import { useChatStore } from '@/stores/chat.store'
import { HubApiError, mockLocalChatGateway, setLocalChatGatewayMode } from '@/shared/api'

describe('ChatComposer', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocalChatGatewayMode('mock')
    mockLocalChatGateway.reset()
  })

  afterEach(() => {
    useChatStore().stopPolling()
    vi.restoreAllMocks()
  })

  it('keeps drafts isolated by conversation and switching alone does not send', async () => {
    const store = useChatStore()
    await store.init()
    await store.selectConversation('conv_analyze_auth')
    const send = vi.spyOn(mockLocalChatGateway, 'sendLocalMessage')
    const wrapper = mount(ChatComposer)

    await wrapper.find('textarea').setValue('任务 A 草稿')
    await store.selectConversation('conv_plan_security')
    await wrapper.vm.$nextTick()
    expect((wrapper.find('textarea').element as HTMLTextAreaElement).value).toBe('')
    await wrapper.find('textarea').setValue('任务 B 草稿')

    await store.selectConversation('conv_analyze_auth')
    await wrapper.vm.$nextTick()
    expect((wrapper.find('textarea').element as HTMLTextAreaElement).value).toBe('任务 A 草稿')
    expect(store.getConversationDraft('conv_plan_security')).toBe('任务 B 草稿')
    expect(send).not.toHaveBeenCalled()
  })

  it('restores a failed send only to its original empty draft', async () => {
    const store = useChatStore()
    await store.init()
    await store.selectConversation('conv_analyze_auth')
    let rejectSend!: (reason: unknown) => void
    const pending = new Promise<any>((_resolve, reject) => { rejectSend = reject })
    vi.spyOn(mockLocalChatGateway, 'sendLocalMessage').mockReturnValueOnce(pending)
    const wrapper = mount(ChatComposer)

    await wrapper.find('textarea').setValue('任务 A 待发送内容')
    await wrapper.find('button[title="发送目标指令 (Enter)"]').trigger('click')
    await store.selectConversation('conv_plan_security')
    await wrapper.find('textarea').setValue('任务 B 新草稿')
    rejectSend(new HubApiError('网络失败', 'HUB_NOT_READY', 503))
    await flushPromises()

    expect((wrapper.find('textarea').element as HTMLTextAreaElement).value).toBe('任务 B 新草稿')
    expect(store.getConversationDraft('conv_analyze_auth')).toBe('任务 A 待发送内容')
  })

  it('does not resurrect a failed prompt after the draft was edited and cleared again', async () => {
    const store = useChatStore()
    await store.init()
    await store.selectConversation('conv_analyze_auth')
    let rejectSend!: (reason: unknown) => void
    const pending = new Promise<any>((_resolve, reject) => { rejectSend = reject })
    vi.spyOn(mockLocalChatGateway, 'sendLocalMessage').mockReturnValueOnce(pending)
    const wrapper = mount(ChatComposer)

    await wrapper.find('textarea').setValue('已经发送的旧提示')
    await wrapper.find('button[title="发送目标指令 (Enter)"]').trigger('click')
    store.setConversationDraft('conv_analyze_auth', '用户后来输入的新草稿')
    store.setConversationDraft('conv_analyze_auth', '')
    rejectSend(new HubApiError('网络失败', 'HUB_NOT_READY', 503))
    await flushPromises()

    expect(store.getConversationDraft('conv_analyze_auth')).toBe('')
  })

  it('shows queued instructions only in their own conversation', async () => {
    const store = useChatStore()
    await store.init()
    await store.selectConversation('conv_develop_ui')
    let release!: (value: any) => void
    const pending = new Promise<any>((resolve) => { release = resolve })
    vi.spyOn(mockLocalChatGateway, 'sendLocalMessage').mockReturnValueOnce(pending)
    const send = store.sendMessage('任务 A 排队指令')
    expect(store.queuedMessages.map((message) => message.text)).toEqual(['任务 A 排队指令'])

    await store.selectConversation('conv_analyze_auth')
    expect(store.queuedMessages).toEqual([])
    release({
      commandId: 'queued-own-conversation',
      conversationId: 'conv_develop_ui',
      messageId: 'queued-message',
      runId: 'run_develop_2',
      status: 'queued',
      duplicate: false,
    })
    await send
  })

  it('removes permanent New/Continue controls and shows a cancellable one-shot reset', async () => {
    const store = useChatStore()
    store.activeConversationId = 'conversation-test'
    expect(store.requestContextReset()).toBe(true)
    const cancelContextReset = vi.spyOn(store, 'cancelContextReset')
    const wrapper = mount(ChatComposer)

    expect(wrapper.text()).toContain('当前任务连续对话')
    expect(wrapper.text()).toContain('下一条消息将使用新的 Agent 会话')
    expect(wrapper.text()).not.toContain('新一轮上下文 (New)')
    expect(wrapper.text()).not.toContain('继续已有Agent会话 (Continue)')

    const cancelButton = wrapper.findAll('button').find(button =>
      button.text().includes('撤销重置')
    )
    await cancelButton!.trigger('click')
    expect(cancelContextReset).toHaveBeenCalledOnce()
  })

  it('routes recovery errors to the confirmed reset flow and disables it while queued', async () => {
    const store = useChatStore()
    await store.init()
    await store.selectConversation('conv_develop_ui')
    let release!: (value: any) => void
    const pending = new Promise<any>((resolve) => { release = resolve })
    vi.spyOn(mockLocalChatGateway, 'sendLocalMessage').mockReturnValueOnce(pending)
    const send = store.sendMessage('旧排队消息')
    store.resumptionError = '原生会话已失效'
    const wrapper = mount(ChatComposer)
    const resetButton = wrapper.findAll('button').find(button =>
      button.text().includes('重置 Agent 上下文')
    )

    expect(resetButton?.attributes('disabled')).toBeDefined()
    release({
      commandId: 'command-queued',
      conversationId: 'conv_develop_ui',
      messageId: 'message-queued',
      runId: 'run_develop_2',
      status: 'queued',
      duplicate: false,
    })
    await send
    store.activeRun = null
    store.conversationRuns = []
    store.resumptionError = '原生会话已失效'
    await wrapper.vm.$nextTick()
    const enabledResetButton = wrapper.findAll('button').find(button =>
      button.text().includes('重置 Agent 上下文')
    )
    expect(enabledResetButton?.attributes('disabled')).toBeUndefined()
    await enabledResetButton!.trigger('click')
    expect(wrapper.emitted('request-context-reset')).toHaveLength(1)
  })

  it('does not send while conversation messages or the active run are loading', async () => {
    const store = useChatStore()
    store.isLoadingMessages = true
    const wrapper = mount(ChatComposer)
    await wrapper.find('textarea').setValue('切换对话期间不应发送')

    const sendButton = wrapper.find('button[title="发送目标指令 (Enter)"]')
    expect(sendButton.attributes('disabled')).toBeDefined()

    store.isLoadingMessages = false
    store.isLoadingRun = true
    await wrapper.vm.$nextTick()
    expect(sendButton.attributes('disabled')).toBeDefined()
  })
})
