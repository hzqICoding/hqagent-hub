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
    expect(wrapper.find('.hq-composer-row').exists()).toBe(true)
    expect(wrapper.find('input[type=radio]').exists()).toBe(false)
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
    await flushPromises()
    const resetMenuItem = [...document.body.querySelectorAll<HTMLButtonElement>('[role=menuitem]')].find(button => button.textContent?.includes('重置 Agent 上下文'))
    expect(resetMenuItem?.disabled).toBe(false)
    resetMenuItem!.click(); await flushPromises()

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
    await flushPromises()
    const resetMenuItem = [...document.body.querySelectorAll<HTMLButtonElement>('[role=menuitem]')].find(button => button.textContent?.includes('重置 Agent 上下文'))
    expect(resetMenuItem?.disabled).toBe(true)
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

  it('displays native session in workbench directly with banner confirmation and takes over conversation', async () => {
    const wrapper = await mountInitializedPage()
    const store = useChatStore()

    const mockNativeSession = {
      nativeSessionId: 'native_example_0',
      title: '终端会话 · 示例重构',
      agentType: 'claude' as const,
      workspaceId: store.workspaces[0].id,
      indexVersion: 1,
      sourceRevision: 'example_source_revision',
      activity: { activity: 'closed_confirmed' as const },
      format: { status: 'readable' as const, cliVersion: '1.0.0' },
      createdAt: '2026-10-05T00:00:00Z',
      updatedAt: '2026-10-05T00:00:00Z',
    }

    const sidebar = wrapper.findComponent({ name: 'ChatSidebar' })
    await sidebar.vm.$emit('select-native-session', mockNativeSession)
    await flushPromises()

    // 1. Displayed in main workbench instead of dialog
    expect(wrapper.find('[data-testid="native-session-workbench-banner"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('终端会话 · 示例重构')
    expect(wrapper.text()).toContain('终端原生会话（只读历史）')
    expect(wrapper.text()).toContain('请先在电脑终端里退出这个会话')

    // 2. Takeover button is disabled until checkbox is checked
    const takeoverBtn = wrapper.findAll('button').find(b => b.text().includes('接管并继续对话'))!
    expect(takeoverBtn.attributes('disabled')).toBeDefined()

    const checkbox = wrapper.find('[data-testid="native-session-workbench-banner"] input[type="checkbox"]')
    await checkbox.setValue(true)
    expect(takeoverBtn.attributes('disabled')).toBeUndefined()

    // 3. Click takeover: imports session and transitions to project task
    const importSpy = vi.spyOn(mockLocalChatGateway, 'importNativeSession')
    await takeoverBtn.trigger('click')
    await flushPromises()

    expect(importSpy).toHaveBeenCalledWith('native_example_0', {
      terminalClosedConfirmed: true,
      sourceRevision: 'example_source_revision',
      expectedIndexVersion: 1,
    })
    expect(store.activeConversation?.conversationKind).toBe('native')
  })

  it('merges consecutive tool calls in native session history into a single line', async () => {
    const wrapper = await mountInitializedPage()
    const store = useChatStore()

    vi.spyOn(mockLocalChatGateway, 'readNativeMessages').mockResolvedValueOnce({
      nativeSessionId: 'native_tool_merge_test',
      snapshotCursor: 'snap_1',
      sourceRevision: 'src_1',
      items: [
        {
          messageId: 'tool_msg_1',
          role: 'tool_summary',
          text: 'Bash: git status -s',
          segmentIndex: 0,
          segmentCount: 1,
          totalUtf8Bytes: 19,
          contentSha256: 'd16e78b36451dc121767a6d4ab89b083f686e0893aff8fff936bff2a7b87c019',
        },
        {
          messageId: 'tool_msg_2',
          role: 'tool_summary',
          text: 'Bash: npm run test',
          segmentIndex: 0,
          segmentCount: 1,
          totalUtf8Bytes: 18,
          contentSha256: 'c43a786452781d0da0f8d9dbb1483f2f7c71ca6c1b40c36563ff539e52cb0bf2',
        },
      ],
      hasMore: false,
    })

    const mockNativeSession = {
      nativeSessionId: 'native_tool_merge_test',
      title: '多工具调用原生会话',
      agentType: 'claude' as const,
      workspaceId: store.workspaces[0].id,
      indexVersion: 1,
      sourceRevision: 'src_1',
      activity: { activity: 'closed_confirmed' as const },
      format: { status: 'readable' as const, cliVersion: '1.0.0' },
      createdAt: '2026-10-05T00:00:00Z',
      updatedAt: '2026-10-05T00:00:00Z',
    }

    const sidebar = wrapper.findComponent({ name: 'ChatSidebar' })
    await sidebar.vm.$emit('select-native-session', mockNativeSession)
    await flushPromises()

    await vi.waitFor(() => {
      expect(wrapper.find('[data-testid="native-merged-tool-line"]').exists()).toBe(true)
    })

    const mergedLine = wrapper.find('[data-testid="native-merged-tool-line"]')
    expect(mergedLine.text()).toContain('执行了 2 个工具调用')
    expect(mergedLine.text()).toContain('Bash')
  })
})
