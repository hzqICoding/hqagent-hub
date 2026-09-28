import type {
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
  RemoteCatalogView,
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

export interface IRemoteGateway {
  // Session & Auth
  login(input: RemoteLoginInput, idempotencyKey?: string): Promise<RemoteAuthenticatedSession>
  getSession(): Promise<RemoteBrowserSessionView>
  logout(idempotencyKey?: string): Promise<RemoteAnonymousSession>

  // Pairing
  previewPairing(input: RemotePairingPreviewInput, idempotencyKey?: string): Promise<RemotePairingPreview>
  confirmPairing(pairRequestId: string, input: RemotePairingConfirmInput, idempotencyKey?: string): Promise<RemoteDeviceView>

  // Devices
  listDevices(cursor?: string, limit?: number): Promise<RemoteDevicePage>
  getDevice(workerId: string): Promise<RemoteDeviceView>
  revokeDevice(workerId: string, input: RemoteDeviceRevokeInput, idempotencyKey?: string): Promise<RemoteDeviceRevocationView>
  getWorkerCatalog(workerId: string): Promise<RemoteCatalogView>

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
