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
  ApiEnvelope,
  ErrorCode,
  PageResult,
  WsTicket,
} from '@hqagent/protocol'

import type { UiGateway, EventSubscription } from './ui-gateway'

export interface HubEndpoint {
  baseUrl: string
  token: string
  pid?: number
}

export class HubApiError extends Error {
  readonly code: ErrorCode
  readonly status: number
  readonly detail?: Record<string, unknown>
  readonly retryable: boolean
  readonly requestId?: string

  constructor(
    message: string,
    code: ErrorCode,
    status: number,
    detail?: Record<string, unknown>,
    retryable = false,
    requestId?: string
  ) {
    super(message)
    this.name = 'HubApiError'
    this.code = code
    this.status = status
    this.detail = detail
    this.retryable = retryable
    this.requestId = requestId
  }
}

// Wrapper for Tauri invoke with strict validation (R1: no hardcoded fallback token)
async function getHubEndpointFromTauri(): Promise<HubEndpoint> {
  if (typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window) {
    const { invoke } = await import('@tauri-apps/api/core')
    return await invoke<HubEndpoint>('get_hub_endpoint')
  }

  // In browser dev mode, only read from explicit environment variables (R1)
  if (import.meta.env.DEV) {
    const baseUrl = import.meta.env.VITE_HUB_BASE_URL
    const token = import.meta.env.VITE_HUB_TOKEN
    if (baseUrl && token) {
      return { baseUrl, token }
    }
  }

  throw new Error('Local Hub endpoint unavailable: not running in Tauri shell and no VITE_HUB_* dev env provided')
}

export class LocalHubGateway implements UiGateway {
  private endpoint: HubEndpoint | null = null
  private ws: WebSocket | null = null
  private lastConfirmedSeq = 0
  private subscribers: Set<(event: HubEvent) => void> = new Set()
  private connectPromise: Promise<void> | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectAttempts = 0

  constructor(initialEndpoint?: HubEndpoint) {
    if (initialEndpoint) {
      this.endpoint = initialEndpoint
    }
  }

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

    // R4: Parse envelope first regardless of status code to preserve error codes
    let envelope: ApiEnvelope<T> | null = null
    try {
      envelope = (await res.json()) as ApiEnvelope<T>
    } catch {
      // Body may not be valid JSON
    }

    if (envelope && !envelope.success && envelope.error) {
      throw new HubApiError(
        envelope.error.message,
        envelope.error.code,
        res.status,
        envelope.error.detail,
        envelope.error.retryable,
        envelope.requestId
      )
    }

    if (!res.ok) {
      const defaultCode: ErrorCode = res.status === 401 ? 'UNAUTHORIZED' : 'INTERNAL'
      throw new HubApiError(
        `HTTP Error ${res.status}: ${res.statusText}`,
        defaultCode,
        res.status
      )
    }

    if (!envelope || !envelope.success) {
      throw new HubApiError(
        envelope?.error?.message || 'Unknown Hub Error',
        envelope?.error?.code || 'INTERNAL',
        res.status
      )
    }

    return envelope.data as T
  }

  /**
   * 原生 WebSocket 无法设 Authorization Header。
   * 必须先用 Bearer 调 POST /api/v1/auth/ws-ticket 换 30 秒一次性 Ticket，再用查询参数握手。
   * 每次重连必须重新换票，严禁缓存复用。
   */
  private async acquireWsTicket(): Promise<string> {
    const res = await this.fetchApi<WsTicket>('/api/v1/auth/ws-ticket', {
      method: 'POST',
      body: JSON.stringify({ purpose: 'events' }),
    })
    return res.ticket
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

  // R7: Exponential backoff reconnect
  private scheduleReconnect(onError?: (err: unknown) => void) {
    if (this.reconnectTimer || this.subscribers.size === 0) return
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), 15000)
    this.reconnectAttempts++
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connectWebSocket(onError)
    }, delay)
  }

  // R2: Single-flight WebSocket connection (returns connectPromise while in-flight)
  private connectWebSocket(onError?: (err: unknown) => void): Promise<void> {
    if (this.subscribers.size === 0) return Promise.resolve()
    if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
      return Promise.resolve()
    }
    if (this.connectPromise) {
      return this.connectPromise
    }

    this.connectPromise = (async () => {
      try {
        const [{ baseUrl }, ticket] = await Promise.all([this.ensureEndpoint(), this.acquireWsTicket()])
        if (this.subscribers.size === 0) {
          return
        }
        const wsUrl =
          baseUrl.replace(/^http/, 'ws') +
          `/api/v1/events/stream?ticket=${encodeURIComponent(ticket)}&after=${this.lastConfirmedSeq}`

        const ws = new WebSocket(wsUrl)
        this.ws = ws

        ws.onopen = () => {
          this.reconnectAttempts = 0
        }

        ws.onmessage = (msg) => {
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

        ws.onerror = (err) => {
          if (onError) onError(err)
        }

        ws.onclose = (event: CloseEvent) => {
          if (this.ws === ws) {
            this.ws = null
          }
          // F2-R2: Check close code 4410 (EVENT_CURSOR_EXPIRED)
          if (event && (event.code === 4410 || event.code === 4010)) {
            this.lastConfirmedSeq = 0
            this.getBootstrap()
              .catch((err) => {
                console.error('[LocalHubGateway] Failed to refetch bootstrap snapshot on cursor expired', err)
              })
              .finally(() => {
                if (this.subscribers.size > 0) {
                  this.scheduleReconnect(onError)
                }
              })
            return
          }
          if (this.subscribers.size > 0) {
            this.scheduleReconnect(onError)
          }
        }
      } catch (err) {
        // R3: Catch ticket acquisition failure before WebSocket is created and schedule reconnect
        console.error('[LocalHubGateway] Failed to establish WS connection', err)
        // R6: Reset sequence cursor if cursor expired
        if (err instanceof HubApiError && err.code === 'EVENT_CURSOR_EXPIRED') {
          this.lastConfirmedSeq = 0
        }
        if (onError) onError(err)
        if (this.subscribers.size > 0) {
          this.scheduleReconnect(onError)
        }
      } finally {
        this.connectPromise = null
      }
    })()

    return this.connectPromise
  }

  subscribeEvents(
    _input: SubscribeEventsInput,
    onEvent: (event: HubEvent) => void,
    onError?: (err: unknown) => void
  ): EventSubscription {
    this.subscribers.add(onEvent)

    if (!this.ws && !this.connectPromise) {
      this.connectWebSocket(onError)
    }

    return {
      unsubscribe: () => {
        this.subscribers.delete(onEvent)
        if (this.subscribers.size === 0) {
          if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer)
            this.reconnectTimer = null
          }
          this.reconnectAttempts = 0
          if (this.ws) {
            this.ws.close()
            this.ws = null
          }
        }
      },
    }
  }
}

export const localHubGateway = new LocalHubGateway()
