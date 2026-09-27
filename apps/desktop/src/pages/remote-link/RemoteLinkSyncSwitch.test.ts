import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import RemoteLinkPage from './RemoteLinkPage.vue'
import ChatSidebar from '@/pages/chat/components/ChatSidebar.vue'
import { useRemoteLinkStore } from '@/stores/remote-link.store'
import { useChatStore } from '@/stores/chat.store'
import { mockLocalChatGateway } from '@/shared/api/mock-local-chat-gateway'
import { setLocalChatGatewayForTesting } from '@/shared/api/local-chat-provider'

describe('R1.5 Sync Master Switch & Visibility Filtering', () => {
  enableAutoUnmount(afterEach)
  let router: any

  beforeEach(async () => {
    setActivePinia(createPinia())
    mockLocalChatGateway.reset()
    setLocalChatGatewayForTesting(mockLocalChatGateway)

    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/remote-link', component: RemoteLinkPage },
        { path: '/chat', component: { template: '<div>Chat</div>' } },
      ],
    })
    await router.push('/remote-link')
  })

  afterEach(() => {
    setLocalChatGatewayForTesting(null)
    vi.restoreAllMocks()
  })

  describe('RemoteLinkPage: Global Sync Master Switch', () => {
    it('renders sync master switch and opens danger confirmation dialog when clicking disable', async () => {
      // Setup paired state with mirrorEnabled = true
      mockLocalChatGateway.mockSimulatePairingSuccess('worker_demo')
      await mockLocalChatGateway.setRemoteSyncSettings({ mirrorEnabled: true, expectedVersion: 1 })

      const wrapper = mount(RemoteLinkPage, {
        global: {
          plugins: [router],
          stubs: {
            HqButton: false,
            HqBadge: false,
            HqDialog: {
              template: '<div v-if="open" class="dialog"><h3>{{ title }}</h3><slot /><slot name="footer" /></div>',
              props: ['open', 'title'],
            },
            QrCodeView: true,
          },
        },
      })
      const linkStore = useRemoteLinkStore()
      await flushPromises()

      expect(linkStore.isPaired).toBe(true)
      expect(linkStore.mirrorEnabled).toBe(true)
      expect(wrapper.text()).toContain('同步总开关')
      expect(wrapper.text()).toContain('已开启')

      // Click "关闭同步" button
      const disableBtn = wrapper.findAll('button').find((b) => b.text().includes('关闭同步'))
      expect(disableBtn).toBeDefined()
      await disableBtn!.trigger('click')
      await flushPromises()

      // Danger confirmation dialog should be open with warning
      expect(wrapper.text()).toContain('关闭同步确认')
      expect(wrapper.text()).toContain('警告：该操作将影响手机端展示')
      expect(wrapper.text()).toContain('服务器上这台电脑的对话副本将被删除')

      // Cancel keeps mirrorEnabled = true
      const cancelBtn = wrapper.findAll('button').find((b) => b.text() === '取消' && b.isVisible())
      if (cancelBtn) {
        await cancelBtn.trigger('click')
        await flushPromises()
        expect(linkStore.mirrorEnabled).toBe(true)
      }

      // Re-open and confirm disable
      await disableBtn!.trigger('click')
      await flushPromises()

      const setSyncSpy = vi.spyOn(mockLocalChatGateway, 'setRemoteSyncSettings')
      const confirmDisableBtn = wrapper.findAll('button').find((b) => b.text().includes('确认关闭'))
      expect(confirmDisableBtn).toBeDefined()
      await confirmDisableBtn!.trigger('click')
      await flushPromises()

      expect(setSyncSpy).toHaveBeenCalledWith(expect.objectContaining({ mirrorEnabled: false }))
      expect(linkStore.mirrorEnabled).toBe(false)
      expect(wrapper.text()).toContain('已关闭')
    })

    it('enables sync immediately when clicking enable sync without modal', async () => {
      mockLocalChatGateway.mockSimulatePairingSuccess('worker_demo')
      await mockLocalChatGateway.setRemoteSyncSettings({ mirrorEnabled: false, expectedVersion: 1 })

      const wrapper = mount(RemoteLinkPage, {
        global: {
          plugins: [router],
          stubs: {
            HqButton: false,
            HqBadge: false,
            HqDialog: false,
            QrCodeView: true,
          },
        },
      })
      const linkStore = useRemoteLinkStore()
      await flushPromises()

      expect(linkStore.mirrorEnabled).toBe(false)
      expect(wrapper.text()).toContain('已关闭')

      const setSyncSpy = vi.spyOn(mockLocalChatGateway, 'setRemoteSyncSettings')
      const enableBtn = wrapper.findAll('button').find((b) => b.text().includes('开启同步'))
      expect(enableBtn).toBeDefined()
      await enableBtn!.trigger('click')
      await flushPromises()

      expect(setSyncSpy).toHaveBeenCalledWith(expect.objectContaining({ mirrorEnabled: true }))
      expect(linkStore.mirrorEnabled).toBe(true)
    })
  })

  describe('ChatSidebar: Visibility Filter and "显示已隐藏的对话"', () => {
    it('hides mobile_only conversations by default, and reveals them when toggle is checked', async () => {
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

      // Default: includeHiddenConversations is false
      expect(store.includeHiddenConversations).toBe(false)
      // Mobile-only conversation ('手机专用：紧急生产巡检') is filtered out from sidebar
      expect(wrapper.text()).not.toContain('手机专用：紧急生产巡检')

      // Check "显示已隐藏的对话"
      const checkbox = wrapper.find<HTMLInputElement>('input[type="checkbox"]')
      expect(checkbox.exists()).toBe(true)
      await checkbox.setValue(true)
      await checkbox.trigger('change')
      await flushPromises()

      expect(store.includeHiddenConversations).toBe(true)
      // Now mobile-only conversation is visible with "仅手机" badge
      expect(wrapper.text()).toContain('手机专用：紧急生产巡检')
      expect(wrapper.text()).toContain('仅手机')
    })
  })
})
