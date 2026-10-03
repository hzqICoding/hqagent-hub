import type { UploadOptions } from '@/shared/attachments/transport'
import type {
  AttachmentDeletedView, RemoteAttachmentView, RemoteAttachmentLimitsView,
  RemoteNativeSessionPage, RemoteNativeSessionView, NativeMessagePage, RemoteNativeImportInput, RemoteResourceQueuedReceipt, DirectoryListingInput, DirectoryListingPage, RemoteWorkspaceRegisterInput, RemoteV5CatalogView,
  RemoteDevicePatchInput,
  RemoteDeviceDeletionView,
  RemoteApiTokenCreateInput,
  RemoteApiTokenPage,
  RemoteApiTokenIssuedView,
  RemoteApiTokenIssueReplayView,
  RemoteApiTokenRevocationView,
  RemoteLoginInput,
  RemoteAuthenticatedSession,
  RemoteBrowserSessionView,
  RemoteAnonymousSession,
  RemotePairingPreviewInput,
  RemotePairingPreview,
  RemotePairingConfirmInput,
  RemoteDeviceView,
  RemoteDevicePage,
  RemoteDeviceRevokeInput,
  RemoteDeviceRevocationView,
  RemoteConversationPage,
  RemoteCreateConversationInput,
  RemoteConversationView,
  RemoteQueuedReceipt,
  RemoteSendMessageInput,
  RemoteSyncConversationInput,
  RemoteSyncMessagePage,
  RemoteRunPage,
  RemoteRunView,
  RemoteRunControlInput,
  RemoteCommandPage,
  RemoteCommandView,
  RemoteCommandWithdrawalInput,
  RemoteApprovalView,
  RemoteApprovalDecisionInput,
  RemoteBrowserEventPage,
  RemoteConversationSnapshot,
} from '@hqagent/protocol'

export type RemoteDeviceFilters = Pick<RemoteDeviceView, 'remoteAccess' | 'online'> & { includeRevoked?: boolean }

export interface IRemoteGateway {
  getAttachmentLimits(): Promise<RemoteAttachmentLimitsView>
  uploadAttachment(conversationId: string, file: Blob, options: UploadOptions): Promise<RemoteAttachmentView>
  getAttachment(id: string): Promise<RemoteAttachmentView>
  deleteAttachment(id: string): Promise<AttachmentDeletedView>
  getAttachmentContent(id: string, signal?: AbortSignal): Promise<Blob>
  getAttachmentThumbnail(id: string, signal?: AbortSignal): Promise<Blob>

  listNativeSessions(workerId: string, cursor?: string): Promise<RemoteNativeSessionPage>
  getNativeSession(id: string): Promise<RemoteNativeSessionView>
  readNativeMessages(id: string, before?: string): Promise<NativeMessagePage>
  importNativeSession(id: string, input: RemoteNativeImportInput, key?: string): Promise<RemoteResourceQueuedReceipt>
  listDirectory(workerId: string, input: DirectoryListingInput): Promise<DirectoryListingPage>
  registerWorkspace(workerId: string, input: RemoteWorkspaceRegisterInput, key?: string): Promise<RemoteResourceQueuedReceipt>
  readonly supportsDeviceManagement: boolean
  patchDevice(workerId: string, input: RemoteDevicePatchInput, idempotencyKey?: string): Promise<RemoteDeviceView>
  deleteDevice(workerId: string, idempotencyKey?: string): Promise<RemoteDeviceDeletionView>
  listApiTokens(cursor?: string, limit?: number, includeRevoked?: boolean): Promise<RemoteApiTokenPage>
  issueApiToken(input: RemoteApiTokenCreateInput, idempotencyKey?: string): Promise<RemoteApiTokenIssuedView | RemoteApiTokenIssueReplayView>
  revokeApiToken(tokenId: string, idempotencyKey?: string): Promise<RemoteApiTokenRevocationView>
  // Session & Auth
  login(input: RemoteLoginInput, idempotencyKey?: string): Promise<RemoteAuthenticatedSession>
  getSession(): Promise<RemoteBrowserSessionView>
  logout(idempotencyKey?: string): Promise<RemoteAnonymousSession>

  // Pairing
  previewPairing(input: RemotePairingPreviewInput, idempotencyKey?: string): Promise<RemotePairingPreview>
  confirmPairing(pairRequestId: string, input: RemotePairingConfirmInput, idempotencyKey?: string): Promise<RemoteDeviceView>

  // Devices
  listDevices(cursor?: string, limit?: number, filters?: RemoteDeviceFilters): Promise<RemoteDevicePage>
  getDevice(workerId: string): Promise<RemoteDeviceView>
  revokeDevice(workerId: string, input: RemoteDeviceRevokeInput, idempotencyKey?: string): Promise<RemoteDeviceRevocationView>
  getWorkerCatalog(workerId: string): Promise<RemoteV5CatalogView>

  // Conversations
  listConversations(params?: {
    workerId?: string
    workspaceId?: string
    cursor?: string
    limit?: number
  }): Promise<RemoteConversationPage>
  createConversation(input: RemoteCreateConversationInput, idempotencyKey?: string): Promise<RemoteQueuedReceipt>
  updateConversation(
    conversationId: string,
    input: RemoteSyncConversationInput,
    idempotencyKey?: string
  ): Promise<RemoteQueuedReceipt>
  getConversation(conversationId: string): Promise<RemoteConversationView>
  getConversationSnapshot(conversationId: string): Promise<RemoteConversationSnapshot>

  // Messages
  sendMessage(conversationId: string, input: RemoteSendMessageInput, idempotencyKey?: string): Promise<RemoteQueuedReceipt>
  listMessages(conversationId: string, before?: string, limit?: number): Promise<RemoteSyncMessagePage>

  // Runs & Controls
  listRuns(conversationId: string, cursor?: string, limit?: number): Promise<RemoteRunPage>
  getRun(runId: string): Promise<RemoteRunView>
  controlRun(runId: string, input: RemoteRunControlInput, idempotencyKey?: string): Promise<RemoteQueuedReceipt>

  // Commands
  listCommands(conversationId: string, cursor?: string, limit?: number): Promise<RemoteCommandPage>
  getCommand(commandId: string): Promise<RemoteCommandView>
  withdrawCommand(commandId: string, input: RemoteCommandWithdrawalInput, idempotencyKey?: string): Promise<RemoteCommandView>

  // Approvals
  getApproval(approvalId: string): Promise<RemoteApprovalView>
  decideApproval(approvalId: string, input: RemoteApprovalDecisionInput, idempotencyKey?: string): Promise<RemoteQueuedReceipt>

  // Events
  listEvents(after?: string, limit?: number): Promise<RemoteBrowserEventPage>
}
