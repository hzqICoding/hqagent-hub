import { describe, it, expect, beforeEach } from 'vitest'
import { MockGateway } from './mock-gateway'

describe('MockGateway', () => {
  let gateway: MockGateway

  beforeEach(() => {
    gateway = new MockGateway('happy-path')
    gateway.setDelay(0)
  })

  it('loads bootstrap data from fixtures', async () => {
    const bootstrap = await gateway.getBootstrap()
    expect(bootstrap.appVersion).toBe('0.1.0')
    expect(bootstrap.agentsCount).toBeGreaterThan(0)
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
  })

  it('fetches task details and approval requests', async () => {
    const task = await gateway.getTask('task_20260905_001')
    expect(task.objective).toContain('HQAgent-Hub')
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
})
