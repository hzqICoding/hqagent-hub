import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { RemoteGateway } from '@/shared/api/remote-gateway'
import { lastRemoteFailureRequestId, remoteRequestFailure } from '@/shared/api/remote-diagnostics'
import { getRemoteErrorMessage } from '@/shared/i18n/remote-errors'
import RemoteRequestNotice from './RemoteRequestNotice.vue'

beforeEach(() => { remoteRequestFailure.value = null; lastRemoteFailureRequestId.value = null })
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('D50 Cookie gateway and diagnostics', () => {
  it('uses Cookie, CSRF and independent write keys for device/PAT management, never Authorization', async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ success: true, protocolVersion: '0.8.0', data: {} })))
    vi.stubGlobal('fetch', fetch)
    const gateway = new RemoteGateway()
    gateway.setCsrfToken('example_csrf')
    await gateway.listDevices(undefined, 50, { includeRevoked: true, remoteAccess: 'suspended', online: true })
    await gateway.patchDevice('worker/a', { expectedVersion: 4, displayName: '' })
    await gateway.deleteDevice('worker/a')
    await gateway.listApiTokens(undefined, 50, true)
    await gateway.issueApiToken({ name: '工具', scopes: ['devices:delete'] }, 'intent_example')
    await gateway.revokeApiToken('pat/a')
    const calls = fetch.mock.calls as unknown as [string, RequestInit][]
    expect(calls[0][0]).toContain('includeRevoked=true')
    expect(calls[0][0]).toContain('remoteAccess=suspended')
    expect(calls[1][0]).toContain('worker%2Fa')
    expect(calls[5][0]).toContain('pat%2Fa')
    for (const [, init] of calls) {
      expect(init.credentials).toBe('same-origin')
      const headers = new Headers(init.headers)
      expect(headers.has('Authorization')).toBe(false)
      if (init.method !== 'GET') {
        expect(headers.get('X-CSRF-Token')).toBe('example_csrf')
        expect(headers.get('Idempotency-Key')).toBeTruthy()
      }
    }
    expect(new Headers(calls[4][1].headers).get('Idempotency-Key')).toBe('intent_example')
  })

  it('retains only failed request IDs in memory, uses response header first, and permits copying', async () => {
    const gateway = new RemoteGateway()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ success: true, data: {}, requestId: 'req_success_12345678', protocolVersion: '0.8.0' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ success: false, error: { code: 'REMOTE_DEVICE_SUSPENDED' }, requestId: 'req_body_123456789' }), { status: 409, headers: { 'X-Request-Id': 'req_header_123456789' } })))
    await gateway.getDevice('worker')
    expect(remoteRequestFailure.value).toBeNull()
    expect(lastRemoteFailureRequestId.value).toBeNull()
    await expect(gateway.getDevice('worker')).rejects.toMatchObject({ requestId: 'req_header_123456789' })
    expect(lastRemoteFailureRequestId.value).toBe('req_header_123456789')
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const wrapper = mount(RemoteRequestNotice)
    expect(wrapper.text()).toContain('requestId: req_header_123456789')
    await wrapper.findAll('button').find((b) => b.text().includes('requestId:'))!.trigger('click')
    expect(writeText).toHaveBeenCalledWith('req_header_123456789')
    expect(JSON.stringify(localStorage)).not.toContain('req_header')
    wrapper.unmount()
  })

  it('falls back to envelope requestId and retains headers on non-JSON errors', async () => {
    const gateway = new RemoteGateway()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ success: false, error: { code: 'CONFLICT' }, requestId: 'req_fallback_123456' }), { status: 409 }))
      .mockResolvedValueOnce(new Response('Service unavailable', { status: 503, headers: { 'X-Request-Id': 'req_proxy_12345678' } })))
    await expect(gateway.getDevice('worker')).rejects.toMatchObject({ requestId: 'req_fallback_123456' })
    await expect(gateway.getDevice('worker')).rejects.toMatchObject({ requestId: 'req_proxy_12345678' })
  })

  it.each(['REMOTE_DEVICE_SUSPENDED', 'REMOTE_API_TOKEN_INVALID', 'REMOTE_API_TOKEN_EXPIRED', 'REMOTE_API_TOKEN_SCOPE_INSUFFICIENT', 'REMOTE_AUTH_AMBIGUOUS', 'CONFLICT'])('localizes %s', (code) => {
    expect(getRemoteErrorMessage(code)).toMatch(/[\u4e00-\u9fff]/)
    expect(getRemoteErrorMessage(code)).not.toBe('远程服务请求失败')
  })
})
