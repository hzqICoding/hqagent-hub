// 此文件由 scripts/protocol/generate.py 生成，请勿手改。
// 改协议请改 packages/protocol/schema/ 或 registry/，然后重新运行:
//     pwsh scripts/protocol/generate.ps1

export const PROTOCOL_VERSION = '0.11.1' as const

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
  | 'REMOTE_AUTH_REQUIRED'
  | 'REMOTE_CSRF_REJECTED'
  | 'REMOTE_DEVICE_OFFLINE'
  | 'REMOTE_DEVICE_REVOKED'
  | 'REMOTE_DEVICE_AUTH_FAILED'
  | 'REMOTE_PAIRING_EXPIRED'
  | 'REMOTE_PAIRING_CONFLICT'
  | 'REMOTE_PAIRING_INVALID'
  | 'REMOTE_COMMAND_EXPIRED'
  | 'REMOTE_COMMAND_WITHDRAWN'
  | 'REMOTE_WITHDRAWAL_UNCONFIRMED'
  | 'REMOTE_STORE_CHANGED'
  | 'REMOTE_EPOCH_STALE'
  | 'REMOTE_PROTOCOL_UNSUPPORTED'
  | 'REMOTE_EVENT_CONFLICT'
  | 'REMOTE_ACK_CONFLICT'
  | 'REMOTE_SEQUENCE_GAP'
  | 'REMOTE_APPROVAL_FORBIDDEN'
  | 'CONVERSATION_AUTHORITY_MISMATCH'
  | 'REMOTE_TARGET_MISMATCH'
  | 'REMOTE_SCENE_VERSION_MISMATCH'
  | 'REMOTE_CURSOR_EXPIRED'
  | 'REMOTE_CURSOR_INVALID'
  | 'REMOTE_RATE_LIMITED'
  | 'REMOTE_FRAME_TOO_LARGE'
  | 'REMOTE_WITHDRAWAL_TOO_LATE'
  | 'REMOTE_PAIRING_IN_PROGRESS'
  | 'REMOTE_SERVER_UNREACHABLE'
  | 'REMOTE_SERVER_ORIGIN_INVALID'
  | 'REMOTE_CONVERSATION_BUSY'
  | 'REMOTE_STATE_NOT_READY'
  | 'REMOTE_SYNC_CONFLICT'
  | 'REMOTE_SYNC_DISABLED'
  | 'REMOTE_DELIVERY_EXPIRED'
  | 'REMOTE_REVISION_REQUIRED'
  | 'REMOTE_SYNC_RESOURCE_LIMIT'
  | 'REMOTE_DEVICE_SUSPENDED'
  | 'REMOTE_API_TOKEN_INVALID'
  | 'REMOTE_API_TOKEN_EXPIRED'
  | 'REMOTE_API_TOKEN_SCOPE_INSUFFICIENT'
  | 'REMOTE_AUTH_AMBIGUOUS'
  | 'REMOTE_QUERY_TIMEOUT'
  | 'REMOTE_QUERY_TOO_LARGE'
  | 'NATIVE_SESSION_ACTIVE'
  | 'NATIVE_SESSION_UNSUPPORTED'
  | 'NATIVE_SESSION_CHANGED'
  | 'NATIVE_SESSION_WRITER_CONFLICT'
  | 'REMOTE_ROOT_NOT_AUTHORIZED'
  | 'REMOTE_PATH_OUTSIDE_ROOT'
  | 'REMOTE_DIRECTORY_CHANGED'
  | 'ATTACHMENT_TOO_LARGE'
  | 'ATTACHMENT_TYPE_UNSUPPORTED'
  | 'ATTACHMENT_COUNT_EXCEEDED'
  | 'ATTACHMENT_QUOTA_EXCEEDED'
  | 'ATTACHMENT_HASH_MISMATCH'
  | 'AGENT_IMAGE_UNSUPPORTED'
  | 'ATTACHMENT_DOWNLOAD_FAILED'
  | 'ATTACHMENT_NOT_READY'
  | 'ATTACHMENT_IN_USE'
  | 'ATTACHMENT_THUMBNAIL_UNAVAILABLE'
  | 'ATTACHMENT_PREPARATION_INTERRUPTED'
  | 'PI_GUARD_UNAVAILABLE'
  | 'PI_UNCONTROLLED_EXTENSIONS'
  | 'PI_TOOL_CALL_BLOCKED'

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
  'analyst',
  'planner',
  'developer',
] as const

export type PiGuardReason =
  | 'guard_not_loaded'
  | 'uncontrolled_extensions'
  | 'policy_unavailable'
  | 'tool_inventory_changed'
  | 'guard_timeout'
  | 'invalid_request'
  | 'argument_mismatch'
  | 'path_outside_scope'
  | 'unsupported_shell'
  | 'approval_required'
  | 'approval_rejected'
  | 'approval_expired'
  | 'read_only_tool'
  | 'tool_not_allowed'

/** Safe diagnostic only. ready requires verified exclusive Hub extension loading and stable tools/policy. Not an OS sandbox guarantee. No extension source, path, arguments or credentials. */
export interface RuntimeGuardView {
  status: 'unverified' | 'ready' | 'blocked'
  isolation: 'unknown' | 'hub_extension_only'
  checkedAt: string
  policyRevision?: string
  reasons: PiGuardReason[]
}

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
  guard?: RuntimeGuardView
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

/** Immutable verified metadata only: no URL, path, base64, body or credentials. Command IDs are public server attachment IDs, at most five, bound to one owner/worker/store/conversation. */
export interface AttachmentManifestItem {
  attachmentId: string
  fileName: string
  kind: 'image' | 'file'
  mimeType: 'image/jpeg' | 'image/png' | 'image/webp' | 'image/gif' | 'application/pdf' | 'text/plain'
  sizeBytes: number
  sha256: string
}

/** Hub to local Adapter only: verified managed read-only input path, never HTTP response or remote command. Recheck hash/size and allowed input location before passing to model. */
export interface AgentInputAttachment {
  attachment: AttachmentManifestItem
  localPath: string
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
  readOnly?: boolean
  modelId?: string
  reasoningEffort?: string
  roleInstructions?: string
  inputAttachments?: AgentInputAttachment[]
}

export interface AgentToolCallPayload {
  toolName: string
  argumentsExcerpt?: string
  resultSummary?: string
  durationMs?: number
  failed?: boolean
  /** 供应商报告的真实命令退出码，仅在命令完成且已知时提供。 */
  exitCode?: number
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

/** Delete only unreferenced uploaded attachment; cannot delete attached history through this endpoint. */
export interface AttachmentDeletedView {
  attachmentId: string
  deleted: true
}

/** Decimal MB/GB. jpg/jpeg/png/webp/gif content-detected; text/source normalized as UTF-8 text/plain; PDF detected by content. Frozen whitelist in contract/fixture. */
export interface AttachmentLimits {
  imageMaxBytes: 10000000
  fileMaxBytes: 20000000
  messageMaxCount: 5
  accountQuotaBytes: 5000000000
  unattachedTtlSeconds: 86400
  imageMimeTypes: ('image/jpeg' | 'image/png' | 'image/webp' | 'image/gif')[]
  fileExtensions: string[]
}

/** supported iff CLI entry/runtime/model path and integration verification all succeed. Unknown/unsupported reject image before send. Missing capability means unknown; never infer from provider brand. */
export interface ImageInputCapability {
  support: 'unknown' | 'unsupported' | 'supported'
  cliEntry: 'unknown' | 'unsupported' | 'supported'
  runtimeImplemented: boolean
  verified: boolean
  mimeTypes: ('image/jpeg' | 'image/png' | 'image/webp' | 'image/gif')[]
  maxBytes: number
  reason?: string
}

/** Current HTTP/local and revision 5 Agent types. NativeAgentType is the immutable revision 3/4 domain. */
export type RuntimeNativeAgentType =
  | 'claude'
  | 'codex'
  | 'pi'

/** Exact resolved Agent instance and model target; modelId omitted only for default selector, whose effective provider/model is included in capability revision. PI uses first-slash provider/modelId and pi-rpc-images-v1. Missing identity/verification means unknown, not supported. */
export interface RuntimeNativeImageCapability {
  agentType: RuntimeNativeAgentType
  imageInput: ImageInputCapability
  /** Exact model selector; reject URLs, filesystem paths, dot/dot-dot segments or credentials. Omitted modelId selects CLI default, not an invented model name. */
  modelId?: string
  transport?: string
  agentId?: string
}

/** Exact resolved Agent instance and model target; modelId omitted only for default selector, whose effective provider/model is included in capability revision. PI uses first-slash provider/modelId and pi-rpc-images-v1. Missing identity/verification means unknown, not supported. */
export interface RuntimeRoleImageCapability {
  roleId: string
  agentId: string
  imageInput: ImageInputCapability
  /** Exact model selector; reject URLs, filesystem paths, dot/dot-dot segments or credentials. Omitted modelId selects CLI default, not an invented model name. */
  modelId?: string
  transport?: string
  agentType?: RuntimeNativeAgentType
}

/** All selected scenario roles, not only executor; native uses exactly one native entry and no scenario roles. Missing role or stale information fails closed. */
export interface AttachmentTargetCapabilities {
  conversationKind: 'scenario' | 'native'
  capabilityRevision: number
  roles: RuntimeRoleImageCapability[]
  native?: RuntimeNativeImageCapability
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

/** Cancel owned work only; never starts the cancel probe or new model inference. */
export interface CancelLocalImageVerificationInput {
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

/** Open scene identifier. analyze, plan, develop are builtin; custom scene IDs are generated by the Worker. */
export type LocalSceneId = string

export interface CreateLocalConversationInput {
  title: string
  workspaceId: string
  sceneId: LocalSceneId
}

/** Validated builtin execution and permission type. Template naming cannot grant extra permissions. */
export type LocalBaseRoleId =
  | 'analyst'
  | 'planner'
  | 'developer'
  | 'reviewer'

export interface CreateLocalRoleTemplateInput {
  name: string
  baseRoleId: LocalBaseRoleId
  instructions: string
}

export interface LocalRoleConfig {
  roleId: string
  agentInstanceId: string
  instructions: string
  modelId?: string
  reasoningEffort?: string
  enabled: boolean
  roleName?: string
  roleTemplateId?: string
  roleTemplateVersion?: number
}

/** independent使用独立reviewer；original_planner以验收阶段恢复本轮planner原生会话。省略时兼容旧独立模式。 */
export type ReviewMode =
  | 'independent'
  | 'original_planner'

export interface CreateLocalSceneInput {
  name: string
  description?: string
  roles: LocalRoleConfig[]
  reviewMode?: ReviewMode
}

export interface RoleExecutionOptions {
  modelId?: string
  reasoningEffort?: string
  instructions?: string
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
  workflowRoles?: string[]
  roleExecutions?: Record<string, RoleExecutionOptions>
  resumeSessions?: Record<string, string>
  reviewMode?: ReviewMode
}

/** Directories only; no files, full path, recursive children or raw error details. */
export interface DirectoryEntry {
  name: string
  isGitRepository: boolean
  directoryToken: string
}

/** Missing directoryToken selects root itself. No path input. Default limit 50. Opaque signed Worker tokens bind root/version/store/real directory identity. */
export interface DirectoryListingInput {
  rootId: string
  rootVersion: number
  directoryToken?: string
  cursor?: string
  limit?: number
}

/** One directory level, <=100 entries, <=1MiB JSON. Cursor pins listing identity/order and expires in 15 minutes. Recheck real paths for each entry. */
export interface DirectoryListingPage {
  rootId: string
  rootVersion: number
  directoryToken: string
  entries: DirectoryEntry[]
  hasMore: boolean
  nextCursor?: string
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

export interface LocalAgentModel {
  /**  For PI use provider/modelId, split the first slash only; pi-rpc-images-v1 transport. Resolve default selection before verification and invalidate on effective provider/model/config change. */
  id: string
  name: string
  efforts: string[]
  isDefault: boolean
}

export interface LocalAgentModelsView {
  agentInstanceId: string
  models: LocalAgentModel[]
  verified: boolean
  reason?: string
}

/** Computer-owned safe blob ID; no path returned. Independent of remote pairing and account quota; local same per-file/count limits apply. */
export interface LocalAttachmentView {
  attachment: AttachmentManifestItem
  conversationId: string
  state: 'uploaded' | 'attached'
  createdAt: string
  expiresAt?: string
  syncStatus?: 'not_synced' | 'pending_upload' | 'available' | 'unavailable'
  syncError?: ErrorCode
}

export interface LocalAuthInput {
  code: string
}

export interface LocalAuthView {
  authenticated: boolean
  protocolVersion: string
}

export interface LocalAuthorizedRoot {
  rootId: string
  displayName: string
  path: string
  version: number
}

/** Only authenticated local API. Existing IDs kept; new IDs allocated by computer. No UNC/device namespaces; canonical path required. */
export interface LocalAuthorizedRootInput {
  rootId?: string
  displayName: string
  path: string
}

/** Atomic replace with CAS. Removed root IDs never reused; changed grants invalidate selection tokens immediately. */
export interface LocalAuthorizedRootsInput {
  expectedVersion: number
  roots: LocalAuthorizedRootInput[]
}

/** Default roots=[] and version=1. Roots can only be configured on this computer. */
export interface LocalAuthorizedRootsView {
  version: number
  roots: LocalAuthorizedRoot[]
}

export interface LocalConnectionCodeView {
  code: string
  expiresInSeconds: number
}

/** 200 only after Hub-owned rows/files erased. No false cloud completion. Same key/version replays minimal receipt; other key after deletion404. Vendor CLI records untouched. */
export interface LocalConversationDeletionView {
  conversationId: string
  deletedAt: Timestamp
  localDeleted: true
  remoteCleanup: 'not_required' | 'pending' | 'confirmed' | 'unconfirmed'
}

export type NativeActivity =
  | 'unknown'
  | 'likely_active'
  | 'closed_confirmed'

/** Unknown is read-only. Positive matching live process or post-confirmation changes invalidate confirmation; absence alone never proves closure. */
export interface NativeActivityEvidence {
  activity: NativeActivity
  observedAt: string
  processMatch: 'present' | 'absent' | 'unknown'
  recentlyModified: boolean
  terminalClosedConfirmedAt?: string
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

/**  Missing conversationKind means scenario (requires existing scene fields). Native requires agentType/nativeSessionId and omits scene fields; exact vendor session binding remains local. */
export interface LocalConversationView {
  id: string
  title: string
  workspaceId: string
  sceneId?: LocalSceneId
  createdAt: Timestamp
  updatedAt: Timestamp
  activeRunId?: string
  lastRunId?: string
  /** Metadata revision. Legacy records are revision 1; message/run updates do not increment this revision. */
  version?: number
  /** Archived conversations remain readable. Legacy records default to false. */
  archived?: boolean
  lastRunStatus?: TaskStatus
  /** Legacy metadata only; not a write restriction in R1.5. Missing=local. */
  authority?: 'local' | 'remote'
  visibility?: 'both' | 'pc_only' | 'mobile_only'
  busy?: boolean
  busyObservedAt?: string
  conversationKind?: 'scenario' | 'native'
  agentType?: RuntimeNativeAgentType
  nativeSessionId?: string
  nativeActivity?: NativeActivityEvidence
  nativeSourceRevision?: string
}

export interface LocalEventPage {
  events: HubEvent[]
  nextSeq: number
  hasMore: boolean
}

/** Allowlisted verification.py diagnostics only. Omit None codes; unknown exception classes become UnknownError. No raw/message/output/prompt/path fields. */
export interface LocalImageProbeDiagnostic {
  result?: 'ok' | 'exception' | 'adapter_failure'
  elapsedMs?: number
  matched?: boolean
  kind?: AdapterFailureKind
  code?: ErrorCode
  retryable?: boolean
  exceptionType?: string
  startupStage?: 'process.start' | 'initialize' | 'model/list' | 'thread/start' | 'thread/resume' | 'turn/start'
  osError?: number
  winError?: number
  outcome?: CancelOutcome
  orphanProcessIds?: number[]
}

/** Structured stage hooks; not_run is not a failed completed probe. */
export interface LocalImageProbeProgress {
  state: 'not_run' | 'running' | 'passed' | 'failed'
  startedAt?: Timestamp
  finishedAt?: Timestamp
}

export interface LocalImageProbeProgressSet {
  new: LocalImageProbeProgress
  resume: LocalImageProbeProgress
  mixedFive: LocalImageProbeProgress
  cancel: LocalImageProbeProgress
  error: LocalImageProbeProgress
}

/** Existing five boolean outcomes; unexecuted legacy outcomes remain false. API mixedFive maps exactly to persisted CLI probe mixed-five. */
export interface LocalImageProbeResults {
  new: boolean
  resume: boolean
  mixedFive: boolean
  cancel: boolean
  error: boolean
}

/** Closed stage-key map. Legacy records can lack error.check; no arbitrary vendor diagnostic fields. API stage keys use camelCase; map source new.start to newStart etc. Do not dump raw storage keys or values. */
export interface LocalImageVerificationDiagnostics {
  newStart?: LocalImageProbeDiagnostic
  newCollect?: LocalImageProbeDiagnostic
  newRecognition?: LocalImageProbeDiagnostic
  resumeStart?: LocalImageProbeDiagnostic
  resumeCollect?: LocalImageProbeDiagnostic
  resumeRecognition?: LocalImageProbeDiagnostic
  mixedFiveStart?: LocalImageProbeDiagnostic
  mixedFiveCollect?: LocalImageProbeDiagnostic
  mixedFiveRecognition?: LocalImageProbeDiagnostic
  cancelStart?: LocalImageProbeDiagnostic
  cancelStop?: LocalImageProbeDiagnostic
  errorCheck?: LocalImageProbeDiagnostic
}

/** Exact local instance/runtime/configuration. Unknown version omitted. Opaque revision contains no path or credential; start requires a detected version and supported transport. */
export interface LocalImageVerificationTarget {
  agentId: string
  agentType: string
  /** Exact model selector; reject URLs, filesystem paths, dot/dot-dot segments or credentials. Omitted modelId selects CLI default, not an invented model name. For PI use provider/modelId, split the first slash only; pi-rpc-images-v1 transport. Resolve default selection before verification and invalidate on effective provider/model/config change. */
  modelId?: string
  cliVersion?: string
  transport?: string
  targetRevision: string
}

/** Historical observation, not proof the current target is verified. Publish capability only after complete probes, confirmed cleanup and unchanged binding. */
export interface LocalImageVerificationRecord {
  recordId: string
  target: LocalImageVerificationTarget
  passed: boolean
  probes: LocalImageProbeResults
  diagnostics: LocalImageVerificationDiagnostics
  mimeTypes: ('image/png' | 'image/jpeg' | 'image/webp' | 'image/gif')[]
  observedAt: Timestamp
  jobId?: string
}

/** Local maintenance job, not TaskStatus or a wire command. Cancellation request is not confirmed stop; interrupted/unconfirmed retains slot until exact execution ends. */
export interface LocalImageVerificationJobView {
  jobId: string
  target: LocalImageVerificationTarget
  status: 'queued' | 'running' | 'cancel_requested' | 'succeeded' | 'failed' | 'cancelled' | 'interrupted'
  acknowledgeModelUsage: true
  acknowledgedAt: Timestamp
  requestId: string
  createdAt: Timestamp
  updatedAt: Timestamp
  startedAt?: Timestamp
  finishedAt?: Timestamp
  probes: LocalImageProbeProgressSet
  diagnostics: LocalImageVerificationDiagnostics
  result?: LocalImageVerificationRecord
  appliedToCurrentTarget: boolean
  cleanupState: 'not_started' | 'pending' | 'confirmed' | 'unconfirmed'
  executionMayStillBeRunning: boolean
  orphanProcessIds: number[]
  slotHeld: boolean
}

export interface LocalImageVerificationUsage {
  sceneId: string
  roleId: string
}

/** One instance x exact selector. Omitted modelId=default. Effective passed=false for stale/unavailable. Old unbound records never auto-apply across instances/models. */
export interface LocalImageVerificationState {
  target: LocalImageVerificationTarget
  inUse: boolean
  usages: LocalImageVerificationUsage[]
  usagesTruncated: boolean
  status: 'unverified' | 'passed' | 'failed' | 'stale' | 'unavailable'
  passed: boolean
  invalidated: boolean
  invalidationReasons: ('cli_version_changed' | 'model_changed' | 'runtime_changed' | 'configuration_changed' | 'legacy_unbound' | 'target_unavailable')[]
  lastRecord?: LocalImageVerificationRecord
  activeJobId?: string
  lastJobId?: string
}

/** Default50/max100; cursor binds filters and snapshot; hasMore requires nextCursor. */
export interface LocalImageVerificationPage {
  items: LocalImageVerificationState[]
  hasMore: boolean
  nextCursor?: string
}

/** Inspect all associated runs/tasks, not recent200; truncate only returned IDs. No model outputs, paths or task specs. */
export interface LocalMaintenanceConflictDetail {
  reason: 'verification_in_progress' | 'target_changed' | 'agent_unavailable' | 'version_mismatch' | 'active_runs' | 'recovery_required' | 'cancellation_unconfirmed' | 'deleting'
  activeJobId?: string
  currentVersion?: number
  blockingRunIds?: string[]
  hasMoreBlockingRuns?: boolean
}

export interface LocalMaintenanceConflictError {
  code: 'CONFLICT'
  message: string
  retryable: false
  detail: LocalMaintenanceConflictDetail
}

export interface LocalMessageReceipt {
  commandId: string
  conversationId: string
  messageId: string
  runId: string
  status: 'queued' | 'accepted'
  duplicate: boolean
}

export interface LocalMessageView {
  id: string
  conversationId: string
  sequence: number
  role: 'user' | 'assistant' | 'system'
  text: string
  runId?: string
  createdAt: Timestamp
  attachments?: AttachmentManifestItem[]
}

export type NativeFormatStatus =
  | 'readable'
  | 'unsupported'

export type PiNativeReaderId =
  | 'pi.jsonl.v3.tree'

export interface PiNativeFormatProfile {
  readerId: PiNativeReaderId
  sessionVersion: 3
  structure: 'tree'
  branchSelection: 'last_persisted_entry'
}

export type RuntimeNativeUnsupportedReason =
  | 'reader_not_implemented'
  | 'unsupported_version'
  | 'unsupported_structure'
  | 'invalid_record'
  | 'invalid_tree'
  | 'current_branch_unavailable'

/** readable requires a tested version/profile readerId. unsupported requires sanitized reason; never guess a format. PI readable requires readerId=pi.jsonl.v3.tree and pi profile; unsupported requires unsupportedReason and sanitized reason. Phase 1 reports reader_not_implemented, never a guessed readable profile. */
export interface RuntimeNativeFormatView {
  status: NativeFormatStatus
  readerId?: string
  cliVersion?: string
  reason?: string
  pi?: PiNativeFormatProfile
  unsupportedReason?: RuntimeNativeUnsupportedReason
}

/** Worker-local opaque index ID, not a path or fuzzy CLI ID. Exact vendor ID is kept in the local binding. Redact before title truncation. No body, tool arguments or process IDs in index. */
export interface RuntimeNativeSessionIndex {
  nativeSessionId: string
  workspaceId: string
  agentType: RuntimeNativeAgentType
  title: string
  createdAt: string
  updatedAt: string
  indexVersion: number
  sourceRevision: string
  format: RuntimeNativeFormatView
  activity: NativeActivityEvidence
}

/** Local index page; default limit 50, max 100. hasMore requires nextCursor, otherwise omit. No pairing or cloud identity needed. */
export interface LocalNativeSessionPage {
  items: RuntimeNativeSessionIndex[]
  hasMore: boolean
  nextCursor?: string
}

export interface LocalRoleTemplateView {
  id: string
  name: string
  baseRoleId: LocalBaseRoleId
  instructions: string
  version: number
  createdAt: Timestamp
  updatedAt: Timestamp
}

export interface LocalSceneView {
  id: LocalSceneId
  name: string
  description: string
  readOnly: boolean
  version: number
  roles: LocalRoleConfig[]
  updatedAt: Timestamp
  reviewMode?: ReviewMode
  isBuiltin?: boolean
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

/** 角色解析来源，对应施工方案 §6.3 的六级优先级。必须持久化，前端要展示为什么用了这个 Agent */
export type ResolveSource =
  | 'task_override'
  | 'workspace_profile'
  | 'global_profile'
  | 'capability_match'
  | 'fallback'
  | 'manual'

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
  /** acceptance表示验收阶段；原会话验收的roleId仍为planner，保持会话权限一致。 */
  phase?: 'execution' | 'acceptance'
  reviewVerdict?: 'passed' | 'changes_requested' | 'insufficient_evidence'
  reviewSourceNodeId?: string
  reviewEvidenceId?: string
}

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

/** Scenario retains sceneSnapshot. Native uses a single bound Runtime/Agent and omits sceneSnapshot; no invented scenario roles. Existing taskId remains execution Task identity. */
export interface LocalRunView {
  id: string
  conversationId: string
  messageId: string
  taskId: string
  sceneSnapshot?: LocalSceneView
  status: TaskStatus
  createdAt: Timestamp
  updatedAt: Timestamp
  error?: string
  task?: TaskDetailView
  conversationKind?: 'scenario' | 'native'
  agentType?: RuntimeNativeAgentType
}

/** Public owner-scoped ID. Explicit pending/unavailable prevents dangling downloads. Thumbnail ready never implies original is safe to inline. */
export interface MessageAttachmentView {
  attachmentId: string
  fileName: string
  kind: 'image' | 'file'
  mimeType: 'image/jpeg' | 'image/png' | 'image/webp' | 'image/gif' | 'application/pdf' | 'text/plain'
  sizeBytes: number
  sha256: string
  availability: 'pending_upload' | 'available' | 'unavailable'
  thumbnailStatus: 'pending' | 'ready' | 'unavailable' | 'not_applicable'
  errorCode?: ErrorCode
}

export type NativeAgentType =
  | 'claude'
  | 'codex'

/** Server-generated from authenticated explicit user action, persisted by Worker at admission and bound to source revision. No caller-supplied owner ID. */
export interface NativeClosureConfirmation {
  confirmationId: string
  confirmedAt: string
  requestId: string
  sourceRevision: string
  terminalClosedConfirmed: true
}

/** Explicit renewed attestation if imported conversation detects external changes. Never override positive live-process evidence. */
export interface NativeContinuationConfirmationInput {
  terminalClosedConfirmed: true
  sourceRevision: string
}

/** readable requires a tested version/profile readerId. unsupported requires sanitized reason; never guess a format. */
export interface NativeFormatView {
  status: NativeFormatStatus
  readerId?: string
  cliVersion?: string
  reason?: string
}

export interface NativeImageCapability {
  agentType: NativeAgentType
  imageInput: ImageInputCapability
}

export interface NativeImportPayload {
  nativeSessionId: string
  expectedIndexVersion: number
  sourceRevision: string
  confirmation: NativeClosureConfirmation
}

/** Normalized/filtered content only. A large message may span pages, with stable hash and ID. No reasoning, instruction prompts, raw tool arguments/results or attachments. */
export interface NativeMessagePart {
  messageId: string
  role: 'user' | 'assistant' | 'tool_summary'
  text: string
  createdAt?: string
  segmentIndex: number
  segmentCount: number
  totalUtf8Bytes: number
  contentSha256: string
}

/** Ephemeral page <=1MiB encoded UTF-8. Newest messages first, segments within a message ascending. Do not render an incomplete message. before continues exclusively after the last part in this order. */
export interface NativeMessagePage {
  nativeSessionId: string
  sourceRevision: string
  snapshotCursor: string
  items: NativeMessagePart[]
  hasMore: boolean
  before?: string
}

/** Exact Worker index ID; limit is message parts, default 50 at HTTP boundary. Snapshot cursor bound to file identity/immutable cut and 15-minute expiry. sourceRevision is optional: initial reads capture current source; before alone pins the older snapshot cut. If both are supplied they must match. Server must not substitute the latest index revision for a cursor-bound revision. */
export interface NativeReadInput {
  nativeSessionId: string
  sourceRevision?: string
  limit: number
  before?: string
}

/** Worker-local opaque index ID, not a path or fuzzy CLI ID. Exact vendor ID is kept in the local binding. Redact before title truncation. No body, tool arguments or process IDs in index. */
export interface NativeSessionIndex {
  nativeSessionId: string
  workspaceId: string
  agentType: NativeAgentType
  title: string
  createdAt: string
  updatedAt: string
  indexVersion: number
  sourceRevision: string
  format: NativeFormatView
  activity: NativeActivityEvidence
}

export interface NodeResolvedPayload {
  roleId: RoleId
  resolvedAgentId: string
  resolvedAgentName?: string
  resolveSource: ResolveSource
  isFallback: boolean
  fallbackReason?: string
  missingCapabilities?: CapabilityId[]
}

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

/** INTERNAL ONLY: raw tool arguments stay in the owned stdio channel, never public events/logs. Hash exact UTF-8 argumentsJson before parsing; reject duplicate JSON keys/non-object/oversize. Bound to a single live process and exact call. */
export interface PiGuardCheckInput {
  version: 1
  requestId: string
  sessionId: string
  nodeId: string
  toolCallId: string
  toolName: string
  policyRevision: string
  toolInventorySha256: string
  argumentsJson: string
  argumentsSha256: string
  expiresAt: string
}

/** INTERNAL ONLY. Block requires reason. Allow expires at the minimum of the check and approval deadlines and consumes the exact request once. Hub policy/approval decision, not model-generated consent. */
export interface PiGuardDecision {
  requestId: string
  sessionId: string
  toolCallId: string
  argumentsSha256: string
  policyRevision: string
  decision: 'allow' | 'block'
  reason?: PiGuardReason
  approvalId?: string
  expiresAt: string
}

/** Internal owned stdio only. Must complete before model prompt. Hub verifies launch isolation independently; extension self-report is not sufficient. */
export interface PiGuardHandshake {
  version: 1
  sessionId: string
  guardRevision: string
  policyRevision: string
  toolInventorySha256: string
  isolation: 'hub_extension_only'
  activeTools: string[]
}

export type PiImageTransport = string

/** The same scalar is used by role.modelId, LocalAgentModel.id, AgentTaskSpec.modelId, verification modelId and catalog bindings. No provider URL or authentication fields. */
export interface PiModelSelection {
  /** PI exact provider/modelId selector; split only the first slash. Model ID may contain additional slashes. Reject URLs, paths, empty/dot segments and inline credentials. Resolve only against local get_available_models. */
  modelId: string
}

export interface PickLocalDirectoryInput {
  initialPath?: string
}

export interface PickLocalDirectoryView {
  cancelled: boolean
  selectedPath?: string
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

/** Current authenticated account only. No ownerId/accountId selector is exposed. */
export interface RemoteAccountView {
  loginName: string
  displayName: string
}

export interface RemoteAnonymousSession {
  authenticated: false
}

export type RemoteApiTokenScope =
  | 'devices:read'
  | 'devices:manage'
  | 'devices:delete'

/** Cookie only. Trimmed name nonempty. Omitted expiry=90 days, max365 days from first issuance; duplicate scope values rejected. */
export interface RemoteApiTokenCreateInput {
  name: string
  /** No duplicates. Independent exact scopes, no implicit inclusion or wildcard. */
  scopes: RemoteApiTokenScope[]
  expiresAt?: string
}

/** Metadata only. Prefix is public selector, never any secret bytes. Revoked takes precedence over expired. */
export interface RemoteApiTokenView {
  tokenId: string
  name: string
  tokenPrefix: string
  /** No duplicates. Independent exact scopes, no implicit inclusion or wildcard. */
  scopes: RemoteApiTokenScope[]
  createdAt: string
  lastUsedAt?: string
  expiresAt: string
  status: 'active' | 'expired' | 'revoked'
  revokedAt?: string
}

/** 200 same intent replay; no secret recovery or second token issuance. If first response was lost, revoke then create using a new key. */
export interface RemoteApiTokenIssueReplayView {
  token: RemoteApiTokenView
  secretAvailable: false
}

/** 201 first issuance only; never store this full response in an idempotency cache. */
export interface RemoteApiTokenIssuedView {
  token: RemoteApiTokenView
  secretAvailable: true
  /** Only first issuance response; fresh 32-byte CSPRNG secret. This is an account API token, never a model credential or Worker device secret. */
  secret: string
}

/** Opaque owner/filter-scoped cursor; hasMore=true requires nextCursor. */
export interface RemoteApiTokenPage {
  items: RemoteApiTokenView[]
  hasMore: boolean
  nextCursor?: string
}

export interface RemoteApiTokenRevocationView {
  tokenId: string
  revokedAt: string
  status: 'revoked'
}

/** Worker looks up current pending approval/action/policy locally. Browser and server cannot supply a lower risk/action classification. */
export interface RemoteApprovalDecisionPayload {
  runId: string
  approvalId: string
  decision: ApprovalDecision
  reason?: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteApprovalDecisionCommand {
  type: 'approval.decide'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteApprovalDecisionPayload
}

/** Only current owner. approve on blocked action is forbidden in R1; reject does not grant execution permission. */
export interface RemoteApprovalDecisionInput {
  decision: ApprovalDecision
  reason?: string
}

/** D40: runId is LocalRun, the user-visible control handle. executionTaskId is the current per-run kernel Task; not a long-lived business Task. No Attempt identity. */
export interface RemoteResultRef {
  runId: string
  executionTaskId?: string
  nodeId?: string
  sessionId?: string
  /** Existing kernel Task.parentTaskId only. Never invented retryOfRunId or a long-lived Task identity. */
  parentExecutionTaskId?: string
}

export type RemoteWire1ErrorCode =
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
  | 'REMOTE_AUTH_REQUIRED'
  | 'REMOTE_CSRF_REJECTED'
  | 'REMOTE_DEVICE_OFFLINE'
  | 'REMOTE_DEVICE_REVOKED'
  | 'REMOTE_DEVICE_AUTH_FAILED'
  | 'REMOTE_PAIRING_EXPIRED'
  | 'REMOTE_PAIRING_CONFLICT'
  | 'REMOTE_PAIRING_INVALID'
  | 'REMOTE_COMMAND_EXPIRED'
  | 'REMOTE_COMMAND_WITHDRAWN'
  | 'REMOTE_WITHDRAWAL_UNCONFIRMED'
  | 'REMOTE_STORE_CHANGED'
  | 'REMOTE_EPOCH_STALE'
  | 'REMOTE_PROTOCOL_UNSUPPORTED'
  | 'REMOTE_EVENT_CONFLICT'
  | 'REMOTE_ACK_CONFLICT'
  | 'REMOTE_SEQUENCE_GAP'
  | 'REMOTE_APPROVAL_FORBIDDEN'
  | 'CONVERSATION_AUTHORITY_MISMATCH'
  | 'REMOTE_TARGET_MISMATCH'
  | 'REMOTE_SCENE_VERSION_MISMATCH'
  | 'REMOTE_CURSOR_EXPIRED'
  | 'REMOTE_CURSOR_INVALID'
  | 'REMOTE_RATE_LIMITED'
  | 'REMOTE_FRAME_TOO_LARGE'
  | 'REMOTE_WITHDRAWAL_TOO_LATE'
  | 'REMOTE_PAIRING_IN_PROGRESS'
  | 'REMOTE_SERVER_UNREACHABLE'
  | 'REMOTE_SERVER_ORIGIN_INVALID'

/** Local Worker policy is authoritative. Mandatory blocked actions are git_push/deploy/delete/db_migrate plus locally declared actions; refusal reason code REMOTE_APPROVAL_FORBIDDEN. Rejection of a dangerous action may still be submitted remotely. */
export interface RemoteWire1ApprovalView {
  approvalId: string
  resultRef: RemoteResultRef
  action: DangerousAction
  targetSummary: string
  riskLevel: RiskLevel
  status: ApprovalStatus
  requestedAt: string
  expiresAt: string
  remoteApprovalAllowed: boolean
  workerPolicyRevision: number
  denialCode?: RemoteWire1ErrorCode
}

export interface RemoteApprovalEvent {
  type: 'approval.state_changed'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  conversationId: string
  payload: RemoteWire1ApprovalView
}

/** Local Worker policy is authoritative. Mandatory blocked actions are git_push/deploy/delete/db_migrate plus locally declared actions; refusal reason code REMOTE_APPROVAL_FORBIDDEN. Rejection of a dangerous action may still be submitted remotely. */
export interface RemoteApprovalView {
  approvalId: string
  resultRef: RemoteResultRef
  action: DangerousAction
  targetSummary: string
  riskLevel: RiskLevel
  status: ApprovalStatus
  requestedAt: string
  expiresAt: string
  remoteApprovalAllowed: boolean
  workerPolicyRevision: number
  denialCode?: ErrorCode
}

/** Owner-scoped logical quota: count each live attachment once, independent of physical deduplication; inflight reservations also consume quota. */
export interface RemoteAttachmentLimitsView {
  limits: AttachmentLimits
  usedBytes: number
  reservedBytes: number
  observedAt: string
}

/** Deleted/expired records are not exposed: NOT_FOUND. uploaded expires after 24h, reserved has bounded command pin, attached belongs to Worker-confirmed message. Attached metadata may precede local-origin bytes. */
export interface RemoteAttachmentView {
  attachment: MessageAttachmentView
  conversationId: string
  state: 'uploaded' | 'reserved' | 'attached'
  createdAt: string
  expiresAt?: string
}

export interface RemoteAuthenticatedSession {
  authenticated: true
  account: RemoteAccountView
  expiresAt: string
  /** Session-bound CSRF value, not authentication. Browser authentication remains an HttpOnly Secure cookie. */
  csrfToken: string
}

/** Opaque local grant identity. Full absolute root path is never exported. */
export interface RemoteAuthorizedRoot {
  rootId: string
  displayName: string
  version: number
}

/** Sanitized error. No credential, raw environment, owner locator or arbitrary detail object. */
export interface RemoteError {
  code: ErrorCode
  message: string
  retryable: boolean
}

/** workspace.register requires workspaceId only; native.import requires workspaceId/conversationId/nativeSessionId. IDs local on wire, owner-scoped in HTTP. No fake Task or Run. */
export interface RemoteResourceResultRef {
  workspaceId?: string
  conversationId?: string
  nativeSessionId?: string
}

/** D41: Worker-only structured evidence, never parsed error text. Empty orphanProcessIds is not proof of no remaining process. A paused process may still exist. */
export interface RemoteControlRejected {
  outcome: 'rejected'
  /** Must be true for adapter_refused without positive stop evidence. Policy rejection before execution may be false; never infer from terminal label or empty orphan list alone. */
  executionMayStillBeRunning: boolean
  orphanProcessIds: number[]
  reason: string
  evidence: 'adapter_refused' | 'worker_policy' | 'already_terminal'
  observedAt: string
}

/** D41: Worker-only structured evidence, never parsed error text. Empty orphanProcessIds is not proof of no remaining process. A paused process may still exist. */
export interface RemoteControlUnconfirmed {
  outcome: 'unconfirmed'
  executionMayStillBeRunning: true
  orphanProcessIds: number[]
  reason: string
  evidence: 'missing_execution_handle' | 'delivery_unknown' | 'recovery_flag' | 'supervisor_unconfirmed'
  observedAt: string
}

/** D41: Worker-only structured evidence, never parsed error text. Empty orphanProcessIds is not proof of no remaining process. A paused process may still exist. input_preparation_cancelled requires durable no-Agent-start fence and confirmed stopped preparation I/O, never inferred from a missing process handle. */
export interface RemoteV4ControlConfirmed {
  outcome: 'confirmed'
  executionMayStillBeRunning: boolean
  orphanProcessIds: number[]
  reason: string
  evidence: 'adapter_confirmed' | 'node_boundary_paused' | 'already_terminal' | 'retry_enqueued' | 'supervisor_resumed' | 'inbox_tombstone' | 'metadata_committed' | 'input_preparation_cancelled'
  observedAt: string
}

export type RemoteV4ControlResult = RemoteV4ControlConfirmed | RemoteControlRejected | RemoteControlUnconfirmed

/** Three layers must be displayed separately: transport/delivery, Worker controlResult, execution status from RemoteRunView. No inference from disconnected transport or command.completed to task success. Resource commands omit conversationId; resourceRef appears after Worker commit and contains mapped public IDs. Read through existing GET commands; no fabricated run/sequence. */
export interface RemoteCommandView {
  commandId: string
  conversationId?: string
  targetWorkerId: string
  type: 'run.submit' | 'run.pause' | 'run.resume' | 'run.cancel' | 'run.retry' | 'approval.decide' | 'command.withdraw' | 'conversation.update' | 'conversation.create' | 'native.import' | 'workspace.register'
  conversationSeq?: number
  status: 'queued' | 'accepted' | 'rejected' | 'completed' | 'failed'
  deliveryState: 'queued_online' | 'queued_offline' | 'sent' | 'acknowledged' | 'reconciliation_required' | 'awaiting_receipt' | 'granted'
  withdrawalState: 'none' | 'requested' | 'confirmed' | 'denied'
  workerOnline: boolean
  observedAt: string
  createdAt: string
  expiresAt: string
  resultStatus?: 'succeeded' | 'cancelled' | 'confirmed' | 'retry_enqueued' | 'approval_consumed' | 'withdrawn' | 'failed' | 'rejected'
  resultRef?: RemoteResultRef
  controlResult?: RemoteV4ControlResult
  error?: RemoteError
  withdrawalCommandId?: string
  deliverBy?: string
  resourceRef?: RemoteResourceResultRef
}

/** Owner-scoped browser event; ordering/resume is only by opaque serverCursor, never by payload Worker seq. */
export interface RemoteBrowserCommandEvent {
  type: 'command.updated'
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  serverCursor: string
  recordedAt: string
  payload: RemoteCommandView
}

export interface RemoteBrowserConversationDeleted {
  type: 'conversation.deleted'
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  serverCursor: string
  recordedAt: string
  conversationId: string
}

/** Worker is the sole writer. authority is legacy metadata, never a write gate. Omitted visibility=both, busy=false, busyFresh=false; targetWorkerId is the legacy workerId alias. Missing conversationKind means scenario (requires existing scene fields). Native requires agentType/nativeSessionId and omits scene fields; exact vendor session binding remains local. */
export interface RemoteConversationView {
  conversationId: string
  targetWorkerId: string
  authority: 'local' | 'remote'
  title: string
  workspaceId: string
  sceneId?: string
  sceneVersion?: number
  createdAt: string
  updatedAt: string
  workerStoreId: string
  workerId?: string
  visibility?: 'both' | 'pc_only' | 'mobile_only'
  busy?: boolean
  busyObservedAt?: string
  busyFresh?: boolean
  lastActivityAt?: string
  archived?: boolean
  metadataVersion?: number
  conversationKind?: 'scenario' | 'native'
  agentType?: RuntimeNativeAgentType
  nativeSessionId?: string
  nativeActivity?: NativeActivityEvidence
  nativeSourceRevision?: string
}

/** Owner-scoped browser event; ordering/resume is only by opaque serverCursor, never by payload Worker seq. */
export interface RemoteBrowserConversationEvent {
  type: 'conversation.updated'
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  serverCursor: string
  recordedAt: string
  payload: RemoteConversationView
}

export interface RemoteMessageView {
  messageId: string
  conversationId: string
  role: 'user' | 'assistant' | 'system'
  /** Complete assembled content, never truncated. Resource quota failures are explicit; no partial message is published. */
  text: string
  createdAt: string
  commandId?: string
  runId?: string
  messageSequence?: number
  messageRevision?: number
  attachments?: MessageAttachmentView[]
}

/** Owner-scoped browser event; ordering/resume is only by opaque serverCursor, never by payload Worker seq. */
export interface RemoteBrowserMessageEvent {
  type: 'message.appended'
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  serverCursor: string
  recordedAt: string
  payload: RemoteMessageView
}

/** Frozen revision 4 error domain. New registry codes never silently broaden older codecs. Missing/deleted/expired attachment uses existing NOT_FOUND after authorization. */
export type RemoteWire5ErrorCode =
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
  | 'REMOTE_AUTH_REQUIRED'
  | 'REMOTE_CSRF_REJECTED'
  | 'REMOTE_DEVICE_OFFLINE'
  | 'REMOTE_DEVICE_REVOKED'
  | 'REMOTE_DEVICE_AUTH_FAILED'
  | 'REMOTE_PAIRING_EXPIRED'
  | 'REMOTE_PAIRING_CONFLICT'
  | 'REMOTE_PAIRING_INVALID'
  | 'REMOTE_COMMAND_EXPIRED'
  | 'REMOTE_COMMAND_WITHDRAWN'
  | 'REMOTE_WITHDRAWAL_UNCONFIRMED'
  | 'REMOTE_STORE_CHANGED'
  | 'REMOTE_EPOCH_STALE'
  | 'REMOTE_PROTOCOL_UNSUPPORTED'
  | 'REMOTE_EVENT_CONFLICT'
  | 'REMOTE_ACK_CONFLICT'
  | 'REMOTE_SEQUENCE_GAP'
  | 'REMOTE_APPROVAL_FORBIDDEN'
  | 'CONVERSATION_AUTHORITY_MISMATCH'
  | 'REMOTE_TARGET_MISMATCH'
  | 'REMOTE_SCENE_VERSION_MISMATCH'
  | 'REMOTE_CURSOR_EXPIRED'
  | 'REMOTE_CURSOR_INVALID'
  | 'REMOTE_RATE_LIMITED'
  | 'REMOTE_FRAME_TOO_LARGE'
  | 'REMOTE_WITHDRAWAL_TOO_LATE'
  | 'REMOTE_PAIRING_IN_PROGRESS'
  | 'REMOTE_SERVER_UNREACHABLE'
  | 'REMOTE_SERVER_ORIGIN_INVALID'
  | 'REMOTE_CONVERSATION_BUSY'
  | 'REMOTE_STATE_NOT_READY'
  | 'REMOTE_SYNC_CONFLICT'
  | 'REMOTE_SYNC_DISABLED'
  | 'REMOTE_DELIVERY_EXPIRED'
  | 'REMOTE_REVISION_REQUIRED'
  | 'REMOTE_SYNC_RESOURCE_LIMIT'
  | 'REMOTE_QUERY_TIMEOUT'
  | 'REMOTE_QUERY_TOO_LARGE'
  | 'NATIVE_SESSION_ACTIVE'
  | 'NATIVE_SESSION_UNSUPPORTED'
  | 'NATIVE_SESSION_CHANGED'
  | 'NATIVE_SESSION_WRITER_CONFLICT'
  | 'REMOTE_ROOT_NOT_AUTHORIZED'
  | 'REMOTE_PATH_OUTSIDE_ROOT'
  | 'REMOTE_DIRECTORY_CHANGED'
  | 'ATTACHMENT_TOO_LARGE'
  | 'ATTACHMENT_TYPE_UNSUPPORTED'
  | 'ATTACHMENT_COUNT_EXCEEDED'
  | 'ATTACHMENT_QUOTA_EXCEEDED'
  | 'ATTACHMENT_HASH_MISMATCH'
  | 'AGENT_IMAGE_UNSUPPORTED'
  | 'ATTACHMENT_DOWNLOAD_FAILED'
  | 'ATTACHMENT_NOT_READY'
  | 'ATTACHMENT_IN_USE'
  | 'ATTACHMENT_THUMBNAIL_UNAVAILABLE'
  | 'ATTACHMENT_PREPARATION_INTERRUPTED'
  | 'PI_GUARD_UNAVAILABLE'
  | 'PI_UNCONTROLLED_EXTENSIONS'
  | 'PI_TOOL_CALL_BLOCKED'

/** Local Worker policy is authoritative. Mandatory blocked actions are git_push/deploy/delete/db_migrate plus locally declared actions; refusal reason code REMOTE_APPROVAL_FORBIDDEN. Rejection of a dangerous action may still be submitted remotely. */
export interface RemoteWire5ApprovalView {
  approvalId: string
  resultRef: RemoteResultRef
  action: DangerousAction
  targetSummary: string
  riskLevel: RiskLevel
  status: ApprovalStatus
  requestedAt: string
  expiresAt: string
  remoteApprovalAllowed: boolean
  workerPolicyRevision: number
  denialCode?: RemoteWire5ErrorCode
}

export interface RemoteV5ApprovalEvent {
  type: 'approval.state_changed'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  conversationId: string
  payload: RemoteWire5ApprovalView
}

/** Browser-only PI approval projection. Emit only after owner/visibility and pi-v1 capability checks. Public IDs, sanitized summary; source wireRevision=5. Do not relay arbitrary revision 5 frames through this variant. */
export interface RemoteBrowserPiApprovalEvent {
  type: 'worker.event'
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  serverCursor: string
  recordedAt: string
  payload: RemoteV5ApprovalEvent
}

export interface RemoteBrowserStoreReset {
  type: 'store.reset'
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  serverCursor: string
  recordedAt: string
  workerId: string
  workerStoreId: string
}

export type RemoteWire2ErrorCode =
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
  | 'REMOTE_AUTH_REQUIRED'
  | 'REMOTE_CSRF_REJECTED'
  | 'REMOTE_DEVICE_OFFLINE'
  | 'REMOTE_DEVICE_REVOKED'
  | 'REMOTE_DEVICE_AUTH_FAILED'
  | 'REMOTE_PAIRING_EXPIRED'
  | 'REMOTE_PAIRING_CONFLICT'
  | 'REMOTE_PAIRING_INVALID'
  | 'REMOTE_COMMAND_EXPIRED'
  | 'REMOTE_COMMAND_WITHDRAWN'
  | 'REMOTE_WITHDRAWAL_UNCONFIRMED'
  | 'REMOTE_STORE_CHANGED'
  | 'REMOTE_EPOCH_STALE'
  | 'REMOTE_PROTOCOL_UNSUPPORTED'
  | 'REMOTE_EVENT_CONFLICT'
  | 'REMOTE_ACK_CONFLICT'
  | 'REMOTE_SEQUENCE_GAP'
  | 'REMOTE_APPROVAL_FORBIDDEN'
  | 'CONVERSATION_AUTHORITY_MISMATCH'
  | 'REMOTE_TARGET_MISMATCH'
  | 'REMOTE_SCENE_VERSION_MISMATCH'
  | 'REMOTE_CURSOR_EXPIRED'
  | 'REMOTE_CURSOR_INVALID'
  | 'REMOTE_RATE_LIMITED'
  | 'REMOTE_FRAME_TOO_LARGE'
  | 'REMOTE_WITHDRAWAL_TOO_LATE'
  | 'REMOTE_PAIRING_IN_PROGRESS'
  | 'REMOTE_SERVER_UNREACHABLE'
  | 'REMOTE_SERVER_ORIGIN_INVALID'
  | 'REMOTE_CONVERSATION_BUSY'
  | 'REMOTE_STATE_NOT_READY'
  | 'REMOTE_SYNC_CONFLICT'
  | 'REMOTE_SYNC_DISABLED'
  | 'REMOTE_DELIVERY_EXPIRED'
  | 'REMOTE_REVISION_REQUIRED'
  | 'REMOTE_SYNC_RESOURCE_LIMIT'

/** Local Worker policy is authoritative. Mandatory blocked actions are git_push/deploy/delete/db_migrate plus locally declared actions; refusal reason code REMOTE_APPROVAL_FORBIDDEN. Rejection of a dangerous action may still be submitted remotely. */
export interface RemoteWire2ApprovalView {
  approvalId: string
  resultRef: RemoteResultRef
  action: DangerousAction
  targetSummary: string
  riskLevel: RiskLevel
  status: ApprovalStatus
  requestedAt: string
  expiresAt: string
  remoteApprovalAllowed: boolean
  workerPolicyRevision: number
  denialCode?: RemoteWire2ErrorCode
}

export interface RemoteV2ApprovalEvent {
  type: 'approval.state_changed'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  conversationId: string
  payload: RemoteWire2ApprovalView
}

/** Worker scene index only; model/provider credential or installation/subscription data is not relayed. */
export interface RemoteSceneSummary {
  sceneId: string
  name: string
  version: number
  readOnly: boolean
}

/** Worker-exported registered workspace index. displayPath is display-only; no server filesystem path resolution or remote arbitrary folder execution. */
export interface RemoteWorkspaceSummary {
  workspaceId: string
  name: string
  displayPath: string
  vcs: Vcs
  canWrite: boolean
}

/** Atomic bounded complete catalog for R1. Reject oversized catalogs instead of truncating; offline entries are last observed, not proof that paths still exist. */
export interface RemoteCatalogView {
  workerId: string
  capabilityRevision: number
  observedAt: string
  workspaces: RemoteWorkspaceSummary[]
  scenes: RemoteSceneSummary[]
  remotelyBlockedActions: DangerousAction[]
  workerStoreId: string
}

export interface RemoteV2CatalogEvent {
  type: 'capability.changed'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  payload: RemoteCatalogView
}

/** Durable inbox admission, not model/execution success. Duplicate immutable commands return the original receipt/event. */
export interface RemoteV2CommandAccepted {
  type: 'command.accepted'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  receivedAt: string
  status: 'accepted'
  resultRef?: RemoteResultRef
}

/** D41: Worker-only structured evidence, never parsed error text. Empty orphanProcessIds is not proof of no remaining process. A paused process may still exist. */
export interface RemoteV2ControlConfirmed {
  outcome: 'confirmed'
  executionMayStillBeRunning: boolean
  orphanProcessIds: number[]
  reason: string
  evidence: 'adapter_confirmed' | 'node_boundary_paused' | 'already_terminal' | 'retry_enqueued' | 'supervisor_resumed' | 'inbox_tombstone' | 'metadata_committed'
  observedAt: string
}

/** Not universally task success. Retry completes on durable new execution reference; execute completes on actual terminal Run success/cancellation. Cancel/pause/resume require confirmed structured control result. */
export interface RemoteV2CommandCompleted {
  type: 'command.completed'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  resultStatus: 'succeeded' | 'cancelled' | 'confirmed' | 'retry_enqueued' | 'approval_consumed' | 'withdrawn'
  resultRef?: RemoteResultRef
  controlResult?: RemoteV2ControlConfirmed
}

/** Sanitized error. No credential, raw environment, owner locator or arbitrary detail object. */
export interface RemoteWire2Error {
  code: RemoteWire2ErrorCode
  message: string
  retryable: boolean
}

/** Failure after admission. A refused control is distinct from unconfirmed cancellation; do not infer that an Agent process has stopped. */
export interface RemoteV2CommandFailed {
  type: 'command.failed'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  resultStatus: 'failed' | 'rejected'
  error: RemoteWire2Error
  resultRef?: RemoteResultRef
  controlResult?: RemoteControlRejected
}

/** Pre-admission rejection only. An expired sequenced submit consumes its ordered slot without execution. */
export interface RemoteV2CommandRejected {
  type: 'command.rejected'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  receivedAt: string
  status: 'rejected'
  error: RemoteWire2Error
}

export type RemoteV2ControlResult = RemoteV2ControlConfirmed | RemoteControlRejected | RemoteControlUnconfirmed

/** D41: unconfirmed leaves command accepted and pending reconciliation. Run-scoped controls include resultRef/executionStatus. Before a Run exists (withdrawal reconciliation), omit both rather than invent an identity or execution state. */
export interface RemoteV2ControlObserved {
  type: 'command.control_result'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  resultRef?: RemoteResultRef
  controlResult: RemoteV2ControlResult
  executionStatus?: TaskStatus
}

/** Worker may emit assistant/system messages, never impersonate a user or allocate conversationSeq. */
export interface RemoteWorkerMessagePayload {
  messageId: string
  conversationId: string
  role: 'assistant' | 'system'
  text: string
  createdAt: string
  commandId?: string
  runId?: string
}

export interface RemoteV2MessageEvent {
  type: 'message.appended'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  conversationId: string
  payload: RemoteWorkerMessagePayload
}

/** Sanitized observable progress only. Never private model reasoning, raw provider auth, full environment, or credential files. */
export interface RemoteV2ProgressEvent {
  type: 'run.progress'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  conversationId: string
  resultRef: RemoteResultRef
  message: string
}

/** Worker execution facts only. Server derives workerOnline for browser RemoteRunView; Worker cannot declare server transport liveness. */
export interface RemoteRunStatePayload {
  runId: string
  conversationId: string
  executionTaskId?: string
  status: TaskStatus
  observedAt: string
  summary?: string
  /** Existing kernel Task.parentTaskId only. Never invented retryOfRunId or a long-lived Task identity. */
  parentExecutionTaskId?: string
}

/** Worker creates/binds LocalRun and execution Task using existing semantics; it does not invent long-lived Task or retryOfRunId. */
export interface RemoteV2RunStateEvent {
  type: 'run.state_changed'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  payload: RemoteRunStatePayload
}

/** Worker records ordered skip in the same durable inbox ordering ledger as submits. */
export interface RemoteV2SkipRecorded {
  type: 'conversation.skip_recorded'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  conversationSeq: number
}

export type RemoteV2ExecutionEvent = RemoteV2CommandAccepted | RemoteV2CommandRejected | RemoteV2CommandCompleted | RemoteV2CommandFailed | RemoteV2ControlObserved | RemoteV2RunStateEvent | RemoteV2MessageEvent | RemoteV2ApprovalEvent | RemoteV2ProgressEvent | RemoteV2CatalogEvent | RemoteV2SkipRecorded

/** Owner-scoped browser event; ordering/resume is only by opaque serverCursor, never by payload Worker seq. */
export interface RemoteBrowserV2WorkerEvent {
  type: 'worker.event'
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  serverCursor: string
  recordedAt: string
  payload: RemoteV2ExecutionEvent
}

export interface RemoteCatalogEvent {
  type: 'capability.changed'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  payload: RemoteCatalogView
}

/** Durable inbox admission, not model/execution success. Duplicate immutable commands return the original receipt/event. */
export interface RemoteCommandAccepted {
  type: 'command.accepted'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  receivedAt: string
  status: 'accepted'
  resultRef?: RemoteResultRef
}

/** D41: Worker-only structured evidence, never parsed error text. Empty orphanProcessIds is not proof of no remaining process. A paused process may still exist. */
export interface RemoteControlConfirmed {
  outcome: 'confirmed'
  executionMayStillBeRunning: boolean
  orphanProcessIds: number[]
  reason: string
  evidence: 'adapter_confirmed' | 'node_boundary_paused' | 'already_terminal' | 'retry_enqueued' | 'supervisor_resumed' | 'inbox_tombstone'
  observedAt: string
}

/** Not universally task success. Retry completes on durable new execution reference; execute completes on actual terminal Run success/cancellation. Cancel/pause/resume require confirmed structured control result. */
export interface RemoteCommandCompleted {
  type: 'command.completed'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  resultStatus: 'succeeded' | 'cancelled' | 'confirmed' | 'retry_enqueued' | 'approval_consumed' | 'withdrawn'
  resultRef?: RemoteResultRef
  controlResult?: RemoteControlConfirmed
}

/** Sanitized error. No credential, raw environment, owner locator or arbitrary detail object. */
export interface RemoteWire1Error {
  code: RemoteWire1ErrorCode
  message: string
  retryable: boolean
}

/** Failure after admission. A refused control is distinct from unconfirmed cancellation; do not infer that an Agent process has stopped. */
export interface RemoteCommandFailed {
  type: 'command.failed'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  resultStatus: 'failed' | 'rejected'
  error: RemoteWire1Error
  resultRef?: RemoteResultRef
  controlResult?: RemoteControlRejected
}

/** Pre-admission rejection only. An expired sequenced submit consumes its ordered slot without execution. */
export interface RemoteCommandRejected {
  type: 'command.rejected'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  receivedAt: string
  status: 'rejected'
  error: RemoteWire1Error
}

export type RemoteControlResult = RemoteControlConfirmed | RemoteControlRejected | RemoteControlUnconfirmed

/** D41: unconfirmed leaves command accepted and pending reconciliation. Run-scoped controls include resultRef/executionStatus. Before a Run exists (withdrawal reconciliation), omit both rather than invent an identity or execution state. */
export interface RemoteControlObserved {
  type: 'command.control_result'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  resultRef?: RemoteResultRef
  controlResult: RemoteControlResult
  executionStatus?: TaskStatus
}

export interface RemoteMessageEvent {
  type: 'message.appended'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  conversationId: string
  payload: RemoteWorkerMessagePayload
}

/** Sanitized observable progress only. Never private model reasoning, raw provider auth, full environment, or credential files. */
export interface RemoteProgressEvent {
  type: 'run.progress'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  conversationId: string
  resultRef: RemoteResultRef
  message: string
}

/** Worker creates/binds LocalRun and execution Task using existing semantics; it does not invent long-lived Task or retryOfRunId. */
export interface RemoteRunStateEvent {
  type: 'run.state_changed'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  payload: RemoteRunStatePayload
}

/** Worker records ordered skip in the same durable inbox ordering ledger as submits. */
export interface RemoteSkipRecorded {
  type: 'conversation.skip_recorded'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  conversationSeq: number
}

export type RemoteVisibleWorkerEvent = RemoteCommandAccepted | RemoteCommandRejected | RemoteCommandCompleted | RemoteCommandFailed | RemoteControlObserved | RemoteRunStateEvent | RemoteMessageEvent | RemoteApprovalEvent | RemoteProgressEvent | RemoteCatalogEvent | RemoteSkipRecorded

/** Owner-scoped browser event; ordering/resume is only by opaque serverCursor, never by payload Worker seq. */
export interface RemoteBrowserWorkerEvent {
  type: 'worker.event'
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  serverCursor: string
  recordedAt: string
  payload: RemoteVisibleWorkerEvent
}

export type RemoteBrowserEvent = RemoteBrowserWorkerEvent | RemoteBrowserCommandEvent | RemoteBrowserConversationEvent | RemoteBrowserMessageEvent | RemoteBrowserV2WorkerEvent | RemoteBrowserConversationDeleted | RemoteBrowserStoreReset | RemoteBrowserPiApprovalEvent

/** GET after opaque serverCursor. Unknown/expired cursor requires snapshot; never silently reset to zero. */
export interface RemoteBrowserEventPage {
  items: RemoteBrowserEvent[]
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  nextServerCursor: string
  hasMore: boolean
}

/** Browser-only compatibility projection, not a Worker transport frame. Source revision 5 stays unchanged in Inbox. Nested wireRevision=2 labels the legacy browser shape only; never feed it to Worker/ACK/grant or infer source revision from it. Authorized non-PI approval IDs are mapped to public IDs before projection. */
export interface RemoteBrowserLegacyApprovalEvent {
  type: 'worker.event'
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  serverCursor: string
  recordedAt: string
  payload: RemoteV2ApprovalEvent
}

export type RemoteBrowserSessionView = RemoteAuthenticatedSession | RemoteAnonymousSession

/** All controls address LocalRun. Optional nodeId is valid only for retry of an existing node within this run. */
export interface RemoteRunControlPayload {
  runId: string
  nodeId?: string
  reason?: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteCancelCommand {
  type: 'run.cancel'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
}

/** Targets an in-flight submit command whose delivery/acceptance is uncertain. Worker persists a tombstone or stops its bound run; server must not claim success first. */
export interface RemoteCommandWithdrawalPayload {
  targetCommandId: string
  reason?: string
  /** Existing target submit sequence, not a new control sequence. Required to persist an ordered tombstone when withdrawal arrives before the original submit. */
  targetConversationSeq: number
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteCommandWithdrawalCommand {
  type: 'command.withdraw'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteCommandWithdrawalPayload
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemotePauseCommand {
  type: 'run.pause'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteResumeCommand {
  type: 'run.resume'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteRetryCommand {
  type: 'run.retry'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
}

/** References registered Worker workspace and scene revision. No model account/config credentials, arbitrary executable, attachment or server filesystem path. An append message is another run.submit, not mutation of a running turn. */
export interface RemoteRunSubmitPayload {
  clientMessageId: string
  workspaceId: string
  sceneId: string
  sceneVersion: number
  sessionMode: 'new' | 'continue'
  text: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteRunSubmitCommand {
  type: 'run.submit'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  commandId: string
  conversationId: string
  conversationSeq: number
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunSubmitPayload
}

export type RemoteCommandEnvelope = RemoteRunSubmitCommand | RemotePauseCommand | RemoteResumeCommand | RemoteCancelCommand | RemoteRetryCommand | RemoteApprovalDecisionCommand | RemoteCommandWithdrawalCommand

/** Bounded owner/resource-scoped page. hasMore=true requires nextCursor; cursor is not a Worker seq. */
export interface RemoteCommandPage {
  items: RemoteCommandView[]
  hasMore: boolean
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  nextCursor?: string
}

export type RemoteCommandReceipt = RemoteCommandAccepted | RemoteCommandRejected

export interface RemoteCommandWithdrawalInput {
  reason?: string
}

/** Worker requests missing commands or skip records. Never run a later user message across a sequence gap. */
export interface RemoteConversationGap {
  type: 'conversation.gap'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  workerId: string
  workerStoreId: string
  workerEpoch: string
  conversationId: string
  expectedSeq: number
  receivedSeq: number
}

/** Bounded owner/resource-scoped page. hasMore=true requires nextCursor; cursor is not a Worker seq. */
export interface RemoteConversationPage {
  items: RemoteConversationView[]
  hasMore: boolean
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  nextCursor?: string
}

/** Durable ordered tombstone for a never-dispatched submit. Not an execution/control command; cannot be used to erase accepted work. Retain until gap replay/snapshot acknowledgement is safe. */
export interface RemoteConversationSkip {
  type: 'conversation.skip'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  commandId: string
  conversationId: string
  conversationSeq: number
  targetWorkerId: string
  expectedWorkerStoreId: string
  reason: 'withdrawn_before_dispatch' | 'expired_before_dispatch'
  recordedAt: string
}

/** Worker-owned execution projection. Offline does not change status. D40 maps LocalRun.taskId to executionTaskId only at remote boundary; existing LocalRunView is unchanged. */
export interface RemoteRunView {
  runId: string
  conversationId: string
  executionTaskId?: string
  status: TaskStatus
  observedAt: string
  workerOnline: boolean
  summary?: string
  /** Existing kernel Task.parentTaskId only. Never invented retryOfRunId or a long-lived Task identity. */
  parentExecutionTaskId?: string
}

/** Consistent selected-conversation projection and cursor transaction. For larger history, fetch bounded resource pages while replaying events after this cursor. No whole-history batch or credential content. */
export interface RemoteConversationSnapshot {
  conversation: RemoteConversationView
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  serverCursor: string
  observedAt: string
  runs: RemoteRunView[]
  commands: RemoteCommandView[]
  messages: RemoteMessageView[]
  hasMore: boolean
  /** Pending, unexpired approvals for this conversation; omitted means []. Truncation sets hasMore. */
  approvals?: RemoteApprovalView[]
}

/** Owner/device/workspace/scene references for a Worker-owned creation command. Requires online revision 2; 202 is a transport receipt, not a server-created conversation. */
export interface RemoteCreateConversationInput {
  targetWorkerId: string
  title: string
  workspaceId: string
  sceneId: string
  sceneVersion: number
  workerStoreId: string
}

/** Deletes server resource/copies and revokes credentials, never claims local execution stopped. */
export interface RemoteDeviceDeletionView {
  workerId: string
  deletedAt: string
  executionMayStillBeRunning: true
}

export interface RemoteDeviceView {
  workerId: string
  deviceName: string
  platform: 'windows' | 'linux' | 'darwin'
  architecture: 'x86_64' | 'aarch64'
  status: 'online' | 'offline' | 'revoked' | 'reconciliation_required'
  workerStoreId: string
  capabilityRevision: number
  observedAt: string
  lastSeenAt?: string
  pairedAt: string
  revokedAt?: string
  online?: boolean
  busySnapshotFresh?: boolean
  supportedWireRevisions?: number[]
  /** Optional legacy compatibility: omitted means enabled. Independent from status/online. */
  remoteAccess?: 'enabled' | 'suspended'
  /** Optional server-only alias; absent means use unchanged Worker deviceName. */
  displayName?: string
  /** Management CAS version, legacy=1. Changes only for management/lifecycle mutations, not heartbeats or snapshots. */
  version?: number
  /** Present only while suspended; resume clears this field. */
  suspendedAt?: string
}

export interface RemoteDevicePage {
  items: RemoteDeviceView[]
  hasMore: boolean
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  nextCursor?: string
}

/** At least one change required. Empty/whitespace displayName clears the server alias; null invalid. Does not rename the Worker. */
export interface RemoteDevicePatchInput {
  expectedVersion: number
  remoteAccess?: 'enabled' | 'suspended'
  displayName?: string
}

/** Revokes transport rights, does not claim execution was cancelled or stopped. */
export interface RemoteDeviceRevocationView {
  workerId: string
  revokedAt: string
  status: 'revoked'
  executionMayStillBeRunning: true
}

export interface RemoteDeviceRevokeInput {
  reason?: string
}

/** Highest durably committed contiguous event seq for this Worker store, never the largest observed seq. */
export interface RemoteEventPosition {
  workerStoreId: string
  seq: number
}

/** Only advances after event persistence AND projection/browser-outbox commit; old store ack never trims new store outbox. */
export interface RemoteEventAck {
  type: 'worker.events_ack'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  connectionId: string
  workerId: string
  position: RemoteEventPosition
}

/** Safe HTTP-only hints. fields contains schema/header names, not input values; currentVersion only after owner/resource authorization. No raw exception, credential, owner locator or request body. */
export interface RemoteHttpErrorDetail {
  fields?: string[]
  currentVersion?: number
  retryAfterSeconds?: number
}

/** HTTP-only error shape inside ApiEnvelope.error; detail does not extend any Worker error DTO. */
export interface RemoteHttpError {
  code: ErrorCode
  message: string
  retryable: boolean
  detail?: RemoteHttpErrorDetail
}

/** Local binding view; connectionStatus is transport only. Frozen blocks command delivery pending reconciliation, even when WSS is online. */
export interface RemoteLinkFrozenView {
  state: 'frozen'
  /** HTTPS origin only; HTTP 127.0.0.1/localhost requires Worker development mode. No userinfo/path/query/fragment. P2 must URL-parse/validate host and normalize scheme/host/default port/trailing root slash; this pattern does not replace URL parsing. */
  serverOrigin: string
  workerId: string
  deviceName: string
  connectionStatus: 'online' | 'connecting' | 'offline'
  /** Last confirmed successful WSS connection; null means never connected. Do not invent a timestamp at pairing. */
  lastConnectedAt: Timestamp | null
  lastErrorCode?: ErrorCode
}

/** Local binding view; connectionStatus is transport only. Paired does not imply WSS connected or execution succeeded. */
export interface RemoteLinkPairedView {
  state: 'paired'
  /** HTTPS origin only; HTTP 127.0.0.1/localhost requires Worker development mode. No userinfo/path/query/fragment. P2 must URL-parse/validate host and normalize scheme/host/default port/trailing root slash; this pattern does not replace URL parsing. */
  serverOrigin: string
  workerId: string
  deviceName: string
  connectionStatus: 'online' | 'connecting' | 'offline'
  /** Last confirmed successful WSS connection; null means never connected. Do not invent a timestamp at pairing. */
  lastConnectedAt: Timestamp | null
  lastErrorCode?: ErrorCode
}

/** Local authenticated pairing request. Worker creates/stores the device credential internally; client cannot supply or retrieve it. Changing server while already paired requires explicit unlink. */
export interface RemoteLinkPairingInput {
  /** HTTPS origin only; HTTP 127.0.0.1/localhost requires Worker development mode. No userinfo/path/query/fragment. P2 must URL-parse/validate host and normalize scheme/host/default port/trailing root slash; this pattern does not replace URL parsing. */
  serverOrigin: string
  deviceName: string
}

/** A server challenge has been obtained. Short code only, never device secret. Expiry/cancel clears candidate credentials and returns unpaired. */
export interface RemoteLinkPairingView {
  state: 'pairing'
  /** HTTPS origin only; HTTP 127.0.0.1/localhost requires Worker development mode. No userinfo/path/query/fragment. P2 must URL-parse/validate host and normalize scheme/host/default port/trailing root slash; this pattern does not replace URL parsing. */
  serverOrigin: string
  deviceName: string
  pairRequestId: string
  pairCode: string
  expiresAt: Timestamp
}

/** Local binding view; connectionStatus is transport only. Revocation fences reconnect; it does not stop or rewrite execution state. */
export interface RemoteLinkRevokedView {
  state: 'revoked'
  /** HTTPS origin only; HTTP 127.0.0.1/localhost requires Worker development mode. No userinfo/path/query/fragment. P2 must URL-parse/validate host and normalize scheme/host/default port/trailing root slash; this pattern does not replace URL parsing. */
  serverOrigin: string
  workerId: string
  deviceName: string
  connectionStatus: 'offline'
  /** Last confirmed successful WSS connection; null means never connected. Do not invent a timestamp at pairing. */
  lastConnectedAt: Timestamp | null
  lastErrorCode?: ErrorCode
}

/** Local binding absent. Optional origin may remain as non-secret preference; lastErrorCode may report unconfirmed best-effort server revocation. Existing remote conversations remain remote and locally read-only. */
export interface RemoteLinkUnpairedView {
  state: 'unpaired'
  /** HTTPS origin only; HTTP 127.0.0.1/localhost requires Worker development mode. No userinfo/path/query/fragment. P2 must URL-parse/validate host and normalize scheme/host/default port/trailing root slash; this pattern does not replace URL parsing. */
  serverOrigin?: string
  lastErrorCode?: ErrorCode
}

export type RemoteLinkView = RemoteLinkUnpairedView | RemoteLinkPairingView | RemoteLinkPairedView | RemoteLinkRevokedView | RemoteLinkFrozenView

export interface RemoteLoginInput {
  loginName: string
  /** Hub Server account password, never a model credential. Never reflected in responses/logs. */
  password: string
}

/** Bounded owner/resource-scoped page. hasMore=true requires nextCursor; cursor is not a Worker seq. */
export interface RemoteMessagePage {
  items: RemoteMessageView[]
  hasMore: boolean
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  nextCursor?: string
}

/** Explicit audited closure confirmation, not permission to override a detected live process. Import copies history and binds exact vendor ID; never starts a model by itself. */
export interface RemoteNativeImportInput {
  terminalClosedConfirmed: true
  expectedIndexVersion: number
  sourceRevision: string
}

/** Owner-scoped public IDs mapped from Worker/store index. Offline metadata is stale evidence, never write permission. */
export interface RemoteNativeSessionView {
  nativeSessionId: string
  workerId: string
  workspaceId: string
  agentType: RuntimeNativeAgentType
  title: string
  createdAt: string
  updatedAt: string
  indexVersion: number
  sourceRevision: string
  format: RuntimeNativeFormatView
  activity: NativeActivityEvidence
  workerOnline: boolean
}

export interface RemoteNativeSessionPage {
  items: RemoteNativeSessionView[]
  hasMore: boolean
  nextCursor?: string
}

/** Worker local event seq continuity without publishing local-only history. Covers inclusive [firstSeq,seq], firstSeq<=seq. Opaque tombstone only, no local conversation/path/model data. Cannot cover any already published event or remote-critical event; immutable bounded ranges are replayed whole. Persist range coverage before advancing contiguous ack. */
export interface RemoteOmittedEvents {
  type: 'events.omitted'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  firstSeq: number
  reason: 'not_remote_visible'
}

/** Five-minute one-use code; no device secret. Never put the code in a URL. */
export interface RemotePairingChallenge {
  pairRequestId: string
  workerId: string
  pairCode: string
  expiresAt: string
  status: 'pending'
}

export interface RemotePairingConfirmInput {
  pairCode: string
}

/** Authenticated browser preview for explicit device confirmation; does not claim or grant access. */
export interface RemotePairingPreview {
  pairRequestId: string
  deviceName: string
  platform: 'windows' | 'linux' | 'darwin'
  architecture: 'x86_64' | 'aarch64'
  expiresAt: string
}

export interface RemotePairingPreviewInput {
  pairCode: string
}

/** Worker sends its locally generated 256-bit device secret only in Authorization header. Body contains no credential. Unclaimed requests are short-lived authentication challenges, not owner-visible devices. */
export interface RemotePairingRequestInput {
  deviceName: string
  workerStoreId: string
  platform: 'windows' | 'linux' | 'darwin'
  architecture: 'x86_64' | 'aarch64'
}

/** Device-authenticated status poll scoped to this exact request/credential. Reveals no owner or raw credential. */
export interface RemotePairingStatusView {
  pairRequestId: string
  workerId: string
  status: 'pending' | 'paired' | 'expired' | 'revoked'
  expiresAt: string
}

/** HTTP202 after command and server outbox commit. conversationSeq present only for run.submit. No fabricated runId before Worker assigns it. */
export interface RemoteQueuedReceipt {
  commandId: string
  conversationId: string
  conversationSeq?: number
  status: 'queued'
  deliveryState: 'queued_online' | 'queued_offline' | 'reconciliation_required'
  workerOnline: boolean
  expiresAt: string
}

/** HTTP202 transport receipt only. No fabricated conversationId/runId or execution sequence. Poll existing GET /commands/{commandId}; authoritative result comes from Worker. */
export interface RemoteResourceQueuedReceipt {
  commandId: string
  targetWorkerId: string
  type: 'native.import' | 'workspace.register'
  status: 'queued'
  deliveryState: 'queued_online'
  workerOnline: true
  expiresAt: string
}

/** Path runId is mandatory user-visible identity; only retry may supply nodeId. Does not allocate conversationSeq. */
export interface RemoteRunControlInput {
  action: 'pause' | 'resume' | 'cancel' | 'retry'
  nodeId?: string
  reason?: string
  expiresAt?: string
}

/** Bounded owner/resource-scoped page. hasMore=true requires nextCursor; cursor is not a Worker seq. */
export interface RemoteRunPage {
  items: RemoteRunView[]
  hasMore: boolean
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  nextCursor?: string
}

/** Computer orders messages. Offline rejects immediately; revision 2 requires a 30-second delivery grant. Legacy expiresAt cannot extend delivery deadline. Optional explicit re-confirmation for an imported native binding only; scenario rejects it. Native always resumes exact ID with sessionMode=continue. */
export interface RemoteSendMessageInput {
  clientMessageId: string
  text: string
  sessionMode: 'new' | 'continue'
  expiresAt?: string
  nativeConfirmation?: NativeContinuationConfirmationInput
  attachmentIds?: string[]
}

/** Heartbeat acknowledgement is not event ack. After 45 seconds without authenticated Worker traffic mark offline without modifying execution state. */
export interface RemoteServerHeartbeat {
  type: 'server.heartbeat'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  connectionId: string
  receivedAt: string
}

/** Frozen delivery requires a reason. Store changes or ack regression require reconciliation; R1 exposes no automatic force-unfreeze API. */
export interface RemoteWorkerHelloAck {
  type: 'worker.hello_ack'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  connectionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  commandDelivery: 'ready' | 'frozen'
  lastServerAck: RemoteEventPosition | null
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  pendingCommandCursor: string
  heartbeatIntervalSeconds: 15
  offlineAfterSeconds: 45
  reason?: RemoteWire1Error
  serverTime: string
}

export interface RemoteWorkerHelloRejected {
  type: 'worker.hello_rejected'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  error: RemoteWire1Error
  /** Server supported wire revisions, mandatory on rejection (including REMOTE_PROTOCOL_UNSUPPORTED). Initially [1]; during upgrades advertise N and N-1. */
  supportedWireRevisions: number[]
}

export type RemoteServerOutboundFrame = RemoteWorkerHelloAck | RemoteWorkerHelloRejected | RemoteServerHeartbeat | RemoteEventAck | RemoteCommandEnvelope | RemoteConversationSkip

/** Worker local identifiers. Server namespaces by worker/store and maps browser IDs; visibility is display-only. */
export interface RemoteSyncConversation {
  conversationId: string
  workspaceId: string
  sceneId: string
  sceneVersion: number
  title: string
  createdAt: string
  updatedAt: string
  archived: boolean
  visibility: 'both' | 'pc_only' | 'mobile_only'
  metadataVersion: number
  authority: 'local' | 'remote'
}

/** At least one mutable field; browser cannot update copy directly. */
export interface RemoteSyncConversationInput {
  expectedVersion: number
  title?: string
  archived?: boolean
  visibility?: 'both' | 'pc_only' | 'mobile_only'
}

/** At least one title/archived/visibility change; Worker checks metadataVersion atomically. */
export interface RemoteSyncConversationUpdate {
  conversationId: string
  expectedVersion: number
  title?: string
  archived?: boolean
  visibility?: 'both' | 'pc_only' | 'mobile_only'
}

/** Newest first. before and snapshotCursor are opaque owner/device/conversation-scoped signed cursors. New items merge by messageId/revision; never by offset. */
export interface RemoteSyncMessagePage {
  items: RemoteMessageView[]
  hasMore: boolean
  before?: string
  snapshotCursor: string
}

/** Whole UTF-8 text, never truncated; 0-based contiguous segments. Immutable metadata per messageRevision, atomic publish only after digest/byte-count verification. */
export interface RemoteSyncMessageSegment {
  messageId: string
  conversationId: string
  messageSequence: number
  messageRevision: number
  role: 'user' | 'assistant' | 'system'
  createdAt: string
  runId?: string
  text: string
  segmentIndex: number
  segmentCount: number
  totalUtf8Bytes: number
  contentSha256: string
}

/** Only retired content slots, never admission/grant/control facts. Original identity and digest are retained, not rewritten. */
export interface RemoteSyncRedactedSlot {
  seq: number
  eventId: string
  originalType: 'sync.conversation.upserted' | 'sync.message.segment' | 'sync.run.state' | 'sync.backfill.progress' | 'message.appended'
  eventSha256: string
}

export interface RemoteSyncRunState {
  runId: string
  conversationId: string
  status: TaskStatus
  observedAt: string
  executionTaskId?: string
  recoveryRequired?: boolean
}

export interface RemoteSyncSettingsInput {
  mirrorEnabled: boolean
  expectedVersion: number
}

/** Global sync toggle, default true on initialization. Historical name mirrorEnabled does not mean read-only or handover. */
export interface RemoteSyncSettingsView {
  mirrorEnabled: boolean
  version: number
  syncGeneration: number
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV2ApprovalDecisionCommand {
  type: 'approval.decide'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteApprovalDecisionPayload
  deliverBy: string
  localConversationId: string
}

export interface RemoteV2BackfillProgress {
  type: 'sync.backfill.progress'
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  backfillId: string
  batchIndex: number
  batchEventCount: number
  snapshotHighWater: number
  complete: boolean
}

export interface RemoteV2BusySnapshot {
  type: 'sync.busy.snapshot'
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  snapshotId: string
  connectionId: string
  capturedAt: string
  partIndex: number
  partCount: number
  conversationIds: string[]
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV2CancelCommand {
  type: 'run.cancel'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV2CommandWithdrawalCommand {
  type: 'command.withdraw'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteCommandWithdrawalPayload
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV2ConversationCreateCommand {
  type: 'conversation.create'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteCreateConversationInput
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV2ConversationUpdateCommand {
  type: 'conversation.update'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteSyncConversationUpdate
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV2PauseCommand {
  type: 'run.pause'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV2ResumeCommand {
  type: 'run.resume'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV2RetryCommand {
  type: 'run.retry'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV2RunSubmitCommand {
  type: 'run.submit'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  commandId: string
  conversationId: string
  conversationSeq: number
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunSubmitPayload
  deliverBy: string
  localConversationId: string
}

export type RemoteV2CommandEnvelope = RemoteV2RunSubmitCommand | RemoteV2PauseCommand | RemoteV2ResumeCommand | RemoteV2CancelCommand | RemoteV2RetryCommand | RemoteV2ApprovalDecisionCommand | RemoteV2CommandWithdrawalCommand | RemoteV2ConversationUpdateCommand | RemoteV2ConversationCreateCommand

export type RemoteV2CommandReceipt = RemoteV2CommandAccepted | RemoteV2CommandRejected

export interface RemoteV2CommandReceived {
  type: 'command.received'
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  commandDigest: string
  deliverBy: string
  receivedAt: string
}

/** Authenticated privacy coverage control, not a replacement immutable event. Bound to a durable reset/deletion fence. No new seq allocation; normal contiguous ACK only after all covered identities/digests and deletion are committed. */
export interface RemoteV2ContentRedaction {
  type: 'sync.content.redaction'
  wireRevision: 2
  redactionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  /** Deletion-fence generation. Reset retires content generations up to this value; conversation deletion additionally restricts the local conversation ID. Never cover later generations or seq >= deletionSeq. */
  syncGeneration: number
  deletionEventId: string
  deletionSeq: number
  conversationId?: string
  slots: RemoteSyncRedactedSlot[]
}

export interface RemoteV2ConversationDeleted {
  type: 'sync.conversation.deleted'
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  conversationId: string
  deletedAt: string
}

/** Worker requests missing commands or skip records. Never run a later user message across a sequence gap. */
export interface RemoteV2ConversationGap {
  type: 'conversation.gap'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  workerId: string
  workerStoreId: string
  workerEpoch: string
  conversationId: string
  expectedSeq: number
  receivedSeq: number
}

/** Durable ordered tombstone for a never-dispatched submit. Not an execution/control command; cannot be used to erase accepted work. Retain until gap replay/snapshot acknowledgement is safe. */
export interface RemoteV2ConversationSkip {
  type: 'conversation.skip'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  commandId: string
  conversationId: string
  conversationSeq: number
  targetWorkerId: string
  expectedWorkerStoreId: string
  reason: 'withdrawn_before_dispatch' | 'expired_before_dispatch'
  recordedAt: string
}

export interface RemoteV2ConversationUpserted {
  type: 'sync.conversation.upserted'
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  payload: RemoteSyncConversation
}

/** Explicit durable execution permission. Continuous event ACK is never permission. Late unconsumed grants expire; persisted grants are not reverted by server timers. */
export interface RemoteV2DeliveryGrant {
  type: 'command.delivery_granted'
  wireRevision: 2
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  receivedEventId: string
  commandDigest: string
  deliverBy: string
  grantedAt: string
}

/** Only advances after event persistence AND projection/browser-outbox commit; old store ack never trims new store outbox. */
export interface RemoteV2EventAck {
  type: 'worker.events_ack'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  connectionId: string
  workerId: string
  position: RemoteEventPosition
}

export interface RemoteV2MessageSegment {
  type: 'sync.message.segment'
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  payload: RemoteSyncMessageSegment
}

/** Worker local event seq continuity without publishing local-only history. Covers inclusive [firstSeq,seq], firstSeq<=seq. Opaque tombstone only, no local conversation/path/model data. Cannot cover any already published event or remote-critical event; immutable bounded ranges are replayed whole. Persist range coverage before advancing contiguous ack. */
export interface RemoteV2OmittedEvents {
  type: 'events.omitted'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  firstSeq: number
  reason: 'not_remote_visible'
}

/** Heartbeat acknowledgement is not event ack. After 45 seconds without authenticated Worker traffic mark offline without modifying execution state. */
export interface RemoteV2ServerHeartbeat {
  type: 'server.heartbeat'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  connectionId: string
  receivedAt: string
}

/** Frozen delivery requires a reason. Store changes or ack regression require reconciliation; R1 exposes no automatic force-unfreeze API. */
export interface RemoteV2WorkerHelloAck {
  type: 'worker.hello_ack'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  connectionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  commandDelivery: 'ready' | 'frozen'
  lastServerAck: RemoteEventPosition | null
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  pendingCommandCursor: string
  heartbeatIntervalSeconds: 15
  offlineAfterSeconds: 45
  reason?: RemoteWire2Error
  serverTime: string
}

export interface RemoteV2WorkerHelloRejected {
  type: 'worker.hello_rejected'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  error: RemoteWire2Error
  /** Server supported wire revisions, mandatory on rejection (including REMOTE_PROTOCOL_UNSUPPORTED). Initially [1]; during upgrades advertise N and N-1. */
  supportedWireRevisions: number[]
}

export type RemoteV2ServerOutboundFrame = RemoteV2WorkerHelloAck | RemoteV2WorkerHelloRejected | RemoteV2ServerHeartbeat | RemoteV2EventAck | RemoteV2CommandEnvelope | RemoteV2ConversationSkip | RemoteV2DeliveryGrant

export interface RemoteV2SyncReset {
  type: 'sync.reset'
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
}

export interface RemoteV2SyncedRunState {
  type: 'sync.run.state'
  wireRevision: 2
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  payload: RemoteSyncRunState
}

export type RemoteV2VisibleWorkerEvent = RemoteV2CommandAccepted | RemoteV2CommandRejected | RemoteV2CommandCompleted | RemoteV2CommandFailed | RemoteV2ControlObserved | RemoteV2RunStateEvent | RemoteV2MessageEvent | RemoteV2ApprovalEvent | RemoteV2ProgressEvent | RemoteV2CatalogEvent | RemoteV2SkipRecorded | RemoteV2ConversationUpserted | RemoteV2MessageSegment | RemoteV2SyncedRunState | RemoteV2ConversationDeleted | RemoteV2SyncReset | RemoteV2BusySnapshot | RemoteV2BackfillProgress | RemoteV2CommandReceived

export type RemoteV2WorkerEvent = RemoteV2VisibleWorkerEvent | RemoteV2OmittedEvents

/** Sent every 15 seconds. It reports liveness only, not durable business-event progress. */
export interface RemoteV2WorkerHeartbeat {
  type: 'worker.heartbeat'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  connectionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  sentAt: string
  lastServerAck: RemoteEventPosition | null
}

/** First frame after device-authenticated WSS. Same store preserves seq across boots; new store requires null ack. Credentials never appear in frames. */
export interface RemoteV2WorkerHello {
  type: 'worker.hello'
  /** Revision 2; select by connection codec, never by package version. */
  wireRevision: 2
  /** Protocol package semantic version for diagnostics only. Never negotiate or reject based on this value. */
  protocolVersion: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  platform: 'windows' | 'linux' | 'darwin'
  architecture: 'x86_64' | 'aarch64'
  capabilityRevision: number
  lastServerAck: RemoteEventPosition | null
}

export type RemoteV2WorkerOutboundFrame = RemoteV2WorkerHello | RemoteV2WorkerHeartbeat | RemoteV2ConversationGap | RemoteV2WorkerEvent | RemoteV2ContentRedaction

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV3ApprovalDecisionCommand {
  type: 'approval.decide'
  wireRevision: 3
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteApprovalDecisionPayload
  deliverBy: string
  localConversationId: string
}

/** Frozen revision 3 code set. Excludes HTTP-only PAT/suspension codes; future public registry extensions cannot silently widen this domain. */
export type RemoteWire3ErrorCode =
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
  | 'REMOTE_AUTH_REQUIRED'
  | 'REMOTE_CSRF_REJECTED'
  | 'REMOTE_DEVICE_OFFLINE'
  | 'REMOTE_DEVICE_REVOKED'
  | 'REMOTE_DEVICE_AUTH_FAILED'
  | 'REMOTE_PAIRING_EXPIRED'
  | 'REMOTE_PAIRING_CONFLICT'
  | 'REMOTE_PAIRING_INVALID'
  | 'REMOTE_COMMAND_EXPIRED'
  | 'REMOTE_COMMAND_WITHDRAWN'
  | 'REMOTE_WITHDRAWAL_UNCONFIRMED'
  | 'REMOTE_STORE_CHANGED'
  | 'REMOTE_EPOCH_STALE'
  | 'REMOTE_PROTOCOL_UNSUPPORTED'
  | 'REMOTE_EVENT_CONFLICT'
  | 'REMOTE_ACK_CONFLICT'
  | 'REMOTE_SEQUENCE_GAP'
  | 'REMOTE_APPROVAL_FORBIDDEN'
  | 'CONVERSATION_AUTHORITY_MISMATCH'
  | 'REMOTE_TARGET_MISMATCH'
  | 'REMOTE_SCENE_VERSION_MISMATCH'
  | 'REMOTE_CURSOR_EXPIRED'
  | 'REMOTE_CURSOR_INVALID'
  | 'REMOTE_RATE_LIMITED'
  | 'REMOTE_FRAME_TOO_LARGE'
  | 'REMOTE_WITHDRAWAL_TOO_LATE'
  | 'REMOTE_PAIRING_IN_PROGRESS'
  | 'REMOTE_SERVER_UNREACHABLE'
  | 'REMOTE_SERVER_ORIGIN_INVALID'
  | 'REMOTE_CONVERSATION_BUSY'
  | 'REMOTE_STATE_NOT_READY'
  | 'REMOTE_SYNC_CONFLICT'
  | 'REMOTE_SYNC_DISABLED'
  | 'REMOTE_DELIVERY_EXPIRED'
  | 'REMOTE_REVISION_REQUIRED'
  | 'REMOTE_SYNC_RESOURCE_LIMIT'
  | 'REMOTE_QUERY_TIMEOUT'
  | 'REMOTE_QUERY_TOO_LARGE'
  | 'NATIVE_SESSION_ACTIVE'
  | 'NATIVE_SESSION_UNSUPPORTED'
  | 'NATIVE_SESSION_CHANGED'
  | 'NATIVE_SESSION_WRITER_CONFLICT'
  | 'REMOTE_ROOT_NOT_AUTHORIZED'
  | 'REMOTE_PATH_OUTSIDE_ROOT'
  | 'REMOTE_DIRECTORY_CHANGED'

/** Local Worker policy is authoritative. Mandatory blocked actions are git_push/deploy/delete/db_migrate plus locally declared actions; refusal reason code REMOTE_APPROVAL_FORBIDDEN. Rejection of a dangerous action may still be submitted remotely. */
export interface RemoteWire3ApprovalView {
  approvalId: string
  resultRef: RemoteResultRef
  action: DangerousAction
  targetSummary: string
  riskLevel: RiskLevel
  status: ApprovalStatus
  requestedAt: string
  expiresAt: string
  remoteApprovalAllowed: boolean
  workerPolicyRevision: number
  denialCode?: RemoteWire3ErrorCode
}

export interface RemoteV3ApprovalEvent {
  type: 'approval.state_changed'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  conversationId: string
  payload: RemoteWire3ApprovalView
}

export interface RemoteV3BackfillProgress {
  type: 'sync.backfill.progress'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  backfillId: string
  batchIndex: number
  batchEventCount: number
  snapshotHighWater: number
  complete: boolean
}

export interface RemoteV3BusySnapshot {
  type: 'sync.busy.snapshot'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  snapshotId: string
  connectionId: string
  capturedAt: string
  partIndex: number
  partCount: number
  conversationIds: string[]
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV3CancelCommand {
  type: 'run.cancel'
  wireRevision: 3
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
  deliverBy: string
  localConversationId: string
}

/** Atomic bounded complete catalog for R1. Reject oversized catalogs instead of truncating; offline entries are last observed, not proof that paths still exist. Revision 3 producers include authorizedRoots, [] when none; omitted legacy HTTP field means no remote project browsing. */
export interface RemoteV3CatalogView {
  workerId: string
  capabilityRevision: number
  observedAt: string
  workspaces: RemoteWorkspaceSummary[]
  scenes: RemoteSceneSummary[]
  remotelyBlockedActions: DangerousAction[]
  workerStoreId: string
  authorizedRoots?: RemoteAuthorizedRoot[]
}

export interface RemoteV3CatalogEvent {
  type: 'capability.changed'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  payload: RemoteV3CatalogView
}

/** Durable inbox admission, not model/execution success. Duplicate immutable commands return the original receipt/event. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV3CommandAccepted {
  type: 'command.accepted'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId?: string
  receivedAt: string
  status: 'accepted'
  resultRef?: RemoteResultRef
}

/** D41: Worker-only structured evidence, never parsed error text. Empty orphanProcessIds is not proof of no remaining process. A paused process may still exist. */
export interface RemoteV3ControlConfirmed {
  outcome: 'confirmed'
  executionMayStillBeRunning: boolean
  orphanProcessIds: number[]
  reason: string
  evidence: 'adapter_confirmed' | 'node_boundary_paused' | 'already_terminal' | 'retry_enqueued' | 'supervisor_resumed' | 'inbox_tombstone' | 'metadata_committed'
  observedAt: string
}

/** Not universally task success. Retry completes on durable new execution reference; execute completes on actual terminal Run success/cancellation. Cancel/pause/resume require confirmed structured control result. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV3CommandCompleted {
  type: 'command.completed'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId?: string
  resultStatus: 'succeeded' | 'cancelled' | 'confirmed' | 'retry_enqueued' | 'approval_consumed' | 'withdrawn'
  resultRef?: RemoteResultRef
  controlResult?: RemoteV3ControlConfirmed
  resourceRef?: RemoteResourceResultRef
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV3CommandWithdrawalCommand {
  type: 'command.withdraw'
  wireRevision: 3
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteCommandWithdrawalPayload
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV3ConversationCreateCommand {
  type: 'conversation.create'
  wireRevision: 3
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteCreateConversationInput
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV3ConversationUpdateCommand {
  type: 'conversation.update'
  wireRevision: 3
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteSyncConversationUpdate
  deliverBy: string
  localConversationId: string
}

export interface RemoteV3NativeImportCommand {
  type: 'native.import'
  wireRevision: 3
  commandId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  deliverBy: string
  requestId: string
  payload: NativeImportPayload
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV3PauseCommand {
  type: 'run.pause'
  wireRevision: 3
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV3ResumeCommand {
  type: 'run.resume'
  wireRevision: 3
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV3RetryCommand {
  type: 'run.retry'
  wireRevision: 3
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
  deliverBy: string
  localConversationId: string
}

/** Scenario retains sceneId/sceneVersion. Native requires conversationKind=native, agentType/nativeSessionId matching persisted binding and sessionMode=continue; omits scene fields. Confirmation optional only when an existing audited confirmation remains valid. No fuzzy IDs or new-session fallback. */
export interface RemoteV3RunSubmitPayload {
  clientMessageId: string
  workspaceId: string
  sceneId?: string
  sceneVersion?: number
  sessionMode: 'new' | 'continue'
  text: string
  conversationKind?: 'scenario' | 'native'
  agentType?: NativeAgentType
  nativeSessionId?: string
  nativeConfirmation?: NativeClosureConfirmation
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV3RunSubmitCommand {
  type: 'run.submit'
  wireRevision: 3
  commandId: string
  conversationId: string
  conversationSeq: number
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteV3RunSubmitPayload
  deliverBy: string
  localConversationId: string
}

/** Register existing selected folder, not mkdir or init-git. Validate real path again at grant; identical local registration checks, including legitimate non-Git read-only workspaces. */
export interface RemoteWorkspaceRegisterInput {
  rootId: string
  rootVersion: number
  directoryToken: string
  name?: string
}

export interface RemoteV3WorkspaceRegisterCommand {
  type: 'workspace.register'
  wireRevision: 3
  commandId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  deliverBy: string
  requestId: string
  payload: RemoteWorkspaceRegisterInput
}

export type RemoteV3CommandEnvelope = RemoteV3RunSubmitCommand | RemoteV3PauseCommand | RemoteV3ResumeCommand | RemoteV3CancelCommand | RemoteV3RetryCommand | RemoteV3ApprovalDecisionCommand | RemoteV3CommandWithdrawalCommand | RemoteV3ConversationUpdateCommand | RemoteV3ConversationCreateCommand | RemoteV3NativeImportCommand | RemoteV3WorkspaceRegisterCommand

/** Sanitized error. No credential, raw environment, owner locator or arbitrary detail object. */
export interface RemoteWire3Error {
  code: RemoteWire3ErrorCode
  message: string
  retryable: boolean
}

/** Failure after admission. A refused control is distinct from unconfirmed cancellation; do not infer that an Agent process has stopped. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV3CommandFailed {
  type: 'command.failed'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId?: string
  resultStatus: 'failed' | 'rejected'
  error: RemoteWire3Error
  resultRef?: RemoteResultRef
  controlResult?: RemoteControlRejected
}

/** Pre-admission rejection only. An expired sequenced submit consumes its ordered slot without execution. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV3CommandRejected {
  type: 'command.rejected'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId?: string
  receivedAt: string
  status: 'rejected'
  error: RemoteWire3Error
}

export type RemoteV3CommandReceipt = RemoteV3CommandAccepted | RemoteV3CommandRejected

/**  For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV3CommandReceived {
  type: 'command.received'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId?: string
  commandDigest: string
  deliverBy: string
  receivedAt: string
}

/** Only retired content slots, never admission/grant/control facts. Original identity and digest are retained, not rewritten. */
export interface RemoteV3RedactedSlot {
  seq: number
  eventId: string
  originalType: 'sync.conversation.upserted' | 'sync.message.segment' | 'sync.run.state' | 'sync.backfill.progress' | 'message.appended' | 'native.index.upserted'
  eventSha256: string
}

/** Authenticated privacy coverage control, not a replacement immutable event. Bound to a durable reset/deletion fence. No new seq allocation; normal contiguous ACK only after all covered identities/digests and deletion are committed. native.index.deleted fences only that nativeSessionId; imported deletes the index, never the newly imported Hub conversation. sync.reset covers both kinds. No redaction of closure confirmation audit. */
export interface RemoteV3ContentRedaction {
  type: 'sync.content.redaction'
  wireRevision: 3
  redactionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  /** Deletion-fence generation. Reset retires content generations up to this value; conversation deletion additionally restricts the local conversation ID. Never cover later generations or seq >= deletionSeq. */
  syncGeneration: number
  deletionEventId: string
  deletionSeq: number
  conversationId?: string
  slots: RemoteV3RedactedSlot[]
  nativeSessionId?: string
}

export type RemoteV3ControlResult = RemoteV3ControlConfirmed | RemoteControlRejected | RemoteControlUnconfirmed

/** D41: unconfirmed leaves command accepted and pending reconciliation. Run-scoped controls include resultRef/executionStatus. Before a Run exists (withdrawal reconciliation), omit both rather than invent an identity or execution state. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV3ControlObserved {
  type: 'command.control_result'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId?: string
  resultRef?: RemoteResultRef
  controlResult: RemoteV3ControlResult
  executionStatus?: TaskStatus
}

export interface RemoteV3ConversationDeleted {
  type: 'sync.conversation.deleted'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  conversationId: string
  deletedAt: string
}

/** Worker requests missing commands or skip records. Never run a later user message across a sequence gap. */
export interface RemoteV3ConversationGap {
  type: 'conversation.gap'
  wireRevision: 3
  workerId: string
  workerStoreId: string
  workerEpoch: string
  conversationId: string
  expectedSeq: number
  receivedSeq: number
}

/** Durable ordered tombstone for a never-dispatched submit. Not an execution/control command; cannot be used to erase accepted work. Retain until gap replay/snapshot acknowledgement is safe. */
export interface RemoteV3ConversationSkip {
  type: 'conversation.skip'
  wireRevision: 3
  commandId: string
  conversationId: string
  conversationSeq: number
  targetWorkerId: string
  expectedWorkerStoreId: string
  reason: 'withdrawn_before_dispatch' | 'expired_before_dispatch'
  recordedAt: string
}

/** Worker local identifiers. Server namespaces by worker/store and maps browser IDs; visibility is display-only. Missing conversationKind means scenario (requires existing scene fields). Native requires agentType/nativeSessionId and omits scene fields; exact vendor session binding remains local. */
export interface RemoteV3SyncConversation {
  conversationId: string
  workspaceId: string
  sceneId?: string
  sceneVersion?: number
  title: string
  createdAt: string
  updatedAt: string
  archived: boolean
  visibility: 'both' | 'pc_only' | 'mobile_only'
  metadataVersion: number
  authority: 'local' | 'remote'
  conversationKind?: 'scenario' | 'native'
  agentType?: NativeAgentType
  nativeSessionId?: string
  nativeActivity?: NativeActivityEvidence
  nativeSourceRevision?: string
}

export interface RemoteV3ConversationUpserted {
  type: 'sync.conversation.upserted'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  payload: RemoteV3SyncConversation
}

/** Explicit durable execution permission. Continuous event ACK is never permission. Late unconsumed grants expire; persisted grants are not reverted by server timers. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV3DeliveryGrant {
  type: 'command.delivery_granted'
  wireRevision: 3
  commandId: string
  conversationId?: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  receivedEventId: string
  commandDigest: string
  deliverBy: string
  grantedAt: string
}

export interface RemoteV3DirectoryQuery {
  type: 'query.directory.list'
  wireRevision: 3
  queryId: string
  requestId: string
  connectionId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  workerEpoch: string
  expiresAt: string
  payload: DirectoryListingInput
}

/** Only advances after event persistence AND projection/browser-outbox commit; old store ack never trims new store outbox. */
export interface RemoteV3EventAck {
  type: 'worker.events_ack'
  wireRevision: 3
  connectionId: string
  workerId: string
  position: RemoteEventPosition
}

export interface RemoteV3MessageEvent {
  type: 'message.appended'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  conversationId: string
  payload: RemoteWorkerMessagePayload
}

/** Sanitized observable progress only. Never private model reasoning, raw provider auth, full environment, or credential files. */
export interface RemoteV3ProgressEvent {
  type: 'run.progress'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  conversationId: string
  resultRef: RemoteResultRef
  message: string
}

/** Worker creates/binds LocalRun and execution Task using existing semantics; it does not invent long-lived Task or retryOfRunId. */
export interface RemoteV3RunStateEvent {
  type: 'run.state_changed'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  payload: RemoteRunStatePayload
}

/** Worker records ordered skip in the same durable inbox ordering ledger as submits. */
export interface RemoteV3SkipRecorded {
  type: 'conversation.skip_recorded'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  conversationSeq: number
}

export type RemoteV3ExecutionEvent = RemoteV3CommandAccepted | RemoteV3CommandRejected | RemoteV3CommandCompleted | RemoteV3CommandFailed | RemoteV3ControlObserved | RemoteV3RunStateEvent | RemoteV3MessageEvent | RemoteV3ApprovalEvent | RemoteV3ProgressEvent | RemoteV3CatalogEvent | RemoteV3SkipRecorded

export interface RemoteV3MessageSegment {
  type: 'sync.message.segment'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  payload: RemoteSyncMessageSegment
}

export interface RemoteV3NativeConfirmationRecorded {
  type: 'native.closure.confirmed'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  nativeSessionId: string
  confirmation: NativeClosureConfirmation
}

export interface RemoteV3NativeIndexDeleted {
  type: 'native.index.deleted'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  nativeSessionId: string
  workspaceId: string
  deletedAt: string
  reason: 'source_removed' | 'workspace_removed' | 'imported'
}

export interface RemoteV3NativeIndexUpserted {
  type: 'native.index.upserted'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  payload: NativeSessionIndex
}

export interface RemoteV3NativeReadQuery {
  type: 'query.native.messages'
  wireRevision: 3
  queryId: string
  requestId: string
  connectionId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  workerEpoch: string
  expiresAt: string
  payload: NativeReadInput
}

/** Worker local event seq continuity without publishing local-only history. Covers inclusive [firstSeq,seq], firstSeq<=seq. Opaque tombstone only, no local conversation/path/model data. Cannot cover any already published event or remote-critical event; immutable bounded ranges are replayed whole. Persist range coverage before advancing contiguous ack. */
export interface RemoteV3OmittedEvents {
  type: 'events.omitted'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  firstSeq: number
  reason: 'not_remote_visible'
}

export interface RemoteV3QueryFailed {
  type: 'query.failed'
  wireRevision: 3
  queryId: string
  requestId: string
  connectionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  error: RemoteWire3Error
}

export type RemoteV3QueryPayload = NativeMessagePage | DirectoryListingPage

export interface RemoteV3QueryResultSegment {
  type: 'query.result.segment'
  wireRevision: 3
  queryId: string
  requestId: string
  connectionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  resultType: 'native.messages' | 'directory.list'
  segmentIndex: number
  segmentCount: number
  totalUtf8Bytes: number
  contentSha256: string
  text: string
}

/** Heartbeat acknowledgement is not event ack. After 45 seconds without authenticated Worker traffic mark offline without modifying execution state. */
export interface RemoteV3ServerHeartbeat {
  type: 'server.heartbeat'
  wireRevision: 3
  connectionId: string
  receivedAt: string
}

/** Frozen delivery requires a reason. Store changes or ack regression require reconciliation; R1 exposes no automatic force-unfreeze API. */
export interface RemoteV3WorkerHelloAck {
  type: 'worker.hello_ack'
  wireRevision: 3
  connectionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  commandDelivery: 'ready' | 'frozen'
  lastServerAck: RemoteEventPosition | null
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  pendingCommandCursor: string
  heartbeatIntervalSeconds: 15
  offlineAfterSeconds: 45
  reason?: RemoteWire3Error
  serverTime: string
}

export interface RemoteV3WorkerHelloRejected {
  type: 'worker.hello_rejected'
  wireRevision: 3
  error: RemoteWire3Error
  /** Server supported wire revisions, mandatory on rejection (including REMOTE_PROTOCOL_UNSUPPORTED). Initially [1]; during upgrades advertise N and N-1. */
  supportedWireRevisions: number[]
}

export type RemoteV3ServerOutboundFrame = RemoteV3WorkerHelloAck | RemoteV3WorkerHelloRejected | RemoteV3ServerHeartbeat | RemoteV3EventAck | RemoteV3CommandEnvelope | RemoteV3ConversationSkip | RemoteV3DeliveryGrant | RemoteV3NativeReadQuery | RemoteV3DirectoryQuery

export interface RemoteV3SyncReset {
  type: 'sync.reset'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
}

export interface RemoteV3SyncedRunState {
  type: 'sync.run.state'
  wireRevision: 3
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  payload: RemoteSyncRunState
}

export type RemoteV3VisibleWorkerEvent = RemoteV3CommandAccepted | RemoteV3CommandRejected | RemoteV3CommandCompleted | RemoteV3CommandFailed | RemoteV3ControlObserved | RemoteV3RunStateEvent | RemoteV3MessageEvent | RemoteV3ApprovalEvent | RemoteV3ProgressEvent | RemoteV3CatalogEvent | RemoteV3SkipRecorded | RemoteV3ConversationUpserted | RemoteV3MessageSegment | RemoteV3SyncedRunState | RemoteV3ConversationDeleted | RemoteV3SyncReset | RemoteV3BusySnapshot | RemoteV3BackfillProgress | RemoteV3CommandReceived | RemoteV3NativeIndexUpserted | RemoteV3NativeIndexDeleted | RemoteV3NativeConfirmationRecorded

export type RemoteV3WorkerEvent = RemoteV3VisibleWorkerEvent | RemoteV3OmittedEvents

/** Sent every 15 seconds. It reports liveness only, not durable business-event progress. */
export interface RemoteV3WorkerHeartbeat {
  type: 'worker.heartbeat'
  wireRevision: 3
  connectionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  sentAt: string
  lastServerAck: RemoteEventPosition | null
}

/** First frame after device-authenticated WSS. Same store preserves seq across boots; new store requires null ack. Credentials never appear in frames. */
export interface RemoteV3WorkerHello {
  type: 'worker.hello'
  wireRevision: 3
  /** Protocol package semantic version for diagnostics only. Never negotiate or reject based on this value. */
  protocolVersion: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  platform: 'windows' | 'linux' | 'darwin'
  architecture: 'x86_64' | 'aarch64'
  capabilityRevision: number
  lastServerAck: RemoteEventPosition | null
}

export type RemoteV3WorkerOutboundFrame = RemoteV3WorkerHello | RemoteV3WorkerHeartbeat | RemoteV3ConversationGap | RemoteV3WorkerEvent | RemoteV3ContentRedaction | RemoteV3QueryResultSegment | RemoteV3QueryFailed

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV4ApprovalDecisionCommand {
  type: 'approval.decide'
  wireRevision: 4
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteApprovalDecisionPayload
  deliverBy: string
  localConversationId: string
}

/** Frozen revision 4 error domain. New registry codes never silently broaden older codecs. Missing/deleted/expired attachment uses existing NOT_FOUND after authorization. */
export type RemoteWire4ErrorCode =
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
  | 'REMOTE_AUTH_REQUIRED'
  | 'REMOTE_CSRF_REJECTED'
  | 'REMOTE_DEVICE_OFFLINE'
  | 'REMOTE_DEVICE_REVOKED'
  | 'REMOTE_DEVICE_AUTH_FAILED'
  | 'REMOTE_PAIRING_EXPIRED'
  | 'REMOTE_PAIRING_CONFLICT'
  | 'REMOTE_PAIRING_INVALID'
  | 'REMOTE_COMMAND_EXPIRED'
  | 'REMOTE_COMMAND_WITHDRAWN'
  | 'REMOTE_WITHDRAWAL_UNCONFIRMED'
  | 'REMOTE_STORE_CHANGED'
  | 'REMOTE_EPOCH_STALE'
  | 'REMOTE_PROTOCOL_UNSUPPORTED'
  | 'REMOTE_EVENT_CONFLICT'
  | 'REMOTE_ACK_CONFLICT'
  | 'REMOTE_SEQUENCE_GAP'
  | 'REMOTE_APPROVAL_FORBIDDEN'
  | 'CONVERSATION_AUTHORITY_MISMATCH'
  | 'REMOTE_TARGET_MISMATCH'
  | 'REMOTE_SCENE_VERSION_MISMATCH'
  | 'REMOTE_CURSOR_EXPIRED'
  | 'REMOTE_CURSOR_INVALID'
  | 'REMOTE_RATE_LIMITED'
  | 'REMOTE_FRAME_TOO_LARGE'
  | 'REMOTE_WITHDRAWAL_TOO_LATE'
  | 'REMOTE_PAIRING_IN_PROGRESS'
  | 'REMOTE_SERVER_UNREACHABLE'
  | 'REMOTE_SERVER_ORIGIN_INVALID'
  | 'REMOTE_CONVERSATION_BUSY'
  | 'REMOTE_STATE_NOT_READY'
  | 'REMOTE_SYNC_CONFLICT'
  | 'REMOTE_SYNC_DISABLED'
  | 'REMOTE_DELIVERY_EXPIRED'
  | 'REMOTE_REVISION_REQUIRED'
  | 'REMOTE_SYNC_RESOURCE_LIMIT'
  | 'REMOTE_QUERY_TIMEOUT'
  | 'REMOTE_QUERY_TOO_LARGE'
  | 'NATIVE_SESSION_ACTIVE'
  | 'NATIVE_SESSION_UNSUPPORTED'
  | 'NATIVE_SESSION_CHANGED'
  | 'NATIVE_SESSION_WRITER_CONFLICT'
  | 'REMOTE_ROOT_NOT_AUTHORIZED'
  | 'REMOTE_PATH_OUTSIDE_ROOT'
  | 'REMOTE_DIRECTORY_CHANGED'
  | 'ATTACHMENT_TOO_LARGE'
  | 'ATTACHMENT_TYPE_UNSUPPORTED'
  | 'ATTACHMENT_COUNT_EXCEEDED'
  | 'ATTACHMENT_QUOTA_EXCEEDED'
  | 'ATTACHMENT_HASH_MISMATCH'
  | 'AGENT_IMAGE_UNSUPPORTED'
  | 'ATTACHMENT_DOWNLOAD_FAILED'
  | 'ATTACHMENT_NOT_READY'
  | 'ATTACHMENT_IN_USE'
  | 'ATTACHMENT_THUMBNAIL_UNAVAILABLE'
  | 'ATTACHMENT_PREPARATION_INTERRUPTED'

/** Local Worker policy is authoritative. Mandatory blocked actions are git_push/deploy/delete/db_migrate plus locally declared actions; refusal reason code REMOTE_APPROVAL_FORBIDDEN. Rejection of a dangerous action may still be submitted remotely. */
export interface RemoteWire4ApprovalView {
  approvalId: string
  resultRef: RemoteResultRef
  action: DangerousAction
  targetSummary: string
  riskLevel: RiskLevel
  status: ApprovalStatus
  requestedAt: string
  expiresAt: string
  remoteApprovalAllowed: boolean
  workerPolicyRevision: number
  denialCode?: RemoteWire4ErrorCode
}

export interface RemoteV4ApprovalEvent {
  type: 'approval.state_changed'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  conversationId: string
  payload: RemoteWire4ApprovalView
}

export interface RemoteV4BackfillProgress {
  type: 'sync.backfill.progress'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  backfillId: string
  batchIndex: number
  batchEventCount: number
  snapshotHighWater: number
  complete: boolean
}

export interface RemoteV4BusySnapshot {
  type: 'sync.busy.snapshot'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  snapshotId: string
  connectionId: string
  capturedAt: string
  partIndex: number
  partCount: number
  conversationIds: string[]
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV4CancelCommand {
  type: 'run.cancel'
  wireRevision: 4
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
  deliverBy: string
  localConversationId: string
}

export interface RoleImageCapability {
  roleId: string
  agentId: string
  imageInput: ImageInputCapability
}

/** Worker scene index only; model/provider credential or installation/subscription data is not relayed. */
export interface RemoteV4SceneSummary {
  sceneId: string
  name: string
  version: number
  readOnly: boolean
  roleImageCapabilities?: RoleImageCapability[]
}

/** Atomic bounded complete catalog for R1. Reject oversized catalogs instead of truncating; offline entries are last observed, not proof that paths still exist. Revision 3 producers include authorizedRoots, [] when none; omitted legacy HTTP field means no remote project browsing. Revision 4 includes each scene role image capability and native Agent capability; missing entries mean unknown. */
export interface RemoteV4CatalogView {
  workerId: string
  capabilityRevision: number
  observedAt: string
  workspaces: RemoteWorkspaceSummary[]
  scenes: RemoteV4SceneSummary[]
  remotelyBlockedActions: DangerousAction[]
  workerStoreId: string
  authorizedRoots?: RemoteAuthorizedRoot[]
  nativeImageCapabilities?: NativeImageCapability[]
}

export interface RemoteV4CatalogEvent {
  type: 'capability.changed'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  payload: RemoteV4CatalogView
}

/** Durable inbox admission, not model/execution success. Duplicate immutable commands return the original receipt/event. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV4CommandAccepted {
  type: 'command.accepted'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId?: string
  receivedAt: string
  status: 'accepted'
  resultRef?: RemoteResultRef
}

/** Not universally task success. Retry completes on durable new execution reference; execute completes on actual terminal Run success/cancellation. Cancel/pause/resume require confirmed structured control result. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV4CommandCompleted {
  type: 'command.completed'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId?: string
  resultStatus: 'succeeded' | 'cancelled' | 'confirmed' | 'retry_enqueued' | 'approval_consumed' | 'withdrawn'
  resultRef?: RemoteResultRef
  controlResult?: RemoteV4ControlConfirmed
  resourceRef?: RemoteResourceResultRef
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV4CommandWithdrawalCommand {
  type: 'command.withdraw'
  wireRevision: 4
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteCommandWithdrawalPayload
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV4ConversationCreateCommand {
  type: 'conversation.create'
  wireRevision: 4
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteCreateConversationInput
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV4ConversationUpdateCommand {
  type: 'conversation.update'
  wireRevision: 4
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteSyncConversationUpdate
  deliverBy: string
  localConversationId: string
}

export interface RemoteV4NativeImportCommand {
  type: 'native.import'
  wireRevision: 4
  commandId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  deliverBy: string
  requestId: string
  payload: NativeImportPayload
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV4PauseCommand {
  type: 'run.pause'
  wireRevision: 4
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV4ResumeCommand {
  type: 'run.resume'
  wireRevision: 4
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV4RetryCommand {
  type: 'run.retry'
  wireRevision: 4
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
  deliverBy: string
  localConversationId: string
}

/** Scenario retains sceneId/sceneVersion. Native requires conversationKind=native, agentType/nativeSessionId matching persisted binding and sessionMode=continue; omits scene fields. Confirmation optional only when an existing audited confirmation remains valid. No fuzzy IDs or new-session fallback. With images, capabilityRevision is mandatory and all selected roles must support the detected image type/size. Download only after accepted grant and before any Agent start. */
export interface RemoteV4RunSubmitPayload {
  clientMessageId: string
  workspaceId: string
  sceneId?: string
  sceneVersion?: number
  sessionMode: 'new' | 'continue'
  text: string
  conversationKind?: 'scenario' | 'native'
  agentType?: NativeAgentType
  nativeSessionId?: string
  nativeConfirmation?: NativeClosureConfirmation
  attachments?: AttachmentManifestItem[]
  attachmentCapabilityRevision?: number
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV4RunSubmitCommand {
  type: 'run.submit'
  wireRevision: 4
  commandId: string
  conversationId: string
  conversationSeq: number
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteV4RunSubmitPayload
  deliverBy: string
  localConversationId: string
}

export interface RemoteV4WorkspaceRegisterCommand {
  type: 'workspace.register'
  wireRevision: 4
  commandId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  deliverBy: string
  requestId: string
  payload: RemoteWorkspaceRegisterInput
}

export type RemoteV4CommandEnvelope = RemoteV4RunSubmitCommand | RemoteV4PauseCommand | RemoteV4ResumeCommand | RemoteV4CancelCommand | RemoteV4RetryCommand | RemoteV4ApprovalDecisionCommand | RemoteV4CommandWithdrawalCommand | RemoteV4ConversationUpdateCommand | RemoteV4ConversationCreateCommand | RemoteV4NativeImportCommand | RemoteV4WorkspaceRegisterCommand

/** Sanitized error. No credential, raw environment, owner locator or arbitrary detail object. */
export interface RemoteWire4Error {
  code: RemoteWire4ErrorCode
  message: string
  retryable: boolean
}

/** Failure after admission. A refused control is distinct from unconfirmed cancellation; do not infer that an Agent process has stopped. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV4CommandFailed {
  type: 'command.failed'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId?: string
  resultStatus: 'failed' | 'rejected'
  error: RemoteWire4Error
  resultRef?: RemoteResultRef
  controlResult?: RemoteControlRejected
}

/** Pre-admission rejection only. An expired sequenced submit consumes its ordered slot without execution. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV4CommandRejected {
  type: 'command.rejected'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId?: string
  receivedAt: string
  status: 'rejected'
  error: RemoteWire4Error
}

export type RemoteV4CommandReceipt = RemoteV4CommandAccepted | RemoteV4CommandRejected

/**  For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV4CommandReceived {
  type: 'command.received'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId?: string
  commandDigest: string
  deliverBy: string
  receivedAt: string
}

/** Only retired content slots, never admission/grant/control facts. Original identity and digest are retained, not rewritten. */
export interface RemoteV4RedactedSlot {
  seq: number
  eventId: string
  originalType: 'sync.conversation.upserted' | 'sync.message.segment' | 'sync.run.state' | 'sync.backfill.progress' | 'message.appended' | 'native.index.upserted'
  eventSha256: string
}

/** Authenticated privacy coverage control, not a replacement immutable event. Bound to a durable reset/deletion fence. No new seq allocation; normal contiguous ACK only after all covered identities/digests and deletion are committed. native.index.deleted fences only that nativeSessionId; imported deletes the index, never the newly imported Hub conversation. sync.reset covers both kinds. No redaction of closure confirmation audit. */
export interface RemoteV4ContentRedaction {
  type: 'sync.content.redaction'
  wireRevision: 4
  redactionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  /** Deletion-fence generation. Reset retires content generations up to this value; conversation deletion additionally restricts the local conversation ID. Never cover later generations or seq >= deletionSeq. */
  syncGeneration: number
  deletionEventId: string
  deletionSeq: number
  conversationId?: string
  slots: RemoteV4RedactedSlot[]
  nativeSessionId?: string
}

/** D41: unconfirmed leaves command accepted and pending reconciliation. Run-scoped controls include resultRef/executionStatus. Before a Run exists (withdrawal reconciliation), omit both rather than invent an identity or execution state. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV4ControlObserved {
  type: 'command.control_result'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId?: string
  resultRef?: RemoteResultRef
  controlResult: RemoteV4ControlResult
  executionStatus?: TaskStatus
}

export interface RemoteV4ConversationDeleted {
  type: 'sync.conversation.deleted'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  conversationId: string
  deletedAt: string
}

/** Worker requests missing commands or skip records. Never run a later user message across a sequence gap. */
export interface RemoteV4ConversationGap {
  type: 'conversation.gap'
  wireRevision: 4
  workerId: string
  workerStoreId: string
  workerEpoch: string
  conversationId: string
  expectedSeq: number
  receivedSeq: number
}

/** Durable ordered tombstone for a never-dispatched submit. Not an execution/control command; cannot be used to erase accepted work. Retain until gap replay/snapshot acknowledgement is safe. */
export interface RemoteV4ConversationSkip {
  type: 'conversation.skip'
  wireRevision: 4
  commandId: string
  conversationId: string
  conversationSeq: number
  targetWorkerId: string
  expectedWorkerStoreId: string
  reason: 'withdrawn_before_dispatch' | 'expired_before_dispatch'
  recordedAt: string
}

/** Worker local identifiers. Server namespaces by worker/store and maps browser IDs; visibility is display-only. Missing conversationKind means scenario (requires existing scene fields). Native requires agentType/nativeSessionId and omits scene fields; exact vendor session binding remains local. */
export interface RemoteV4SyncConversation {
  conversationId: string
  workspaceId: string
  sceneId?: string
  sceneVersion?: number
  title: string
  createdAt: string
  updatedAt: string
  archived: boolean
  visibility: 'both' | 'pc_only' | 'mobile_only'
  metadataVersion: number
  authority: 'local' | 'remote'
  conversationKind?: 'scenario' | 'native'
  agentType?: NativeAgentType
  nativeSessionId?: string
  nativeActivity?: NativeActivityEvidence
  nativeSourceRevision?: string
}

export interface RemoteV4ConversationUpserted {
  type: 'sync.conversation.upserted'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  payload: RemoteV4SyncConversation
}

/** Explicit durable execution permission. Continuous event ACK is never permission. Late unconsumed grants expire; persisted grants are not reverted by server timers. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV4DeliveryGrant {
  type: 'command.delivery_granted'
  wireRevision: 4
  commandId: string
  conversationId?: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  receivedEventId: string
  commandDigest: string
  deliverBy: string
  grantedAt: string
}

export interface RemoteV4DirectoryQuery {
  type: 'query.directory.list'
  wireRevision: 4
  queryId: string
  requestId: string
  connectionId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  workerEpoch: string
  expiresAt: string
  payload: DirectoryListingInput
}

/** Only advances after event persistence AND projection/browser-outbox commit; old store ack never trims new store outbox. */
export interface RemoteV4EventAck {
  type: 'worker.events_ack'
  wireRevision: 4
  connectionId: string
  workerId: string
  position: RemoteEventPosition
}

export interface RemoteV4MessageEvent {
  type: 'message.appended'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  conversationId: string
  payload: RemoteWorkerMessagePayload
}

/** Sanitized observable progress only. Never private model reasoning, raw provider auth, full environment, or credential files. */
export interface RemoteV4ProgressEvent {
  type: 'run.progress'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  conversationId: string
  resultRef: RemoteResultRef
  message: string
}

/** Worker creates/binds LocalRun and execution Task using existing semantics; it does not invent long-lived Task or retryOfRunId. */
export interface RemoteV4RunStateEvent {
  type: 'run.state_changed'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  payload: RemoteRunStatePayload
}

/** Worker records ordered skip in the same durable inbox ordering ledger as submits. */
export interface RemoteV4SkipRecorded {
  type: 'conversation.skip_recorded'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  conversationSeq: number
}

export type RemoteV4ExecutionEvent = RemoteV4CommandAccepted | RemoteV4CommandRejected | RemoteV4CommandCompleted | RemoteV4CommandFailed | RemoteV4ControlObserved | RemoteV4RunStateEvent | RemoteV4MessageEvent | RemoteV4ApprovalEvent | RemoteV4ProgressEvent | RemoteV4CatalogEvent | RemoteV4SkipRecorded

/** Worker-local attachment identity; originAttachmentId only for a browser upload authorized in this message command. Pending/unavailable never claim bytes exist; available requires server-verified upload. Same metadata in every message segment. */
export interface SyncAttachmentItem {
  localAttachmentId: string
  fileName: string
  kind: 'image' | 'file'
  mimeType: 'image/jpeg' | 'image/png' | 'image/webp' | 'image/gif' | 'application/pdf' | 'text/plain'
  sizeBytes: number
  sha256: string
  availability: 'pending_upload' | 'available' | 'unavailable'
  originAttachmentId?: string
  errorCode?: RemoteWire4ErrorCode
}

/** Whole UTF-8 text, never truncated; 0-based contiguous segments. Immutable metadata per messageRevision, atomic publish only after digest/byte-count verification. */
export interface RemoteV4SyncMessageSegment {
  messageId: string
  conversationId: string
  messageSequence: number
  messageRevision: number
  role: 'user' | 'assistant' | 'system'
  createdAt: string
  runId?: string
  text: string
  segmentIndex: number
  segmentCount: number
  totalUtf8Bytes: number
  contentSha256: string
  attachments?: SyncAttachmentItem[]
  sourceCommandId?: string
}

export interface RemoteV4MessageSegment {
  type: 'sync.message.segment'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  payload: RemoteV4SyncMessageSegment
}

export interface RemoteV4NativeConfirmationRecorded {
  type: 'native.closure.confirmed'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  nativeSessionId: string
  confirmation: NativeClosureConfirmation
}

export interface RemoteV4NativeIndexDeleted {
  type: 'native.index.deleted'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  nativeSessionId: string
  workspaceId: string
  deletedAt: string
  reason: 'source_removed' | 'workspace_removed' | 'imported'
}

export interface RemoteV4NativeIndexUpserted {
  type: 'native.index.upserted'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  payload: NativeSessionIndex
}

export interface RemoteV4NativeReadQuery {
  type: 'query.native.messages'
  wireRevision: 4
  queryId: string
  requestId: string
  connectionId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  workerEpoch: string
  expiresAt: string
  payload: NativeReadInput
}

/** Worker local event seq continuity without publishing local-only history. Covers inclusive [firstSeq,seq], firstSeq<=seq. Opaque tombstone only, no local conversation/path/model data. Cannot cover any already published event or remote-critical event; immutable bounded ranges are replayed whole. Persist range coverage before advancing contiguous ack. */
export interface RemoteV4OmittedEvents {
  type: 'events.omitted'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  firstSeq: number
  reason: 'not_remote_visible'
}

export interface RemoteV4QueryFailed {
  type: 'query.failed'
  wireRevision: 4
  queryId: string
  requestId: string
  connectionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  error: RemoteWire4Error
}

export type RemoteV4QueryPayload = NativeMessagePage | DirectoryListingPage

export interface RemoteV4QueryResultSegment {
  type: 'query.result.segment'
  wireRevision: 4
  queryId: string
  requestId: string
  connectionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  resultType: 'native.messages' | 'directory.list'
  segmentIndex: number
  segmentCount: number
  totalUtf8Bytes: number
  contentSha256: string
  text: string
}

/** Heartbeat acknowledgement is not event ack. After 45 seconds without authenticated Worker traffic mark offline without modifying execution state. */
export interface RemoteV4ServerHeartbeat {
  type: 'server.heartbeat'
  wireRevision: 4
  connectionId: string
  receivedAt: string
}

/** Frozen delivery requires a reason. Store changes or ack regression require reconciliation; R1 exposes no automatic force-unfreeze API. */
export interface RemoteV4WorkerHelloAck {
  type: 'worker.hello_ack'
  wireRevision: 4
  connectionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  commandDelivery: 'ready' | 'frozen'
  lastServerAck: RemoteEventPosition | null
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  pendingCommandCursor: string
  heartbeatIntervalSeconds: 15
  offlineAfterSeconds: 45
  reason?: RemoteWire4Error
  serverTime: string
}

export interface RemoteV4WorkerHelloRejected {
  type: 'worker.hello_rejected'
  wireRevision: 4
  error: RemoteWire4Error
  /** Server supported wire revisions, mandatory on rejection (including REMOTE_PROTOCOL_UNSUPPORTED). Initially [1]; during upgrades advertise N and N-1. */
  supportedWireRevisions: number[]
}

export type RemoteV4ServerOutboundFrame = RemoteV4WorkerHelloAck | RemoteV4WorkerHelloRejected | RemoteV4ServerHeartbeat | RemoteV4EventAck | RemoteV4CommandEnvelope | RemoteV4ConversationSkip | RemoteV4DeliveryGrant | RemoteV4NativeReadQuery | RemoteV4DirectoryQuery

export interface RemoteV4SyncReset {
  type: 'sync.reset'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
}

export interface RemoteV4SyncedRunState {
  type: 'sync.run.state'
  wireRevision: 4
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  payload: RemoteSyncRunState
}

export type RemoteV4VisibleWorkerEvent = RemoteV4CommandAccepted | RemoteV4CommandRejected | RemoteV4CommandCompleted | RemoteV4CommandFailed | RemoteV4ControlObserved | RemoteV4RunStateEvent | RemoteV4MessageEvent | RemoteV4ApprovalEvent | RemoteV4ProgressEvent | RemoteV4CatalogEvent | RemoteV4SkipRecorded | RemoteV4ConversationUpserted | RemoteV4MessageSegment | RemoteV4SyncedRunState | RemoteV4ConversationDeleted | RemoteV4SyncReset | RemoteV4BusySnapshot | RemoteV4BackfillProgress | RemoteV4CommandReceived | RemoteV4NativeIndexUpserted | RemoteV4NativeIndexDeleted | RemoteV4NativeConfirmationRecorded

export type RemoteV4WorkerEvent = RemoteV4VisibleWorkerEvent | RemoteV4OmittedEvents

/** Sent every 15 seconds. It reports liveness only, not durable business-event progress. */
export interface RemoteV4WorkerHeartbeat {
  type: 'worker.heartbeat'
  wireRevision: 4
  connectionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  sentAt: string
  lastServerAck: RemoteEventPosition | null
}

/** First frame after device-authenticated WSS. Same store preserves seq across boots; new store requires null ack. Credentials never appear in frames. */
export interface RemoteV4WorkerHello {
  type: 'worker.hello'
  wireRevision: 4
  /** Protocol package semantic version for diagnostics only. Never negotiate or reject based on this value. */
  protocolVersion: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  platform: 'windows' | 'linux' | 'darwin'
  architecture: 'x86_64' | 'aarch64'
  capabilityRevision: number
  lastServerAck: RemoteEventPosition | null
}

export type RemoteV4WorkerOutboundFrame = RemoteV4WorkerHello | RemoteV4WorkerHeartbeat | RemoteV4ConversationGap | RemoteV4WorkerEvent | RemoteV4ContentRedaction | RemoteV4QueryResultSegment | RemoteV4QueryFailed

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV5ApprovalDecisionCommand {
  type: 'approval.decide'
  wireRevision: 5
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteApprovalDecisionPayload
  deliverBy: string
  localConversationId: string
}

export interface RemoteV5BackfillProgress {
  type: 'sync.backfill.progress'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  backfillId: string
  batchIndex: number
  batchEventCount: number
  snapshotHighWater: number
  complete: boolean
}

export interface RemoteV5BusySnapshot {
  type: 'sync.busy.snapshot'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  snapshotId: string
  connectionId: string
  capturedAt: string
  partIndex: number
  partCount: number
  conversationIds: string[]
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV5CancelCommand {
  type: 'run.cancel'
  wireRevision: 5
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
  deliverBy: string
  localConversationId: string
}

/** Worker scene index only; model/provider credential or installation/subscription data is not relayed. */
export interface RemoteV5SceneSummary {
  sceneId: string
  name: string
  version: number
  readOnly: boolean
  roleImageCapabilities?: RuntimeRoleImageCapability[]
}

export interface RuntimeCatalogEntry {
  agentId: string
  agentType: RuntimeNativeAgentType
  guard?: RuntimeGuardView
  nativeSessionsSupported: boolean
}

/** Atomic bounded complete catalog for R1. Reject oversized catalogs instead of truncating; offline entries are last observed, not proof that paths still exist. Revision 3 producers include authorizedRoots, [] when none; omitted legacy HTTP field means no remote project browsing. Revision 4 includes each scene role image capability and native Agent capability; missing entries mean unknown. */
export interface RemoteV5CatalogView {
  workerId: string
  capabilityRevision: number
  observedAt: string
  workspaces: RemoteWorkspaceSummary[]
  scenes: RemoteV5SceneSummary[]
  remotelyBlockedActions: DangerousAction[]
  workerStoreId: string
  authorizedRoots?: RemoteAuthorizedRoot[]
  nativeImageCapabilities?: RuntimeNativeImageCapability[]
  runtimes?: RuntimeCatalogEntry[]
}

export interface RemoteV5CatalogEvent {
  type: 'capability.changed'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  payload: RemoteV5CatalogView
}

/** Durable inbox admission, not model/execution success. Duplicate immutable commands return the original receipt/event. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV5CommandAccepted {
  type: 'command.accepted'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId?: string
  receivedAt: string
  status: 'accepted'
  resultRef?: RemoteResultRef
}

/** D41: Worker-only structured evidence, never parsed error text. Empty orphanProcessIds is not proof of no remaining process. A paused process may still exist. input_preparation_cancelled requires durable no-Agent-start fence and confirmed stopped preparation I/O, never inferred from a missing process handle. */
export interface RemoteV5ControlConfirmed {
  outcome: 'confirmed'
  executionMayStillBeRunning: boolean
  orphanProcessIds: number[]
  reason: string
  evidence: 'adapter_confirmed' | 'node_boundary_paused' | 'already_terminal' | 'retry_enqueued' | 'supervisor_resumed' | 'inbox_tombstone' | 'metadata_committed' | 'input_preparation_cancelled'
  observedAt: string
}

/** Not universally task success. Retry completes on durable new execution reference; execute completes on actual terminal Run success/cancellation. Cancel/pause/resume require confirmed structured control result. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV5CommandCompleted {
  type: 'command.completed'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId?: string
  resultStatus: 'succeeded' | 'cancelled' | 'confirmed' | 'retry_enqueued' | 'approval_consumed' | 'withdrawn'
  resultRef?: RemoteResultRef
  controlResult?: RemoteV5ControlConfirmed
  resourceRef?: RemoteResourceResultRef
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV5CommandWithdrawalCommand {
  type: 'command.withdraw'
  wireRevision: 5
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteCommandWithdrawalPayload
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV5ConversationCreateCommand {
  type: 'conversation.create'
  wireRevision: 5
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteCreateConversationInput
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV5ConversationUpdateCommand {
  type: 'conversation.update'
  wireRevision: 5
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteSyncConversationUpdate
  deliverBy: string
  localConversationId: string
}

export interface RemoteV5NativeImportCommand {
  type: 'native.import'
  wireRevision: 5
  commandId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  deliverBy: string
  requestId: string
  payload: NativeImportPayload
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV5PauseCommand {
  type: 'run.pause'
  wireRevision: 5
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV5ResumeCommand {
  type: 'run.resume'
  wireRevision: 5
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
  deliverBy: string
  localConversationId: string
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV5RetryCommand {
  type: 'run.retry'
  wireRevision: 5
  commandId: string
  conversationId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteRunControlPayload
  deliverBy: string
  localConversationId: string
}

/** Scenario retains sceneId/sceneVersion. Native requires conversationKind=native, agentType/nativeSessionId matching persisted binding and sessionMode=continue; omits scene fields. Confirmation optional only when an existing audited confirmation remains valid. No fuzzy IDs or new-session fallback. With images, capabilityRevision is mandatory and all selected roles must support the detected image type/size. Download only after accepted grant and before any Agent start. */
export interface RemoteV5RunSubmitPayload {
  clientMessageId: string
  workspaceId: string
  sceneId?: string
  sceneVersion?: number
  sessionMode: 'new' | 'continue'
  text: string
  conversationKind?: 'scenario' | 'native'
  agentType?: RuntimeNativeAgentType
  nativeSessionId?: string
  nativeConfirmation?: NativeClosureConfirmation
  attachments?: AttachmentManifestItem[]
  attachmentCapabilityRevision?: number
}

/** Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice. */
export interface RemoteV5RunSubmitCommand {
  type: 'run.submit'
  wireRevision: 5
  commandId: string
  conversationId: string
  conversationSeq: number
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  payload: RemoteV5RunSubmitPayload
  deliverBy: string
  localConversationId: string
}

export interface RemoteV5WorkspaceRegisterCommand {
  type: 'workspace.register'
  wireRevision: 5
  commandId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  createdAt: string
  expiresAt: string
  deliverBy: string
  requestId: string
  payload: RemoteWorkspaceRegisterInput
}

export type RemoteV5CommandEnvelope = RemoteV5RunSubmitCommand | RemoteV5PauseCommand | RemoteV5ResumeCommand | RemoteV5CancelCommand | RemoteV5RetryCommand | RemoteV5ApprovalDecisionCommand | RemoteV5CommandWithdrawalCommand | RemoteV5ConversationUpdateCommand | RemoteV5ConversationCreateCommand | RemoteV5NativeImportCommand | RemoteV5WorkspaceRegisterCommand

/** Sanitized error. No credential, raw environment, owner locator or arbitrary detail object. */
export interface RemoteWire5Error {
  code: RemoteWire5ErrorCode
  message: string
  retryable: boolean
}

/** Failure after admission. A refused control is distinct from unconfirmed cancellation; do not infer that an Agent process has stopped. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV5CommandFailed {
  type: 'command.failed'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId?: string
  resultStatus: 'failed' | 'rejected'
  error: RemoteWire5Error
  resultRef?: RemoteResultRef
  controlResult?: RemoteControlRejected
}

/** Pre-admission rejection only. An expired sequenced submit consumes its ordered slot without execution. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV5CommandRejected {
  type: 'command.rejected'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId?: string
  receivedAt: string
  status: 'rejected'
  error: RemoteWire5Error
}

export type RemoteV5CommandReceipt = RemoteV5CommandAccepted | RemoteV5CommandRejected

/**  For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV5CommandReceived {
  type: 'command.received'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId?: string
  commandDigest: string
  deliverBy: string
  receivedAt: string
}

/** Only retired content slots, never admission/grant/control facts. Original identity and digest are retained, not rewritten. */
export interface RemoteV5RedactedSlot {
  seq: number
  eventId: string
  originalType: 'sync.conversation.upserted' | 'sync.message.segment' | 'sync.run.state' | 'sync.backfill.progress' | 'message.appended' | 'native.index.upserted'
  eventSha256: string
}

/** Authenticated privacy coverage control, not a replacement immutable event. Bound to a durable reset/deletion fence. No new seq allocation; normal contiguous ACK only after all covered identities/digests and deletion are committed. native.index.deleted fences only that nativeSessionId; imported deletes the index, never the newly imported Hub conversation. sync.reset covers both kinds. No redaction of closure confirmation audit. */
export interface RemoteV5ContentRedaction {
  type: 'sync.content.redaction'
  wireRevision: 5
  redactionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  /** Deletion-fence generation. Reset retires content generations up to this value; conversation deletion additionally restricts the local conversation ID. Never cover later generations or seq >= deletionSeq. */
  syncGeneration: number
  deletionEventId: string
  deletionSeq: number
  conversationId?: string
  slots: RemoteV5RedactedSlot[]
  nativeSessionId?: string
}

export type RemoteV5ControlResult = RemoteV5ControlConfirmed | RemoteControlRejected | RemoteControlUnconfirmed

/** D41: unconfirmed leaves command accepted and pending reconciliation. Run-scoped controls include resultRef/executionStatus. Before a Run exists (withdrawal reconciliation), omit both rather than invent an identity or execution state. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV5ControlObserved {
  type: 'command.control_result'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId?: string
  resultRef?: RemoteResultRef
  controlResult: RemoteV5ControlResult
  executionStatus?: TaskStatus
}

export interface RemoteV5ConversationDeleted {
  type: 'sync.conversation.deleted'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  conversationId: string
  deletedAt: string
}

/** Worker requests missing commands or skip records. Never run a later user message across a sequence gap. */
export interface RemoteV5ConversationGap {
  type: 'conversation.gap'
  wireRevision: 5
  workerId: string
  workerStoreId: string
  workerEpoch: string
  conversationId: string
  expectedSeq: number
  receivedSeq: number
}

/** Durable ordered tombstone for a never-dispatched submit. Not an execution/control command; cannot be used to erase accepted work. Retain until gap replay/snapshot acknowledgement is safe. */
export interface RemoteV5ConversationSkip {
  type: 'conversation.skip'
  wireRevision: 5
  commandId: string
  conversationId: string
  conversationSeq: number
  targetWorkerId: string
  expectedWorkerStoreId: string
  reason: 'withdrawn_before_dispatch' | 'expired_before_dispatch'
  recordedAt: string
}

/** Worker local identifiers. Server namespaces by worker/store and maps browser IDs; visibility is display-only. Missing conversationKind means scenario (requires existing scene fields). Native requires agentType/nativeSessionId and omits scene fields; exact vendor session binding remains local. */
export interface RemoteV5SyncConversation {
  conversationId: string
  workspaceId: string
  sceneId?: string
  sceneVersion?: number
  title: string
  createdAt: string
  updatedAt: string
  archived: boolean
  visibility: 'both' | 'pc_only' | 'mobile_only'
  metadataVersion: number
  authority: 'local' | 'remote'
  conversationKind?: 'scenario' | 'native'
  agentType?: RuntimeNativeAgentType
  nativeSessionId?: string
  nativeActivity?: NativeActivityEvidence
  nativeSourceRevision?: string
}

export interface RemoteV5ConversationUpserted {
  type: 'sync.conversation.upserted'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  payload: RemoteV5SyncConversation
}

/** Explicit durable execution permission. Continuous event ACK is never permission. Late unconsumed grants expire; persisted grants are not reverted by server timers. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command. */
export interface RemoteV5DeliveryGrant {
  type: 'command.delivery_granted'
  wireRevision: 5
  commandId: string
  conversationId?: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  receivedEventId: string
  commandDigest: string
  deliverBy: string
  grantedAt: string
}

export interface RemoteV5DirectoryQuery {
  type: 'query.directory.list'
  wireRevision: 5
  queryId: string
  requestId: string
  connectionId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  workerEpoch: string
  expiresAt: string
  payload: DirectoryListingInput
}

/** Only advances after event persistence AND projection/browser-outbox commit; old store ack never trims new store outbox. */
export interface RemoteV5EventAck {
  type: 'worker.events_ack'
  wireRevision: 5
  connectionId: string
  workerId: string
  position: RemoteEventPosition
}

export interface RemoteV5MessageEvent {
  type: 'message.appended'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  conversationId: string
  payload: RemoteWorkerMessagePayload
}

/** Sanitized observable progress only. Never private model reasoning, raw provider auth, full environment, or credential files. */
export interface RemoteV5ProgressEvent {
  type: 'run.progress'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  conversationId: string
  resultRef: RemoteResultRef
  message: string
}

/** Worker creates/binds LocalRun and execution Task using existing semantics; it does not invent long-lived Task or retryOfRunId. */
export interface RemoteV5RunStateEvent {
  type: 'run.state_changed'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  payload: RemoteRunStatePayload
}

/** Worker records ordered skip in the same durable inbox ordering ledger as submits. */
export interface RemoteV5SkipRecorded {
  type: 'conversation.skip_recorded'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  conversationId: string
  conversationSeq: number
}

export type RemoteV5ExecutionEvent = RemoteV5CommandAccepted | RemoteV5CommandRejected | RemoteV5CommandCompleted | RemoteV5CommandFailed | RemoteV5ControlObserved | RemoteV5RunStateEvent | RemoteV5MessageEvent | RemoteV5ApprovalEvent | RemoteV5ProgressEvent | RemoteV5CatalogEvent | RemoteV5SkipRecorded

/** Whole UTF-8 text, never truncated; 0-based contiguous segments. Immutable metadata per messageRevision, atomic publish only after digest/byte-count verification. */
export interface RemoteV5SyncMessageSegment {
  messageId: string
  conversationId: string
  messageSequence: number
  messageRevision: number
  role: 'user' | 'assistant' | 'system'
  createdAt: string
  runId?: string
  text: string
  segmentIndex: number
  segmentCount: number
  totalUtf8Bytes: number
  contentSha256: string
  attachments?: SyncAttachmentItem[]
  sourceCommandId?: string
}

export interface RemoteV5MessageSegment {
  type: 'sync.message.segment'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  payload: RemoteV5SyncMessageSegment
}

export interface RemoteV5NativeConfirmationRecorded {
  type: 'native.closure.confirmed'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  commandId: string
  nativeSessionId: string
  confirmation: NativeClosureConfirmation
}

export interface RemoteV5NativeIndexDeleted {
  type: 'native.index.deleted'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  nativeSessionId: string
  workspaceId: string
  deletedAt: string
  reason: 'source_removed' | 'workspace_removed' | 'imported'
}

export interface RemoteV5NativeIndexUpserted {
  type: 'native.index.upserted'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  payload: RuntimeNativeSessionIndex
}

export interface RemoteV5NativeReadQuery {
  type: 'query.native.messages'
  wireRevision: 5
  queryId: string
  requestId: string
  connectionId: string
  targetWorkerId: string
  expectedWorkerStoreId: string
  workerEpoch: string
  expiresAt: string
  payload: NativeReadInput
}

/** Worker local event seq continuity without publishing local-only history. Covers inclusive [firstSeq,seq], firstSeq<=seq. Opaque tombstone only, no local conversation/path/model data. Cannot cover any already published event or remote-critical event; immutable bounded ranges are replayed whole. Persist range coverage before advancing contiguous ack. */
export interface RemoteV5OmittedEvents {
  type: 'events.omitted'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  firstSeq: number
  reason: 'not_remote_visible'
}

export interface RemoteV5QueryFailed {
  type: 'query.failed'
  wireRevision: 5
  queryId: string
  requestId: string
  connectionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  error: RemoteWire5Error
}

export type RemoteV5QueryPayload = NativeMessagePage | DirectoryListingPage

export interface RemoteV5QueryResultSegment {
  type: 'query.result.segment'
  wireRevision: 5
  queryId: string
  requestId: string
  connectionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  resultType: 'native.messages' | 'directory.list'
  segmentIndex: number
  segmentCount: number
  totalUtf8Bytes: number
  contentSha256: string
  text: string
}

/** Heartbeat acknowledgement is not event ack. After 45 seconds without authenticated Worker traffic mark offline without modifying execution state. */
export interface RemoteV5ServerHeartbeat {
  type: 'server.heartbeat'
  wireRevision: 5
  connectionId: string
  receivedAt: string
}

/** Frozen delivery requires a reason. Store changes or ack regression require reconciliation; R1 exposes no automatic force-unfreeze API. */
export interface RemoteV5WorkerHelloAck {
  type: 'worker.hello_ack'
  wireRevision: 5
  connectionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  commandDelivery: 'ready' | 'frozen'
  lastServerAck: RemoteEventPosition | null
  /** Opaque owner/resource-scoped server cursor; never a Worker seq or cross-owner resource selector. */
  pendingCommandCursor: string
  heartbeatIntervalSeconds: 15
  offlineAfterSeconds: 45
  reason?: RemoteWire5Error
  serverTime: string
}

export interface RemoteV5WorkerHelloRejected {
  type: 'worker.hello_rejected'
  wireRevision: 5
  error: RemoteWire5Error
  /** Server supported wire revisions, mandatory on rejection (including REMOTE_PROTOCOL_UNSUPPORTED). Initially [1]; during upgrades advertise N and N-1. */
  supportedWireRevisions: number[]
}

export type RemoteV5ServerOutboundFrame = RemoteV5WorkerHelloAck | RemoteV5WorkerHelloRejected | RemoteV5ServerHeartbeat | RemoteV5EventAck | RemoteV5CommandEnvelope | RemoteV5ConversationSkip | RemoteV5DeliveryGrant | RemoteV5NativeReadQuery | RemoteV5DirectoryQuery

export interface RemoteV5SyncReset {
  type: 'sync.reset'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
}

export interface RemoteV5SyncedRunState {
  type: 'sync.run.state'
  wireRevision: 5
  eventId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  seq: number
  occurredAt: string
  syncGeneration: number
  payload: RemoteSyncRunState
}

export type RemoteV5VisibleWorkerEvent = RemoteV5CommandAccepted | RemoteV5CommandRejected | RemoteV5CommandCompleted | RemoteV5CommandFailed | RemoteV5ControlObserved | RemoteV5RunStateEvent | RemoteV5MessageEvent | RemoteV5ApprovalEvent | RemoteV5ProgressEvent | RemoteV5CatalogEvent | RemoteV5SkipRecorded | RemoteV5ConversationUpserted | RemoteV5MessageSegment | RemoteV5SyncedRunState | RemoteV5ConversationDeleted | RemoteV5SyncReset | RemoteV5BusySnapshot | RemoteV5BackfillProgress | RemoteV5CommandReceived | RemoteV5NativeIndexUpserted | RemoteV5NativeIndexDeleted | RemoteV5NativeConfirmationRecorded

export type RemoteV5WorkerEvent = RemoteV5VisibleWorkerEvent | RemoteV5OmittedEvents

/** Sent every 15 seconds. It reports liveness only, not durable business-event progress. */
export interface RemoteV5WorkerHeartbeat {
  type: 'worker.heartbeat'
  wireRevision: 5
  connectionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  sentAt: string
  lastServerAck: RemoteEventPosition | null
}

/** First frame after device-authenticated WSS. Same store preserves seq across boots; new store requires null ack. Credentials never appear in frames. */
export interface RemoteV5WorkerHello {
  type: 'worker.hello'
  wireRevision: 5
  /** Protocol package semantic version for diagnostics only. Never negotiate or reject based on this value. */
  protocolVersion: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  platform: 'windows' | 'linux' | 'darwin'
  architecture: 'x86_64' | 'aarch64'
  capabilityRevision: number
  lastServerAck: RemoteEventPosition | null
}

export type RemoteV5WorkerOutboundFrame = RemoteV5WorkerHello | RemoteV5WorkerHeartbeat | RemoteV5ConversationGap | RemoteV5WorkerEvent | RemoteV5ContentRedaction | RemoteV5QueryResultSegment | RemoteV5QueryFailed

export type RemoteWorkerEvent = RemoteVisibleWorkerEvent | RemoteOmittedEvents

/** Sent every 15 seconds. It reports liveness only, not durable business-event progress. */
export interface RemoteWorkerHeartbeat {
  type: 'worker.heartbeat'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  connectionId: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  sentAt: string
  lastServerAck: RemoteEventPosition | null
}

/** First frame after device-authenticated WSS. Same store preserves seq across boots; new store requires null ack. Credentials never appear in frames. */
export interface RemoteWorkerHello {
  type: 'worker.hello'
  /** Worker/Server wire revision, independent of protocol package version. Revision 1 shape is frozen. */
  wireRevision: 1
  /** Protocol package semantic version for diagnostics only. Never negotiate or reject based on this value. */
  protocolVersion: string
  workerId: string
  workerStoreId: string
  workerEpoch: string
  platform: 'windows' | 'linux' | 'darwin'
  architecture: 'x86_64' | 'aarch64'
  capabilityRevision: number
  lastServerAck: RemoteEventPosition | null
}

export type RemoteWorkerOutboundFrame = RemoteWorkerHello | RemoteWorkerHeartbeat | RemoteConversationGap | RemoteWorkerEvent

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
  taskSpec?: AgentTaskSpec
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

export interface SaveLocalSceneInput {
  roles: LocalRoleConfig[]
  expectedVersion: number
  reviewMode?: ReviewMode
  name?: string
  description?: string
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

/**  Optional explicit re-confirmation for an imported native binding only; scenario rejects it. Native always resumes exact ID with sessionMode=continue. */
export interface SendLocalMessageInput {
  clientMessageId: string
  text: string
  sessionMode: 'new' | 'continue'
  nativeConfirmation?: NativeContinuationConfirmationInput
  attachmentIds?: string[]
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

/** Explicit consent to multiple real model calls and potential charges for this exact target. No automatic model fallback/retry/restart. GET does not run probes. */
export interface StartLocalImageVerificationInput {
  agentId: string
  /** Exact model selector; reject URLs, filesystem paths, dot/dot-dot segments or credentials. Omitted modelId selects CLI default, not an invented model name. For PI use provider/modelId, split the first slash only; pi-rpc-images-v1 transport. Resolve default selection before verification and invalidate on effective provider/model/config change. */
  modelId?: string
  expectedTargetRevision: string
  acknowledgeModelUsage: true
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

export interface TaskCreatedPayload {
  objective: string
  workspaceId: string
  profileId: string
  source: TaskSource
  parentTaskId?: string
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

/** At least one non-null title, archived or visibility is required. Workspace, scene and session associations remain unchanged. */
export interface UpdateLocalConversationInput {
  expectedVersion: number
  title?: string
  archived?: boolean
  visibility?: 'both' | 'pc_only' | 'mobile_only'
}

export interface UpdateLocalRoleTemplateInput {
  expectedVersion: number
  name: string
  instructions: string
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
  { id: 'analyst', displayName: '代码分析', description: '只读梳理代码与调用链' },
  { id: 'planner', displayName: '需求规划', description: '只读分析需求并输出方案，不修改业务文件' },
  { id: 'developer', displayName: '项目开发', description: '在授权项目的隔离工作树实施并验证' },
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
  REMOTE_AUTH_REQUIRED: { http: 401, retryable: false },
  REMOTE_CSRF_REJECTED: { http: 403, retryable: false },
  REMOTE_DEVICE_OFFLINE: { http: 409, retryable: true },
  REMOTE_DEVICE_REVOKED: { http: 403, retryable: false },
  REMOTE_DEVICE_AUTH_FAILED: { http: 401, retryable: false },
  REMOTE_PAIRING_EXPIRED: { http: 410, retryable: false },
  REMOTE_PAIRING_CONFLICT: { http: 409, retryable: false },
  REMOTE_PAIRING_INVALID: { http: 404, retryable: false },
  REMOTE_COMMAND_EXPIRED: { http: 410, retryable: false },
  REMOTE_COMMAND_WITHDRAWN: { http: 409, retryable: false },
  REMOTE_WITHDRAWAL_UNCONFIRMED: { http: 409, retryable: false },
  REMOTE_STORE_CHANGED: { http: 409, retryable: false },
  REMOTE_EPOCH_STALE: { http: 409, retryable: false },
  REMOTE_PROTOCOL_UNSUPPORTED: { http: 409, retryable: false },
  REMOTE_EVENT_CONFLICT: { http: 409, retryable: false },
  REMOTE_ACK_CONFLICT: { http: 409, retryable: false },
  REMOTE_SEQUENCE_GAP: { http: 409, retryable: true },
  REMOTE_APPROVAL_FORBIDDEN: { http: 403, retryable: false },
  CONVERSATION_AUTHORITY_MISMATCH: { http: 409, retryable: false },
  REMOTE_TARGET_MISMATCH: { http: 409, retryable: false },
  REMOTE_SCENE_VERSION_MISMATCH: { http: 409, retryable: false },
  REMOTE_CURSOR_EXPIRED: { http: 410, retryable: false },
  REMOTE_CURSOR_INVALID: { http: 400, retryable: false },
  REMOTE_RATE_LIMITED: { http: 429, retryable: true },
  REMOTE_FRAME_TOO_LARGE: { http: 413, retryable: false },
  REMOTE_WITHDRAWAL_TOO_LATE: { http: 409, retryable: false },
  REMOTE_PAIRING_IN_PROGRESS: { http: 409, retryable: false },
  REMOTE_SERVER_UNREACHABLE: { http: 503, retryable: true },
  REMOTE_SERVER_ORIGIN_INVALID: { http: 422, retryable: false },
  REMOTE_CONVERSATION_BUSY: { http: 409, retryable: true },
  REMOTE_STATE_NOT_READY: { http: 409, retryable: true },
  REMOTE_SYNC_CONFLICT: { http: 409, retryable: false },
  REMOTE_SYNC_DISABLED: { http: 409, retryable: false },
  REMOTE_DELIVERY_EXPIRED: { http: 409, retryable: true },
  REMOTE_REVISION_REQUIRED: { http: 409, retryable: false },
  REMOTE_SYNC_RESOURCE_LIMIT: { http: 413, retryable: false },
  REMOTE_DEVICE_SUSPENDED: { http: 409, retryable: false },
  REMOTE_API_TOKEN_INVALID: { http: 401, retryable: false },
  REMOTE_API_TOKEN_EXPIRED: { http: 401, retryable: false },
  REMOTE_API_TOKEN_SCOPE_INSUFFICIENT: { http: 403, retryable: false },
  REMOTE_AUTH_AMBIGUOUS: { http: 400, retryable: false },
  REMOTE_QUERY_TIMEOUT: { http: 504, retryable: true },
  REMOTE_QUERY_TOO_LARGE: { http: 413, retryable: false },
  NATIVE_SESSION_ACTIVE: { http: 409, retryable: false },
  NATIVE_SESSION_UNSUPPORTED: { http: 422, retryable: false },
  NATIVE_SESSION_CHANGED: { http: 409, retryable: false },
  NATIVE_SESSION_WRITER_CONFLICT: { http: 409, retryable: false },
  REMOTE_ROOT_NOT_AUTHORIZED: { http: 403, retryable: false },
  REMOTE_PATH_OUTSIDE_ROOT: { http: 403, retryable: false },
  REMOTE_DIRECTORY_CHANGED: { http: 409, retryable: false },
  ATTACHMENT_TOO_LARGE: { http: 413, retryable: false },
  ATTACHMENT_TYPE_UNSUPPORTED: { http: 415, retryable: false },
  ATTACHMENT_COUNT_EXCEEDED: { http: 422, retryable: false },
  ATTACHMENT_QUOTA_EXCEEDED: { http: 409, retryable: false },
  ATTACHMENT_HASH_MISMATCH: { http: 422, retryable: false },
  AGENT_IMAGE_UNSUPPORTED: { http: 422, retryable: false },
  ATTACHMENT_DOWNLOAD_FAILED: { http: 502, retryable: true },
  ATTACHMENT_NOT_READY: { http: 409, retryable: false },
  ATTACHMENT_IN_USE: { http: 409, retryable: false },
  ATTACHMENT_THUMBNAIL_UNAVAILABLE: { http: 409, retryable: false },
  ATTACHMENT_PREPARATION_INTERRUPTED: { http: 409, retryable: false },
  PI_GUARD_UNAVAILABLE: { http: 409, retryable: false },
  PI_UNCONTROLLED_EXTENSIONS: { http: 409, retryable: false },
  PI_TOOL_CALL_BLOCKED: { http: 403, retryable: false },
}
