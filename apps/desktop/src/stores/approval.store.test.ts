import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useApprovalStore } from './approval.store'

describe('useApprovalStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('fetches approvals and distinguishes pending vs decided', async () => {
    const store = useApprovalStore()
    await store.fetchApprovals()

    expect(store.approvals.length).toBeGreaterThan(0)
    expect(store.pendingApprovals.length).toBeGreaterThan(0)
    expect(store.pendingCount).toBe(store.pendingApprovals.length)
  })

  it('identifies high-risk actions requiring secondary confirmation', () => {
    const store = useApprovalStore()
    expect(store.isHighRiskAction('git_push')).toBe(true)
    expect(store.isHighRiskAction('shell')).toBe(true)
    expect(store.isHighRiskAction('delete')).toBe(true)
    expect(store.isHighRiskAction('deploy')).toBe(true)
    expect(store.isHighRiskAction('network')).toBe(false)
  })

  it('responds to an approval request and updates state', async () => {
    const store = useApprovalStore()
    await store.fetchApprovals()

    const pending = store.pendingApprovals[0]
    expect(pending).toBeDefined()

    const result = await store.respondApproval(pending.id, {
      decision: 'approve',
      reason: '已人工核验 git commit diff',
    })

    expect(result.status).toBe('approved')
    expect(result.decision).toBe('approve')
  })

  it('handles realtime approval events', async () => {
    const store = useApprovalStore()
    store.handleApprovalEvent({
      eventId: 'evt_appr_new',
      seq: 999,
      occurredAt: '2026-09-06T12:00:00Z',
      aggregateType: 'approval',
      aggregateId: 'appr_new_1',
      taskId: 'task_2',
      type: 'approval.required',
      payload: {
        approvalId: 'appr_new_1',
        action: 'delete',
        targetResource: 'rm -rf /dist',
        riskLevel: 'critical',
      },
      protocolVersion: '0.2.0',
    })

    const found = store.approvals.find((a) => a.id === 'appr_new_1')
    expect(found).toBeDefined()
    expect(found?.action).toBe('delete')
    expect(found?.status).toBe('pending')

    // Resolve it
    store.handleApprovalEvent({
      eventId: 'evt_appr_res',
      seq: 1000,
      occurredAt: '2026-09-06T12:01:00Z',
      aggregateType: 'approval',
      aggregateId: 'appr_new_1',
      type: 'approval.resolved',
      payload: {
        approvalId: 'appr_new_1',
        decision: 'reject',
        reason: '风险过高',
        decidedAt: '2026-09-06T12:01:00Z',
      },
      protocolVersion: '0.2.0',
    })

    expect(found?.status).toBe('rejected')
  })
})
