import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { invoke } from '@tauri-apps/api/core'
import { RealLocalChatGateway } from './local-chat-gateway'
import { LocalHubGateway } from './local-hub-gateway'
import { getDesktopEndpoint } from './desktop-endpoint'
import { getUiGateway } from './index'
import { getLocalChatGatewayMode, setLocalChatGatewayMode } from './local-chat-provider'

vi.mock('@tauri-apps/api/core', () => ({ invoke: vi.fn() }))
const mockedInvoke = vi.mocked(invoke)
const first = { baseUrl: 'http://127.0.0.1:45001', token: 'synthetic-first-token' }
const second = { baseUrl: 'http://127.0.0.1:45002', token: 'synthetic-second-token' }
const internals = window as unknown as Record<string, unknown>

beforeEach(() => { internals.__TAURI_INTERNALS__ = {}; mockedInvoke.mockReset(); mockedInvoke.mockResolvedValue(first) })
afterEach(() => { delete internals.__TAURI_INTERNALS__; vi.unstubAllGlobals(); vi.restoreAllMocks(); setLocalChatGatewayMode('real') })

describe('desktop gateway authentication', () => {
  it('refreshes v1 and v2 endpoints after restart, uses Bearer and never stores credentials', async () => {
    const localWrite = vi.spyOn(Storage.prototype, 'setItem')
    const fetch = vi.fn(async () => new Response(JSON.stringify({ success: true, data: { authenticated: true } })))
    vi.stubGlobal('fetch', fetch)
    const chat = new RealLocalChatGateway(), hub = new LocalHubGateway()
    await chat.getLocalAuthStatus()
    await hub.getBootstrap()
    mockedInvoke.mockResolvedValue(second)
    await chat.getLocalAuthStatus()
    await hub.getBootstrap()
    const calls = fetch.mock.calls as unknown as [string, RequestInit][]
    expect(calls.map(([url]) => url)).toEqual([
      `${first.baseUrl}/api/v2/auth/status`, `${first.baseUrl}/api/v1/bootstrap`,
      `${second.baseUrl}/api/v2/auth/status`, `${second.baseUrl}/api/v1/bootstrap`,
    ])
    calls.forEach(([, init], i) => {
      expect(new Headers(init.headers).get('Authorization')).toBe(`Bearer ${i < 2 ? first.token : second.token}`)
      expect(init.credentials).toBe('omit')
      expect(init.redirect).toBe('error')
    })
    expect(localWrite).not.toHaveBeenCalled()
    expect(mockedInvoke).toHaveBeenCalledWith('get_hub_endpoint')
  })

  it('browser v2 remains Cookie-based without invoking the shell', async () => {
    delete internals.__TAURI_INTERNALS__
    const fetch = vi.fn(async () => new Response(JSON.stringify({ success: true, data: {} })))
    vi.stubGlobal('fetch', fetch)
    await new RealLocalChatGateway().openLocalSession({ code: 'browser-code-example' })
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v2/auth/local-session')
    expect(init.credentials).toBe('include')
    expect(new Headers(init.headers).has('Authorization')).toBe(false)
    expect(mockedInvoke).not.toHaveBeenCalled()
  })

  it('coalesces concurrent endpoint reads and rejects non-loopback endpoints', async () => {
    await Promise.all([getDesktopEndpoint(), getDesktopEndpoint()])
    expect(mockedInvoke).toHaveBeenCalledTimes(1)
    mockedInvoke.mockResolvedValue({ ...first, baseUrl: 'https://example.com' })
    await expect(getDesktopEndpoint()).rejects.toThrow('桌面服务地址无效')
  })

  it('uses the frozen v1 Bearer maintenance API in desktop without changing browser Cookie routes', async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ success: true, data: {} })))
    vi.stubGlobal('fetch', fetch)
    const gateway = new RealLocalChatGateway()
    await gateway.listImageVerifications()
    await gateway.startImageVerification({ agentId: 'agent', expectedTargetRevision: 'revision', acknowledgeModelUsage: true }, 'start-key')
    await gateway.getImageVerificationJob('job')
    await gateway.cancelImageVerification('job', 'cancel-key')
    await gateway.deleteLocalConversation('conversation', 3, 'delete-key')
    const calls = fetch.mock.calls as unknown as [string, RequestInit][]
    expect(calls.map(([url]) => url.replace(first.baseUrl, '').split('?')[0])).toEqual([
      '/api/v1/agents/image-verifications', '/api/v1/agents/image-verification-jobs',
      '/api/v1/agents/image-verification-jobs/job', '/api/v1/agents/image-verification-jobs/job/cancellations',
      '/api/v1/conversations/conversation',
    ])
    for (const [, init] of calls) expect(new Headers(init.headers).get('Authorization')).toBe(`Bearer ${first.token}`)
    delete internals.__TAURI_INTERNALS__
    await gateway.listImageVerifications()
    expect((fetch.mock.calls[5] as unknown as [string])[0]).toMatch(/^\/api\/v2\/agents\/image-verifications/)
  })

  it('ignores saved Mock mode in the packaged shell', () => {
    setLocalChatGatewayMode('mock')
    expect(getLocalChatGatewayMode()).toBe('real')
    expect(getUiGateway()).toBeInstanceOf(LocalHubGateway)
  })

  it('sends Bearer on attachment uploads/downloads without cookies or token URLs', async () => {
    const headers: Record<string, string> = {}
    class FakeXhr {
      static last: FakeXhr
      upload = {}; withCredentials = true; timeout = 0; status = 200
      responseText = JSON.stringify({ success: true, data: {} })
      onload?: () => void
      constructor() { FakeXhr.last = this }
      open(_method: string, url: string) { expect(url).toBe(`${first.baseUrl}/api/v2/conversations/c/attachments`) }
      setRequestHeader(key: string, value: string) { headers[key] = value }
      send() { this.onload?.() }
      getResponseHeader() { return null }
    }
    vi.stubGlobal('XMLHttpRequest', FakeXhr)
    const fetch = vi.fn(async () => new Response('binary'))
    vi.stubGlobal('fetch', fetch)
    const gateway = new RealLocalChatGateway()
    await gateway.uploadAttachment('c', new Blob(['x']), { fileName: 'x.txt', sha256: 'a'.repeat(64), idempotencyKey: 'upload-key' })
    expect(headers.Authorization).toBe(`Bearer ${first.token}`)
    expect(FakeXhr.last.withCredentials).toBe(false)
    await gateway.getAttachmentContent('a')
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe(`${first.baseUrl}/api/v2/attachments/a/content`)
    expect(new Headers(init.headers).get('Authorization')).toBe(`Bearer ${first.token}`)
    expect(init.credentials).toBe('omit')
    await flushPromises()
  })
})
