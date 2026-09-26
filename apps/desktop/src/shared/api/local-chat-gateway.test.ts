import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { RealLocalChatGateway } from './local-chat-gateway'
import { HubApiError } from './local-hub-gateway'

describe('RealLocalChatGateway', () => {
  let gateway: RealLocalChatGateway
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    gateway = new RealLocalChatGateway('http://127.0.0.1:49210')
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('sends credentials=include and headers with JSON envelopes', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        success: true,
        data: { authenticated: true, protocolVersion: '0.3.0' },
        requestId: 'req_123',
        protocolVersion: '0.3.0',
      }),
    })
    globalThis.fetch = mockFetch as any

    const res = await gateway.getLocalAuthStatus()
    expect(res.authenticated).toBe(true)
    expect(mockFetch).toHaveBeenCalledWith(
      'http://127.0.0.1:49210/api/v2/auth/status',
      expect.objectContaining({
        credentials: 'include',
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
        }),
      })
    )
  })

  it('passes Idempotency-Key header on creation or message sending', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({
        success: true,
        data: {
          id: 'conv_1',
          title: '测试',
          workspaceId: 'ws_1',
          sceneId: 'analyze',
          createdAt: '2026-09-24T00:00:00Z',
          updatedAt: '2026-09-24T00:00:00Z',
        },
        requestId: 'req_create',
        protocolVersion: '0.3.0',
      }),
    })
    globalThis.fetch = mockFetch as any

    await gateway.createLocalConversation(
      { title: '测试', workspaceId: 'ws_1', sceneId: 'analyze' },
      'idemp_key_999'
    )

    expect(mockFetch).toHaveBeenCalledWith(
      'http://127.0.0.1:49210/api/v2/conversations',
      expect.objectContaining({
        headers: expect.objectContaining({
          'Idempotency-Key': 'idemp_key_999',
        }),
      })
    )
  })

  it('patches conversation metadata with expected version and a required idempotency key', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        success: true,
        data: {
          id: 'conv_1', title: '新名称', workspaceId: 'ws_1', sceneId: 'analyze',
          createdAt: '2026-09-24T00:00:00Z', updatedAt: '2026-09-26T00:00:00Z',
          version: 2, archived: false,
        },
      }),
    })
    globalThis.fetch = mockFetch as any

    await gateway.updateLocalConversation(
      'conv_1',
      { expectedVersion: 1, title: '新名称' },
      'metadata-request-1'
    )

    expect(mockFetch).toHaveBeenCalledWith(
      'http://127.0.0.1:49210/api/v2/conversations/conv_1',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ expectedVersion: 1, title: '新名称' }),
        headers: expect.objectContaining({ 'Idempotency-Key': 'metadata-request-1' }),
      })
    )
  })

  it('creates custom scenes and role templates through the v2 write endpoints', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ success: true, data: { id: 'created', version: 1 } }),
    })
    globalThis.fetch = mockFetch as any

    await gateway.createLocalScene({
      name: '自定义开发',
      roles: [{ roleId: 'developer', roleName: '实现者', agentInstanceId: 'agent-1', instructions: '实现', enabled: true }],
    }, 'scene-create-key')
    await gateway.createLocalRoleTemplate({
      name: '安全审查', baseRoleId: 'reviewer', instructions: '检查安全边界',
    }, 'template-create-key')
    await gateway.updateLocalRoleTemplate('template-1', {
      expectedVersion: 1, name: '安全验收', instructions: '检查安全与证据',
    }, 'template-update-key')

    expect(mockFetch).toHaveBeenNthCalledWith(1, expect.stringContaining('/api/v2/scenes'),
      expect.objectContaining({ method: 'POST', headers: expect.objectContaining({ 'Idempotency-Key': 'scene-create-key' }) }))
    expect(mockFetch).toHaveBeenNthCalledWith(2, expect.stringContaining('/api/v2/role-templates'),
      expect.objectContaining({ method: 'POST', headers: expect.objectContaining({ 'Idempotency-Key': 'template-create-key' }) }))
    expect(mockFetch).toHaveBeenNthCalledWith(3, expect.stringContaining('/api/v2/role-templates/template-1'),
      expect.objectContaining({ method: 'PUT', headers: expect.objectContaining({ 'Idempotency-Key': 'template-update-key' }) }))
  })

  it('unwraps HubApiError from unsuccessful envelope', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({
        success: false,
        error: {
          code: 'CONFLICT',
          message: '版本冲突',
          retryable: false,
          detail: { expectedVersion: 1, currentVersion: 2 },
        },
        requestId: 'req_conflict',
        protocolVersion: '0.3.0',
      }),
    })
    globalThis.fetch = mockFetch as any

    await expect(
      gateway.saveLocalScene('develop', { roles: [], expectedVersion: 1 })
    ).rejects.toThrow(HubApiError)
  })

  it('sends the required idempotency key on approval decisions', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, status: 200,
      json: async () => ({ success: true, data: { id: 'approval-1', status: 'approved' } }) })
    globalThis.fetch = mockFetch as any
    await gateway.decideLocalApproval('approval-1', { decision: 'approve' }, 'approval-request-1')
    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/approvals/approval-1/decisions'),
      expect.objectContaining({ headers: expect.objectContaining({ 'Idempotency-Key': 'approval-request-1' }) }))
  })

  it('handles network failure with retryable HUB_NOT_READY HubApiError', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('Connection refused')) as any

    try {
      await gateway.getLocalAuthStatus()
      expect.unreachable('Should have thrown HubApiError')
    } catch (err: any) {
      expect(err).toBeInstanceOf(HubApiError)
      expect(err.code).toBe('HUB_NOT_READY')
      expect(err.retryable).toBe(true)
    }
  })

  it('requests a local directory dialog with cookie auth and preserves cancellation', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, status: 200,
      json: async () => ({ success: true, data: { cancelled: true } }) })
    globalThis.fetch = mockFetch as any
    expect(await gateway.pickLocalDirectory({})).toEqual({ cancelled: true })
    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/workspaces/pick'),
      expect.objectContaining({ method: 'POST', body: '{}', credentials: 'include' }))
  })
})
