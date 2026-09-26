import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ChatPage from './ChatPage.vue'
import { setLocalChatGatewayMode, mockLocalChatGateway } from '@/shared/api'
import { useChatStore } from '@/stores/chat.store'

describe('ChatPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocalChatGatewayMode('mock')
    mockLocalChatGateway.reset()
  })

  it('renders chat workbench with conversations, messages, and composer', async () => {
    const wrapper = mount(ChatPage)
    // Wait for store init
    await new Promise((r) => setTimeout(r, 50))

    expect(wrapper.text()).toContain('项目任务')
    expect(wrapper.text()).toContain('新建任务')
    expect(wrapper.find('textarea').exists()).toBe(true)
    expect(wrapper.text()).toContain('当前任务连续对话')
    expect(wrapper.text()).not.toContain('新一轮上下文 (New)')
    expect(wrapper.text()).not.toContain('继续已有Agent会话 (Continue)')
  })

  it('displays active run snapshot drawer when conversation is active', async () => {
    const wrapper = mount(ChatPage)
    await new Promise((r) => setTimeout(r, 50))

    expect(wrapper.text()).toContain('本轮场景与执行详情')
    expect(wrapper.text()).toContain('本轮场景快照')
    expect(wrapper.text()).toContain('执行步骤')
    expect(wrapper.text()).toContain('验收方式')
    expect(wrapper.text()).toContain('原规划者验收')
    expect(wrapper.text()).toContain('原生 Session: native_planner_run_2')
    expect(wrapper.text()).toContain('验收证据: evidence_run_2_pending')
    expect(wrapper.text()).toContain('尚未产生验收结论')
  })

  it('allows user to type while keeping context mode internal', async () => {
    const wrapper = mount(ChatPage)
    await new Promise((r) => setTimeout(r, 50))

    const textarea = wrapper.find('textarea')
    await textarea.setValue('分析当前模块并输出方案')
    expect((textarea.element as HTMLTextAreaElement).value).toBe('分析当前模块并输出方案')

    expect(wrapper.findAll('button').some(button => button.text().includes('Continue'))).toBe(false)
  })

  it('opens the shared new task dialog from the chat header', async () => {
    const wrapper = mount(ChatPage)
    await new Promise((r) => setTimeout(r, 50))

    const headerButton = wrapper.findAll('button').filter(button =>
      button.text().includes('新建任务')
    ).at(-1)
    await headerButton!.trigger('click')

    expect(document.body.textContent).toContain('创建独立任务对话')
    expect(document.body.textContent).toContain('任务标题')
  })

  it('confirms an explicit one-shot Agent context reset from the header menu', async () => {
    const wrapper = mount(ChatPage)
    await new Promise((r) => setTimeout(r, 50))
    const store = useChatStore()
    await store.selectConversation('conv_analyze_auth')
    const resetSpy = vi.spyOn(store, 'requestContextReset')

    await wrapper.find('button[title="更多任务操作"]').trigger('click')
    const resetMenuItem = wrapper.findAll('button').find(button =>
      button.text().includes('重置 Agent 上下文')
    )
    expect(resetMenuItem?.attributes('disabled')).toBeUndefined()
    await resetMenuItem!.trigger('click')

    expect(document.body.textContent).toContain('新会话不会自动携带全部历史')
    const confirm = Array.from(document.body.querySelectorAll('button')).find(button =>
      button.textContent?.includes('确认重置')
    ) as HTMLButtonElement
    confirm.click()
    expect(resetSpy).toHaveBeenCalledOnce()
  })

  it('disables context reset while a run is active', async () => {
    const wrapper = mount(ChatPage)
    await new Promise((r) => setTimeout(r, 50))

    await wrapper.find('button[title="更多任务操作"]').trigger('click')
    const resetMenuItem = wrapper.findAll('button').find(button =>
      button.text().includes('重置 Agent 上下文')
    )
    expect(resetMenuItem?.attributes('disabled')).toBeDefined()
  })
})
