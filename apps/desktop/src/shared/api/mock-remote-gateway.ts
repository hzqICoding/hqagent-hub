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
  RemoteMessagePage,
  RemoteMessageView,
  RemoteRunPage,
  RemoteRunView,
  RemoteRunControlInput,
  RemoteCommandPage,
  RemoteCommandView,
  RemoteCommandWithdrawalInput,
  RemoteApprovalView,
  RemoteApprovalDecisionInput,
  RemoteBrowserEvent,
  RemoteBrowserEventPage,
  RemoteConversationSnapshot,
} from '@hqagent/protocol'
import type { IRemoteGateway } from './remote-gateway.interface'
import { RemoteApiError } from './remote-gateway'
import { getRemoteErrorMessage } from '@/shared/i18n/remote-errors'

export class MockRemoteGateway implements IRemoteGateway {
  // Configurable test scenarios
  public authenticated = true
  public workerOnline = true
  public rateLimited = false
  public rateLimitSeconds = 30
  public pairingErrorCode: 'REMOTE_PAIRING_EXPIRED' | 'REMOTE_PAIRING_CONFLICT' | 'REMOTE_PAIRING_INVALID' | null = null
  public cursorExpired = false
  public highRiskApprovalAllowed = false
  public withdrawalOutcome: 'success' | 'too_late' | 'unconfirmed' = 'success'
  public controlOutcome: 'confirmed' | 'rejected' | 'unconfirmed' = 'confirmed'

  // In-memory data structures
  public session: RemoteAuthenticatedSession = {
    authenticated: true,
    account: {
      loginName: 'demo-user',
      displayName: 'Demo',
    },
    expiresAt: '2026-09-26T12:05:00Z',
    csrfToken: 'csrf_mock_token_000000000000000000000000',
  }

  public devices: RemoteDeviceView[] = [
    {
      workerId: 'worker_demo',
      deviceName: 'Office PC (Alex)',
      platform: 'windows',
      architecture: 'x86_64',
      status: 'online',
      workerStoreId: 'store_demo',
      capabilityRevision: 1,
      observedAt: '2026-09-26T12:00:00Z',
      pairedAt: '2026-09-26T12:00:00Z',
    },
  ]

  public catalog: RemoteCatalogView = {
    workerId: 'worker_demo',
    capabilityRevision: 1,
    observedAt: '2026-09-26T12:00:00Z',
    workerStoreId: 'store_demo',
    remotelyBlockedActions: ['git_push', 'deploy', 'delete', 'db_migrate'],
    workspaces: [
      {
        workspaceId: 'workspace_demo',
        name: 'HQAgent-Hub',
        displayPath: 'E:\\OtherPro\\HQAgent-Hub',
        vcs: 'git',
        canWrite: true,
      },
    ],
    scenes: [
      {
        sceneId: 'analyze',
        name: '代码分析',
        version: 1,
        readOnly: false,
      },
      {
        sceneId: 'plan',
        name: '需求规划',
        version: 1,
        readOnly: false,
      },
      {
        sceneId: 'develop',
        name: '代码开发',
        version: 1,
        readOnly: false,
      },
    ],
  }

  public conversations: RemoteConversationView[] = [
    {
      conversationId: 'conversation_demo',
      targetWorkerId: 'worker_demo',
      authority: 'remote',
      title: '远程分析系统架构',
      workspaceId: 'workspace_demo',
      sceneId: 'analyze',
      sceneVersion: 1,
      createdAt: '2026-09-26T12:00:00Z',
      updatedAt: '2026-09-26T12:00:00Z',
      workerStoreId: 'store_demo',
    },
  ]

  public messages: RemoteMessageView[] = [
    {
      messageId: 'msg_001',
      conversationId: 'conversation_demo',
      role: 'user',
      text: '请梳理当前工程的核心类职责与接口关系',
      createdAt: '2026-09-26T12:00:10Z',
    },
    {
      messageId: 'msg_002',
      conversationId: 'conversation_demo',
      role: 'assistant',
      text: '正在分析 HQAgent-Hub 架构，已建立本地上下文索引。',
      createdAt: '2026-09-26T12:00:15Z',
      runId: 'run_demo',
    },
  ]

  public runs: RemoteRunView[] = [
    {
      runId: 'run_demo',
      conversationId: 'conversation_demo',
      status: 'running',
      observedAt: '2026-09-26T12:00:00Z',
      workerOnline: true,
    },
  ]

  public commands: RemoteCommandView[] = [
    {
      commandId: 'cmd_demo_001',
      conversationId: 'conversation_demo',
      targetWorkerId: 'worker_demo',
      type: 'run.submit',
      conversationSeq: 1,
      status: 'accepted',
      deliveryState: 'sent',
      withdrawalState: 'none',
      workerOnline: true,
      observedAt: '2026-09-26T12:00:10Z',
      createdAt: '2026-09-26T12:00:10Z',
      expiresAt: '2026-09-27T12:00:10Z',
    },
  ]

  public approvals: RemoteApprovalView[] = [
    {
      approvalId: 'approval_demo',
      resultRef: {
        runId: 'run_demo',
      },
      action: 'git_push',
      targetSummary: 'push commits to origin/main',
      riskLevel: 'high',
      status: 'pending',
      requestedAt: '2026-09-26T12:00:00Z',
      expiresAt: '2026-09-26T12:05:00Z',
      remoteApprovalAllowed: false,
      workerPolicyRevision: 1,
      denialCode: 'REMOTE_APPROVAL_FORBIDDEN',
    },
  ]

  public streamCursor = 'opaque_server_cursor_001'
  private cursorCounter = 0

  // --- Auth & Session ---

  async login(input: RemoteLoginInput): Promise<RemoteAuthenticatedSession> {
    if (this.rateLimited) {
      throw new RemoteApiError({
        message: getRemoteErrorMessage('REMOTE_RATE_LIMITED'),
        code: 'REMOTE_RATE_LIMITED',
        status: 429,
        retryAfter: this.rateLimitSeconds,
      })
    }

    if (input.loginName === 'wrong' || input.password === 'wrong') {
      throw new RemoteApiError({
        message: '用户名或口令错误',
        code: 'REMOTE_AUTH_REQUIRED',
        status: 401,
      })
    }

    this.authenticated = true
    this.session.account.loginName = input.loginName
    return this.session
  }

  async getSession(): Promise<RemoteBrowserSessionView> {
    if (!this.authenticated) {
      const anon: RemoteAnonymousSession = { authenticated: false }
      return anon
    }
    return this.session
  }

  async logout(): Promise<RemoteAnonymousSession> {
    this.authenticated = false
    const anon: RemoteAnonymousSession = { authenticated: false }
    return anon
  }

  // --- Pairing ---

  async previewPairing(input: RemotePairingPreviewInput): Promise<RemotePairingPreview> {
    if (this.pairingErrorCode) {
      const code = this.pairingErrorCode
      throw new RemoteApiError({
        message: getRemoteErrorMessage(code),
        code,
        status: code === 'REMOTE_PAIRING_EXPIRED' ? 410 : code === 'REMOTE_PAIRING_CONFLICT' ? 409 : 404,
      })
    }

    const code = input.pairCode.trim().toUpperCase()
    if (code === 'INVALID0' || code.length !== 8) {
      throw new RemoteApiError({
        message: getRemoteErrorMessage('REMOTE_PAIRING_INVALID'),
        code: 'REMOTE_PAIRING_INVALID',
        status: 404,
      })
    }
    if (code === 'EXPIRED0') {
      throw new RemoteApiError({
        message: getRemoteErrorMessage('REMOTE_PAIRING_EXPIRED'),
        code: 'REMOTE_PAIRING_EXPIRED',
        status: 410,
      })
    }
    if (code === 'CONFLICT') {
      throw new RemoteApiError({
        message: getRemoteErrorMessage('REMOTE_PAIRING_CONFLICT'),
        code: 'REMOTE_PAIRING_CONFLICT',
        status: 409,
      })
    }

    return {
      pairRequestId: 'pair_demo',
      deviceName: 'Office PC (Alex)',
      platform: 'windows',
      architecture: 'x86_64',
      expiresAt: new Date(Date.now() + 300000).toISOString(),
    }
  }

  async confirmPairing(pairRequestId: string, input: RemotePairingConfirmInput): Promise<RemoteDeviceView> {
    if (this.pairingErrorCode) {
      const code = this.pairingErrorCode
      throw new RemoteApiError({
        message: getRemoteErrorMessage(code),
        code,
        status: code === 'REMOTE_PAIRING_EXPIRED' ? 410 : code === 'REMOTE_PAIRING_CONFLICT' ? 409 : 404,
      })
    }

    const code = input.pairCode.trim().toUpperCase()
    if (code === 'INVALID0') {
      throw new RemoteApiError({
        message: getRemoteErrorMessage('REMOTE_PAIRING_INVALID'),
        code: 'REMOTE_PAIRING_INVALID',
        status: 404,
      })
    }

    const newDevice: RemoteDeviceView = {
      workerId: `worker_${pairRequestId}`,
      deviceName: 'Office PC (Alex)',
      platform: 'windows',
      architecture: 'x86_64',
      status: 'online',
      workerStoreId: 'store_demo',
      capabilityRevision: 1,
      observedAt: new Date().toISOString(),
      pairedAt: new Date().toISOString(),
    }
    this.devices.push(newDevice)
    return newDevice
  }

  // --- Devices ---

  async listDevices(): Promise<RemoteDevicePage> {
    const items = this.devices.map((d) => ({
      ...d,
      status: this.workerOnline ? ('online' as const) : ('offline' as const),
    }))
    return {
      items,
      hasMore: false,
    }
  }

  async getDevice(workerId: string): Promise<RemoteDeviceView> {
    const d = this.devices.find((item) => item.workerId === workerId)
    if (!d) {
      throw new RemoteApiError({
        message: '设备未找到',
        code: 'NOT_FOUND',
        status: 404,
      })
    }
    return {
      ...d,
      status: this.workerOnline ? 'online' : 'offline',
    }
  }

  async revokeDevice(workerId: string, _input?: RemoteDeviceRevokeInput): Promise<RemoteDeviceRevocationView> {
    const idx = this.devices.findIndex((d) => d.workerId === workerId)
    if (idx >= 0) {
      this.devices.splice(idx, 1)
    }
    return {
      workerId,
      revokedAt: new Date().toISOString(),
      status: 'revoked',
      executionMayStillBeRunning: true,
    }
  }

  async getWorkerCatalog(): Promise<RemoteCatalogView> {
    return this.catalog
  }

  // --- Conversations ---

  async listConversations(): Promise<RemoteConversationPage> {
    return {
      items: this.conversations,
      hasMore: false,
    }
  }

  async createConversation(input: RemoteCreateConversationInput): Promise<RemoteConversationView> {
    const newConv: RemoteConversationView = {
      conversationId: `conv_${Date.now()}`,
      targetWorkerId: input.targetWorkerId,
      authority: 'remote',
      title: input.title,
      workspaceId: input.workspaceId,
      sceneId: input.sceneId,
      sceneVersion: 1,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      workerStoreId: 'store_demo',
    }
    this.conversations.unshift(newConv)
    return newConv
  }

  async getConversation(conversationId: string): Promise<RemoteConversationView> {
    const c = this.conversations.find((item) => item.conversationId === conversationId)
    if (!c) {
      throw new RemoteApiError({
        message: '对话未找到',
        code: 'NOT_FOUND',
        status: 404,
      })
    }
    return c
  }

  async getConversationSnapshot(conversationId: string): Promise<RemoteConversationSnapshot> {
    const conv = await this.getConversation(conversationId)
    const runs = this.runs.filter((r) => r.conversationId === conversationId).map((r) => ({
      ...r,
      workerOnline: this.workerOnline,
    }))
    const commands = this.commands.filter((c) => c.conversationId === conversationId).map((c) => ({
      ...c,
      workerOnline: this.workerOnline,
    }))
    const messages = this.messages.filter((m) => m.conversationId === conversationId)
    const approvals = this.approvals
      .filter((a) => a.status === 'pending')
      .map((a) => ({
        ...a,
        remoteApprovalAllowed: this.highRiskApprovalAllowed,
      }))

    this.streamCursor = `snapshot_cursor_${Date.now()}_${++this.cursorCounter}`

    return {
      conversation: conv,
      serverCursor: this.streamCursor,
      observedAt: new Date().toISOString(),
      runs,
      commands,
      messages,
      approvals,
      hasMore: false,
    }
  }

  // --- Messages ---

  async sendMessage(conversationId: string, input: RemoteSendMessageInput): Promise<RemoteQueuedReceipt> {
    const msgId = `msg_${Date.now()}`
    const cmdId = `cmd_${Date.now()}`
    const seq = this.messages.filter((m) => m.conversationId === conversationId).length + 1

    this.messages.push({
      messageId: msgId,
      conversationId,
      role: 'user',
      text: input.text,
      createdAt: new Date().toISOString(),
    })

    const receipt: RemoteQueuedReceipt = {
      commandId: cmdId,
      conversationId,
      status: 'queued',
      deliveryState: this.workerOnline ? 'queued_online' : 'queued_offline',
      workerOnline: this.workerOnline,
      expiresAt: new Date(Date.now() + 86400000).toISOString(),
      conversationSeq: seq,
    }

    this.commands.push({
      commandId: cmdId,
      conversationId,
      targetWorkerId: 'worker_demo',
      type: 'run.submit',
      conversationSeq: seq,
      status: 'queued',
      deliveryState: this.workerOnline ? 'sent' : 'queued_offline',
      withdrawalState: 'none',
      workerOnline: this.workerOnline,
      observedAt: new Date().toISOString(),
      createdAt: new Date().toISOString(),
      expiresAt: receipt.expiresAt,
    })

    return receipt
  }

  async listMessages(conversationId: string): Promise<RemoteMessagePage> {
    const items = this.messages.filter((m) => m.conversationId === conversationId)
    return {
      items,
      hasMore: false,
    }
  }

  // --- Runs & Controls ---

  async listRuns(conversationId: string): Promise<RemoteRunPage> {
    const items = this.runs.filter((r) => r.conversationId === conversationId).map((r) => ({
      ...r,
      workerOnline: this.workerOnline,
    }))
    return {
      items,
      hasMore: false,
    }
  }

  async getRun(runId: string): Promise<RemoteRunView> {
    const r = this.runs.find((item) => item.runId === runId)
    if (!r) {
      throw new RemoteApiError({
        message: '运行未找到',
        code: 'NOT_FOUND',
        status: 404,
      })
    }
    return {
      ...r,
      workerOnline: this.workerOnline,
    }
  }

  async controlRun(runId: string, input: RemoteRunControlInput): Promise<RemoteQueuedReceipt> {
    const cmdId = `ctrl_cmd_${Date.now()}`
    const r = this.runs.find((item) => item.runId === runId)
    const convId = r ? r.conversationId : 'conversation_demo'

    // Update command representation
    const controlResult =
      this.controlOutcome === 'confirmed'
        ? {
            outcome: 'confirmed' as const,
            executionMayStillBeRunning: false,
            orphanProcessIds: [],
            reason: `Action ${input.action} confirmed`,
            evidence: 'adapter_confirmed' as const,
            observedAt: new Date().toISOString(),
          }
        : this.controlOutcome === 'rejected'
          ? {
              outcome: 'rejected' as const,
              executionMayStillBeRunning: true,
              orphanProcessIds: [],
              reason: `Action ${input.action} rejected by adapter`,
              evidence: 'adapter_refused' as const,
              observedAt: new Date().toISOString(),
            }
          : {
              outcome: 'unconfirmed' as const,
              executionMayStillBeRunning: true as const,
              orphanProcessIds: [],
              reason: `Action ${input.action} outcome uncertain`,
              evidence: 'missing_execution_handle' as const,
              observedAt: new Date().toISOString(),
            }

    if (r && this.controlOutcome === 'confirmed') {
      if (input.action === 'pause') r.status = 'paused'
      if (input.action === 'resume') r.status = 'running'
      if (input.action === 'cancel') r.status = 'cancelled'
    }

    this.commands.push({
      commandId: cmdId,
      conversationId: convId,
      targetWorkerId: 'worker_demo',
      type: `run.${input.action}` as RemoteCommandView['type'],
      status: this.controlOutcome === 'confirmed' ? 'completed' : this.controlOutcome === 'rejected' ? 'rejected' : 'accepted',
      deliveryState: this.workerOnline ? 'sent' : 'queued_offline',
      withdrawalState: 'none',
      workerOnline: this.workerOnline,
      observedAt: new Date().toISOString(),
      createdAt: new Date().toISOString(),
      expiresAt: new Date(Date.now() + 300000).toISOString(),
      controlResult,
      resultStatus: this.controlOutcome === 'confirmed' ? 'confirmed' : this.controlOutcome === 'rejected' ? 'rejected' : undefined,
    })

    return {
      commandId: cmdId,
      conversationId: convId,
      status: 'queued',
      deliveryState: this.workerOnline ? 'queued_online' : 'queued_offline',
      workerOnline: this.workerOnline,
      expiresAt: new Date(Date.now() + 300000).toISOString(),
    }
  }

  // --- Commands ---

  async listCommands(conversationId: string): Promise<RemoteCommandPage> {
    const items = this.commands.filter((c) => c.conversationId === conversationId).map((c) => ({
      ...c,
      workerOnline: this.workerOnline,
    }))
    return {
      items,
      hasMore: false,
    }
  }

  async getCommand(commandId: string): Promise<RemoteCommandView> {
    const c = this.commands.find((item) => item.commandId === commandId)
    if (!c) {
      throw new RemoteApiError({
        message: '指令未找到',
        code: 'NOT_FOUND',
        status: 404,
      })
    }
    return {
      ...c,
      workerOnline: this.workerOnline,
    }
  }

  async withdrawCommand(commandId: string, input: RemoteCommandWithdrawalInput): Promise<RemoteCommandView> {
    if (this.withdrawalOutcome === 'too_late') {
      throw new RemoteApiError({
        message: getRemoteErrorMessage('REMOTE_WITHDRAWAL_TOO_LATE'),
        code: 'REMOTE_WITHDRAWAL_TOO_LATE',
        status: 409,
      })
    }

    if (this.withdrawalOutcome === 'unconfirmed') {
      throw new RemoteApiError({
        message: getRemoteErrorMessage('REMOTE_WITHDRAWAL_UNCONFIRMED'),
        code: 'REMOTE_WITHDRAWAL_UNCONFIRMED',
        status: 409,
      })
    }

    const c = this.commands.find((item) => item.commandId === commandId)
    if (!c) {
      throw new RemoteApiError({
        message: '指令未找到',
        code: 'NOT_FOUND',
        status: 404,
      })
    }

    c.status = 'rejected'
    c.withdrawalState = 'confirmed'
    c.resultStatus = 'withdrawn'
    c.controlResult = {
      outcome: 'confirmed',
      executionMayStillBeRunning: false,
      orphanProcessIds: [],
      reason: input.reason || 'Withdrawn by user',
      evidence: 'inbox_tombstone',
      observedAt: new Date().toISOString(),
    }

    return c
  }

  // --- Approvals ---

  async getApproval(approvalId: string): Promise<RemoteApprovalView> {
    const a = this.approvals.find((item) => item.approvalId === approvalId)
    if (!a) {
      throw new RemoteApiError({
        message: '审批未找到',
        code: 'NOT_FOUND',
        status: 404,
      })
    }
    return {
      ...a,
      remoteApprovalAllowed: this.highRiskApprovalAllowed,
    }
  }

  async decideApproval(approvalId: string, input: RemoteApprovalDecisionInput): Promise<RemoteQueuedReceipt> {
    const a = this.approvals.find((item) => item.approvalId === approvalId)
    const isHighRiskAction = a && ['git_push', 'deploy', 'delete', 'db_migrate'].includes(a.action)
    const isDisallowed = !this.highRiskApprovalAllowed || isHighRiskAction

    if (input.decision === 'approve' && isDisallowed) {
      throw new RemoteApiError({
        message: getRemoteErrorMessage('REMOTE_APPROVAL_FORBIDDEN'),
        code: 'REMOTE_APPROVAL_FORBIDDEN',
        status: 403,
      })
    }

    if (a) {
      a.status = input.decision === 'approve' ? 'approved' : 'rejected'
    }

    return {
      commandId: `cmd_approval_${Date.now()}`,
      conversationId: 'conversation_demo',
      status: 'queued',
      deliveryState: this.workerOnline ? 'queued_online' : 'queued_offline',
      workerOnline: this.workerOnline,
      expiresAt: new Date(Date.now() + 300000).toISOString(),
    }
  }

  // --- Events ---

  public eventPages: RemoteBrowserEventPage[] = []
  public pendingEvents: RemoteBrowserEvent[] = []
  public hasMoreEvents = false

  async listEvents(_cursor?: string): Promise<RemoteBrowserEventPage> {
    if (this.cursorExpired) {
      throw new RemoteApiError({
        message: getRemoteErrorMessage('REMOTE_CURSOR_EXPIRED'),
        code: 'REMOTE_CURSOR_EXPIRED',
        status: 410,
      })
    }

    if (this.eventPages.length > 0) {
      const page = this.eventPages.shift()!
      this.streamCursor = page.nextServerCursor
      return page
    }

    this.streamCursor = `opaque_server_cursor_${Date.now()}`
    const items = [...this.pendingEvents]
    return {
      items,
      nextServerCursor: this.streamCursor,
      hasMore: this.hasMoreEvents,
    }
  }
}

export const mockRemoteGateway = new MockRemoteGateway()
