import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ChatSidebar from './ChatSidebar.vue'
import { useChatStore } from '@/stores/chat.store'
import { HqSelect } from '@/shared/ui'

describe('ChatSidebar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('uses the active task workspace when opening the shared new task dialog', async () => {
    const store = useChatStore()
    store.workspaces = [
      {
        id: 'workspace-first',
        name: 'First',
        path: 'E:/first',
        vcs: 'git',
        lastOpenedAt: '2026-09-25T00:00:00Z',
      },
      {
        id: 'workspace-current',
        name: 'Current',
        path: 'E:/current',
        vcs: 'git',
        lastOpenedAt: '2026-09-25T00:00:00Z',
      },
    ]
    store.conversations = [{
      id: 'conversation-current',
      title: 'Current task',
      workspaceId: 'workspace-current',
      sceneId: 'develop',
      createdAt: '2026-09-25T00:00:00Z',
      updatedAt: '2026-09-25T00:00:00Z',
    }]
    store.activeConversationId = 'conversation-current'
    const wrapper = mount(ChatSidebar)

    await wrapper.findAll('button').find(button => button.text().includes('新建任务'))!.trigger('click')
    const workspaceSelect = wrapper.findAllComponents(HqSelect)[0]
    expect(workspaceSelect.props('modelValue')).toBe('workspace-current')
    expect(document.body.textContent).toContain('创建独立任务对话')
  })
})
