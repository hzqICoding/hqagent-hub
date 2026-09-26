import { afterEach, describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ChatPage from './ChatPage.vue'
import { setLocalChatGatewayMode, mockLocalChatGateway } from '@/shared/api'
import { useChatStore } from '@/stores/chat.store'

describe('ChatPage', () => {
  const wrappers: VueWrapper[] = []

  beforeEach(() => {
    setActivePinia(createPinia())
    setLocalChatGatewayMode('mock')
    mockLocalChatGateway.reset()
  })

  afterEach(() => {
    useChatStore().stopPolling()
    for (const wrapper of wrappers.splice(0)) wrapper.unmount()
    document.body.replaceChildren()
    vi.restoreAllMocks()
  })

  async function mountInitializedPage(): Promise<VueWrapper> {
    const wrapper = mount(ChatPage)
    wrappers.push(wrapper)
    const store = useChatStore()
    await vi.waitFor(() => {
      expect(store.activeConversationId).toBeTruthy()
      expect(store.isLoadingMessages).toBe(false)
      expect(store.isLoadingRun).toBe(false)
      expect(store.workspaces.length).toBeGreaterThan(0)
    })
    await flushPromises()
    return wrapper
  }

  it('renders chat workbench with conversations, messages, and composer', async () => {
    const wrapper = await mountInitializedPage()

    expect(wrapper.text()).toContain('项目任务')
    expect(wrapper.text()).toContain('新建任务')
    expect(wrapper.find('textarea').exists()).toBe(true)
    expect(wrapper.text()).toContain('当前任务连续对话')
    expect(wrapper.text()).not.toContain('新一轮上下文 (New)')
    expect(wrapper.text()).not.toContain('继续已有Agent会话 (Continue)')
  })

  it('displays active run snapshot drawer when conversation is active', async () => {
    const wrapper = await mountInitializedPage()

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
    const wrapper = await mountInitializedPage()

    const textarea = wrapper.find('textarea')
    await textarea.setValue('分析当前模块并输出方案')
    expect((textarea.element as HTMLTextAreaElement).value).toBe('分析当前模块并输出方案')

    expect(wrapper.findAll('button').some(button => button.text().includes('Continue'))).toBe(false)
  })

  it('opens the shared new task dialog from the chat header', async () => {
    const wrapper = await mountInitializedPage()

    const headerButton = wrapper.findAll('button').filter(button =>
      button.text().includes('新建任务')
    ).at(-1)
    await headerButton!.trigger('click')

    expect(document.body.textContent).toContain('创建独立任务对话')
    expect(document.body.textContent).toContain('任务标题')
  })

  it('confirms an explicit one-shot Agent context reset from the header menu', async () => {
    const wrapper = await mountInitializedPage()
    const store = useChatStore()
    await store.selectConversation('conv_analyze_auth')
    await vi.waitFor(() => {
      expect(store.activeConversationId).toBe('conv_analyze_auth')
      expect(store.isLoadingMessages).toBe(false)
      expect(store.isLoadingRun).toBe(false)
      expect(store.canResetContext).toBe(true)
    })
    await wrapper.vm.$nextTick()
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
    const wrapper = await mountInitializedPage()

    await wrapper.find('button[title="更多任务操作"]').trigger('click')
    const resetMenuItem = wrapper.findAll('button').find(button =>
      button.text().includes('重置 Agent 上下文')
    )
    expect(resetMenuItem?.attributes('disabled')).toBeDefined()
  })

  it('shows returned custom scene names and generic starter prompts', async () => {
    const customScene = await mockLocalChatGateway.createLocalScene({
      name: 'RTK 定制分析',
      roles: [{ roleId: 'analyst', roleName: 'RTK 分析员', agentInstanceId: 'claude-code-local', instructions: '分析', enabled: true }],
    }, 'chat-custom-scene')
    const conversation = await mockLocalChatGateway.createLocalConversation({
      title: 'RTK 对话', workspaceId: 'ws_local_hub', sceneId: customScene.id,
    })
    const wrapper = await mountInitializedPage()
    const store = useChatStore()
    await store.selectConversation(conversation.id)
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('RTK 定制分析')
    expect(wrapper.text()).toContain('分析当前工程代码结构并提出优化建议')
  })
})
