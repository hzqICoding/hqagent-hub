import type {
  LocalAuthView,
  LocalAuthInput,
  AgentView,
  AgentDiscoveryResult,
  LocalAgentModelsView,
  WorkspaceView,
  AddWorkspaceInput,
  LocalSceneView,
  SaveLocalSceneInput,
  LocalConversationView,
  CreateLocalConversationInput,
  LocalMessageView,
  SendLocalMessageInput,
  LocalMessageReceipt,
  LocalRunView,
  TaskActionInput,
  LocalEventPage,
  ApprovalView,
  ApprovalResponseInput,
  SessionView,
} from '@hqagent/protocol'

export interface LocalChatGateway {
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

  // Scenes
  listLocalScenes(): Promise<LocalSceneView[]>
  saveLocalScene(sceneId: string, input: SaveLocalSceneInput): Promise<LocalSceneView>

  // Conversations & Messages
  listLocalConversations(): Promise<LocalConversationView[]>
  createLocalConversation(
    input: CreateLocalConversationInput,
    idempotencyKey?: string
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
    input: ApprovalResponseInput
  ): Promise<ApprovalView>
  listLocalSessions(): Promise<SessionView[]>
}
