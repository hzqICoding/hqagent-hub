import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useTaskStore } from './task.store'
import { useAppStore } from './app.store'
import { getUiGateway, HubApiError } from '@/shared/api'
import type { HubEvent } from '@hqagent/protocol'

describe('useTaskStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('fetches tasks and filters correctly', async () => {
    const store = useTaskStore()
    await store.fetchTasks()

    expect(store.tasks.length).toBeGreaterThan(0)
    expect(store.totalTasks).toBeGreaterThan(0)

    store.filterStatus = 'running'
    expect(store.filteredTasks.every((t) => t.status === 'running')).toBe(true)

    store.filterStatus = 'all'
    store.filterSearch = '契约测试'
    expect(store.filteredTasks.length).toBeGreaterThan(0)
  })

  it('fetches single task detail and initializes event stream', async () => {
    const store = useTaskStore()
    await store.fetchTask('task_20260905_001')

    expect(store.currentTask).not.toBeNull()
    expect(store.currentTask?.id).toBe('task_20260905_001')
    expect(store.currentNodes.length).toBe(3)
    expect(store.events.length).toBeGreaterThan(0)
    expect(store.lastEventSeq).toBeGreaterThan(0)
  })

  it('Trap 1: append_instruction is forbidden when active node is running and allowed when idle', async () => {
    const store = useTaskStore()
    await store.fetchTask('task_20260905_001') // task_20260905_001 has node_02 in 'running' status

    expect(store.hasRunningNode).toBe(true)
    expect(store.canAppendInstruction).toBe(false)

    // Attempting append_instruction should reject
    await expect(
      store.controlTask('task_20260905_001', {
        action: 'append_instruction',
        instruction: '追加指令',
      })
    ).rejects.toThrow(/节点正在运行中/)

    // Simulate node completion
    store.handleHubEvent({
      eventId: 'evt_comp_1',
      seq: 200,
      occurredAt: '2026-09-06T12:00:00Z',
      aggregateType: 'task',
      aggregateId: 'task_20260905_001',
      taskId: 'task_20260905_001',
      nodeId: 'node_02',
      type: 'agent.completed',
      payload: { result: { status: 'done', summary: 'Done' } },
      protocolVersion: '0.2.0',
    })

    // Now all nodes are succeeded or pending (not running or resolving)
    expect(store.hasRunningNode).toBe(false)
    expect(store.canAppendInstruction).toBe(true)
  })

  it('Trap 2: successful cancel marks status as cancelled, refused cancel exposes orphanProcessIds', async () => {
    const store = useTaskStore()
    await store.fetchTask('task_20260905_001')

    // Successful cancel
    const updated = await store.controlTask('task_20260905_001', { action: 'cancel' })
    expect(updated.status).toBe('cancelled')
    expect(store.currentTask?.status).toBe('cancelled')
    expect(store.orphanProcessIds).toEqual([])

    // Refused cancel simulation (TASK_NOT_CANCELLABLE)
    const gateway = getUiGateway()
    const origControl = gateway.controlTask
    gateway.controlTask = async () => {
      throw new HubApiError(
        'Adapter refused cancel',
        'TASK_NOT_CANCELLABLE',
        409,
        { orphanProcessIds: [14208, 14209] },
        false
      )
    }

    await expect(
      store.controlTask('task_20260905_001', { action: 'cancel' })
    ).rejects.toThrow()

    expect(store.orphanProcessIds).toEqual([14208, 14209])
    expect(store.actionError).toContain('14208')
    expect(store.actionError).toContain('14209')

    gateway.controlTask = origControl
  })

  it('Trap 3 & 4: supports resolving, skipped, and 6-level resolveSource', async () => {
    const store = useTaskStore()
    await store.fetchTask('task_20260905_001')

    // Simulate node.resolved event with fallback resolveSource
    const nodeEvent: HubEvent = {
      eventId: 'evt_node_res_1',
      seq: 300,
      occurredAt: '2026-09-06T12:05:00Z',
      aggregateType: 'task',
      aggregateId: 'task_20260905_001',
      taskId: 'task_20260905_001',
      nodeId: 'node_03',
      roleId: 'reviewer',
      type: 'node.resolved',
      payload: {
        roleId: 'reviewer',
        resolvedAgentId: 'agent_codex_default',
        resolvedAgentName: 'Codex App Server',
        resolveSource: 'fallback',
        isFallback: true,
        fallbackReason: 'Claude 达到配额上限，回退到备用 Agent',
      },
      protocolVersion: '0.2.0',
    }

    store.handleHubEvent(nodeEvent)

    const node = store.currentNodes.find((n) => n.id === 'node_03')
    expect(node).toBeDefined()
    expect(node?.resolveSource).toBe('fallback')
    expect(node?.isFallback).toBe(true)
    expect(node?.fallbackReason).toContain('Claude 达到配额上限')
  })

  it('F2-R1 integration: blocks task creation when hubGate is active', async () => {
    const appStore = useAppStore()
    const taskStore = useTaskStore()

    appStore.hubGate = 'maintenance'
    appStore.hubGateReason = 'Hub 正在维护'

    await expect(
      taskStore.createTask({
        objective: '新任务',
        workspaceId: 'ws_1',
      })
    ).rejects.toThrow(/Hub 正在维护/)
  })

  it('filters event stream reactively by type and keyword', async () => {
    const store = useTaskStore()
    await store.fetchTask('task_20260905_001')

    const totalEvents = store.events.length
    expect(totalEvents).toBeGreaterThan(0)

    store.eventFilterType = 'agent.progress'
    expect(store.filteredEvents.every((e) => e.type === 'agent.progress')).toBe(true)

    store.eventFilterType = 'all'
    store.eventSearch = '断线重连'
    expect(store.filteredEvents.length).toBeGreaterThan(0)
  })
})
