import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import TeamsPage from './TeamsPage.vue'
import { useAppStore } from '@/stores/app.store'
import { mockGateway } from '@/shared/api'

describe('TeamsPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockGateway.setDelay(0)
  })

  it('renders team profile list, role bindings, and resolution preview', async () => {
    const wrapper = mount(TeamsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('团队配置 (Team Profiles)')
    expect(wrapper.text()).toContain('HQ 默认双 Agent 团队')
    expect(wrapper.text()).toContain('角色分配与备用链')
    expect(wrapper.text()).toContain('路由解析结果预览')
  })

  it('renders 6-value resolveSource badges including fallback distinctly', async () => {
    const wrapper = mount(TeamsPage)
    await flushPromises()

    // In mock-gateway.ts, frontend_implementer is mapped to fallback
    expect(wrapper.text()).toContain('备用链故障降级')
    expect(wrapper.text()).toContain('降级原因:')
  })

  it('renders offline state when Hub is disconnected', async () => {
    const appStore = useAppStore()
    appStore.connectionStatus = 'disconnected'

    const wrapper = mount(TeamsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('Local Hub 已断开连接')
  })
})
