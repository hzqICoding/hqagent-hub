import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import ProcessActivityGroup from './ProcessActivityGroup.vue'
import type { ActivityItem } from '@/stores/chat.store'

describe('ProcessActivityGroup component', () => {
  const sampleActivities: ActivityItem[] = [
    {
      id: 'act_1',
      type: 'file',
      verb: 'Analyzed',
      target: 'apps/desktop/src/shared/ui/HqMarkdown.vue',
      detail: 'Parsed 190 lines',
      status: 'done',
      durationMs: 120,
      timestamp: '2026-09-24T12:00:00Z',
    },
    {
      id: 'act_2',
      type: 'command',
      verb: 'Ran',
      target: 'pnpm test',
      detail: '31 passed',
      status: 'done',
      durationMs: 1250,
      timestamp: '2026-09-24T12:00:01Z',
    },
  ]

  it('renders summary title with files and commands count', () => {
    const wrapper = mount(ProcessActivityGroup, {
      props: {
        activities: sampleActivities,
        isLive: false,
        initiallyExpanded: false,
      },
    })
    expect(wrapper.text()).toContain('已探索 1 个文件，已运行 1 条命令')
    expect(wrapper.text()).toContain('2 步')
  })

  it('expands timeline items on click', async () => {
    const wrapper = mount(ProcessActivityGroup, {
      props: {
        activities: sampleActivities,
        isLive: false,
        initiallyExpanded: false,
      },
    })
    // Initially collapsed
    expect(wrapper.text()).not.toContain('HqMarkdown.vue')

    // Click header button to expand
    await wrapper.find('button').trigger('click')
    expect(wrapper.text()).toContain('HqMarkdown.vue')
    expect(wrapper.text()).toContain('pnpm test')
    expect(wrapper.text()).toContain('Analyzed')
    expect(wrapper.text()).toContain('Ran')
  })

  it('shows live executing status when isLive is true', () => {
    const wrapper = mount(ProcessActivityGroup, {
      props: {
        activities: sampleActivities,
        isLive: true,
        initiallyExpanded: true,
      },
    })
    expect(wrapper.text()).toContain('正在 探索 1 个文件，运行 1 条命令...')
    expect(wrapper.find('.animate-spin').exists()).toBe(true)
  })
})
