import type {
  BootstrapView,
  WorkspaceView,
  WorkspaceQuery,
  AgentView,
  AgentDiscoveryResult,
  TeamProfileView,
  SaveTeamProfileInput,
  ResolveTeamProfileInput,
  ResolvedTeamView,
  TaskSummaryView,
  TaskDetailView,
  TaskQuery,
  CreateTaskInput,
  TaskActionInput,
  SessionView,
  SessionQuery,
  ResumeSessionInput,
  ApprovalView,
  ApprovalQuery,
  ApprovalResponseInput,
  UserSettingsView,
  AppearanceSettings,
  UpdateStateView,
  UpdateActionInput,
  SubscribeEventsInput,
  HubEvent,
  PageResult,
} from '@hqagent/protocol'

export interface EventSubscription {
  unsubscribe: () => void
}

export interface UiGateway {
  getBootstrap(): Promise<BootstrapView>

  listWorkspaces(query?: WorkspaceQuery): Promise<WorkspaceView[]>
  listAgents(): Promise<AgentView[]>
  refreshAgents(): Promise<AgentDiscoveryResult>

  listTeamProfiles(): Promise<TeamProfileView[]>
  getTeamProfile(id: string): Promise<TeamProfileView>
  saveTeamProfile(input: SaveTeamProfileInput): Promise<TeamProfileView>
  resolveTeamProfile(input: ResolveTeamProfileInput): Promise<ResolvedTeamView>

  listTasks(query: TaskQuery): Promise<PageResult<TaskSummaryView>>
  getTask(id: string): Promise<TaskDetailView>
  createTask(input: CreateTaskInput): Promise<TaskDetailView>
  controlTask(id: string, action: TaskActionInput): Promise<TaskDetailView>

  listSessions(query: SessionQuery): Promise<PageResult<SessionView>>
  resumeSession(id: string, input?: ResumeSessionInput): Promise<TaskDetailView>

  listApprovals(query?: ApprovalQuery): Promise<ApprovalView[]>
  respondApproval(id: string, input: ApprovalResponseInput): Promise<ApprovalView>

  getSettings(): Promise<UserSettingsView>
  updateAppearance(input: AppearanceSettings): Promise<AppearanceSettings>

  getUpdateState(): Promise<UpdateStateView>
  controlUpdate(action: UpdateActionInput): Promise<UpdateStateView>

  subscribeEvents(
    input: SubscribeEventsInput,
    onEvent: (event: HubEvent) => void,
    onError?: (err: unknown) => void
  ): EventSubscription
}
