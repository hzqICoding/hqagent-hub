import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import ChatSidebar from './components/ChatSidebar.vue'
import ChatComposer from './components/ChatComposer.vue'
import RunSnapshotDrawer from './components/RunSnapshotDrawer.vue'
import ChatPage from './ChatPage.vue'
import { useChatStore } from '@/stores/chat.store'
import { mockLocalChatGateway } from '@/shared/api/mock-local-chat-gateway'
import { setLocalChatGatewayForTesting } from '@/shared/api/local-chat-provider'

describe('Remote Conversation Interoperability and Cross-Endpoint Busy Lock on PC (R1.5)', () => {
  let router: any

  beforeEach(async () => {
    setActivePinia(createPinia())
    mockLocalChatGateway.reset()
    setLocalChatGatewayForTesting(mockLocalChatGateway)

    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/chat', component: ChatPage },
        { path: '/remote-link', component: { template: '<div>Remote Link</div>' } },
      ],
    })
    await router.push('/chat')
  })

  afterEach(() => {
    setLocalChatGatewayForTesting(null)
    vi.restoreAllMocks()
  })

  it('renders "来自手机" badge in ChatSidebar for conversations with authority === remote', async () => {
    const store = useChatStore()
    await store.init()

    const wrapper = mount(ChatSidebar, {
      global: {
        plugins: [router],
        stubs: {
          HqButton: true,
          HqDialog: true,
          HqDropdown: {
            template: '<div><slot /><slot name="overlay" /></div>',
          },
          HqInput: true,
          HqSelect: true,
        },
      },
    })

    await flushPromises()

    // Find remote conversation
    const remoteConv = store.conversations.find((c) => c.authority === 'remote')
    expect(remoteConv).toBeDefined()
    expect(remoteConv?.title).toBe('手机远程：排查订单超时')

    // Sidebar should render the "来自手机" badge text
    expect(wrapper.text()).toContain('手机远程：排查订单超时')
    expect(wrapper.text()).toContain('来自手机')
  })

  it('renders "手机远程" badge in ChatPage header when remote conversation is active', async () => {
    const store = useChatStore()
    await store.init()
    const remoteConv = store.conversations.find((c) => c.authority === 'remote')
    await store.selectConversation(remoteConv!.id)

    const wrapper = mount(ChatPage, {
      global: {
        plugins: [router],
        stubs: {
          ChatSidebar: { template: '<div class="sidebar-stub" />' },
          ChatMessageItem: { template: '<div class="msg-stub" />' },
          ProcessActivityGroup: true,
          ChatComposer: { template: '<div class="composer-stub" />' },
          RunSnapshotDrawer: { template: '<div class="drawer-stub" />' },
          HqBadge: {
            template: '<span class="badge"><slot /></span>',
          },
          HqButton: true,
          HqDialog: true,
          HqDropdown: true,
        },
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('手机远程：排查订单超时')
    expect(wrapper.text()).toContain('手机远程')
  })

  it('enforces busy lock banner and disables input when mobile run is in progress', async () => {
    const store = useChatStore()
    await store.init()
    const remoteConv = store.conversations.find((c) => c.authority === 'remote')
    await store.selectConversation(remoteConv!.id)

    // Remote conversation is busy from mobile
    expect(store.isRemoteConversation).toBe(true)
    expect(store.isConversationBusy).toBe(true)

    const wrapper = mount(ChatComposer, {
      global: {
        stubs: {
          HqButton: true,
        },
      },
    })

    await flushPromises()

    // Alert banner for busy lock
    expect(wrapper.text()).toContain('对话正在进行，结束后再继续')

    // Textarea disabled & placeholder
    const textarea = wrapper.find('textarea')
    expect(textarea.attributes('disabled')).toBeDefined()
    expect(textarea.attributes('placeholder')).toContain('对话正在进行，结束后再继续')

    // When running from mobile, stop button is displayed and enabled (cancel is never locked)
    const stopBtn = wrapper.find('button[title*="中止当前执行轮次"]')
    expect(stopBtn.exists()).toBe(true)
    expect(stopBtn.attributes('disabled')).toBeUndefined()
  })

  it('allows typing and sending messages on remote conversations when idle/not busy', async () => {
    const store = useChatStore()
    await store.init()
    const remoteConv = store.conversations.find((c) => c.authority === 'remote')
    expect(remoteConv).toBeDefined()

    // Simulate idle remote conversation (mobile run finished)
    remoteConv!.busy = false
    remoteConv!.activeRunId = undefined
    remoteConv!.lastRunStatus = 'succeeded'
    await store.selectConversation(remoteConv!.id)

    expect(store.isConversationBusy).toBe(false)

    const wrapper = mount(ChatComposer, {
      global: {
        stubs: {
          HqButton: true,
        },
      },
    })

    await flushPromises()

    // No busy lock banner
    expect(wrapper.text()).not.toContain('对话正在进行')

    // Textarea is enabled
    const textarea = wrapper.find('textarea')
    expect(textarea.attributes('disabled')).toBeUndefined()

    // Sending message succeeds without 409 authority mismatch
    await expect(store.sendMessage('PC 端继续远程对话')).resolves.not.toThrow()
    expect(store.messages.some((m) => m.text === 'PC 端继续远程对话')).toBe(true)
  })

  it('allows run controls and approvals on remote conversations without authority mismatch', async () => {
    const store = useChatStore()
    await store.init()
    const remoteConv = store.conversations.find((c) => c.authority === 'remote')
    await store.selectConversation(remoteConv!.id)

    const wrapper = mount(RunSnapshotDrawer, {
      global: {
        stubs: {
          HqButton: true,
          HqBadge: true,
          HqDialog: true,
          HqMarkdown: true,
          ResolveSourceBadge: true,
        },
      },
    })

    await flushPromises()

    // R1.5 allows PC to control runs and approvals: NO read-only blocking banner
    expect(wrapper.text()).not.toContain('这是手机远程对话，运行控制请在手机上继续操作')

    // Cancel is NEVER locked even when busy from mobile
    await expect(store.controlRun('run_remote_1', 'cancel')).resolves.not.toThrow()

    // When idle / not busy, other control actions (e.g. pause) also succeed without 409 authority mismatch
    const updatedConv = store.conversations.find((c) => c.id === remoteConv!.id)!
    updatedConv.busy = false
    await expect(store.controlRun('run_remote_1', 'pause')).resolves.not.toThrow()
  })

  it('allows archive and rename on remote conversations in R1.5', async () => {
    const store = useChatStore()
    await store.init()
    const remoteConv = store.conversations.find((c) => c.authority === 'remote')
    expect(remoteConv).toBeDefined()

    // Rename succeeds without CONVERSATION_AUTHORITY_MISMATCH
    const renamed = await store.renameConversation(remoteConv!.id, '新标题：排查订单超时已完成')
    expect(renamed.title).toBe('新标题：排查订单超时已完成')
    expect(store.conversations.find((c) => c.id === remoteConv!.id)?.title).toBe('新标题：排查订单超时已完成')

    // Archive succeeds once run is completed / cancelled and not busy
    await store.controlRun('run_remote_1', 'cancel')
    const targetConv = store.conversations.find((c) => c.id === remoteConv!.id)!
    targetConv.busy = false
    targetConv.activeRunId = undefined
    targetConv.lastRunStatus = 'cancelled'
    expect(store.canArchiveConversation(targetConv)).toBe(true)

    const archived = await store.setConversationArchived(targetConv.id, true)
    expect(archived.archived).toBe(true)
  })

  it('ensures local conversations without authority or authority === local are completely unaffected', async () => {
    const store = useChatStore()
    await store.init()

    const localConv = store.conversations.find((c) => c.authority !== 'remote')
    expect(localConv).toBeDefined()
    expect(localConv?.authority).toBeUndefined()

    await store.selectConversation(localConv!.id)
    expect(store.isRemoteConversation).toBe(false)
    expect(store.isBusyFromOtherEnd).toBe(false)

    const wrapper = mount(ChatComposer, {
      global: {
        stubs: {
          HqButton: true,
        },
      },
    })

    await flushPromises()

    const textarea = wrapper.find('textarea')
    expect(textarea.attributes('disabled')).toBeUndefined()
    expect(textarea.attributes('placeholder')).toContain('向角色团队输入任务目标')
    expect(wrapper.text()).not.toContain('这是手机远程对话')
    expect(wrapper.text()).not.toContain('对话正在进行')
  })
})

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 10))
}
