import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import TemplatesPage from './TemplatesPage.vue'
import { useAppStore } from '@/stores/app.store'
import { mockGateway } from '@/shared/api'

const dummyRouter = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: { template: '<div>Home</div>' } },
    { path: '/teams', component: { template: '<div>Teams</div>' } },
  ],
})

describe('TemplatesPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockGateway.setDelay(0)
  })

  it('renders template library cards with roles and compatibility metric', async () => {
    const wrapper = mount(TemplatesPage, {
      global: { plugins: [dummyRouter] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('开箱模板库 (Templates)')
    expect(wrapper.text()).toContain('标准全栈协作团队')
    expect(wrapper.text()).toContain('极速原型与敏捷构建')
    expect(wrapper.text()).toContain('代码审查与质量把关')
    expect(wrapper.text()).toContain('所需协作角色')
  })

  it('filters templates by category and search term', async () => {
    const wrapper = mount(TemplatesPage, {
      global: { plugins: [dummyRouter] },
    })
    await flushPromises()

    const searchInput = wrapper.find('input')
    await searchInput.setValue('全栈')
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('标准全栈协作团队')
    expect(wrapper.text()).not.toContain('极速原型与敏捷构建')
  })

  it('renders offline state when Hub is disconnected', async () => {
    const appStore = useAppStore()
    appStore.connectionStatus = 'disconnected'

    const wrapper = mount(TemplatesPage, {
      global: { plugins: [dummyRouter] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Local Hub 已断开连接')
  })
})
