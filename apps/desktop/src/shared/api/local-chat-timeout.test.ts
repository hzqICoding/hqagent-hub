import { afterEach, describe, expect, it, vi } from 'vitest'
import { RealLocalChatGateway } from './local-chat-gateway'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('local chat request deadline', () => {
  it.each(['headers', 'body'])('times out stalled %s and allows a subsequent request', async phase => {
    vi.useFakeTimers()
    const never = new Promise<never>(() => {})
    const fetch = vi.fn().mockImplementationOnce(() => phase === 'headers'
      ? never : Promise.resolve({ ok: true, status: 200, json: () => never }))
      .mockResolvedValue({ ok: true, status: 200,
        json: async () => ({ success: true, data: { authenticated: true } }) })
    vi.stubGlobal('fetch', fetch)
    const gateway = new RealLocalChatGateway()
    const request = gateway.getLocalAuthStatus()
    const rejected = expect(request).rejects.toMatchObject({ code: 'HUB_NOT_READY', retryable: true })
    await vi.advanceTimersByTimeAsync(15000)
    await rejected
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true)
    expect((await gateway.getLocalAuthStatus()).authenticated).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('keeps the native folder dialog request alive beyond the normal HTTP deadline', async () => {
    vi.useFakeTimers()
    let complete!: (value: unknown) => void
    const fetch = vi.fn().mockImplementation(() => new Promise(resolve => { complete = resolve }))
    vi.stubGlobal('fetch', fetch)
    const request = new RealLocalChatGateway().pickLocalDirectory({})
    await vi.advanceTimersByTimeAsync(15000)
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(false)
    complete({ ok: true, status: 200, json: async () => ({ success: true, data: { cancelled: true } }) })
    expect(await request).toEqual({ cancelled: true })
    expect(vi.getTimerCount()).toBe(0)
  })
})
