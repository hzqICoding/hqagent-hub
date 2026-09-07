// 此文件由 scripts/protocol/generate.py 生成，请勿手改。
// 改协议请改 packages/protocol/schema/ 或 registry/，然后重新运行:
//     pwsh scripts/protocol/generate.ps1

export const PROTOCOL_VERSION = '0.2.2' as const

export interface AcknowledgeUpdateResultInput {
  /** 要确认的结果版本，防止确认了一个已被覆盖的旧回执 */
  toVersion?: string
}

/** 适配器 ID。首发 claude / codex；antigravity 见 DECISIONS.md D5，不在一期关键路径 */
export type AdapterId = string

/** 接入方式，按施工方案 §7.1 的可靠性优先级排列。gui_automation 仅为实验性兜底，不得作为正式适配器标准，Role Resolver 不应把它选为主力 */
export type AdapterIntegrationKind =
  | 'sdk'
  | 'cli_stream'
  | 'mcp'
  | 'sidecar'
  | 'gui_automation'

/** 一期只验收 windows；macos/linux 在 Phase 3 */
export type AdapterPlatform =
  | 'windows'
  | 'macos'
  | 'linux'

/** Agent 所需鉴权方式，由适配器声明 */
export type AuthKind =
  | 'local_login'
  | 'api_key'
  | 'oauth'
  | 'device_code'
  | 'none'

/** 能力 ID，见 registry/capabilities.yaml */
export type CapabilityId =
  | 'orchestration'
  | 'architecture'
  | 'coding'
  | 'review'
  | 'testing'
  | 'shell'
  | 'file_write'
  | 'git_worktree'
  | 'session_resume'
  | 'streaming_events'
  | 'tool_approval'
  | 'structured_output'
  | 'vision'
  | 'browser'

export interface DeclaredCapability {
  id: CapabilityId
  supported: boolean
  /** supported=false 时说明原因；部分支持也必须报 false 并在此说明，不得报 true 后在运行时静默降级 */
  note?: string
}

/** RFC3339 时间戳，一律带时区 */
export type Timestamp = string

/** detect() 的返回值。描述「这个 Adapter 是什么、装没装、能干什么」，是一次性发现结果，不是周期性存活状态——后者见 AdapterHealth。 */
export interface AdapterDescriptor {
  adapterId: AdapterId
  displayName: string
  integrationKind: AdapterIntegrationKind
  authKind: AuthKind
  supportedPlatforms: AdapterPlatform[]
  /** false 时 detectedVersion / executablePath 可以缺省。发现状态不在本 DTO 里表达：AdapterDescriptor 描述「装了什么」，运行时能不能用由 AdapterHealth 组合出 AgentView.status（裁决 D31） */
  installed: boolean
  detectedVersion?: string
  /** 低于此版本必须报 incompatible，不得降级尝试 */
  minimumVersion?: string
  executablePath?: string
  /** Adapter 声明支持的能力。硬能力（capabilities.yaml 里 hard:true）只能由此声明，用户不能在 UI 上勾选覆盖——施工方案 §6.2 */
  capabilities: DeclaredCapability[]
  detectedAt?: Timestamp
}

/** streamEvents() 逐条产出的事件（裁决 D32）。故意不带 eventId 和 seq——全局单调 seq 与幂等 eventId 由 Hub 分配，Adapter 直接产出 HubEvent 会把这个所有权弄乱。Hub 收到后补齐这两个字段再落库广播。不冻结这个形状的话，W2 定义一套、W3 消费时再猜一套，接缝正好落在两个包中间 */
export interface AdapterEvent {
  /** Hub 本地会话 ID，即 AgentTaskSpec.sessionId（裁决 D25） */
  sessionId: string
  /** 必须是 FZ-1 冻结的 28 个事件类型之一，见 events/event-dictionary.md。Adapter 不得新增类型（裁决 D21） */
  type: string
  occurredAt: Timestamp
  /** 按 type 取 agent-event.json 里对应的 payload 形状 */
  payload: Record<string, unknown>
  /** 供应商侧请求 ID。审批类事件必须带上，用于和 ApprovalDispatch 关联（裁决 D33） */
  externalRequestId?: string
  /** 映射自哪个供应商原生事件名，仅供排障。UI 不得据此渲染 */
  vendorEventName?: string
}

/** Adapter 失败分类。Hub 据此决定重试、降级还是直接失败，不靠解析错误文案 */
export type AdapterFailureKind =
  | 'not_installed'
  | 'not_logged_in'
  | 'version_incompatible'
  | 'capability_missing'
  | 'transport_error'
  | 'agent_error'
  | 'timeout'
  | 'cancelled'
  | 'path_violation'

/** 错误码，见 registry/error-codes.yaml。前端按 code 决定行为，不得解析 message */
export type ErrorCode =
  | 'BAD_REQUEST'
  | 'VALIDATION_FAILED'
  | 'UNAUTHORIZED'
  | 'ORIGIN_NOT_ALLOWED'
  | 'NOT_FOUND'
  | 'CONFLICT'
  | 'IDEMPOTENCY_MISMATCH'
  | 'PROTOCOL_VERSION_MISMATCH'
  | 'HUB_NOT_READY'
  | 'HUB_MAINTENANCE'
  | 'EVENT_CURSOR_EXPIRED'
  | 'FEATURE_UNAVAILABLE'
  | 'AGENT_NOT_FOUND'
  | 'AGENT_OFFLINE'
  | 'AGENT_NOT_LOGGED_IN'
  | 'AGENT_INCOMPATIBLE'
  | 'CAPABILITY_MISSING'
  | 'ROLE_UNRESOLVED'
  | 'SESSION_NOT_RESUMABLE'
  | 'TASK_NOT_CANCELLABLE'
  | 'TASK_ACTION_INVALID'
  | 'WORKTREE_BUSY'
  | 'PATH_NOT_ALLOWED'
  | 'APPROVAL_REQUIRED'
  | 'APPROVAL_EXPIRED'
  | 'APPROVAL_ALREADY_DECIDED'
  | 'UPDATE_NOT_AVAILABLE'
  | 'UPDATE_BUSY'
  | 'UPDATE_VERIFY_FAILED'
  | 'UPDATE_DRAIN_TIMEOUT'
  | 'INTERNAL'

/** 任何 Port 方法失败时的统一结构。接入失败或缺少硬能力必须走这里，不得返回成功后在事件里静默降级。 */
export interface AdapterFailure {
  kind: AdapterFailureKind
  code?: ErrorCode
  message: string
  retryable: boolean
  /** kind=capability_missing 时必填，供 Role Resolver 提示能力缺口 */
  missingCapabilities?: CapabilityId[]
  /** kind=path_violation 时必填 */
  violationPaths?: string[]
  /** 供应商原始错误摘要，仅用于诊断包。长度上限 2048 字符，超出截断 */
  raw?: string
}

/** Agent 实例状态 */
export type AgentStatus =
  | 'discovering'
  | 'ready'
  | 'busy'
  | 'not_logged_in'
  | 'incompatible'
  | 'disabled'
  | 'offline'
  | 'error'
  | 'unknown'

/** health() 的返回值。周期性探活与登录态检查，比 detect() 轻量，不重新枚举能力。 */
export interface AdapterHealth {
  status: AgentStatus
  checkedAt: Timestamp
  latencyMs?: number
  /** false 时 status 必须是 not_logged_in。凭据本身绝不出现在本结构里 */
  authValid?: boolean
  /** 面向用户的可操作提示，例如「请先运行 claude login」。不得包含 token、路径以外的敏感信息 */
  diagnosticMessage?: string
}

/** streamEvents() 的终止原因。transport_lost=连接断了但 Agent 可能还活着，会话保持 active 且可重连；agent_exited=Agent 进程已退出，会话置 invalid；ended=正常收尾。把这两种混为一谈会导致 Hub 要么误判任务失败，要么永远等一个已死的进程 */
export type AdapterStreamStatus =
  | 'streaming'
  | 'transport_lost'
  | 'agent_exited'
  | 'ended'

export interface AdapterStreamEnd {
  status: AdapterStreamStatus
  endedAt: Timestamp
  lastEventSeq?: number
  /** 仅 transport_lost 时可能为 true */
  resumable?: boolean
  detail?: string
}

export interface AddWorkspaceInput {
  /** 本机绝对路径。Hub 会自行探测是不是 Git 仓库并写入 vcs，不接受调用方声明——声明和事实不符时，写任务的隔离保护就成了摆设 */
  path: string
  /** 省略时取目录名 */
  name?: string
  defaultProfileId?: string
}

export interface Blocker {
  kind: 'capability_gap' | 'permission_denied' | 'dependency_missing' | 'ambiguous_requirement' | 'external_failure' | 'other'
  message: string
  detail?: Record<string, unknown>
}

export interface FileChange {
  path: string
  changeKind: 'added' | 'modified' | 'deleted' | 'renamed'
  insertions?: number
  deletions?: number
  renamedFrom?: string
}

export interface TestOutcome {
  name: string
  command: string
  passed: boolean
  durationMs?: number
  exitCode?: number
  /** 命令输出摘录，供 reviewer 核对。不是 Agent 的自然语言总结 */
  outputExcerpt?: string
}

export interface AgentResult {
  /** 硬能力缺失时必须是 blocked 并给出 capability_gap，不得伪装成 done */
  status: 'done' | 'failed' | 'blocked'
  summary: string
  changedFiles?: FileChange[]
  tests?: TestOutcome[]
  commit?: string
  branch?: string
  artifacts?: string[]
  blockers?: Blocker[]
  questions?: string[]
}

export interface AgentCompletedPayload {
  result: AgentResult
}

export interface AgentDiscoveryError {
  adapterId: AdapterId
  code: ErrorCode
  message: string
}

export interface AgentDiscoveryCompletedPayload {
  total: number
  ready: number
  errors?: AgentDiscoveryError[]
  durationMs?: number
}

export interface CapabilityItem {
  id: CapabilityId
  name: string
  description?: string
  /** 硬能力用户不能勾选覆盖；软能力用户可以补充偏好 */
  hard: boolean
  /** detected=探测得到，adapter=适配器静态声明，user=用户补充的软能力偏好 */
  source: 'detected' | 'user' | 'adapter'
  /** 省略等同 true。false 表示适配器明确不支持，用于展示能力缺口 */
  supported?: boolean
  note?: string
}

/** 角色 ID。内置角色见 registry/roles.yaml，用户自定义角色不在注册表内 */
export type RoleId = string

export const BUILTIN_ROLE_IDS = [
  'orchestrator',
  'architect',
  'frontend_implementer',
  'general_implementer',
  'reviewer',
  'tester',
  'deployer',
  'integrator',
] as const

export interface AgentView {
  /** Agent 实例 ID，例如 agent_codex_default */
  id: string
  adapterId: AdapterId
  displayName: string
  version: string
  status: AgentStatus
  detectedAt: Timestamp
  capabilities: CapabilityItem[]
  /** 当前生效 Profile 里绑定到该 Agent 的角色（含 fallback） */
  assignedRoles: RoleId[]
  /** 该 Agent 作为 primary 的角色 */
  isPrimaryFor: RoleId[]
  /** 非 ready 状态时给用户的可操作说明，例如「已安装但未登录，请在终端执行 codex login」 */
  diagnosticMessage?: string
  authKind?: AuthKind
  executablePath?: string
  /** 适配器要求的最低版本，低于此值状态为 incompatible */
  minimumVersion?: string
  lastHealthyAt?: Timestamp
}

export interface AgentDiscoveryResult {
  discovered: AgentView[]
  total: number
  timestamp: Timestamp
  /** 探测失败的适配器。有 error 不代表整体失败，UI 要能同时展示成功和失败 */
  errors?: AgentDiscoveryError[]
  durationMs?: number
}

export interface AgentFailedPayload {
  errorCode: ErrorCode
  message: string
  blockers?: Blocker[]
}

export interface AgentProgressPayload {
  message: string
  percent?: number
  /** 未识别的原生事件原文，降级时保留 */
  raw?: Record<string, unknown>
}

export interface AgentQuestionPayload {
  questionId: string
  question: string
  options?: string[]
  expiresAt?: Timestamp
}

/** start() 的返回值。Adapter 必须在此返回明确的外部会话 ID，Hub 据此写入 SessionView.externalSessionId。 */
export interface AgentSessionHandle {
  /** Hub 本地会话 ID，由 Hub 生成后传给 Adapter，不是 Adapter 生成的 */
  sessionId: string
  /** Claude 的 session_id / Codex 的 thread_id / Antigravity 的 conversation_id。Adapter 声明 session_resume 能力时此字段必填；声明不支持时允许缺省 */
  externalSessionId?: string
  adapterId: AdapterId
  startedAt: Timestamp
  /** 本次会话是否可被后续 resume。与 DeclaredCapability 的 session_resume 可以不同——某些 Agent 只对特定模式的会话支持续接 */
  supportsResume: boolean
  workingDirectory?: string
}

/** 会话用途。同一 Agent 同时承担实现与审核时，两者的 purpose 必须不同，且必须是两个独立会话 */
export type SessionPurpose =
  | 'orchestrate'
  | 'architect'
  | 'implement'
  | 'review'
  | 'test'
  | 'deploy'
  | 'integrate'
  | 'adhoc'

/** new_session=默认，每个任务新开；resume_explicit=用户/调用方显式指定 resumeSessionId；continue_lineage=同一任务谱系内的后续节点继续用父会话 */
export type SessionReusePolicy =
  | 'new_session'
  | 'resume_explicit'
  | 'continue_lineage'

export interface AgentStartedPayload {
  sessionId: string
  externalSessionId?: string
  purpose: SessionPurpose
  reusePolicy: SessionReusePolicy
  worktreePath?: string
  branch?: string
}

/** 需要审批的动作全集，与 registry/roles.yaml 的 dangerousActions 一致 */
export type DangerousAction =
  | 'deploy'
  | 'git_push'
  | 'git_merge'
  | 'delete'
  | 'shell'
  | 'network'
  | 'db_migrate'

/** start() 的输入。对应施工方案 §8.1 的任务结构，字段名按 D11 转为 camelCase。 */
export interface AgentTaskSpec {
  /** Hub 本地会话 ID，由 Hub 生成后传入（裁决 D25）。Adapter 收到什么就用什么，不得自行生成——同一 Agent 承担实现与复核时必须是两个不同会话（裁决 D7），这个约束只有 Hub 能保证 */
  sessionId: string
  taskId: string
  nodeId: string
  workspaceId: string
  roleId: RoleId
  objective: string
  /** 并发写任务必须给独立 worktree。Adapter 必须以此为工作目录，不得回退到仓库主目录 */
  worktreePath?: string
  branch?: string
  baseCommit?: string
  /** glob。Adapter 若能在写入前拦截就拦截；不能拦截的，Hub 在 collectResult 时按 changedFiles 校验并发 task.path_violation */
  allowedPaths: string[]
  /** 开工前必读文档路径。项目背景靠这个和 handoff 注入，不靠把所有工作塞进一个长期会话——施工方案 §8.2 */
  readFirst?: string[]
  /** 验收命令。Adapter 不负责执行，只负责把它写进给 Agent 的指令 */
  acceptance?: string[]
  /** 需要人工审批的动作。Adapter 若不具备 tool_approval 硬能力，Hub 不得把带此字段的任务派给它 */
  requiresApproval?: DangerousAction[]
  sessionPurpose: SessionPurpose
  reusePolicy: SessionReusePolicy
  /** 仅当 reusePolicy=resume_explicit 时有值，且必须是明确的外部会话 ID。禁止 latest 之类不确定值——施工方案 §8.2 */
  resumeSessionId?: string
  /** 上游节点的 handoff 文件路径，由 Hub 注入 */
  handoffDocuments?: string[]
  /** 超过则 Hub 发起 graceful cancel。Adapter 自身不负责计时 */
  timeoutSeconds?: number
}

export interface AgentToolCallPayload {
  toolName: string
  argumentsExcerpt?: string
  resultSummary?: string
  durationMs?: number
  failed?: boolean
}

/** 事件聚合根类型，用于事件路由和订阅过滤 */
export type AggregateType =
  | 'agent'
  | 'task'
  | 'session'
  | 'approval'
  | 'update'
  | 'system'

export interface ApiError {
  code: ErrorCode
  /** 面向用户的中文说明，不得被前端用于逻辑判断 */
  message: string
  /** 结构化细节，例如越界路径列表、能力缺口列表、字段级校验错误 */
  detail?: Record<string, unknown>
  /** 同样的请求稍后重试是否有意义 */
  retryable: boolean
}

/** 协议版本。minor 只允许追加可选字段；major 变更必须全体停工对齐 */
export type ProtocolVersion = string

export interface ApiEnvelope<T = unknown> {
  success: boolean
  /** success 为 true 时存在 */
  data?: T
  /** success 为 false 时存在 */
  error?: ApiError
  /** 服务端生成，日志与错误上报的关联键 */
  requestId: string
  protocolVersion: ProtocolVersion
}

/** 对比度 */
export type ContrastMode =
  | 'normal'
  | 'high'

/** 字号缩放档位 */
export type FontScale =
  | 0.9
  | 1
  | 1.1
  | 1.2

/** 跟随系统 / 强制减少动效 / 强制保留动效。用三值枚举而不是 boolean|'system' 联合类型，是为了让 Python 和 Go 能生成干净的类型 */
export type ReduceMotion =
  | 'system'
  | 'on'
  | 'off'

/** 外观模式，与配色方案解耦 */
export type ThemeMode =
  | 'system'
  | 'light'
  | 'dark'

/** 配色方案，与外观模式独立选择 */
export type ThemePalette =
  | 'hq-blue'
  | 'ai-violet'
  | 'tech-cyan'
  | 'ops-emerald'

/** 界面密度 */
export type UiDensity =
  | 'comfortable'
  | 'compact'

export interface AppearanceSettings {
  mode: ThemeMode
  palette: ThemePalette
  density: UiDensity
  contrast: ContrastMode
  reduceMotion: ReduceMotion
  fontScale: FontScale
}

/** 审批决定 */
export type ApprovalDecision =
  | 'approve'
  | 'reject'

/** approve() 的输入。Hub 是审批时效的唯一权威——Adapter 不得自行判定过期后放行。 */
export interface ApprovalDispatch {
  /** Hub 侧审批 ID，与 ApprovalView.id 一致 */
  approvalId: string
  /** Adapter 发起审批时携带的供应商侧请求 ID。Adapter 负责把它与 approvalId 关联 */
  externalRequestId?: string
  decision: ApprovalDecision
  reason?: string
  decidedAt: Timestamp
}

/** 审批状态 */
export type ApprovalStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'expired'

export interface ApprovalQuery {
  status?: ApprovalStatus
  taskId?: string
}

/** 危险动作风险等级，决定审批 UI 的强度 */
export type RiskLevel =
  | 'low'
  | 'medium'
  | 'high'
  | 'critical'

export interface ApprovalRequiredPayload {
  approvalId: string
  action: DangerousAction
  targetResource: string
  riskLevel: RiskLevel
  expiresAt?: Timestamp
  /** 供应商侧审批请求 ID（裁决 D33）。ApprovalDispatch.externalRequestId 要求 Adapter 做关联，关联 ID 必须随事件走完全程，否则排障时和供应商日志对不上 */
  externalRequestId?: string
}

export interface ApprovalResolvedPayload {
  approvalId: string
  decision: ApprovalDecision
  reason?: string
  decidedAt: Timestamp
}

export interface ApprovalResponseInput {
  decision: ApprovalDecision
  reason?: string
}

export interface ApprovalView {
  id: string
  taskId: string
  taskObjective: string
  nodeId?: string
  requestAgentId: string
  requestAgentName: string
  roleId?: RoleId
  action: DangerousAction
  /** 将要作用的对象，例如 git push 的远端分支、要删除的路径、要执行的命令 */
  targetResource: string
  riskLevel: RiskLevel
  status: ApprovalStatus
  requestedAt: Timestamp
  decidedAt?: Timestamp
  decision?: ApprovalDecision
  reason?: string
  /** 超时后状态变 expired，对应错误码 APPROVAL_EXPIRED */
  expiresAt?: Timestamp
  /** 结构化上下文，例如完整命令行、影响文件数、diff 摘要 */
  details?: Record<string, unknown>
}

export interface BootstrapAgentsSummary {
  total: number
  ready: number
  /** not_logged_in / incompatible / error 的合计，首屏要引导用户去处理 */
  issues: number
  lastDiscoveryAt?: Timestamp
}

/** 客户端更新状态机，严格对应 OTA升级架构设计.md §6。所有状态必须持久化，进程重启后能恢复或进入明确失败态 */
export type UpdatePhase =
  | 'idle'
  | 'checking'
  | 'up_to_date'
  | 'available'
  | 'downloading'
  | 'downloaded'
  | 'verifying'
  | 'ready_to_install'
  | 'draining_tasks'
  | 'waiting_user'
  | 'installing'
  | 'health_checking'
  | 'succeeded'
  | 'rolling_back'
  | 'rollback_succeeded'
  | 'rollback_failed'
  | 'cancelled'
  | 'failed'

export interface BootstrapUpdateSummary {
  phase: UpdatePhase
  hasUpdate: boolean
  currentVersion: string
  latestVersion?: string
  mandatory?: boolean
  /** 存在未确认的升级回执，首屏要弹提示 */
  unacknowledgedResult?: boolean
}

export interface FeatureState {
  available: boolean
  /** available=false 时必填。例如「Update Agent 未运行」「Adapter 尚未接入（W2 未完成）」 */
  reason?: string
}

/** 分阶段交付期间，未就绪的工作包必须在这里明确报 unavailable 并给原因。前端据此禁用入口并显示说明，不允许用空列表伪装成「功能可用但没数据」——那会让集成期的问题晚好几天才暴露 */
export interface FeatureAvailability {
  agents: FeatureState
  teamProfiles: FeatureState
  tasks: FeatureState
  sessions: FeatureState
  approvals: FeatureState
  updates: FeatureState
}

/** 工作区版本控制类型。非 git 工作区不支持 worktree 隔离 */
export type Vcs =
  | 'git'
  | 'none'

/** 工作区当前能承接什么任务（裁决 D38）。非 Git 目录是合法工作区，但拿不到 worktree 隔离，因此只能派只读任务 */
export interface WorkspaceCapabilityView {
  canRunWriteTasks: boolean
  /** canRunWriteTasks 为 false 时说明原因，前端直接展示，不要自己编文案 */
  reason?: string
  /** 是否可以用 POST /workspaces/{id}/init-git 一键变成 Git 仓库 */
  canInitGit?: boolean
}

export interface WorkspaceView {
  id: string
  name: string
  /** 本机绝对路径 */
  path: string
  vcs: Vcs
  branch?: string
  /** 工作区是否干净。非 clean 时创建写任务要提示 */
  isClean?: boolean
  defaultProfileId?: string
  lastOpenedAt: Timestamp
  capabilities?: WorkspaceCapabilityView
  /** 是否存在 .hqagent/ 共享记忆目录（施工方案 §5.5）。不存在时引导用户初始化 */
  memoryDirPresent?: boolean
}

export interface BootstrapView {
  protocolVersion: ProtocolVersion
  appVersion: string
  environment: 'production' | 'development' | 'test'
  /** true 时前端显示全局维护 Gate，禁用新建任务入口 */
  maintenance: boolean
  appearance: AppearanceSettings
  agents: BootstrapAgentsSummary
  defaultProfileId?: string
  currentWorkspace?: WorkspaceView
  workspaceCount: number
  activeTasksCount: number
  pendingApprovalsCount: number
  update: BootstrapUpdateSummary
  features: FeatureAvailability
  /** 本次 Hub 启动的实例 ID。前端发现它变化即知道 Hub 重启过，应重新 bootstrap 而不是继续用旧 seq */
  instanceId?: string
  /** 前端据此建立事件流起点，避免首屏与事件流之间丢事件 */
  lastEventSeq: number
  hubStartedAt: Timestamp
}

/** graceful=向 Agent 发出停止指令并等待它自行收尾；force=直接终止进程/连接。Hub 先 graceful，超时后升级到 force */
export type CancelMode =
  | 'graceful'
  | 'force'

/** refused=Adapter 明确表示无法取消（例如底层 Agent 不提供中断入口）。此时 Hub 必须把节点标记为 failed 而不是 cancelled，并让用户知道该进程可能还在跑——不得假装取消成功 */
export type CancelOutcome =
  | 'stopped_gracefully'
  | 'force_killed'
  | 'already_finished'
  | 'not_found'
  | 'refused'

export interface CancelRequest {
  sessionId: string
  mode: CancelMode
  reason?: string
  /** mode=graceful 时的等待上限。到点后 Hub 会再发一次 mode=force，Adapter 不得自行延长 */
  graceSeconds?: number
}

export interface CancelResult {
  outcome: CancelOutcome
  completedAt: Timestamp
  elapsedMs?: number
  detail?: string
  /** outcome=refused 或 force_killed 后仍可能残留的进程。OTA 排空的 waitPids 需要它 */
  orphanProcessIds?: number[]
}

export interface ConnectionSettings {
  /** 只读展示，实际值来自 hub.json。用户不能在设置页改它 */
  hubUrl: string
  /** 一期恒为 false，云端属于 Phase 2 */
  cloudEnabled: boolean
  deviceName: string
}

/** 任务来源。一期只产生 desktop；pwa 为二期预留 */
export type TaskSource =
  | 'desktop'
  | 'pwa'
  | 'scheduler'
  | 'cli'

export interface CreateTaskInput {
  objective: string
  workspaceId: string
  /** 省略时用工作区默认 Profile，再省略用全局默认 */
  profileId?: string
  source?: TaskSource
  /** 单次任务覆盖，以 roleId 为键、agentInstanceId 为值。这是解析优先级的最高层 */
  roleOverrides?: Record<string, string>
  parentTaskId?: string
  allowedPaths?: string[]
  readFirst?: string[]
  acceptance?: string[]
  /** 省略时取角色默认的 requiresApproval，不是取空 */
  requiresApproval?: DangerousAction[]
}

/** 任务排空步骤，对应 OTA升级架构设计.md §7 的排空序列 */
export type DrainStep =
  | 'stop_accepting'
  | 'save_sessions'
  | 'wait_running_tasks'
  | 'backup_data'
  | 'ready'

export interface ProcessDescriptor {
  component: 'desktop' | 'core' | 'update-agent' | 'agent-worker'
  pid: number
  name?: string
}

export interface DrainProgress {
  /** step=ready 时必须给全。Updater 要等这些进程全部退出才能替换文件——漏一个就会出现文件占用导致安装失败 */
  waitPids?: ProcessDescriptor[]
  /** WAL checkpoint 与 SQLite Backup 是否已完成。false 时不得进入安装 */
  backupCompleted?: boolean
  step: DrainStep
  activeTasksRemaining: number
  percent: number
  startedAt?: Timestamp
  /** 超时后进入 waiting_user，由用户选择继续等待、取消任务或退出应用 */
  timeoutAt?: Timestamp
  waitingTaskIds?: string[]
}

export interface HubEvent<T = unknown> {
  /** 全局唯一。相同 eventId 不得重复应用 */
  eventId: string
  /** Hub 内单调递增序号，由 events 表自增列提供。前端重连携带最后确认的 seq，Hub 返回缺失事件 */
  seq: number
  occurredAt: Timestamp
  aggregateType: AggregateType
  /** 聚合根 ID，用于订阅过滤 */
  aggregateId: string
  /** 事件类型，取值见 events/event-dictionary.md */
  type: string
  /** 按 type 决定结构，见 agent-event.json 与事件字典 */
  payload: T
  protocolVersion: ProtocolVersion
  /** 业务标识冗余在顶层，前端时间线无需挖 payload */
  taskId?: string
  nodeId?: string
  roleId?: RoleId
  agentInstanceId?: string
  adapterId?: AdapterId
}

export interface EventPage {
  events: HubEvent[]
  lastSeq: number
  /** true 表示还有更多历史事件未补完，调用方应继续拉 */
  hasMore: boolean
}

/** 角色的文件系统权限 */
export type FilesystemAccess =
  | 'read_only'
  | 'read_write'

/** 界面语言 */
export type Language =
  | 'zh-CN'
  | 'en-US'

export interface GeneralSettings {
  language: Language
  launchAtLogin: boolean
  minimizeToTray: boolean
  /** true 时关窗不停止 Local Hub，任务继续在后台执行 */
  closeToTray: boolean
}

export interface HealthCheckOutcome {
  /** 对应 Update Plan v2 的 healthChecks */
  type: 'process' | 'http' | 'protocol' | 'database'
  component?: string
  passed: boolean
  detail?: string
  durationMs?: number
}

/** GET /healthz 的返回。这是唯一免鉴权的端点：Update Plan v2 的 healthChecks 要在没有 token 的情况下探活。只返回非敏感信息 */
export interface HealthView {
  /** Updater 的 health check 只认 ok */
  status: 'ok' | 'starting' | 'maintenance' | 'degraded'
  appVersion: string
  protocolVersion: ProtocolVersion
  pid: number
  startedAt: Timestamp
}

export interface HubRuntimeDescriptor {
  schemaVersion: 1
  /** 每次启动新生成。桌面壳据此识别并忽略陈旧 Descriptor——进程被强杀时文件可能残留，只看 pid 会连到已经不存在或被复用的进程上 */
  instanceId: string
  /** 随机高位端口，每次启动重新选取，不固定 */
  port: number
  /** 32 字节随机数的 base64url 编码，每次启动轮换。绝不允许出现在任何 HTTP 响应体、事件 payload 或日志里 */
  token: string
  /** hqagent-core.exe 的进程 ID，供桌面壳守护和 Updater 等待退出使用 */
  pid: number
  /** 只能是 127.0.0.1。Hub 不监听 0.0.0.0，不监听 :: */
  baseUrl: string
  appVersion: string
  protocolVersion: ProtocolVersion
  startedAt: Timestamp
}

/** 安装策略。一期只实现 windows-nsis */
export type InstallStrategy =
  | 'windows-nsis'
  | 'windows-msi'
  | 'windows-portable'
  | 'macos-app-bundle'
  | 'linux-appimage'
  | 'linux-deb'

/** 角色解析来源，对应施工方案 §6.3 的六级优先级。必须持久化，前端要展示为什么用了这个 Agent */
export type ResolveSource =
  | 'task_override'
  | 'workspace_profile'
  | 'global_profile'
  | 'capability_match'
  | 'fallback'
  | 'manual'

export interface NodeResolvedPayload {
  roleId: RoleId
  resolvedAgentId: string
  resolvedAgentName?: string
  resolveSource: ResolveSource
  isFallback: boolean
  fallbackReason?: string
  missingCapabilities?: CapabilityId[]
}

/** 任务节点状态。节点比任务多 resolving 和 skipped，不能复用 TaskStatus */
export type NodeStatus =
  | 'pending'
  | 'resolving'
  | 'running'
  | 'waiting_approval'
  | 'succeeded'
  | 'failed'
  | 'skipped'
  | 'cancelled'

export interface PageResult<T = unknown> {
  items: T[]
  total: number
  page: number
  pageSize: number
  hasMore: boolean
}

export interface PathViolationPayload {
  violationPaths: string[]
  allowedPaths: string[]
  /** 保留现场供人工查看，不自动清理 */
  worktreePath?: string
}

/** 升级渠道 */
export type UpdateChannel =
  | 'stable'
  | 'beta'

export interface ReleaseInfo {
  version: string
  channel: UpdateChannel
  /** 例如 windows-amd64-installer */
  targetKey: string
  publishedAt: Timestamp
  sizeBytes: number
  sha256: string
  /** Ed25519 签名 */
  signature?: string
  signatureAlgorithm?: string
  /** 为密钥轮换预留 */
  keyId?: string
  mandatory: boolean
  minimumSupportedVersion?: string
  releaseNotes?: string
  installStrategy?: InstallStrategy
  /** false 表示包含不可逆迁移，回滚需要额外确认 */
  rollbackCompatible?: boolean
}

export interface ResolveTeamProfileInput {
  profileId: string
  workspaceId?: string
  /** 可选，用于能力匹配时的提示 */
  taskObjective?: string
}

export interface ResolvedRoleItem {
  roleId: RoleId
  resolvedAgentId: string
  resolvedAgentName: string
  resolveSource: ResolveSource
  isFallback: boolean
  /** 降级原因必须可读，UI 要展示「为什么用了这个 Agent」 */
  fallbackReason?: string
  missingCapabilities?: CapabilityId[]
}

export interface ResolvedTeamGap {
  roleId: RoleId
  reason: string
  missingCapabilities?: CapabilityId[]
}

export interface ResolvedTeamView {
  profileId: string
  workspaceId?: string
  /** 以 roleId 为键 */
  resolvedRoles: Record<string, ResolvedRoleItem>
  hasGaps: boolean
  gaps: ResolvedTeamGap[]
  resolvedAt?: Timestamp
}

/** system 解析后的实际模式 */
export type ResolvedThemeMode =
  | 'light'
  | 'dark'

/** resume() 的输入。只有用户显式继续、工作流显式声明复用，或任务传入 resumeSessionId 时才会走到这里。 */
export interface ResumeRequest {
  /** Hub 本地会话 ID */
  sessionId: string
  externalSessionId?: string
  message: string
  acceptance?: string[]
}

export interface ResumeSessionInput {
  /** 继续该会话要做什么。恢复会话必须是显式动作，不允许空调用 */
  instruction: string
  workspaceId?: string
  acceptance?: string[]
}

/** 用户对该角色的额外约束，只能收紧、不能放宽角色默认权限 */
export interface RoleBindingConstraints {
  requireHardCapabilities?: CapabilityId[]
  allowShell?: boolean
  readOnlyFs?: boolean
}

/** 权限绑角色不绑品牌。换 Agent 后仍沿用同一角色权限（施工方案 §6.5） */
export interface RolePermissions {
  filesystem: FilesystemAccess
  shell: boolean
  canApprove: boolean
  /** 默认只允许一个 integrator 为 true */
  canMerge: boolean
  /** glob 列表。空数组表示不允许写任何业务路径 */
  writablePaths: string[]
  requiresApproval: DangerousAction[]
}

export interface RoleBindingView {
  roleId: RoleId
  roleName: string
  /** 空字符串表示未绑定，解析时走能力匹配 */
  primaryAgentId: string
  fallbackAgentIds: string[]
  constraints?: RoleBindingConstraints
  /** 省略时取 registry/roles.yaml 的默认权限 */
  permissions?: RolePermissions
}

export interface TeamProfilePolicies {
  /** 默认 fallback_then_ask（施工方案 §6.4） */
  missingAgentStrategy: 'fallback_then_ask' | 'fallback_then_fail' | 'ask'
  allowOneAgentMultipleRoles: boolean
  preferCrossAgentReview: boolean
  /** 实现与审核落到同一 Agent 时：isolated_session 必须新开独立 Session 并重读验收标准与 diff */
  sameAgentReviewStrategy: 'isolated_session' | 'forbid'
}

export interface SaveTeamProfileInput {
  /** 省略表示新建 */
  id?: string
  name: string
  description?: string
  scope: 'global' | 'workspace'
  workspaceId?: string
  isDefault?: boolean
  roleBindings: Record<string, RoleBindingView>
  policies?: TeamProfilePolicies
}

export interface SecuritySettings {
  /** 关闭需要二次确认，且不影响角色自身声明的 requiresApproval */
  requireApprovalForDangerousActions: boolean
  allowedPathsOnly: boolean
  approvalTimeoutMinutes?: number
}

export interface SessionQuery {
  workspaceId?: string
  agentId?: string
  roleId?: RoleId
  taskId?: string
  purpose?: SessionPurpose
  onlyValid?: boolean
  search?: string
  page?: number
  pageSize?: number
}

/** active=正在被某个节点使用；idle=可被显式恢复；closed=已正常结束；invalid=外部会话失效，只能新建 */
export type SessionStatus =
  | 'active'
  | 'idle'
  | 'closed'
  | 'invalid'

export interface SessionView {
  /** Hub 本地会话 ID，不是外部会话 ID */
  id: string
  status: SessionStatus
  workspaceId: string
  workspaceName: string
  roleId: RoleId
  agentInstanceId: string
  agentDisplayName: string
  adapterId?: AdapterId
  /** 供应商侧会话 ID。不支持恢复的 Agent 可以缺省（裁决 D28）——空字符串虽然能跑，但让前端分不清「这个 Agent 不支持恢复」和「支持但凭据丢了」，而 Session 页的「继续」按钮该不该出现正取决于这个区别 */
  externalSessionId?: string
  purpose: SessionPurpose
  reusePolicy: SessionReusePolicy
  /** 创建该会话的任务 */
  taskId?: string
  /** 创建该会话的节点 */
  nodeId?: string
  /** 任务血缘。continue_lineage 时指向被继续的会话 */
  parentSessionId?: string
  /** 谱系根任务，用于按谱系聚合展示 */
  rootTaskId?: string
  createdAt: Timestamp
  lastUsedAt: Timestamp
  /** false 表示外部会话已失效或适配器不支持恢复，只能新建；对应错误码 SESSION_NOT_RESUMABLE */
  isValid: boolean
  summary?: string
  turnCount?: number
}

export interface SubscribeEventsInput {
  /** 从该 seq 之后开始补发；省略表示只要新事件 */
  afterSeq?: number
  aggregateTypes?: AggregateType[]
  /** 只订阅某个任务的事件 */
  taskId?: string
}

export interface SystemMaintenancePayload {
  active: boolean
  /** 例如 update_install / manual */
  reason: string
  drainProgress?: DrainProgress
}

export interface TaskActionInput {
  action: 'pause' | 'resume' | 'cancel' | 'retry' | 'append_instruction'
  /** action=append_instruction 时必填 */
  instruction?: string
  /** action=retry 时可指定重跑某个节点 */
  nodeId?: string
}

export interface TaskArtifactView {
  id: string
  taskId: string
  title: string
  path: string
  type: 'file' | 'diff' | 'report' | 'log'
  sizeBytes: number
  createdAt: Timestamp
}

export interface TaskCreatedPayload {
  objective: string
  workspaceId: string
  profileId: string
  source: TaskSource
  parentTaskId?: string
}

export interface TaskNodeView {
  id: string
  taskId: string
  roleId: RoleId
  resolvedAgentId: string
  resolvedAgentName: string
  resolveSource: ResolveSource
  status: NodeStatus
  startedAt?: Timestamp
  completedAt?: Timestamp
  outputSummary?: string
  error?: string
  isFallback?: boolean
  fallbackReason?: string
  /** 本节点使用的 Hub 本地会话 ID。同一 Agent 承担实现与审核时，两个节点必须是两个不同的会话（裁决 D7） */
  sessionId?: string
  externalSessionId?: string
  worktreePath?: string
  branch?: string
  /** git diff --name-only 的结果 */
  changedFiles?: string[]
  /** 越界修改的路径。非空即判定任务失败，且保留 worktree 供人工查看 */
  violationPaths?: string[]
}

/** 任务状态。终态：succeeded / failed / cancelled */
export type TaskStatus =
  | 'draft'
  | 'queued'
  | 'running'
  | 'waiting_approval'
  | 'paused'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'unknown'

export interface TaskSummaryView {
  id: string
  objective: string
  workspaceId: string
  workspaceName: string
  profileId: string
  profileName: string
  status: TaskStatus
  source: TaskSource
  createdAt: Timestamp
  updatedAt: Timestamp
  durationMs?: number
  currentRole?: RoleId
  /** 当前执行 Agent 的显示名 */
  currentAgent?: string
  pendingApprovalId?: string
  parentTaskId?: string
}

export interface TaskDetailView extends TaskSummaryView {
  nodes: TaskNodeView[]
  artifacts: TaskArtifactView[]
  events: HubEvent[]
  worktreePath?: string
  branch?: string
  failureReason?: string
  /** 本任务允许修改的 glob 列表。任务结束用 git diff --name-only 对照校验 */
  allowedPaths?: string[]
  /** 执行前必须阅读的共享记忆文件 */
  readFirst?: string[]
  /** 验收命令，例如 npm test / pytest */
  acceptance?: string[]
  requiresApproval?: DangerousAction[]
  result?: AgentResult
  lastEventSeq?: number
}

export interface TaskQuery {
  page?: number
  pageSize?: number
  status?: TaskStatus
  workspaceId?: string
  search?: string
}

export interface TaskStatusChangedPayload {
  from: TaskStatus
  to: TaskStatus
  reason?: string
}

export interface TeamProfileView {
  id: string
  name: string
  description?: string
  scope: 'global' | 'workspace'
  /** scope=workspace 时必须存在 */
  workspaceId?: string
  isDefault: boolean
  /** 以 roleId 为键 */
  roleBindings: Record<string, RoleBindingView>
  policies?: TeamProfilePolicies
  updatedAt: Timestamp
}

export interface TelemetrySettings {
  /** 一期默认关闭且不上传。关闭后不得产生任何上传请求 */
  anonymousTelemetry: boolean
}

export interface UpdateActionInput {
  /** 与 OTA 文档 §13.2 的 9 条细路径一一对应。前端 UiGateway.controlUpdate 在 Gateway 层做映射，页面不感知 */
  action: 'check' | 'download' | 'cancel' | 'install' | 'defer' | 'acknowledge'
  /** action=defer 时必填 */
  deferMinutes?: number
  /** action=install 且存在运行任务时，是否允许取消任务以完成排空。默认 false */
  allowTaskCancellation?: boolean
}

/** 对应 update-agent.json。Update Agent 不向 Vue 暴露第二个 Base URL（裁决 D1） */
export interface UpdateAgentRuntimeDescriptor {
  schemaVersion: 1
  /** 每次启动新生成，用于识别陈旧 Descriptor */
  instanceId: string
  port: number
  /** Update Agent 的内部 Token，只由 Local Hub 与 W5 桌面壳读取。Vue 永远拿不到，也永远不直连 Update Agent */
  token: string
  pid: number
  baseUrl: string
  agentVersion: string
  startedAt: Timestamp
}

export interface UpdateResultView {
  schemaVersion: 2
  appId: string
  fromVersion: string
  toVersion: string
  channel?: UpdateChannel
  success: boolean
  finishedAt: Timestamp
  installStrategy?: InstallStrategy
  healthChecks?: HealthCheckOutcome[]
  healthCheckPassed?: boolean
  rolledBack?: boolean
  rollbackSucceeded?: boolean
  /** 回滚时实际恢复的数据库备份文件名。没有恢复则省略 */
  restoredDatabaseBackup?: string
  error?: string
  errorCode?: ErrorCode
  /** 用户是否已在界面确认。未确认的结果每次启动都要提示 */
  acknowledged: boolean
}

export interface UpdateCompletedPayload {
  result: UpdateResultView
}

export interface UpdateDownloadProgressPayload {
  downloadBytes: number
  totalBytes: number
  percent: number
  speedBytesPerSecond?: number
  etaSeconds?: number
}

export interface UpdateHealthCheckPayload {
  passed: boolean
  checks: HealthCheckOutcome[]
}

export interface UpdateRollbackPayload {
  reason: string
  succeeded?: boolean
  restoredDatabaseBackup?: string
}

export interface UpdateSettings {
  channel: UpdateChannel
  autoCheck: boolean
  autoDownload: boolean
  /** 一期恒为 false。安装必须由用户确认，因为要排空正在跑的任务 */
  autoInstall?: boolean
}

export interface UpdateStateView {
  phase: UpdatePhase
  currentVersion: string
  channel: UpdateChannel
  latestVersion?: string
  targetKey?: string
  releaseNotes?: string
  mandatory?: boolean
  downloadProgress?: number
  downloadBytes?: number
  totalBytes?: number
  speedBytesPerSecond?: number
  etaSeconds?: number
  drainProgress?: DrainProgress
  /** false 时前端必须禁用「立即安装」，不能靠 phase 自己推断 */
  canInstallNow: boolean
  deferredUntil?: Timestamp
  lastCheckedAt: Timestamp
  error?: string
  errorCode?: ErrorCode
  protocolVersion?: ProtocolVersion
}

export interface UpdateStateChangedPayload {
  state: UpdateStateView
  previousPhase?: UpdatePhase
}

export interface UpdateVerificationCompletedPayload {
  passed: boolean
  sizeMatched: boolean
  sha256Matched: boolean
  signatureValid: boolean
  keyId?: string
  /** 验签失败没有「忽略并继续」入口 */
  error?: string
}

export interface UserSettingsView {
  appearance: AppearanceSettings
  general: GeneralSettings
  connection: ConnectionSettings
  security: SecuritySettings
  updates: UpdateSettings
  telemetry: TelemetrySettings
  dataDir?: string
  logDir?: string
  appVersion?: string
  protocolVersion?: ProtocolVersion
}

/** Adapter 必须声明的供应商事件到统一事件字典的映射表。事件字典已在 FZ-1 冻结（28 条），Adapter 不得新增事件类型。 */
export interface VendorEventMapping {
  vendorType: string
  /** 必须是 events/event-dictionary.md 里已有的类型 */
  unifiedType: string
  /** true 表示该供应商事件被有意丢弃。丢弃必须显式声明并计数，不得静默吞掉 */
  dropped?: boolean
  note?: string
}

export interface WorkspaceQuery {
  search?: string
  limit?: number
}

export interface WsTicket {
  /** 一次性、单次使用。用过即作废，过期即作废，重放必须失败 */
  ticket: string
  expiresAt: Timestamp
  /** 固定 30 秒。Ticket 不写日志、不持久化、不进 localStorage */
  ttlSeconds: 30
}

export interface WsTicketRequest {
  /** 一期只有事件流一种用途 */
  purpose?: 'events'
}

export const BUILTIN_ROLES = [
  { id: 'orchestrator', displayName: '总控', description: '总控、拆解、调度、状态汇总和异常处理' },
  { id: 'architect', displayName: '架构', description: '需求分析、方案、架构、接口和约束定义' },
  { id: 'frontend_implementer', displayName: '前端实现', description: '页面、组件、样式、交互和前端测试' },
  { id: 'general_implementer', displayName: '通用实现', description: '后端、客户端、脚本、数据库和通用工程实现' },
  { id: 'reviewer', displayName: '审核', description: '方案审核、代码审查、风险检查和验收' },
  { id: 'tester', displayName: '测试', description: '测试设计、执行、证据收集和回归验证' },
  { id: 'deployer', displayName: '发布', description: '构建、发布、部署、回滚和运行维护' },
  { id: 'integrator', displayName: '合并', description: '跨分支检查和最终合并；默认只允许一个 integrator 执行最终合并' },
] as const

export const DANGEROUS_ACTIONS = [
  'deploy',
  'git_push',
  'git_merge',
  'delete',
  'shell',
  'network',
  'db_migrate',
] as const

export const ERROR_CATALOG: Record<ErrorCode, { http: number; retryable: boolean }> = {
  BAD_REQUEST: { http: 400, retryable: false },
  VALIDATION_FAILED: { http: 422, retryable: false },
  UNAUTHORIZED: { http: 401, retryable: false },
  ORIGIN_NOT_ALLOWED: { http: 403, retryable: false },
  NOT_FOUND: { http: 404, retryable: false },
  CONFLICT: { http: 409, retryable: false },
  IDEMPOTENCY_MISMATCH: { http: 409, retryable: false },
  PROTOCOL_VERSION_MISMATCH: { http: 426, retryable: false },
  HUB_NOT_READY: { http: 503, retryable: true },
  HUB_MAINTENANCE: { http: 503, retryable: true },
  EVENT_CURSOR_EXPIRED: { http: 410, retryable: false },
  FEATURE_UNAVAILABLE: { http: 503, retryable: true },
  AGENT_NOT_FOUND: { http: 404, retryable: false },
  AGENT_OFFLINE: { http: 409, retryable: true },
  AGENT_NOT_LOGGED_IN: { http: 409, retryable: false },
  AGENT_INCOMPATIBLE: { http: 409, retryable: false },
  CAPABILITY_MISSING: { http: 409, retryable: false },
  ROLE_UNRESOLVED: { http: 409, retryable: false },
  SESSION_NOT_RESUMABLE: { http: 409, retryable: false },
  TASK_NOT_CANCELLABLE: { http: 409, retryable: false },
  TASK_ACTION_INVALID: { http: 409, retryable: false },
  WORKTREE_BUSY: { http: 409, retryable: true },
  PATH_NOT_ALLOWED: { http: 403, retryable: false },
  APPROVAL_REQUIRED: { http: 409, retryable: false },
  APPROVAL_EXPIRED: { http: 410, retryable: false },
  APPROVAL_ALREADY_DECIDED: { http: 409, retryable: false },
  UPDATE_NOT_AVAILABLE: { http: 409, retryable: false },
  UPDATE_BUSY: { http: 409, retryable: true },
  UPDATE_VERIFY_FAILED: { http: 422, retryable: false },
  UPDATE_DRAIN_TIMEOUT: { http: 409, retryable: true },
  INTERNAL: { http: 500, retryable: true },
}
