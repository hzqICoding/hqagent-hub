import { afterEach, describe, expect, it, vi } from 'vitest'
import { RemoteGateway } from '@/shared/api/remote-gateway'
import { RealLocalChatGateway } from '@/shared/api/local-chat-gateway'
import { getRemoteErrorMessage } from '@/shared/i18n/remote-errors'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })
describe('R3 gateway contracts', () => {
  it('uses Cookie-only remote R3 paths, token bodies, before cursors and no-store', async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ success: true, data: {}, protocolVersion: '0.9.1' })))
    vi.stubGlobal('fetch', fetch)
    const gateway = new RemoteGateway()
    gateway.setCsrfToken('example_csrf')
    await gateway.listNativeSessions('worker/a', 'index_cursor')
    await gateway.getNativeSession('native/a')
    await gateway.readNativeMessages('native/a', 'snapshot_before')
    await gateway.importNativeSession('native/a', { terminalClosedConfirmed: true, expectedIndexVersion: 4, sourceRevision: 'source_digest' }, 'import-intent')
    await gateway.listDirectory('worker/a', { rootId: 'root', rootVersion: 3, directoryToken: 'opaque_directory', cursor: 'directory_cursor' })
    await gateway.registerWorkspace('worker/a', { rootId: 'root', rootVersion: 3, directoryToken: 'opaque_directory', name: '合成项目' }, 'workspace-intent')
    const calls = fetch.mock.calls as unknown as [string, RequestInit][]
    expect(calls[0][0]).toContain('/devices/worker%2Fa/native-sessions?')
    expect(calls[2][0]).toContain('before=snapshot_before')
    expect(calls[2][0]).not.toContain('sourceRevision')
    expect(JSON.parse(calls[4][1].body as string)).toEqual({ rootId: 'root', rootVersion: 3, directoryToken: 'opaque_directory', cursor: 'directory_cursor' })
    for (const [url, init] of calls) {
      expect(init.cache).toBe('no-store'); expect(init.credentials).toBe('same-origin')
      expect(new Headers(init.headers).has('Authorization')).toBe(false)
      expect(url).not.toContain('opaque_directory'); expect(url).not.toContain('合成项目')
      if (init.method === 'POST') expect(new Headers(init.headers).get('X-CSRF-Token')).toBe('example_csrf')
    }
  })
  it('uses local Cookie endpoints, CAS and no-store independently of remote pairing', async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ success: true, data: {} })))
    vi.stubGlobal('fetch', fetch)
    const gateway = new RealLocalChatGateway()
    await gateway.listNativeSessions('cursor_example')
    await gateway.getNativeSession('native/local')
    await gateway.readNativeMessages('native/local', 'before_example')
    await gateway.importNativeSession('native/local', { terminalClosedConfirmed: true, expectedIndexVersion: 2, sourceRevision: 'revision' })
    await gateway.getAuthorizedRoots()
    await gateway.setAuthorizedRoots({ expectedVersion: 3, roots: [{ displayName: '授权项目', path: 'E:/SyntheticRoot' }] })
    const calls = fetch.mock.calls as unknown as [string, RequestInit][]
    expect(calls[0][0]).toContain('/api/v2/native-sessions?')
    expect(calls[2][0]).not.toContain('sourceRevision')
    expect(calls[3][0]).toContain('/native-sessions/native%2Flocal/imports')
    expect(calls[5][1].method).toBe('PUT')
    expect(JSON.parse(calls[5][1].body as string).expectedVersion).toBe(3)
    for (const [url, init] of calls) { expect(init.cache).toBe('no-store'); expect(init.credentials).toBe('include'); expect(url).not.toContain('SyntheticRoot') }
  })
  it('keeps local requestId from header in structured native errors', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ success: false, error: { code: 'NATIVE_SESSION_ACTIVE', message: '原生会话仍在使用', retryable: false }, requestId: 'req_body_example' }), { status: 409, headers: { 'X-Request-Id': 'req_header_example' } })))
    await expect(new RealLocalChatGateway().getNativeSession('n')).rejects.toMatchObject({ code: 'NATIVE_SESSION_ACTIVE', requestId: 'req_header_example' })
  })
  it.each(['REMOTE_QUERY_TIMEOUT','REMOTE_QUERY_TOO_LARGE','NATIVE_SESSION_ACTIVE','NATIVE_SESSION_UNSUPPORTED','NATIVE_SESSION_CHANGED','NATIVE_SESSION_WRITER_CONFLICT','REMOTE_ROOT_NOT_AUTHORIZED','REMOTE_PATH_OUTSIDE_ROOT','REMOTE_DIRECTORY_CHANGED'])('localizes %s', (code) => {
    expect(getRemoteErrorMessage(code)).not.toBe('远程服务请求失败')
    expect(getRemoteErrorMessage(code)).toMatch(/[\u4e00-\u9fff]/)
  })
})
