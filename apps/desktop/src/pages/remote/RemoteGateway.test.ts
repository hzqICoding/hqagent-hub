import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { RemoteGateway, RemoteApiError } from '@/shared/api/remote-gateway'
import { getRemoteErrorMessage } from '@/shared/i18n/remote-errors'

describe('RemoteGateway Real HTTP Wrapper', () => {
  let gateway: RemoteGateway
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    gateway = new RemoteGateway('https://hub.example.com')
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('manages CSRF token strictly in memory and does not write to localStorage or sessionStorage', async () => {
    const mockSession = {
      success: true,
      data: {
        authenticated: true,
        account: { loginName: 'test-user', displayName: 'Test User' },
        expiresAt: '2026-09-27T00:00:00Z',
        csrfToken: 'csrf_secret_token_12345678901234567890',
      },
      requestId: 'req_001',
      protocolVersion: '0.6.0',
    }

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => mockSession,
    })

    const session = await gateway.login({ loginName: 'test-user', password: 'secretpassword' })
    expect(session.authenticated).toBe(true)
    expect(gateway.getCsrfToken()).toBe('csrf_secret_token_12345678901234567890')

    // Audit: NO tokens stored in Web Storage
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('injects X-CSRF-Token and Idempotency-Key headers on mutating write requests', async () => {
    gateway.setCsrfToken('csrf_active_token_99999999999999999999')

    let capturedHeaders: Record<string, string> = {}
    let capturedBody = ''

    globalThis.fetch = vi.fn().mockImplementation((_url, init) => {
      capturedHeaders = init.headers
      capturedBody = init.body
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => ({
          success: true,
          data: {
            pairRequestId: 'pair_req_01',
            deviceName: 'Office PC',
            platform: 'windows',
            architecture: 'x86_64',
            expiresAt: '2026-09-26T12:05:00Z',
          },
          requestId: 'req_002',
          protocolVersion: '0.6.0',
        }),
      })
    })

    const preview = await gateway.previewPairing({ pairCode: 'ABCD1234' }, 'custom-idemp-key')
    expect(preview.deviceName).toBe('Office PC')
    expect(capturedHeaders['X-CSRF-Token']).toBe('csrf_active_token_99999999999999999999')
    expect(capturedHeaders['Idempotency-Key']).toBe('custom-idemp-key')
    expect(capturedHeaders['Content-Type']).toBe('application/json')
    expect(JSON.parse(capturedBody)).toEqual({ pairCode: 'ABCD1234' })
  })

  it('parses Retry-After header on HTTP 429 rate limit responses', async () => {
    const errorEnvelope = {
      success: false,
      error: {
        code: 'REMOTE_RATE_LIMITED',
        message: 'Rate limit exceeded',
      },
      requestId: 'req_rate_limit',
      protocolVersion: '0.6.0',
    }

    const headers = new Headers()
    headers.set('Retry-After', '45')

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      headers,
      json: async () => errorEnvelope,
    })

    try {
      await gateway.login({ loginName: 'alice', password: 'password123' })
      expect.unreachable('Should have thrown RemoteApiError')
    } catch (err: unknown) {
      expect(err).toBeInstanceOf(RemoteApiError)
      const apiErr = err as RemoteApiError
      expect(apiErr.code).toBe('REMOTE_RATE_LIMITED')
      expect(apiErr.status).toBe(429)
      expect(apiErr.retryAfter).toBe(45)
      expect(apiErr.message).toBe('请求过于频繁被限流，请稍候再试')
    }
  })

  it('maps all error codes including CONVERSATION_AUTHORITY_MISMATCH to localized Chinese text', () => {
    expect(getRemoteErrorMessage('REMOTE_AUTH_REQUIRED')).toBe('远程账号会话缺失或已过期，请重新登录')
    expect(getRemoteErrorMessage('CONVERSATION_AUTHORITY_MISMATCH')).toBe('对话归属不匹配（远程对话不能通过本地私有通道写入）')
    expect(getRemoteErrorMessage('REMOTE_PAIRING_EXPIRED')).toBe('配对请求或配对短码已过期，请在电脑端重新发起')
    expect(getRemoteErrorMessage('REMOTE_APPROVAL_FORBIDDEN')).toBe('高风险或受限动作禁止在手机端远程批准，请回到电脑端处理')
    expect(getRemoteErrorMessage('REMOTE_WITHDRAWAL_TOO_LATE')).toBe('原任务已在执行或已结束，无法撤回；如需停止请使用取消运行')
  })
})
