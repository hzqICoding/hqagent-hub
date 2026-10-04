import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LocalHubGateway } from './local-hub-gateway'
import type { EventSubscription } from './ui-gateway'

class Socket {
  static CONNECTING = 0
  static OPEN = 1
  static instances: Socket[] = []
  readyState = 1
  onopen: (() => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: ((error: unknown) => void) | null = null
  constructor(readonly url: string) { Socket.instances.push(this) }
  close() { this.readyState = 3; this.onclose?.({ code: 1000 }) }
  expire() { this.readyState = 3; this.onclose?.({ code: 4410 }) }
}

const ticketResponse = () => ({
  ok: true, status: 200,
  json: async () => ({ success: true, data: { ticket: 'synthetic-ticket' } }),
})

describe('local event stream cursor recovery', () => {
  let subscription: EventSubscription | undefined
  beforeEach(() => {
    vi.useFakeTimers()
    Socket.instances = []
    vi.stubGlobal('WebSocket', Socket)
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => ticketResponse()))
  })
  afterEach(() => {
    subscription?.unsubscribe()
    subscription = undefined
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it.each(['pending', 'failed'])('reconnects after 4410 even when bootstrap is %s, with increasing backoff', async (state) => {
    const gateway = new LocalHubGateway({ baseUrl: 'http://localhost:54321', token: 'synthetic' })
    const bootstrap = vi.spyOn(gateway, 'getBootstrap')
    if (state === 'pending') bootstrap.mockImplementation(() => new Promise(() => {}))
    else bootstrap.mockRejectedValue(new Error('snapshot unavailable'))
    subscription = gateway.subscribeEvents({}, vi.fn())
    await vi.advanceTimersByTimeAsync(0)
    let socket = Socket.instances[0]
    socket.onopen?.()
    socket.onmessage?.({ data: JSON.stringify({ seq: 99 }) })
    for (const delay of [1000, 1500, 2250]) {
      const count = Socket.instances.length
      socket.expire()
      await vi.advanceTimersByTimeAsync(delay - 1)
      expect(Socket.instances).toHaveLength(count)
      await vi.advanceTimersByTimeAsync(1)
      expect(Socket.instances).toHaveLength(count + 1)
      socket = Socket.instances[count]
      expect(socket.url).toContain('after=0')
      socket.onopen?.()
    }
    expect(bootstrap).toHaveBeenCalledTimes(3)
    socket.onmessage?.({ data: JSON.stringify({ seq: 100 }) })
    socket.expire()
    await vi.advanceTimersByTimeAsync(1000)
    expect(Socket.instances).toHaveLength(5)
    subscription.unsubscribe()
    await vi.advanceTimersByTimeAsync(60000)
    expect(Socket.instances).toHaveLength(5)
  })

  it.each([undefined, 80])('recovers an expired ticket cursor with latestSeq %s and refreshes bootstrap', async (latestSeq) => {
    const gateway = new LocalHubGateway({ baseUrl: 'http://localhost:54321', token: 'synthetic' })
    const bootstrap = vi.spyOn(gateway, 'getBootstrap').mockImplementation(() => new Promise(() => {}))
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false, status: 410,
      json: async () => ({ success: false, error: { code: 'EVENT_CURSOR_EXPIRED', message: 'expired', detail: { latestSeq } } }),
    } as Response)
    subscription = gateway.subscribeEvents({}, vi.fn(), vi.fn())
    await vi.advanceTimersByTimeAsync(0)
    expect(bootstrap).toHaveBeenCalledTimes(1)
    expect(Socket.instances).toHaveLength(0)
    await vi.advanceTimersByTimeAsync(1000)
    expect(Socket.instances).toHaveLength(1)
    expect(Socket.instances[0].url).toContain(`after=${latestSeq ?? 0}`)
  })
})
