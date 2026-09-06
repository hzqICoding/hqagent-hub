import { describe, it, expect, beforeEach } from 'vitest'
import { MockGateway } from './mock-gateway'

describe('MockGateway', () => {
  let gateway: MockGateway

  beforeEach(() => {
    gateway = new MockGateway('happy-path')
    gateway.setDelay(0)
  })

  it('loads bootstrap data from contract fixtures', async () => {
    const bootstrap = await gateway.getBootstrap()
    expect(bootstrap.appVersion).toBe('0.1.0')
    expect(bootstrap.agents.total).toBe(2)
    expect(bootstrap.agents.ready).toBe(2)
    expect(bootstrap.features.tasks.available).toBe(true)
    expect(bootstrap.features.updates.available).toBe(false)
    expect(bootstrap.features.updates.reason).toContain('Update Agent 未运行')
    expect((bootstrap as any).hubEndpoint).toBeUndefined()
    expect(bootstrap.currentWorkspace?.name).toBe('HQAgent-Hub')
  })

  it('lists agents correctly in happy-path scenario', async () => {
    const agents = await gateway.listAgents()
    expect(agents.length).toBe(3)
    const claude = agents.find((a) => a.adapterId === 'claude')
    expect(claude).toBeDefined()
    expect(claude?.status).toBe('ready')
  })

  it('returns empty agent list in first-run-no-agent scenario', async () => {
    gateway.setScenario('first-run-no-agent')
    const agents = await gateway.listAgents()
    expect(agents.length).toBe(0)

    const bootstrap = await gateway.getBootstrap()
    expect(bootstrap.agents.total).toBe(0)
    expect(bootstrap.agents.ready).toBe(0)
  })

  it('fetches task details and approval requests', async () => {
    const task = await gateway.getTask('task_20260905_001')
    expect(task.objective).toContain('Local Hub')
    expect(task.nodes.length).toBeGreaterThan(0)

    const approvals = await gateway.listApprovals()
    expect(approvals.length).toBe(1)
    expect(approvals[0].action).toBe('git_push')
  })

  it('handles approval responses properly', async () => {
    const res = await gateway.respondApproval('appr_99812', { decision: 'approve' })
    expect(res.status).toBe('approved')
    expect(res.decision).toBe('approve')
  })

  it('throws error when simulated disconnected', async () => {
    gateway.setScenario('hub-disconnected')
    await expect(gateway.getBootstrap()).rejects.toThrow('ERR_HUB_DISCONNECTED')
  })

  it('Trap 6: concurrent subscriptions in the same tick deduplicate into a single connection', async () => {
    const received1: any[] = []
    const received2: any[] = []

    // Simulate AppLayout and TaskDetailPage subscribing in the same tick
    const sub1 = gateway.subscribeEvents({ afterSeq: 0 }, (e) => received1.push(e))
    const sub2 = gateway.subscribeEvents({ afterSeq: 0 }, (e) => received2.push(e))

    await new Promise((resolve) => setTimeout(resolve, 30))

    expect(gateway.ticketRequestCount).toBe(1)
    expect(gateway.connectionCount).toBe(1)
    expect(gateway.isConnected).toBe(true)

    // Emit single event
    gateway.emitMockEvent({ type: 'agent.progress', payload: { message: 'test' } })

    // Each subscriber gets exactly 1 event (no duplicates)
    expect(received1.length).toBe(1)
    expect(received2.length).toBe(1)

    sub1.unsubscribe()
    sub2.unsubscribe()
    expect(gateway.isConnected).toBe(false)
  })

  it('replays historical events when afterSeq is provided', async () => {
    // Emit some events first
    gateway.emitMockEvent({ type: 'agent.started', payload: {} })
    gateway.emitMockEvent({ type: 'agent.progress', payload: { message: 'step 1' } })

    const replayed: any[] = []
    const sub = gateway.subscribeEvents({ afterSeq: 0 }, (e) => replayed.push(e))

    expect(replayed.length).toBe(2)
    sub.unsubscribe()
  })

  it('Trap 5: handles 10,000 events throughput smoothly', () => {
    const events = gateway.generate10kEvents('task_20260905_001')
    expect(events.length).toBe(10000)
    expect(events[0].seq).toBeLessThan(events[9999].seq)
  })

  it('simulates close with code 4410 resetting sequence cursor', () => {
    let closedCode = 0
    gateway.onSimulatedClose((code) => {
      closedCode = code
    })

    gateway.simulateClose(4410)
    expect(closedCode).toBe(4410)
    expect(gateway.isConnected).toBe(false)
  })
})
