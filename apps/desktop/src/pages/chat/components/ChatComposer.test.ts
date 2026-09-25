import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ChatComposer from './ChatComposer.vue'
import { useChatStore } from '@/stores/chat.store'

describe('ChatComposer', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
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
    store.activeConversationId = 'conversation-test'
    store.resumptionError = '原生会话已失效'
    store.queuedMessages = [{ id: 'queued-1', text: '旧排队消息' }]
    const wrapper = mount(ChatComposer)
    const resetButton = wrapper.findAll('button').find(button =>
      button.text().includes('重置 Agent 上下文')
    )

    expect(resetButton?.attributes('disabled')).toBeDefined()
    store.queuedMessages = []
    await wrapper.vm.$nextTick()
    expect(resetButton?.attributes('disabled')).toBeUndefined()
    await resetButton!.trigger('click')
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
