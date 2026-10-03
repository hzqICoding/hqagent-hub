import type { UploadOptions } from '@/shared/attachments/transport'
import type {
  LocalImageVerificationPage, LocalImageVerificationJobView, StartLocalImageVerificationInput, LocalConversationDeletionView,
  AttachmentLimits, AttachmentDeletedView, LocalAttachmentView, AttachmentTargetCapabilities,
  LocalNativeSessionPage, NativeSessionIndex, NativeMessagePage, RemoteNativeImportInput, LocalAuthorizedRootsView, LocalAuthorizedRootsInput,
  LocalAuthView,
  LocalAuthInput,
  AgentView,
  AgentDiscoveryResult,
  LocalAgentModelsView,
  WorkspaceView,
  AddWorkspaceInput,
  PickLocalDirectoryInput,
  PickLocalDirectoryView,
  LocalSceneView,
  CreateLocalSceneInput,
  SaveLocalSceneInput,
  LocalRoleTemplateView,
  CreateLocalRoleTemplateInput,
  UpdateLocalRoleTemplateInput,
  LocalConversationView,
  CreateLocalConversationInput,
  UpdateLocalConversationInput,
  LocalMessageView,
  SendLocalMessageInput,
  LocalMessageReceipt,
  LocalRunView,
  TaskActionInput,
  LocalEventPage,
  ApprovalView,
  ApprovalResponseInput,
  SessionView,
  RemoteLinkView,
  RemoteLinkPairingInput,
  RemoteSyncSettingsView,
  RemoteSyncSettingsInput,
} from '@hqagent/protocol'

export interface LocalChatGateway {
  listImageVerifications(options?: { includeInactiveModels?: boolean; cursor?: string }): Promise<LocalImageVerificationPage>
  startImageVerification(input: StartLocalImageVerificationInput, key: string): Promise<LocalImageVerificationJobView>
  getImageVerificationJob(jobId: string): Promise<LocalImageVerificationJobView>
  cancelImageVerification(jobId: string, key: string): Promise<LocalImageVerificationJobView>
  deleteLocalConversation(id: string, expectedVersion: number, key: string): Promise<LocalConversationDeletionView>
  getAttachmentLimits(): Promise<AttachmentLimits>
  uploadAttachment(conversationId: string, file: Blob, options: UploadOptions): Promise<LocalAttachmentView>
  getAttachment(id: string): Promise<LocalAttachmentView>
  deleteAttachment(id: string): Promise<AttachmentDeletedView>
  getAttachmentContent(id: string, signal?: AbortSignal): Promise<Blob>
  getAttachmentThumbnail(id: string, signal?: AbortSignal): Promise<Blob>
  getAttachmentCapabilities(conversationId: string): Promise<AttachmentTargetCapabilities>

  listNativeSessions(cursor?: string): Promise<LocalNativeSessionPage>
  getNativeSession(id: string): Promise<NativeSessionIndex>
  readNativeMessages(id: string, before?: string): Promise<NativeMessagePage>
  importNativeSession(id: string, input: RemoteNativeImportInput, key?: string): Promise<LocalConversationView>
  getAuthorizedRoots(): Promise<LocalAuthorizedRootsView>
  setAuthorizedRoots(input: LocalAuthorizedRootsInput): Promise<LocalAuthorizedRootsView>
  // Remote Link (D44) & Sync Settings (R1.5)
  getRemoteLink(): Promise<RemoteLinkView>
  startRemotePairing(
    input: RemoteLinkPairingInput,
    idempotencyKey?: string
  ): Promise<RemoteLinkView>
  cancelRemotePairing(idempotencyKey?: string): Promise<RemoteLinkView>
  unlinkRemote(idempotencyKey?: string): Promise<RemoteLinkView>
  getRemoteSyncSettings(): Promise<RemoteSyncSettingsView>
  setRemoteSyncSettings(
    input: RemoteSyncSettingsInput,
    idempotencyKey?: string
  ): Promise<RemoteSyncSettingsView>

  // Auth
  getLocalAuthStatus(): Promise<LocalAuthView>
  openLocalSession(input: LocalAuthInput): Promise<LocalAuthView>
  logoutLocalSession(): Promise<LocalAuthView>

  // Agents & Models
  listLocalAgents(): Promise<AgentView[]>
  discoverLocalAgents(): Promise<AgentDiscoveryResult>
  getAgentModels(agentId: string): Promise<LocalAgentModelsView>

  // Workspaces
  listLocalWorkspaces(): Promise<WorkspaceView[]>
  addLocalWorkspace(input: AddWorkspaceInput): Promise<WorkspaceView>
  pickLocalDirectory(input: PickLocalDirectoryInput): Promise<PickLocalDirectoryView>

  // Scenes
  listLocalScenes(): Promise<LocalSceneView[]>
  createLocalScene(
    input: CreateLocalSceneInput,
    idempotencyKey: string
  ): Promise<LocalSceneView>
  saveLocalScene(sceneId: string, input: SaveLocalSceneInput): Promise<LocalSceneView>
  listLocalRoleTemplates(): Promise<LocalRoleTemplateView[]>
  createLocalRoleTemplate(
    input: CreateLocalRoleTemplateInput,
    idempotencyKey: string
  ): Promise<LocalRoleTemplateView>
  updateLocalRoleTemplate(
    templateId: string,
    input: UpdateLocalRoleTemplateInput,
    idempotencyKey: string
  ): Promise<LocalRoleTemplateView>

  // Conversations & Messages
  listLocalConversations(params?: {
    includeHidden?: boolean
    workspaceId?: string
  }): Promise<LocalConversationView[]>
  createLocalConversation(
    input: CreateLocalConversationInput,
    idempotencyKey?: string
  ): Promise<LocalConversationView>
  updateLocalConversation(
    conversationId: string,
    input: UpdateLocalConversationInput,
    idempotencyKey: string
  ): Promise<LocalConversationView>
  listLocalMessages(
    conversationId: string,
    after?: number,
    limit?: number
  ): Promise<LocalMessageView[]>
  sendLocalMessage(
    conversationId: string,
    input: SendLocalMessageInput,
    idempotencyKey?: string
  ): Promise<LocalMessageReceipt>

  // Runs
  listConversationRuns(conversationId: string): Promise<LocalRunView[]>
  getLocalRun(runId: string): Promise<LocalRunView>
  controlLocalRun(
    runId: string,
    input: TaskActionInput,
    idempotencyKey?: string
  ): Promise<LocalRunView>

  // Events
  listLocalEvents(after?: number, limit?: number): Promise<LocalEventPage>

  // Approvals & Sessions
  listLocalApprovals(): Promise<ApprovalView[]>
  decideLocalApproval(
    approvalId: string,
    input: ApprovalResponseInput,
    idempotencyKey?: string
  ): Promise<ApprovalView>
  listLocalSessions(): Promise<SessionView[]>
}
