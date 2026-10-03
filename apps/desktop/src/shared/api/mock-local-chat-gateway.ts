import { MockVerifications } from '@/shared/maintenance/mock-verifications'
import { MockAttachmentLibrary } from '@/shared/attachments/mock-library'
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
  LocalRoleConfig,
  LocalBaseRoleId,
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
  HubEvent,
  TaskDetailView,
  LocalSceneId,
  ErrorCode,
  RemoteLinkView,
  RemoteLinkPairingInput,
  RemoteSyncSettingsView,
  RemoteSyncSettingsInput,
} from '@hqagent/protocol'
import { nativeExamples, nativeExampleMessages, nativeExampleText } from './native-examples'
import { PROTOCOL_VERSION } from '@hqagent/protocol'

import type { LocalChatGateway } from './local-chat-gateway.interface'
import { HubApiError } from './local-hub-gateway'

// Import contract fixtures
import analyzeSceneFixture from '@hqagent/fixtures/local-scene.analyze.json'
import agentsDiscoveryFixture from '@hqagent/fixtures/agents.discovery-partial.json'

export class MockLocalChatGateway implements LocalChatGateway {
  verification = new MockVerifications()
  deletionCleanup: LocalConversationDeletionView['remoteCleanup'] = 'pending'
  private deletionReceipts = new Map<string, { id: string; version: number; result: LocalConversationDeletionView }>()
  async listImageVerifications(options: { includeInactiveModels?: boolean; cursor?: string } = {}): Promise<LocalImageVerificationPage> { return { items: structuredClone(this.verification.states.filter(s=>s.inUse||options.includeInactiveModels).sort((a,b)=>a.target.agentId.localeCompare(b.target.agentId)||(a.target.modelId??'').localeCompare(b.target.modelId??''))), hasMore:false } }
  async startImageVerification(input: StartLocalImageVerificationInput, key:string): Promise<LocalImageVerificationJobView> { return this.verification.start(input,key) }
  async getImageVerificationJob(id:string): Promise<LocalImageVerificationJobView> { return this.verification.get(id) }
  async cancelImageVerification(id:string, _key:string): Promise<LocalImageVerificationJobView> { return this.verification.cancel(id) }
  async deleteLocalConversation(id:string, version:number, key:string): Promise<LocalConversationDeletionView> {
    const previous=this.deletionReceipts.get(key)
    if(previous){if(previous.id!==id||previous.version!==version)throw new HubApiError('幂等意图不同','IDEMPOTENCY_MISMATCH',409);return previous.result}
    const conversation=this.conversations.find(c=>c.id===id)
    if(!conversation)throw new HubApiError('对话不存在','NOT_FOUND',404)
    if((conversation.version??1)!==version)throw new HubApiError('版本已变化','CONFLICT',409,{reason:'version_mismatch',currentVersion:conversation.version??1})
    const blockers=[...this.runs.values()].filter(r=>r.conversationId===id&&['queued','running','waiting_approval','paused'].includes(r.status))
    if(blockers.length)throw new HubApiError('运行未结束','CONFLICT',409,{reason:'active_runs',blockingRunIds:blockers.map(r=>r.id),hasMoreBlockingRuns:false})
    this.conversations=this.conversations.filter(c=>c.id!==id);this.messages.delete(id)
    for(const [runId,run] of this.runs)if(run.conversationId===id)this.runs.delete(runId)
    for(const [attachmentId,record] of this.attachmentLibrary.records)if(record.local.conversationId===id)this.attachmentLibrary.records.delete(attachmentId)
    const result: LocalConversationDeletionView={conversationId:id,localDeleted:true,deletedAt:new Date().toISOString(),remoteCleanup:this.deletionCleanup}
    this.deletionReceipts.set(key,{id,version,result});return result
  }

  public attachmentLibrary = new MockAttachmentLibrary()
  async getAttachmentLimits(): Promise<AttachmentLimits> { return this.attachmentLibrary.limits }
  async uploadAttachment(conversationId: string, file: Blob, options: UploadOptions): Promise<LocalAttachmentView> { return (await this.attachmentLibrary.upload(conversationId, file, options)).local }
  async getAttachment(id: string): Promise<LocalAttachmentView> { return this.attachmentLibrary.get(id).local }
  async deleteAttachment(id: string): Promise<AttachmentDeletedView> { return this.attachmentLibrary.remove(id) }
  async getAttachmentContent(id: string): Promise<Blob> { return this.attachmentLibrary.get(id).blob }
  async getAttachmentThumbnail(id: string): Promise<Blob> { return this.attachmentLibrary.thumbnail(id) }
  async getAttachmentCapabilities(): Promise<AttachmentTargetCapabilities> { return this.attachmentLibrary.capabilities }

  public authorizedRoots: LocalAuthorizedRootsView = { version: 1, roots: [] }
  public importedNativeIds = new Set<string>()
  async listNativeSessions(): Promise<LocalNativeSessionPage> {
    return { items: nativeExamples(this.workspaces[0]?.id || 'workspace_example').filter((item) => !this.importedNativeIds.has(item.nativeSessionId)), hasMore: false }
  }
  async getNativeSession(id: string): Promise<NativeSessionIndex> {
    const item = (await this.listNativeSessions()).items.find((item) => item.nativeSessionId === id)
    if (!item) throw new HubApiError('会话不存在', 'NOT_FOUND', 404)
    return item
  }
  readNativeMessages(id: string): Promise<NativeMessagePage> { return nativeExampleMessages(id) }
  async importNativeSession(id: string, input: RemoteNativeImportInput): Promise<LocalConversationView> {
    const item = await this.getNativeSession(id)
    if (!input.terminalClosedConfirmed || item.activity.activity === 'likely_active') throw new HubApiError('电脑检测到该会话仍在运行', 'NATIVE_SESSION_ACTIVE', 409)
    if (input.sourceRevision !== item.sourceRevision || input.expectedIndexVersion !== item.indexVersion) throw new HubApiError('终端中有新内容，请重新确认', 'NATIVE_SESSION_CHANGED', 409)
    const conversation: LocalConversationView = { id: `imported_${id}`, title: item.title, workspaceId: item.workspaceId, conversationKind: 'native', agentType: item.agentType, nativeSessionId: id,
      nativeSourceRevision: item.sourceRevision, nativeActivity: { ...item.activity, activity: 'closed_confirmed' }, createdAt: item.createdAt, updatedAt: item.updatedAt }
    this.conversations.unshift(conversation)
    this.messages.set(conversation.id, [{ id: `${conversation.id}_history`, conversationId: conversation.id, role: 'assistant', text: nativeExampleText, sequence: 1, createdAt: conversation.createdAt }])
    this.importedNativeIds.add(id)
    return conversation
  }
  async getAuthorizedRoots(): Promise<LocalAuthorizedRootsView> { return structuredClone(this.authorizedRoots) }
  async setAuthorizedRoots(input: LocalAuthorizedRootsInput): Promise<LocalAuthorizedRootsView> {
    if (input.expectedVersion !== this.authorizedRoots.version) throw new HubApiError('授权根目录已变化，请刷新后重试', 'CONFLICT', 409)
    this.authorizedRoots = { version: input.expectedVersion + 1, roots: input.roots.map((root, i) => ({ ...root, rootId: root.rootId || `root_example_${i}`, version: input.expectedVersion + 1 })) }
    return this.getAuthorizedRoots()
  }
  public isMock = true
  private authenticated = true
  private protocolVersion = PROTOCOL_VERSION

  private workspaces: WorkspaceView[] = []
  private agents: AgentView[] = []
  private scenes: LocalSceneView[] = []
  private roleTemplates: LocalRoleTemplateView[] = []
  private conversations: LocalConversationView[] = []
  private messages: Map<string, LocalMessageView[]> = new Map()
  private runs: Map<string, LocalRunView> = new Map()
  private approvals: ApprovalView[] = []
  private sessions: SessionView[] = []
  private events: HubEvent[] = []
  private processedClientMessageIds: Set<string> = new Set()
  private conversationUpdateReceipts = new Map<string, { signature: string; response: LocalConversationView }>()
  private sceneCreateReceipts = new Map<string, { signature: string; response: LocalSceneView }>()
  private roleTemplateWriteReceipts = new Map<string, { signature: string; response: LocalRoleTemplateView }>()
  private eventSeq = 1

  // Remote Link (D44)
  private remoteLink: RemoteLinkView = {
    state: 'unpaired',
    serverOrigin: 'https://hub.example.com',
  }

  // Simulation flags
  public simulateCursorExpired = false
  public simulateSessionNotResumable = false

  constructor() {
    this.reset()
  }

  reset(): void {
    this.verification.reset();this.deletionReceipts.clear();this.deletionCleanup='pending'
    this.attachmentLibrary.reset()
    this.authorizedRoots = { version: 1, roots: [] }
    this.importedNativeIds.clear()
    this.authenticated = true
    this.processedClientMessageIds.clear()
    this.conversationUpdateReceipts.clear()
    this.sceneCreateReceipts.clear()
    this.roleTemplateWriteReceipts.clear()
    this.messages.clear()
    this.runs.clear()
    this.syncSettings = {
      mirrorEnabled: true,
      version: 1,
      syncGeneration: 1,
    }

    // Seed workspaces
    this.workspaces = [
      {
        id: 'ws_local_hub',
        name: 'HQAgent-Hub',
        path: 'E:\\OtherPro\\HQAgent-Hub',
        vcs: 'git',
        branch: 'work/vnext-frontend',
        isClean: true,
        memoryDirPresent: true,
        lastOpenedAt: '2026-09-24T10:00:00Z',
      },
      {
        id: 'ws_demo_project',
        name: 'Web-Ecommerce',
        path: 'D:\\Projects\\Web-Ecommerce',
        vcs: 'git',
        branch: 'main',
        isClean: false,
        memoryDirPresent: true,
        lastOpenedAt: '2026-09-23T18:00:00Z',
      },
    ]

    // Seed agents
    const discoveredList = (agentsDiscoveryFixture as any).discovered || (agentsDiscoveryFixture as any).agents || []
    this.agents = discoveredList.map((a: any) => ({
      ...a,
    }))

    // Seed scenes
    const analyzeScene: LocalSceneView = {
      ...(analyzeSceneFixture as unknown as LocalSceneView),
      isBuiltin: true,
      roles: (analyzeSceneFixture.roles || []).map((r: any) => ({
        ...r,
        agentInstanceId: r.agentInstanceId || (this.agents[0]?.id ?? 'claude-code-local'),
        modelId: 'claude-3-7-sonnet',
        reasoningEffort: 'medium',
      })),
    }

    const planScene: LocalSceneView = {
      id: 'plan' as LocalSceneId,
      name: '需求规划',
      description: '只读分析需求并输出落地实施方案，不修改业务文件',
      readOnly: true,
      version: 1,
      roles: [
        {
          roleId: 'analyst',
          agentInstanceId: this.agents[0]?.id ?? 'claude-code-local',
          instructions: '阅读现有代码与依赖，梳理业务范围与现状约束。',
          modelId: 'claude-3-7-sonnet',
          reasoningEffort: 'high',
          enabled: true,
        },
        {
          roleId: 'planner',
          agentInstanceId: this.agents[1]?.id ?? 'codex-cli-local',
          instructions: '按技术规范输出详细分步拆解方案、验收指标与风险提示。',
          modelId: 'o3-mini',
          reasoningEffort: 'high',
          enabled: true,
        },
      ],
      updatedAt: '2026-09-24T02:00:00Z',
      isBuiltin: true,
    }

    const developScene: LocalSceneView = {
      id: 'develop' as LocalSceneId,
      name: '开发修复',
      description: '在授权项目的隔离工作树中完成编码实施、单测验证与审查',
      readOnly: false,
      version: 2,
      reviewMode: 'original_planner',
      roles: [
        {
          roleId: 'analyst',
          agentInstanceId: this.agents[0]?.id ?? 'claude-code-local',
          instructions: '定位待改动文件范围与调用链路，提出最小改动方案。',
          modelId: 'claude-3-7-sonnet',
          reasoningEffort: 'medium',
          enabled: true,
        },
        {
          roleId: 'planner',
          agentInstanceId: this.agents[0]?.id ?? 'claude-code-local',
          instructions: '先形成可执行计划；开发结束后在原会话中依据冻结证据完成验收。',
          modelId: 'claude-3-7-sonnet',
          reasoningEffort: 'high',
          enabled: true,
        },
        {
          roleId: 'developer',
          agentInstanceId: this.agents[1]?.id ?? 'codex-cli-local',
          instructions: '遵循既有代码规范与架构约束进行编码实现，编写单元测试。',
          modelId: 'o3-mini',
          reasoningEffort: 'high',
          enabled: true,
        },
        {
          roleId: 'reviewer',
          agentInstanceId: this.agents[0]?.id ?? 'claude-code-local',
          instructions: '依据冻结证据核对实施是否满足原方案、验收指标与安全边界，并明确给出结论。',
          modelId: 'claude-3-7-sonnet',
          reasoningEffort: 'high',
          enabled: true,
        },
      ],
      updatedAt: '2026-09-24T03:00:00Z',
      isBuiltin: true,
    }

    this.scenes = [analyzeScene, planScene, developScene]
    this.roleTemplates = [
      {
        id: 'role_template_security_review',
        name: '安全边界审查',
        baseRoleId: 'reviewer',
        instructions: '检查越界修改、敏感信息泄漏、危险操作审批与回滚证据。',
        version: 1,
        createdAt: '2026-09-24T03:10:00Z',
        updatedAt: '2026-09-24T03:10:00Z',
      },
    ]

    // Seed conversations & runs
    const conv1Id = 'conv_analyze_auth'
    const run1Id = 'run_analyze_1'
    const conv1: LocalConversationView = {
      id: conv1Id,
      title: '梳理登录鉴权与连接链路',
      workspaceId: this.workspaces[0].id,
      sceneId: 'analyze',
      createdAt: '2026-09-24T08:00:00Z',
      updatedAt: '2026-09-24T08:05:00Z',
      activeRunId: undefined,
      lastRunId: run1Id,
      version: 1,
      archived: false,
      lastRunStatus: 'succeeded',
    }

    const conv1Messages: LocalMessageView[] = [
      {
        id: 'msg_1_1',
        conversationId: conv1Id,
        sequence: 1,
        role: 'user',
        text: '请分析当前前端与 Worker 之间的 Local Session 鉴权通信路径，指出哪些位置使用了 Cookie，是否有安全隐患。',
        createdAt: '2026-09-24T08:00:00Z',
      },
      {
        id: 'msg_1_2',
        conversationId: conv1Id,
        sequence: 2,
        role: 'system',
        text: '【代码分析 (Analyst)】已完成代码静态扫描与调用链排查，生成了结构化时序报告。',
        runId: run1Id,
        createdAt: '2026-09-24T08:02:00Z',
      },
      {
        id: 'msg_1_3',
        conversationId: conv1Id,
        sequence: 3,
        role: 'assistant',
        text: `### 本地鉴权链路分析报告

经过对 \`packages/protocol/openapi/local-chat.v2.yaml\` 及前端网关的梳理，结论如下：

1. **会话建立**：
   - 用户输入一次性连接码通过 \`POST /api/v2/auth/local-session\` 校验。
   - 服务端下发 \`HttpOnly; SameSite=Strict\` Cookie（名为 \`hqagent_local_session\`）。
2. **安全隔离**：
   - 浏览器端完全不存储 Hub Token 或敏感密钥在 \`localStorage\` 中。
   - 所有 \`fetchApi\` 请求显式配置 \`credentials: 'include'\`。
3. **零跨站风险**：
   - Web 资源与 API 均运行于本地 Worker 同源环境，杜绝外部网页劫持。`,
        runId: run1Id,
        createdAt: '2026-09-24T08:05:00Z',
      },
    ]

    const run1Task: TaskDetailView = {
      id: 'task_run_1',
      objective: '梳理登录鉴权与连接链路',
      workspaceId: this.workspaces[0].id,
      workspaceName: this.workspaces[0].name,
      profileId: 'prof_analyze',
      profileName: '代码分析',
      status: 'succeeded',
      source: 'desktop',
      createdAt: '2026-09-24T08:00:05Z',
      updatedAt: '2026-09-24T08:05:00Z',
      durationMs: 295000,
      nodes: [
        {
          id: 'node_run_1_1',
          taskId: 'task_run_1',
          roleId: 'analyst',
          resolvedAgentId: this.agents[0]?.id ?? 'claude-code-local',
          resolvedAgentName: 'Claude Code',
          resolveSource: 'workspace_profile',
          status: 'succeeded',
          startedAt: '2026-09-24T08:00:10Z',
          completedAt: '2026-09-24T08:04:55Z',
          outputSummary: '检索 18 个涉及鉴权的文件，完成调用链梳理',
          changedFiles: [],
        },
      ],
      artifacts: [
        {
          id: 'art_1',
          taskId: 'task_run_1',
          title: 'auth-sequence-analysis.md',
          path: '.hqagent/reports/auth-sequence-analysis.md',
          type: 'report',
          sizeBytes: 4280,
          createdAt: '2026-09-24T08:04:50Z',
        },
      ],
      events: [],
    }

    const run1: LocalRunView = {
      id: run1Id,
      conversationId: conv1Id,
      messageId: 'msg_1_1',
      taskId: 'task_run_1',
      sceneSnapshot: JSON.parse(JSON.stringify(analyzeScene)),
      status: 'succeeded',
      createdAt: '2026-09-24T08:00:05Z',
      updatedAt: '2026-09-24T08:05:00Z',
      task: run1Task,
    }

    // Conv 2: Develop (Running / Interactive)
    const conv2Id = 'conv_develop_ui'
    const run2Id = 'run_develop_2'
    const conv2: LocalConversationView = {
      id: conv2Id,
      title: '实现 N0 本地角色对话工作台',
      workspaceId: this.workspaces[0].id,
      sceneId: 'develop',
      createdAt: '2026-09-24T09:30:00Z',
      updatedAt: '2026-09-24T09:32:00Z',
      activeRunId: run2Id,
      lastRunId: run2Id,
      version: 1,
      archived: false,
      lastRunStatus: 'running',
    }

    const conv2Messages: LocalMessageView[] = [
      {
        id: 'msg_2_1',
        conversationId: conv2Id,
        sequence: 1,
        role: 'user',
        text: '请构建对话工作台前端，复用 HqVirtualList 与 HqMarkdown，并支持三栏布局与场景快照抽屉。',
        createdAt: '2026-09-24T09:30:00Z',
      },
      {
        id: 'msg_2_2',
        conversationId: conv2Id,
        sequence: 2,
        role: 'system',
        text: '【代码分析 (Analyst)】分析现有组件库能力，规划 ChatPage.vue 结构。已完成。',
        runId: run2Id,
        createdAt: '2026-09-24T09:31:00Z',
      },
      {
        id: 'msg_2_3',
        conversationId: conv2Id,
        sequence: 3,
        role: 'system',
        text: '【项目开发 (Developer)】正在编写 ChatPage.vue 及辅助卡片组件...',
        runId: run2Id,
        createdAt: '2026-09-24T09:32:00Z',
      },
    ]

    const run2Task: TaskDetailView = {
      id: 'task_run_2',
      objective: '实现 N0 本地角色对话工作台',
      workspaceId: this.workspaces[0].id,
      workspaceName: this.workspaces[0].name,
      profileId: 'prof_develop',
      profileName: '开发修复',
      status: 'running',
      source: 'desktop',
      createdAt: '2026-09-24T09:30:05Z',
      updatedAt: '2026-09-24T09:32:00Z',
      currentRole: 'developer',
      currentAgent: 'Codex CLI',
      nodes: [
        {
          id: 'node_run_2_1',
          taskId: 'task_run_2',
          roleId: 'planner',
          resolvedAgentId: this.agents[0]?.id ?? 'claude-code-local',
          resolvedAgentName: 'Claude Code',
          resolveSource: 'workspace_profile',
          status: 'succeeded',
          startedAt: '2026-09-24T09:30:10Z',
          completedAt: '2026-09-24T09:31:00Z',
          outputSummary: 'UI 方案已确认',
          phase: 'execution',
          sessionId: 'session_planner_run_2',
          externalSessionId: 'native_planner_run_2',
        },
        {
          id: 'node_run_2_2',
          taskId: 'task_run_2',
          roleId: 'developer',
          resolvedAgentId: this.agents[1]?.id ?? 'codex-cli-local',
          resolvedAgentName: 'Codex CLI',
          resolveSource: 'capability_match',
          status: 'running',
          phase: 'execution',
          sessionId: 'session_developer_run_2',
          externalSessionId: 'native_developer_run_2',
          startedAt: '2026-09-24T09:31:05Z',
          changedFiles: [
            'apps/desktop/src/pages/chat/ChatPage.vue',
            'apps/desktop/src/stores/chat.store.ts',
          ],
        },
        {
          id: 'node_run_2_3',
          taskId: 'task_run_2',
          roleId: 'planner',
          resolvedAgentId: this.agents[0]?.id ?? 'claude-code-local',
          resolvedAgentName: 'Claude Code',
          resolveSource: 'workspace_profile',
          status: 'pending',
          phase: 'acceptance',
          sessionId: 'session_planner_run_2',
          externalSessionId: 'native_planner_run_2',
          reviewSourceNodeId: 'node_run_2_2',
          reviewEvidenceId: 'evidence_run_2_pending',
        },
      ],
      artifacts: [],
      events: [],
    }

    const run2: LocalRunView = {
      id: run2Id,
      conversationId: conv2Id,
      messageId: 'msg_2_1',
      taskId: 'task_run_2',
      sceneSnapshot: JSON.parse(JSON.stringify(developScene)),
      status: 'running',
      createdAt: '2026-09-24T09:30:05Z',
      updatedAt: '2026-09-24T09:32:00Z',
      task: run2Task,
    }

    // Conv 3: Waiting Approval
    const conv3Id = 'conv_plan_security'
    const run3Id = 'run_plan_3'
    const approvalId = 'appr_shell_git'
    const conv3: LocalConversationView = {
      id: conv3Id,
      title: '生产环境构建与验证',
      workspaceId: this.workspaces[0].id,
      sceneId: 'plan',
      createdAt: '2026-09-24T10:10:00Z',
      updatedAt: '2026-09-24T10:12:00Z',
      activeRunId: run3Id,
      lastRunId: run3Id,
      version: 1,
      archived: false,
      lastRunStatus: 'waiting_approval',
    }

    const conv3Messages: LocalMessageView[] = [
      {
        id: 'msg_3_1',
        conversationId: conv3Id,
        sequence: 1,
        role: 'user',
        text: '准备部署脚本并验证环境配置。',
        createdAt: '2026-09-24T10:10:00Z',
      },
      {
        id: 'msg_3_2',
        conversationId: conv3Id,
        sequence: 2,
        role: 'system',
        text: '【安全审批】任务触发危险操作：git_push，需要人工确认审批。',
        runId: run3Id,
        createdAt: '2026-09-24T10:12:00Z',
      },
    ]

    const run3Task: TaskDetailView = {
      id: 'task_run_3',
      objective: '生产环境构建与验证',
      workspaceId: this.workspaces[0].id,
      workspaceName: this.workspaces[0].name,
      profileId: 'prof_plan',
      profileName: '需求规划',
      status: 'waiting_approval',
      source: 'desktop',
      createdAt: '2026-09-24T10:10:05Z',
      updatedAt: '2026-09-24T10:12:00Z',
      pendingApprovalId: approvalId,
      nodes: [
        {
          id: 'node_run_3_1',
          taskId: 'task_run_3',
          roleId: 'analyst',
          resolvedAgentId: this.agents[0]?.id ?? 'claude-code-local',
          resolvedAgentName: 'Claude Code',
          resolveSource: 'workspace_profile',
          status: 'waiting_approval',
        },
      ],
      artifacts: [],
      events: [],
    }

    const run3: LocalRunView = {
      id: run3Id,
      conversationId: conv3Id,
      messageId: 'msg_3_1',
      taskId: 'task_run_3',
      sceneSnapshot: JSON.parse(JSON.stringify(planScene)),
      status: 'waiting_approval',
      createdAt: '2026-09-24T10:10:05Z',
      updatedAt: '2026-09-24T10:12:00Z',
      task: run3Task,
    }

    const archivedConversation: LocalConversationView = {
      id: 'conv_archived_checkout',
      title: '已归档的结算页排查',
      workspaceId: this.workspaces[1].id,
      sceneId: 'analyze',
      createdAt: '2026-09-20T08:00:00Z',
      updatedAt: '2026-09-20T09:00:00Z',
      version: 2,
      archived: true,
      lastRunStatus: 'succeeded',
    }

    const remoteConvId = 'conv_remote_mobile'
    const remoteRunId = 'run_remote_1'
    const remoteConversation: LocalConversationView = {
      id: remoteConvId,
      title: '手机远程：排查订单超时',
      workspaceId: this.workspaces[0].id,
      sceneId: 'analyze',
      createdAt: '2026-09-26T14:00:00Z',
      updatedAt: '2026-09-26T14:10:00Z',
      version: 1,
      archived: false,
      authority: 'remote',
      visibility: 'both',
      busy: true,
      busyObservedAt: '2026-09-26T14:10:00Z',
      lastRunStatus: 'running',
      activeRunId: remoteRunId,
    }
    const mobileOnlyConvId = 'conv_mobile_only_1'
    const mobileOnlyConversation: LocalConversationView = {
      id: mobileOnlyConvId,
      title: '手机专用：紧急生产巡检',
      workspaceId: this.workspaces[0].id,
      sceneId: 'analyze',
      createdAt: '2026-09-26T15:00:00Z',
      updatedAt: '2026-09-26T15:10:00Z',
      version: 1,
      archived: false,
      authority: 'remote',
      visibility: 'mobile_only',
      lastRunStatus: 'succeeded',
    }
    const remoteMessages: LocalMessageView[] = [
      {
        id: 'msg_remote_1',
        conversationId: remoteConvId,
        sequence: 1,
        role: 'user',
        text: '来自手机端指令：排查订单超时告警并定位日志',
        createdAt: '2026-09-26T14:00:00Z',
      },
      {
        id: 'msg_remote_2',
        conversationId: remoteConvId,
        sequence: 2,
        role: 'assistant',
        text: '已在本地电脑执行分析：识别到订单超时主要由于数据库连接池等待。',
        runId: remoteRunId,
        createdAt: '2026-09-26T14:00:10Z',
      },
    ]
    const remoteRun: LocalRunView = {
      id: remoteRunId,
      conversationId: remoteConvId,
      messageId: 'msg_remote_1',
      taskId: 'task_run_remote_1',
      sceneSnapshot: JSON.parse(JSON.stringify(analyzeSceneFixture)),
      status: 'running',
      createdAt: '2026-09-26T14:00:05Z',
      updatedAt: '2026-09-26T14:00:10Z',
    }

    this.conversations = [conv2, conv1, remoteConversation, mobileOnlyConversation, conv3, archivedConversation]
    this.messages.set(conv1Id, conv1Messages)
    this.messages.set(conv2Id, conv2Messages)
    this.messages.set(conv3Id, conv3Messages)
    this.messages.set(remoteConvId, remoteMessages)
    this.messages.set(mobileOnlyConvId, [])
    this.runs.set(run1Id, run1)
    this.runs.set(run2Id, run2)
    this.runs.set(run3Id, run3)
    this.runs.set(remoteRunId, remoteRun)
    this.remoteLink = {
      state: 'unpaired',
      serverOrigin: 'https://hub.example.com',
    }

    // Seed approvals
    this.approvals = [
      {
        id: approvalId,
        taskId: 'task_run_3',
        taskObjective: '生产环境构建与验证',
        requestAgentId: this.agents[0]?.id ?? 'claude-code-local',
        requestAgentName: 'Claude Code',
        action: 'git_push',
        targetResource: 'origin/work/vnext-frontend',
        riskLevel: 'high',
        status: 'pending',
        requestedAt: '2026-09-24T10:12:00Z',
        details: {
          branch: 'work/vnext-frontend',
          remote: 'origin',
        },
      },
    ]

    // Seed sessions
    this.sessions = [
      {
        id: 'sess_1',
        agentInstanceId: this.agents[0]?.id ?? 'claude-code-local',
        agentDisplayName: 'Claude Code',
        workspaceId: this.workspaces[0].id,
        workspaceName: this.workspaces[0].name,
        roleId: 'analyst',
        status: 'active',
        isValid: true,
        purpose: 'architect',
        reusePolicy: 'new_session',
        createdAt: '2026-09-24T08:00:00Z',
        lastUsedAt: '2026-09-24T08:05:00Z',
      },
      {
        id: 'sess_2',
        agentInstanceId: this.agents[1]?.id ?? 'codex-cli-local',
        agentDisplayName: 'Codex CLI',
        workspaceId: this.workspaces[0].id,
        workspaceName: this.workspaces[0].name,
        roleId: 'developer',
        status: 'active',
        isValid: true,
        purpose: 'implement',
        reusePolicy: 'continue_lineage',
        createdAt: '2026-09-24T09:30:00Z',
        lastUsedAt: '2026-09-24T09:32:00Z',
      },
    ]

    // Seed events
    this.events = [
      {
        eventId: 'evt_1',
        seq: 1,
        aggregateType: 'task',
        aggregateId: 'task_run_1',
        type: 'task.status_changed',
        occurredAt: '2026-09-24T08:05:00Z',
        payload: {
          taskId: 'task_run_1',
          from: 'running',
          to: 'succeeded',
        },
        protocolVersion: PROTOCOL_VERSION,
      },
      {
        eventId: 'evt_2',
        seq: 2,
        aggregateType: 'task',
        aggregateId: 'task_run_2',
        type: 'task.status_changed',
        occurredAt: '2026-09-24T09:30:05Z',
        payload: {
          taskId: 'task_run_2',
          from: 'queued',
          to: 'running',
        },
        protocolVersion: PROTOCOL_VERSION,
      },
    ]
    this.eventSeq = 3
  }

  // Auth
  async getLocalAuthStatus(): Promise<LocalAuthView> {
    return {
      authenticated: this.authenticated,
      protocolVersion: this.protocolVersion,
    }
  }

  async openLocalSession(input: LocalAuthInput): Promise<LocalAuthView> {
    if (!input.code || input.code.trim().length < 6) {
      throw new HubApiError(
        '连接码格式无效，必须至少包含 6 位字符',
        'VALIDATION_FAILED' as ErrorCode,
        422
      )
    }

    if (input.code === 'expired_code') {
      throw new HubApiError(
        '连接码已过期，请在 Worker 控制台获取最新连接码',
        'UNAUTHORIZED' as ErrorCode,
        401
      )
    }

    this.authenticated = true
    return {
      authenticated: true,
      protocolVersion: this.protocolVersion,
    }
  }

  async logoutLocalSession(): Promise<LocalAuthView> {
    this.authenticated = false
    return {
      authenticated: false,
      protocolVersion: this.protocolVersion,
    }
  }

  // Agents & Models
  async listLocalAgents(): Promise<AgentView[]> {
    return [...this.agents]
  }

  async discoverLocalAgents(): Promise<AgentDiscoveryResult> {
    return {
      total: this.agents.length,
      discovered: [...this.agents],
      timestamp: new Date().toISOString(),
    }
  }

  async getAgentModels(agentId: string): Promise<LocalAgentModelsView> {
    if (agentId.includes('claude')) {
      return {
        agentInstanceId: agentId,
        verified: true,
        models: [
          {
            id: 'claude-3-7-sonnet',
            name: 'Claude 3.7 Sonnet (Hybrid Reasoning)',
            efforts: ['low', 'medium', 'high'],
            isDefault: true,
          },
          {
            id: 'claude-3-5-sonnet',
            name: 'Claude 3.5 Sonnet',
            efforts: ['low'],
            isDefault: false,
          },
          {
            id: 'claude-3-5-haiku',
            name: 'Claude 3.5 Haiku',
            efforts: ['low'],
            isDefault: false,
          },
        ],
      }
    }

    if (agentId.includes('codex') || agentId.includes('openai')) {
      return {
        agentInstanceId: agentId,
        verified: true,
        models: [
          {
            id: 'o3-mini',
            name: 'OpenAI o3-mini',
            efforts: ['low', 'medium', 'high'],
            isDefault: true,
          },
          {
            id: 'gpt-4o',
            name: 'OpenAI GPT-4o',
            efforts: ['low'],
            isDefault: false,
          },
        ],
      }
    }

    // Unverified model catalog scenario
    return {
      agentInstanceId: agentId,
      verified: false,
      models: [],
      reason: '未检测到可用供应商模型配置，支持手动指定由后端验证',
    }
  }

  // Workspaces
  async listLocalWorkspaces(): Promise<WorkspaceView[]> {
    return [...this.workspaces]
  }

  async addLocalWorkspace(input: AddWorkspaceInput): Promise<WorkspaceView> {
    const newWs: WorkspaceView = {
      id: `ws_${Date.now()}`,
      name: input.path.split(/[\\/]/).filter(Boolean).pop() || 'Workspace',
      path: input.path,
      vcs: 'git',
      branch: 'main',
      isClean: true,
      memoryDirPresent: false,
      lastOpenedAt: new Date().toISOString(),
    }
    this.workspaces.unshift(newWs)
    return newWs
  }

  // Scenes
  async pickLocalDirectory(_input: PickLocalDirectoryInput): Promise<PickLocalDirectoryView> {
    // Mock mode never opens a native dialog or registers a fictitious real folder.
    return { cancelled: true }
  }

  // Scenes
  async listLocalScenes(): Promise<LocalSceneView[]> {
    return JSON.parse(JSON.stringify(this.scenes))
  }

  private validateSceneRoles(roles: LocalRoleConfig[], reviewMode: string | undefined, strictPlannerOrder: boolean): void {
    const baseRoles: LocalBaseRoleId[] = ['analyst', 'planner', 'developer', 'reviewer']
    if (roles.length < 1 || roles.length > 4) {
      throw new HubApiError('场景需要配置 1 到 4 个顺序阶段。', 'VALIDATION_FAILED' as ErrorCode, 422)
    }
    if (new Set(roles.map((role) => role.roleId)).size !== roles.length) {
      throw new HubApiError('同一基础角色在场景中最多出现一次。', 'VALIDATION_FAILED' as ErrorCode, 422)
    }
    if (roles.some((role) => !baseRoles.includes(role.roleId as LocalBaseRoleId))) {
      throw new HubApiError('场景阶段必须继承内置基础角色。', 'VALIDATION_FAILED' as ErrorCode, 422)
    }
    if (!roles.some((role) => role.enabled)) {
      throw new HubApiError('场景至少需要一个启用阶段。', 'VALIDATION_FAILED' as ErrorCode, 422)
    }
    for (const role of roles) {
      const hasTemplateId = role.roleTemplateId !== undefined
      const hasTemplateVersion = role.roleTemplateVersion !== undefined
      if (hasTemplateId !== hasTemplateVersion) {
        throw new HubApiError('模板来源 ID 与版本必须同时提供。', 'VALIDATION_FAILED' as ErrorCode, 422)
      }
      if (hasTemplateId) {
        if (!role.roleTemplateId?.trim()
          || !Number.isInteger(role.roleTemplateVersion)
          || (role.roleTemplateVersion || 0) < 1) {
          throw new HubApiError('角色模板来源 ID 必须非空且版本必须为正整数。', 'VALIDATION_FAILED' as ErrorCode, 422)
        }
        const template = this.roleTemplates.find((item) => item.id === role.roleTemplateId)
        if (!template || template.baseRoleId !== role.roleId || (role.roleTemplateVersion || 0) > template.version) {
          throw new HubApiError('角色模板来源与基础类型或版本不匹配。', 'VALIDATION_FAILED' as ErrorCode, 422)
        }
      }
    }
    if (reviewMode === 'original_planner') {
      const enabledIds = roles.filter((role) => role.enabled).map((role) => role.roleId)
      if (strictPlannerOrder && enabledIds.join(',') !== 'planner,developer,reviewer') {
        throw new HubApiError(
          '自定义场景的原规划者验收要求启用阶段严格为 Planner → Developer → Reviewer。',
          'VALIDATION_FAILED' as ErrorCode,
          422
        )
      }
      const planner = roles.find((role) => role.roleId === 'planner')
      const developer = roles.find((role) => role.roleId === 'developer')
      const reviewer = roles.find((role) => role.roleId === 'reviewer')
      if (!planner?.enabled || !developer?.enabled || !reviewer?.enabled || !planner.agentInstanceId?.trim()) {
        throw new HubApiError(
          '原规划者验收需要启用 Planner、Developer、Reviewer 并配置 Planner Agent。',
          'VALIDATION_FAILED' as ErrorCode,
          422
        )
      }
    }
  }

  private normalizeSceneRoles(roles: LocalRoleConfig[], reviewMode?: string): LocalRoleConfig[] {
    const result = roles.map((role) => ({ ...role }))
    if (reviewMode === 'original_planner') {
      const planner = result.find((role) => role.roleId === 'planner')!
      const reviewer = result.find((role) => role.roleId === 'reviewer')!
      reviewer.agentInstanceId = planner.agentInstanceId
      reviewer.modelId = planner.modelId
      reviewer.reasoningEffort = planner.reasoningEffort
    }
    return result
  }

  async createLocalScene(
    input: CreateLocalSceneInput,
    idempotencyKey: string
  ): Promise<LocalSceneView> {
    if (!idempotencyKey) {
      throw new HubApiError('缺少 Idempotency-Key', 'VALIDATION_FAILED' as ErrorCode, 422)
    }
    const signature = JSON.stringify(input)
    const previous = this.sceneCreateReceipts.get(idempotencyKey)
    if (previous) {
      if (previous.signature !== signature) {
        throw new HubApiError('同一 Idempotency-Key 不能用于不同请求', 'IDEMPOTENCY_MISMATCH' as ErrorCode, 409)
      }
      return JSON.parse(JSON.stringify(previous.response))
    }
    if (!input.name.trim()) {
      throw new HubApiError('场景名称不能为空。', 'VALIDATION_FAILED' as ErrorCode, 422)
    }
    this.validateSceneRoles(input.roles, input.reviewMode, true)
    const roles = this.normalizeSceneRoles(input.roles, input.reviewMode)
    const now = new Date().toISOString()
    const scene: LocalSceneView = {
      id: `scene_custom_${Date.now()}_${this.scenes.length}`,
      name: input.name.trim(),
      description: input.description?.trim() || '',
      readOnly: !roles.some((role) => role.enabled && role.roleId === 'developer'),
      version: 1,
      roles,
      updatedAt: now,
      reviewMode: input.reviewMode ?? 'independent',
      isBuiltin: false,
    }
    this.scenes.push(scene)
    const response = JSON.parse(JSON.stringify(scene)) as LocalSceneView
    this.sceneCreateReceipts.set(idempotencyKey, { signature, response })
    return JSON.parse(JSON.stringify(response))
  }

  async saveLocalScene(
    sceneId: string,
    input: SaveLocalSceneInput
  ): Promise<LocalSceneView> {
    const scene = this.scenes.find((s) => s.id === sceneId)
    if (!scene) {
      throw new HubApiError('场景未找到', 'NOT_FOUND' as ErrorCode, 404)
    }

    if (input.expectedVersion !== scene.version) {
      throw new HubApiError(
        `配置版本冲突：当前版本为 ${scene.version}，提交期望版本为 ${input.expectedVersion}。请刷新获取最新配置。`,
        'CONFLICT' as ErrorCode,
        409,
        { currentVersion: scene.version, expectedVersion: input.expectedVersion }
      )
    }

    const isBuiltin = scene.isBuiltin ?? ['analyze', 'plan', 'develop'].includes(scene.id)
    if (isBuiltin && input.roles.map((role) => role.roleId).join(',') !== scene.roles.map((role) => role.roleId).join(',')) {
      throw new HubApiError('内置场景的角色集合与顺序不可修改。', 'VALIDATION_FAILED' as ErrorCode, 422)
    }
    this.validateSceneRoles(input.roles, input.reviewMode, !isBuiltin)
    if (!isBuiltin && input.name !== undefined && !input.name.trim()) {
      throw new HubApiError('场景名称不能为空。', 'VALIDATION_FAILED' as ErrorCode, 422)
    }

    scene.roles = this.normalizeSceneRoles(input.roles, input.reviewMode)
    scene.reviewMode = input.reviewMode ?? 'independent'
    if (!isBuiltin) {
      if (input.name !== undefined) scene.name = input.name.trim()
      if (input.description !== undefined) scene.description = input.description.trim()
    }
    scene.readOnly = !scene.roles.some((role) => role.enabled && role.roleId === 'developer')
    scene.version += 1
    scene.updatedAt = new Date().toISOString()
    return JSON.parse(JSON.stringify(scene))
  }

  async listLocalRoleTemplates(): Promise<LocalRoleTemplateView[]> {
    return JSON.parse(JSON.stringify(this.roleTemplates))
  }

  async createLocalRoleTemplate(
    input: CreateLocalRoleTemplateInput,
    idempotencyKey: string
  ): Promise<LocalRoleTemplateView> {
    if (!idempotencyKey) {
      throw new HubApiError('缺少 Idempotency-Key', 'VALIDATION_FAILED' as ErrorCode, 422)
    }
    const signature = JSON.stringify(input)
    const previous = this.roleTemplateWriteReceipts.get(idempotencyKey)
    if (previous) {
      if (previous.signature !== signature) {
        throw new HubApiError('同一 Idempotency-Key 不能用于不同请求', 'IDEMPOTENCY_MISMATCH' as ErrorCode, 409)
      }
      return JSON.parse(JSON.stringify(previous.response))
    }
    if (!input.name.trim()) {
      throw new HubApiError('模板名称不能为空。', 'VALIDATION_FAILED' as ErrorCode, 422)
    }
    if (!['analyst', 'planner', 'developer', 'reviewer'].includes(input.baseRoleId)) {
      throw new HubApiError('角色模板必须继承有效基础角色。', 'VALIDATION_FAILED' as ErrorCode, 422)
    }
    const now = new Date().toISOString()
    const template: LocalRoleTemplateView = {
      id: `role_template_${Date.now()}_${this.roleTemplates.length}`,
      name: input.name.trim(),
      baseRoleId: input.baseRoleId,
      instructions: input.instructions,
      version: 1,
      createdAt: now,
      updatedAt: now,
    }
    this.roleTemplates.push(template)
    const response = JSON.parse(JSON.stringify(template)) as LocalRoleTemplateView
    this.roleTemplateWriteReceipts.set(idempotencyKey, { signature, response })
    return JSON.parse(JSON.stringify(response))
  }

  async updateLocalRoleTemplate(
    templateId: string,
    input: UpdateLocalRoleTemplateInput,
    idempotencyKey: string
  ): Promise<LocalRoleTemplateView> {
    if (!idempotencyKey) {
      throw new HubApiError('缺少 Idempotency-Key', 'VALIDATION_FAILED' as ErrorCode, 422)
    }
    const signature = JSON.stringify({ templateId, input })
    const previous = this.roleTemplateWriteReceipts.get(idempotencyKey)
    if (previous) {
      if (previous.signature !== signature) {
        throw new HubApiError('同一 Idempotency-Key 不能用于不同请求', 'IDEMPOTENCY_MISMATCH' as ErrorCode, 409)
      }
      return JSON.parse(JSON.stringify(previous.response))
    }
    const template = this.roleTemplates.find((item) => item.id === templateId)
    if (!template) throw new HubApiError('角色模板不存在', 'NOT_FOUND' as ErrorCode, 404)
    if (input.expectedVersion !== template.version) {
      throw new HubApiError('角色模板版本冲突，请刷新后重试。', 'CONFLICT' as ErrorCode, 409, {
        currentVersion: template.version,
        expectedVersion: input.expectedVersion,
      })
    }
    if (!input.name.trim()) {
      throw new HubApiError('模板名称不能为空。', 'VALIDATION_FAILED' as ErrorCode, 422)
    }
    template.name = input.name.trim()
    template.instructions = input.instructions
    template.version += 1
    template.updatedAt = new Date().toISOString()
    const response = JSON.parse(JSON.stringify(template)) as LocalRoleTemplateView
    this.roleTemplateWriteReceipts.set(idempotencyKey, { signature, response })
    return JSON.parse(JSON.stringify(response))
  }

  // Conversations & Messages
  async listLocalConversations(params?: {
    includeHidden?: boolean
    workspaceId?: string
  }): Promise<LocalConversationView[]> {
    let list = [...this.conversations]
    if (params?.workspaceId) {
      list = list.filter((c) => c.workspaceId === params.workspaceId)
    }
    if (!params?.includeHidden) {
      list = list.filter((c) => c.visibility !== 'mobile_only')
    }
    return list
  }

  async createLocalConversation(
    input: CreateLocalConversationInput,
    _idempotencyKey?: string
  ): Promise<LocalConversationView> {
    const scene = this.scenes.find((s) => s.id === input.sceneId)
    if (!scene) {
      throw new HubApiError('场景不存在', 'NOT_FOUND' as ErrorCode, 404)
    }

    const newConv: LocalConversationView = {
      id: `conv_${Date.now()}`,
      title: input.title,
      workspaceId: input.workspaceId,
      sceneId: input.sceneId,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      version: 1,
      archived: false,
    }
    this.conversations.unshift(newConv)
    this.messages.set(newConv.id, [])
    return newConv
  }

  async updateLocalConversation(
    conversationId: string,
    input: UpdateLocalConversationInput,
    idempotencyKey: string
  ): Promise<LocalConversationView> {
    if (!idempotencyKey) {
      throw new HubApiError('缺少 Idempotency-Key', 'VALIDATION_FAILED' as ErrorCode, 422)
    }
    const signature = JSON.stringify({ conversationId, input })
    const previous = this.conversationUpdateReceipts.get(idempotencyKey)
    if (previous) {
      if (previous.signature !== signature) {
        throw new HubApiError('同一 Idempotency-Key 不能用于不同请求', 'IDEMPOTENCY_MISMATCH' as ErrorCode, 409)
      }
      return JSON.parse(JSON.stringify(previous.response))
    }
    const conversation = this.conversations.find((item) => item.id === conversationId)
    if (!conversation) {
      throw new HubApiError('对话不存在', 'NOT_FOUND' as ErrorCode, 404)
    }
    const currentVersion = conversation.version ?? 1
    if (input.expectedVersion !== currentVersion) {
      throw new HubApiError(
        '任务信息已在其他窗口更新，请刷新后重试',
        'CONFLICT' as ErrorCode,
        409,
        { currentVersion }
      )
    }
    if (input.title === undefined && input.archived === undefined && input.visibility === undefined) {
      throw new HubApiError('至少需要修改标题、归档状态或可见性', 'VALIDATION_FAILED' as ErrorCode, 422)
    }
    if (input.title !== undefined && !input.title.trim()) {
      throw new HubApiError('任务标题不能为空', 'VALIDATION_FAILED' as ErrorCode, 422)
    }
    if (input.archived === true) {
      const hasUnfinishedRun = Array.from(this.runs.values()).some(
        (run) => run.conversationId === conversationId
          && ['queued', 'running', 'waiting_approval', 'paused'].includes(run.status)
      )
      if (hasUnfinishedRun) {
        throw new HubApiError('任务仍在运行、排队、等待审批或暂停，暂时不能归档', 'CONFLICT' as ErrorCode, 409)
      }
    }
    if (input.title !== undefined) conversation.title = input.title.trim()
    if (input.archived !== undefined) conversation.archived = input.archived
    if (input.visibility !== undefined) conversation.visibility = input.visibility
    conversation.version = currentVersion + 1
    conversation.updatedAt = new Date().toISOString()
    const response = JSON.parse(JSON.stringify(conversation)) as LocalConversationView
    this.conversationUpdateReceipts.set(idempotencyKey, { signature, response })
    return JSON.parse(JSON.stringify(response))
  }

  async listLocalMessages(
    conversationId: string,
    after = 0,
    limit = 200
  ): Promise<LocalMessageView[]> {
    const list = this.messages.get(conversationId) || []
    return list.filter((m) => m.sequence > after).slice(0, limit)
  }

  async sendLocalMessage(
    conversationId: string,
    input: SendLocalMessageInput,
    _idempotencyKey?: string
  ): Promise<LocalMessageReceipt> {
    const conv = this.conversations.find((c) => c.id === conversationId)
    if (!conv) {
      throw new HubApiError('对话不存在', 'NOT_FOUND' as ErrorCode, 404)
    }
    if (conv.archived) {
      throw new HubApiError('请先恢复已归档任务，再发送消息', 'CONFLICT' as ErrorCode, 409)
    }

    // Check duplicate
    if (this.processedClientMessageIds.has(input.clientMessageId)) {
      return {
        commandId: `cmd_dup_${Date.now()}`,
        conversationId,
        messageId: `msg_${input.clientMessageId}`,
        runId: conv.activeRunId || conv.lastRunId || 'run_default',
        status: 'accepted',
        duplicate: true,
      }
    }
    this.processedClientMessageIds.add(input.clientMessageId)

    // Check resume session capability
    if (input.sessionMode === 'continue' && this.simulateSessionNotResumable) {
      throw new HubApiError(
        '会话无法恢复：底层 Agent 进程已关闭或已超出最大上下文窗口',
        'SESSION_NOT_RESUMABLE' as ErrorCode,
        409
      )
    }

    const list = this.messages.get(conversationId) || []
    const nextSeq = list.length > 0 ? Math.max(...list.map((m) => m.sequence)) + 1 : 1

    const userMessage: LocalMessageView = {
      id: `msg_${Date.now()}`,
      conversationId,
      sequence: nextSeq,
      role: 'user',
      text: input.text,
      attachments: input.attachmentIds?.map((id) => { const record = this.attachmentLibrary.get(id); record.local.state = 'attached'; return { ...record.local.attachment } }),
      createdAt: new Date().toISOString(),
    }
    list.push(userMessage)

    // Native Mock runs have a bound single Agent, never a fabricated scenario snapshot.
    if (conv.conversationKind === 'native') {
      if (input.sessionMode !== 'continue') throw new HubApiError('原生会话必须继续原上下文', 'VALIDATION_FAILED', 422)
      const runId = `run_native_${crypto.randomUUID()}`
      const now = new Date().toISOString()
      this.runs.set(runId, { id: runId, conversationId, messageId: userMessage.id, taskId: `task_${runId}`, conversationKind: 'native', agentType: conv.agentType, status: 'running', createdAt: now, updatedAt: now })
      this.messages.set(conversationId, list)
      conv.activeRunId = runId; conv.lastRunId = runId; conv.lastRunStatus = 'running'
      return { commandId: `cmd_${runId}`, conversationId, messageId: userMessage.id, runId, status: 'accepted', duplicate: false }
    }
    // Start a new run
    const scene = this.scenes.find((s) => s.id === conv.sceneId) || this.scenes[0]
    const runId = `run_${Date.now()}`
    const taskId = `task_${runId}`

    const enabledRoles = scene.roles.filter((role) => role.enabled)
    const planner = enabledRoles.find((role) => role.roleId === 'planner')
    const taskNodes = enabledRoles.map((role, idx) => {
      const isOriginalPlannerAcceptance =
        scene.reviewMode === 'original_planner' && role.roleId === 'reviewer' && planner
      const effectiveRole = isOriginalPlannerAcceptance ? planner : role
      const plannerSessionId = `session_${runId}_planner`
      const plannerExternalSessionId = `native_${runId}_planner`
      return {
        id: `node_${runId}_${idx + 1}`,
        taskId,
        roleId: (isOriginalPlannerAcceptance ? 'planner' : role.roleId) as any,
        resolvedAgentId: effectiveRole.agentInstanceId,
        resolvedAgentName:
          this.agents.find((agent) => agent.id === effectiveRole.agentInstanceId)?.displayName ||
          effectiveRole.agentInstanceId,
        resolveSource: 'workspace_profile' as const,
        status: (idx === 0 ? 'running' : 'pending') as any,
        phase: (isOriginalPlannerAcceptance ? 'acceptance' : 'execution') as 'acceptance' | 'execution',
        sessionId: effectiveRole.roleId === 'planner'
          ? plannerSessionId
          : `session_${runId}_${effectiveRole.roleId}`,
        externalSessionId: effectiveRole.roleId === 'planner'
          ? plannerExternalSessionId
          : `native_${runId}_${effectiveRole.roleId}`,
        ...(isOriginalPlannerAcceptance
          ? {
              reviewSourceNodeId: `node_${runId}_${Math.max(1, idx)}`,
              reviewEvidenceId: `evidence_${runId}_pending`,
            }
          : {}),
      }
    })

    const newTask: TaskDetailView = {
      id: taskId,
      objective: input.text.slice(0, 100),
      workspaceId: conv.workspaceId,
      workspaceName:
        this.workspaces.find((w) => w.id === conv.workspaceId)?.name || 'Local Workspace',
      profileId: `prof_${scene.id}`,
      profileName: scene.name,
      status: 'running',
      source: 'desktop',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      nodes: taskNodes,
      artifacts: [],
      events: [],
    }

    const newRun: LocalRunView = {
      id: runId,
      conversationId,
      messageId: userMessage.id,
      taskId,
      sceneSnapshot: JSON.parse(JSON.stringify(scene)), // immutable snapshot!
      status: 'running',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      task: newTask,
    }

    this.runs.set(runId, newRun)
    conv.activeRunId = runId
    conv.lastRunId = runId
    conv.lastRunStatus = 'running'
    conv.updatedAt = new Date().toISOString()

    // Add progress system message
    const role1 = scene.roles.find((r) => r.enabled)
    const procMsg: LocalMessageView = {
      id: `msg_proc_${Date.now()}`,
      conversationId,
      sequence: nextSeq + 1,
      role: 'system',
      text: `【${role1?.roleId || 'Agent'}】收到指令，开始执行步骤...`,
      runId,
      createdAt: new Date().toISOString(),
    }
    list.push(procMsg)
    this.messages.set(conversationId, list)

    // Emit events
    this.events.push(
      {
        eventId: `evt_${this.eventSeq}`,
        seq: this.eventSeq++,
        aggregateType: 'task',
        aggregateId: taskId,
        taskId,
        type: 'task.status_changed',
        occurredAt: new Date().toISOString(),
        payload: { taskId, from: 'queued', to: 'running' },
        protocolVersion: PROTOCOL_VERSION,
      },
      {
        eventId: `evt_${this.eventSeq}`,
        seq: this.eventSeq++,
        aggregateType: 'task',
        aggregateId: taskId,
        taskId,
        type: 'agent.started',
        occurredAt: new Date().toISOString(),
        payload: { sessionId: `sess_${runId}`, purpose: 'adhoc' },
        protocolVersion: PROTOCOL_VERSION,
      },
      {
        eventId: `evt_${this.eventSeq}`,
        seq: this.eventSeq++,
        aggregateType: 'task',
        aggregateId: taskId,
        taskId,
        type: 'agent.progress',
        occurredAt: new Date().toISOString(),
        payload: { message: 'Thought: 分析当前工程架构并定位相关代码模块' },
        protocolVersion: PROTOCOL_VERSION,
      },
      {
        eventId: `evt_${this.eventSeq}`,
        seq: this.eventSeq++,
        aggregateType: 'task',
        aggregateId: taskId,
        taskId,
        type: 'agent.tool_call',
        occurredAt: new Date().toISOString(),
        payload: {
          toolName: 'view_file',
          argumentsExcerpt: 'apps/desktop/src/shared/ui/HqMarkdown.vue',
          resultSummary: '文件解析完成，识别 190 行定义',
          failed: false,
          durationMs: 120,
        },
        protocolVersion: PROTOCOL_VERSION,
      },
      {
        eventId: `evt_${this.eventSeq}`,
        seq: this.eventSeq++,
        aggregateType: 'task',
        aggregateId: taskId,
        taskId,
        type: 'agent.tool_call',
        occurredAt: new Date().toISOString(),
        payload: {
          toolName: 'commandExecution',
          argumentsExcerpt: 'pnpm --filter @hqagent/desktop test',
          resultSummary: '31 test files passed (137 tests)',
          failed: false,
          durationMs: 1250,
        },
        protocolVersion: PROTOCOL_VERSION,
      }
    )

    return {
      commandId: `cmd_${Date.now()}`,
      conversationId,
      messageId: userMessage.id,
      runId,
      status: 'accepted',
      duplicate: false,
    }
  }

  // Runs
  async listConversationRuns(conversationId: string): Promise<LocalRunView[]> {
    return Array.from(this.runs.values())
      .filter((r) => r.conversationId === conversationId)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
  }

  async getLocalRun(runId: string): Promise<LocalRunView> {
    const run = this.runs.get(runId)
    if (!run) {
      throw new HubApiError('Run 未找到', 'NOT_FOUND' as ErrorCode, 404)
    }
    return JSON.parse(JSON.stringify(run))
  }

  async controlLocalRun(
    runId: string,
    input: TaskActionInput,
    _idempotencyKey?: string
  ): Promise<LocalRunView> {
    const run = this.runs.get(runId)
    if (!run) {
      throw new HubApiError('Run 未找到', 'NOT_FOUND' as ErrorCode, 404)
    }
    const conversation = this.conversations.find((item) => item.id === run.conversationId)
    if (conversation?.archived && (input.action === 'resume' || input.action === 'retry')) {
      throw new HubApiError('请先恢复已归档任务，再继续或重试', 'CONFLICT' as ErrorCode, 409)
    }

    if (input.action === 'pause') {
      run.status = 'paused'
      if (run.task) run.task.status = 'paused'
    } else if (input.action === 'resume') {
      run.status = 'running'
      if (run.task) run.task.status = 'running'
    } else if (input.action === 'cancel') {
      run.status = 'cancelled'
      if (run.task) run.task.status = 'cancelled'
      const conv = this.conversations.find((c) => c.id === run.conversationId)
      if (conv && conv.activeRunId === runId) {
        conv.activeRunId = undefined
      }
    } else if (input.action === 'retry') {
      run.status = 'running'
      if (run.task) run.task.status = 'running'
    }

    run.updatedAt = new Date().toISOString()
    if (conversation) {
      conversation.lastRunStatus = run.status
      conversation.activeRunId = ['queued', 'running', 'waiting_approval', 'paused'].includes(run.status)
        ? run.id
        : undefined
    }

    // Add event
    this.events.push({
      eventId: `evt_${this.eventSeq}`,
      seq: this.eventSeq++,
      aggregateType: 'task',
      aggregateId: run.taskId,
      type: 'task.status_changed',
      occurredAt: new Date().toISOString(),
      payload: { taskId: run.taskId, to: run.status },
      protocolVersion: PROTOCOL_VERSION,
    })

    return JSON.parse(JSON.stringify(run))
  }

  // Events
  async listLocalEvents(after = 0, limit = 200): Promise<LocalEventPage> {
    if (this.simulateCursorExpired) {
      this.simulateCursorExpired = false
      throw new HubApiError(
        '事件游标已过期，请重新拉取快照',
        'EVENT_CURSOR_EXPIRED' as ErrorCode,
        410
      )
    }

    const filtered = this.events.filter((e) => e.seq > after).slice(0, limit)
    const nextSeq =
      filtered.length > 0 ? filtered[filtered.length - 1].seq : after

    return {
      events: filtered,
      nextSeq,
      hasMore: this.events.some((e) => e.seq > nextSeq),
    }
  }

  // Approvals & Sessions
  async listLocalApprovals(): Promise<ApprovalView[]> {
    return [...this.approvals]
  }

  async decideLocalApproval(
    approvalId: string,
    input: ApprovalResponseInput
  ): Promise<ApprovalView> {
    const appr = this.approvals.find((a) => a.id === approvalId)
    if (!appr) {
      throw new HubApiError('审批请求不存在', 'NOT_FOUND' as ErrorCode, 404)
    }

    appr.status = input.decision === 'approve' ? 'approved' : 'rejected'
    appr.decision = input.decision
    appr.reason = input.reason
    appr.decidedAt = new Date().toISOString()
    return { ...appr }
  }

  async listLocalSessions(): Promise<SessionView[]> {
    return [...this.sessions]
  }

  // Remote Link (D44)
  setRemoteLinkState(view: RemoteLinkView): void {
    this.remoteLink = JSON.parse(JSON.stringify(view))
  }

  async getRemoteLink(): Promise<RemoteLinkView> {
    if (this.remoteLink.state === 'pairing') {
      const now = Date.now()
      const expiry = new Date(this.remoteLink.expiresAt).getTime()
      if (now >= expiry) {
        this.remoteLink = {
          state: 'unpaired',
          serverOrigin: this.remoteLink.serverOrigin,
          lastErrorCode: 'REMOTE_PAIRING_EXPIRED' as ErrorCode,
        }
      }
    }
    return JSON.parse(JSON.stringify(this.remoteLink))
  }

  async startRemotePairing(
    input: RemoteLinkPairingInput,
    _idempotencyKey?: string
  ): Promise<RemoteLinkView> {
    const origin = (input.serverOrigin || '').trim()
    const isValidOrigin =
      /^(?:https:\/\/(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?|\[[0-9A-Fa-f:]+\])|http:\/\/(?:127\.0\.0\.1|localhost))(?::(?:[1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?\/?$/.test(
        origin
      )

    if (!isValidOrigin) {
      throw new HubApiError(
        '服务器地址格式不正确，必须为 HTTPS 地址（本地测试可用 localhost 或 127.0.0.1）',
        'REMOTE_SERVER_ORIGIN_INVALID' as ErrorCode,
        400
      )
    }

    if (this.remoteLink.state === 'pairing') {
      throw new HubApiError(
        '已有配对请求正在进行中，请先取消或等待过期',
        'REMOTE_PAIRING_IN_PROGRESS' as ErrorCode,
        409
      )
    }

    const deviceName = (input.deviceName || '').trim() || '我的电脑'
    this.remoteLink = {
      state: 'pairing',
      serverOrigin: origin,
      deviceName,
      pairRequestId: `pair_req_${Date.now()}`,
      pairCode: 'ABCD2345',
      expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
    }
    return JSON.parse(JSON.stringify(this.remoteLink))
  }

  async cancelRemotePairing(_idempotencyKey?: string): Promise<RemoteLinkView> {
    const prevOrigin = (this.remoteLink as any).serverOrigin || 'https://hub.example.com'
    this.remoteLink = {
      state: 'unpaired',
      serverOrigin: prevOrigin,
    }
    return JSON.parse(JSON.stringify(this.remoteLink))
  }

  async unlinkRemote(_idempotencyKey?: string): Promise<RemoteLinkView> {
    const prevOrigin = (this.remoteLink as any).serverOrigin || 'https://hub.example.com'
    this.remoteLink = {
      state: 'unpaired',
      serverOrigin: prevOrigin,
    }
    return JSON.parse(JSON.stringify(this.remoteLink))
  }

  // Simulation helpers for testing / dev
  mockSimulatePairingSuccess(workerId = 'worker_local_pc'): RemoteLinkView {
    const origin = (this.remoteLink as any).serverOrigin || 'https://hub.example.com'
    const deviceName = (this.remoteLink as any).deviceName || '我的电脑'
    this.remoteLink = {
      state: 'paired',
      serverOrigin: origin,
      workerId,
      deviceName,
      connectionStatus: 'online',
      lastConnectedAt: new Date().toISOString(),
    }
    return JSON.parse(JSON.stringify(this.remoteLink))
  }

  mockSimulateConnectionStatus(
    connectionStatus: 'online' | 'connecting' | 'offline',
    lastErrorCode?: ErrorCode
  ): RemoteLinkView {
    if (this.remoteLink.state === 'paired' || this.remoteLink.state === 'frozen') {
      this.remoteLink.connectionStatus = connectionStatus
      if (lastErrorCode) this.remoteLink.lastErrorCode = lastErrorCode
    }
    return JSON.parse(JSON.stringify(this.remoteLink))
  }

  mockSimulateRevoked(lastErrorCode: ErrorCode = 'REMOTE_DEVICE_REVOKED'): RemoteLinkView {
    const origin = (this.remoteLink as any).serverOrigin || 'https://hub.example.com'
    const workerId = (this.remoteLink as any).workerId || 'worker_local_pc'
    const deviceName = (this.remoteLink as any).deviceName || '我的电脑'
    const lastConnectedAt = (this.remoteLink as any).lastConnectedAt || null
    this.remoteLink = {
      state: 'revoked',
      serverOrigin: origin,
      workerId,
      deviceName,
      connectionStatus: 'offline',
      lastConnectedAt,
      lastErrorCode,
    }
    return JSON.parse(JSON.stringify(this.remoteLink))
  }

  mockSimulateFrozen(lastErrorCode: ErrorCode = 'REMOTE_EPOCH_STALE'): RemoteLinkView {
    const origin = (this.remoteLink as any).serverOrigin || 'https://hub.example.com'
    const workerId = (this.remoteLink as any).workerId || 'worker_local_pc'
    const deviceName = (this.remoteLink as any).deviceName || '我的电脑'
    const lastConnectedAt = (this.remoteLink as any).lastConnectedAt || new Date().toISOString()
    this.remoteLink = {
      state: 'frozen',
      serverOrigin: origin,
      workerId,
      deviceName,
      connectionStatus: 'online',
      lastConnectedAt,
      lastErrorCode,
    }
    return JSON.parse(JSON.stringify(this.remoteLink))
  }

  // Remote Sync Settings (R1.5 / 0.7.0)
  private syncSettings: RemoteSyncSettingsView = {
    mirrorEnabled: true,
    version: 1,
    syncGeneration: 1,
  }

  async getRemoteSyncSettings(): Promise<RemoteSyncSettingsView> {
    return JSON.parse(JSON.stringify(this.syncSettings))
  }

  async setRemoteSyncSettings(
    input: RemoteSyncSettingsInput,
    _idempotencyKey?: string
  ): Promise<RemoteSyncSettingsView> {
    if (input.expectedVersion !== this.syncSettings.version) {
      throw new HubApiError('同步设置版本冲突，请刷新后重试', 'CONFLICT' as ErrorCode, 409)
    }
    this.syncSettings = {
      mirrorEnabled: input.mirrorEnabled,
      version: this.syncSettings.version + 1,
      syncGeneration: this.syncSettings.syncGeneration + 1,
    }
    return JSON.parse(JSON.stringify(this.syncSettings))
  }
}

export const mockLocalChatGateway = new MockLocalChatGateway()
