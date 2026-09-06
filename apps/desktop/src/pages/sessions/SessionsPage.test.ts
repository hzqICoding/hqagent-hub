import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import SessionsPage from './SessionsPage.vue'
import { mockGateway } from '@/shared/api'
import { useAppStore } from '@/stores/app.store'

const dummyRouter = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: { template: '<div></div>' } },
    { path: '/tasks/:taskId', component: { template: '<div></div>' } },
  ],
})

describe('SessionsPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockGateway.setDelay(0)
  })

  it('renders session list with agent names, status, and resume button', async () => {
    const wrapper = mount(SessionsPage, {
      global: { plugins: [dummyRouter] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('会话历史')
    expect(wrapper.text()).toContain('Claude Code')
    expect(wrapper.text()).toContain('Codex App Server')
    expect(wrapper.text()).toContain('恢复会话')
  })

  it('filters sessions by search input', async () => {
    const wrapper = mount(SessionsPage, {
      global: { plugins: [dummyRouter] },
    })
    await flushPromises()

    const searchInput = wrapper.find('input[type="text"]')
    await searchInput.setValue('sess_claude')
    await flushPromises()

    expect(wrapper.text()).toContain('sess_claude')
  })

  it('renders offline state when Hub is disconnected', async () => {
    const appStore = useAppStore()
    appStore.connectionStatus = 'disconnected'

    const wrapper = mount(SessionsPage, {
      global: { plugins: [dummyRouter] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Local Hub 已断开连接')
  })
})
