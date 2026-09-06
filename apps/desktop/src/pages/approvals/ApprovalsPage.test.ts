import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import ApprovalsPage from './ApprovalsPage.vue'
import { mockGateway } from '@/shared/api'
import { useAppStore } from '@/stores/app.store'

const dummyRouter = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: { template: '<div></div>' } },
    { path: '/tasks/:taskId', component: { template: '<div></div>' } },
  ],
})

describe('ApprovalsPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockGateway.setDelay(0)
  })

  it('renders pending approvals and dangerous action target resource', async () => {
    const wrapper = mount(ApprovalsPage, {
      global: { plugins: [dummyRouter] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('安全审批中心')
    expect(wrapper.text()).toContain('待处理审批')
    expect(wrapper.text()).toContain('远程仓库推送 (git push)')
    expect(wrapper.text()).toContain('git push origin feat/f0-desktop-skeleton')
    expect(wrapper.text()).toContain('高风险 (High)')
  })

  it('opens secondary confirmation modal for high-risk actions', async () => {
    const wrapper = mount(ApprovalsPage, {
      attachTo: document.body,
      global: { plugins: [dummyRouter] },
    })
    await flushPromises()

    const approveBtn = wrapper.findAll('button').find((b) => b.text().includes('批准执行'))
    expect(approveBtn).toBeDefined()
    await approveBtn?.trigger('click')
    await flushPromises()

    expect(document.body.textContent).toContain('高危操作二次确认')
    expect(document.body.textContent).toContain('我已人工核验并完全知晓风险')
    wrapper.unmount()
  })

  it('renders offline state when Hub is disconnected', async () => {
    const appStore = useAppStore()
    appStore.connectionStatus = 'disconnected'

    const wrapper = mount(ApprovalsPage, {
      global: { plugins: [dummyRouter] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Local Hub 已断开连接')
  })
})
