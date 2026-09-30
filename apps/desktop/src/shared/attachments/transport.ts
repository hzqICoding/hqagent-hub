import type { ApiEnvelope, ErrorCode } from '@hqagent/protocol'
import { getRemoteErrorMessage } from '@/shared/i18n/remote-errors'

// Internal transport options, not a protocol DTO. Binary payloads are never logged/cached.
export interface UploadOptions {
  sha256: string
  fileName: string
  idempotencyKey: string
  signal?: AbortSignal
  onProgress?: (fraction: number) => void
}
export type AttachmentErrorFactory = (code: ErrorCode, status: number, requestId?: string) => Error
export function encodedFileName(name: string): string {
  const basename = Array.from(name.normalize('NFC').split(/[\\/]/).at(-1)!).filter((c) => c.charCodeAt(0) >= 32 && c.charCodeAt(0) !== 127 && c !== ':').join('') || 'attachment'
  const chars = Array.from(basename).slice(0,120)
  while (encodeURIComponent(chars.join('')).length > 512) chars.pop()
  return encodeURIComponent(chars.join('') || 'attachment')
}
export function uploadAttachment<T>(url: string, file: Blob, options: UploadOptions, csrf: string | null, error: AttachmentErrorFactory): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const abort = () => xhr.abort()
    let idle: ReturnType<typeof setTimeout> | undefined
    let idleExpired = false
    const cleanup = () => { clearTimeout(idle); options.signal?.removeEventListener('abort', abort) }
    const resetIdle = () => { clearTimeout(idle); idle = setTimeout(() => { idleExpired = true; xhr.abort() }, 30000) }
    xhr.open('POST', url)
    xhr.withCredentials = true
    xhr.timeout = 120000
    xhr.setRequestHeader('Content-Type','application/octet-stream')
    xhr.setRequestHeader('X-File-Name',encodedFileName(options.fileName))
    xhr.setRequestHeader('X-Content-Sha256',options.sha256)
    xhr.setRequestHeader('Idempotency-Key',options.idempotencyKey)
    if (csrf) xhr.setRequestHeader('X-CSRF-Token',csrf)
    // Content-Length and Origin belong to the browser. Never set them here.
    xhr.upload.onprogress = (event) => { resetIdle(); if (event.lengthComputable) options.onProgress?.(event.loaded / event.total) }
    xhr.onload = () => {
      cleanup()
      let envelope: ApiEnvelope<T> | undefined
      try { envelope = JSON.parse(xhr.responseText) as ApiEnvelope<T> } catch { /* Non-JSON errors have no content retained. */ }
      if (xhr.status >= 200 && xhr.status < 300 && envelope?.success) resolve(envelope.data as T)
      else reject(error(envelope?.error?.code || (xhr.status === 413 ? 'ATTACHMENT_TOO_LARGE' : xhr.status === 429 ? 'REMOTE_RATE_LIMITED' : 'INTERNAL'), xhr.status, xhr.getResponseHeader('X-Request-Id') || envelope?.requestId))
    }
    xhr.onerror = () => { cleanup(); reject(new Error('附件上传连接中断，请重试')) }
    xhr.ontimeout = () => { cleanup(); reject(new Error('附件上传超时，请重试')) }
    xhr.onabort = () => { cleanup(); reject(idleExpired ? new Error('附件上传长时间没有进展，请重试') : new DOMException('已取消', 'AbortError')) }
    options.signal?.addEventListener('abort',abort,{once:true})
    if (options.signal?.aborted) { cleanup(); reject(new DOMException('已取消','AbortError')); return }
    resetIdle()
    xhr.send(file)
  })
}
export async function attachmentBlob(url: string, thumbnail: boolean, signal: AbortSignal | undefined, error: AttachmentErrorFactory): Promise<Blob> {
  const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal })
  if (!response.ok) {
    let envelope: ApiEnvelope<never> | undefined
    try { envelope = await response.json() } catch { /* Do not retain binary/error body. */ }
    throw error(envelope?.error?.code || (response.status === 429 ? 'REMOTE_RATE_LIMITED' : 'ATTACHMENT_DOWNLOAD_FAILED'), response.status, response.headers.get('X-Request-Id') || envelope?.requestId)
  }
  const blob = await response.blob()
  const length = response.headers.get('Content-Length')
  if (length && blob.size !== Number(length)) throw error('ATTACHMENT_HASH_MISMATCH',502,response.headers.get('X-Request-Id') || undefined)
  if (thumbnail) {
    const signature = new Uint8Array(await blob.slice(0,8).arrayBuffer())
    if (response.headers.get('Content-Type')?.split(';')[0] !== 'image/png' || signature.join(',') !== '137,80,78,71,13,10,26,10') throw error('ATTACHMENT_THUMBNAIL_UNAVAILABLE',409)
  }
  return thumbnail ? blob : new Blob([blob], { type: 'application/octet-stream' })
}
export function attachmentErrorText(err: unknown): string {
  const value = err as { code?: string; requestId?: string }
  const text = value?.code ? getRemoteErrorMessage(value.code) : err instanceof Error ? err.message : '附件操作失败，请重试'
  return value?.requestId ? `${text}（requestId: ${value.requestId}）` : text
}
