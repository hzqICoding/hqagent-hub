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

  it('configures original planner acceptance and saves inherited reviewer identity', async () => {
    const develop = (await mockLocalChatGateway.listLocalScenes()).find(s => s.id === 'develop')!
    const planner = develop.roles.find(role => role.roleId === 'planner')!
    const reviewer = develop.roles.find(role => role.roleId === 'reviewer')!
    planner.agentInstanceId = 'codex-cli-local'
    planner.modelId = 'o3-mini'
    planner.reasoningEffort = 'high'
    reviewer.agentInstanceId = 'claude-code-local'
    reviewer.modelId = 'claude-3-5-sonnet'
    reviewer.reasoningEffort = 'low'
    develop.reviewMode = 'original_planner'

    vi.spyOn(mockLocalChatGateway, 'listLocalScenes').mockResolvedValue([develop])
    const saveSpy = vi.spyOn(mockLocalChatGateway, 'saveLocalScene')
    const wrapper = mount(ScenesPage)
    await new Promise(resolve => setTimeout(resolve, 50))

    expect(wrapper.text()).toContain('原规划者验收')
    expect(wrapper.text()).toContain('修改后请使用「新一轮上下文」')
    expect(wrapper.text()).toContain('执行身份、模型与原生会话继承本轮 Planner')

    const reviewerCard = wrapper.find('[data-role-id="reviewer"]')
    expect(reviewerCard.exists()).toBe(true)
    expect(reviewerCard.findAll('button[disabled], input[disabled]').length).toBeGreaterThan(0)

    const saveButton = wrapper.findAll('button').find(button => button.text().includes('保存场景配置'))
    await saveButton!.trigger('click')
    await new Promise(resolve => setTimeout(resolve, 20))

    const input = saveSpy.mock.calls[0][1]
    expect(input.reviewMode).toBe('original_planner')
    const savedPlanner = input.roles.find(role => role.roleId === 'planner')!
    const savedReviewer = input.roles.find(role => role.roleId === 'reviewer')!
    expect(savedReviewer.agentInstanceId).toBe(savedPlanner.agentInstanceId)
    expect(savedReviewer.modelId).toBe(savedPlanner.modelId)
    expect(savedReviewer.reasoningEffort).toBe(savedPlanner.reasoningEffort)
  })

  it('treats a missing review mode as the legacy independent reviewer mode', async () => {
    const develop = (await mockLocalChatGateway.listLocalScenes()).find(s => s.id === 'develop')!
    delete develop.reviewMode
    vi.spyOn(mockLocalChatGateway, 'listLocalScenes').mockResolvedValue([develop])

    const wrapper = mount(ScenesPage)
    await new Promise(resolve => setTimeout(resolve, 50))

    const independentRadio = wrapper.findAll('[role="radio"]').find(radio =>
      radio.element.parentElement?.textContent?.includes('独立 Reviewer')
    )
    expect(independentRadio?.attributes('aria-checked')).toBe('true')
    expect(wrapper.text()).toContain('代码审查 (Reviewer)')
  })
})
