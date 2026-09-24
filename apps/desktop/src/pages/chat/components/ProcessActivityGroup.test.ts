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
    expect(wrapper.find('.spin-indicator').exists()).toBe(true)
  })

  it('shows live generic progress when activities are tools/steps without files or commands', () => {
    const genericActivities: ActivityItem[] = [
      {
        id: 'step_1',
        type: 'progress',
        verb: 'Step',
        target: 'Analyzing architecture requirements',
        status: 'done',
        timestamp: '2026-09-24T12:00:00Z',
      },
      {
        id: 'step_2',
        type: 'tool',
        verb: 'Tool',
        target: 'git_status: checking worktree',
        status: 'done',
        timestamp: '2026-09-24T12:00:01Z',
      },
    ]

    const liveWrapper = mount(ProcessActivityGroup, {
      props: {
        activities: genericActivities,
        isLive: true,
      },
    })
    expect(liveWrapper.text()).toContain('正在执行 (2 个步骤)...')
    expect(liveWrapper.find('.spin-indicator').exists()).toBe(true)

    const completedWrapper = mount(ProcessActivityGroup, {
      props: {
        activities: genericActivities,
        isLive: false,
      },
    })
    expect(completedWrapper.text()).toContain('执行了 2 个步骤')
    expect(completedWrapper.find('.spin-indicator').exists()).toBe(false)
  })

  it('renders smart path layout with fileName and dirPath, and expands full target on click', async () => {
    const pathActivity: ActivityItem[] = [
      {
        id: 'act_file_1',
        type: 'file',
        verb: 'Read',
        target: 'E:\\WorkSpace\\ua_android\\ua_home\\src\\main\\java\\com\\example\\RtkService.java',
        fileName: 'RtkService.java',
        dirPath: 'E:/WorkSpace/ua_android/ua_home/src/main/java/com/example',
        rawArgs: '{"file_path":"E:\\\\WorkSpace\\\\ua_android\\\\ua_home\\\\src\\\\main\\\\java\\\\com\\\\example\\\\RtkService.java"}',
        detail: 'package com.example;\npublic class RtkService {}',
        status: 'done',
        durationMs: 45,
        timestamp: '2026-09-24T12:00:00Z',
      },
    ]

    const wrapper = mount(ProcessActivityGroup, {
      props: {
        activities: pathActivity,
        isLive: false,
        initiallyExpanded: true,
      },
    })

    // Filename should be prominent
    expect(wrapper.text()).toContain('RtkService.java')
    expect(wrapper.text()).toContain('E:/WorkSpace/ua_android/ua_home')

    // Click item row to expand full details
    const itemRow = wrapper.find('.group\\/item')
    await itemRow.trigger('click')

    // Expanded detail card should show full path with break-all and copy button
    expect(wrapper.text()).toContain('完整目标 / 路径:')
    expect(wrapper.text()).toContain('E:\\WorkSpace\\ua_android\\ua_home\\src\\main\\java\\com\\example\\RtkService.java')
    expect(wrapper.text()).toContain('复制目标')
    expect(wrapper.text()).toContain('调用参数:')
    expect(wrapper.text()).toContain('执行输出:')
    expect(wrapper.text()).toContain('public class RtkService')
  })
})


