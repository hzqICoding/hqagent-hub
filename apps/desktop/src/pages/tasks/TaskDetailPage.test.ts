import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import TaskDetailPage from './TaskDetailPage.vue'
import { useTaskStore } from '@/stores/task.store'
import { mockGateway } from '@/shared/api'

const dummyRouter = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/tasks/:taskId', component: TaskDetailPage },
    { path: '/tasks', component: { template: '<div></div>' } },
    { path: '/approvals', component: { template: '<div></div>' } },
  ],
})

describe('TaskDetailPage', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    mockGateway.setDelay(0)
    dummyRouter.push('/tasks/task_20260905_001')
    await dummyRouter.isReady()
  })

  it('renders task details, action buttons, and timeline nodes', async () => {
    const wrapper = mount(TaskDetailPage, {
      global: { plugins: [dummyRouter] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('task_20260905_001')
    expect(wrapper.text()).toContain('为 Local Hub 事件总线补充断线补发的契约测试')
    expect(wrapper.text()).toContain('暂停执行')
    expect(wrapper.text()).toContain('追加指令')
    expect(wrapper.text()).toContain('多 Agent 协作时间线')
  })

  it('Trap 1: append_instruction button is disabled when node is running', async () => {
    const wrapper = mount(TaskDetailPage, {
      global: { plugins: [dummyRouter] },
    })
    await flushPromises()

    const appendBtn = wrapper.findAll('button').find((b) => b.text().includes('追加指令'))
    expect(appendBtn).toBeDefined()
    expect(appendBtn?.attributes('disabled')).toBeDefined()
  })

  it('Trap 2: renders orphan process warning banner when orphanProcessIds are present', async () => {
    const wrapper = mount(TaskDetailPage, {
      global: { plugins: [dummyRouter] },
    })
    await flushPromises()

    const taskStore = useTaskStore()
    taskStore.orphanProcessIds = [14208, 14209]
    await flushPromises()

    expect(wrapper.text()).toContain('任务取消被拒绝：存在残留孤儿进程')
    expect(wrapper.text()).toContain('PID: 14208')
    expect(wrapper.text()).toContain('PID: 14209')
  })

  it('Trap 4: renders resolveSource badges on timeline nodes', async () => {
    const wrapper = mount(TaskDetailPage, {
      global: { plugins: [dummyRouter] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('全局团队配置')
  })

  it('switches to virtualized events tab without error', async () => {
    const wrapper = mount(TaskDetailPage, {
      global: { plugins: [dummyRouter] },
    })
    await flushPromises()

    const eventsTab = wrapper.findAll('button').find((b) => b.text().includes('实时事件流'))
    expect(eventsTab).toBeDefined()
    await eventsTab?.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('自动滚动至最新')
    expect(wrapper.text()).toContain('agent.progress')
  })
})
