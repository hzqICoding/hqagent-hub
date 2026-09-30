import type { AttachmentLimits, AttachmentTargetCapabilities, LocalAttachmentView, RemoteAttachmentView, MessageAttachmentView } from '@hqagent/protocol'
import limitsFixture from '@hqagent/fixtures/r16.AttachmentLimits.json'
import capabilityFixture from '@hqagent/fixtures/r16.AttachmentTargetCapabilities.json'
import { selectedFileType } from './validation'
import type { UploadOptions } from './transport'

// In-memory only, synthetic UI scenarios. Real backend remains the authority.
export class MockAttachmentLibrary {
  limits = structuredClone(limitsFixture) as AttachmentLimits
  capabilities = structuredClone(capabilityFixture) as AttachmentTargetCapabilities
  records = new Map<string, { local: LocalAttachmentView; remote: RemoteAttachmentView; blob: Blob }>()
  reset() { this.records.clear() }
  async upload(conversationId: string, blob: Blob, options: UploadOptions) {
    if (options.signal?.aborted) throw new DOMException('已取消','AbortError')
    const existing = this.records.get(options.idempotencyKey)
    if (existing) return existing
    const mimeType = await selectedFileType(Object.assign(blob.slice(), { name: options.fileName }), this.limits)
    const attachment: MessageAttachmentView = { attachmentId: options.idempotencyKey, fileName: options.fileName, kind: mimeType.startsWith('image/') ? 'image' : 'file', mimeType, sizeBytes: blob.size, sha256: options.sha256, availability: 'available', thumbnailStatus: mimeType.startsWith('image/') ? 'pending' : 'not_applicable' }
    const base = { conversationId, state: 'uploaded' as const, createdAt: new Date().toISOString(), expiresAt: new Date(Date.now() + this.limits.unattachedTtlSeconds * 1000).toISOString() }
    const { availability: _availability, thumbnailStatus: _thumbnailStatus, ...manifest } = attachment
    const record = { local: { ...base, attachment: manifest, syncStatus: 'not_synced' as const }, remote: { ...base, attachment }, blob }
    this.records.set(attachment.attachmentId, record)
    options.onProgress?.(1)
    return record
  }
  get(id: string) {
    const record = this.records.get(id)
    if (!record) throw Object.assign(new Error('附件不存在或已清理'), { code: 'NOT_FOUND', status: 404 })
    return record
  }
  remove(id: string) {
    const record = this.get(id)
    if (record.local.state !== 'uploaded' || record.remote.state !== 'uploaded') throw Object.assign(new Error('附件已被消息引用'), { code: 'ATTACHMENT_IN_USE', status: 409 })
    this.records.delete(id)
    return { attachmentId: id, deleted: true as const }
  }
  thumbnail(id: string) {
    const record = this.get(id)
    if (record.remote.attachment.thumbnailStatus !== 'ready') throw Object.assign(new Error('缩略图不可用'), { code: 'ATTACHMENT_THUMBNAIL_UNAVAILABLE', status: 409 })
    // A fixed synthetic 1px PNG representing a server product; never the uploaded original.
    const bytes = Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9l8AAAAASUVORK5CYII='), (c) => c.charCodeAt(0))
    return new Blob([bytes], { type: 'image/png' })
  }
}
