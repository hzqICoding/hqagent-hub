import type {
  BootstrapView,
  AgentView,
  AgentDiscoveryResult,
  TaskDetailView,
  TaskSummaryView,
  UpdateStateView,
  ApprovalView,
  SessionView,
  WorkspaceView,
  TeamProfileView,
} from '@hqagent/protocol'

import bootstrapHappyData from '@hqagent/fixtures/bootstrap.happy.json'
import agentsData from '@hqagent/fixtures/agents.discovery-partial.json'
import taskMultiRoleRunningData from '@hqagent/fixtures/task.multi-role-running.json'
import taskWaitingApprovalData from '@hqagent/fixtures/task.waiting-approval.json'
import taskFailedFallbackData from '@hqagent/fixtures/task.failed-with-fallback.json'
import updateDownloadingData from '@hqagent/fixtures/update.downloading.json'
import updateDrainingData from '@hqagent/fixtures/update.draining.json'

export type MockScenarioId =
  | 'happy-path'
  | 'first-run-no-agent'
  | 'task-running'
  | 'task-waiting-approval'
  | 'task-failed'
  | 'update-downloading'
  | 'update-draining'
  | 'hub-disconnected'

export interface ScenarioDefinition {
  id: MockScenarioId
  name: string
  description: string
  getBootstrap: () => BootstrapView
  getAgents: () => AgentView[]
  getDiscovery: () => AgentDiscoveryResult
  getTasks: () => TaskSummaryView[]
  getTaskDetail: (id: string) => TaskDetailView
  getApprovals: () => ApprovalView[]
  getUpdateState: () => UpdateStateView
  getSessions: () => SessionView[]
  getWorkspaces: () => WorkspaceView[]
  getTeamProfiles: () => TeamProfileView[]
}

export const scenarios: Record<MockScenarioId, ScenarioDefinition> = {
  'happy-path': {
    id: 'happy-path',
    name: '正常全流程 (Happy Path)',
    description: 'Agent 正常在线，多角色协作运行中，有待处理审批',
    getBootstrap: () => JSON.parse(JSON.stringify(bootstrapHappyData)),
    getAgents: () => JSON.parse(JSON.stringify(agentsData.discovered)),
    getDiscovery: () => JSON.parse(JSON.stringify(agentsData)),
    getTasks: () => [
      JSON.parse(JSON.stringify(taskMultiRoleRunningData)),
      JSON.parse(JSON.stringify(taskWaitingApprovalData)),
      JSON.parse(JSON.stringify(taskFailedFallbackData)),
    ],
    getTaskDetail: (id: string) => {
      if (id === taskWaitingApprovalData.id) return JSON.parse(JSON.stringify(taskWaitingApprovalData))
      if (id === taskFailedFallbackData.id) return JSON.parse(JSON.stringify(taskFailedFallbackData))
      return JSON.parse(JSON.stringify(taskMultiRoleRunningData))
    },
    getApprovals: () => [
      {
        id: 'appr_99812',
        taskId: taskWaitingApprovalData.id,
        taskObjective: taskWaitingApprovalData.objective,
        requestAgentId: 'agent_codex_default',
        requestAgentName: 'Codex App Server',
        action: 'git_push',
        targetResource: 'git push origin feat/f0-desktop-skeleton',
        riskLevel: 'high',
        status: 'pending',
        requestedAt: '2026-09-05T18:18:05Z',
        details: {
          branch: 'feat/f0-desktop-skeleton',
          remote: 'origin',
        },
      },
    ],
    getUpdateState: () => JSON.parse(JSON.stringify(updateDownloadingData)),
    getSessions: () => [
      {
        id: 'sess_claude_01',
        status: 'active',
        workspaceId: 'ws_hqagent_hub',
        workspaceName: 'HQAgent-Hub',
        roleId: 'architect',
        agentInstanceId: 'agent_claude_default',
        agentDisplayName: 'Claude Code',
        adapterId: 'claude',
        externalSessionId: 'session-claude-uuid-7718-20260905',
        purpose: 'architect',
        reusePolicy: 'resume_explicit',
        lastUsedAt: '2026-09-05T18:12:30Z',
        createdAt: '2026-09-05T18:00:00Z',
        taskId: taskMultiRoleRunningData.id,
        isValid: true,
      },
      {
        id: 'sess_codex_01',
        status: 'active',
        workspaceId: 'ws_hqagent_hub',
        workspaceName: 'HQAgent-Hub',
        roleId: 'general_implementer',
        agentInstanceId: 'agent_codex_default',
        agentDisplayName: 'Codex App Server',
        adapterId: 'codex',
        externalSessionId: 'thread_codex_app_server_4481_2026',
        purpose: 'implement',
        reusePolicy: 'resume_explicit',
        lastUsedAt: '2026-09-05T18:18:20Z',
        createdAt: '2026-09-05T18:05:00Z',
        taskId: taskMultiRoleRunningData.id,
        isValid: true,
      },
    ],
    getWorkspaces: () => [
      {
        id: 'ws_hqagent_hub',
        name: 'HQAgent-Hub',
        path: 'E:/OtherPro/HQAgent-Hub',
        vcs: 'git',
        branch: 'integration/phase1',
        isClean: true,
        defaultProfileId: 'profile_hq_default',
        lastOpenedAt: '2026-09-05T18:00:00Z',
        memoryDirPresent: true,
      },
    ],
    getTeamProfiles: () => [
      {
        id: 'profile_hq_default',
        name: 'HQ 默认双 Agent 团队',
        description: 'Claude 负责架构与审查，Codex 负责实现与测试，自动处理 fallback',
        scope: 'global',
        isDefault: true,
        updatedAt: '2026-09-05T18:00:00Z',
        roleBindings: {
          orchestrator: {
            roleId: 'orchestrator',
            roleName: '总控调度',
            primaryAgentId: 'agent_claude_default',
            fallbackAgentIds: ['agent_codex_default'],
          },
          architect: {
            roleId: 'architect',
            roleName: '系统架构',
            primaryAgentId: 'agent_claude_default',
            fallbackAgentIds: [],
          },
          frontend_implementer: {
            roleId: 'frontend_implementer',
            roleName: '前端开发',
            primaryAgentId: 'agent_codex_default',
            fallbackAgentIds: ['agent_claude_default'],
          },
          general_implementer: {
            roleId: 'general_implementer',
            roleName: '全栈实现',
            primaryAgentId: 'agent_codex_default',
            fallbackAgentIds: ['agent_claude_default'],
          },
          reviewer: {
            roleId: 'reviewer',
            roleName: '代码审查',
            primaryAgentId: 'agent_claude_default',
            fallbackAgentIds: [],
          },
          tester: {
            roleId: 'tester',
            roleName: '测试执行',
            primaryAgentId: 'agent_codex_default',
            fallbackAgentIds: ['agent_claude_default'],
          },
        },
      },
    ],
  },

  'first-run-no-agent': {
    id: 'first-run-no-agent',
    name: '首次运行无 Agent',
    description: '未检测到任何本地 Agent 时的引导与空状态',
    getBootstrap: () => {
      const b = JSON.parse(JSON.stringify(bootstrapHappyData)) as BootstrapView
      b.agents = { total: 0, ready: 0, issues: 0 }
      b.activeTasksCount = 0
      b.pendingApprovalsCount = 0
      return b
    },
    getAgents: () => [],
    getDiscovery: () => ({ discovered: [], total: 0, ready: 0, timestamp: new Date().toISOString() }),
    getTasks: () => [],
    getTaskDetail: () => {
      throw new Error('NOT_FOUND: 任务不存在')
    },
    getApprovals: () => [],
    getUpdateState: () => ({
      currentVersion: '0.1.0',
      channel: 'stable',
      phase: 'idle',
      canInstallNow: false,
      lastCheckedAt: new Date().toISOString(),
    }),
    getSessions: () => [],
    getWorkspaces: () => [JSON.parse(JSON.stringify(bootstrapHappyData.currentWorkspace))],
    getTeamProfiles: () => [],
  },

  'task-running': {
    id: 'task-running',
    name: '多 Agent 协作进行中',
    description: 'Architect 完成，Frontend 实现中，Reviewer 排队中',
    getBootstrap: () => JSON.parse(JSON.stringify(bootstrapHappyData)),
    getAgents: () => JSON.parse(JSON.stringify(agentsData.discovered)),
    getDiscovery: () => JSON.parse(JSON.stringify(agentsData)),
    getTasks: () => [JSON.parse(JSON.stringify(taskMultiRoleRunningData))],
    getTaskDetail: () => JSON.parse(JSON.stringify(taskMultiRoleRunningData)),
    getApprovals: () => [],
    getUpdateState: () => JSON.parse(JSON.stringify(updateDownloadingData)),
    getSessions: () => scenarios['happy-path'].getSessions(),
    getWorkspaces: () => scenarios['happy-path'].getWorkspaces(),
    getTeamProfiles: () => scenarios['happy-path'].getTeamProfiles(),
  },

  'task-waiting-approval': {
    id: 'task-waiting-approval',
    name: '任务等待审批 (Waiting Approval)',
    description: '触发 git_push 高风险命令，等待用户二次确认',
    getBootstrap: () => JSON.parse(JSON.stringify(bootstrapHappyData)),
    getAgents: () => JSON.parse(JSON.stringify(agentsData.discovered)),
    getDiscovery: () => JSON.parse(JSON.stringify(agentsData)),
    getTasks: () => [JSON.parse(JSON.stringify(taskWaitingApprovalData))],
    getTaskDetail: () => JSON.parse(JSON.stringify(taskWaitingApprovalData)),
    getApprovals: () => scenarios['happy-path'].getApprovals(),
    getUpdateState: () => JSON.parse(JSON.stringify(updateDownloadingData)),
    getSessions: () => scenarios['happy-path'].getSessions(),
    getWorkspaces: () => scenarios['happy-path'].getWorkspaces(),
    getTeamProfiles: () => scenarios['happy-path'].getTeamProfiles(),
  },

  'task-failed': {
    id: 'task-failed',
    name: '任务失败与越界拦截',
    description: '前端尝试越界写后端目录，被 PermissionEngine 拦截',
    getBootstrap: () => JSON.parse(JSON.stringify(bootstrapHappyData)),
    getAgents: () => JSON.parse(JSON.stringify(agentsData.discovered)),
    getDiscovery: () => JSON.parse(JSON.stringify(agentsData)),
    getTasks: () => [JSON.parse(JSON.stringify(taskFailedFallbackData))],
    getTaskDetail: () => JSON.parse(JSON.stringify(taskFailedFallbackData)),
    getApprovals: () => [],
    getUpdateState: () => JSON.parse(JSON.stringify(updateDownloadingData)),
    getSessions: () => scenarios['happy-path'].getSessions(),
    getWorkspaces: () => scenarios['happy-path'].getWorkspaces(),
    getTeamProfiles: () => scenarios['happy-path'].getTeamProfiles(),
  },

  'update-downloading': {
    id: 'update-downloading',
    name: 'OTA 下载中',
    description: '显示 68.5% 下载进度与断点续传能力',
    getBootstrap: () => JSON.parse(JSON.stringify(bootstrapHappyData)),
    getAgents: () => JSON.parse(JSON.stringify(agentsData.discovered)),
    getDiscovery: () => JSON.parse(JSON.stringify(agentsData)),
    getTasks: () => scenarios['happy-path'].getTasks(),
    getTaskDetail: (id) => scenarios['happy-path'].getTaskDetail(id),
    getApprovals: () => scenarios['happy-path'].getApprovals(),
    getUpdateState: () => JSON.parse(JSON.stringify(updateDownloadingData)),
    getSessions: () => scenarios['happy-path'].getSessions(),
    getWorkspaces: () => scenarios['happy-path'].getWorkspaces(),
    getTeamProfiles: () => scenarios['happy-path'].getTeamProfiles(),
  },

  'update-draining': {
    id: 'update-draining',
    name: 'OTA Task Drain 排空保护',
    description: '升级安装前进入维护模式，等待正在运行的任务安全保存',
    getBootstrap: () => {
      const b = JSON.parse(JSON.stringify(bootstrapHappyData)) as BootstrapView
      b.maintenance = true
      return b
    },
    getAgents: () => JSON.parse(JSON.stringify(agentsData.discovered)),
    getDiscovery: () => JSON.parse(JSON.stringify(agentsData)),
    getTasks: () => scenarios['happy-path'].getTasks(),
    getTaskDetail: (id) => scenarios['happy-path'].getTaskDetail(id),
    getApprovals: () => scenarios['happy-path'].getApprovals(),
    getUpdateState: () => JSON.parse(JSON.stringify(updateDrainingData)),
    getSessions: () => scenarios['happy-path'].getSessions(),
    getWorkspaces: () => scenarios['happy-path'].getWorkspaces(),
    getTeamProfiles: () => scenarios['happy-path'].getTeamProfiles(),
  },

  'hub-disconnected': {
    id: 'hub-disconnected',
    name: 'Local Hub 断开连接',
    description: '模拟 127.0.0.1 端口失联，展示全局离线与重连引导',
    getBootstrap: () => {
      throw new Error('ERR_HUB_DISCONNECTED: Failed to connect to Local Hub at 127.0.0.1:49210')
    },
    getAgents: () => {
      throw new Error('ERR_HUB_DISCONNECTED: Failed to connect to Local Hub')
    },
    getDiscovery: () => {
      throw new Error('ERR_HUB_DISCONNECTED: Failed to connect to Local Hub')
    },
    getTasks: () => {
      throw new Error('ERR_HUB_DISCONNECTED: Failed to connect to Local Hub')
    },
    getTaskDetail: () => {
      throw new Error('ERR_HUB_DISCONNECTED: Failed to connect to Local Hub')
    },
    getApprovals: () => {
      throw new Error('ERR_HUB_DISCONNECTED: Failed to connect to Local Hub')
    },
    getUpdateState: () => {
      throw new Error('ERR_HUB_DISCONNECTED: Failed to connect to Local Hub')
    },
    getSessions: () => {
      throw new Error('ERR_HUB_DISCONNECTED: Failed to connect to Local Hub')
    },
    getWorkspaces: () => {
      throw new Error('ERR_HUB_DISCONNECTED: Failed to connect to Local Hub')
    },
    getTeamProfiles: () => {
      throw new Error('ERR_HUB_DISCONNECTED: Failed to connect to Local Hub')
    },
  },
}
