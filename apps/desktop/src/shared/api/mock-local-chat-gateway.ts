import type {
  LocalAuthView,
  LocalAuthInput,
  AgentView,
  AgentDiscoveryResult,
  LocalAgentModelsView,
  WorkspaceView,
  AddWorkspaceInput,
  LocalSceneView,
  SaveLocalSceneInput,
  LocalConversationView,
  CreateLocalConversationInput,
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
} from '@hqagent/protocol'

import type {
  LocalChatGateway,
  PickLocalDirectoryInput,
  PickLocalDirectoryView,
} from './local-chat-gateway.interface'
import { HubApiError } from './local-hub-gateway'

// Import contract fixtures
import analyzeSceneFixture from '@hqagent/fixtures/local-scene.analyze.json'
import agentsDiscoveryFixture from '@hqagent/fixtures/agents.discovery-partial.json'

export class MockLocalChatGateway implements LocalChatGateway {
  public isMock = true
  private authenticated = true
  private protocolVersion = '0.3.0'

  private workspaces: WorkspaceView[] = []
  private agents: AgentView[] = []
  private scenes: LocalSceneView[] = []
  private conversations: LocalConversationView[] = []
  private messages: Map<string, LocalMessageView[]> = new Map()
  private runs: Map<string, LocalRunView> = new Map()
  private approvals: ApprovalView[] = []
  private sessions: SessionView[] = []
  private events: HubEvent[] = []
  private processedClientMessageIds: Set<string> = new Set()
  private eventSeq = 1

  // Simulation flags
  public simulateCursorExpired = false
  public simulateSessionNotResumable = false

  constructor() {
    this.reset()
  }

  reset(): void {
    this.authenticated = true
    this.processedClientMessageIds.clear()

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
    }

    const developScene: LocalSceneView = {
      id: 'develop' as LocalSceneId,
      name: '开发修复',
      description: '在授权项目的隔离工作树中完成编码实施、单测验证与审查',
      readOnly: false,
      version: 2,
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
          instructions: '严格审查 git diff，检查代码坏味道、越界修改与安全风险。',
          modelId: 'claude-3-5-sonnet',
          reasoningEffort: 'low',
          enabled: true,
        },
      ],
      updatedAt: '2026-09-24T03:00:00Z',
    }

    this.scenes = [analyzeScene, planScene, developScene]

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
      sceneSnapshot: analyzeScene,
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
          roleId: 'analyst',
          resolvedAgentId: this.agents[0]?.id ?? 'claude-code-local',
          resolvedAgentName: 'Claude Code',
          resolveSource: 'workspace_profile',
          status: 'succeeded',
          startedAt: '2026-09-24T09:30:10Z',
          completedAt: '2026-09-24T09:31:00Z',
          outputSummary: 'UI 方案已确认',
        },
        {
          id: 'node_run_2_2',
          taskId: 'task_run_2',
          roleId: 'developer',
          resolvedAgentId: this.agents[1]?.id ?? 'codex-cli-local',
          resolvedAgentName: 'Codex CLI',
          resolveSource: 'capability_match',
          status: 'running',
          startedAt: '2026-09-24T09:31:05Z',
          changedFiles: [
            'apps/desktop/src/pages/chat/ChatPage.vue',
            'apps/desktop/src/stores/chat.store.ts',
          ],
        },
        {
          id: 'node_run_2_3',
          taskId: 'task_run_2',
          roleId: 'reviewer',
          resolvedAgentId: this.agents[0]?.id ?? 'claude-code-local',
          resolvedAgentName: 'Claude Code',
          resolveSource: 'workspace_profile',
          status: 'pending',
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
      sceneSnapshot: developScene,
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
      sceneSnapshot: planScene,
      status: 'waiting_approval',
      createdAt: '2026-09-24T10:10:05Z',
      updatedAt: '2026-09-24T10:12:00Z',
      task: run3Task,
    }

    this.conversations = [conv2, conv1, conv3]
    this.messages.set(conv1Id, conv1Messages)
    this.messages.set(conv2Id, conv2Messages)
    this.messages.set(conv3Id, conv3Messages)
    this.runs.set(run1Id, run1)
    this.runs.set(run2Id, run2)
    this.runs.set(run3Id, run3)

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
        protocolVersion: '0.3.0',
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
        protocolVersion: '0.3.0',
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

    scene.roles = [...input.roles]
    scene.version += 1
    scene.updatedAt = new Date().toISOString()
    return { ...scene }
  }

  // Conversations & Messages
  async listLocalConversations(): Promise<LocalConversationView[]> {
    return [...this.conversations]
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
    }
    this.conversations.unshift(newConv)
    this.messages.set(newConv.id, [])
    return newConv
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
      createdAt: new Date().toISOString(),
    }
    list.push(userMessage)

    // Start a new run
    const scene = this.scenes.find((s) => s.id === conv.sceneId) || this.scenes[0]
    const runId = `run_${Date.now()}`
    const taskId = `task_${runId}`

    const taskNodes = scene.roles
      .filter((r) => r.enabled)
      .map((r, idx) => ({
        id: `node_${runId}_${idx + 1}`,
        taskId,
        roleId: r.roleId as any,
        resolvedAgentId: r.agentInstanceId,
        resolvedAgentName:
          this.agents.find((a) => a.id === r.agentInstanceId)?.displayName ||
          r.agentInstanceId,
        resolveSource: 'workspace_profile' as const,
        status: (idx === 0 ? 'running' : 'pending') as any,
      }))

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
        protocolVersion: '0.3.0',
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
        protocolVersion: '0.3.0',
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
        protocolVersion: '0.3.0',
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
        protocolVersion: '0.3.0',
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
        protocolVersion: '0.3.0',
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

    // Add event
    this.events.push({
      eventId: `evt_${this.eventSeq}`,
      seq: this.eventSeq++,
      aggregateType: 'task',
      aggregateId: run.taskId,
      type: 'task.status_changed',
      occurredAt: new Date().toISOString(),
      payload: { taskId: run.taskId, to: run.status },
      protocolVersion: '0.3.0',
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
}

export const mockLocalChatGateway = new MockLocalChatGateway()
