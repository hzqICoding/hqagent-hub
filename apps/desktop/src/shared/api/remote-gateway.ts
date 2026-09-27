import type {
  ApiEnvelope,
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
  RemoteMessagePage,
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
import type { IRemoteGateway } from './remote-gateway.interface'
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
      })
    } catch (err: unknown) {
      throw new RemoteApiError({
        message: err instanceof Error ? err.message : '网络连接失败，请检查网络设置',
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

    if (!response.ok || !envelope || !envelope.success) {
      const code = envelope?.error?.code || (response.status === 429 ? 'REMOTE_RATE_LIMITED' : 'INTERNAL')
      const rawMessage = envelope?.error?.message || response.statusText || '请求失败'
      const localizedMessage = getRemoteErrorMessage(code, rawMessage)

      throw new RemoteApiError({
        message: localizedMessage,
        code,
        status: response.status,
        detail: envelope?.error?.detail,
        retryAfter,
        requestId: envelope?.requestId,
      })
    }

    return envelope.data as T
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

  async listDevices(cursor?: string, limit?: number): Promise<RemoteDevicePage> {
    return this.fetchApi<RemoteDevicePage>('/api/v2/devices', {
      method: 'GET',
      params: { cursor, limit },
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

  async getWorkerCatalog(workerId: string): Promise<RemoteCatalogView> {
    return this.fetchApi<RemoteCatalogView>(`/api/v2/devices/${encodeURIComponent(workerId)}/catalog`, {
      method: 'GET',
    })
  }

  // --- Conversations ---

  async listConversations(cursor?: string, limit?: number): Promise<RemoteConversationPage> {
    return this.fetchApi<RemoteConversationPage>('/api/v2/conversations', {
      method: 'GET',
      params: { cursor, limit },
    })
  }

  async createConversation(
    input: RemoteCreateConversationInput,
    idempotencyKey?: string
  ): Promise<RemoteConversationView> {
    return this.fetchApi<RemoteConversationView>('/api/v2/conversations', {
      method: 'POST',
      body: input,
      idempotencyKey,
    })
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

  async listMessages(conversationId: string, cursor?: string, limit?: number): Promise<RemoteMessagePage> {
    return this.fetchApi<RemoteMessagePage>(
      `/api/v2/conversations/${encodeURIComponent(conversationId)}/messages`,
      {
        method: 'GET',
        params: { cursor, limit },
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
