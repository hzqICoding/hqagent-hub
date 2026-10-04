import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { File as NodeFile, Blob as NodeBlob } from 'node:buffer'
import { RemoteGateway } from '@/shared/api/remote-gateway'
import { RealLocalChatGateway } from '@/shared/api/local-chat-gateway'
import { encodedFileName } from './transport'

class FakeXhr {
  static last: FakeXhr
  headers: Record<string,string> = {}
  upload = { onprogress: null as ((event: ProgressEvent) => void) | null }
  method = ''; url = ''; body?: Blob; withCredentials = false; timeout = 0
  status = 201; responseText = ''
  onload?: () => void; onerror?: () => void; onabort?: () => void; ontimeout?: () => void
  constructor() { FakeXhr.last = this }
  open(method: string, url: string) { this.method = method; this.url = url }
  setRequestHeader(key: string, value: string) { this.headers[key] = value }
  getResponseHeader(key: string) { return key === 'X-Request-Id' ? 'req_upload_example' : null }
  send(body: Blob) { this.body = body }
  abort() { this.onabort?.() }
  respond(data: unknown, success = true) { this.responseText = JSON.stringify(success ? {success:true,data} : {success:false,error:data}); this.onload?.() }
}
beforeEach(() => { vi.stubGlobal('Blob', NodeBlob) })
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('attachment binary gateways', () => {
  it.each([true,false])('uploads a raw File with encoded name and without restricted headers (remote=%s)', async (remote) => {
    vi.stubGlobal('XMLHttpRequest', FakeXhr)
    const gateway = remote ? new RemoteGateway() : new RealLocalChatGateway()
    if (gateway instanceof RemoteGateway) gateway.setCsrfToken('synthetic_csrf')
    const file = new NodeFile(['synthetic'], '示例 文件.txt') as unknown as File
    const onProgress = vi.fn()
    const promise = gateway.uploadAttachment('conv/a',file,{fileName:file.name,sha256:'a'.repeat(64),idempotencyKey:'intent_1',onProgress})
    const xhr = FakeXhr.last
    expect(xhr.headers['X-HQ-Client-Features']).toBe('pi-v1')
    expect(xhr.method).toBe('POST'); expect(xhr.url).toBe('/api/v2/conversations/conv%2Fa/attachments')
    expect(xhr.body).toBe(file); expect(xhr.withCredentials).toBe(true)
    expect(xhr.headers['Content-Type']).toBe('application/octet-stream')
    expect(xhr.headers['X-File-Name']).toBe(encodeURIComponent(file.name))
    expect(xhr.headers['X-Content-Sha256']).toBe('a'.repeat(64))
    expect(xhr.headers['Idempotency-Key']).toBe('intent_1')
    expect(xhr.headers).not.toHaveProperty('Content-Length'); expect(xhr.headers).not.toHaveProperty('Authorization'); expect(xhr.headers).not.toHaveProperty('Origin')
    if (remote) expect(xhr.headers['X-CSRF-Token']).toBe('synthetic_csrf')
    xhr.upload.onprogress?.({lengthComputable:true,loaded:5,total:10} as ProgressEvent)
    expect(onProgress).toHaveBeenCalledWith(0.5)
    xhr.respond({attachment:{attachmentId:'example'}})
    await expect(promise).resolves.toMatchObject({attachment:{attachmentId:'example'}})
  })
  it('reports binary upload failures with requestId and supports cancellation', async () => {
    vi.stubGlobal('XMLHttpRequest', FakeXhr)
    const gateway = new RemoteGateway(); const file = new NodeFile(['x'],'x.txt') as unknown as File
    const result = gateway.uploadAttachment('c',file,{fileName:'x.txt',sha256:'a'.repeat(64),idempotencyKey:'k'})
    FakeXhr.last.status = 413; FakeXhr.last.respond({code:'ATTACHMENT_TOO_LARGE'},false)
    await expect(result).rejects.toMatchObject({code:'ATTACHMENT_TOO_LARGE',requestId:'req_upload_example'})
    const controller = new AbortController()
    const cancelled = gateway.uploadAttachment('c',file,{fileName:'x.txt',sha256:'a'.repeat(64),idempotencyKey:'k',signal:controller.signal})
    controller.abort(); await expect(cancelled).rejects.toMatchObject({name:'AbortError'})
  })
  it('reads binary endpoints with Cookie/no-store/no redirects and does not put names in URLs', async () => {
    const fetch = vi.fn(async () => new Response('example', { headers: {'Content-Type':'application/octet-stream','Content-Length':'7'} }))
    vi.stubGlobal('fetch',fetch)
    await new RemoteGateway().getAttachmentContent('id/a')
    await new RealLocalChatGateway().getAttachmentContent('local/a')
    const calls = fetch.mock.calls as unknown as [string,RequestInit][]
    expect(calls[0][0]).toBe('/api/v2/attachments/id%2Fa/content')
    for (const [url,init] of calls) { expect(url).not.toContain('?'); expect(init.cache).toBe('no-store'); expect(init.redirect).toBe('error'); expect(init.credentials).toBe('same-origin'); expect(new Headers(init.headers).has('Authorization')).toBe(false) }
  })
  it('rejects a truncated binary result and HTML masquerading as a PNG thumbnail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response('tiny',{headers:{'Content-Length':'40'}})).mockResolvedValueOnce(new Response('<svg/>',{headers:{'Content-Type':'image/png'}})))
    await expect(new RemoteGateway().getAttachmentContent('a')).rejects.toMatchObject({code:'ATTACHMENT_HASH_MISMATCH'})
    await expect(new RemoteGateway().getAttachmentThumbnail('a')).rejects.toMatchObject({code:'ATTACHMENT_THUMBNAIL_UNAVAILABLE'})
  })
  it('keeps binary errors structured and never turns error JSON into a preview', async () => {
    vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({success:false,error:{code:'ATTACHMENT_THUMBNAIL_UNAVAILABLE'},requestId:'req_body_example'}),{status:409,headers:{'X-Request-Id':'req_header_example'}})))
    await expect(new RealLocalChatGateway().getAttachmentThumbnail('a')).rejects.toMatchObject({code:'ATTACHMENT_THUMBNAIL_UNAVAILABLE',requestId:'req_header_example'})
  })
  it('queries local capabilities and deletes with Cookie idempotency and no credential URLs', async () => {
    const fetch = vi.fn(async()=>new Response(JSON.stringify({success:true,data:{}})))
    vi.stubGlobal('fetch',fetch)
    await new RealLocalChatGateway().getAttachmentCapabilities('conv/a')
    await new RealLocalChatGateway().deleteAttachment('attachment/a')
    const calls = fetch.mock.calls as unknown as [string,RequestInit][]
    expect(calls[0][0]).toBe('/api/v2/conversations/conv%2Fa/attachment-capabilities')
    expect(calls[1][1].method).toBe('DELETE')
    expect(new Headers(calls[1][1].headers).get('Idempotency-Key')).toBeTruthy()
  })
  it('normalizes upload names without directory fragments and caps encoded header length', () => {
    expect(decodeURIComponent(encodedFileName('C:\\secret\\a\r\n.txt'))).toBe('a.txt')
    expect(encodedFileName('中'.repeat(200)+'.txt').length).toBeLessThanOrEqual(512)
  })
})
