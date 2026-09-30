import { MockAttachmentLibrary } from '@/shared/attachments/mock-library'
import type { UploadOptions } from '@/shared/attachments/transport'
import type {
  AttachmentDeletedView, RemoteAttachmentView, RemoteAttachmentLimitsView,
  RemoteNativeSessionPage, RemoteNativeSessionView, NativeMessagePage, RemoteNativeImportInput, RemoteResourceQueuedReceipt, DirectoryListingInput, DirectoryListingPage, RemoteWorkspaceRegisterInput, RemoteV4CatalogView,
  RemoteDevicePatchInput,
  RemoteDeviceDeletionView,
  RemoteApiTokenView,
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
  RemoteMessageView,
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
  RemoteBrowserEvent,
  RemoteBrowserEventPage,
  RemoteConversationSnapshot,
} from '@hqagent/protocol'
import { nativeExamples, nativeExampleMessages, nativeExampleText } from './native-examples'
import type { IRemoteGateway, RemoteDeviceFilters } from './remote-gateway.interface'
import { RemoteApiError } from './remote-gateway'
import { getRemoteErrorMessage } from '@/shared/i18n/remote-errors'

export class MockRemoteGateway implements IRemoteGateway {
  public attachmentLibrary = new MockAttachmentLibrary()
  async getAttachmentLimits(): Promise<RemoteAttachmentLimitsView> { return { limits: this.attachmentLibrary.limits, usedBytes: [...this.attachmentLibrary.records.values()].reduce((sum, r) => sum + r.blob.size, 0), reservedBytes: 0, observedAt: new Date().toISOString() } }
  async uploadAttachment(conversationId: string, file: Blob, options: UploadOptions): Promise<RemoteAttachmentView> { return (await this.attachmentLibrary.upload(conversationId, file, options)).remote }
  async getAttachment(id: string): Promise<RemoteAttachmentView> { return this.attachmentLibrary.get(id).remote }
  async deleteAttachment(id: string): Promise<AttachmentDeletedView> { return this.attachmentLibrary.remove(id) }
  async getAttachmentContent(id: string): Promise<Blob> { return this.attachmentLibrary.get(id).blob }
  async getAttachmentThumbnail(id: string): Promise<Blob> { return this.attachmentLibrary.thumbnail(id) }

  public importedNativeIds = new Set<string>()
  async listNativeSessions(workerId: string): Promise<RemoteNativeSessionPage> {
    return { items: nativeExamples(this.catalog.workspaces[0]?.workspaceId || 'workspace_demo').filter((item) => !this.importedNativeIds.has(item.nativeSessionId)).map((item) => ({ ...item, workerId, workerOnline: this.workerOnline })), hasMore: false }
  }
  async getNativeSession(id: string): Promise<RemoteNativeSessionView> {
    const item = (await this.listNativeSessions('worker_demo')).items.find((item) => item.nativeSessionId === id)
    if (!item) throw new RemoteApiError({ message: '会话不存在', code: 'NOT_FOUND', status: 404 })
    return item
  }
  async readNativeMessages(id: string): Promise<NativeMessagePage> {
    if (!this.workerOnline) throw new RemoteApiError({ message: '电脑离线，无法读取原生会话内容', code: 'REMOTE_DEVICE_OFFLINE', status: 409 })
    return nativeExampleMessages(id)
  }
  async importNativeSession(id: string, input: RemoteNativeImportInput): Promise<RemoteResourceQueuedReceipt> {
    const item = await this.getNativeSession(id)
    if (!input.terminalClosedConfirmed || item.activity.activity === 'likely_active') throw new RemoteApiError({ message: '电脑检测到该会话仍在运行', code: 'NATIVE_SESSION_ACTIVE', status: 409 })
    const conversationId = `imported_${id}`
    this.conversations.unshift({ conversationId, title: item.title, workspaceId: item.workspaceId, targetWorkerId: item.workerId, workerStoreId: this.catalog.workerStoreId, authority: 'remote', conversationKind: 'native', agentType: item.agentType, nativeSessionId: id, nativeSourceRevision: item.sourceRevision, nativeActivity: { ...item.activity, activity: 'closed_confirmed' }, createdAt: item.createdAt, updatedAt: item.updatedAt })
    this.messages.push({ messageId: `${conversationId}_history`, conversationId, role: 'assistant', text: nativeExampleText, messageSequence: 1, messageRevision: 1, createdAt: item.createdAt })
    this.importedNativeIds.add(id)
    return this.resourceExample('native.import', { conversationId, nativeSessionId: id, workspaceId: item.workspaceId })
  }
  async listDirectory(_workerId: string, input: DirectoryListingInput): Promise<DirectoryListingPage> {
    return { rootId: input.rootId, rootVersion: input.rootVersion, directoryToken: input.directoryToken || 'example_root_token', hasMore: false,
      entries: input.directoryToken ? [] : [{ name: '示例代码库', isGitRepository: true, directoryToken: 'example_git_token' }, { name: '示例资料', isGitRepository: false, directoryToken: 'example_readonly_token' }] }
  }
  async registerWorkspace(_workerId: string, input: RemoteWorkspaceRegisterInput): Promise<RemoteResourceQueuedReceipt> {
    const workspaceId = `workspace_registered_${this.catalog.workspaces.length}`
    this.catalog.workspaces.push({ workspaceId, name: input.name || '示例项目', displayPath: '', vcs: input.directoryToken === 'example_git_token' ? 'git' : 'none', canWrite: input.directoryToken === 'example_git_token' })
    return this.resourceExample('workspace.register', { workspaceId })
  }
  private resourceExample(type: RemoteResourceQueuedReceipt['type'], resourceRef: NonNullable<RemoteCommandView['resourceRef']>): RemoteResourceQueuedReceipt {
    const commandId = `resource_${crypto.randomUUID()}`
    const receipt: RemoteResourceQueuedReceipt = { commandId, type, targetWorkerId: 'worker_demo', status: 'queued', deliveryState: 'queued_online', workerOnline: true, expiresAt: new Date(Date.now() + 30000).toISOString() }
    this.commands.push({ ...receipt, status: 'completed', resourceRef, withdrawalState: 'none', observedAt: new Date().toISOString(), createdAt: new Date().toISOString() })
    return receipt
  }
  supportsDeviceManagement = true
  public apiTokens: RemoteApiTokenView[] = []
  private tokenIntents = new Map<string, string>()

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
  public syncCreatedConversationImmediately = false

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
      capabilityRevision: 2,
      observedAt: '2026-09-26T12:00:00Z',
      pairedAt: '2026-09-26T12:00:00Z',
      online: true,
      busySnapshotFresh: true,
      supportedWireRevisions: [1, 2],
    },
    {
      workerId: 'worker_home_pc',
      deviceName: 'Home PC (Alex)',
      platform: 'windows',
      architecture: 'x86_64',
      status: 'offline',
      workerStoreId: 'store_home',
      capabilityRevision: 2,
      observedAt: '2026-09-26T12:00:00Z',
      pairedAt: '2026-09-26T12:00:00Z',
      online: false,
      busySnapshotFresh: false,
      supportedWireRevisions: [2],
    },
  ]

  public catalog: RemoteV4CatalogView = {
    workerId: 'worker_demo',
    capabilityRevision: 2,
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
      {
        workspaceId: 'workspace_web',
        name: 'Web-Ecommerce',
        displayPath: 'D:\\Projects\\Web-Ecommerce',
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
      workerId: 'worker_demo',
      authority: 'remote',
      title: '远程分析系统架构',
      workspaceId: 'workspace_demo',
      sceneId: 'analyze',
      sceneVersion: 1,
      createdAt: '2026-09-26T12:00:00Z',
      updatedAt: '2026-09-26T12:00:00Z',
      workerStoreId: 'store_demo',
      visibility: 'both',
      busy: false,
      busyFresh: true,
      metadataVersion: 1,
      archived: false,
    },
    {
      conversationId: 'conv_pc_created_1',
      targetWorkerId: 'worker_demo',
      workerId: 'worker_demo',
      authority: 'local',
      title: '电脑端创建：自动化测试修复',
      workspaceId: 'workspace_demo',
      sceneId: 'develop',
      sceneVersion: 1,
      createdAt: '2026-09-26T13:00:00Z',
      updatedAt: '2026-09-26T13:10:00Z',
      workerStoreId: 'store_demo',
      visibility: 'both',
      busy: false,
      busyFresh: true,
      metadataVersion: 1,
      archived: false,
    },
    {
      conversationId: 'conv_busy_demo_1',
      targetWorkerId: 'worker_demo',
      workerId: 'worker_demo',
      authority: 'remote',
      title: '正在执行：全量编译构建',
      workspaceId: 'workspace_demo',
      sceneId: 'develop',
      sceneVersion: 1,
      createdAt: '2026-09-26T13:30:00Z',
      updatedAt: '2026-09-26T13:35:00Z',
      workerStoreId: 'store_demo',
      visibility: 'both',
      busy: true,
      busyFresh: true,
      busyObservedAt: '2026-09-26T13:35:00Z',
      metadataVersion: 1,
      archived: false,
    },
    {
      conversationId: 'conv_pc_only_1',
      targetWorkerId: 'worker_demo',
      workerId: 'worker_demo',
      authority: 'local',
      title: '电脑私有会话',
      workspaceId: 'workspace_demo',
      sceneId: 'analyze',
      sceneVersion: 1,
      createdAt: '2026-09-26T14:00:00Z',
      updatedAt: '2026-09-26T14:00:00Z',
      workerStoreId: 'store_demo',
      visibility: 'pc_only',
      metadataVersion: 1,
      archived: false,
    },
    {
      conversationId: 'conv_home_1',
      targetWorkerId: 'worker_home_pc',
      workerId: 'worker_home_pc',
      authority: 'remote',
      title: '家庭电脑任务',
      workspaceId: 'workspace_web',
      sceneId: 'analyze',
      sceneVersion: 1,
      createdAt: '2026-09-26T14:30:00Z',
      updatedAt: '2026-09-26T14:30:00Z',
      workerStoreId: 'store_home',
      visibility: 'both',
      metadataVersion: 1,
      archived: false,
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
    {
      messageId: 'msg_003',
      conversationId: 'conversation_demo',
      role: 'user',
      text: '请生成组件关系图',
      createdAt: '2026-09-26T12:01:00Z',
    },
    {
      messageId: 'msg_004',
      conversationId: 'conversation_demo',
      role: 'assistant',
      text: '已生成组件依赖拓扑图，已保存至本地 artifacts 目录。',
      createdAt: '2026-09-26T12:01:20Z',
      runId: 'run_demo',
    },
    {
      messageId: 'msg_pc_1',
      conversationId: 'conv_pc_created_1',
      role: 'user',
      text: '电脑端提交任务：检查测试覆盖率',
      createdAt: '2026-09-26T13:00:00Z',
    },
    {
      messageId: 'msg_pc_2',
      conversationId: 'conv_pc_created_1',
      role: 'assistant',
      text: '测试套件共 50 个文件，全部通过。',
      createdAt: '2026-09-26T13:00:20Z',
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

  async listDevices(cursor?: string, limit = 50, filters: RemoteDeviceFilters = {}): Promise<RemoteDevicePage> {
    const items = this.devices.map((d) => {
      if (d.workerId === 'worker_demo' && d.status !== 'revoked') {
        return {
          ...d,
          status: this.workerOnline ? ('online' as const) : ('offline' as const),
          online: this.workerOnline,
          busySnapshotFresh: this.workerOnline,
        }
      }
      return { ...d }
    })
    const filtered = items.filter((d) => (filters.includeRevoked || d.status !== 'revoked') &&
      (!filters.remoteAccess || (d.remoteAccess || 'enabled') === filters.remoteAccess) &&
      (filters.online === undefined || (d.online ?? d.status === 'online') === filters.online))
    const start = Number(cursor || 0)
    return { items: filtered.slice(start, start + limit), hasMore: start + limit < filtered.length,
      nextCursor: start + limit < filtered.length ? String(start + limit) : undefined }
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
    if (d.workerId === 'worker_demo' && d.status !== 'revoked') {
      return {
        ...d,
        status: this.workerOnline ? 'online' : 'offline',
        online: this.workerOnline,
        busySnapshotFresh: this.workerOnline,
      }
    }
    return { ...d }
  }

  async revokeDevice(workerId: string, _input?: RemoteDeviceRevokeInput): Promise<RemoteDeviceRevocationView> {
    const idx = this.devices.findIndex((d) => d.workerId === workerId)
    if (idx >= 0) {
      this.devices[idx] = { ...this.devices[idx], status: 'revoked', online: false }
    }
    return {
      workerId,
      revokedAt: new Date().toISOString(),
      status: 'revoked',
      executionMayStillBeRunning: true,
    }
  }

  async getWorkerCatalog(workerId: string): Promise<RemoteV4CatalogView> {
    const device = this.devices.find((d) => d.workerId === workerId)
    return { ...this.catalog, workerId, workerStoreId: device?.workerStoreId || this.catalog.workerStoreId }
  }

  async patchDevice(workerId: string, input: RemoteDevicePatchInput): Promise<RemoteDeviceView> {
    const device = this.devices.find((d) => d.workerId === workerId)
    if (!device) throw new RemoteApiError({ message: '设备未找到', code: 'NOT_FOUND', status: 404 })
    if (device.status === 'revoked') throw new RemoteApiError({ message: '设备已撤销', code: 'REMOTE_DEVICE_REVOKED', status: 409 })
    if ((device.version ?? 1) !== input.expectedVersion) throw new RemoteApiError({ message: '资源版本或状态已变化，请刷新后重试', code: 'CONFLICT', status: 409 })
    if (input.displayName !== undefined) {
      if (input.displayName.trim()) device.displayName = input.displayName.trim()
      else delete device.displayName
    }
    if (input.remoteAccess) device.remoteAccess = input.remoteAccess
    device.version = (device.version ?? 1) + 1
    return this.getDevice(workerId)
  }

  async deleteDevice(workerId: string): Promise<RemoteDeviceDeletionView> {
    await this.getDevice(workerId)
    this.devices = this.devices.filter((d) => d.workerId !== workerId)
    this.conversations = this.conversations.filter((c) => c.targetWorkerId !== workerId)
    return { workerId, deletedAt: new Date().toISOString(), executionMayStillBeRunning: true }
  }

  async listApiTokens(cursor?: string, limit = 50, includeRevoked = false): Promise<RemoteApiTokenPage> {
    const items = this.apiTokens.filter((t) => includeRevoked || t.status !== 'revoked')
    const start = Number(cursor || 0)
    return { items: structuredClone(items.slice(start, start + limit)), hasMore: start + limit < items.length,
      nextCursor: start + limit < items.length ? String(start + limit) : undefined }
  }

  async issueApiToken(input: RemoteApiTokenCreateInput, idempotencyKey = crypto.randomUUID()): Promise<RemoteApiTokenIssuedView | RemoteApiTokenIssueReplayView> {
    const existingId = this.tokenIntents.get(idempotencyKey)
    if (existingId) return { token: { ...this.apiTokens.find((t) => t.tokenId === existingId)! }, secretAvailable: false }
    const selector = crypto.randomUUID().replaceAll('-', '').slice(0, 24)
    const token: RemoteApiTokenView = { tokenId: `pat_${selector}`, name: input.name, scopes: [...input.scopes],
      tokenPrefix: `hqr_pat_${selector}`, createdAt: new Date().toISOString(),
      expiresAt: input.expiresAt || new Date(Date.now() + 90 * 86400000).toISOString(), status: 'active' }
    this.apiTokens.unshift(token)
    this.tokenIntents.set(idempotencyKey, token.tokenId)
    // Synthetic, non-authenticating example. The mock stores metadata only, never the full secret.
    return { token: { ...token }, secretAvailable: true, secret: `${token.tokenPrefix}_${'EXAMPLE_ONLY_NOT_FOR_REAL_AUTH_'.padEnd(43, '0')}` }
  }

  async revokeApiToken(tokenId: string): Promise<RemoteApiTokenRevocationView> {
    const token = this.apiTokens.find((t) => t.tokenId === tokenId)
    if (!token) throw new RemoteApiError({ message: '令牌不存在', code: 'NOT_FOUND', status: 404 })
    token.status = 'revoked'
    token.revokedAt ||= new Date().toISOString()
    return { tokenId, status: 'revoked', revokedAt: token.revokedAt }
  }

  // --- Conversations ---

  async listConversations(params?: {
    workerId?: string
    workspaceId?: string
    cursor?: string
    limit?: number
  }): Promise<RemoteConversationPage> {
    // Hide pc_only from mobile
    let items = this.conversations.filter((c) => c.visibility !== 'pc_only')
    if (params?.workerId) {
      items = items.filter((c) => c.targetWorkerId === params.workerId || c.workerId === params.workerId)
    }
    if (params?.workspaceId) {
      items = items.filter((c) => c.workspaceId === params.workspaceId)
    }
    return {
      items: JSON.parse(JSON.stringify(items)),
      hasMore: false,
    }
  }

  async createConversation(input: RemoteCreateConversationInput): Promise<RemoteQueuedReceipt> {
    const convId = `conv_${Date.now()}`
    const newConv: RemoteConversationView = {
      conversationId: convId,
      targetWorkerId: input.targetWorkerId,
      workerId: input.targetWorkerId,
      authority: 'remote',
      title: input.title,
      workspaceId: input.workspaceId,
      sceneId: input.sceneId,
      sceneVersion: input.sceneVersion,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      workerStoreId: input.workerStoreId,
      visibility: 'both',
      busy: false,
      busyFresh: true,
      metadataVersion: 1,
      archived: false,
    }
    if (this.syncCreatedConversationImmediately) {
      this.conversations.unshift(newConv)
    }
    return {
      commandId: `cmd_conv_create_${Date.now()}`,
      conversationId: convId,
      status: 'queued',
      deliveryState: 'queued_online',
      workerOnline: this.workerOnline,
      expiresAt: new Date(Date.now() + 30000).toISOString(),
    }
  }

  async updateConversation(
    conversationId: string,
    input: RemoteSyncConversationInput
  ): Promise<RemoteQueuedReceipt> {
    const conv = this.conversations.find((item) => item.conversationId === conversationId)
    if (!conv) {
      throw new RemoteApiError({
        message: '对话未找到',
        code: 'NOT_FOUND',
        status: 404,
      })
    }
    const currentVersion = conv.metadataVersion ?? 1
    if (input.expectedVersion !== currentVersion) {
      throw new RemoteApiError({
        message: getRemoteErrorMessage('REMOTE_SYNC_CONFLICT'),
        code: 'REMOTE_SYNC_CONFLICT',
        status: 409,
      })
    }
    if (input.title !== undefined) conv.title = input.title.trim()
    if (input.archived !== undefined) conv.archived = input.archived
    if (input.visibility !== undefined) conv.visibility = input.visibility
    conv.metadataVersion = currentVersion + 1
    conv.updatedAt = new Date().toISOString()
    return {
      commandId: `cmd_update_${Date.now()}`,
      conversationId,
      status: 'queued',
      deliveryState: 'queued_online',
      workerOnline: this.workerOnline,
      expiresAt: new Date(Date.now() + 30000).toISOString(),
    }
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
    const conv = this.conversations.find((c) => c.conversationId === conversationId)
    const targetWorker = this.devices.find((d) => d.workerId === conv?.targetWorkerId) || this.devices[0]

    // R1.5 Rule: Offline immediately fails, never queued
    if (!this.workerOnline || targetWorker?.online === false || targetWorker?.status === 'offline') {
      throw new RemoteApiError({
        message: getRemoteErrorMessage('REMOTE_DEVICE_OFFLINE'),
        code: 'REMOTE_DEVICE_OFFLINE',
        status: 409,
      })
    }

    if (targetWorker?.supportedWireRevisions && !targetWorker.supportedWireRevisions.includes(2)) {
      throw new RemoteApiError({
        message: getRemoteErrorMessage('REMOTE_REVISION_REQUIRED'),
        code: 'REMOTE_REVISION_REQUIRED',
        status: 409,
      })
    }

    if (targetWorker?.busySnapshotFresh === false) {
      throw new RemoteApiError({
        message: getRemoteErrorMessage('REMOTE_STATE_NOT_READY'),
        code: 'REMOTE_STATE_NOT_READY',
        status: 409,
      })
    }

    if (conv?.busy) {
      throw new RemoteApiError({
        message: getRemoteErrorMessage('REMOTE_CONVERSATION_BUSY'),
        code: 'REMOTE_CONVERSATION_BUSY',
        status: 409,
      })
    }

    const msgId = `msg_${Date.now()}`
    const cmdId = `cmd_${Date.now()}`
    const seq = this.messages.filter((m) => m.conversationId === conversationId).length + 1

    this.messages.push({
      messageId: msgId,
      conversationId,
      role: 'user',
      text: input.text,
      attachments: input.attachmentIds?.map((id) => { const record = this.attachmentLibrary.get(id); record.remote.state = 'attached'; return { ...record.remote.attachment } }),
      createdAt: new Date().toISOString(),
    })

    const receipt: RemoteQueuedReceipt = {
      commandId: cmdId,
      conversationId,
      status: 'queued',
      deliveryState: 'queued_online',
      workerOnline: this.workerOnline,
      expiresAt: new Date(Date.now() + 30000).toISOString(),
      conversationSeq: seq,
    }

    this.commands.push({
      commandId: cmdId,
      conversationId,
      targetWorkerId: conv?.targetWorkerId || 'worker_demo',
      type: 'run.submit',
      conversationSeq: seq,
      status: 'queued',
      deliveryState: 'queued_online',
      withdrawalState: 'none',
      workerOnline: this.workerOnline,
      observedAt: new Date().toISOString(),
      createdAt: new Date().toISOString(),
      expiresAt: receipt.expiresAt,
    })

    return receipt
  }

  async listMessages(
    conversationId: string,
    before?: string,
    limit = 20
  ): Promise<RemoteSyncMessagePage> {
    const convMsgs = this.messages.filter((m) => m.conversationId === conversationId)
    // Newest first (descending by createdAt)
    let sorted = [...convMsgs].sort(
      (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
    )
    if (before) {
      const beforeIdx = sorted.findIndex((m) => m.messageId === before)
      if (beforeIdx !== -1) {
        sorted = sorted.slice(beforeIdx + 1)
      }
    }
    const pageItems = sorted.slice(0, limit)
    const hasMore = sorted.length > limit
    const nextBefore = hasMore ? pageItems[pageItems.length - 1]?.messageId : undefined

    return {
      items: JSON.parse(JSON.stringify(pageItems)),
      hasMore,
      before: nextBefore,
      snapshotCursor: `snap_${Date.now()}`,
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
    this.pendingEvents = []
    return {
      items,
      nextServerCursor: this.streamCursor,
      hasMore: this.hasMoreEvents,
    }
  }

  mockEmitConversationDeleted(conversationId: string): void {
    this.pendingEvents.push({
      type: 'conversation.deleted',
      serverCursor: `del_${Date.now()}`,
      recordedAt: new Date().toISOString(),
      conversationId,
    })
  }

  mockEmitStoreReset(workerId = 'worker_demo', workerStoreId = 'store_demo'): void {
    this.pendingEvents.push({
      type: 'store.reset',
      serverCursor: `reset_${Date.now()}`,
      recordedAt: new Date().toISOString(),
      workerId,
      workerStoreId,
    })
  }

  reset(): void {
    this.attachmentLibrary.reset()
    this.importedNativeIds.clear()
    this.apiTokens = []
    this.tokenIntents.clear()
    this.supportsDeviceManagement = true
    this.authenticated = true
    this.workerOnline = true
    this.rateLimited = false
    this.pairingErrorCode = null
    this.cursorExpired = false
    this.highRiskApprovalAllowed = false
    this.withdrawalOutcome = 'success'
    this.controlOutcome = 'confirmed'
    this.syncCreatedConversationImmediately = false
    this.eventPages = []
    this.pendingEvents = []
    this.hasMoreEvents = false

    this.devices = [
      {
        workerId: 'worker_demo',
        deviceName: 'Office PC (Alex)',
        platform: 'windows',
        architecture: 'x86_64',
        status: 'online',
        workerStoreId: 'store_demo',
        capabilityRevision: 2,
        observedAt: '2026-09-26T12:00:00Z',
        pairedAt: '2026-09-26T12:00:00Z',
        online: true,
        busySnapshotFresh: true,
        supportedWireRevisions: [1, 2],
      },
      {
        workerId: 'worker_home_pc',
        deviceName: 'Home PC (Alex)',
        platform: 'windows',
        architecture: 'x86_64',
        status: 'offline',
        workerStoreId: 'store_home',
        capabilityRevision: 2,
        observedAt: '2026-09-26T12:00:00Z',
        pairedAt: '2026-09-26T12:00:00Z',
        online: false,
        busySnapshotFresh: false,
        supportedWireRevisions: [2],
      },
    ]

    this.conversations = [
      {
        conversationId: 'conversation_demo',
        targetWorkerId: 'worker_demo',
        workerId: 'worker_demo',
        authority: 'remote',
        title: '远程分析系统架构',
        workspaceId: 'workspace_demo',
        sceneId: 'analyze',
        sceneVersion: 1,
        createdAt: '2026-09-26T12:00:00Z',
        updatedAt: '2026-09-26T12:00:00Z',
        workerStoreId: 'store_demo',
        visibility: 'both',
        busy: false,
        busyFresh: true,
        metadataVersion: 1,
        archived: false,
      },
      {
        conversationId: 'conv_pc_created_1',
        targetWorkerId: 'worker_demo',
        workerId: 'worker_demo',
        authority: 'local',
        title: '电脑端创建：自动化测试修复',
        workspaceId: 'workspace_demo',
        sceneId: 'develop',
        sceneVersion: 1,
        createdAt: '2026-09-26T13:00:00Z',
        updatedAt: '2026-09-26T13:10:00Z',
        workerStoreId: 'store_demo',
        visibility: 'both',
        busy: false,
        busyFresh: true,
        metadataVersion: 1,
        archived: false,
      },
      {
        conversationId: 'conv_busy_demo_1',
        targetWorkerId: 'worker_demo',
        workerId: 'worker_demo',
        authority: 'remote',
        title: '正在执行：全量编译构建',
        workspaceId: 'workspace_demo',
        sceneId: 'develop',
        sceneVersion: 1,
        createdAt: '2026-09-26T13:30:00Z',
        updatedAt: '2026-09-26T13:35:00Z',
        workerStoreId: 'store_demo',
        visibility: 'both',
        busy: true,
        busyFresh: true,
        busyObservedAt: '2026-09-26T13:35:00Z',
        metadataVersion: 1,
        archived: false,
      },
      {
        conversationId: 'conv_pc_only_1',
        targetWorkerId: 'worker_demo',
        workerId: 'worker_demo',
        authority: 'local',
        title: '电脑私有会话',
        workspaceId: 'workspace_demo',
        sceneId: 'analyze',
        sceneVersion: 1,
        createdAt: '2026-09-26T14:00:00Z',
        updatedAt: '2026-09-26T14:00:00Z',
        workerStoreId: 'store_demo',
        visibility: 'pc_only',
        metadataVersion: 1,
        archived: false,
      },
      {
        conversationId: 'conv_home_1',
        targetWorkerId: 'worker_home_pc',
        workerId: 'worker_home_pc',
        authority: 'remote',
        title: '家庭电脑任务',
        workspaceId: 'workspace_web',
        sceneId: 'analyze',
        sceneVersion: 1,
        createdAt: '2026-09-26T14:30:00Z',
        updatedAt: '2026-09-26T14:30:00Z',
        workerStoreId: 'store_home',
        visibility: 'both',
        metadataVersion: 1,
        archived: false,
      },
    ]

    this.messages = [
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
      {
        messageId: 'msg_003',
        conversationId: 'conversation_demo',
        role: 'user',
        text: '请生成组件关系图',
        createdAt: '2026-09-26T12:01:00Z',
      },
      {
        messageId: 'msg_004',
        conversationId: 'conversation_demo',
        role: 'assistant',
        text: '已生成组件依赖拓扑图，已保存至本地 artifacts 目录。',
        createdAt: '2026-09-26T12:01:20Z',
        runId: 'run_demo',
      },
      {
        messageId: 'msg_pc_1',
        conversationId: 'conv_pc_created_1',
        role: 'user',
        text: '电脑端提交任务：检查测试覆盖率',
        createdAt: '2026-09-26T13:00:00Z',
      },
      {
        messageId: 'msg_pc_2',
        conversationId: 'conv_pc_created_1',
        role: 'assistant',
        text: '测试套件共 50 个文件，全部通过。',
        createdAt: '2026-09-26T13:00:20Z',
      },
    ]
  }
}

export const mockRemoteGateway = new MockRemoteGateway()
