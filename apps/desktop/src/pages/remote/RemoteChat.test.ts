import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import RemoteChatPage from './RemoteChatPage.vue'
import { useRemoteChatStore } from '@/stores/remote-chat.store'
import { mockRemoteGateway } from '@/shared/api/mock-remote-gateway'
import { setRemoteGatewayForTesting } from '@/shared/api/remote-provider'

describe('RemoteChat Workbench and Three-Layer Status', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setRemoteGatewayForTesting(mockRemoteGateway)
    mockRemoteGateway.workerOnline = true
    mockRemoteGateway.cursorExpired = false
    mockRemoteGateway.highRiskApprovalAllowed = false
    mockRemoteGateway.controlOutcome = 'confirmed'
    mockRemoteGateway.withdrawalOutcome = 'success'
  })

  afterEach(() => {
    const store = useRemoteChatStore()
    store.stopPolling()
    store.stopDevicePolling()
    setRemoteGatewayForTesting(null)
    vi.restoreAllMocks()
  })

  it('displays "电脑离线" and NEVER "执行中" when computer is offline, and rejects message immediately', async () => {
    mockRemoteGateway.workerOnline = false
    const wrapper = mount(RemoteChatPage)
    const store = useRemoteChatStore()

    await flushPromises()
    expect(store.isWorkerOnline).toBe(false)

    // Layer 1 Transport status must display "电脑离线"
    expect(wrapper.text()).toContain('电脑离线')
    expect(wrapper.text()).not.toContain('电脑在线')

    // Sending a message while computer is offline fails immediately (no offline queueing in R1.5)
    await expect(store.sendMessage('离线测试指令')).rejects.toThrow('设备离线，发送失败')
    await flushPromises()

    expect(store.sendError).toBe('设备离线，发送失败')
    expect(wrapper.text()).toContain('设备离线，发送失败')

    // Absolutely NEVER claim running/executing on transport layer when offline
    const transportSection = wrapper.find('section')
    expect(transportSection.text()).toContain('电脑离线')
    expect(transportSection.text()).not.toContain('电脑在线')
  })

  it('renders all three distinct layers: Transport State, Control Result, and Execution State', async () => {
    mockRemoteGateway.workerOnline = true
    mockRemoteGateway.controlOutcome = 'confirmed'
    const wrapper = mount(RemoteChatPage)
    const store = useRemoteChatStore()
    await flushPromises()

    // 1. Transport state
    expect(wrapper.text()).toContain('1. 传输状态')
    expect(wrapper.text()).toContain('电脑在线')

    // 2. Control result - trigger control action pause
    await store.controlRun('run_demo', 'pause')
    await flushPromises()
    expect(wrapper.text()).toContain('2. 控制结果')
    expect(wrapper.text()).toContain('已确认生效')

    // 3. Execution status (Worker status)
    expect(wrapper.text()).toContain('3. 执行状态 (Worker)')
    expect(wrapper.text()).toContain('Worker 已暂停')
  })

  it('displays rejected and unconfirmed control outcomes accurately', async () => {
    const wrapper = mount(RemoteChatPage)
    const store = useRemoteChatStore()
    await flushPromises()

    // Test rejected control outcome
    mockRemoteGateway.controlOutcome = 'rejected'
    await store.controlRun('run_demo', 'pause')
    await flushPromises()
    expect(wrapper.text()).toContain('已被拒绝 (执行可能仍在进行)')

    // Test unconfirmed control outcome
    mockRemoteGateway.controlOutcome = 'unconfirmed'
    await store.controlRun('run_demo', 'resume')
    await flushPromises()
    expect(wrapper.text()).toContain('未能确认 (需回电脑核对)')
  })

  it('falls back to conversation snapshot when server cursor expires (REMOTE_CURSOR_EXPIRED)', async () => {
    const store = useRemoteChatStore()
    await store.fetchConversations()
    const initialCursor = store.serverCursor
    expect(initialCursor).toBeTruthy()

    // Simulate cursor expiration on events poll
    mockRemoteGateway.cursorExpired = true

    await store.pollEvents()
    await flushPromises()

    // Rebuilt snapshot cursor
    expect(store.serverCursor).toContain('snapshot_cursor_')
    expect(store.serverCursor).not.toBe(initialCursor)
    expect(store.messages.length).toBeGreaterThan(0)
  })

  it('enforces high-risk approval restrictions: hides approve button and displays warning banner', async () => {
    const wrapper = mount(RemoteChatPage)
    const store = useRemoteChatStore()
    await flushPromises()

    // Ensure pending high-risk approval exists
    expect(store.activeApprovals.length).toBeGreaterThan(0)
    const approval = store.activeApprovals[0]
    expect(approval.action).toBe('git_push')

    // High risk banner must be visible
    expect(wrapper.text()).toContain('高风险操作，请回到电脑上处理')

    // "批准执行" button MUST NOT exist in DOM
    const allButtons = wrapper.findAll('button')
    const approveBtn = allButtons.find((btn) => btn.text().includes('批准执行'))
    expect(approveBtn).toBeUndefined()

    // "拒绝拦截" button is visible
    const rejectBtn = allButtons.find((btn) => btn.text().includes('拒绝拦截'))
    expect(rejectBtn).toBeDefined()
    expect(rejectBtn?.exists()).toBe(true)

    // Programmatic safety check: store blocks approving high-risk action
    const approvalAttempt = await store.decideApproval(approval.approvalId, 'approve')
    expect(approvalAttempt).toBe(false)
    expect(store.actionError).toContain('高风险操作禁止在手机端远程批准')

    // Rejecting is permitted
    const rejectAttempt = await store.decideApproval(approval.approvalId, 'reject')
    expect(rejectAttempt).toBe(true)
    expect(approval.status).toBe('rejected')
  })

  it('handles too-late and unconfirmed command withdrawals', async () => {
    const store = useRemoteChatStore()
    await store.fetchConversations()

    // Too late withdrawal
    mockRemoteGateway.withdrawalOutcome = 'too_late'
    const successTooLate = await store.withdrawCommand('cmd_demo_001')
    expect(successTooLate).toBe(false)
    expect(store.actionError).toBe('原任务已在执行或已结束，无法撤回；如需停止请使用取消运行')

    // Unconfirmed withdrawal
    mockRemoteGateway.withdrawalOutcome = 'unconfirmed'
    const successUnconfirmed = await store.withdrawCommand('cmd_demo_001')
    expect(successUnconfirmed).toBe(false)
    expect(store.actionError).toBe('指令可能已发送至电脑，撤回未能确认，请回到电脑核对')
  })

  it('supports opening and closing mobile sidebar drawer', async () => {
    const wrapper = mount(RemoteChatPage)
    await flushPromises()

    // Initially drawer is closed
    const drawer = wrapper.find('aside')
    expect(drawer.classes()).toContain('-translate-x-full')

    // Click menu toggle button
    const menuBtn = wrapper.find('button[title="打开对话列表"]')
    await menuBtn.trigger('click')
    await wrapper.vm.$nextTick()

    // Drawer is now open
    expect(drawer.classes()).toContain('translate-x-0')

    // Backdrop exists and clicking it closes drawer
    const backdrop = wrapper.find('.fixed.inset-0.bg-black\\/50')
    expect(backdrop.exists()).toBe(true)
    await backdrop.trigger('click')
    await wrapper.vm.$nextTick()
    expect(drawer.classes()).toContain('-translate-x-full')
  })
})
