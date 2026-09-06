import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import OnboardingPage from './OnboardingPage.vue'
import { useAppStore } from '@/stores/app.store'

const dummyRouter = createRouter({
  history: createWebHistory(),
  routes: [{ path: '/', component: { template: '<div></div>' } }],
})

describe('OnboardingPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders step 1 by default', async () => {
    const appStore = useAppStore()
    await appStore.setScenario('happy-path')

    const wrapper = mount(OnboardingPage, {
      global: {
        plugins: [dummyRouter],
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('HQAgent-Hub 快速配置向导')
    expect(wrapper.text()).toContain('第 1 步')
    expect(wrapper.text()).toContain('本地优先，多 Agent 协同控制中心')
  })

  it('navigates through steps with next button', async () => {
    const appStore = useAppStore()
    await appStore.setScenario('happy-path')

    const wrapper = mount(OnboardingPage, {
      global: {
        plugins: [dummyRouter],
      },
    })
    await flushPromises()

    const nextBtn = wrapper.findAll('button').find((b) => b.text().includes('下一步'))
    expect(nextBtn).toBeDefined()

    await nextBtn?.trigger('click')
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('第 2 步')
    expect(wrapper.text()).toContain('检测 Local Hub 服务')
  })
})
