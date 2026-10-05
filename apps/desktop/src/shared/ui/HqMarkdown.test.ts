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

  it('parses and renders markdown tables with columns and rows', () => {
    const content = `
| 模块 | 说明 | 状态 |
| :--- | :---: | ---: |
| ChatComposer | 悬浮卡片 | 完成 |
| ChatMessageItem | 气泡 | 完成 |
`
    const wrapper = mount(HqMarkdown, { props: { content } })
    const table = wrapper.find('table')
    expect(table.exists()).toBe(true)
    expect(wrapper.findAll('th')).toHaveLength(3)
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
    expect(wrapper.text()).toContain('ChatComposer')
    expect(wrapper.text()).toContain('悬浮卡片')
  })

  it('parses ordered and unordered lists properly', () => {
    const content = `
1. 第一项配置
2. 第二项配置

- 无序条目 A
- 无序条目 B
`
    const wrapper = mount(HqMarkdown, { props: { content } })
    const ol = wrapper.find('ol')
    expect(ol.exists()).toBe(true)
    expect(ol.findAll('li')).toHaveLength(2)
    expect(ol.text()).toContain('第一项配置')

    const ul = wrapper.find('ul')
    expect(ul.exists()).toBe(true)
    expect(ul.findAll('li')).toHaveLength(2)
    expect(ul.text()).toContain('无序条目 A')
  })

  it('formats file paths as highlight chips', () => {
    const content = '定位在 ua_settings/src/main/java/com/ua/settings/module/rtk/RtkSettingFragment.kt:12 位置。'
    const wrapper = mount(HqMarkdown, { props: { content } })
    const code = wrapper.find('code')
    expect(code.exists()).toBe(true)
    expect(code.text()).toContain('RtkSettingFragment.kt:12')
  })

  it('renders section titles with accent indicators', () => {
    const content = '核心文件与职责（5个）：\n1. 文件一'
    const wrapper = mount(HqMarkdown, { props: { content } })
    expect(wrapper.text()).toContain('核心文件与职责（5个）：')
    expect(wrapper.find('ol').exists()).toBe(true)
  })

  it('parses standard, indented, CRLF and Chinese headings properly into heading tags', () => {
    const content = '## 需求分析\r\n段落说明\r\n  ### 次级重点\n##核心结论\n#tag'
    const wrapper = mount(HqMarkdown, { props: { content } })
    const h2s = wrapper.findAll('h2')
    expect(h2s).toHaveLength(2)
    expect(h2s[0].text()).toBe('需求分析')
    expect(h2s[1].text()).toBe('核心结论')

    const h3 = wrapper.find('h3')
    expect(h3.exists()).toBe(true)
    expect(h3.text()).toBe('次级重点')

    // #tag remains text inside paragraph and not a heading
    expect(wrapper.find('h1').exists()).toBe(false)
    expect(wrapper.text()).toContain('#tag')
  })
})

