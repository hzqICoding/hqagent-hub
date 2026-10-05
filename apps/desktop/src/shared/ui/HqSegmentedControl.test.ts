import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import HqSegmentedControl from './HqSegmentedControl.vue'

describe('HqSegmentedControl', () => {
  const options = [
    { label: '对话', value: 'chat' },
    { label: '场景', value: 'scenes' },
    { label: '禁用项', value: 'disabled', disabled: true },
  ]

  it('renders all options and reflects active value', () => {
    const wrapper = mount(HqSegmentedControl, {
      props: {
        modelValue: 'chat',
        options,
      },
    })

    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(3)
    expect(buttons[0].attributes('aria-checked')).toBe('true')
    expect(buttons[1].attributes('aria-checked')).toBe('false')
  })

  it('emits update:modelValue when an enabled option is clicked', async () => {
    const wrapper = mount(HqSegmentedControl, {
      props: {
        modelValue: 'chat',
        options,
      },
    })

    const buttons = wrapper.findAll('button')
    await buttons[1].trigger('click')

    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['scenes'])
    expect(wrapper.emitted('change')?.[0]).toEqual(['scenes'])
  })

  it('does not emit events when a disabled option is clicked', async () => {
    const wrapper = mount(HqSegmentedControl, {
      props: {
        modelValue: 'chat',
        options,
      },
    })

    const buttons = wrapper.findAll('button')
    await buttons[2].trigger('click')

    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })
})
