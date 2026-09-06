import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import TasksPage from './TasksPage.vue'
import { useAppStore } from '@/stores/app.store'
import { mockGateway } from '@/shared/api'

const dummyRouter = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: { template: '<div></div>' } },
    { path: '/tasks/:taskId', component: { template: '<div></div>' } },
  ],
})

describe('TasksPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockGateway.setDelay(0)
  })

  it('renders task list with status badges and filters', async () => {
    const wrapper = mount(TasksPage, {
      global: { plugins: [dummyRouter] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('任务中心')
    expect(wrapper.text()).toContain('为 Local Hub 事件总线补充断线补发的契约测试')
    expect(wrapper.text()).toContain('新建任务')
  })

  it('disables create task button when hubGate is active (F2-R1)', async () => {
    const appStore = useAppStore()
    appStore.hubGate = 'maintenance'
    appStore.hubGateReason = '系统维护排空中'

    const wrapper = mount(TasksPage, {
      global: { plugins: [dummyRouter] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('系统维护 Gate 保护中')
    expect(wrapper.text()).toContain('系统维护排空中')

    const createBtn = wrapper.findAll('button').find((b) => b.text().includes('新建任务'))
    expect(createBtn?.attributes('disabled')).toBeDefined()
  })

  it('renders offline state when Hub is disconnected', async () => {
    const appStore = useAppStore()
    appStore.connectionStatus = 'disconnected'

    const wrapper = mount(TasksPage, {
      global: { plugins: [dummyRouter] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Local Hub 已断开连接')
  })
})
