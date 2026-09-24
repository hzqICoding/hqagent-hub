import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import type { LocalRunView } from '@hqagent/protocol'
import RunSnapshotDrawer from './RunSnapshotDrawer.vue'
import { useChatStore } from '@/stores/chat.store'

describe('RunSnapshotDrawer', () => {
  it('distinguishes a negative review verdict from an acceptance execution error', () => {
    setActivePinia(createPinia())
    const store = useChatStore()
    store.activeRun = {
      id: 'run_review_result',
      conversationId: 'conv_review_result',
      messageId: 'msg_review_result',
      taskId: 'task_review_result',
      status: 'failed',
      createdAt: '2026-09-25T00:00:00Z',
      updatedAt: '2026-09-25T00:10:00Z',
      sceneSnapshot: {
        id: 'develop',
        name: '开发修复',
        description: '验证审核结论展示',
        readOnly: false,
        version: 4,
        reviewMode: 'original_planner',
        updatedAt: '2026-09-25T00:00:00Z',
        roles: [],
      },
      task: {
        id: 'task_review_result',
        objective: '验证验收结论',
        workspaceId: 'ws_review',
        workspaceName: 'Review Workspace',
        profileId: 'profile_review',
        profileName: '开发修复',
        status: 'failed',
        source: 'desktop',
        createdAt: '2026-09-25T00:00:00Z',
        updatedAt: '2026-09-25T00:10:00Z',
        nodes: [
          {
            id: 'node_changes_requested',
            taskId: 'task_review_result',
            roleId: 'planner',
            resolvedAgentId: 'agent_planner',
            resolvedAgentName: 'Planner Agent',
            resolveSource: 'manual',
            status: 'failed',
            phase: 'acceptance',
            reviewVerdict: 'changes_requested',
            reviewEvidenceId: 'evidence_changes_requested',
          },
          {
            id: 'node_transport_error',
            taskId: 'task_review_result',
            roleId: 'planner',
            resolvedAgentId: 'agent_planner',
            resolvedAgentName: 'Planner Agent',
            resolveSource: 'manual',
            status: 'failed',
            phase: 'acceptance',
            error: '原生会话恢复失败',
          },
        ],
        artifacts: [],
        events: [],
      },
    } satisfies LocalRunView

    const wrapper = mount(RunSnapshotDrawer)

    expect(wrapper.text()).toContain('验收不通过：需要修改')
    expect(wrapper.text()).toContain('验收执行出错，未产生有效审核结论：原生会话恢复失败')
    expect(wrapper.text()).not.toContain('验收通过')
  })
})
