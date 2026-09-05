import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import HqButton from './HqButton.vue'

describe('HqButton', () => {
  it('renders default slot text correctly', () => {
    const wrapper = mount(HqButton, {
      slots: { default: '确认操作' },
    })
    expect(wrapper.text()).toContain('确认操作')
  })

  it('emits click event when clicked', async () => {
    const wrapper = mount(HqButton, {
      slots: { default: '点击' },
    })
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toHaveLength(1)
  })

  it('does not emit click when disabled or loading', async () => {
    const wrapperDisabled = mount(HqButton, {
      props: { disabled: true },
      slots: { default: '禁用' },
    })
    await wrapperDisabled.trigger('click')
    expect(wrapperDisabled.emitted('click')).toBeUndefined()

    const wrapperLoading = mount(HqButton, {
      props: { loading: true },
      slots: { default: '加载中' },
    })
    await wrapperLoading.trigger('click')
    expect(wrapperLoading.emitted('click')).toBeUndefined()
  })

  it('applies variant classes accurately', () => {
    const wrapper = mount(HqButton, {
      props: { variant: 'danger' },
    })
    expect(wrapper.classes()).toContain('bg-status-danger')
  })
})
