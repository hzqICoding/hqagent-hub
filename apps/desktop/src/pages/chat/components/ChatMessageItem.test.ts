import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ChatMessageItem from './ChatMessageItem.vue'
import type { LocalMessageView } from '@hqagent/protocol'

describe('ChatMessageItem component', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    // Mock navigator.clipboard
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    })
  })

  const sampleAssistantMsg: LocalMessageView = {
    id: 'msg_asst_1',
    conversationId: 'conv_1',
    role: 'assistant',
    text: '### RTK 方案分析\n- 步骤 1\n- 步骤 2',
    sequence: 2,
    createdAt: '2026-09-24T12:00:00Z',
  }

  const sampleUserMsg: LocalMessageView = {
    id: 'msg_user_1',
    conversationId: 'conv_1',
    role: 'user',
    text: '请分析 RTK 方案',
    sequence: 1,
    createdAt: '2026-09-24T11:59:00Z',
  }

  it('renders assistant message with quick copy buttons', () => {
    const wrapper = mount(ChatMessageItem, {
      props: { message: sampleAssistantMsg },
    })

    expect(wrapper.text()).toContain('HQAgent 团队')
    expect(wrapper.text()).toContain('RTK 方案分析')

    // Find copy buttons (floating on card, bottom action bar, and header)
    const copyBtns = wrapper.findAll('button').filter(b => b.text().includes('复制'))
    expect(copyBtns.length).toBeGreaterThanOrEqual(2)
  })

  it('copies message text to clipboard when copy button clicked', async () => {
    const wrapper = mount(ChatMessageItem, {
      props: { message: sampleAssistantMsg },
    })

    const copyBtn = wrapper.findAll('button').find(b => b.text().includes('复制全文'))
    expect(copyBtn).toBeDefined()

    await copyBtn?.trigger('click')
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(sampleAssistantMsg.text)
    expect(wrapper.text()).toContain('已复制')
  })

  it('renders user message with copy button', async () => {
    const wrapper = mount(ChatMessageItem, {
      props: { message: sampleUserMsg },
    })

    expect(wrapper.text()).toContain('你')
    expect(wrapper.text()).toContain('请分析 RTK 方案')

    const userCopyBtn = wrapper.find('button[title="复制输入"]')
    expect(userCopyBtn.exists()).toBe(true)

    await userCopyBtn.trigger('click')
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(sampleUserMsg.text)
  })

  it('renders system execution record collapsed by default and expands on click', async () => {
    const sampleSystemMsg: LocalMessageView = {
      id: 'msg_sys_1',
      conversationId: 'conv_1',
      role: 'system',
      text: 'Bash: 历史返回记录\nexit 0',
      sequence: 3,
      createdAt: '2026-09-24T12:01:00Z',
    }

    const wrapper = mount(ChatMessageItem, {
      props: { message: sampleSystemMsg },
    })

    expect(wrapper.text()).toContain('执行记录')
    expect(wrapper.text()).toContain('#3')

    // Terminal body is collapsed initially
    const disclosureBtn = wrapper.find('button')
    expect(disclosureBtn.exists()).toBe(true)

    // Click to expand
    await disclosureBtn.trigger('click')
    expect(wrapper.text()).toContain('Bash: 历史返回记录')
  })
})
