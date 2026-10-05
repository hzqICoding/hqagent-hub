import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { invoke } from '@tauri-apps/api/core'
import SettingsPage from './SettingsPage.vue'
import LocalChatLayout from '@/app/layouts/LocalChatLayout.vue'
import ChatSidebar from '@/pages/chat/components/ChatSidebar.vue'
import { useRemoteLinkStore } from '@/stores/remote-link.store'
import { mockLocalChatGateway } from '@/shared/api/mock-local-chat-gateway'
import { setLocalChatGatewayForTesting } from '@/shared/api/local-chat-provider'

vi.mock('@tauri-apps/api/core', () => ({ invoke: vi.fn() }))

describe('SettingsPage & Integrated Navigation', () => {
  let router: any

  beforeEach(() => {
    setActivePinia(createPinia())
    mockLocalChatGateway.reset()
    setLocalChatGatewayForTesting(mockLocalChatGateway)
    vi.mocked(invoke).mockResolvedValue(false as any)

    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/chat', component: { template: '<div>Chat Page</div>' } },
        { path: '/settings', component: SettingsPage },
        { path: '/agents', component: SettingsPage, props: { initialTab: 'agents' } },
        { path: '/scenes', component: SettingsPage, props: { initialTab: 'scenes' } },
        { path: '/remote-link', component: SettingsPage, props: { initialTab: 'remote-link' } },
      ],
    })
  })

  afterEach(() => {
    setLocalChatGatewayForTesting(null)
    vi.restoreAllMocks()
  })

  it('LocalChatLayout removes top-right clutter and renders clean brand header', async () => {
    await router.push('/chat')
    const wrapper = mount(LocalChatLayout, {
      global: {
        plugins: [router],
      },
    })
    await flushPromises()

    // 4 legacy links are removed from the top header
    expect(wrapper.find('nav').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('本地对话')

    // Brand header exists cleanly
    expect(wrapper.text()).toContain('HQAgent Hub')
    // Top-right buttons are cleanly removed
    expect(wrapper.find('a[href="/settings"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('本机 Worker')
  })

  it('SettingsPage renders all 5 tabs and defaults to agents', async () => {
    await router.push('/settings')
    const wrapper = mount(SettingsPage, {
      global: {
        plugins: [router],
      },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="settings-tab-agents"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="settings-tab-scenes"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="settings-tab-workspaces"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="settings-tab-remote-link"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="settings-tab-about"]').exists()).toBe(true)

    // Agents tab is active by default, contains heading
    expect(wrapper.text()).toContain('Agent 实例管理与诊断')
  })

  it('SettingsPage switches tabs when clicking tabs', async () => {
    await router.push('/settings')
    const wrapper = mount(SettingsPage, {
      global: {
        plugins: [router],
      },
    })
    await flushPromises()

    // Switch to remote-link
    await wrapper.find('[data-testid="settings-tab-remote-link"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('连接手机')

    // Switch to about
    await wrapper.find('[data-testid="settings-tab-about"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('HQAgent Hub')
    expect(wrapper.text()).toContain('实时系统日志与事件流')
  })

  it('ChatSidebar displays mobile connection status bar and navigates to remote-link tab', async () => {
    const store = useRemoteLinkStore()
    mockLocalChatGateway.setRemoteLinkState({
      state: 'paired',
      connectionStatus: 'online',
      deviceName: '我的手机',
      serverOrigin: 'https://hub.example.com',
      workerId: 'worker_001',
      lastConnectedAt: new Date().toISOString(),
    })

    const wrapper = mount(ChatSidebar, {
      global: {
        plugins: [router],
      },
    })
    await flushPromises()

    const statusBar = wrapper.find('[data-testid="sidebar-mobile-link-status"]')
    expect(statusBar.exists()).toBe(true)
    expect(statusBar.text()).toContain('手机连接状态')

    // When paired and connected
    store.linkView = {
      state: 'paired',
      connectionStatus: 'online',
    } as any
    await wrapper.vm.$nextTick()
    expect(statusBar.text()).toContain('已连接')

    // Click enters settings remote-link tab
    const pushSpy = vi.spyOn(router, 'push')
    await statusBar.trigger('click')
    expect(pushSpy).toHaveBeenCalledWith({
      path: '/settings',
      query: { tab: 'remote-link' },
    })
  })

  it('workspaces tab displays AuthorizedRootsSettings and read-only registered workspaces', async () => {
    await router.push('/settings?tab=workspaces')
    const wrapper = mount(SettingsPage, {
      global: {
        plugins: [router],
      },
    })
    await flushPromises()

    // Authorized roots section exists
    expect(wrapper.find('[data-testid="authorized-roots"]').exists()).toBe(true)

    // Registered workspaces section exists
    const workspacesSection = wrapper.find('[data-testid="registered-workspaces"]')
    expect(workspacesSection.exists()).toBe(true)
    expect(workspacesSection.text()).toContain('已登记项目')
  })

  it('workspaces tab shows empty state when no workspaces registered', async () => {
    vi.spyOn(mockLocalChatGateway, 'listLocalWorkspaces').mockResolvedValue([])
    await router.push('/settings?tab=workspaces')
    const wrapper = mount(SettingsPage, {
      global: {
        plugins: [router],
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('在对话页新建任务时登记项目')
  })

  it('remote-link tab shows jump notice to workspaces tab instead of inline authorized roots', async () => {
    await router.push('/settings?tab=remote-link')
    const wrapper = mount(SettingsPage, {
      global: {
        plugins: [router],
      },
    })
    await flushPromises()

    // Does NOT render inline authorized roots in remote-link tab
    expect(wrapper.find('[data-testid="authorized-roots"]').exists()).toBe(false)

    // Shows single-line description with link
    expect(wrapper.text()).toContain('手机可浏览的目录在『项目与授权目录』中设置')
    expect(wrapper.text()).toContain('前往设置')
  })

  it('renders autostart switch in about tab and toggles autostart via invoke', async () => {
    vi.mocked(invoke).mockImplementation(async (cmd) => {
      if (cmd === 'get_autostart_enabled') return false
      return undefined
    })
    await router.push('/settings?tab=about')
    const wrapper = mount(SettingsPage, {
      global: {
        plugins: [router],
      },
    })
    await flushPromises()

    const autostartSection = wrapper.find('[data-testid="settings-autostart-section"]')
    expect(autostartSection.exists()).toBe(true)
    expect(autostartSection.text()).toContain('开机自启')

    const switchBtn = wrapper.find('[data-testid="autostart-switch"] button[role="switch"]')
    expect(switchBtn.exists()).toBe(true)
    await switchBtn.trigger('click')
    await flushPromises()

    expect(invoke).toHaveBeenCalledWith('set_autostart_enabled', { enabled: true })
  })
})
