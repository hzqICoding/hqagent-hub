import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import HqMarkdown from './HqMarkdown.vue'

describe('HqMarkdown untrusted content', () => {
  it('rejects executable URLs and quote-based attribute injection', () => {
    const wrapper = mount(HqMarkdown, { props: { content: '[bad](javascript:alert(1))\n\n[x](https://example.org/" onmouseover="alert(1))\n\n[good](https://example.org/path)' } })
    expect(wrapper.findAll('a').every(a => !a.attributes('href')?.startsWith('javascript:'))).toBe(true)
    expect(wrapper.find('[onmouseover]').exists()).toBe(false)
    expect(wrapper.find('[onclick]').exists()).toBe(false)
    expect(wrapper.find('a[href="https://example.org/path"]').exists()).toBe(true)
  })

  it('consumes unsupported heading and quote syntax without looping', () => {
    const wrapper = mount(HqMarkdown, { props: { content: '#tag\n#### fourth heading\n>no-space' } })
    expect(wrapper.text()).toContain('#tag')
    expect(wrapper.text()).toContain('fourth heading')
    expect(wrapper.text()).toContain('>no-space')
  })
})
