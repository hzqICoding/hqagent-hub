import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
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
})
