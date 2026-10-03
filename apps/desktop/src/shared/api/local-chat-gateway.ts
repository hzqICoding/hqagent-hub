import { getRemoteErrorMessage } from '@/shared/i18n/remote-errors'
import { uploadAttachment as uploadBinary, attachmentBlob } from '@/shared/attachments/transport'
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
  ApiEnvelope,
  ErrorCode,
} from '@hqagent/protocol'

import type { LocalChatGateway } from './local-chat-gateway.interface'
import { HubApiError } from './local-hub-gateway'

export class RealLocalChatGateway implements LocalChatGateway {
  listImageVerifications(options: { includeInactiveModels?: boolean; cursor?: string } = {}): Promise<LocalImageVerificationPage> {
    const query = new URLSearchParams({ limit: '50', includeInactiveModels: String(options.includeInactiveModels ?? false), ...(options.cursor ? { cursor: options.cursor } : {}) })
    return this.fetchApi(`/api/v2/agents/image-verifications?${query}`)
  }
  startImageVerification(input: StartLocalImageVerificationInput, key: string): Promise<LocalImageVerificationJobView> {
    return this.fetchApi('/api/v2/agents/image-verification-jobs', { method: 'POST', body: JSON.stringify(input) }, key)
  }
  getImageVerificationJob(id: string): Promise<LocalImageVerificationJobView> { return this.fetchApi(`/api/v2/agents/image-verification-jobs/${encodeURIComponent(id)}`) }
  cancelImageVerification(id: string, key: string): Promise<LocalImageVerificationJobView> { return this.fetchApi(`/api/v2/agents/image-verification-jobs/${encodeURIComponent(id)}/cancellations`, { method: 'POST', body: '{}' }, key) }
  deleteLocalConversation(id: string, expectedVersion: number, key: string): Promise<LocalConversationDeletionView> {
    return this.fetchApi(`/api/v2/conversations/${encodeURIComponent(id)}?expectedVersion=${expectedVersion}`, { method: 'DELETE' }, key)
  }

  private attachmentError = (code: ErrorCode, status: number, requestId?: string): Error => {
    return new HubApiError(getRemoteErrorMessage(code), code, status, undefined, false, requestId)
  }
  getAttachmentLimits(): Promise<AttachmentLimits> { return this.fetchApi('/api/v2/attachments/limits') }
  uploadAttachment(conversationId: string, file: Blob, options: UploadOptions): Promise<LocalAttachmentView> {
    return uploadBinary(`${this.baseUrl}/api/v2/conversations/${encodeURIComponent(conversationId)}/attachments`, file, options, null, this.attachmentError)
  }
  getAttachment(id: string): Promise<LocalAttachmentView> { return this.fetchApi(`/api/v2/attachments/${encodeURIComponent(id)}`) }
  deleteAttachment(id: string): Promise<AttachmentDeletedView> {
    return this.fetchApi(`/api/v2/attachments/${encodeURIComponent(id)}`, { method: 'DELETE' }, crypto.randomUUID())
  }
  getAttachmentContent(id: string, signal?: AbortSignal): Promise<Blob> { return attachmentBlob(`${this.baseUrl}/api/v2/attachments/${encodeURIComponent(id)}/content`, false, signal, this.attachmentError) }
  getAttachmentThumbnail(id: string, signal?: AbortSignal): Promise<Blob> { return attachmentBlob(`${this.baseUrl}/api/v2/attachments/${encodeURIComponent(id)}/thumbnail`, true, signal, this.attachmentError) }
  getAttachmentCapabilities(conversationId: string): Promise<AttachmentTargetCapabilities> { return this.fetchApi(`/api/v2/conversations/${encodeURIComponent(conversationId)}/attachment-capabilities`) }

  private baseUrl: string

  constructor(baseUrl = '') {
    // In dev, defaults to '' which uses Vite proxy for /api and /ws
    // In production, Worker serves web from same origin
    this.baseUrl = baseUrl.replace(/\/$/, '')
  }

  listNativeSessions(cursor?: string): Promise<LocalNativeSessionPage> {
    const query = new URLSearchParams({ limit: '50', ...(cursor ? { cursor } : {}) })
    return this.fetchApi(`/api/v2/native-sessions?${query}`)
  }
  getNativeSession(id: string): Promise<NativeSessionIndex> {
    return this.fetchApi(`/api/v2/native-sessions/${encodeURIComponent(id)}`)
  }
  readNativeMessages(id: string, before?: string): Promise<NativeMessagePage> {
    const query = new URLSearchParams({ limit: '50', ...(before ? { before } : {}) })
    return this.fetchApi(`/api/v2/native-sessions/${encodeURIComponent(id)}/messages?${query}`)
  }
  importNativeSession(id: string, input: RemoteNativeImportInput, key = crypto.randomUUID()): Promise<LocalConversationView> {
    return this.fetchApi(`/api/v2/native-sessions/${encodeURIComponent(id)}/imports`, { method: 'POST', body: JSON.stringify(input) }, key)
  }
  getAuthorizedRoots(): Promise<LocalAuthorizedRootsView> {
    return this.fetchApi('/api/v2/remote/authorized-roots')
  }
  setAuthorizedRoots(input: LocalAuthorizedRootsInput): Promise<LocalAuthorizedRootsView> {
    return this.fetchApi('/api/v2/remote/authorized-roots', { method: 'PUT', body: JSON.stringify(input) }, crypto.randomUUID())
  }

  private async fetchApi<T>(
    endpoint: string,
    options: RequestInit = {},
    idempotencyKey?: string,
    timeoutMs = 15000
  ): Promise<T> {
    const controller = new AbortController()
    const cancel = () => controller.abort()
    options.signal?.addEventListener('abort', cancel, { once: true })
    if (options.signal?.aborted) cancel()
    let timer: ReturnType<typeof setTimeout> | undefined
    const deadline = new Promise<never>((_resolve, reject) => {
      timer = setTimeout(() => {
        reject(new HubApiError('本地服务响应超时，请稍后重试；状态刷新会自动重连', 'HUB_NOT_READY', 503, undefined, true))
        controller.abort()
      }, timeoutMs)
    })
    try {
      return await Promise.race([
        this.fetchEnvelope<T>(endpoint, { ...options, signal: controller.signal }, idempotencyKey),
        deadline,
      ])
    } finally {
      clearTimeout(timer)
      options.signal?.removeEventListener('abort', cancel)
    }
  }

  private async fetchEnvelope<T>(
    endpoint: string,
    options: RequestInit = {},
    idempotencyKey?: string
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...((options.headers as Record<string, string>) || {}),
    }

    if (idempotencyKey) {
      headers['Idempotency-Key'] = idempotencyKey
    }

    let response: Response
    try {
      response = await fetch(url, {
        ...options,
        headers,
        cache: 'no-store',
        credentials: 'include', // HttpOnly cookie session
      })
    } catch (networkErr) {
      throw new HubApiError(
        networkErr instanceof Error ? networkErr.message : 'Network request failed',
        'HUB_NOT_READY' as ErrorCode,
        503,
        undefined,
        true
      )
    }

    let envelope: ApiEnvelope<T>
    try {
      envelope = (await response.json()) as ApiEnvelope<T>
    } catch {
      if (!response.ok) {
        throw new HubApiError(
          `HTTP ${response.status}: ${response.statusText}`,
          (response.status === 401
            ? 'UNAUTHORIZED'
            : response.status === 403
            ? 'ORIGIN_NOT_ALLOWED'
            : response.status === 404
            ? 'NOT_FOUND'
            : response.status === 409
            ? 'CONFLICT'
            : response.status === 410
            ? 'EVENT_CURSOR_EXPIRED'
            : 'INTERNAL') as ErrorCode,
          response.status,
          undefined,
          response.status >= 500
        )
      }
      throw new HubApiError(
        'Invalid JSON response from server',
        'INTERNAL' as ErrorCode,
        response.status
      )
    }

    if (!envelope.success || envelope.error) {
      const err = envelope.error
      const code = (err?.code || 'INTERNAL') as ErrorCode
      throw new HubApiError(
        err?.message || (code === 'SESSION_NOT_RESUMABLE' ? '' : `Request failed with code ${code}`),
        code,
        response.status,
        err?.detail as Record<string, unknown> | undefined,
        err?.retryable ?? response.status >= 500,
        response.headers?.get('X-Request-Id') || envelope.requestId
      )
    }

    return envelope.data as T
  }

  // Auth
  async getLocalAuthStatus(): Promise<LocalAuthView> {
    return this.fetchApi<LocalAuthView>('/api/v2/auth/status', { method: 'GET' })
  }

  async openLocalSession(input: LocalAuthInput): Promise<LocalAuthView> {
    return this.fetchApi<LocalAuthView>('/api/v2/auth/local-session', {
      method: 'POST',
      body: JSON.stringify(input),
    })
  }

  async logoutLocalSession(): Promise<LocalAuthView> {
    return this.fetchApi<LocalAuthView>('/api/v2/auth/logout', { method: 'POST' })
  }

  // Agents & Models
  async listLocalAgents(): Promise<AgentView[]> {
    return this.fetchApi<AgentView[]>('/api/v2/agents', { method: 'GET' })
  }

  async discoverLocalAgents(): Promise<AgentDiscoveryResult> {
    return this.fetchApi<AgentDiscoveryResult>('/api/v2/agents/discover', {
      method: 'POST',
    })
  }

  async getAgentModels(agentId: string): Promise<LocalAgentModelsView> {
    return this.fetchApi<LocalAgentModelsView>(
      `/api/v2/agents/${encodeURIComponent(agentId)}/models`,
      { method: 'GET' }
    )
  }

  // Workspaces
  async listLocalWorkspaces(): Promise<WorkspaceView[]> {
    return this.fetchApi<WorkspaceView[]>('/api/v2/workspaces', { method: 'GET' })
  }

  async addLocalWorkspace(input: AddWorkspaceInput): Promise<WorkspaceView> {
    return this.fetchApi<WorkspaceView>('/api/v2/workspaces', {
      method: 'POST',
      body: JSON.stringify(input),
    })
  }

  // Scenes
  async pickLocalDirectory(input: PickLocalDirectoryInput): Promise<PickLocalDirectoryView> {
    return this.fetchApi<PickLocalDirectoryView>('/api/v2/workspaces/pick', {
      method: 'POST',
      body: JSON.stringify(input),
    }, undefined, 125000)
  }

  // Scenes
  async listLocalScenes(): Promise<LocalSceneView[]> {
    return this.fetchApi<LocalSceneView[]>('/api/v2/scenes', { method: 'GET' })
  }

  async createLocalScene(
    input: CreateLocalSceneInput,
    idempotencyKey: string
  ): Promise<LocalSceneView> {
    return this.fetchApi<LocalSceneView>(
      '/api/v2/scenes',
      { method: 'POST', body: JSON.stringify(input) },
      idempotencyKey
    )
  }

  async saveLocalScene(
    sceneId: string,
    input: SaveLocalSceneInput
  ): Promise<LocalSceneView> {
    return this.fetchApi<LocalSceneView>(
      `/api/v2/scenes/${encodeURIComponent(sceneId)}`,
      {
        method: 'PUT',
        body: JSON.stringify(input),
      }
    )
  }

  async listLocalRoleTemplates(): Promise<LocalRoleTemplateView[]> {
    return this.fetchApi<LocalRoleTemplateView[]>('/api/v2/role-templates', { method: 'GET' })
  }

  async createLocalRoleTemplate(
    input: CreateLocalRoleTemplateInput,
    idempotencyKey: string
  ): Promise<LocalRoleTemplateView> {
    return this.fetchApi<LocalRoleTemplateView>(
      '/api/v2/role-templates',
      { method: 'POST', body: JSON.stringify(input) },
      idempotencyKey
    )
  }

  async updateLocalRoleTemplate(
    templateId: string,
    input: UpdateLocalRoleTemplateInput,
    idempotencyKey: string
  ): Promise<LocalRoleTemplateView> {
    return this.fetchApi<LocalRoleTemplateView>(
      `/api/v2/role-templates/${encodeURIComponent(templateId)}`,
      { method: 'PUT', body: JSON.stringify(input) },
      idempotencyKey
    )
  }

  // Conversations & Messages
  async listLocalConversations(params?: {
    includeHidden?: boolean
    workspaceId?: string
  }): Promise<LocalConversationView[]> {
    const sp = new URLSearchParams()
    if (params?.includeHidden) sp.set('includeHidden', 'true')
    if (params?.workspaceId) sp.set('workspaceId', params.workspaceId)
    const qs = sp.toString()
    return this.fetchApi<LocalConversationView[]>(`/api/v2/conversations${qs ? `?${qs}` : ''}`, {
      method: 'GET',
    })
  }

  async createLocalConversation(
    input: CreateLocalConversationInput,
    idempotencyKey?: string
  ): Promise<LocalConversationView> {
    return this.fetchApi<LocalConversationView>(
      '/api/v2/conversations',
      {
        method: 'POST',
        body: JSON.stringify(input),
      },
      idempotencyKey
    )
  }

  async updateLocalConversation(
    conversationId: string,
    input: UpdateLocalConversationInput,
    idempotencyKey: string
  ): Promise<LocalConversationView> {
    return this.fetchApi<LocalConversationView>(
      `/api/v2/conversations/${encodeURIComponent(conversationId)}`,
      {
        method: 'PATCH',
        body: JSON.stringify(input),
      },
      idempotencyKey
    )
  }

  async listLocalMessages(
    conversationId: string,
    after = 0,
    limit = 200
  ): Promise<LocalMessageView[]> {
    const query = new URLSearchParams({
      after: String(after),
      limit: String(limit),
    }).toString()
    return this.fetchApi<LocalMessageView[]>(
      `/api/v2/conversations/${encodeURIComponent(conversationId)}/messages?${query}`,
      { method: 'GET' }
    )
  }

  async sendLocalMessage(
    conversationId: string,
    input: SendLocalMessageInput,
    idempotencyKey?: string
  ): Promise<LocalMessageReceipt> {
    return this.fetchApi<LocalMessageReceipt>(
      `/api/v2/conversations/${encodeURIComponent(conversationId)}/messages`,
      {
        method: 'POST',
        body: JSON.stringify(input),
      },
      idempotencyKey
    )
  }

  // Runs
  async listConversationRuns(conversationId: string): Promise<LocalRunView[]> {
    return this.fetchApi<LocalRunView[]>(
      `/api/v2/conversations/${encodeURIComponent(conversationId)}/runs`,
      { method: 'GET' }
    )
  }

  async getLocalRun(runId: string): Promise<LocalRunView> {
    return this.fetchApi<LocalRunView>(
      `/api/v2/runs/${encodeURIComponent(runId)}`,
      { method: 'GET' }
    )
  }

  async controlLocalRun(
    runId: string,
    input: TaskActionInput,
    idempotencyKey?: string
  ): Promise<LocalRunView> {
    return this.fetchApi<LocalRunView>(
      `/api/v2/runs/${encodeURIComponent(runId)}/commands`,
      {
        method: 'POST',
        body: JSON.stringify(input),
      },
      idempotencyKey
    )
  }

  // Events
  async listLocalEvents(after = 0, limit = 200): Promise<LocalEventPage> {
    const query = new URLSearchParams({
      after: String(after),
      limit: String(limit),
    }).toString()
    return this.fetchApi<LocalEventPage>(`/api/v2/events?${query}`, {
      method: 'GET',
    })
  }

  // Approvals & Sessions
  async listLocalApprovals(): Promise<ApprovalView[]> {
    return this.fetchApi<ApprovalView[]>('/api/v2/approvals', { method: 'GET' })
  }

  async decideLocalApproval(
    approvalId: string,
    input: ApprovalResponseInput,
    idempotencyKey?: string
  ): Promise<ApprovalView> {
    return this.fetchApi<ApprovalView>(
      `/api/v2/approvals/${encodeURIComponent(approvalId)}/decisions`,
      {
        method: 'POST',
        body: JSON.stringify(input),
      },
      idempotencyKey || `approval_${approvalId}_${input.decision}`
    )
  }

  async listLocalSessions(): Promise<SessionView[]> {
    return this.fetchApi<SessionView[]>('/api/v2/sessions', { method: 'GET' })
  }

  // Remote Link (D44)
  async getRemoteLink(): Promise<RemoteLinkView> {
    return this.fetchApi<RemoteLinkView>('/api/v2/remote/link', { method: 'GET' })
  }

  async startRemotePairing(
    input: RemoteLinkPairingInput,
    idempotencyKey?: string
  ): Promise<RemoteLinkView> {
    return this.fetchApi<RemoteLinkView>(
      '/api/v2/remote/pairing',
      {
        method: 'POST',
        body: JSON.stringify(input),
      },
      idempotencyKey || `pairing_${Date.now()}`
    )
  }

  async cancelRemotePairing(idempotencyKey?: string): Promise<RemoteLinkView> {
    return this.fetchApi<RemoteLinkView>(
      '/api/v2/remote/pairing',
      {
        method: 'DELETE',
      },
      idempotencyKey || `cancel_pairing_${Date.now()}`
    )
  }

  async unlinkRemote(idempotencyKey?: string): Promise<RemoteLinkView> {
    return this.fetchApi<RemoteLinkView>(
      '/api/v2/remote/unlink',
      {
        method: 'POST',
      },
      idempotencyKey || `unlink_${Date.now()}`
    )
  }

  // Remote Sync Settings (R1.5 / 0.7.0)
  async getRemoteSyncSettings(): Promise<RemoteSyncSettingsView> {
    return this.fetchApi<RemoteSyncSettingsView>('/api/v2/remote/sync-settings', {
      method: 'GET',
    })
  }

  async setRemoteSyncSettings(
    input: RemoteSyncSettingsInput,
    idempotencyKey?: string
  ): Promise<RemoteSyncSettingsView> {
    return this.fetchApi<RemoteSyncSettingsView>(
      '/api/v2/remote/sync-settings',
      {
        method: 'PUT',
        body: JSON.stringify(input),
      },
      idempotencyKey || `sync_settings_${Date.now()}`
    )
  }
}

export const realLocalChatGateway = new RealLocalChatGateway()
