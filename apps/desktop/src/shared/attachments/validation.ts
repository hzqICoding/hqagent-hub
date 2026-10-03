import type { AttachmentLimits, ImageInputCapability, LocalAttachmentView, AttachmentTargetCapabilities, RemoteV5CatalogView, RemoteConversationView, MessageAttachmentView } from '@hqagent/protocol'
import { RemoteApiError } from '@/shared/api/remote-gateway'

export function attachmentFailure(code: ConstructorParameters<typeof RemoteApiError>[0]['code'], message: string): never {
  throw new RemoteApiError({ code, message, status: 422 })
}
export function formatBytes(bytes: number): string { return bytes < 1000 ? `${bytes} B` : bytes < 1000000 ? `${(bytes / 1000).toFixed(1)} KB` : `${(bytes / 1000000).toFixed(1)} MB` }
export async function selectedFileType(file: Blob & { name: string }, limits: AttachmentLimits): Promise<MessageAttachmentView['mimeType']> {
  const b = new Uint8Array(await file.slice(0,16).arrayBuffer())
  const ascii = String.fromCharCode(...b)
  const mime = b[0] === 255 && b[1] === 216 && b[2] === 255 ? 'image/jpeg'
    : b.slice(0,8).join(',') === '137,80,78,71,13,10,26,10' ? 'image/png'
    : /^GIF8[79]a/.test(ascii) ? 'image/gif'
    : ascii.startsWith('RIFF') && ascii.slice(8,12) === 'WEBP' ? 'image/webp' : null
  if (mime && limits.imageMimeTypes.includes(mime)) return mime
  if (!mime && limits.fileExtensions.includes(`.${file.name.split('.').at(-1)?.toLowerCase()}`)) return ascii.startsWith('%PDF-') ? 'application/pdf' : 'text/plain'
  if (!mime && ascii.startsWith('%PDF-') && limits.fileExtensions.includes('.pdf')) return 'application/pdf'
  return attachmentFailure('ATTACHMENT_TYPE_UNSUPPORTED', '不支持此附件类型，请按允许的类型选择文件')
}
export function validateFileSize(size: number, image: boolean, limits: AttachmentLimits) {
  if (!size) attachmentFailure('VALIDATION_FAILED', '不能上传空文件')
  if (size > (image ? limits.imageMaxBytes : limits.fileMaxBytes)) attachmentFailure('ATTACHMENT_TOO_LARGE', `附件超过${formatBytes(image ? limits.imageMaxBytes : limits.fileMaxBytes)}限制`)
}
function supports(capability: ImageInputCapability | undefined, image: LocalAttachmentView['attachment']): boolean {
  return Boolean(capability && capability.support === 'supported' && capability.cliEntry === 'supported' && capability.runtimeImplemented && capability.verified && capability.mimeTypes.some((mime) => mime === image.mimeType) && capability.maxBytes >= image.sizeBytes)
}
export function validateImageCapabilities(images: LocalAttachmentView['attachment'][], target?: AttachmentTargetCapabilities): void {
  if (!images.length) return
  const bindings = target?.conversationKind === 'native' ? [target.native] : target?.roles || []
  if (bindings.some(binding => binding?.agentType === 'pi' && (!binding.agentId || binding.transport !== 'pi-rpc-images-v1'))) attachmentFailure('AGENT_IMAGE_UNSUPPORTED', '当前 Agent 不支持图片')
  const capabilities = target?.conversationKind === 'native' ? [target.native?.imageInput] : target?.roles?.map((role) => role?.imageInput)
  if (!capabilities?.length || images.some((image) => capabilities.some((capability) => !supports(capability, image)))) attachmentFailure('AGENT_IMAGE_UNSUPPORTED', '当前 Agent 不支持图片')
}
// Remote native conversation metadata has no exact PI instance/model binding. Never pick the first PI capability.
export function remoteCapabilities(conversation: RemoteConversationView, catalog: RemoteV5CatalogView): AttachmentTargetCapabilities {
  if (conversation.conversationKind === 'native') return { conversationKind: 'native', capabilityRevision: catalog.capabilityRevision, roles: [], native: conversation.agentType === 'pi' ? undefined : catalog.nativeImageCapabilities?.find((entry) => entry.agentType === conversation.agentType) }
  const scene = catalog.scenes.find((entry) => entry.sceneId === conversation.sceneId && entry.version === conversation.sceneVersion)
  return { conversationKind: 'scenario', capabilityRevision: catalog.capabilityRevision, roles: (scene?.roleImageCapabilities || []).map(role => ({ ...role, agentType: role.agentType || catalog.runtimes?.find(runtime=>runtime.agentId===role.agentId)?.agentType })) }
}
