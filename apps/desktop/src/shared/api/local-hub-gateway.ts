import type {
  UiGateway,
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
  EventSubscription,
  HubEvent,
  ApiEnvelope,
  PageResult,
} from '@hqagent/protocol'

interface HubEndpoint {
  baseUrl: string
  token: string
  pid?: number
}

// Wrapper for Tauri invoke with safe browser fallback
async function getHubEndpointFromTauri(): Promise<HubEndpoint> {
  if (typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window) {
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      return await invoke<HubEndpoint>('get_hub_endpoint')
    } catch (err) {
      console.warn('[LocalHubGateway] invoke("get_hub_endpoint") failed, using fallback', err)
    }
  }
  // Fallback for dev / browser testing
  return {
    baseUrl: 'http://127.0.0.1:49210',
    token: 'tok_dev_fallback_hub_token',
  }
}

export class LocalHubGateway implements UiGateway {
  private endpoint: HubEndpoint | null = null
  private ws: WebSocket | null = null
  private lastConfirmedSeq = 0
  private subscribers: Set<(event: HubEvent) => void> = new Set()

  private async ensureEndpoint(): Promise<HubEndpoint> {
    if (!this.endpoint) {
      this.endpoint = await getHubEndpointFromTauri()
    }
    return this.endpoint
  }

  private async fetchApi<T>(path: string, options: RequestInit = {}): Promise<T> {
    const { baseUrl, token } = await this.ensureEndpoint()
    const headers = new Headers(options.headers || {})
    headers.set('Authorization', `Bearer ${token}`)
    headers.set('Content-Type', 'application/json')
    headers.set('X-Client-Id', 'hqagent-desktop')

    const res = await fetch(`${baseUrl}${path}`, {
      ...options,
      headers,
    })

    if (!res.ok) {
      throw new Error(`HTTP Error ${res.status}: ${res.statusText}`)
    }

    const envelope = (await res.json()) as ApiEnvelope<T>
    if (!envelope.success) {
      throw new Error(envelope.error?.message || 'Unknown Hub Error')
    }
    return envelope.data as T
  }

  async getBootstrap(): Promise<BootstrapView> {
    return this.fetchApi<BootstrapView>('/api/v1/bootstrap')
  }

  async listWorkspaces(query?: WorkspaceQuery): Promise<WorkspaceView[]> {
    const params = new URLSearchParams()
    if (query?.search) params.set('search', query.search)
    return this.fetchApi<WorkspaceView[]>(`/api/v1/workspaces?${params.toString()}`)
  }

  async listAgents(): Promise<AgentView[]> {
    return this.fetchApi<AgentView[]>('/api/v1/agents')
  }

  async refreshAgents(): Promise<AgentDiscoveryResult> {
    return this.fetchApi<AgentDiscoveryResult>('/api/v1/agents/discovery', {
      method: 'POST',
    })
  }

  async listTeamProfiles(): Promise<TeamProfileView[]> {
    return this.fetchApi<TeamProfileView[]>('/api/v1/team-profiles')
  }

  async getTeamProfile(id: string): Promise<TeamProfileView> {
    return this.fetchApi<TeamProfileView>(`/api/v1/team-profiles/${id}`)
  }

  async saveTeamProfile(input: SaveTeamProfileInput): Promise<TeamProfileView> {
    const url = input.id ? `/api/v1/team-profiles/${input.id}` : '/api/v1/team-profiles'
    return this.fetchApi<TeamProfileView>(url, {
      method: input.id ? 'PUT' : 'POST',
      body: JSON.stringify(input),
    })
  }

  async resolveTeamProfile(input: ResolveTeamProfileInput): Promise<ResolvedTeamView> {
    return this.fetchApi<ResolvedTeamView>('/api/v1/team-profiles/resolve', {
      method: 'POST',
      body: JSON.stringify(input),
    })
  }

  async listTasks(query: TaskQuery): Promise<PageResult<TaskSummaryView>> {
    const params = new URLSearchParams()
    if (query.page) params.set('page', String(query.page))
    if (query.pageSize) params.set('pageSize', String(query.pageSize))
    if (query.status) params.set('status', query.status)
    return this.fetchApi<PageResult<TaskSummaryView>>(`/api/v1/tasks?${params.toString()}`)
  }

  async getTask(id: string): Promise<TaskDetailView> {
    return this.fetchApi<TaskDetailView>(`/api/v1/tasks/${id}`)
  }

  async createTask(input: CreateTaskInput): Promise<TaskDetailView> {
    return this.fetchApi<TaskDetailView>('/api/v1/tasks', {
      method: 'POST',
      body: JSON.stringify(input),
    })
  }

  async controlTask(id: string, action: TaskActionInput): Promise<TaskDetailView> {
    return this.fetchApi<TaskDetailView>(`/api/v1/tasks/${id}/actions`, {
      method: 'POST',
      body: JSON.stringify(action),
    })
  }

  async listSessions(query: SessionQuery): Promise<PageResult<SessionView>> {
    const params = new URLSearchParams()
    if (query.workspaceId) params.set('workspaceId', query.workspaceId)
    return this.fetchApi<PageResult<SessionView>>(`/api/v1/sessions?${params.toString()}`)
  }

  async resumeSession(id: string, input?: ResumeSessionInput): Promise<TaskDetailView> {
    return this.fetchApi<TaskDetailView>(`/api/v1/sessions/${id}/resume`, {
      method: 'POST',
      body: JSON.stringify(input || {}),
    })
  }

  async listApprovals(query?: ApprovalQuery): Promise<ApprovalView[]> {
    const params = new URLSearchParams()
    if (query?.status) params.set('status', query.status)
    return this.fetchApi<ApprovalView[]>(`/api/v1/approvals?${params.toString()}`)
  }

  async respondApproval(id: string, input: ApprovalResponseInput): Promise<ApprovalView> {
    return this.fetchApi<ApprovalView>(`/api/v1/approvals/${id}/response`, {
      method: 'POST',
      body: JSON.stringify(input),
    })
  }

  async getSettings(): Promise<UserSettingsView> {
    return this.fetchApi<UserSettingsView>('/api/v1/settings')
  }

  async updateAppearance(input: AppearanceSettings): Promise<AppearanceSettings> {
    return this.fetchApi<AppearanceSettings>('/api/v1/settings/appearance', {
      method: 'PUT',
      body: JSON.stringify(input),
    })
  }

  async getUpdateState(): Promise<UpdateStateView> {
    return this.fetchApi<UpdateStateView>('/api/v1/updates/state')
  }

  async controlUpdate(action: UpdateActionInput): Promise<UpdateStateView> {
    return this.fetchApi<UpdateStateView>('/api/v1/updates/actions', {
      method: 'POST',
      body: JSON.stringify(action),
    })
  }

  subscribeEvents(
    input: SubscribeEventsInput,
    onEvent: (event: HubEvent) => void,
    onError?: (err: unknown) => void
  ): EventSubscription {
    this.subscribers.add(onEvent)

    this.ensureEndpoint().then(({ baseUrl, token }) => {
      const wsUrl = baseUrl.replace(/^http/, 'ws') + `/api/v1/events/stream?token=${encodeURIComponent(token)}&after=${this.lastConfirmedSeq}`
      this.ws = new WebSocket(wsUrl)

      this.ws.onmessage = (msg) => {
        try {
          const event = JSON.parse(msg.data) as HubEvent
          if (event.seq > this.lastConfirmedSeq) {
            this.lastConfirmedSeq = event.seq
          }
          this.subscribers.forEach((fn) => fn(event))
        } catch (e) {
          console.error('[LocalHubGateway] WS parse error', e)
        }
      }

      this.ws.onerror = (err) => {
        if (onError) onError(err)
      }
    })

    return {
      unsubscribe: () => {
        this.subscribers.delete(onEvent)
        if (this.subscribers.size === 0 && this.ws) {
          this.ws.close()
          this.ws = null
        }
      },
    }
  }
}

export const localHubGateway = new LocalHubGateway()
