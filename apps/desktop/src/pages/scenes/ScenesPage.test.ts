import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ScenesPage from './ScenesPage.vue'
import { mockLocalChatGateway, setLocalChatGatewayMode } from '@/shared/api'
import { useScenesStore } from '@/stores/scenes.store'
import { HqSelect } from '@/shared/ui'

describe('ScenesPage', () => {
  const wrappers: VueWrapper[] = []

  beforeEach(() => {
    setActivePinia(createPinia())
    setLocalChatGatewayMode('mock')
    mockLocalChatGateway.reset()
  })

  afterEach(() => {
    for (const wrapper of wrappers.splice(0)) wrapper.unmount()
    document.body.replaceChildren()
    vi.restoreAllMocks()
  })

  async function mountReady(): Promise<VueWrapper> {
    const wrapper = mount(ScenesPage)
    wrappers.push(wrapper)
    const store = useScenesStore()
    await vi.waitFor(() => {
      expect(store.isLoading).toBe(false)
      expect(store.scenes.length).toBeGreaterThan(0)
      expect(store.currentScene).toBeTruthy()
    })
    await flushPromises()
    return wrapper
  }

  it('renders builtin scenes and the ordered role configuration studio', async () => {
    const wrapper = await mountReady()
    expect(wrapper.text()).toContain('场景清单')
    expect(wrapper.text()).toContain('代码分析')
    expect(wrapper.text()).toContain('需求规划')
    expect(wrapper.text()).toContain('开发修复')
    expect(wrapper.text()).toContain('内置场景')
    expect(wrapper.text()).toContain('保存场景配置')
    expect(wrapper.text()).toContain('只读权限')
  })

  it('allows editing role instructions without exposing a permission switch', async () => {
    const wrapper = await mountReady()
    const textareas = wrapper.findAll('textarea')
    expect(textareas.length).toBeGreaterThan(0)
    await textareas[0].setValue('新指令：必须完成全量边界测试')
    expect((textareas[0].element as HTMLTextAreaElement).value).toBe('新指令：必须完成全量边界测试')
    expect(wrapper.text()).not.toContain('文件系统权限')
  })

  it('uses runtime model effort levels for optional builtin roles', async () => {
    const scenes = await mockLocalChatGateway.listLocalScenes()
    const develop = scenes.find(scene => scene.id === 'develop')!
    develop.reviewMode = 'independent'
    develop.roles = [
      { roleId: 'planner', agentInstanceId: 'agent-codex', instructions: 'plan', enabled: false, modelId: 'runtime-model' },
      { roleId: 'developer', agentInstanceId: 'agent-codex', instructions: 'develop', enabled: true, modelId: 'runtime-model' },
      { roleId: 'reviewer', agentInstanceId: 'agent-codex', instructions: 'review', enabled: false },
    ]
    vi.spyOn(mockLocalChatGateway, 'listLocalScenes').mockResolvedValue([develop])
    vi.spyOn(mockLocalChatGateway, 'getAgentModels').mockResolvedValue({
      agentInstanceId: 'agent-codex',
      verified: true,
      models: [{ id: 'runtime-model', name: 'Runtime model', efforts: ['low', 'xhigh', 'max'], isDefault: true }],
    })
    const wrapper = await mountReady()
    expect(wrapper.findAll('[role="switch"]')).toHaveLength(2)
    await wrapper.findAll('[role="switch"]')[0].trigger('click')
    const options = wrapper.findAllComponents(HqSelect).flatMap(component => component.props('options'))
    expect(options.some(option => option.value === 'xhigh')).toBe(true)
    expect(options.some(option => option.value === 'max')).toBe(true)
  })

  it('keeps builtin original-planner inheritance and validation', async () => {
    const develop = (await mockLocalChatGateway.listLocalScenes()).find(scene => scene.id === 'develop')!
    develop.reviewMode = 'independent'
    const planner = develop.roles.find(role => role.roleId === 'planner')!
    const reviewer = develop.roles.find(role => role.roleId === 'reviewer')!
    planner.enabled = false
    planner.agentInstanceId = ''
    reviewer.enabled = false
    vi.spyOn(mockLocalChatGateway, 'listLocalScenes').mockResolvedValue([develop])
    const wrapper = await mountReady()

    const originalPlannerRadio = wrapper.findAll('[role="radio"]').find(radio =>
      radio.element.parentElement?.textContent?.includes('原规划者验收')
    )!
    await originalPlannerRadio.trigger('click')

    expect(wrapper.find('[data-role-id="planner"] [role="switch"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-role-id="reviewer"] [role="switch"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Planner) 尚未配置执行 Agent')
    expect(wrapper.findAll('button').find(button => button.text().includes('保存场景配置'))?.attributes('disabled')).toBeDefined()
  })

  it('saves inherited reviewer runtime identity for original-planner review', async () => {
    const develop = (await mockLocalChatGateway.listLocalScenes()).find(scene => scene.id === 'develop')!
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
    const wrapper = await mountReady()

    expect(wrapper.text()).toContain('继承 Planner')
    await wrapper.findAll('button').find(button => button.text().includes('保存场景配置'))!.trigger('click')
    await flushPromises()

    const input = saveSpy.mock.calls[0][1]
    const savedPlanner = input.roles.find(role => role.roleId === 'planner')!
    const savedReviewer = input.roles.find(role => role.roleId === 'reviewer')!
    expect(savedReviewer.agentInstanceId).toBe(savedPlanner.agentInstanceId)
    expect(savedReviewer.modelId).toBe(savedPlanner.modelId)
    expect(savedReviewer.reasoningEffort).toBe(savedPlanner.reasoningEffort)
  })

  it('creates a blank custom scene with one analyst stage', async () => {
    const createSpy = vi.spyOn(mockLocalChatGateway, 'createLocalScene')
    const wrapper = await mountReady()
    await wrapper.findAll('button').find(button => button.text().trim() === '新建')!.trigger('click')
    expect(document.body.textContent).toContain('复制当前场景')

    const blankRadio = Array.from(document.body.querySelectorAll<HTMLElement>('[role="radio"]')).find(element =>
      element.parentElement?.textContent?.includes('空白场景')
    )!
    blankRadio.click()
    const nameInput = document.body.querySelector<HTMLInputElement>('input[placeholder="例如：RTK 模块开发与验收"]')!
    nameInput.value = 'RTK 分析场景'
    nameInput.dispatchEvent(new Event('input', { bubbles: true }))
    await flushPromises()
    const createButton = Array.from(document.body.querySelectorAll<HTMLButtonElement>('button')).find(button =>
      button.textContent?.includes('创建场景')
    )!
    createButton.click()
    await flushPromises()

    expect(createSpy).toHaveBeenCalledOnce()
    expect(createSpy.mock.calls[0][0]).toMatchObject({
      name: 'RTK 分析场景',
      reviewMode: 'independent',
      roles: [{ roleId: 'analyst', enabled: true }],
    })
    expect(wrapper.text()).toContain('自定义场景')
  })

  it('adds a role-template copy to a custom scene and can reorder stages', async () => {
    const custom = await mockLocalChatGateway.createLocalScene({
      name: '自定义流水线',
      roles: [{ roleId: 'analyst', roleName: '现状分析', agentInstanceId: 'claude-code-local', instructions: '分析', enabled: true }],
    }, 'seed-custom-scene')
    const wrapper = await mountReady()
    await wrapper.findAll('button').find(button => button.text().includes(custom.name))!.trigger('click')
    await wrapper.vm.$nextTick()

    const stageSelect = wrapper.findAllComponents(HqSelect).find(component =>
      component.props('placeholder') === '选择基础角色或角色模板'
    )!
    const template = useScenesStore().roleTemplates.find(item => item.name === '安全边界审查')!
    stageSelect.vm.$emit('update:modelValue', `template:${template.id}`)
    await wrapper.vm.$nextTick()
    await wrapper.findAll('button').find(button => button.text().includes('添加阶段'))!.trigger('click')

    const cardsBefore = wrapper.findAll('[data-role-id]')
    expect(cardsBefore.map(card => card.attributes('data-role-id'))).toEqual(['analyst', 'reviewer'])
    expect(wrapper.text()).toContain('当前职责是独立副本')
    await cardsBefore[1].find('button[title="上移阶段"]').trigger('click')
    expect(wrapper.findAll('[data-role-id]').map(card => card.attributes('data-role-id'))).toEqual(['reviewer', 'analyst'])
  })

  it('creates and edits role templates without offering deletion', async () => {
    const createSpy = vi.spyOn(mockLocalChatGateway, 'createLocalRoleTemplate')
    const wrapper = await mountReady()
    await wrapper.findAll('button').find(button => button.text().includes('角色模板'))!.trigger('click')
    const newTemplateButton = Array.from(document.body.querySelectorAll<HTMLButtonElement>('button')).find(button =>
      button.textContent?.includes('新建模板')
    )!
    newTemplateButton.click()
    const nameInput = Array.from(document.body.querySelectorAll<HTMLInputElement>('input')).find(input =>
      input.placeholder.includes('RTK 安全审查员')
    )!
    nameInput.value = 'RTK 分析员'
    nameInput.dispatchEvent(new Event('input', { bubbles: true }))
    await flushPromises()
    const saveButton = Array.from(document.body.querySelectorAll<HTMLButtonElement>('button')).find(button =>
      button.textContent?.includes('创建模板')
    )!
    saveButton.click()
    await flushPromises()

    expect(createSpy).toHaveBeenCalledWith(expect.objectContaining({
      name: 'RTK 分析员', baseRoleId: 'analyst',
    }), expect.any(String))
    expect(document.body.textContent).not.toContain('删除模板')
  })

  it('treats missing additive fields as legacy builtin defaults', async () => {
    const analyze = (await mockLocalChatGateway.listLocalScenes()).find(scene => scene.id === 'analyze')!
    delete analyze.isBuiltin
    delete analyze.roles[0].roleName
    delete analyze.roles[0].roleTemplateId
    delete analyze.roles[0].roleTemplateVersion
    vi.spyOn(mockLocalChatGateway, 'listLocalScenes').mockResolvedValue([analyze])
    const wrapper = await mountReady()

    expect(wrapper.text()).toContain('内置场景')
    expect(wrapper.text()).toContain('代码分析 (Analyst)')
    expect(wrapper.text()).not.toContain('当前职责是独立副本')
  })
})
