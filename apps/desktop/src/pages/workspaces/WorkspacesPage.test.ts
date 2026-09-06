import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import WorkspacesPage from './WorkspacesPage.vue'
import { useWorkspaceStore } from '@/stores/workspace.store'
import { useAppStore } from '@/stores/app.store'
import { mockGateway } from '@/shared/api'

describe('WorkspacesPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockGateway.setDelay(0)
  })

  it('renders workspace list and kpi cards', async () => {
    const wrapper = mount(WorkspacesPage)
    await flushPromises()

    expect(wrapper.text()).toContain('工作区与项目管理')
    expect(wrapper.text()).toContain('HQAgent-Hub')
    expect(wrapper.text()).toContain('受管工作区总数')
    expect(wrapper.text()).toContain('.hqagent 记忆已就绪')
  })

  it('allows adding a new workspace via modal', async () => {
    const wrapper = mount(WorkspacesPage)
    await flushPromises()

    const workspaceStore = useWorkspaceStore()
    const initialCount = workspaceStore.workspaces.length

    workspaceStore.addWorkspace('D:/Projects/NewApp', 'NewApp')
    await wrapper.vm.$nextTick()

    expect(workspaceStore.workspaces).toHaveLength(initialCount + 1)
    expect(wrapper.text()).toContain('NewApp')
  })

  it('renders offline state when Hub is disconnected', async () => {
    const appStore = useAppStore()
    appStore.connectionStatus = 'disconnected'

    const wrapper = mount(WorkspacesPage)
    await flushPromises()

    expect(wrapper.text()).toContain('Local Hub 已断开连接')
  })
})
