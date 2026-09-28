import { afterEach, describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ChatPage from './ChatPage.vue'
import { setLocalChatGatewayMode, mockLocalChatGateway } from '@/shared/api'
import { useChatStore } from '@/stores/chat.store'

describe('ChatMobile Layout and Interactions', () => {
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

  it('renders mobile menu button and opens/closes the sidebar drawer', async () => {
    const wrapper = await mountInitializedPage()

    // 1. Mobile menu button exists with proper title and accessible label
    const menuBtn = wrapper.find('button[title="打开任务列表"]')
    expect(menuBtn.exists()).toBe(true)
    expect(menuBtn.attributes('aria-label')).toBe('打开任务列表')

    // Initially mobile sidebar is closed (has -translate-x-full class)
    const sidebar = wrapper.findComponent({ name: 'ChatSidebar' })
    expect(sidebar.exists()).toBe(true)
    expect(sidebar.classes()).toContain('-translate-x-full')

    // 2. Click menu button to open drawer
    await menuBtn.trigger('click')
    await wrapper.vm.$nextTick()

    // Sidebar now has translate-x-0 class and shadow
    expect(sidebar.classes()).toContain('translate-x-0')

    // Backdrop is displayed
    const backdrop = wrapper.find('.fixed.inset-0.bg-black\\/50')
    expect(backdrop.exists()).toBe(true)

    // 3. Clicking backdrop closes drawer
    await backdrop.trigger('click')
    await wrapper.vm.$nextTick()

    expect(sidebar.classes()).toContain('-translate-x-full')
  })

  it('automatically closes mobile sidebar drawer when a conversation is selected', async () => {
    const wrapper = await mountInitializedPage()
    const store = useChatStore()

    // Open drawer
    const menuBtn = wrapper.find('button[title="打开任务列表"]')
    await menuBtn.trigger('click')
    await wrapper.vm.$nextTick()

    const sidebar = wrapper.findComponent({ name: 'ChatSidebar' })
    expect(sidebar.classes()).toContain('translate-x-0')

    // Pick another conversation
    const otherConv = store.conversations.find((c) => c.id !== store.activeConversationId)
    if (otherConv) {
      // Find the conversation element in the sidebar and click it
      const convButtons = sidebar.findAll('[role="button"]')
      const targetBtn = convButtons.find((btn) => btn.text().includes(otherConv.title))
      if (targetBtn) {
        await targetBtn.trigger('click')
        await wrapper.vm.$nextTick()
      } else {
        await store.selectConversation(otherConv.id)
        await wrapper.vm.$nextTick()
      }
    } else {
      // Re-select current conversation
      await store.selectConversation(store.activeConversationId!)
      await wrapper.vm.$nextTick()
    }

    // Drawer is automatically closed
    expect(sidebar.classes()).toContain('-translate-x-full')
  })

  it('closes mobile sidebar drawer via drawer close X button', async () => {
    const wrapper = await mountInitializedPage()

    // Open drawer
    const menuBtn = wrapper.find('button[title="打开任务列表"]')
    await menuBtn.trigger('click')
    await wrapper.vm.$nextTick()

    const sidebar = wrapper.findComponent({ name: 'ChatSidebar' })
    expect(sidebar.classes()).toContain('translate-x-0')

    // Click drawer close X button inside sidebar
    const closeBtn = sidebar.find('button[title="关闭任务列表"]')
    expect(closeBtn.exists()).toBe(true)
    await closeBtn.trigger('click')
    await wrapper.vm.$nextTick()

    expect(sidebar.classes()).toContain('-translate-x-full')
  })

  it('toggles and closes mobile run snapshot drawer with backdrop', async () => {
    const wrapper = await mountInitializedPage()

    // Header drawer button
    const drawerToggleBtn = wrapper.find('button[aria-label="执行详情"]')
    expect(drawerToggleBtn.exists()).toBe(true)

    // Initially open in test environment
    const snapshotDrawer = wrapper.findComponent({ name: 'RunSnapshotDrawer' })
    expect(snapshotDrawer.exists()).toBe(true)

    // Close drawer via close X button in RunSnapshotDrawer
    const closeX = snapshotDrawer.find('button[title="关闭执行详情"]')
    expect(closeX.exists()).toBe(true)
    await closeX.trigger('click')
    await wrapper.vm.$nextTick()

    expect(wrapper.findComponent({ name: 'RunSnapshotDrawer' }).exists()).toBe(false)

    // Reopen via header toggle button
    await drawerToggleBtn.trigger('click')
    await wrapper.vm.$nextTick()

    expect(wrapper.findComponent({ name: 'RunSnapshotDrawer' }).exists()).toBe(true)
  })

  it('ensures all mobile touch target buttons meet min 44x44px requirements', async () => {
    const wrapper = await mountInitializedPage()

    // Mobile sidebar toggle button
    const menuBtn = wrapper.find('button[title="打开任务列表"]')
    expect(menuBtn.classes()).toContain('min-w-[44px]')
    expect(menuBtn.classes()).toContain('min-h-[44px]')

    // New task button
    const newTaskBtn = wrapper.findAll('button').find((b) => b.text().includes('新建任务'))
    expect(newTaskBtn?.classes()).toContain('min-h-[44px]')
    expect(newTaskBtn?.classes()).toContain('min-w-[44px]')

    // More operations dropdown button
    const moreBtn = wrapper.find('button[title="更多任务操作"]')
    expect(moreBtn.classes()).toContain('min-w-[44px]')
    expect(moreBtn.classes()).toContain('min-h-[44px]')

    // Execution details button
    const detailsBtn = wrapper.find('button[aria-label="执行详情"]')
    expect(detailsBtn.classes()).toContain('min-w-[44px]')
    expect(detailsBtn.classes()).toContain('min-h-[44px]')

    // Drawer close buttons have min-w-[44px] min-h-[44px]
    const sidebar = wrapper.findComponent({ name: 'ChatSidebar' })
    const sidebarCloseBtn = sidebar.find('button[title="关闭任务列表"]')
    expect(sidebarCloseBtn.classes()).toContain('min-w-[44px]')
    expect(sidebarCloseBtn.classes()).toContain('min-h-[44px]')

    const snapshotDrawer = wrapper.findComponent({ name: 'RunSnapshotDrawer' })
    const snapshotCloseBtn = snapshotDrawer.find('button[title="关闭执行详情"]')
    expect(snapshotCloseBtn.classes()).toContain('min-w-[44px]')
    expect(snapshotCloseBtn.classes()).toContain('min-h-[44px]')
  })
})

describe('ScenesPage Mobile Responsive Layout', () => {
  it('renders scenes in single-column stacked layout and allows viewing and editing', async () => {
    setActivePinia(createPinia())
    setLocalChatGatewayMode('mock')
    mockLocalChatGateway.reset()

    const { default: ScenesPage } = await import('@/pages/scenes/ScenesPage.vue')
    const { useScenesStore } = await import('@/stores/scenes.store')

    const wrapper = mount(ScenesPage)
    const store = useScenesStore()

    await vi.waitFor(() => {
      expect(store.isLoading).toBe(false)
      expect(store.scenes.length).toBeGreaterThan(0)
      expect(store.currentScene).toBeTruthy()
    })
    await flushPromises()

    // 1. Single column layout: container has flex-col md:flex-row
    const container = wrapper.find('.flex-1.flex.flex-col.md\\:flex-row')
    expect(container.exists()).toBe(true)

    // 2. Aside exists and contains scene cards with mobile horizontal scroll
    const aside = wrapper.find('aside')
    expect(aside.exists()).toBe(true)
    expect(aside.text()).toContain('场景清单')
    expect(aside.text()).toContain('代码分析')
    expect(aside.text()).toContain('需求规划')
    expect(aside.text()).toContain('开发修复')

    // 3. Main area exists and displays active scene configuration
    const main = wrapper.find('main')
    expect(main.exists()).toBe(true)
    expect(main.text()).toContain('保存场景配置')

    // 4. Role instructions can be viewed and edited in mobile view
    const textareas = main.findAll('textarea')
    expect(textareas.length).toBeGreaterThan(0)
    await textareas[0].setValue('移动端修改的职责')
    expect((textareas[0].element as HTMLTextAreaElement).value).toBe('移动端修改的职责')

    // 5. Switching scenes in mobile list updates main detail
    const planBtn = aside.findAll('button').find((b) => b.text().includes('需求规划'))
    expect(planBtn).toBeDefined()
    await planBtn!.trigger('click')
    await wrapper.vm.$nextTick()
    expect(main.text()).toContain('需求规划')

    wrapper.unmount()
    document.body.replaceChildren()
  })
})
