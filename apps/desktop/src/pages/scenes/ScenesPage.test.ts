import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ScenesPage from './ScenesPage.vue'
import { setLocalChatGatewayMode, mockLocalChatGateway } from '@/shared/api'
import { HqSelect } from '@/shared/ui'

describe('ScenesPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocalChatGatewayMode('mock')
    mockLocalChatGateway.reset()
  })
  afterEach(() => { vi.restoreAllMocks() })

  it('renders scenes list and role configuration studio', async () => {
    const wrapper = mount(ScenesPage)
    await new Promise((r) => setTimeout(r, 50))

    expect(wrapper.text()).toContain('预置场景清单')
    expect(wrapper.text()).toContain('代码分析')
    expect(wrapper.text()).toContain('需求规划')
    expect(wrapper.text()).toContain('开发修复')
    expect(wrapper.text()).toContain('保存场景配置')
  })

  it('locks read-only roles with badge and prevents privilege escalation', async () => {
    const wrapper = mount(ScenesPage)
    await new Promise((r) => setTimeout(r, 50))

    // analyst is read-only
    expect(wrapper.text()).toContain('只读约束 (禁止提权)')
  })

  it('allows editing instructions and selecting agents', async () => {
    const wrapper = mount(ScenesPage)
    await new Promise((r) => setTimeout(r, 50))

    const textareas = wrapper.findAll('textarea')
    expect(textareas.length).toBeGreaterThan(0)
    await textareas[0].setValue('新指令：必须完成全量边界测试')
    expect((textareas[0].element as HTMLTextAreaElement).value).toBe('新指令：必须完成全量边界测试')
  })

  it('allows the optional development planner and uses runtime effort levels', async () => {
    const scenes = await mockLocalChatGateway.listLocalScenes()
    const develop = scenes.find(s => s.id === 'develop')!
    develop.roles = [
      { roleId: 'planner', agentInstanceId: 'agent-codex', instructions: 'plan', enabled: false, modelId: 'runtime-model' },
      { roleId: 'developer', agentInstanceId: 'agent-codex', instructions: 'develop', enabled: true, modelId: 'runtime-model' },
      { roleId: 'reviewer', agentInstanceId: 'agent-codex', instructions: 'review', enabled: false },
    ]
    vi.spyOn(mockLocalChatGateway, 'listLocalScenes').mockResolvedValue([develop])
    vi.spyOn(mockLocalChatGateway, 'getAgentModels').mockResolvedValue({ agentInstanceId: 'agent-codex', verified: true,
      models: [{ id: 'runtime-model', name: 'Runtime model', efforts: ['low', 'xhigh', 'max'], isDefault: true }] })
    const wrapper = mount(ScenesPage)
    await new Promise(resolve => setTimeout(resolve, 50))
    expect(wrapper.findAll('[role="switch"]')).toHaveLength(2)
    await wrapper.findAll('[role="switch"]')[0].trigger('click')
    expect(wrapper.findAll('[role="switch"]')[0].attributes('aria-checked')).toBe('true')
    const options = wrapper.findAllComponents(HqSelect).flatMap(w => w.props('options'))
    expect(options.some(option => option.value === 'xhigh')).toBe(true)
    expect(options.some(option => option.value === 'max')).toBe(true)
  })
})
