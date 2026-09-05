import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from './AppLayout.vue'
import { useAppStore } from '@/stores/app.store'
import { mockGateway } from '@/shared/api'

const dummyRouter = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: { template: '<div>Dashboard Content</div>' },
      meta: { title: '总览控制台' },
    },
  ],
})

describe('AppLayout', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockGateway.setDelay(0)
  })

  it('renders application skeleton with sidebar, header, and status bar', async () => {
    const appStore = useAppStore()
    await appStore.setScenario('happy-path')

    const wrapper = mount(AppLayout, {
      global: {
        plugins: [dummyRouter],
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('HQAgent-Hub')
    expect(wrapper.text()).toContain('总览')
    expect(wrapper.text()).toContain('Agent 管理')
    expect(wrapper.text()).toContain('日志')
    expect(wrapper.text()).toContain('检视器')
  })

  it('toggles log drawer and inspector panel', async () => {
    const appStore = useAppStore()
    await appStore.setScenario('happy-path')

    const wrapper = mount(AppLayout, {
      global: {
        plugins: [dummyRouter],
      },
    })
    await flushPromises()

    expect(appStore.isLogDrawerOpen).toBe(false)
    appStore.toggleLogDrawer()
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('系统日志 / 事件流')

    expect(appStore.inspector.isOpen).toBe(false)
    appStore.openInspector('task', null)
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('上下文检视')
    expect(wrapper.text()).toContain('当前活跃任务快照')
  })

  it('handles feature gating by showing disabled tooltip on sidebar item', async () => {
    const appStore = useAppStore()
    await appStore.setScenario('happy-path')

    const wrapper = mount(AppLayout, {
      global: {
        plugins: [dummyRouter],
      },
    })
    await flushPromises()

    // Updates feature is disabled in bootstrap.happy.json
    expect(appStore.isFeatureAvailable('updates')).toBe(false)
  })
})
