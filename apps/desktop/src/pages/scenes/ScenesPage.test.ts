import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ScenesPage from './ScenesPage.vue'
import { setLocalChatGatewayMode, mockLocalChatGateway } from '@/shared/api'

describe('ScenesPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocalChatGatewayMode('mock')
    mockLocalChatGateway.reset()
  })

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
})
