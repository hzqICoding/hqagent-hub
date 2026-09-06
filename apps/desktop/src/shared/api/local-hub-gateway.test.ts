import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { LocalHubGateway, HubApiError } from './local-hub-gateway'

describe('LocalHubGateway', () => {
  const mockEndpoint = {
    baseUrl: 'http://127.0.0.1:54321',
    token: 'tok_test_mock_123',
  }

  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('HubApiError captures code, status, and detail correctly', () => {
    const err = new HubApiError(
      'Origin not allowed',
      'ORIGIN_NOT_ALLOWED',
      403,
      { origin: 'http://malicious.local' },
      false,
      'req_123'
    )
    expect(err.message).toBe('Origin not allowed')
    expect(err.code).toBe('ORIGIN_NOT_ALLOWED')
    expect(err.status).toBe(403)
    expect(err.detail).toEqual({ origin: 'http://malicious.local' })
    expect(err.retryable).toBe(false)
    expect(err.requestId).toBe('req_123')
  })

  it('R1: throws when endpoint cannot be acquired (no hardcoded fallback token)', async () => {
    // Construct gateway without initial endpoint and without Tauri or env vars
    const originalInternals = (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__

    const gateway = new LocalHubGateway()
    await expect(gateway.getBootstrap()).rejects.toThrow(
      /Local Hub endpoint unavailable/
    )

    if (originalInternals !== undefined) {
      ;(window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = originalInternals
    }
  })

  it('R4: throws HubApiError with protocol error code on structured error response', async () => {
    const gateway = new LocalHubGateway(mockEndpoint)

    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      statusText: 'Service Unavailable',
      json: async () => ({
        success: false,
        error: {
          code: 'HUB_MAINTENANCE',
          message: 'Hub is undergoing maintenance',
          detail: { draining: true },
          retryable: true,
        },
        requestId: 'req_maint_99',
        protocolVersion: '0.2.0',
      }),
    })
    globalThis.fetch = mockFetch as unknown as typeof fetch

    await expect(gateway.getBootstrap()).rejects.toThrow(HubApiError)
    try {
      await gateway.getBootstrap()
    } catch (e) {
      expect(e).toBeInstanceOf(HubApiError)
      const hubErr = e as HubApiError
      expect(hubErr.code).toBe('HUB_MAINTENANCE')
      expect(hubErr.status).toBe(503)
      expect(hubErr.detail).toEqual({ draining: true })
      expect(hubErr.retryable).toBe(true)
      expect(hubErr.requestId).toBe('req_maint_99')
    }
  })

  it('R4: throws HubApiError with ORIGIN_NOT_ALLOWED on 403 response', async () => {
    const gateway = new LocalHubGateway(mockEndpoint)

    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      statusText: 'Forbidden',
      json: async () => ({
        success: false,
        error: {
          code: 'ORIGIN_NOT_ALLOWED',
          message: 'Token valid but origin not permitted',
          retryable: false,
        },
        requestId: 'req_orig_403',
        protocolVersion: '0.2.0',
      }),
    })
    globalThis.fetch = mockFetch as unknown as typeof fetch

    try {
      await gateway.listAgents()
    } catch (e) {
      expect(e).toBeInstanceOf(HubApiError)
      const hubErr = e as HubApiError
      expect(hubErr.code).toBe('ORIGIN_NOT_ALLOWED')
      expect(hubErr.status).toBe(403)
    }
  })

  it('R2: single-flight WS connection prevents duplicate tickets and sockets', async () => {
    const gateway = new LocalHubGateway(mockEndpoint)
    let ticketCallCount = 0

    const mockFetch = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes('/api/v1/auth/ws-ticket')) {
        ticketCallCount++
        return {
          ok: true,
          status: 200,
          json: async () => ({
            success: true,
            data: { ticket: 'tkt_mock_once', expiresAt: '2026-09-06T12:00:00Z' },
            requestId: 'req_ws_1',
            protocolVersion: '0.2.0',
          }),
        }
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ success: true, data: {} }),
      }
    })
    globalThis.fetch = mockFetch as unknown as typeof fetch

    let wsCreatedCount = 0
    class MockWebSocket {
      readyState = 1 // OPEN
      onopen: (() => void) | null = null
      onmessage: ((msg: { data: string }) => void) | null = null
      onerror: ((err: unknown) => void) | null = null
      onclose: (() => void) | null = null

      constructor(_url: string) {
        wsCreatedCount++
        setTimeout(() => {
          if (this.onopen) this.onopen()
        }, 0)
      }

      close() {
        this.readyState = 3 // CLOSED
        if (this.onclose) this.onclose()
      }
    }
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket

    const fn1 = vi.fn()
    const fn2 = vi.fn()

    // Subscribe twice in the same tick
    const sub1 = gateway.subscribeEvents({ afterSeq: 0 }, fn1)
    const sub2 = gateway.subscribeEvents({ afterSeq: 0 }, fn2)

    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(ticketCallCount).toBe(1)
    expect(wsCreatedCount).toBe(1)

    sub1.unsubscribe()
    sub2.unsubscribe()
  })

  it('R3 & R7: handles WS ticket acquisition failure with reconnect backoff', async () => {
    vi.useFakeTimers()
    const gateway = new LocalHubGateway(mockEndpoint)
    let ticketAttempts = 0

    const mockFetch = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes('/api/v1/auth/ws-ticket')) {
        ticketAttempts++
        return {
          ok: false,
          status: 503,
          json: async () => ({
            success: false,
            error: {
              code: 'HUB_NOT_READY',
              message: 'Hub is still starting up',
              retryable: true,
            },
            requestId: 'req_init',
            protocolVersion: '0.2.0',
          }),
        }
      }
      return { ok: true, json: async () => ({ success: true, data: {} }) }
    })
    globalThis.fetch = mockFetch as unknown as typeof fetch

    const onError = vi.fn()
    const sub = gateway.subscribeEvents({ afterSeq: 0 }, vi.fn(), onError)

    // Initial failure
    await vi.advanceTimersByTimeAsync(10)
    expect(ticketAttempts).toBe(1)
    expect(onError).toHaveBeenCalled()

    // Advance 1000ms (1st backoff attempt: 1000 * 1.5^0 = 1000ms)
    await vi.advanceTimersByTimeAsync(1000)
    expect(ticketAttempts).toBe(2)

    sub.unsubscribe()
    vi.useRealTimers()
  })
})
