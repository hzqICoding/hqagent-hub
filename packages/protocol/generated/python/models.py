"""此文件由 scripts/protocol/generate.py 生成，请勿手改。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION = "0.3.0"


class _Base(BaseModel):
    """边界 DTO 基类：线上字段是 camelCase，Python 侧用 snake_case 访问。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class AcknowledgeUpdateResultInput(_Base):
    to_version: str | None = Field(default=None, alias="toVersion")


AdapterId = str


class AdapterIntegrationKind(StrEnum):
    SDK = "sdk"
    CLI_STREAM = "cli_stream"
    MCP = "mcp"
    SIDECAR = "sidecar"
    GUI_AUTOMATION = "gui_automation"


class AdapterPlatform(StrEnum):
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"


class AuthKind(StrEnum):
    LOCAL_LOGIN = "local_login"
    API_KEY = "api_key"
    OAUTH = "oauth"
    DEVICE_CODE = "device_code"
    NONE = "none"


class CapabilityId(StrEnum):
    ORCHESTRATION = "orchestration"
    ARCHITECTURE = "architecture"
    CODING = "coding"
    REVIEW = "review"
    TESTING = "testing"
    SHELL = "shell"
    FILE_WRITE = "file_write"
    GIT_WORKTREE = "git_worktree"
    SESSION_RESUME = "session_resume"
    STREAMING_EVENTS = "streaming_events"
    TOOL_APPROVAL = "tool_approval"
    STRUCTURED_OUTPUT = "structured_output"
    VISION = "vision"
    BROWSER = "browser"


class DeclaredCapability(_Base):
    id: CapabilityId = Field(alias="id")
    supported: bool = Field(alias="supported")
    note: str | None = Field(default=None, alias="note")


Timestamp = str


class AdapterDescriptor(_Base):
    """detect() 的返回值。描述「这个 Adapter 是什么、装没装、能干什么」，是一次性发现结果，不是周期性存活状态——后者见 AdapterHealth。"""

    adapter_id: AdapterId = Field(alias="adapterId")
    display_name: str = Field(alias="displayName")
    integration_kind: AdapterIntegrationKind = Field(alias="integrationKind")
    auth_kind: AuthKind = Field(alias="authKind")
    supported_platforms: list[AdapterPlatform] = Field(alias="supportedPlatforms")
    installed: bool = Field(alias="installed")
    detected_version: str | None = Field(default=None, alias="detectedVersion")
    minimum_version: str | None = Field(default=None, alias="minimumVersion")
    executable_path: str | None = Field(default=None, alias="executablePath")
    capabilities: list[DeclaredCapability] = Field(alias="capabilities")
    detected_at: Timestamp | None = Field(default=None, alias="detectedAt")


class AdapterEvent(_Base):
    """streamEvents() 逐条产出的事件（裁决 D32）。故意不带 eventId 和 seq——全局单调 seq 与幂等 eventId 由 Hub 分配，Adapter 直接产出 HubEvent 会把这个所有权弄乱。Hub 收到后补齐这两个字段再落库广播。不冻结这个形状的话，W2 定义一套、W3 消费时再猜一套，接缝正好落在两个包中间"""

    session_id: str = Field(alias="sessionId")
    type: str = Field(alias="type")
    occurred_at: Timestamp = Field(alias="occurredAt")
    payload: dict[str, Any] = Field(alias="payload")
    external_request_id: str | None = Field(default=None, alias="externalRequestId")
    vendor_event_name: str | None = Field(default=None, alias="vendorEventName")


class AdapterFailureKind(StrEnum):
    NOT_INSTALLED = "not_installed"
    NOT_LOGGED_IN = "not_logged_in"
    VERSION_INCOMPATIBLE = "version_incompatible"
    CAPABILITY_MISSING = "capability_missing"
    TRANSPORT_ERROR = "transport_error"
    AGENT_ERROR = "agent_error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PATH_VIOLATION = "path_violation"


class ErrorCode(StrEnum):
    BAD_REQUEST = "BAD_REQUEST"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    UNAUTHORIZED = "UNAUTHORIZED"
    ORIGIN_NOT_ALLOWED = "ORIGIN_NOT_ALLOWED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    IDEMPOTENCY_MISMATCH = "IDEMPOTENCY_MISMATCH"
    PROTOCOL_VERSION_MISMATCH = "PROTOCOL_VERSION_MISMATCH"
    HUB_NOT_READY = "HUB_NOT_READY"
    HUB_MAINTENANCE = "HUB_MAINTENANCE"
    EVENT_CURSOR_EXPIRED = "EVENT_CURSOR_EXPIRED"
    FEATURE_UNAVAILABLE = "FEATURE_UNAVAILABLE"
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    AGENT_OFFLINE = "AGENT_OFFLINE"
    AGENT_NOT_LOGGED_IN = "AGENT_NOT_LOGGED_IN"
    AGENT_INCOMPATIBLE = "AGENT_INCOMPATIBLE"
    CAPABILITY_MISSING = "CAPABILITY_MISSING"
    ROLE_UNRESOLVED = "ROLE_UNRESOLVED"
    SESSION_NOT_RESUMABLE = "SESSION_NOT_RESUMABLE"
    TASK_NOT_CANCELLABLE = "TASK_NOT_CANCELLABLE"
    TASK_ACTION_INVALID = "TASK_ACTION_INVALID"
    WORKTREE_BUSY = "WORKTREE_BUSY"
    PATH_NOT_ALLOWED = "PATH_NOT_ALLOWED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_ALREADY_DECIDED = "APPROVAL_ALREADY_DECIDED"
    UPDATE_NOT_AVAILABLE = "UPDATE_NOT_AVAILABLE"
    UPDATE_BUSY = "UPDATE_BUSY"
    UPDATE_VERIFY_FAILED = "UPDATE_VERIFY_FAILED"
    UPDATE_DRAIN_TIMEOUT = "UPDATE_DRAIN_TIMEOUT"
    INTERNAL = "INTERNAL"


class AdapterFailure(_Base):
    """任何 Port 方法失败时的统一结构。接入失败或缺少硬能力必须走这里，不得返回成功后在事件里静默降级。"""

    kind: AdapterFailureKind = Field(alias="kind")
    code: ErrorCode | None = Field(default=None, alias="code")
    message: str = Field(alias="message")
    retryable: bool = Field(alias="retryable")
    missing_capabilities: list[CapabilityId] | None = Field(default=None, alias="missingCapabilities")
    violation_paths: list[str] | None = Field(default=None, alias="violationPaths")
    raw: str | None = Field(default=None, alias="raw")


class AgentStatus(StrEnum):
    DISCOVERING = "discovering"
    READY = "ready"
    BUSY = "busy"
    NOT_LOGGED_IN = "not_logged_in"
    INCOMPATIBLE = "incompatible"
    DISABLED = "disabled"
    OFFLINE = "offline"
    ERROR = "error"
    UNKNOWN = "unknown"


class AdapterHealth(_Base):
    """health() 的返回值。周期性探活与登录态检查，比 detect() 轻量，不重新枚举能力。"""

    status: AgentStatus = Field(alias="status")
    checked_at: Timestamp = Field(alias="checkedAt")
    latency_ms: int | None = Field(default=None, alias="latencyMs")
    auth_valid: bool | None = Field(default=None, alias="authValid")
    diagnostic_message: str | None = Field(default=None, alias="diagnosticMessage")


class AdapterStreamStatus(StrEnum):
    STREAMING = "streaming"
    TRANSPORT_LOST = "transport_lost"
    AGENT_EXITED = "agent_exited"
    ENDED = "ended"


class AdapterStreamEnd(_Base):
    status: AdapterStreamStatus = Field(alias="status")
    ended_at: Timestamp = Field(alias="endedAt")
    last_event_seq: int | None = Field(default=None, alias="lastEventSeq")
    resumable: bool | None = Field(default=None, alias="resumable")
    detail: str | None = Field(default=None, alias="detail")


class AddWorkspaceInput(_Base):
    path: str = Field(alias="path")
    name: str | None = Field(default=None, alias="name")
    default_profile_id: str | None = Field(default=None, alias="defaultProfileId")


class Blocker(_Base):
    kind: Literal["capability_gap", "permission_denied", "dependency_missing", "ambiguous_requirement", "external_failure", "other"] = Field(alias="kind")
    message: str = Field(alias="message")
    detail: dict[str, Any] | None = Field(default=None, alias="detail")


class FileChange(_Base):
    path: str = Field(alias="path")
    change_kind: Literal["added", "modified", "deleted", "renamed"] = Field(alias="changeKind")
    insertions: int | None = Field(default=None, alias="insertions")
    deletions: int | None = Field(default=None, alias="deletions")
    renamed_from: str | None = Field(default=None, alias="renamedFrom")


class TestOutcome(_Base):
    name: str = Field(alias="name")
    command: str = Field(alias="command")
    passed: bool = Field(alias="passed")
    duration_ms: int | None = Field(default=None, alias="durationMs")
    exit_code: int | None = Field(default=None, alias="exitCode")
    output_excerpt: str | None = Field(default=None, alias="outputExcerpt")


class AgentResult(_Base):
    status: Literal["done", "failed", "blocked"] = Field(alias="status")
    summary: str = Field(alias="summary")
    changed_files: list[FileChange] | None = Field(default=None, alias="changedFiles")
    tests: list[TestOutcome] | None = Field(default=None, alias="tests")
    commit: str | None = Field(default=None, alias="commit")
    branch: str | None = Field(default=None, alias="branch")
    artifacts: list[str] | None = Field(default=None, alias="artifacts")
    blockers: list[Blocker] | None = Field(default=None, alias="blockers")
    questions: list[str] | None = Field(default=None, alias="questions")


class AgentCompletedPayload(_Base):
    result: AgentResult = Field(alias="result")


class AgentDiscoveryError(_Base):
    adapter_id: AdapterId = Field(alias="adapterId")
    code: ErrorCode = Field(alias="code")
    message: str = Field(alias="message")


class AgentDiscoveryCompletedPayload(_Base):
    total: int = Field(alias="total")
    ready: int = Field(alias="ready")
    errors: list[AgentDiscoveryError] | None = Field(default=None, alias="errors")
    duration_ms: int | None = Field(default=None, alias="durationMs")


class CapabilityItem(_Base):
    id: CapabilityId = Field(alias="id")
    name: str = Field(alias="name")
    description: str | None = Field(default=None, alias="description")
    hard: bool = Field(alias="hard")
    source: Literal["detected", "user", "adapter"] = Field(alias="source")
    supported: bool | None = Field(default=None, alias="supported")
    note: str | None = Field(default=None, alias="note")


class BuiltinRoleId(StrEnum):
    """内置RoleId值。边界类型是 str，自定义值同样合法（裁决 D30）。"""

    ORCHESTRATOR = "orchestrator"
    ARCHITECT = "architect"
    FRONTEND_IMPLEMENTER = "frontend_implementer"
    GENERAL_IMPLEMENTER = "general_implementer"
    REVIEWER = "reviewer"
    TESTER = "tester"
    DEPLOYER = "deployer"
    INTEGRATOR = "integrator"
    ANALYST = "analyst"
    PLANNER = "planner"
    DEVELOPER = "developer"

RoleId = str


class AgentView(_Base):
    id: str = Field(alias="id")
    adapter_id: AdapterId = Field(alias="adapterId")
    display_name: str = Field(alias="displayName")
    version: str = Field(alias="version")
    status: AgentStatus = Field(alias="status")
    detected_at: Timestamp = Field(alias="detectedAt")
    capabilities: list[CapabilityItem] = Field(alias="capabilities")
    assigned_roles: list[RoleId] = Field(alias="assignedRoles")
    is_primary_for: list[RoleId] = Field(alias="isPrimaryFor")
    diagnostic_message: str | None = Field(default=None, alias="diagnosticMessage")
    auth_kind: AuthKind | None = Field(default=None, alias="authKind")
    executable_path: str | None = Field(default=None, alias="executablePath")
    minimum_version: str | None = Field(default=None, alias="minimumVersion")
    last_healthy_at: Timestamp | None = Field(default=None, alias="lastHealthyAt")


class AgentDiscoveryResult(_Base):
    discovered: list[AgentView] = Field(alias="discovered")
    total: int = Field(alias="total")
    timestamp: Timestamp = Field(alias="timestamp")
    errors: list[AgentDiscoveryError] | None = Field(default=None, alias="errors")
    duration_ms: int | None = Field(default=None, alias="durationMs")


class AgentFailedPayload(_Base):
    error_code: ErrorCode = Field(alias="errorCode")
    message: str = Field(alias="message")
    blockers: list[Blocker] | None = Field(default=None, alias="blockers")


class AgentProgressPayload(_Base):
    message: str = Field(alias="message")
    percent: int | None = Field(default=None, alias="percent")
    raw: dict[str, Any] | None = Field(default=None, alias="raw")


class AgentQuestionPayload(_Base):
    question_id: str = Field(alias="questionId")
    question: str = Field(alias="question")
    options: list[str] | None = Field(default=None, alias="options")
    expires_at: Timestamp | None = Field(default=None, alias="expiresAt")


class AgentSessionHandle(_Base):
    """start() 的返回值。Adapter 必须在此返回明确的外部会话 ID，Hub 据此写入 SessionView.externalSessionId。"""

    session_id: str = Field(alias="sessionId")
    external_session_id: str | None = Field(default=None, alias="externalSessionId")
    adapter_id: AdapterId = Field(alias="adapterId")
    started_at: Timestamp = Field(alias="startedAt")
    supports_resume: bool = Field(alias="supportsResume")
    working_directory: str | None = Field(default=None, alias="workingDirectory")


class SessionPurpose(StrEnum):
    ORCHESTRATE = "orchestrate"
    ARCHITECT = "architect"
    IMPLEMENT = "implement"
    REVIEW = "review"
    TEST = "test"
    DEPLOY = "deploy"
    INTEGRATE = "integrate"
    ADHOC = "adhoc"


class SessionReusePolicy(StrEnum):
    NEW_SESSION = "new_session"
    RESUME_EXPLICIT = "resume_explicit"
    CONTINUE_LINEAGE = "continue_lineage"


class AgentStartedPayload(_Base):
    session_id: str = Field(alias="sessionId")
    external_session_id: str | None = Field(default=None, alias="externalSessionId")
    purpose: SessionPurpose = Field(alias="purpose")
    reuse_policy: SessionReusePolicy = Field(alias="reusePolicy")
    worktree_path: str | None = Field(default=None, alias="worktreePath")
    branch: str | None = Field(default=None, alias="branch")


class DangerousAction(StrEnum):
    DEPLOY = "deploy"
    GIT_PUSH = "git_push"
    GIT_MERGE = "git_merge"
    DELETE = "delete"
    SHELL = "shell"
    NETWORK = "network"
    DB_MIGRATE = "db_migrate"


class AgentTaskSpec(_Base):
    """start() 的输入。对应施工方案 §8.1 的任务结构，字段名按 D11 转为 camelCase。"""

    session_id: str = Field(alias="sessionId")
    task_id: str = Field(alias="taskId")
    node_id: str = Field(alias="nodeId")
    workspace_id: str = Field(alias="workspaceId")
    role_id: RoleId = Field(alias="roleId")
    objective: str = Field(alias="objective")
    worktree_path: str | None = Field(default=None, alias="worktreePath")
    branch: str | None = Field(default=None, alias="branch")
    base_commit: str | None = Field(default=None, alias="baseCommit")
    allowed_paths: list[str] = Field(alias="allowedPaths")
    read_first: list[str] | None = Field(default=None, alias="readFirst")
    acceptance: list[str] | None = Field(default=None, alias="acceptance")
    requires_approval: list[DangerousAction] | None = Field(default=None, alias="requiresApproval")
    session_purpose: SessionPurpose = Field(alias="sessionPurpose")
    reuse_policy: SessionReusePolicy = Field(alias="reusePolicy")
    resume_session_id: str | None = Field(default=None, alias="resumeSessionId")
    handoff_documents: list[str] | None = Field(default=None, alias="handoffDocuments")
    timeout_seconds: int | None = Field(default=None, alias="timeoutSeconds")
    read_only: bool | None = Field(default=None, alias="readOnly")
    model_id_: str | None = Field(default=None, alias="modelId")
    reasoning_effort: str | None = Field(default=None, alias="reasoningEffort")
    role_instructions: str | None = Field(default=None, alias="roleInstructions")


class AgentToolCallPayload(_Base):
    tool_name: str = Field(alias="toolName")
    arguments_excerpt: str | None = Field(default=None, alias="argumentsExcerpt")
    result_summary: str | None = Field(default=None, alias="resultSummary")
    duration_ms: int | None = Field(default=None, alias="durationMs")
    failed: bool | None = Field(default=None, alias="failed")


class AggregateType(StrEnum):
    AGENT = "agent"
    TASK = "task"
    SESSION = "session"
    APPROVAL = "approval"
    UPDATE = "update"
    SYSTEM = "system"


class ApiError(_Base):
    code: ErrorCode = Field(alias="code")
    message: str = Field(alias="message")
    detail: dict[str, Any] | None = Field(default=None, alias="detail")
    retryable: bool = Field(alias="retryable")


ProtocolVersion = str


class ApiEnvelope(_Base):
    success: bool = Field(alias="success")
    data: Any | None = Field(default=None, alias="data")
    error: ApiError | None = Field(default=None, alias="error")
    request_id: str = Field(alias="requestId")
    protocol_version: ProtocolVersion = Field(alias="protocolVersion")


class ContrastMode(StrEnum):
    NORMAL = "normal"
    HIGH = "high"


FontScale = Literal[0.9, 1, 1.1, 1.2]


class ReduceMotion(StrEnum):
    SYSTEM = "system"
    ON = "on"
    OFF = "off"


class ThemeMode(StrEnum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


class ThemePalette(StrEnum):
    HQ_BLUE = "hq-blue"
    AI_VIOLET = "ai-violet"
    TECH_CYAN = "tech-cyan"
    OPS_EMERALD = "ops-emerald"


class UiDensity(StrEnum):
    COMFORTABLE = "comfortable"
    COMPACT = "compact"


class AppearanceSettings(_Base):
    mode: ThemeMode = Field(alias="mode")
    palette: ThemePalette = Field(alias="palette")
    density: UiDensity = Field(alias="density")
    contrast: ContrastMode = Field(alias="contrast")
    reduce_motion: ReduceMotion = Field(alias="reduceMotion")
    font_scale: FontScale = Field(alias="fontScale")


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ApprovalDispatch(_Base):
    """approve() 的输入。Hub 是审批时效的唯一权威——Adapter 不得自行判定过期后放行。"""

    approval_id: str = Field(alias="approvalId")
    external_request_id: str | None = Field(default=None, alias="externalRequestId")
    decision: ApprovalDecision = Field(alias="decision")
    reason: str | None = Field(default=None, alias="reason")
    decided_at: Timestamp = Field(alias="decidedAt")


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalQuery(_Base):
    status: ApprovalStatus | None = Field(default=None, alias="status")
    task_id: str | None = Field(default=None, alias="taskId")


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalRequiredPayload(_Base):
    approval_id: str = Field(alias="approvalId")
    action: DangerousAction = Field(alias="action")
    target_resource: str = Field(alias="targetResource")
    risk_level: RiskLevel = Field(alias="riskLevel")
    expires_at: Timestamp | None = Field(default=None, alias="expiresAt")
    external_request_id: str | None = Field(default=None, alias="externalRequestId")


class ApprovalResolvedPayload(_Base):
    approval_id: str = Field(alias="approvalId")
    decision: ApprovalDecision = Field(alias="decision")
    reason: str | None = Field(default=None, alias="reason")
    decided_at: Timestamp = Field(alias="decidedAt")


class ApprovalResponseInput(_Base):
    decision: ApprovalDecision = Field(alias="decision")
    reason: str | None = Field(default=None, alias="reason")


class ApprovalView(_Base):
    id: str = Field(alias="id")
    task_id: str = Field(alias="taskId")
    task_objective: str = Field(alias="taskObjective")
    node_id: str | None = Field(default=None, alias="nodeId")
    request_agent_id: str = Field(alias="requestAgentId")
    request_agent_name: str = Field(alias="requestAgentName")
    role_id: RoleId | None = Field(default=None, alias="roleId")
    action: DangerousAction = Field(alias="action")
    target_resource: str = Field(alias="targetResource")
    risk_level: RiskLevel = Field(alias="riskLevel")
    status: ApprovalStatus = Field(alias="status")
    requested_at: Timestamp = Field(alias="requestedAt")
    decided_at: Timestamp | None = Field(default=None, alias="decidedAt")
    decision: ApprovalDecision | None = Field(default=None, alias="decision")
    reason: str | None = Field(default=None, alias="reason")
    expires_at: Timestamp | None = Field(default=None, alias="expiresAt")
    details: dict[str, Any] | None = Field(default=None, alias="details")


class BootstrapAgentsSummary(_Base):
    total: int = Field(alias="total")
    ready: int = Field(alias="ready")
    issues: int = Field(alias="issues")
    last_discovery_at: Timestamp | None = Field(default=None, alias="lastDiscoveryAt")


class UpdatePhase(StrEnum):
    IDLE = "idle"
    CHECKING = "checking"
    UP_TO_DATE = "up_to_date"
    AVAILABLE = "available"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    VERIFYING = "verifying"
    READY_TO_INSTALL = "ready_to_install"
    DRAINING_TASKS = "draining_tasks"
    WAITING_USER = "waiting_user"
    INSTALLING = "installing"
    HEALTH_CHECKING = "health_checking"
    SUCCEEDED = "succeeded"
    ROLLING_BACK = "rolling_back"
    ROLLBACK_SUCCEEDED = "rollback_succeeded"
    ROLLBACK_FAILED = "rollback_failed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class BootstrapUpdateSummary(_Base):
    phase: UpdatePhase = Field(alias="phase")
    has_update: bool = Field(alias="hasUpdate")
    current_version: str = Field(alias="currentVersion")
    latest_version: str | None = Field(default=None, alias="latestVersion")
    mandatory: bool | None = Field(default=None, alias="mandatory")
    unacknowledged_result: bool | None = Field(default=None, alias="unacknowledgedResult")


class FeatureState(_Base):
    available: bool = Field(alias="available")
    reason: str | None = Field(default=None, alias="reason")


class FeatureAvailability(_Base):
    """分阶段交付期间，未就绪的工作包必须在这里明确报 unavailable 并给原因。前端据此禁用入口并显示说明，不允许用空列表伪装成「功能可用但没数据」——那会让集成期的问题晚好几天才暴露"""

    agents: FeatureState = Field(alias="agents")
    team_profiles: FeatureState = Field(alias="teamProfiles")
    tasks: FeatureState = Field(alias="tasks")
    sessions: FeatureState = Field(alias="sessions")
    approvals: FeatureState = Field(alias="approvals")
    updates: FeatureState = Field(alias="updates")


class Vcs(StrEnum):
    GIT = "git"
    NONE = "none"


class WorkspaceCapabilityView(_Base):
    """工作区当前能承接什么任务（裁决 D38）。非 Git 目录是合法工作区，但拿不到 worktree 隔离，因此只能派只读任务"""

    can_run_write_tasks: bool = Field(alias="canRunWriteTasks")
    reason: str | None = Field(default=None, alias="reason")
    can_init_git: bool | None = Field(default=None, alias="canInitGit")


class WorkspaceView(_Base):
    id: str = Field(alias="id")
    name: str = Field(alias="name")
    path: str = Field(alias="path")
    vcs: Vcs = Field(alias="vcs")
    branch: str | None = Field(default=None, alias="branch")
    is_clean: bool | None = Field(default=None, alias="isClean")
    default_profile_id: str | None = Field(default=None, alias="defaultProfileId")
    last_opened_at: Timestamp = Field(alias="lastOpenedAt")
    capabilities: WorkspaceCapabilityView | None = Field(default=None, alias="capabilities")
    memory_dir_present: bool | None = Field(default=None, alias="memoryDirPresent")


class BootstrapView(_Base):
    protocol_version: ProtocolVersion = Field(alias="protocolVersion")
    app_version: str = Field(alias="appVersion")
    environment: Literal["production", "development", "test"] = Field(alias="environment")
    maintenance: bool = Field(alias="maintenance")
    appearance: AppearanceSettings = Field(alias="appearance")
    agents: BootstrapAgentsSummary = Field(alias="agents")
    default_profile_id: str | None = Field(default=None, alias="defaultProfileId")
    current_workspace: WorkspaceView | None = Field(default=None, alias="currentWorkspace")
    workspace_count: int = Field(alias="workspaceCount")
    active_tasks_count: int = Field(alias="activeTasksCount")
    pending_approvals_count: int = Field(alias="pendingApprovalsCount")
    update: BootstrapUpdateSummary = Field(alias="update")
    features: FeatureAvailability = Field(alias="features")
    instance_id: str | None = Field(default=None, alias="instanceId")
    last_event_seq: int = Field(alias="lastEventSeq")
    hub_started_at: Timestamp = Field(alias="hubStartedAt")


class CancelMode(StrEnum):
    GRACEFUL = "graceful"
    FORCE = "force"


class CancelOutcome(StrEnum):
    STOPPED_GRACEFULLY = "stopped_gracefully"
    FORCE_KILLED = "force_killed"
    ALREADY_FINISHED = "already_finished"
    NOT_FOUND = "not_found"
    REFUSED = "refused"


class CancelRequest(_Base):
    session_id: str = Field(alias="sessionId")
    mode: CancelMode = Field(alias="mode")
    reason: str | None = Field(default=None, alias="reason")
    grace_seconds: int | None = Field(default=None, alias="graceSeconds")


class CancelResult(_Base):
    outcome: CancelOutcome = Field(alias="outcome")
    completed_at: Timestamp = Field(alias="completedAt")
    elapsed_ms: int | None = Field(default=None, alias="elapsedMs")
    detail: str | None = Field(default=None, alias="detail")
    orphan_process_ids: list[int] | None = Field(default=None, alias="orphanProcessIds")


class ConnectionSettings(_Base):
    hub_url: str = Field(alias="hubUrl")
    cloud_enabled: bool = Field(alias="cloudEnabled")
    device_name: str = Field(alias="deviceName")


class LocalSceneId(StrEnum):
    ANALYZE = "analyze"
    PLAN = "plan"
    DEVELOP = "develop"


class CreateLocalConversationInput(_Base):
    title: str = Field(alias="title")
    workspace_id: str = Field(alias="workspaceId")
    scene_id: LocalSceneId = Field(alias="sceneId")


class RoleExecutionOptions(_Base):
    model_id_: str | None = Field(default=None, alias="modelId")
    reasoning_effort: str | None = Field(default=None, alias="reasoningEffort")
    instructions: str | None = Field(default=None, alias="instructions")


class TaskSource(StrEnum):
    DESKTOP = "desktop"
    PWA = "pwa"
    SCHEDULER = "scheduler"
    CLI = "cli"


class CreateTaskInput(_Base):
    objective: str = Field(alias="objective")
    workspace_id: str = Field(alias="workspaceId")
    profile_id: str | None = Field(default=None, alias="profileId")
    source: TaskSource | None = Field(default=None, alias="source")
    role_overrides: dict[str, str] | None = Field(default=None, alias="roleOverrides")
    parent_task_id: str | None = Field(default=None, alias="parentTaskId")
    allowed_paths: list[str] | None = Field(default=None, alias="allowedPaths")
    read_first: list[str] | None = Field(default=None, alias="readFirst")
    acceptance: list[str] | None = Field(default=None, alias="acceptance")
    requires_approval: list[DangerousAction] | None = Field(default=None, alias="requiresApproval")
    workflow_roles: list[str] | None = Field(default=None, alias="workflowRoles")
    role_executions: dict[str, RoleExecutionOptions] | None = Field(default=None, alias="roleExecutions")
    resume_sessions: dict[str, str] | None = Field(default=None, alias="resumeSessions")


class DrainStep(StrEnum):
    STOP_ACCEPTING = "stop_accepting"
    SAVE_SESSIONS = "save_sessions"
    WAIT_RUNNING_TASKS = "wait_running_tasks"
    BACKUP_DATA = "backup_data"
    READY = "ready"


class ProcessDescriptor(_Base):
    component: Literal["desktop", "core", "update-agent", "agent-worker"] = Field(alias="component")
    pid: int = Field(alias="pid")
    name: str | None = Field(default=None, alias="name")


class DrainProgress(_Base):
    wait_pids: list[ProcessDescriptor] | None = Field(default=None, alias="waitPids")
    backup_completed: bool | None = Field(default=None, alias="backupCompleted")
    step: DrainStep = Field(alias="step")
    active_tasks_remaining: int = Field(alias="activeTasksRemaining")
    percent: int = Field(alias="percent")
    started_at: Timestamp | None = Field(default=None, alias="startedAt")
    timeout_at: Timestamp | None = Field(default=None, alias="timeoutAt")
    waiting_task_ids: list[str] | None = Field(default=None, alias="waitingTaskIds")


class HubEvent(_Base):
    event_id: str = Field(alias="eventId")
    seq: int = Field(alias="seq")
    occurred_at: Timestamp = Field(alias="occurredAt")
    aggregate_type: AggregateType = Field(alias="aggregateType")
    aggregate_id: str = Field(alias="aggregateId")
    type: str = Field(alias="type")
    payload: Any = Field(alias="payload")
    protocol_version: ProtocolVersion = Field(alias="protocolVersion")
    task_id: str | None = Field(default=None, alias="taskId")
    node_id: str | None = Field(default=None, alias="nodeId")
    role_id: RoleId | None = Field(default=None, alias="roleId")
    agent_instance_id: str | None = Field(default=None, alias="agentInstanceId")
    adapter_id: AdapterId | None = Field(default=None, alias="adapterId")


class EventPage(_Base):
    events: list[HubEvent] = Field(alias="events")
    last_seq: int = Field(alias="lastSeq")
    has_more: bool = Field(alias="hasMore")


class FilesystemAccess(StrEnum):
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


class Language(StrEnum):
    ZH_CN = "zh-CN"
    EN_US = "en-US"


class GeneralSettings(_Base):
    language: Language = Field(alias="language")
    launch_at_login: bool = Field(alias="launchAtLogin")
    minimize_to_tray: bool = Field(alias="minimizeToTray")
    close_to_tray: bool = Field(alias="closeToTray")


class HealthCheckOutcome(_Base):
    type: Literal["process", "http", "protocol", "database"] = Field(alias="type")
    component: str | None = Field(default=None, alias="component")
    passed: bool = Field(alias="passed")
    detail: str | None = Field(default=None, alias="detail")
    duration_ms: int | None = Field(default=None, alias="durationMs")


class HealthView(_Base):
    """GET /healthz 的返回。这是唯一免鉴权的端点：Update Plan v2 的 healthChecks 要在没有 token 的情况下探活。只返回非敏感信息"""

    status: Literal["ok", "starting", "maintenance", "degraded"] = Field(alias="status")
    app_version: str = Field(alias="appVersion")
    protocol_version: ProtocolVersion = Field(alias="protocolVersion")
    pid: int = Field(alias="pid")
    started_at: Timestamp = Field(alias="startedAt")


class HubRuntimeDescriptor(_Base):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    instance_id: str = Field(alias="instanceId")
    port: int = Field(alias="port")
    token: str = Field(alias="token")
    pid: int = Field(alias="pid")
    base_url: str = Field(alias="baseUrl")
    app_version: str = Field(alias="appVersion")
    protocol_version: ProtocolVersion = Field(alias="protocolVersion")
    started_at: Timestamp = Field(alias="startedAt")


class InstallStrategy(StrEnum):
    WINDOWS_NSIS = "windows-nsis"
    WINDOWS_MSI = "windows-msi"
    WINDOWS_PORTABLE = "windows-portable"
    MACOS_APP_BUNDLE = "macos-app-bundle"
    LINUX_APPIMAGE = "linux-appimage"
    LINUX_DEB = "linux-deb"


class LocalAgentModel(_Base):
    id: str = Field(alias="id")
    name: str = Field(alias="name")
    efforts: list[str] = Field(alias="efforts")
    is_default: bool = Field(alias="isDefault")


class LocalAgentModelsView(_Base):
    agent_instance_id: str = Field(alias="agentInstanceId")
    models: list[LocalAgentModel] = Field(alias="models")
    verified: bool = Field(alias="verified")
    reason: str | None = Field(default=None, alias="reason")


class LocalAuthInput(_Base):
    code: str = Field(alias="code")


class LocalAuthView(_Base):
    authenticated: bool = Field(alias="authenticated")
    protocol_version: str = Field(alias="protocolVersion")


class LocalConversationView(_Base):
    id: str = Field(alias="id")
    title: str = Field(alias="title")
    workspace_id: str = Field(alias="workspaceId")
    scene_id: LocalSceneId = Field(alias="sceneId")
    created_at: Timestamp = Field(alias="createdAt")
    updated_at: Timestamp = Field(alias="updatedAt")
    active_run_id: str | None = Field(default=None, alias="activeRunId")
    last_run_id: str | None = Field(default=None, alias="lastRunId")


class LocalEventPage(_Base):
    events: list[HubEvent] = Field(alias="events")
    next_seq: int = Field(alias="nextSeq")
    has_more: bool = Field(alias="hasMore")


class LocalMessageReceipt(_Base):
    command_id: str = Field(alias="commandId")
    conversation_id: str = Field(alias="conversationId")
    message_id: str = Field(alias="messageId")
    run_id: str = Field(alias="runId")
    status: Literal["queued", "accepted"] = Field(alias="status")
    duplicate: bool = Field(alias="duplicate")


class LocalMessageView(_Base):
    id: str = Field(alias="id")
    conversation_id: str = Field(alias="conversationId")
    sequence: int = Field(alias="sequence")
    role: Literal["user", "assistant", "system"] = Field(alias="role")
    text: str = Field(alias="text")
    run_id: str | None = Field(default=None, alias="runId")
    created_at: Timestamp = Field(alias="createdAt")


class LocalRoleConfig(_Base):
    role_id: str = Field(alias="roleId")
    agent_instance_id: str = Field(alias="agentInstanceId")
    instructions: str = Field(alias="instructions")
    model_id_: str | None = Field(default=None, alias="modelId")
    reasoning_effort: str | None = Field(default=None, alias="reasoningEffort")
    enabled: bool = Field(alias="enabled")


class LocalSceneView(_Base):
    id: LocalSceneId = Field(alias="id")
    name: str = Field(alias="name")
    description: str = Field(alias="description")
    read_only: bool = Field(alias="readOnly")
    version: int = Field(alias="version")
    roles: list[LocalRoleConfig] = Field(alias="roles")
    updated_at: Timestamp = Field(alias="updatedAt")


class TaskArtifactView(_Base):
    id: str = Field(alias="id")
    task_id: str = Field(alias="taskId")
    title: str = Field(alias="title")
    path: str = Field(alias="path")
    type: Literal["file", "diff", "report", "log"] = Field(alias="type")
    size_bytes: int = Field(alias="sizeBytes")
    created_at: Timestamp = Field(alias="createdAt")


class NodeStatus(StrEnum):
    PENDING = "pending"
    RESOLVING = "resolving"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class ResolveSource(StrEnum):
    TASK_OVERRIDE = "task_override"
    WORKSPACE_PROFILE = "workspace_profile"
    GLOBAL_PROFILE = "global_profile"
    CAPABILITY_MATCH = "capability_match"
    FALLBACK = "fallback"
    MANUAL = "manual"


class TaskNodeView(_Base):
    id: str = Field(alias="id")
    task_id: str = Field(alias="taskId")
    role_id: RoleId = Field(alias="roleId")
    resolved_agent_id: str = Field(alias="resolvedAgentId")
    resolved_agent_name: str = Field(alias="resolvedAgentName")
    resolve_source: ResolveSource = Field(alias="resolveSource")
    status: NodeStatus = Field(alias="status")
    started_at: Timestamp | None = Field(default=None, alias="startedAt")
    completed_at: Timestamp | None = Field(default=None, alias="completedAt")
    output_summary: str | None = Field(default=None, alias="outputSummary")
    error: str | None = Field(default=None, alias="error")
    is_fallback: bool | None = Field(default=None, alias="isFallback")
    fallback_reason: str | None = Field(default=None, alias="fallbackReason")
    session_id: str | None = Field(default=None, alias="sessionId")
    external_session_id: str | None = Field(default=None, alias="externalSessionId")
    worktree_path: str | None = Field(default=None, alias="worktreePath")
    branch: str | None = Field(default=None, alias="branch")
    changed_files: list[str] | None = Field(default=None, alias="changedFiles")
    violation_paths: list[str] | None = Field(default=None, alias="violationPaths")


class TaskStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class TaskSummaryView(_Base):
    id: str = Field(alias="id")
    objective: str = Field(alias="objective")
    workspace_id: str = Field(alias="workspaceId")
    workspace_name: str = Field(alias="workspaceName")
    profile_id: str = Field(alias="profileId")
    profile_name: str = Field(alias="profileName")
    status: TaskStatus = Field(alias="status")
    source: TaskSource = Field(alias="source")
    created_at: Timestamp = Field(alias="createdAt")
    updated_at: Timestamp = Field(alias="updatedAt")
    duration_ms: int | None = Field(default=None, alias="durationMs")
    current_role: RoleId | None = Field(default=None, alias="currentRole")
    current_agent: str | None = Field(default=None, alias="currentAgent")
    pending_approval_id: str | None = Field(default=None, alias="pendingApprovalId")
    parent_task_id: str | None = Field(default=None, alias="parentTaskId")


class TaskDetailView(TaskSummaryView):
    nodes: list[TaskNodeView] = Field(alias="nodes")
    artifacts: list[TaskArtifactView] = Field(alias="artifacts")
    events: list[HubEvent] = Field(alias="events")
    worktree_path: str | None = Field(default=None, alias="worktreePath")
    branch: str | None = Field(default=None, alias="branch")
    failure_reason: str | None = Field(default=None, alias="failureReason")
    allowed_paths: list[str] | None = Field(default=None, alias="allowedPaths")
    read_first: list[str] | None = Field(default=None, alias="readFirst")
    acceptance: list[str] | None = Field(default=None, alias="acceptance")
    requires_approval: list[DangerousAction] | None = Field(default=None, alias="requiresApproval")
    result: AgentResult | None = Field(default=None, alias="result")
    last_event_seq: int | None = Field(default=None, alias="lastEventSeq")


class LocalRunView(_Base):
    id: str = Field(alias="id")
    conversation_id: str = Field(alias="conversationId")
    message_id: str = Field(alias="messageId")
    task_id: str = Field(alias="taskId")
    scene_snapshot: LocalSceneView = Field(alias="sceneSnapshot")
    status: TaskStatus = Field(alias="status")
    created_at: Timestamp = Field(alias="createdAt")
    updated_at: Timestamp = Field(alias="updatedAt")
    error: str | None = Field(default=None, alias="error")
    task: TaskDetailView | None = Field(default=None, alias="task")


class NodeResolvedPayload(_Base):
    role_id: RoleId = Field(alias="roleId")
    resolved_agent_id: str = Field(alias="resolvedAgentId")
    resolved_agent_name: str | None = Field(default=None, alias="resolvedAgentName")
    resolve_source: ResolveSource = Field(alias="resolveSource")
    is_fallback: bool = Field(alias="isFallback")
    fallback_reason: str | None = Field(default=None, alias="fallbackReason")
    missing_capabilities: list[CapabilityId] | None = Field(default=None, alias="missingCapabilities")


class PageResult(_Base):
    items: list[Any] = Field(alias="items")
    total: int = Field(alias="total")
    page: int = Field(alias="page")
    page_size: int = Field(alias="pageSize")
    has_more: bool = Field(alias="hasMore")


class PathViolationPayload(_Base):
    violation_paths: list[str] = Field(alias="violationPaths")
    allowed_paths: list[str] = Field(alias="allowedPaths")
    worktree_path: str | None = Field(default=None, alias="worktreePath")


class UpdateChannel(StrEnum):
    STABLE = "stable"
    BETA = "beta"


class ReleaseInfo(_Base):
    version: str = Field(alias="version")
    channel: UpdateChannel = Field(alias="channel")
    target_key: str = Field(alias="targetKey")
    published_at: Timestamp = Field(alias="publishedAt")
    size_bytes: int = Field(alias="sizeBytes")
    sha256: str = Field(alias="sha256")
    signature: str | None = Field(default=None, alias="signature")
    signature_algorithm: str | None = Field(default=None, alias="signatureAlgorithm")
    key_id: str | None = Field(default=None, alias="keyId")
    mandatory: bool = Field(alias="mandatory")
    minimum_supported_version: str | None = Field(default=None, alias="minimumSupportedVersion")
    release_notes: str | None = Field(default=None, alias="releaseNotes")
    install_strategy: InstallStrategy | None = Field(default=None, alias="installStrategy")
    rollback_compatible: bool | None = Field(default=None, alias="rollbackCompatible")


class ResolveTeamProfileInput(_Base):
    profile_id: str = Field(alias="profileId")
    workspace_id: str | None = Field(default=None, alias="workspaceId")
    task_objective: str | None = Field(default=None, alias="taskObjective")


class ResolvedRoleItem(_Base):
    role_id: RoleId = Field(alias="roleId")
    resolved_agent_id: str = Field(alias="resolvedAgentId")
    resolved_agent_name: str = Field(alias="resolvedAgentName")
    resolve_source: ResolveSource = Field(alias="resolveSource")
    is_fallback: bool = Field(alias="isFallback")
    fallback_reason: str | None = Field(default=None, alias="fallbackReason")
    missing_capabilities: list[CapabilityId] | None = Field(default=None, alias="missingCapabilities")


class ResolvedTeamGap(_Base):
    role_id: RoleId = Field(alias="roleId")
    reason: str = Field(alias="reason")
    missing_capabilities: list[CapabilityId] | None = Field(default=None, alias="missingCapabilities")


class ResolvedTeamView(_Base):
    profile_id: str = Field(alias="profileId")
    workspace_id: str | None = Field(default=None, alias="workspaceId")
    resolved_roles: dict[str, ResolvedRoleItem] = Field(alias="resolvedRoles")
    has_gaps: bool = Field(alias="hasGaps")
    gaps: list[ResolvedTeamGap] = Field(alias="gaps")
    resolved_at: Timestamp | None = Field(default=None, alias="resolvedAt")


class ResolvedThemeMode(StrEnum):
    LIGHT = "light"
    DARK = "dark"


class ResumeRequest(_Base):
    """resume() 的输入。只有用户显式继续、工作流显式声明复用，或任务传入 resumeSessionId 时才会走到这里。"""

    session_id: str = Field(alias="sessionId")
    external_session_id: str | None = Field(default=None, alias="externalSessionId")
    message: str = Field(alias="message")
    acceptance: list[str] | None = Field(default=None, alias="acceptance")
    task_spec: AgentTaskSpec | None = Field(default=None, alias="taskSpec")


class ResumeSessionInput(_Base):
    instruction: str = Field(alias="instruction")
    workspace_id: str | None = Field(default=None, alias="workspaceId")
    acceptance: list[str] | None = Field(default=None, alias="acceptance")


class RoleBindingConstraints(_Base):
    """用户对该角色的额外约束，只能收紧、不能放宽角色默认权限"""

    require_hard_capabilities: list[CapabilityId] | None = Field(default=None, alias="requireHardCapabilities")
    allow_shell: bool | None = Field(default=None, alias="allowShell")
    read_only_fs: bool | None = Field(default=None, alias="readOnlyFs")


class RolePermissions(_Base):
    """权限绑角色不绑品牌。换 Agent 后仍沿用同一角色权限（施工方案 §6.5）"""

    filesystem: FilesystemAccess = Field(alias="filesystem")
    shell: bool = Field(alias="shell")
    can_approve: bool = Field(alias="canApprove")
    can_merge: bool = Field(alias="canMerge")
    writable_paths: list[str] = Field(alias="writablePaths")
    requires_approval: list[DangerousAction] = Field(alias="requiresApproval")


class RoleBindingView(_Base):
    role_id: RoleId = Field(alias="roleId")
    role_name: str = Field(alias="roleName")
    primary_agent_id: str = Field(alias="primaryAgentId")
    fallback_agent_ids: list[str] = Field(alias="fallbackAgentIds")
    constraints: RoleBindingConstraints | None = Field(default=None, alias="constraints")
    permissions: RolePermissions | None = Field(default=None, alias="permissions")


class SaveLocalSceneInput(_Base):
    roles: list[LocalRoleConfig] = Field(alias="roles")
    expected_version: int = Field(alias="expectedVersion")


class TeamProfilePolicies(_Base):
    missing_agent_strategy: Literal["fallback_then_ask", "fallback_then_fail", "ask"] = Field(alias="missingAgentStrategy")
    allow_one_agent_multiple_roles: bool = Field(alias="allowOneAgentMultipleRoles")
    prefer_cross_agent_review: bool = Field(alias="preferCrossAgentReview")
    same_agent_review_strategy: Literal["isolated_session", "forbid"] = Field(alias="sameAgentReviewStrategy")


class SaveTeamProfileInput(_Base):
    id: str | None = Field(default=None, alias="id")
    name: str = Field(alias="name")
    description: str | None = Field(default=None, alias="description")
    scope: Literal["global", "workspace"] = Field(alias="scope")
    workspace_id: str | None = Field(default=None, alias="workspaceId")
    is_default: bool | None = Field(default=None, alias="isDefault")
    role_bindings: dict[str, RoleBindingView] = Field(alias="roleBindings")
    policies: TeamProfilePolicies | None = Field(default=None, alias="policies")


class SecuritySettings(_Base):
    require_approval_for_dangerous_actions: bool = Field(alias="requireApprovalForDangerousActions")
    allowed_paths_only: bool = Field(alias="allowedPathsOnly")
    approval_timeout_minutes: int | None = Field(default=None, alias="approvalTimeoutMinutes")


class SendLocalMessageInput(_Base):
    client_message_id: str = Field(alias="clientMessageId")
    text: str = Field(alias="text")
    session_mode: Literal["new", "continue"] = Field(alias="sessionMode")


class SessionQuery(_Base):
    workspace_id: str | None = Field(default=None, alias="workspaceId")
    agent_id: str | None = Field(default=None, alias="agentId")
    role_id: RoleId | None = Field(default=None, alias="roleId")
    task_id: str | None = Field(default=None, alias="taskId")
    purpose: SessionPurpose | None = Field(default=None, alias="purpose")
    only_valid: bool | None = Field(default=None, alias="onlyValid")
    search: str | None = Field(default=None, alias="search")
    page: int | None = Field(default=None, alias="page")
    page_size: int | None = Field(default=None, alias="pageSize")


class SessionStatus(StrEnum):
    ACTIVE = "active"
    IDLE = "idle"
    CLOSED = "closed"
    INVALID = "invalid"


class SessionView(_Base):
    id: str = Field(alias="id")
    status: SessionStatus = Field(alias="status")
    workspace_id: str = Field(alias="workspaceId")
    workspace_name: str = Field(alias="workspaceName")
    role_id: RoleId = Field(alias="roleId")
    agent_instance_id: str = Field(alias="agentInstanceId")
    agent_display_name: str = Field(alias="agentDisplayName")
    adapter_id: AdapterId | None = Field(default=None, alias="adapterId")
    external_session_id: str | None = Field(default=None, alias="externalSessionId")
    purpose: SessionPurpose = Field(alias="purpose")
    reuse_policy: SessionReusePolicy = Field(alias="reusePolicy")
    task_id: str | None = Field(default=None, alias="taskId")
    node_id: str | None = Field(default=None, alias="nodeId")
    parent_session_id: str | None = Field(default=None, alias="parentSessionId")
    root_task_id: str | None = Field(default=None, alias="rootTaskId")
    created_at: Timestamp = Field(alias="createdAt")
    last_used_at: Timestamp = Field(alias="lastUsedAt")
    is_valid: bool = Field(alias="isValid")
    summary: str | None = Field(default=None, alias="summary")
    turn_count: int | None = Field(default=None, alias="turnCount")


class SubscribeEventsInput(_Base):
    after_seq: int | None = Field(default=None, alias="afterSeq")
    aggregate_types: list[AggregateType] | None = Field(default=None, alias="aggregateTypes")
    task_id: str | None = Field(default=None, alias="taskId")


class SystemMaintenancePayload(_Base):
    active: bool = Field(alias="active")
    reason: str = Field(alias="reason")
    drain_progress: DrainProgress | None = Field(default=None, alias="drainProgress")


class TaskActionInput(_Base):
    action: Literal["pause", "resume", "cancel", "retry", "append_instruction"] = Field(alias="action")
    instruction: str | None = Field(default=None, alias="instruction")
    node_id: str | None = Field(default=None, alias="nodeId")


class TaskCreatedPayload(_Base):
    objective: str = Field(alias="objective")
    workspace_id: str = Field(alias="workspaceId")
    profile_id: str = Field(alias="profileId")
    source: TaskSource = Field(alias="source")
    parent_task_id: str | None = Field(default=None, alias="parentTaskId")


class TaskQuery(_Base):
    page: int | None = Field(default=None, alias="page")
    page_size: int | None = Field(default=None, alias="pageSize")
    status: TaskStatus | None = Field(default=None, alias="status")
    workspace_id: str | None = Field(default=None, alias="workspaceId")
    search: str | None = Field(default=None, alias="search")


class TaskStatusChangedPayload(_Base):
    from_: TaskStatus = Field(alias="from")
    to: TaskStatus = Field(alias="to")
    reason: str | None = Field(default=None, alias="reason")


class TeamProfileView(_Base):
    id: str = Field(alias="id")
    name: str = Field(alias="name")
    description: str | None = Field(default=None, alias="description")
    scope: Literal["global", "workspace"] = Field(alias="scope")
    workspace_id: str | None = Field(default=None, alias="workspaceId")
    is_default: bool = Field(alias="isDefault")
    role_bindings: dict[str, RoleBindingView] = Field(alias="roleBindings")
    policies: TeamProfilePolicies | None = Field(default=None, alias="policies")
    updated_at: Timestamp = Field(alias="updatedAt")


class TelemetrySettings(_Base):
    anonymous_telemetry: bool = Field(alias="anonymousTelemetry")


class UpdateActionInput(_Base):
    action: Literal["check", "download", "cancel", "install", "defer", "acknowledge"] = Field(alias="action")
    defer_minutes: int | None = Field(default=None, alias="deferMinutes")
    allow_task_cancellation: bool | None = Field(default=None, alias="allowTaskCancellation")


class UpdateAgentRuntimeDescriptor(_Base):
    """对应 update-agent.json。Update Agent 不向 Vue 暴露第二个 Base URL（裁决 D1）"""

    schema_version: Literal[1] = Field(alias="schemaVersion")
    instance_id: str = Field(alias="instanceId")
    port: int = Field(alias="port")
    token: str = Field(alias="token")
    pid: int = Field(alias="pid")
    base_url: str = Field(alias="baseUrl")
    agent_version: str = Field(alias="agentVersion")
    started_at: Timestamp = Field(alias="startedAt")


class UpdateResultView(_Base):
    schema_version: Literal[2] = Field(alias="schemaVersion")
    app_id: str = Field(alias="appId")
    from_version: str = Field(alias="fromVersion")
    to_version: str = Field(alias="toVersion")
    channel: UpdateChannel | None = Field(default=None, alias="channel")
    success: bool = Field(alias="success")
    finished_at: Timestamp = Field(alias="finishedAt")
    install_strategy: InstallStrategy | None = Field(default=None, alias="installStrategy")
    health_checks: list[HealthCheckOutcome] | None = Field(default=None, alias="healthChecks")
    health_check_passed: bool | None = Field(default=None, alias="healthCheckPassed")
    rolled_back: bool | None = Field(default=None, alias="rolledBack")
    rollback_succeeded: bool | None = Field(default=None, alias="rollbackSucceeded")
    restored_database_backup: str | None = Field(default=None, alias="restoredDatabaseBackup")
    error: str | None = Field(default=None, alias="error")
    error_code: ErrorCode | None = Field(default=None, alias="errorCode")
    acknowledged: bool = Field(alias="acknowledged")


class UpdateCompletedPayload(_Base):
    result: UpdateResultView = Field(alias="result")


class UpdateDownloadProgressPayload(_Base):
    download_bytes: int = Field(alias="downloadBytes")
    total_bytes: int = Field(alias="totalBytes")
    percent: float = Field(alias="percent")
    speed_bytes_per_second: int | None = Field(default=None, alias="speedBytesPerSecond")
    eta_seconds: int | None = Field(default=None, alias="etaSeconds")


class UpdateHealthCheckPayload(_Base):
    passed: bool = Field(alias="passed")
    checks: list[HealthCheckOutcome] = Field(alias="checks")


class UpdateRollbackPayload(_Base):
    reason: str = Field(alias="reason")
    succeeded: bool | None = Field(default=None, alias="succeeded")
    restored_database_backup: str | None = Field(default=None, alias="restoredDatabaseBackup")


class UpdateSettings(_Base):
    channel: UpdateChannel = Field(alias="channel")
    auto_check: bool = Field(alias="autoCheck")
    auto_download: bool = Field(alias="autoDownload")
    auto_install: bool | None = Field(default=None, alias="autoInstall")


class UpdateStateView(_Base):
    phase: UpdatePhase = Field(alias="phase")
    current_version: str = Field(alias="currentVersion")
    channel: UpdateChannel = Field(alias="channel")
    latest_version: str | None = Field(default=None, alias="latestVersion")
    target_key: str | None = Field(default=None, alias="targetKey")
    release_notes: str | None = Field(default=None, alias="releaseNotes")
    mandatory: bool | None = Field(default=None, alias="mandatory")
    download_progress: float | None = Field(default=None, alias="downloadProgress")
    download_bytes: int | None = Field(default=None, alias="downloadBytes")
    total_bytes: int | None = Field(default=None, alias="totalBytes")
    speed_bytes_per_second: int | None = Field(default=None, alias="speedBytesPerSecond")
    eta_seconds: int | None = Field(default=None, alias="etaSeconds")
    drain_progress: DrainProgress | None = Field(default=None, alias="drainProgress")
    can_install_now: bool = Field(alias="canInstallNow")
    deferred_until: Timestamp | None = Field(default=None, alias="deferredUntil")
    last_checked_at: Timestamp = Field(alias="lastCheckedAt")
    error: str | None = Field(default=None, alias="error")
    error_code: ErrorCode | None = Field(default=None, alias="errorCode")
    protocol_version: ProtocolVersion | None = Field(default=None, alias="protocolVersion")


class UpdateStateChangedPayload(_Base):
    state: UpdateStateView = Field(alias="state")
    previous_phase: UpdatePhase | None = Field(default=None, alias="previousPhase")


class UpdateVerificationCompletedPayload(_Base):
    passed: bool = Field(alias="passed")
    size_matched: bool = Field(alias="sizeMatched")
    sha256_matched: bool = Field(alias="sha256Matched")
    signature_valid: bool = Field(alias="signatureValid")
    key_id: str | None = Field(default=None, alias="keyId")
    error: str | None = Field(default=None, alias="error")


class UserSettingsView(_Base):
    appearance: AppearanceSettings = Field(alias="appearance")
    general: GeneralSettings = Field(alias="general")
    connection: ConnectionSettings = Field(alias="connection")
    security: SecuritySettings = Field(alias="security")
    updates: UpdateSettings = Field(alias="updates")
    telemetry: TelemetrySettings = Field(alias="telemetry")
    data_dir: str | None = Field(default=None, alias="dataDir")
    log_dir: str | None = Field(default=None, alias="logDir")
    app_version: str | None = Field(default=None, alias="appVersion")
    protocol_version: ProtocolVersion | None = Field(default=None, alias="protocolVersion")


class VendorEventMapping(_Base):
    """Adapter 必须声明的供应商事件到统一事件字典的映射表。事件字典已在 FZ-1 冻结（28 条），Adapter 不得新增事件类型。"""

    vendor_type: str = Field(alias="vendorType")
    unified_type: str = Field(alias="unifiedType")
    dropped: bool | None = Field(default=None, alias="dropped")
    note: str | None = Field(default=None, alias="note")


class WorkspaceQuery(_Base):
    search: str | None = Field(default=None, alias="search")
    limit: int | None = Field(default=None, alias="limit")


class WsTicket(_Base):
    ticket: str = Field(alias="ticket")
    expires_at: Timestamp = Field(alias="expiresAt")
    ttl_seconds: Literal[30] = Field(alias="ttlSeconds")


class WsTicketRequest(_Base):
    purpose: Literal["events"] | None = Field(default=None, alias="purpose")


ERROR_CATALOG: dict[str, dict[str, Any]] = {
    "BAD_REQUEST": {"http": 400, "retryable": False},
    "VALIDATION_FAILED": {"http": 422, "retryable": False},
    "UNAUTHORIZED": {"http": 401, "retryable": False},
    "ORIGIN_NOT_ALLOWED": {"http": 403, "retryable": False},
    "NOT_FOUND": {"http": 404, "retryable": False},
    "CONFLICT": {"http": 409, "retryable": False},
    "IDEMPOTENCY_MISMATCH": {"http": 409, "retryable": False},
    "PROTOCOL_VERSION_MISMATCH": {"http": 426, "retryable": False},
    "HUB_NOT_READY": {"http": 503, "retryable": True},
    "HUB_MAINTENANCE": {"http": 503, "retryable": True},
    "EVENT_CURSOR_EXPIRED": {"http": 410, "retryable": False},
    "FEATURE_UNAVAILABLE": {"http": 503, "retryable": True},
    "AGENT_NOT_FOUND": {"http": 404, "retryable": False},
    "AGENT_OFFLINE": {"http": 409, "retryable": True},
    "AGENT_NOT_LOGGED_IN": {"http": 409, "retryable": False},
    "AGENT_INCOMPATIBLE": {"http": 409, "retryable": False},
    "CAPABILITY_MISSING": {"http": 409, "retryable": False},
    "ROLE_UNRESOLVED": {"http": 409, "retryable": False},
    "SESSION_NOT_RESUMABLE": {"http": 409, "retryable": False},
    "TASK_NOT_CANCELLABLE": {"http": 409, "retryable": False},
    "TASK_ACTION_INVALID": {"http": 409, "retryable": False},
    "WORKTREE_BUSY": {"http": 409, "retryable": True},
    "PATH_NOT_ALLOWED": {"http": 403, "retryable": False},
    "APPROVAL_REQUIRED": {"http": 409, "retryable": False},
    "APPROVAL_EXPIRED": {"http": 410, "retryable": False},
    "APPROVAL_ALREADY_DECIDED": {"http": 409, "retryable": False},
    "UPDATE_NOT_AVAILABLE": {"http": 409, "retryable": False},
    "UPDATE_BUSY": {"http": 409, "retryable": True},
    "UPDATE_VERIFY_FAILED": {"http": 422, "retryable": False},
    "UPDATE_DRAIN_TIMEOUT": {"http": 409, "retryable": True},
    "INTERNAL": {"http": 500, "retryable": True},
}
