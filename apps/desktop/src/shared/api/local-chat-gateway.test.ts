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
})
