import { uploadAttachment as uploadBinary, attachmentBlob } from '@/shared/attachments/transport'
import type { UploadOptions } from '@/shared/attachments/transport'
import type {
  AttachmentDeletedView, RemoteAttachmentView, RemoteAttachmentLimitsView,
  RemoteNativeSessionPage, RemoteNativeSessionView, NativeMessagePage, RemoteNativeImportInput, RemoteResourceQueuedReceipt, DirectoryListingInput, DirectoryListingPage, RemoteWorkspaceRegisterInput, RemoteV4CatalogView,
  ErrorCode,
  ApiEnvelope,
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
import type { IRemoteGateway, RemoteDeviceFilters } from './remote-gateway.interface'
import { recordRemoteFailure, clearRemoteFailureFor } from './remote-diagnostics'
import { getRemoteErrorMessage } from '@/shared/i18n/remote-errors'

export class RemoteApiError extends Error {
  readonly code: string
  readonly status: number
  readonly detail?: unknown
  readonly retryAfter?: number
  readonly requestId?: string

  constructor(options: {
    message: string
    code: string
    status: number
    detail?: unknown
    retryAfter?: number
    requestId?: string
  }) {
    super(options.message)
    this.name = 'RemoteApiError'
    this.code = options.code
    this.status = options.status
    this.detail = options.detail
    this.retryAfter = options.retryAfter
    this.requestId = options.requestId
  }
}

export class RemoteGateway implements IRemoteGateway {
  supportsDeviceManagement = false
  private attachmentError = (code: ErrorCode, status: number, requestId?: string): Error => {
    return new RemoteApiError({ code, status, requestId, message: getRemoteErrorMessage(code) })
  }
  getAttachmentLimits(): Promise<RemoteAttachmentLimitsView> { return this.fetchApi('/api/v2/attachments/limits') }
  uploadAttachment(conversationId: string, file: Blob, options: UploadOptions): Promise<RemoteAttachmentView> {
    return uploadBinary(`${this.baseUrl}/api/v2/conversations/${encodeURIComponent(conversationId)}/attachments`, file, options, this.csrfToken, this.attachmentError)
  }
  getAttachment(id: string): Promise<RemoteAttachmentView> { return this.fetchApi(`/api/v2/attachments/${encodeURIComponent(id)}`) }
  deleteAttachment(id: string): Promise<AttachmentDeletedView> {
    return this.fetchApi(`/api/v2/attachments/${encodeURIComponent(id)}`, { method: 'DELETE', idempotencyKey: crypto.randomUUID() })
  }
  getAttachmentContent(id: string, signal?: AbortSignal): Promise<Blob> { return attachmentBlob(`${this.baseUrl}/api/v2/attachments/${encodeURIComponent(id)}/content`, false, signal, this.attachmentError) }
  getAttachmentThumbnail(id: string, signal?: AbortSignal): Promise<Blob> { return attachmentBlob(`${this.baseUrl}/api/v2/attachments/${encodeURIComponent(id)}/thumbnail`, true, signal, this.attachmentError) }

  private baseUrl: string
  // Kept in memory only. NEVER stored to localStorage/sessionStorage/IndexedDB!
  private csrfToken: string | null = null

  constructor(baseUrl = '') {
    this.baseUrl = baseUrl.replace(/\/+$/, '')
  }

  getCsrfToken(): string | null {
    return this.csrfToken
  }

  setCsrfToken(token: string | null): void {
    this.csrfToken = token
  }

  private generateIdempotencyKey(): string {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID()
    }
    return `rem_idemp_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
  }

  private async fetchApi<T>(
    endpoint: string,
    options: {
      method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'
      body?: unknown
      idempotencyKey?: string
      params?: Record<string, string | number | boolean | undefined>
    } = {}
  ): Promise<T> {
    const method = options.method || 'GET'
    const isMutating = ['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)

    let url = `${this.baseUrl}${endpoint}`
    if (options.params) {
      const sp = new URLSearchParams()
      for (const [k, v] of Object.entries(options.params)) {
        if (v !== undefined && v !== null) {
          sp.append(k, String(v))
        }
      }
      const qs = sp.toString()
      if (qs) {
        url += (url.includes('?') ? '&' : '?') + qs
      }
    }

    const headers: Record<string, string> = {
      Accept: 'application/json',
    }

    if (isMutating) {
      headers['Content-Type'] = 'application/json'
      headers['Idempotency-Key'] = options.idempotencyKey || this.generateIdempotencyKey()
      if (this.csrfToken) {
        headers['X-CSRF-Token'] = this.csrfToken
      }
    }

    let response: Response
    try {
      response = await fetch(url, {
        method,
        headers,
        body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
        // Browser authentication is via HttpOnly Secure Cookie __Host-hqremote
        credentials: 'same-origin',
        cache: 'no-store',
      })
    } catch {
      recordRemoteFailure(endpoint, method, '网络连接失败，请检查网络设置')
      throw new RemoteApiError({
        message: '网络连接失败，请检查网络设置',
        code: 'NETWORK_ERROR',
        status: 0,
      })
    }

    let retryAfter: number | undefined
    const retryAfterHeader = response.headers.get('Retry-After')
    if (retryAfterHeader) {
      const parsed = parseInt(retryAfterHeader, 10)
      if (!Number.isNaN(parsed)) {
        retryAfter = parsed
      }
    }

    let envelope: ApiEnvelope<T> | null = null
    try {
      envelope = (await response.json()) as ApiEnvelope<T>
    } catch {
      // JSON parse error
    }

    const version = envelope?.protocolVersion?.match(/^(\d+)\.(\d+)(?:\.|$)/)
    if (version) this.supportsDeviceManagement = Number(version[1]) === 0 && Number(version[2]) >= 8

    if (!response.ok || !envelope || !envelope.success) {
      const code = envelope?.error?.code || (response.status === 429 ? 'REMOTE_RATE_LIMITED' : 'INTERNAL')
      const rawMessage = envelope?.error?.message || response.statusText || '请求失败'
      const localizedMessage = getRemoteErrorMessage(code, rawMessage)

      const requestId = response.headers.get('X-Request-Id') || envelope?.requestId
      recordRemoteFailure(endpoint, method, localizedMessage, requestId)
      throw new RemoteApiError({
        message: localizedMessage,
        code,
        status: response.status,
        detail: envelope?.error?.detail,
        retryAfter,
        requestId: response.headers.get('X-Request-Id') || envelope?.requestId,
      })
    }

    clearRemoteFailureFor(endpoint, method)
    return envelope.data as T
  }

  listNativeSessions(workerId: string, cursor?: string): Promise<RemoteNativeSessionPage> {
    return this.fetchApi(`/api/v2/devices/${encodeURIComponent(workerId)}/native-sessions`, { params: { cursor, limit: 50 } })
  }
  getNativeSession(id: string): Promise<RemoteNativeSessionView> {
    return this.fetchApi(`/api/v2/native-sessions/${encodeURIComponent(id)}`)
  }
  readNativeMessages(id: string, before?: string): Promise<NativeMessagePage> {
    return this.fetchApi(`/api/v2/native-sessions/${encodeURIComponent(id)}/messages`, { params: { before, limit: 50 } })
  }
  importNativeSession(id: string, input: RemoteNativeImportInput, key?: string): Promise<RemoteResourceQueuedReceipt> {
    return this.fetchApi(`/api/v2/native-sessions/${encodeURIComponent(id)}/imports`, { method: 'POST', body: input, idempotencyKey: key })
  }
  listDirectory(workerId: string, input: DirectoryListingInput): Promise<DirectoryListingPage> {
    return this.fetchApi(`/api/v2/devices/${encodeURIComponent(workerId)}/directory-listings`, { method: 'POST', body: input })
  }
  registerWorkspace(workerId: string, input: RemoteWorkspaceRegisterInput, key?: string): Promise<RemoteResourceQueuedReceipt> {
    return this.fetchApi(`/api/v2/devices/${encodeURIComponent(workerId)}/workspaces`, { method: 'POST', body: input, idempotencyKey: key })
  }

  // --- Auth & Session ---

  async login(input: RemoteLoginInput, idempotencyKey?: string): Promise<RemoteAuthenticatedSession> {
    const data = await this.fetchApi<RemoteAuthenticatedSession>('/api/v2/auth/login', {
      method: 'POST',
      body: input,
      idempotencyKey,
    })
    if (data.csrfToken) {
      this.csrfToken = data.csrfToken
    }
    return data
  }

  async getSession(): Promise<RemoteBrowserSessionView> {
    const data = await this.fetchApi<RemoteBrowserSessionView>('/api/v2/auth/session', {
      method: 'GET',
    })
    if (data.authenticated && data.csrfToken) {
      this.csrfToken = data.csrfToken
    } else {
      this.csrfToken = null
    }
    return data
  }

  async logout(idempotencyKey?: string): Promise<RemoteAnonymousSession> {
    const data = await this.fetchApi<RemoteAnonymousSession>('/api/v2/auth/logout', {
      method: 'POST',
      idempotencyKey,
    })
    this.csrfToken = null
    return data
  }

  // --- Pairing ---

  async previewPairing(input: RemotePairingPreviewInput, idempotencyKey?: string): Promise<RemotePairingPreview> {
    return this.fetchApi<RemotePairingPreview>('/api/v2/pairings/preview', {
      method: 'POST',
      body: input,
      idempotencyKey,
    })
  }

  async confirmPairing(
    pairRequestId: string,
    input: RemotePairingConfirmInput,
    idempotencyKey?: string
  ): Promise<RemoteDeviceView> {
    return this.fetchApi<RemoteDeviceView>(`/api/v2/pairings/${encodeURIComponent(pairRequestId)}/confirm`, {
      method: 'POST',
      body: input,
      idempotencyKey,
    })
  }

  // --- Devices ---

  async listDevices(cursor?: string, limit?: number, filters: RemoteDeviceFilters = {}): Promise<RemoteDevicePage> {
    return this.fetchApi<RemoteDevicePage>('/api/v2/devices', {
      method: 'GET',
      params: { cursor, limit, includeRevoked: false, ...filters },
    })
  }

  async getDevice(workerId: string): Promise<RemoteDeviceView> {
    return this.fetchApi<RemoteDeviceView>(`/api/v2/devices/${encodeURIComponent(workerId)}`, {
      method: 'GET',
    })
  }

  async revokeDevice(
    workerId: string,
    input: RemoteDeviceRevokeInput,
    idempotencyKey?: string
  ): Promise<RemoteDeviceRevocationView> {
    return this.fetchApi<RemoteDeviceRevocationView>(
      `/api/v2/devices/${encodeURIComponent(workerId)}/revocations`,
      {
        method: 'POST',
        body: input,
        idempotencyKey,
      }
    )
  }

  async getWorkerCatalog(workerId: string): Promise<RemoteV4CatalogView> {
    return this.fetchApi<RemoteV4CatalogView>(`/api/v2/devices/${encodeURIComponent(workerId)}/catalog`, {
      method: 'GET',
    })
  }

  async patchDevice(workerId: string, input: RemoteDevicePatchInput, idempotencyKey?: string): Promise<RemoteDeviceView> {
    return this.fetchApi(`/api/v2/devices/${encodeURIComponent(workerId)}`, { method: 'PATCH', body: input, idempotencyKey })
  }

  async deleteDevice(workerId: string, idempotencyKey?: string): Promise<RemoteDeviceDeletionView> {
    return this.fetchApi(`/api/v2/devices/${encodeURIComponent(workerId)}`, { method: 'DELETE', idempotencyKey })
  }

  async listApiTokens(cursor?: string, limit?: number, includeRevoked = false): Promise<RemoteApiTokenPage> {
    return this.fetchApi('/api/v2/api-tokens', { params: { cursor, limit, includeRevoked } })
  }

  async issueApiToken(input: RemoteApiTokenCreateInput, idempotencyKey?: string): Promise<RemoteApiTokenIssuedView | RemoteApiTokenIssueReplayView> {
    // No response caching: the one-time secret goes directly to the issuing dialog.
    return this.fetchApi('/api/v2/api-tokens', { method: 'POST', body: input, idempotencyKey })
  }

  async revokeApiToken(tokenId: string, idempotencyKey?: string): Promise<RemoteApiTokenRevocationView> {
    return this.fetchApi(`/api/v2/api-tokens/${encodeURIComponent(tokenId)}`, { method: 'DELETE', idempotencyKey })
  }

  // --- Conversations ---

  async listConversations(params?: {
    workerId?: string
    workspaceId?: string
    cursor?: string
    limit?: number
  }): Promise<RemoteConversationPage> {
    return this.fetchApi<RemoteConversationPage>('/api/v2/conversations', {
      method: 'GET',
      params: {
        workerId: params?.workerId,
        workspaceId: params?.workspaceId,
        cursor: params?.cursor,
        limit: params?.limit,
      },
    })
  }

  async createConversation(
    input: RemoteCreateConversationInput,
    idempotencyKey?: string
  ): Promise<RemoteQueuedReceipt> {
    return this.fetchApi<RemoteQueuedReceipt>('/api/v2/conversations', {
      method: 'POST',
      body: input,
      idempotencyKey,
    })
  }

  async updateConversation(
    conversationId: string,
    input: RemoteSyncConversationInput,
    idempotencyKey?: string
  ): Promise<RemoteQueuedReceipt> {
    return this.fetchApi<RemoteQueuedReceipt>(
      `/api/v2/conversations/${encodeURIComponent(conversationId)}`,
      {
        method: 'PATCH',
        body: input,
        idempotencyKey,
      }
    )
  }

  async getConversation(conversationId: string): Promise<RemoteConversationView> {
    return this.fetchApi<RemoteConversationView>(`/api/v2/conversations/${encodeURIComponent(conversationId)}`, {
      method: 'GET',
    })
  }

  async getConversationSnapshot(conversationId: string): Promise<RemoteConversationSnapshot> {
    return this.fetchApi<RemoteConversationSnapshot>(
      `/api/v2/conversations/${encodeURIComponent(conversationId)}/snapshot`,
      {
        method: 'GET',
      }
    )
  }

  // --- Messages ---

  async sendMessage(
    conversationId: string,
    input: RemoteSendMessageInput,
    idempotencyKey?: string
  ): Promise<RemoteQueuedReceipt> {
    return this.fetchApi<RemoteQueuedReceipt>(
      `/api/v2/conversations/${encodeURIComponent(conversationId)}/messages`,
      {
        method: 'POST',
        body: input,
        idempotencyKey,
      }
    )
  }

  async listMessages(conversationId: string, before?: string, limit?: number): Promise<RemoteSyncMessagePage> {
    return this.fetchApi<RemoteSyncMessagePage>(
      `/api/v2/conversations/${encodeURIComponent(conversationId)}/messages`,
      {
        method: 'GET',
        params: { before, limit },
      }
    )
  }

  // --- Runs & Controls ---

  async listRuns(conversationId: string, cursor?: string, limit?: number): Promise<RemoteRunPage> {
    return this.fetchApi<RemoteRunPage>(
      `/api/v2/conversations/${encodeURIComponent(conversationId)}/runs`,
      {
        method: 'GET',
        params: { cursor, limit },
      }
    )
  }

  async getRun(runId: string): Promise<RemoteRunView> {
    return this.fetchApi<RemoteRunView>(`/api/v2/runs/${encodeURIComponent(runId)}`, {
      method: 'GET',
    })
  }

  async controlRun(
    runId: string,
    input: RemoteRunControlInput,
    idempotencyKey?: string
  ): Promise<RemoteQueuedReceipt> {
    return this.fetchApi<RemoteQueuedReceipt>(`/api/v2/runs/${encodeURIComponent(runId)}/commands`, {
      method: 'POST',
      body: input,
      idempotencyKey,
    })
  }

  // --- Commands ---

  async listCommands(conversationId: string, cursor?: string, limit?: number): Promise<RemoteCommandPage> {
    return this.fetchApi<RemoteCommandPage>(
      `/api/v2/conversations/${encodeURIComponent(conversationId)}/commands`,
      {
        method: 'GET',
        params: { cursor, limit },
      }
    )
  }

  async getCommand(commandId: string): Promise<RemoteCommandView> {
    return this.fetchApi<RemoteCommandView>(`/api/v2/commands/${encodeURIComponent(commandId)}`, {
      method: 'GET',
    })
  }

  async withdrawCommand(
    commandId: string,
    input: RemoteCommandWithdrawalInput,
    idempotencyKey?: string
  ): Promise<RemoteCommandView> {
    return this.fetchApi<RemoteCommandView>(
      `/api/v2/commands/${encodeURIComponent(commandId)}/cancellations`,
      {
        method: 'POST',
        body: input,
        idempotencyKey,
      }
    )
  }

  // --- Approvals ---

  async getApproval(approvalId: string): Promise<RemoteApprovalView> {
    return this.fetchApi<RemoteApprovalView>(`/api/v2/approvals/${encodeURIComponent(approvalId)}`, {
      method: 'GET',
    })
  }

  async decideApproval(
    approvalId: string,
    input: RemoteApprovalDecisionInput,
    idempotencyKey?: string
  ): Promise<RemoteQueuedReceipt> {
    return this.fetchApi<RemoteQueuedReceipt>(
      `/api/v2/approvals/${encodeURIComponent(approvalId)}/decisions`,
      {
        method: 'POST',
        body: input,
        idempotencyKey,
      }
    )
  }

  // --- Events ---

  async listEvents(after?: string, limit?: number): Promise<RemoteBrowserEventPage> {
    return this.fetchApi<RemoteBrowserEventPage>('/api/v2/events', {
      method: 'GET',
      params: { after, limit },
    })
  }
}

export const remoteGateway = new RemoteGateway()
