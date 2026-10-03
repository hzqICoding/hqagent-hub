import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import AgentsPage from './AgentsPage.vue'
import { useAppStore } from '@/stores/app.store'
import { useAgentStore } from '@/stores/agent.store'
import { setLocalChatGatewayMode, mockGateway } from '@/shared/api'

describe('AgentsPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocalChatGatewayMode('mock')
    mockGateway.setDelay(0)
  })

  it('renders agents list with status badges', async () => {
    const appStore = useAppStore()
    await appStore.setScenario('happy-path')

    const wrapper = mount(AgentsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('Agent 实例管理与诊断')
    expect(wrapper.text()).toContain('刷新探测')
    expect(wrapper.text()).toContain('Claude Code')
  })

  it('displays empty state when first-run-no-agent scenario is active', async () => {
    const appStore = useAppStore()
    await appStore.setScenario('first-run-no-agent')

    const wrapper = mount(AgentsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('未发现任何本地 Agent')
  })

  it('filters agents by status', async () => {
    const appStore = useAppStore()
    await appStore.setScenario('happy-path')

    const agentStore = useAgentStore()
    await agentStore.fetchAgents()

    const wrapper = mount(AgentsPage)
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const disabledBtn = buttons.find((b) => b.text().includes('已停用'))
    expect(disabledBtn).toBeDefined()
    await disabledBtn?.trigger('click')
    await wrapper.vm.$nextTick()

    expect(agentStore.statusFilter).toBe('disabled')
  })
})
