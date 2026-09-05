import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import OverviewPage from './OverviewPage.vue'
import { useAppStore } from '@/stores/app.store'
import { mockGateway } from '@/shared/api'

const dummyRouter = createRouter({
  history: createWebHistory(),
  routes: [{ path: '/', component: { template: '<div></div>' } }],
})

describe('OverviewPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockGateway.setDelay(0)
  })

  it('renders overview page with bento card and metrics in happy-path scenario', async () => {
    const appStore = useAppStore()
    await appStore.setScenario('happy-path')

    const wrapper = mount(OverviewPage, {
      global: {
        plugins: [dummyRouter],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('HQAgent-Hub')
    expect(wrapper.text()).toContain('重点协作任务')
    expect(wrapper.text()).toContain('Agent 状态群')
  })

  it('renders offline state when hub is disconnected', async () => {
    const appStore = useAppStore()
    await appStore.setScenario('hub-disconnected')

    const wrapper = mount(OverviewPage, {
      global: {
        plugins: [dummyRouter],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Local Hub 未连接')
  })
})
