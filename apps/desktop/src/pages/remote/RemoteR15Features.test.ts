import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import RemoteDevicesPage from './RemoteDevicesPage.vue'
import RemoteChatPage from './RemoteChatPage.vue'
import { useRemoteChatStore } from '@/stores/remote-chat.store'
import { mockRemoteGateway } from '@/shared/api/mock-remote-gateway'
import { setRemoteGatewayForTesting } from '@/shared/api/remote-provider'
import type { RemoteMessageView } from '@hqagent/protocol'

describe('R1.5 Remote Features: Multi-PC, Workspace Grouping, Pagination, Settings & Offline Lock', () => {
  enableAutoUnmount(afterEach)
  let router: any

  beforeEach(async () => {
    setActivePinia(createPinia())
    setRemoteGatewayForTesting(mockRemoteGateway)
    mockRemoteGateway.workerOnline = true
    mockRemoteGateway.cursorExpired = false
    mockRemoteGateway.runs = []
    mockRemoteGateway.commands = []
    mockRemoteGateway.eventPages = []
    mockRemoteGateway.pendingEvents = []

    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/remote/devices', component: RemoteDevicesPage },
        { path: '/remote/chat', component: RemoteChatPage },
        { path: '/remote/pair', component: { template: '<div>Pair</div>' } },
        { path: '/remote/login', component: { template: '<div>Login</div>' } },
      ],
    })
    await router.push('/remote/devices')
  })

  afterEach(() => {
    const store = useRemoteChatStore()
    store.stopPolling()
    store.stopDevicePolling()
    setRemoteGatewayForTesting(null)
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  describe('RemoteDevicesPage (我的电脑)', () => {
    it('renders "我的电脑" title and lists paired computers with protocol v2 badges', async () => {
      const wrapper = mount(RemoteDevicesPage, {
        global: { plugins: [router] },
      })
      await flushPromises()

      expect(wrapper.text()).toContain('我的电脑')
      expect(wrapper.text()).toContain('Office PC (Alex)')
      expect(wrapper.text()).toContain('Home PC (Alex)')

      // Supported wire revisions v2 displays "支持互通 (v2)"
      expect(wrapper.text()).toContain('支持互通 (v2)')

      // Office PC is online, Home PC is offline
      expect(wrapper.text()).toContain('电脑在线')
      expect(wrapper.text()).toContain('电脑离线')
    })

    it('polls device status every 15s and pauses when document is hidden', async () => {
      vi.useFakeTimers()
      const fetchDevicesSpy = vi.spyOn(mockRemoteGateway, 'listDevices')

      mount(RemoteDevicesPage, {
        global: { plugins: [router] },
      })
      await flushPromises()

      const initialCount = fetchDevicesSpy.mock.calls.length
      expect(initialCount).toBeGreaterThanOrEqual(1)

      // Advance 15s while document is visible
      await vi.advanceTimersByTimeAsync(15000)
      await flushPromises()
      expect(fetchDevicesSpy.mock.calls.length).toBe(initialCount + 1)

      // Simulate document hidden
      Object.defineProperty(document, 'hidden', { value: true, configurable: true })
      await vi.advanceTimersByTimeAsync(15000)
      await flushPromises()
      // Should not poll while hidden
      expect(fetchDevicesSpy.mock.calls.length).toBe(initialCount + 1)

      // Simulate document becomes visible again
      Object.defineProperty(document, 'hidden', { value: false, configurable: true })
      document.dispatchEvent(new Event('visibilitychange'))
      await flushPromises()
      // Immediately refreshed on visibility change
      expect(fetchDevicesSpy.mock.calls.length).toBe(initialCount + 2)
    })

    it('navigates to /remote/chat with workerId query when clicking a computer card', async () => {
      const wrapper = mount(RemoteDevicesPage, {
        global: { plugins: [router] },
      })
      await flushPromises()

      const deviceCards = wrapper.findAll('main div.cursor-pointer')
      expect(deviceCards.length).toBeGreaterThanOrEqual(1)

      await deviceCards[0].trigger('click')
      await flushPromises()

      expect(router.currentRoute.value.path).toBe('/remote/chat')
      expect(router.currentRoute.value.query.workerId).toBe('worker_demo')
    })
  })

  describe('RemoteChatPage: Workspace Grouping & Navigation', () => {
    beforeEach(async () => {
      await router.push('/remote/chat?workerId=worker_demo')
    })

    it('shows current computer name in top bar and groups conversations by workspace in drawer', async () => {
      const wrapper = mount(RemoteChatPage, {
        global: { plugins: [router] },
      })
      const store = useRemoteChatStore()
      await flushPromises()

      // Top bar displays current computer name
      expect(wrapper.text()).toContain('Office PC (Alex)')

      // Conversations grouped by workspace in sidebar
      expect(store.conversationsByWorkspace.length).toBeGreaterThanOrEqual(1)
      expect(wrapper.text()).toContain('HQAgent-Hub')
    })
  })

  describe('Message Pagination with before Cursor', () => {
    it('loads earlier messages using before cursor and merges without duplicates', async () => {
      const store = useRemoteChatStore()
      await store.selectDevice('worker_demo')
      await store.fetchConversations()

      // Mock earlier message page returned by listMessages with before cursor
      const earlierMessages: RemoteMessageView[] = [
        {
          messageId: 'msg_earlier_000',
          conversationId: 'conversation_demo',
          role: 'user',
          text: '这是更早之前的历史消息',
          createdAt: '2026-09-26T11:50:00Z',
        },
      ]
      vi.spyOn(mockRemoteGateway, 'listMessages').mockResolvedValueOnce({
        items: earlierMessages,
        before: 'cur_even_earlier',
        snapshotCursor: 'snap_001',
        hasMore: false,
      })

      store.hasMoreMessages = true
      store.beforeCursor = 'msg_001'

      await store.loadEarlierMessages()
      await flushPromises()

      expect(store.messages.some((m) => m.messageId === 'msg_earlier_000')).toBe(true)
      expect(store.messages[0].messageId).toBe('msg_earlier_000')
      expect(store.hasMoreMessages).toBe(false)
    })
  })

  describe('Conversation Settings & Visibility', () => {
    it('updates conversation visibility to pc_only after secondary confirmation', async () => {
      await router.push('/remote/chat')
      const wrapper = mount(RemoteChatPage, {
        global: {
          plugins: [router],
          stubs: {
            HqDialog: {
              template: '<div v-if="open" class="dialog"><h3>{{ title }}</h3><slot /><slot name="footer" /></div>',
              props: ['open', 'title'],
            },
          },
        },
      })
      await flushPromises()

      // Open conversation settings
      const settingsBtn = wrapper.find('button[title="对话设置"]')
      expect(settingsBtn.exists()).toBe(true)
      await settingsBtn.trigger('click')
      await flushPromises()

      // Verify settings modal is open
      expect(wrapper.text()).toContain('对话设置')
      expect(wrapper.text()).toContain('可见性')

      // Select pc_only
      const pcOnlyRadio = wrapper.find<HTMLInputElement>('input[type="radio"][value="pc_only"]')
      expect(pcOnlyRadio.exists()).toBe(true)
      await pcOnlyRadio.setValue()
      await pcOnlyRadio.trigger('change')
      await flushPromises()

      // Click "保存" to trigger secondary confirmation modal for pc_only
      const saveBtn = wrapper.findAll('button').find((b) => b.text().trim() === '保存')
      expect(saveBtn).toBeDefined()
      await saveBtn!.trigger('click')
      await flushPromises()

      // Warning prompt displayed
      expect(wrapper.text()).toContain('设置为仅电脑可见确认')
      expect(wrapper.text()).toContain('该对话将从手机端列表中移除')

      // Confirm change to pc_only
      const updateSpy = vi.spyOn(mockRemoteGateway, 'updateConversation')
      const confirmPcOnlyBtn = wrapper.findAll('button').find((b) => b.text().includes('确认设置'))
      expect(confirmPcOnlyBtn).toBeDefined()
      await confirmPcOnlyBtn!.trigger('click')
      await flushPromises()

      expect(updateSpy).toHaveBeenCalledWith(
        'conversation_demo',
        expect.objectContaining({ visibility: 'pc_only' })
      )
    })
  })

  describe('Immediate Offline Rejection & Input Retention', () => {
    it('immediately rejects sending when offline, displays error, and retains composer text', async () => {
      await router.push('/remote/chat')
      mockRemoteGateway.workerOnline = false
      const wrapper = mount(RemoteChatPage, {
        global: { plugins: [router] },
      })
      const store = useRemoteChatStore()
      await flushPromises()

      expect(store.isWorkerOnline).toBe(false)

      // Type text into composer
      const textarea = wrapper.find('textarea')
      expect(textarea.exists()).toBe(true)
      await textarea.setValue('离线保留的未发送输入')

      // Trigger send via Enter key
      await textarea.trigger('keydown.enter')
      await flushPromises()

      // Rejects immediately with error message
      expect(wrapper.text()).toContain('设备离线，发送失败')

      // Composer text MUST be retained!
      expect(textarea.element.value).toBe('离线保留的未发送输入')
    })

    it('immediately rejects control actions and approvals when offline', async () => {
      mockRemoteGateway.workerOnline = false
      const store = useRemoteChatStore()
      await store.fetchDevices()

      await expect(store.controlRun('run_demo', 'cancel')).rejects.toThrow('设备离线，发送失败')
    })
  })

  describe('Busy Lock on Mobile', () => {
    it('disables send and displays busy banner when computer is executing', async () => {
      await router.push('/remote/chat')
      mockRemoteGateway.workerOnline = true
      const wrapper = mount(RemoteChatPage, {
        global: { plugins: [router] },
      })
      const store = useRemoteChatStore()
      await flushPromises()
      await store.selectConversation('conv_busy_demo_1')
      await flushPromises()

      expect(store.isConversationBusy).toBe(true)

      // Busy banner displayed
      expect(wrapper.text()).toContain('当前电脑正在执行，请等待完成')

      // Textarea and Send button disabled
      const textarea = wrapper.find('textarea')
      expect(textarea.attributes('disabled')).toBeDefined()

      const sendBtn = wrapper.find('footer button')
      expect(sendBtn.attributes('disabled')).toBeDefined()
    })
  })
})
