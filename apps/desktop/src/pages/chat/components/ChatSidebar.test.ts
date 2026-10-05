import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ChatSidebar from './ChatSidebar.vue'
import { useChatStore } from '@/stores/chat.store'
import { HqSelect } from '@/shared/ui'

describe('ChatSidebar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    document.body.replaceChildren()
  })

  it('uses the active task workspace when opening the shared new task dialog', async () => {
    const store = useChatStore()
    store.workspaces = [
      {
        id: 'workspace-first',
        name: 'First',
        path: 'E:/first',
        vcs: 'git',
        lastOpenedAt: '2026-09-25T00:00:00Z',
      },
      {
        id: 'workspace-current',
        name: 'Current',
        path: 'E:/current',
        vcs: 'git',
        lastOpenedAt: '2026-09-25T00:00:00Z',
      },
    ]
    store.conversations = [{
      id: 'conversation-current',
      title: 'Current task',
      workspaceId: 'workspace-current',
      sceneId: 'develop',
      createdAt: '2026-09-25T00:00:00Z',
      updatedAt: '2026-09-25T00:00:00Z',
    }]
    store.activeConversationId = 'conversation-current'
    const wrapper = mount(ChatSidebar)

    await wrapper.findAll('button').find(button => button.text().includes('新建任务'))!.trigger('click')
    const workspaceSelect = wrapper.findAllComponents(HqSelect)[0]
    expect(workspaceSelect.props('modelValue')).toBe('workspace-current')
    expect(document.body.textContent).toContain('创建独立任务对话')
  })

  it('opens a new task for the explicitly selected empty project', async () => {
    const store = useChatStore()
    store.workspaces = [
      { id: 'workspace-a', name: 'Project A', path: 'E:/a', vcs: 'git', lastOpenedAt: '2026-09-25T00:00:00Z' },
      { id: 'workspace-empty', name: 'Empty Project', path: 'E:/empty', vcs: 'git', lastOpenedAt: '2026-09-25T00:00:00Z' },
    ]
    store.conversations = [{
      id: 'conversation-a', title: 'Task A', workspaceId: 'workspace-a', sceneId: 'analyze',
      createdAt: '2026-09-25T00:00:00Z', updatedAt: '2026-09-25T00:00:00Z',
    }]
    store.activeConversationId = 'conversation-a'
    const wrapper = mount(ChatSidebar)

    const emptyProjectButton = wrapper.findAll('button').find((button) =>
      button.text().includes('该项目暂无任务，点击新建')
    )
    await emptyProjectButton!.trigger('click')

    expect(wrapper.findAllComponents(HqSelect)[0].props('modelValue')).toBe('workspace-empty')
  })

  it('uses returned custom scenes and defaults to the active task scene', async () => {
    const store = useChatStore()
    store.workspaces = [{ id: 'workspace-a', name: 'Project A', path: 'E:/a', vcs: 'git', lastOpenedAt: '2026-09-25T00:00:00Z' }]
    store.scenes = [{
      id: 'scene-custom-rtk', name: 'RTK 定制分析', description: '定制', readOnly: true,
      version: 1, roles: [], updatedAt: '2026-09-25T00:00:00Z', isBuiltin: false,
    }]
    store.conversations = [{
      id: 'conversation-custom', title: 'RTK Task', workspaceId: 'workspace-a', sceneId: 'scene-custom-rtk',
      createdAt: '2026-09-25T00:00:00Z', updatedAt: '2026-09-25T00:00:00Z',
    }]
    store.activeConversationId = 'conversation-custom'
    const wrapper = mount(ChatSidebar)

    await wrapper.findAll('button').find(button => button.text().includes('新建任务'))!.trigger('click')
    const customSceneButton = Array.from(document.body.querySelectorAll<HTMLButtonElement>('button')).find(button =>
      button.textContent?.includes('RTK 定制分析')
    )!
    expect(customSceneButton.className).toContain('border-primary')
  })

  it('distinguishes folder-level plus new conversation from header new task', async () => {
    const store = useChatStore()
    store.workspaces = [
      { id: 'workspace-a', name: 'Project Alpha', path: 'E:/alpha', vcs: 'git', lastOpenedAt: '2026-09-25T00:00:00Z' },
    ]
    store.conversations = [
      {
        id: 'conversation-a',
        title: 'Alpha Task',
        workspaceId: 'workspace-a',
        sceneId: 'analyze',
        createdAt: '2026-09-25T00:00:00Z',
        updatedAt: '2026-09-25T00:00:00Z',
      },
    ]
    store.activeConversationId = 'conversation-a'
    const wrapper = mount(ChatSidebar)

    // 1. Click folder right-side '+' button
    const folderPlusBtn = wrapper.find('button[title="在此项目新建对话"]')
    expect(folderPlusBtn.exists()).toBe(true)
    await folderPlusBtn.trigger('click')

    expect(document.body.textContent).toContain('新建对话 · Project Alpha')
    expect(document.body.textContent).toContain('在当前项目「Project Alpha」下创建新对话')
    const lockedSelect = wrapper.findAllComponents(HqSelect)[0]
    expect(lockedSelect.props('modelValue')).toBe('workspace-a')
    expect(lockedSelect.props('disabled')).toBe(true)
    expect(document.body.textContent).toContain('创建对话')
    expect(document.body.textContent).not.toContain('选择项目目录')

    // 2. Click header '新建任务' button
    const cancelBtn = Array.from(document.body.querySelectorAll<HTMLButtonElement>('button')).find(b => b.textContent?.includes('取消'))
    cancelBtn?.click()
    const headerNewTaskBtn = wrapper.findAll('button').find(b => b.text().includes('新建任务'))!
    await headerNewTaskBtn.trigger('click')

    expect(document.body.textContent).toContain('新建任务')
    expect(document.body.textContent).toContain('创建独立任务对话')
    const unlockedSelect = wrapper.findAllComponents(HqSelect)[0]
    expect(unlockedSelect.props('disabled')).toBe(false)
    expect(document.body.textContent).toContain('创建任务')
    expect(document.body.textContent).toContain('选择项目目录')
  })

  it('switches between 项目任务, 原生会话, and 已归档 tabs', async () => {
    const store = useChatStore()
    store.workspaces = [
      { id: 'workspace-a', name: 'Project Alpha', path: 'E:/alpha', vcs: 'git', lastOpenedAt: '2026-09-25T00:00:00Z' },
    ]
    store.conversations = [
      {
        id: 'conversation-active',
        title: 'Active Task',
        workspaceId: 'workspace-a',
        sceneId: 'analyze',
        archived: false,
        createdAt: '2026-09-25T00:00:00Z',
        updatedAt: '2026-09-25T00:00:00Z',
      },
      {
        id: 'conversation-archived',
        title: 'Old Archived Task',
        workspaceId: 'workspace-a',
        sceneId: 'analyze',
        archived: true,
        createdAt: '2026-09-24T00:00:00Z',
        updatedAt: '2026-09-24T00:00:00Z',
      },
    ]
    const wrapper = mount(ChatSidebar)

    // Default: '项目任务' tab active
    expect(wrapper.text()).toContain('Active Task')
    expect(wrapper.text()).not.toContain('Old Archived Task')
    expect(wrapper.findComponent({ name: 'NativeSessionsPanel' }).exists()).toBe(false)

    // Switch to '原生会话' tab
    const nativeTabBtn = wrapper.findAll('button').find(b => b.text() === '原生会话')!
    await nativeTabBtn.trigger('click')

    expect(wrapper.findComponent({ name: 'NativeSessionsPanel' }).exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Active Task')

    // Switch to archived view via bottom toolbar button
    const archiveBtn = wrapper.find('button[data-testid="sidebar-archived-toggle"]')
    await archiveBtn.trigger('click')

    expect(store.showArchived).toBe(true)
    expect(wrapper.findComponent({ name: 'NativeSessionsPanel' }).exists()).toBe(false)
    expect(wrapper.text()).toContain('Old Archived Task')
    expect(wrapper.text()).not.toContain('Active Task')
  })

  it('renders project section and conversations grouped by workspace', () => {
    const store = useChatStore()
    store.workspaces = [
      { id: 'workspace-a', name: 'Project Alpha', path: 'E:/alpha', vcs: 'git', lastOpenedAt: '2026-09-25T00:00:00Z' },
    ]
    store.conversations = [
      {
        id: 'conversation-a',
        title: 'Project Task',
        workspaceId: 'workspace-a',
        sceneId: 'analyze',
        createdAt: '2026-09-25T00:00:00Z',
        updatedAt: '2026-09-25T00:00:00Z',
      },
    ]
    const wrapper = mount(ChatSidebar)

    expect(wrapper.text()).not.toContain('暂无临时对话')
    expect(wrapper.text()).toContain('项目')
    expect(wrapper.text()).toContain('Project Alpha')
    expect(wrapper.text()).toContain('Project Task')
  })

  it('guides user to register a project directory when no workspaces exist instead of using fallback', async () => {
    const store = useChatStore()
    store.workspaces = []
    store.conversations = []
    const wrapper = mount(ChatSidebar)

    expect(wrapper.text()).toContain('暂未登记项目，请先登记本地项目目录以开始任务')
    const registerBtn = wrapper.findAll('button').find(b => b.text().includes('登记项目目录'))
    expect(registerBtn).toBeDefined()
    await registerBtn!.trigger('click')

    expect(document.body.textContent).toContain('创建项目')
    expect(document.body.textContent).toContain('添加文件夹 · 选择项目目录')

    // Attempting to submit without selecting folder or typing path shows error guidance
    const submitBtn = Array.from(document.body.querySelectorAll<HTMLButtonElement>('button')).find(b =>
      b.textContent?.includes('创建项目')
    )
    // Disabled when no title and no workspace
    expect(submitBtn?.disabled).toBe(true)
  })

  it('renders create project modal matching Image 1 layout with character count, sources, and folder picker', async () => {
    const store = useChatStore()
    store.workspaces = [
      { id: 'workspace-a', name: 'Project Alpha', path: 'E:/alpha', vcs: 'git', lastOpenedAt: '2026-09-25T00:00:00Z' },
    ]
    const wrapper = mount(ChatSidebar)

    // Click project creation button
    const createProjectBtn = wrapper.find('button[title="创建项目"]')
    expect(createProjectBtn.exists()).toBe(true)
    await createProjectBtn.trigger('click')

    // Modal matching Image 1
    expect(document.body.textContent).toContain('创建项目')
    expect(document.body.textContent).toContain('项目名称')
    expect(document.body.textContent).toContain('0/80')
    expect(document.body.textContent).toContain('来源')
    expect(document.body.textContent).toContain('此电脑')
    expect(document.body.textContent).toContain('Git 仓库')
    expect(document.body.textContent).toContain('工作区')
    expect(document.body.textContent).toContain('添加文件夹 · 选择项目目录')
    expect(document.body.textContent).toContain('初始场景')
    expect(document.body.textContent).toContain('创建项目')
  })

  it('toggles archived view from bottom toolbar archive button', async () => {
    const store = useChatStore()
    store.workspaces = [
      { id: 'workspace-a', name: 'Project Alpha', path: 'E:/alpha', vcs: 'git', lastOpenedAt: '2026-09-25T00:00:00Z' },
    ]
    const wrapper = mount(ChatSidebar)

    const archiveBtn = wrapper.find('button[data-testid="sidebar-archived-toggle"]')
    expect(archiveBtn.exists()).toBe(true)
    expect(store.showArchived).toBe(false)

    await archiveBtn.trigger('click')
    expect(store.showArchived).toBe(true)

    await archiveBtn.trigger('click')
    expect(store.showArchived).toBe(false)
  })
})

