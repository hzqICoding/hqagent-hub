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

describe('Remote Conversation Read-Only Display on PC', () => {
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

  it('renders "远程" badge in ChatSidebar for conversations with authority === remote', async () => {
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

    // Sidebar should render the 远程 badge text
    expect(wrapper.text()).toContain('手机远程：排查订单超时')
    expect(wrapper.text()).toContain('远程')
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

  it('disables input in ChatComposer and displays "这是手机远程对话，请在手机上继续"', async () => {
    const store = useChatStore()
    await store.init()
    const remoteConv = store.conversations.find((c) => c.authority === 'remote')
    await store.selectConversation(remoteConv!.id)

    expect(store.isRemoteConversation).toBe(true)

    const wrapper = mount(ChatComposer, {
      global: {
        stubs: {
          HqButton: true,
        },
      },
    })

    await flushPromises()

    // Alert banner
    expect(wrapper.text()).toContain('这是手机远程对话，电脑端仅供只读查看，请在手机上继续操作')

    // Textarea disabled & placeholder
    const textarea = wrapper.find('textarea')
    expect(textarea.attributes('disabled')).toBeDefined()
    expect(textarea.attributes('placeholder')).toContain('这是手机远程对话，请在手机上继续')

    // Send button disabled
    const sendBtn = wrapper.find('button[title*="发送目标指令"]')
    expect(sendBtn.attributes('disabled')).toBeDefined()
  })

  it('disables run controls and approvals in RunSnapshotDrawer for remote conversations', async () => {
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

    // Should display remote readonly guidance banner instead of interactive control buttons
    expect(wrapper.text()).toContain('这是手机远程对话，运行控制请在手机上继续操作')
    // No pause/resume buttons should be active
    expect(wrapper.text()).not.toContain('节点间暂停')
    expect(wrapper.text()).not.toContain('取消任务')
  })

  it('disables archive in store for remote conversations', async () => {
    const store = useChatStore()
    await store.init()
    const remoteConv = store.conversations.find((c) => c.authority === 'remote')
    expect(remoteConv).toBeDefined()

    expect(store.canArchiveConversation(remoteConv!)).toBe(false)
  })

  it('strictly rejects sending messages, controlling runs, and updating metadata with 409 CONVERSATION_AUTHORITY_MISMATCH', async () => {
    const store = useChatStore()
    await store.init()
    const remoteConv = store.conversations.find((c) => c.authority === 'remote')
    await store.selectConversation(remoteConv!.id)

    // 1. Send message rejection
    await expect(store.sendMessage('电脑试图发送消息')).rejects.toMatchObject({
      code: 'CONVERSATION_AUTHORITY_MISMATCH',
      status: 409,
    })

    // 2. Control run rejection
    await expect(store.controlRun('run_remote_1', 'pause')).rejects.toMatchObject({
      code: 'CONVERSATION_AUTHORITY_MISMATCH',
      status: 409,
    })

    // 3. Rename rejection
    await expect(store.renameConversation(remoteConv!.id, '新标题')).rejects.toMatchObject({
      code: 'CONVERSATION_AUTHORITY_MISMATCH',
      status: 409,
    })
  })

  it('ensures local conversations without authority or authority === local are completely unaffected', async () => {
    const store = useChatStore()
    await store.init()

    const localConv = store.conversations.find((c) => c.authority !== 'remote')
    expect(localConv).toBeDefined()
    expect(localConv?.authority).toBeUndefined()

    await store.selectConversation(localConv!.id)
    expect(store.isRemoteConversation).toBe(false)

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
  })
})

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 10))
}
