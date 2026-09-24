import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ChatPage from './ChatPage.vue'
import { setLocalChatGatewayMode, mockLocalChatGateway } from '@/shared/api'

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

    expect(wrapper.text()).toContain('本地对话')
    expect(wrapper.text()).toContain('新建')
    expect(wrapper.find('textarea').exists()).toBe(true)
    expect(wrapper.text()).toContain('新一轮上下文')
    expect(wrapper.text()).toContain('继续已有Agent会话')
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

  it('allows user to type into composer and toggle context modes', async () => {
    const wrapper = mount(ChatPage)
    await new Promise((r) => setTimeout(r, 50))

    const textarea = wrapper.find('textarea')
    await textarea.setValue('分析当前模块并输出方案')
    expect((textarea.element as HTMLTextAreaElement).value).toBe('分析当前模块并输出方案')

    // Find continue button
    const continueBtn = wrapper
      .findAll('button')
      .find((b) => b.text().includes('继续已有Agent会话'))
    expect(continueBtn).toBeDefined()
    await continueBtn?.trigger('click')
  })
})
