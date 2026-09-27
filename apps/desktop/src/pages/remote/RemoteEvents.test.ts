import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import RemoteChatPage from './RemoteChatPage.vue'
import remoteChatStoreRaw from '@/stores/remote-chat.store.ts?raw'
import { useRemoteChatStore } from '@/stores/remote-chat.store'
import { mockRemoteGateway } from '@/shared/api/mock-remote-gateway'
import { setRemoteGatewayForTesting } from '@/shared/api/remote-provider'
import type {
  RemoteBrowserEvent,
  RemoteBrowserEventPage,
  RemoteApprovalView,
} from '@hqagent/protocol'

describe('Remote Events Loop, Incremental Updating & Approvals (B1 & B2)', () => {
  enableAutoUnmount(afterEach)
  let router: any

  beforeEach(async () => {
    setActivePinia(createPinia())
    setRemoteGatewayForTesting(mockRemoteGateway)
    mockRemoteGateway.workerOnline = true
    mockRemoteGateway.cursorExpired = false
    mockRemoteGateway.highRiskApprovalAllowed = false
    mockRemoteGateway.controlOutcome = 'confirmed'
    mockRemoteGateway.withdrawalOutcome = 'success'
    mockRemoteGateway.eventPages = []
    mockRemoteGateway.pendingEvents = []
    mockRemoteGateway.hasMoreEvents = false

    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/remote/chat', component: RemoteChatPage },
        { path: '/remote/devices', component: { template: '<div>Devices</div>' } },
        { path: '/remote/login', component: { template: '<div>Login</div>' } },
      ],
    })
    await router.push('/remote/chat')
  })

  afterEach(() => {
    const store = useRemoteChatStore()
    store.stopPolling()
    store.stopDevicePolling()
    setRemoteGatewayForTesting(null)
    vi.restoreAllMocks()
  })

  it('B1: incrementally processes command delivery -> accepted -> message appended -> run succeeded', async () => {
    mockRemoteGateway.commands = []
    const wrapper = mount(RemoteChatPage, {
      global: { plugins: [router] },
    })
    const store = useRemoteChatStore()
    await flushPromises()

    // Step 0: User sends message -> Command queued & delivered
    const receipt = await store.sendMessage('请帮我统计本月代码提交量')
    await flushPromises()
    expect(receipt).toBeTruthy()
    const commandId = receipt!.commandId

    // Stage 1: UI displays "已投递" (or "已投递到云端")
    expect(wrapper.text()).toContain('已投递')
    expect(wrapper.text()).not.toContain('已接单')

    // Stage 2: Event arrives: command.accepted
    const acceptedEvent: RemoteBrowserEvent = {
      type: 'worker.event',
      serverCursor: 'cur_002',
      recordedAt: new Date().toISOString(),
      payload: {
        type: 'command.accepted',
        wireRevision: 1,
        eventId: 'ev_accepted_01',
        workerId: 'worker_demo',
        workerStoreId: 'store_demo',
        workerEpoch: 'epoch_1',
        seq: 1,
        occurredAt: new Date().toISOString(),
        commandId,
        conversationId: 'conversation_demo',
        receivedAt: new Date().toISOString(),
        status: 'accepted',
      },
    }
    mockRemoteGateway.pendingEvents = [acceptedEvent]
    await store.pollEvents()
    await flushPromises()

    // UI displays "已接单"
    expect(wrapper.text()).toContain('已接单')

    // Stage 3: Event arrives: assistant message.appended
    const assistantMessageEvent: RemoteBrowserEvent = {
      type: 'worker.event',
      serverCursor: 'cur_003',
      recordedAt: new Date().toISOString(),
      payload: {
        type: 'message.appended',
        wireRevision: 1,
        eventId: 'ev_msg_01',
        workerId: 'worker_demo',
        workerStoreId: 'store_demo',
        workerEpoch: 'epoch_1',
        seq: 2,
        occurredAt: new Date().toISOString(),
        conversationId: 'conversation_demo',
        payload: {
          messageId: 'msg_asst_999',
          conversationId: 'conversation_demo',
          role: 'assistant',
          text: '本月共提交了 42 次 commit，代码行变动净增 3500 行。',
          createdAt: new Date().toISOString(),
        },
      },
    }
    mockRemoteGateway.pendingEvents = [assistantMessageEvent]
    await store.pollEvents()
    await flushPromises()

    // UI displays assistant response text
    expect(wrapper.text()).toContain('本月共提交了 42 次 commit，代码行变动净增 3500 行。')

    // Stage 4: Event arrives: run.state_changed (status: succeeded)
    const runSucceededEvent: RemoteBrowserEvent = {
      type: 'worker.event',
      serverCursor: 'cur_004',
      recordedAt: new Date().toISOString(),
      payload: {
        type: 'run.state_changed',
        wireRevision: 1,
        eventId: 'ev_run_01',
        workerId: 'worker_demo',
        workerStoreId: 'store_demo',
        workerEpoch: 'epoch_1',
        seq: 3,
        occurredAt: new Date().toISOString(),
        commandId,
        conversationId: 'conversation_demo',
        payload: {
          runId: 'run_demo',
          conversationId: 'conversation_demo',
          status: 'succeeded',
          observedAt: new Date().toISOString(),
          summary: '统计完成',
        },
      },
    }
    mockRemoteGateway.pendingEvents = [runSucceededEvent]
    await store.pollEvents()
    await flushPromises()

    // UI displays "执行成功"
    expect(wrapper.text()).toContain('执行成功')
  })

  it('B1: correctly renders all three outcomes of controlResult from events', async () => {
    const wrapper = mount(RemoteChatPage, {
      global: { plugins: [router] },
    })
    const store = useRemoteChatStore()
    await flushPromises()

    // 1. confirmed
    const confirmedEv: RemoteBrowserEvent = {
      type: 'worker.event',
      serverCursor: 'cur_ctrl_1',
      recordedAt: new Date().toISOString(),
      payload: {
        type: 'command.control_result',
        wireRevision: 1,
        eventId: 'ev_ctrl_1',
        workerId: 'worker_demo',
        workerStoreId: 'store_demo',
        workerEpoch: 'epoch_1',
        seq: 10,
        occurredAt: new Date().toISOString(),
        commandId: 'cmd_ctrl_1',
        conversationId: 'conversation_demo',
        controlResult: {
          outcome: 'confirmed',
          executionMayStillBeRunning: false,
          orphanProcessIds: [],
          reason: 'Pause applied at boundary',
          evidence: 'adapter_confirmed',
          observedAt: new Date().toISOString(),
        },
      },
    }
    mockRemoteGateway.pendingEvents = [confirmedEv]
    await store.pollEvents()
    await flushPromises()
    expect(wrapper.text()).toContain('已确认生效')

    // 2. rejected
    const rejectedEv: RemoteBrowserEvent = {
      type: 'worker.event',
      serverCursor: 'cur_ctrl_2',
      recordedAt: new Date().toISOString(),
      payload: {
        type: 'command.control_result',
        wireRevision: 1,
        eventId: 'ev_ctrl_2',
        workerId: 'worker_demo',
        workerStoreId: 'store_demo',
        workerEpoch: 'epoch_1',
        seq: 11,
        occurredAt: new Date().toISOString(),
        commandId: 'cmd_ctrl_2',
        conversationId: 'conversation_demo',
        controlResult: {
          outcome: 'rejected',
          executionMayStillBeRunning: true,
          orphanProcessIds: [1234],
          reason: 'Worker refused cancel for critical section',
          evidence: 'adapter_refused',
          observedAt: new Date().toISOString(),
        },
      },
    }
    mockRemoteGateway.pendingEvents = [rejectedEv]
    await store.pollEvents()
    await flushPromises()
    expect(wrapper.text()).toContain('已被拒绝 (执行可能仍在进行)')

    // 3. unconfirmed
    const unconfirmedEv: RemoteBrowserEvent = {
      type: 'worker.event',
      serverCursor: 'cur_ctrl_3',
      recordedAt: new Date().toISOString(),
      payload: {
        type: 'command.control_result',
        wireRevision: 1,
        eventId: 'ev_ctrl_3',
        workerId: 'worker_demo',
        workerStoreId: 'store_demo',
        workerEpoch: 'epoch_1',
        seq: 12,
        occurredAt: new Date().toISOString(),
        commandId: 'cmd_ctrl_3',
        conversationId: 'conversation_demo',
        controlResult: {
          outcome: 'unconfirmed',
          executionMayStillBeRunning: true,
          orphanProcessIds: [],
          reason: 'Timeout waiting for worker stop confirmation',
          evidence: 'delivery_unknown',
          observedAt: new Date().toISOString(),
        },
      },
    }
    mockRemoteGateway.pendingEvents = [unconfirmedEv]
    await store.pollEvents()
    await flushPromises()
    expect(wrapper.text()).toContain('未能确认 (需回电脑核对)')
  })

  it('B1: continuously fetches subsequent event pages when hasMore is true', async () => {
    const store = useRemoteChatStore()
    await store.fetchConversations()

    const page1: RemoteBrowserEventPage = {
      items: [
        {
          type: 'message.appended',
          serverCursor: 'cursor_p1_end',
          recordedAt: new Date().toISOString(),
          payload: {
            messageId: 'msg_page_1',
            conversationId: 'conversation_demo',
            role: 'assistant',
            text: 'First page response',
            createdAt: new Date().toISOString(),
          },
        },
      ],
      nextServerCursor: 'cursor_p2_start',
      hasMore: true,
    }

    const page2: RemoteBrowserEventPage = {
      items: [
        {
          type: 'message.appended',
          serverCursor: 'cursor_p2_end',
          recordedAt: new Date().toISOString(),
          payload: {
            messageId: 'msg_page_2',
            conversationId: 'conversation_demo',
            role: 'assistant',
            text: 'Second page response',
            createdAt: new Date().toISOString(),
          },
        },
      ],
      nextServerCursor: 'cursor_p3_final',
      hasMore: false,
    }

    mockRemoteGateway.eventPages = [page1, page2]
    await store.pollEvents()

    // Both messages from both pages must be present
    expect(store.messages.some((m) => m.messageId === 'msg_page_1')).toBe(true)
    expect(store.messages.some((m) => m.messageId === 'msg_page_2')).toBe(true)
    expect(store.serverCursor).toBe('cursor_p3_final')
  })

  it('B1: ignores events from other conversations without impacting active conversation', async () => {
    const store = useRemoteChatStore()
    await store.fetchConversations()
    const initialMessageCount = store.messages.length

    const otherConvEvent: RemoteBrowserEvent = {
      type: 'message.appended',
      serverCursor: 'cur_other',
      recordedAt: new Date().toISOString(),
      payload: {
        messageId: 'msg_other_conv',
        conversationId: 'different_conv_999',
        role: 'assistant',
        text: 'This belongs to another conversation',
        createdAt: new Date().toISOString(),
      },
    }

    mockRemoteGateway.pendingEvents = [otherConvEvent]
    await store.pollEvents()

    expect(store.messages.length).toBe(initialMessageCount)
    expect(store.messages.some((m) => m.messageId === 'msg_other_conv')).toBe(false)
  })

  it('B1: falls back to rebuildFromSnapshot upon encountering unrecognized event structure for current conversation', async () => {
    const store = useRemoteChatStore()
    await store.fetchConversations()

    const snapshotSpy = vi.spyOn(mockRemoteGateway, 'getConversationSnapshot')

    const unknownEvent = {
      type: 'custom.unrecognized_event',
      serverCursor: 'cur_unknown',
      recordedAt: new Date().toISOString(),
      conversationId: 'conversation_demo',
      payload: { someUnknownField: 123 },
    } as unknown as RemoteBrowserEvent

    mockRemoteGateway.pendingEvents = [unknownEvent]
    await store.pollEvents()

    expect(snapshotSpy).toHaveBeenCalledWith('conversation_demo')
  })

  it('B2: displays pending approval loaded from snapshot.approvals', async () => {
    const testApproval: RemoteApprovalView = {
      approvalId: 'appr_test_01',
      resultRef: { runId: 'run_demo' },
      action: 'delete',
      targetSummary: 'rm -rf /tmp/build_cache',
      riskLevel: 'high',
      status: 'pending',
      requestedAt: new Date().toISOString(),
      expiresAt: new Date(Date.now() + 300000).toISOString(),
      remoteApprovalAllowed: false,
      workerPolicyRevision: 1,
    }

    mockRemoteGateway.approvals = [testApproval]

    const wrapper = mount(RemoteChatPage, {
      global: { plugins: [router] },
    })
    const store = useRemoteChatStore()
    await flushPromises()

    expect(store.activeApprovals.length).toBe(1)
    expect(store.activeApprovals[0].approvalId).toBe('appr_test_01')
    expect(wrapper.text()).toContain('安全审批请求：delete')
    expect(wrapper.text()).toContain('rm -rf /tmp/build_cache')
  })

  it('B2: adds pending approval on approval.state_changed and removes it once consumed/decided', async () => {
    const store = useRemoteChatStore()
    await store.fetchConversations()

    // Start with empty approvals
    store.approvals = []
    expect(store.activeApprovals.length).toBe(0)

    // 1. New pending approval arrives via event
    const newApproval: RemoteApprovalView = {
      approvalId: 'appr_inc_01',
      resultRef: { runId: 'run_demo' },
      action: 'shell',
      targetSummary: 'run command: pnpm build',
      riskLevel: 'low',
      status: 'pending',
      requestedAt: new Date().toISOString(),
      expiresAt: new Date(Date.now() + 300000).toISOString(),
      remoteApprovalAllowed: true,
      workerPolicyRevision: 1,
    }

    const approvalAddEvent: RemoteBrowserEvent = {
      type: 'worker.event',
      serverCursor: 'cur_appr_1',
      recordedAt: new Date().toISOString(),
      payload: {
        type: 'approval.state_changed',
        wireRevision: 1,
        eventId: 'ev_appr_1',
        workerId: 'worker_demo',
        workerStoreId: 'store_demo',
        workerEpoch: 'epoch_1',
        seq: 50,
        occurredAt: new Date().toISOString(),
        conversationId: 'conversation_demo',
        payload: newApproval,
      },
    }

    mockRemoteGateway.pendingEvents = [approvalAddEvent]
    await store.pollEvents()

    expect(store.activeApprovals.length).toBe(1)
    expect(store.activeApprovals[0].approvalId).toBe('appr_inc_01')

    // 2. Approval consumed/approved event arrives -> removed from approvals
    const approvalResolvedEvent: RemoteBrowserEvent = {
      type: 'worker.event',
      serverCursor: 'cur_appr_2',
      recordedAt: new Date().toISOString(),
      payload: {
        type: 'approval.state_changed',
        wireRevision: 1,
        eventId: 'ev_appr_2',
        workerId: 'worker_demo',
        workerStoreId: 'store_demo',
        workerEpoch: 'epoch_1',
        seq: 51,
        occurredAt: new Date().toISOString(),
        conversationId: 'conversation_demo',
        payload: {
          ...newApproval,
          status: 'approved',
        },
      },
    }

    mockRemoteGateway.pendingEvents = [approvalResolvedEvent]
    await store.pollEvents()

    expect(store.activeApprovals.length).toBe(0)
  })

  it('B2: production code in remote-chat.store.ts has zero hardcoded mock IDs (e.g. approval_demo)', () => {
    expect(remoteChatStoreRaw).not.toContain('approval_demo')
    expect(remoteChatStoreRaw).not.toContain('getApproval(')
  })

  it('B4: activeRun selects the latest run (last in ascending sequence); status bar and cancel button target the latest running run', async () => {
    mockRemoteGateway.runs = [
      {
        runId: 'run_seq_1',
        conversationId: 'conversation_demo',
        status: 'succeeded',
        observedAt: '2026-09-27T10:00:00Z',
        workerOnline: true,
      },
      {
        runId: 'run_seq_2',
        conversationId: 'conversation_demo',
        status: 'cancelled',
        observedAt: '2026-09-27T10:05:00Z',
        workerOnline: true,
      },
      {
        runId: 'run_seq_3',
        conversationId: 'conversation_demo',
        status: 'running',
        observedAt: '2026-09-27T10:10:00Z',
        workerOnline: true,
      },
    ]

    const controlSpy = vi.spyOn(mockRemoteGateway, 'controlRun')

    const wrapper = mount(RemoteChatPage, {
      global: { plugins: [router] },
    })
    const store = useRemoteChatStore()
    await flushPromises()

    // 1. activeRun must be run_seq_3 (latest, running)
    expect(store.activeRun).toBeTruthy()
    expect(store.activeRun?.runId).toBe('run_seq_3')
    expect(store.activeRun?.status).toBe('running')

    // 2. Status bar displays run_seq_3 info
    expect(wrapper.text()).toContain('Run: run_seq_3')
    expect(wrapper.text()).toContain('Worker 执行中')
    expect(wrapper.text()).not.toContain('Run: run_seq_1')

    // 3. Cancel button targets run_seq_3
    const allButtons = wrapper.findAll('button')
    const cancelBtn = allButtons.find((btn) => btn.text().includes('取消'))
    expect(cancelBtn).toBeDefined()
    expect(cancelBtn?.exists()).toBe(true)

    await cancelBtn?.trigger('click')
    await flushPromises()

    expect(controlSpy).toHaveBeenCalledWith('run_seq_3', { action: 'cancel' })
  })

  it('B4: status bar and control buttons automatically switch to new run when arriving via run.state_changed event', async () => {
    mockRemoteGateway.runs = [
      {
        runId: 'run_seq_3',
        conversationId: 'conversation_demo',
        status: 'running',
        observedAt: '2026-09-27T10:10:00Z',
        workerOnline: true,
      },
    ]

    const controlSpy = vi.spyOn(mockRemoteGateway, 'controlRun')

    const wrapper = mount(RemoteChatPage, {
      global: { plugins: [router] },
    })
    const store = useRemoteChatStore()
    await flushPromises()

    expect(store.activeRun?.runId).toBe('run_seq_3')

    // A new run run_seq_4 arrives via event in paused state
    const newRunEvent: RemoteBrowserEvent = {
      type: 'worker.event',
      serverCursor: 'cur_run_4',
      recordedAt: new Date().toISOString(),
      payload: {
        type: 'run.state_changed',
        wireRevision: 1,
        eventId: 'ev_run_4',
        workerId: 'worker_demo',
        workerStoreId: 'store_demo',
        workerEpoch: 'epoch_1',
        seq: 60,
        occurredAt: new Date().toISOString(),
        commandId: 'cmd_run_4',
        conversationId: 'conversation_demo',
        payload: {
          runId: 'run_seq_4',
          conversationId: 'conversation_demo',
          status: 'paused',
          observedAt: new Date().toISOString(),
          summary: 'Paused at breakpoint',
        },
      },
    }

    mockRemoteGateway.pendingEvents = [newRunEvent]
    await store.pollEvents()
    await flushPromises()

    // Status bar and activeRun automatically switch to run_seq_4
    expect(store.activeRun?.runId).toBe('run_seq_4')
    expect(store.activeRun?.status).toBe('paused')
    expect(wrapper.text()).toContain('Run: run_seq_4')
    expect(wrapper.text()).toContain('Worker 已暂停')

    // Control button now shows resume for run_seq_4
    const allButtons = wrapper.findAll('button')
    const resumeBtn = allButtons.find((btn) => btn.text().includes('恢复'))
    expect(resumeBtn).toBeDefined()
    await resumeBtn?.trigger('click')
    await flushPromises()

    expect(controlSpy).toHaveBeenCalledWith('run_seq_4', { action: 'resume' })
  })

  it('B4: defaults sessionMode to new and displays warning tip when latest run is cancelled or failed', async () => {
    // 1. Cancelled run
    mockRemoteGateway.runs = [
      {
        runId: 'run_prev',
        conversationId: 'conversation_demo',
        status: 'cancelled',
        observedAt: '2026-09-27T10:10:00Z',
        workerOnline: true,
      },
    ]

    const wrapper = mount(RemoteChatPage, {
      global: { plugins: [router] },
    })
    const store = useRemoteChatStore()
    await flushPromises()

    // Warning tip displayed
    expect(wrapper.text()).toContain('上一轮已中断，继续上下文可能失败')

    // Radio input for "new" is checked
    const newTopicRadio = wrapper.find<HTMLInputElement>('input[type="radio"][value="new"]')
    expect(newTopicRadio.element.checked).toBe(true)

    // 2. Failed run via event
    const failedRunEvent: RemoteBrowserEvent = {
      type: 'worker.event',
      serverCursor: 'cur_run_failed',
      recordedAt: new Date().toISOString(),
      payload: {
        type: 'run.state_changed',
        wireRevision: 1,
        eventId: 'ev_run_fail',
        workerId: 'worker_demo',
        workerStoreId: 'store_demo',
        workerEpoch: 'epoch_1',
        seq: 70,
        occurredAt: new Date().toISOString(),
        commandId: 'cmd_run_fail',
        conversationId: 'conversation_demo',
        payload: {
          runId: 'run_failed_new',
          conversationId: 'conversation_demo',
          status: 'failed',
          observedAt: new Date().toISOString(),
          summary: 'Task crashed',
        },
      },
    }

    mockRemoteGateway.pendingEvents = [failedRunEvent]
    await store.pollEvents()
    await flushPromises()

    expect(store.activeRun?.runId).toBe('run_failed_new')
    expect(store.activeRun?.status).toBe('failed')
    expect(wrapper.text()).toContain('上一轮已中断，继续上下文可能失败')
    expect(newTopicRadio.element.checked).toBe(true)
  })

  it('B6: device transitions from online to offline, without reloading page, badge becomes 电脑离线 after next device poll', async () => {
    vi.useFakeTimers()
    mockRemoteGateway.workerOnline = true

    const wrapper = mount(RemoteChatPage, {
      global: { plugins: [router] },
    })
    const store = useRemoteChatStore()
    await flushPromises()

    expect(store.isWorkerOnline).toBe(true)
    expect(wrapper.text()).toContain('电脑在线')

    // Device goes offline on server side
    mockRemoteGateway.workerOnline = false

    // Before next poll, without reloading page, badge remains 电脑在线
    expect(wrapper.text()).toContain('电脑在线')

    // Advance 15 seconds to trigger next device poll
    await vi.advanceTimersByTimeAsync(15000)
    await flushPromises()

    // After poll, badge automatically updates to 电脑离线
    expect(store.isWorkerOnline).toBe(false)
    expect(wrapper.text()).toContain('电脑离线')
    expect(wrapper.text()).not.toContain('电脑在线')

    vi.useRealTimers()
  })

  it('B6: updates device online status and badge immediately upon receiving command.updated event with workerOnline', async () => {
    mockRemoteGateway.workerOnline = true

    const wrapper = mount(RemoteChatPage, {
      global: { plugins: [router] },
    })
    const store = useRemoteChatStore()
    await flushPromises()

    expect(store.isWorkerOnline).toBe(true)
    expect(wrapper.text()).toContain('电脑在线')

    // Event arrives: command.updated with workerOnline: false
    const commandOfflineEvent: RemoteBrowserEvent = {
      type: 'command.updated',
      serverCursor: 'cur_cmd_offline',
      recordedAt: new Date().toISOString(),
      payload: {
        commandId: 'cmd_demo_001',
        conversationId: 'conversation_demo',
        targetWorkerId: 'worker_demo',
        type: 'run.submit',
        conversationSeq: 1,
        status: 'accepted',
        deliveryState: 'sent',
        withdrawalState: 'none',
        workerOnline: false,
        observedAt: new Date().toISOString(),
        createdAt: new Date().toISOString(),
        expiresAt: new Date(Date.now() + 86400000).toISOString(),
      },
    }

    mockRemoteGateway.pendingEvents = [commandOfflineEvent]
    await store.pollEvents()
    await flushPromises()

    expect(store.isWorkerOnline).toBe(false)
    expect(wrapper.text()).toContain('电脑离线')

    // Event arrives: command.updated with workerOnline: true
    const commandOnlineEvent: RemoteBrowserEvent = {
      type: 'command.updated',
      serverCursor: 'cur_cmd_online',
      recordedAt: new Date().toISOString(),
      payload: {
        commandId: 'cmd_demo_001',
        conversationId: 'conversation_demo',
        targetWorkerId: 'worker_demo',
        type: 'run.submit',
        conversationSeq: 1,
        status: 'accepted',
        deliveryState: 'sent',
        withdrawalState: 'none',
        workerOnline: true,
        observedAt: new Date().toISOString(),
        createdAt: new Date().toISOString(),
        expiresAt: new Date(Date.now() + 86400000).toISOString(),
      },
    }

    mockRemoteGateway.pendingEvents = [commandOnlineEvent]
    await store.pollEvents()
    await flushPromises()

    expect(store.isWorkerOnline).toBe(true)
    expect(wrapper.text()).toContain('电脑在线')
  })

  it('B6: pauses device polling when page visibility is hidden, and refreshes immediately when visibility returns to visible', async () => {
    vi.useFakeTimers()
    mockRemoteGateway.workerOnline = true

    const wrapper = mount(RemoteChatPage, {
      global: { plugins: [router] },
    })
    const store = useRemoteChatStore()
    await flushPromises()

    expect(store.isWorkerOnline).toBe(true)
    expect(wrapper.text()).toContain('电脑在线')

    const getDeviceSpy = vi.spyOn(mockRemoteGateway, 'getDevice')
    getDeviceSpy.mockClear()

    // 1. Page becomes hidden -> stops device polling
    Object.defineProperty(document, 'visibilityState', {
      value: 'hidden',
      writable: true,
      configurable: true,
    })
    document.dispatchEvent(new Event('visibilitychange'))

    // Advance 30 seconds while hidden; no device poll should occur
    await vi.advanceTimersByTimeAsync(30000)
    await flushPromises()
    expect(getDeviceSpy).not.toHaveBeenCalled()

    // Server state changes while user is away
    mockRemoteGateway.workerOnline = false

    // 2. User switches back to tab: page becomes visible -> immediate refresh
    Object.defineProperty(document, 'visibilityState', {
      value: 'visible',
      writable: true,
      configurable: true,
    })
    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()

    // Called immediately on returning to visible
    expect(getDeviceSpy).toHaveBeenCalledTimes(1)
    expect(store.isWorkerOnline).toBe(false)
    expect(wrapper.text()).toContain('电脑离线')

    // Polling also resumed (advancing 15s calls it again)
    mockRemoteGateway.workerOnline = true
    await vi.advanceTimersByTimeAsync(15000)
    await flushPromises()
    expect(getDeviceSpy).toHaveBeenCalledTimes(2)
    expect(store.isWorkerOnline).toBe(true)
    expect(wrapper.text()).toContain('电脑在线')

    vi.useRealTimers()
  })
})

