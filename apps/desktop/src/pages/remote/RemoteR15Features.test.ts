import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import RemoteDevicesPage from './RemoteDevicesPage.vue'
import RemoteChatPage from './RemoteChatPage.vue'
import { useRemoteChatStore, mergeRemoteMessages } from '@/stores/remote-chat.store'
import { mockRemoteGateway } from '@/shared/api/mock-remote-gateway'
import { setRemoteGatewayForTesting } from '@/shared/api/remote-provider'
import type { RemoteMessageView, RemoteConversationView } from '@hqagent/protocol'

describe('R1.5 Remote Features: Multi-PC, Workspace Grouping, Pagination, Settings & Offline Lock', () => {
  enableAutoUnmount(afterEach)
  let router: any

  beforeEach(async () => {
    setActivePinia(createPinia())
    mockRemoteGateway.reset()
    mockRemoteGateway.runs = []
    mockRemoteGateway.commands = []
    setRemoteGatewayForTesting(mockRemoteGateway)

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

      const sendBtn = wrapper.get('button[aria-label="发送消息"]')
      expect(sendBtn.attributes('disabled')).toBeDefined()
    })
  })

  describe('F1: Asynchronous Conversation Creation Placeholder & Event Resolution', () => {
    it('shows pending placeholder after 202 instead of fake conversation view, selects real conversation upon event, and fails after 30s timeout', async () => {
      vi.useFakeTimers()
      mockRemoteGateway.syncCreatedConversationImmediately = false
      const store = useRemoteChatStore()
      await store.fetchDevices()

      const createdId = await store.createConversation({
        targetWorkerId: 'worker_demo',
        title: '新任务对话',
        workspaceId: 'workspace_demo',
        sceneId: 'analyze',
        sceneVersion: 1,
        workerStoreId: 'store_demo',
      })

      expect(createdId).toBeDefined()
      // Does NOT forge RemoteConversationView in conversations
      expect(store.conversations.some((c) => c.conversationId === createdId)).toBe(false)
      // Pending placeholder exists
      expect(store.pendingConversation).toBeDefined()
      expect(store.pendingConversation?.status).toBe('creating')
      expect(store.pendingConversation?.title).toBe('新任务对话')

      // Timeout after 30s transitions to failed
      await vi.advanceTimersByTimeAsync(30000)
      expect(store.pendingConversation?.status).toBe('failed')

      // Can close failed placeholder
      store.clearPendingConversation()
      expect(store.pendingConversation).toBeNull()

      // Reset and test resolution via conversation.updated
      const nextId = await store.createConversation({
        targetWorkerId: 'worker_demo',
        title: '新任务对话2',
        workspaceId: 'workspace_demo',
        sceneId: 'analyze',
        sceneVersion: 1,
        workerStoreId: 'store_demo',
      })
      expect(store.pendingConversation?.status).toBe('creating')

      // Real conversation event arrives from computer
      const realConv: RemoteConversationView = {
        conversationId: nextId!,
        targetWorkerId: 'worker_demo',
        workerId: 'worker_demo',
        authority: 'remote',
        title: '新任务对话2',
        workspaceId: 'workspace_demo',
        sceneId: 'analyze',
        sceneVersion: 1,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        workerStoreId: 'store_demo',
        visibility: 'both',
        busy: false,
        busyFresh: true,
        metadataVersion: 1,
      }
      await store.applyEvent({
        type: 'conversation.updated',
        serverCursor: 'cur_conv_1',
        recordedAt: new Date().toISOString(),
        payload: realConv,
      })

      // Placeholder removed and real conversation automatically selected
      expect(store.pendingConversation).toBeNull()
      expect(store.activeConversationId).toBe(nextId)
      expect(store.conversations.some((c) => c.conversationId === nextId)).toBe(true)
    })
  })

  describe('F2: Conversation Settings 202 without Local Mutation & Conflict Handling', () => {
    it('does not modify local conversation on 202, updates on conversation.updated, and refetches on REMOTE_SYNC_CONFLICT', async () => {
      const store = useRemoteChatStore()
      await store.fetchDevices()
      await store.fetchConversations('worker_demo')
      await store.selectConversation('conversation_demo')

      const originalTitle = store.conversations.find((c) => c.conversationId === 'conversation_demo')?.title
      expect(originalTitle).toBe('远程分析系统架构')

      // Call updateConversationSettings
      await store.updateConversationSettings('conversation_demo', { title: '暂未确认的新标题' })

      // Local conversation title MUST NOT be mutated before server event
      expect(store.conversations.find((c) => c.conversationId === 'conversation_demo')?.title).toBe(originalTitle)
      expect(store.settingsNotice).toBe('等待电脑确认')

      // Server event arrives
      await store.applyEvent({
        type: 'conversation.updated',
        serverCursor: 'cur_upd_1',
        recordedAt: new Date().toISOString(),
        payload: {
          conversationId: 'conversation_demo',
          targetWorkerId: 'worker_demo',
          workerId: 'worker_demo',
          authority: 'remote',
          title: '电脑确认后的新标题',
          workspaceId: 'workspace_demo',
          sceneId: 'analyze',
          sceneVersion: 1,
          createdAt: '2026-09-26T12:00:00Z',
          updatedAt: new Date().toISOString(),
          workerStoreId: 'store_demo',
          visibility: 'both',
          metadataVersion: 2,
        },
      })

      // Now updated from event payload
      expect(store.conversations.find((c) => c.conversationId === 'conversation_demo')?.title).toBe('电脑确认后的新标题')
      expect(store.conversations.find((c) => c.conversationId === 'conversation_demo')?.metadataVersion).toBe(2)

      // REMOTE_SYNC_CONFLICT handling: refetches conversations and displays error
      const listSpy = vi.spyOn(mockRemoteGateway, 'listConversations')
      vi.spyOn(mockRemoteGateway, 'updateConversation').mockRejectedValueOnce(
        new (await import('@/shared/api')).RemoteApiError({
          message: '同步冲突，请刷新',
          code: 'REMOTE_SYNC_CONFLICT',
          status: 409,
        })
      )

      await expect(
        store.updateConversationSettings('conversation_demo', { title: '冲突标题' })
      ).rejects.toThrow()

      expect(listSpy).toHaveBeenCalled()
      expect(store.actionError).toBe('同步冲突，请刷新')
    })
  })

  describe('F3: Upsert on conversation.updated, Worker Filtering, and pc_only Removal', () => {
    it('upserts new conversation when no active conversation is selected, filters by workerId, and removes pc_only', async () => {
      const store = useRemoteChatStore()
      await store.fetchDevices()
      await store.selectDevice('worker_demo')
      store.activeConversationId = null // Ensure no active conversation

      // 1. New conversation event for current worker arrives -> upserted into conversations
      const newConv: RemoteConversationView = {
        conversationId: 'conv_pc_side_new',
        targetWorkerId: 'worker_demo',
        workerId: 'worker_demo',
        authority: 'local',
        title: '电脑端新开对话',
        workspaceId: 'workspace_demo',
        sceneId: 'analyze',
        sceneVersion: 1,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        workerStoreId: 'store_demo',
        visibility: 'both',
        metadataVersion: 1,
      }

      await store.applyEvent({
        type: 'conversation.updated',
        serverCursor: 'cur_f3_1',
        recordedAt: new Date().toISOString(),
        payload: newConv,
      })

      expect(store.conversations.some((c) => c.conversationId === 'conv_pc_side_new')).toBe(true)

      // 2. Event for another worker arrives -> ignored
      await store.applyEvent({
        type: 'conversation.updated',
        serverCursor: 'cur_f3_2',
        recordedAt: new Date().toISOString(),
        payload: {
          ...newConv,
          conversationId: 'conv_other_pc',
          workerId: 'worker_home_pc',
          targetWorkerId: 'worker_home_pc',
        },
      })
      expect(store.conversations.some((c) => c.conversationId === 'conv_other_pc')).toBe(false)

      // 3. pc_only event arrives -> removed from mobile list, clears active conversation if active
      await store.selectConversation('conv_pc_side_new')
      expect(store.activeConversationId).toBe('conv_pc_side_new')

      await store.applyEvent({
        type: 'conversation.updated',
        serverCursor: 'cur_f3_3',
        recordedAt: new Date().toISOString(),
        payload: {
          ...newConv,
          visibility: 'pc_only',
        },
      })

      expect(store.conversations.some((c) => c.conversationId === 'conv_pc_side_new')).toBe(false)
      expect(store.activeConversationId).toBeNull()
    })
  })

  describe('F4: Message Merging and Ordering', () => {
    it('higher revision replaces lower revision, out-of-order messages sorted by messageSequence, and deduplicates', () => {
      const existing: RemoteMessageView[] = [
        {
          messageId: 'msg_1',
          conversationId: 'conv_1',
          role: 'user',
          text: '初始消息版本 1',
          createdAt: '2026-09-26T12:00:00Z',
          messageSequence: 1,
          messageRevision: 1,
        },
        {
          messageId: 'temp_user_1',
          conversationId: 'conv_1',
          role: 'user',
          text: '临时用户输入',
          createdAt: '2026-09-26T12:01:00Z',
        },
      ]

      const incoming: RemoteMessageView[] = [
        {
          messageId: 'msg_3',
          conversationId: 'conv_1',
          role: 'assistant',
          text: '第三条消息（乱序提前到达）',
          createdAt: '2026-09-26T12:03:00Z',
          messageSequence: 3,
          messageRevision: 1,
        },
        {
          messageId: 'msg_1',
          conversationId: 'conv_1',
          role: 'user',
          text: '更高修订版本 2',
          createdAt: '2026-09-26T12:00:00Z',
          messageSequence: 1,
          messageRevision: 2,
        },
        {
          messageId: 'msg_2',
          conversationId: 'conv_1',
          role: 'user',
          text: '临时用户输入',
          createdAt: '2026-09-26T12:01:00Z',
          messageSequence: 2,
          messageRevision: 1,
        },
      ]

      const merged = mergeRemoteMessages(existing, incoming)

      // Length is 3 (temp_user_1 replaced by msg_2, msg_1 deduplicated with rev 2, msg_3 included)
      expect(merged).toHaveLength(3)

      // Ordered strictly by messageSequence 1, 2, 3
      expect(merged[0].messageId).toBe('msg_1')
      expect(merged[0].text).toBe('更高修订版本 2')
      expect(merged[0].messageRevision).toBe(2)

      expect(merged[1].messageId).toBe('msg_2')
      expect(merged[1].text).toBe('临时用户输入')

      expect(merged[2].messageId).toBe('msg_3')
      expect(merged[2].messageSequence).toBe(3)

      // Lower revision does NOT overwrite higher revision
      const mergedOlder = mergeRemoteMessages(merged, [
        {
          messageId: 'msg_1',
          conversationId: 'conv_1',
          role: 'user',
          text: '旧版本 1 重新到达',
          createdAt: '2026-09-26T12:00:00Z',
          messageSequence: 1,
          messageRevision: 1,
        },
      ])
      expect(mergedOlder[0].text).toBe('更高修订版本 2')
      expect(mergedOlder[0].messageRevision).toBe(2)
    })
  })

  describe('F5: Distinguish Version Outdated from State Not Ready', () => {
    it('throws REMOTE_REVISION_REQUIRED when wire revision 2 is unsupported, and REMOTE_STATE_NOT_READY when busySnapshotFresh is false', async () => {
      const store = useRemoteChatStore()
      await store.fetchDevices()
      await store.selectDevice('worker_demo')
      await store.selectConversation('conversation_demo')

      // Case 1: supportedWireRevisions lacks 2
      store.devices[0].supportedWireRevisions = [1]
      await expect(store.sendMessage('test')).rejects.toMatchObject({
        code: 'REMOTE_REVISION_REQUIRED',
        message: '电脑端版本过旧，请升级 HQAgent',
      })
      expect(store.sendError).toBe('电脑端版本过旧，请升级 HQAgent')

      // Case 2: supportedWireRevisions contains 2, but busySnapshotFresh is false
      store.devices[0].supportedWireRevisions = [1, 2]
      store.devices[0].busySnapshotFresh = false
      await expect(store.sendMessage('test')).rejects.toMatchObject({
        code: 'REMOTE_STATE_NOT_READY',
        message: '正在同步电脑状态，请稍后再试',
      })
      expect(store.sendError).toBe('正在同步电脑状态，请稍后再试')
    })
  })
})
