import type { LocalAttachmentView, RemoteAttachmentView, RemoteConversationView } from '@hqagent/protocol'
import { getLocalChatGateway, getRemoteGateway } from '@/shared/api'
import { attachmentFailure, validateFileSize, validateImageCapabilities, remoteCapabilities } from './validation'

export async function preflightAttachments(remote: boolean, conversationId: string, ids: string[], conversation?: RemoteConversationView): Promise<void> {
  if (!ids.length) return
  const gateway = remote ? getRemoteGateway() : getLocalChatGateway()
  const response = await gateway.getAttachmentLimits()
  const limits = 'limits' in response ? response.limits : response
  if (ids.length > limits.messageMaxCount || new Set(ids).size !== ids.length) attachmentFailure('ATTACHMENT_COUNT_EXCEEDED', '附件数量超过限制或重复')
  const records: (RemoteAttachmentView | LocalAttachmentView)[] = []
  // Serial reads avoid burst limits and keep memory bounded on phones.
  for (const id of ids) records.push(await gateway.getAttachment(id))
  for (const record of records) {
    if (record.conversationId !== conversationId) attachmentFailure('NOT_FOUND', '附件不属于当前对话，请重新选择')
    if ('availability' in record.attachment && record.attachment.availability !== 'available') attachmentFailure('ATTACHMENT_NOT_READY', '附件尚不可用，请重新选择或等待上传')
    if (record.state === 'uploaded' && record.expiresAt && Date.parse(record.expiresAt) <= Date.now()) attachmentFailure('NOT_FOUND', '未发送附件已清理，请重新选择文件')
    validateFileSize(record.attachment.sizeBytes, record.attachment.kind === 'image', limits)
  }
  const images = records.map((record) => record.attachment).filter((item) => item.kind === 'image')
  if (!images.length) return
  if (remote) {
    if (!conversation) attachmentFailure('NOT_FOUND','当前对话不存在')
    const catalog = await getRemoteGateway().getWorkerCatalog(conversation.targetWorkerId)
    if (catalog.workerId !== conversation.targetWorkerId || catalog.workerStoreId !== conversation.workerStoreId) attachmentFailure('REMOTE_STORE_CHANGED','电脑存储已变化，请刷新')
    validateImageCapabilities(images, remoteCapabilities(conversation, catalog))
  } else validateImageCapabilities(images, await getLocalChatGateway().getAttachmentCapabilities(conversationId))
}
