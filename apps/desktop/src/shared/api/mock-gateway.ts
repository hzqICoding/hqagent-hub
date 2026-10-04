import { piAgents } from '@/shared/runtime/pi-examples'
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

import type { UiGateway, EventSubscription } from './ui-gateway'
import { scenarios, type MockScenarioId } from '@/mocks/scenarios'

export type MockScenario = MockScenarioId

export class MockGateway implements UiGateway {
  private currentScenario: MockScenario = 'happy-path'
  private delayMs = 60
  private shouldFail = false
  private eventListeners: Set<(event: HubEvent) => void> = new Set()
  private currentSeq = 100
  public connectionCount = 0
  public ticketRequestCount = 0
  public isConnected = false
  private connectPromise: Promise<void> | null = null
  private historicalEvents: HubEvent[] = []
  private closeListeners: Set<(code: number) => void> = new Set()

  constructor(initialScenario: MockScenario = 'happy-path') {
    this.currentScenario = initialScenario
  }

  public setScenario(scenario: MockScenario) {
    this.currentScenario = scenario
  }

  public getScenario(): MockScenario {
    return this.currentScenario
  }

  public setDelay(ms: number) {
    this.delayMs = ms
  }

  public setShouldFail(fail: boolean) {
    this.shouldFail = fail
  }

  private async wait() {
    if (this.currentScenario === 'hub-disconnected') {
      throw new Error('ERR_HUB_DISCONNECTED: Failed to connect to Local Hub at 127.0.0.1:49210')
    }
    if (this.shouldFail) {
      throw new Error('ERR_MOCK_FAILURE: Simulated gateway failure')
    }
    if (this.delayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, this.delayMs))
    }
  }

  private getScenarioDef() {
    return scenarios[this.currentScenario] || scenarios['happy-path']
  }

  async getBootstrap(): Promise<BootstrapView> {
    await this.wait()
    return this.getScenarioDef().getBootstrap()
  }

  async listWorkspaces(_query?: WorkspaceQuery): Promise<WorkspaceView[]> {
    await this.wait()
    return this.getScenarioDef().getWorkspaces()
  }

  async listAgents(): Promise<AgentView[]> {
    await this.wait()
    const agents=this.getScenarioDef().getAgents()
    return agents.length ? [...agents,...piAgents()] : agents
  }

  async refreshAgents(): Promise<AgentDiscoveryResult> {
    await this.wait()
    const result=this.getScenarioDef().getDiscovery()
    return result.discovered.length ? {...result,discovered:[...result.discovered,...piAgents()],total:result.total+piAgents().length} : result
  }

  async listTeamProfiles(): Promise<TeamProfileView[]> {
    await this.wait()
    return this.getScenarioDef().getTeamProfiles()
  }

  async getTeamProfile(id: string): Promise<TeamProfileView> {
    const list = await this.listTeamProfiles()
    const found = list.find((p) => p.id === id)
    if (!found) throw new Error(`NOT_FOUND: Team profile ${id} not found`)
    return found
  }

  async saveTeamProfile(input: SaveTeamProfileInput): Promise<TeamProfileView> {
    await this.wait()
    return {
      id: input.id || 'profile_' + Math.random().toString(36).substring(2, 7),
      name: input.name,
      description: input.description,
      scope: input.scope,
      workspaceId: input.workspaceId,
      isDefault: Boolean(input.isDefault),
      roleBindings: input.roleBindings,
      updatedAt: new Date().toISOString(),
    }
  }

  async resolveTeamProfile(input: ResolveTeamProfileInput): Promise<ResolvedTeamView> {
    await this.wait()
    return {
      profileId: input.profileId,
      hasGaps: false,
      resolvedRoles: {
        architect: {
          roleId: 'architect',
          resolvedAgentId: 'agent_claude_default',
          resolvedAgentName: 'Claude Code',
          resolveSource: 'global_profile',
          isFallback: false,
        },
        frontend_implementer: {
          roleId: 'frontend_implementer',
          resolvedAgentId: 'agent_codex_default',
          resolvedAgentName: 'Codex App Server',
          resolveSource: 'fallback',
          isFallback: true,
          fallbackReason: '首选 Antigravity 离线/未登录，已命中备用 Codex',
        },
        reviewer: {
          roleId: 'reviewer',
          resolvedAgentId: 'agent_claude_default',
          resolvedAgentName: 'Claude Code',
          resolveSource: 'global_profile',
          isFallback: false,
        },
      },
      gaps: [],
    }
  }

  async listTasks(_query: TaskQuery): Promise<PageResult<TaskSummaryView>> {
    await this.wait()
    const items = this.getScenarioDef().getTasks()
    return {
      items,
      total: items.length,
      page: 1,
      pageSize: 10,
      hasMore: false,
    }
  }

  async getTask(id: string): Promise<TaskDetailView> {
    await this.wait()
    return this.getScenarioDef().getTaskDetail(id)
  }

  async createTask(input: CreateTaskInput): Promise<TaskDetailView> {
    await this.wait()
    const newTask: TaskDetailView = {
      id: 'task_' + Date.now(),
      objective: input.objective,
      workspaceId: input.workspaceId,
      workspaceName: 'HQAgent-Hub',
      profileId: input.profileId || 'profile_hq_default',
      profileName: 'HQ默认双Agent团队',
      status: 'queued',
      source: input.source || 'desktop',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      nodes: [],
      artifacts: [],
      events: [],
    }
    return newTask
  }

  async controlTask(id: string, action: TaskActionInput): Promise<TaskDetailView> {
    await this.wait()
    const task = await this.getTask(id)
    if (action.action === 'pause') task.status = 'paused'
    else if (action.action === 'resume') task.status = 'running'
    else if (action.action === 'cancel') task.status = 'cancelled'
    else if (action.action === 'retry') task.status = 'running'
    return task
  }

  async listSessions(_query: SessionQuery): Promise<PageResult<SessionView>> {
    await this.wait()
    const items = this.getScenarioDef().getSessions()
    return {
      items,
      total: items.length,
      page: 1,
      pageSize: 10,
      hasMore: false,
    }
  }

  async resumeSession(id: string, _input?: ResumeSessionInput): Promise<TaskDetailView> {
    await this.wait()
    const base = this.getScenarioDef().getTasks()[0] || (await this.getTask('task_20260905_001'))
    const detail = await this.getTask(base.id)
    return {
      ...detail,
      id: 'task_resumed_' + id,
      objective: `[恢复会话] ${detail.objective}`,
      status: 'running',
    }
  }

  async listApprovals(_query?: ApprovalQuery): Promise<ApprovalView[]> {
    await this.wait()
    return this.getScenarioDef().getApprovals()
  }

  async respondApproval(id: string, input: ApprovalResponseInput): Promise<ApprovalView> {
    await this.wait()
    return {
      id,
      taskId: 'task_20260905_002',
      taskObjective: '集成外部依赖并执行测试分支推送到远程仓库',
      requestAgentId: 'agent_codex_default',
      requestAgentName: 'Codex App Server',
      action: 'git_push',
      targetResource: 'git push origin feat/f0-desktop-skeleton',
      riskLevel: 'high',
      status: input.decision === 'approve' ? 'approved' : 'rejected',
      requestedAt: '2026-09-05T18:18:05Z',
      decidedAt: new Date().toISOString(),
      decision: input.decision,
      reason: input.reason,
    }
  }

  async getSettings(): Promise<UserSettingsView> {
    await this.wait()
    return {
      appearance: {
        mode: 'system',
        palette: 'hq-blue',
        density: 'comfortable',
        contrast: 'normal',
        reduceMotion: 'system',
        fontScale: 1,
      },
      general: {
        language: 'zh-CN',
        launchAtLogin: false,
        minimizeToTray: true,
        closeToTray: true,
      },
      connection: {
        hubUrl: 'http://127.0.0.1:49210',
        cloudEnabled: false,
        deviceName: 'DESKTOP-HQAGENT',
      },
      security: {
        requireApprovalForDangerousActions: true,
        allowedPathsOnly: true,
      },
      updates: {
        channel: 'beta',
        autoCheck: true,
        autoDownload: false,
      },
      telemetry: {
        anonymousTelemetry: false,
      },
    }
  }

  async updateAppearance(input: AppearanceSettings): Promise<AppearanceSettings> {
    await this.wait()
    return input
  }

  async getUpdateState(): Promise<UpdateStateView> {
    await this.wait()
    return this.getScenarioDef().getUpdateState()
  }

  async controlUpdate(action: UpdateActionInput): Promise<UpdateStateView> {
    await this.wait()
    const state = await this.getUpdateState()
    if (action.action === 'download') {
      state.phase = 'downloading'
    } else if (action.action === 'cancel') {
      state.phase = 'available'
    } else if (action.action === 'install') {
      state.phase = 'draining_tasks'
    }
    return state
  }

  public emitMockEvent(event: Partial<HubEvent>) {
    this.currentSeq++
    const fullEvent: HubEvent = {
      eventId: 'evt_' + Math.random().toString(36).substring(2, 9),
      seq: this.currentSeq,
      occurredAt: new Date().toISOString(),
      aggregateType: 'task',
      aggregateId: 'task_20260905_001',
      type: 'agent.progress',
      payload: {},
      protocolVersion: '0.2.0',
      ...event,
    }
    this.historicalEvents.push(fullEvent)
    this.eventListeners.forEach((fn) => fn(fullEvent))
    return fullEvent
  }

  public simulateClose(code = 1000) {
    this.isConnected = false
    if (code === 4410) {
      this.currentSeq = 0
    }
    this.closeListeners.forEach((fn) => fn(code))
  }

  public onSimulatedClose(fn: (code: number) => void) {
    this.closeListeners.add(fn)
    return () => this.closeListeners.delete(fn)
  }

  public generate10kEvents(taskId = 'task_20260905_001'): HubEvent[] {
    const list: HubEvent[] = []
    const baseSeq = this.currentSeq
    for (let i = 1; i <= 10000; i++) {
      const evt: HubEvent = {
        eventId: `evt_10k_${i}`,
        seq: baseSeq + i,
        occurredAt: new Date(Date.now() - (10000 - i) * 100).toISOString(),
        aggregateType: 'task',
        aggregateId: taskId,
        taskId,
        nodeId: i % 2 === 0 ? 'node_01' : 'node_02',
        roleId: i % 2 === 0 ? 'general_implementer' : 'reviewer',
        type: i % 5 === 0 ? 'agent.tool_call' : 'agent.progress',
        payload: {
          message: `正在执行第 ${i} 步自动化测试与代码分析...`,
          percent: Math.min(100, Math.floor((i / 10000) * 100)),
        },
        protocolVersion: '0.2.0',
      }
      list.push(evt)
    }
    this.currentSeq += 10000
    this.historicalEvents.push(...list)
    return list
  }

  subscribeEvents(
    input: SubscribeEventsInput,
    onEvent: (event: HubEvent) => void,
    onError?: (err: unknown) => void
  ): EventSubscription {
    this.eventListeners.add(onEvent)

    // Single-flight connection establishment simulation (Trap 6)
    if (!this.isConnected && !this.connectPromise) {
      this.connectPromise = (async () => {
        this.ticketRequestCount++
        await new Promise((r) => setTimeout(r, 10))
        this.connectionCount++
        this.isConnected = true
        this.connectPromise = null
      })().catch((err) => {
        this.connectPromise = null
        if (onError) onError(err)
      })
    }

    // Replay historical events if afterSeq specified
    if (input.afterSeq !== undefined && input.afterSeq >= 0) {
      const replay = this.historicalEvents.filter((e) => e.seq > (input.afterSeq ?? 0))
      for (const evt of replay) {
        onEvent(evt)
      }
    }

    return {
      unsubscribe: () => {
        this.eventListeners.delete(onEvent)
        if (this.eventListeners.size === 0) {
          this.isConnected = false
        }
      },
    }
  }
}

export const mockGateway = new MockGateway()
