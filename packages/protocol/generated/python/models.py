"""此文件由 scripts/protocol/generate.py 生成，请勿手改。"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_serializer, model_validator

PROTOCOL_VERSION = "0.9.0"


class _Base(BaseModel):
    """边界 DTO 基类：线上字段是 camelCase，Python 侧用 snake_case 访问。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class _RemoteBase(_Base):
    """R1 wire DTOs: omitted optional fields are allowed; explicit null is opt-in."""

    @model_validator(mode="before")
    @classmethod
    def _check_wire_scalars(cls, value):
        if isinstance(value, dict):
            by_alias = {field.alias: field for field in cls.model_fields.values()}
            for key, item in value.items():
                field = by_alias.get(key) or cls.model_fields.get(key)
                if field is None:
                    continue
                rules = field.json_schema_extra or {}
                if item is None and not rules.get("wireNullable"):
                    raise ValueError(f"{key} must be omitted rather than null")
                if rules.get("wireType") == "boolean" and not isinstance(item, bool):
                    raise ValueError(f"{key} must be a boolean")
                if rules.get("wireType") == "integer" and (not isinstance(item, int) or isinstance(item, bool)):
                    raise ValueError(f"{key} must be an integer")
        return value

    @model_serializer(mode="wrap")
    def _serialize_wire(self, handler, info):
        data = handler(self)
        for name, field in type(self).model_fields.items():
            if not (field.json_schema_extra or {}).get("wireNullable") or getattr(self, name) is not None:
                continue
            if info.exclude and name in info.exclude:
                continue
            if info.include is not None and name not in info.include:
                continue
            if field.is_required() or name in self.model_fields_set:
                data[field.alias if info.by_alias else name] = None
        return data


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
    REMOTE_AUTH_REQUIRED = "REMOTE_AUTH_REQUIRED"
    REMOTE_CSRF_REJECTED = "REMOTE_CSRF_REJECTED"
    REMOTE_DEVICE_OFFLINE = "REMOTE_DEVICE_OFFLINE"
    REMOTE_DEVICE_REVOKED = "REMOTE_DEVICE_REVOKED"
    REMOTE_DEVICE_AUTH_FAILED = "REMOTE_DEVICE_AUTH_FAILED"
    REMOTE_PAIRING_EXPIRED = "REMOTE_PAIRING_EXPIRED"
    REMOTE_PAIRING_CONFLICT = "REMOTE_PAIRING_CONFLICT"
    REMOTE_PAIRING_INVALID = "REMOTE_PAIRING_INVALID"
    REMOTE_COMMAND_EXPIRED = "REMOTE_COMMAND_EXPIRED"
    REMOTE_COMMAND_WITHDRAWN = "REMOTE_COMMAND_WITHDRAWN"
    REMOTE_WITHDRAWAL_UNCONFIRMED = "REMOTE_WITHDRAWAL_UNCONFIRMED"
    REMOTE_STORE_CHANGED = "REMOTE_STORE_CHANGED"
    REMOTE_EPOCH_STALE = "REMOTE_EPOCH_STALE"
    REMOTE_PROTOCOL_UNSUPPORTED = "REMOTE_PROTOCOL_UNSUPPORTED"
    REMOTE_EVENT_CONFLICT = "REMOTE_EVENT_CONFLICT"
    REMOTE_ACK_CONFLICT = "REMOTE_ACK_CONFLICT"
    REMOTE_SEQUENCE_GAP = "REMOTE_SEQUENCE_GAP"
    REMOTE_APPROVAL_FORBIDDEN = "REMOTE_APPROVAL_FORBIDDEN"
    CONVERSATION_AUTHORITY_MISMATCH = "CONVERSATION_AUTHORITY_MISMATCH"
    REMOTE_TARGET_MISMATCH = "REMOTE_TARGET_MISMATCH"
    REMOTE_SCENE_VERSION_MISMATCH = "REMOTE_SCENE_VERSION_MISMATCH"
    REMOTE_CURSOR_EXPIRED = "REMOTE_CURSOR_EXPIRED"
    REMOTE_CURSOR_INVALID = "REMOTE_CURSOR_INVALID"
    REMOTE_RATE_LIMITED = "REMOTE_RATE_LIMITED"
    REMOTE_FRAME_TOO_LARGE = "REMOTE_FRAME_TOO_LARGE"
    REMOTE_WITHDRAWAL_TOO_LATE = "REMOTE_WITHDRAWAL_TOO_LATE"
    REMOTE_PAIRING_IN_PROGRESS = "REMOTE_PAIRING_IN_PROGRESS"
    REMOTE_SERVER_UNREACHABLE = "REMOTE_SERVER_UNREACHABLE"
    REMOTE_SERVER_ORIGIN_INVALID = "REMOTE_SERVER_ORIGIN_INVALID"
    REMOTE_CONVERSATION_BUSY = "REMOTE_CONVERSATION_BUSY"
    REMOTE_STATE_NOT_READY = "REMOTE_STATE_NOT_READY"
    REMOTE_SYNC_CONFLICT = "REMOTE_SYNC_CONFLICT"
    REMOTE_SYNC_DISABLED = "REMOTE_SYNC_DISABLED"
    REMOTE_DELIVERY_EXPIRED = "REMOTE_DELIVERY_EXPIRED"
    REMOTE_REVISION_REQUIRED = "REMOTE_REVISION_REQUIRED"
    REMOTE_SYNC_RESOURCE_LIMIT = "REMOTE_SYNC_RESOURCE_LIMIT"
    REMOTE_DEVICE_SUSPENDED = "REMOTE_DEVICE_SUSPENDED"
    REMOTE_API_TOKEN_INVALID = "REMOTE_API_TOKEN_INVALID"
    REMOTE_API_TOKEN_EXPIRED = "REMOTE_API_TOKEN_EXPIRED"
    REMOTE_API_TOKEN_SCOPE_INSUFFICIENT = "REMOTE_API_TOKEN_SCOPE_INSUFFICIENT"
    REMOTE_AUTH_AMBIGUOUS = "REMOTE_AUTH_AMBIGUOUS"
    REMOTE_QUERY_TIMEOUT = "REMOTE_QUERY_TIMEOUT"
    REMOTE_QUERY_TOO_LARGE = "REMOTE_QUERY_TOO_LARGE"
    NATIVE_SESSION_ACTIVE = "NATIVE_SESSION_ACTIVE"
    NATIVE_SESSION_UNSUPPORTED = "NATIVE_SESSION_UNSUPPORTED"
    NATIVE_SESSION_CHANGED = "NATIVE_SESSION_CHANGED"
    NATIVE_SESSION_WRITER_CONFLICT = "NATIVE_SESSION_WRITER_CONFLICT"
    REMOTE_ROOT_NOT_AUTHORIZED = "REMOTE_ROOT_NOT_AUTHORIZED"
    REMOTE_PATH_OUTSIDE_ROOT = "REMOTE_PATH_OUTSIDE_ROOT"
    REMOTE_DIRECTORY_CHANGED = "REMOTE_DIRECTORY_CHANGED"


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
    exit_code: int | None = Field(default=None, alias="exitCode")


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


LocalSceneId = str


class CreateLocalConversationInput(_Base):
    title: str = Field(alias="title")
    workspace_id: str = Field(alias="workspaceId")
    scene_id: LocalSceneId = Field(alias="sceneId")


class LocalBaseRoleId(StrEnum):
    ANALYST = "analyst"
    PLANNER = "planner"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"


class CreateLocalRoleTemplateInput(_Base):
    name: str = Field(alias="name")
    base_role_id: LocalBaseRoleId = Field(alias="baseRoleId")
    instructions: str = Field(alias="instructions")


class LocalRoleConfig(_Base):
    role_id: str = Field(alias="roleId")
    agent_instance_id: str = Field(alias="agentInstanceId")
    instructions: str = Field(alias="instructions")
    model_id_: str | None = Field(default=None, alias="modelId")
    reasoning_effort: str | None = Field(default=None, alias="reasoningEffort")
    enabled: bool = Field(alias="enabled")
    role_name: str | None = Field(default=None, alias="roleName")
    role_template_id: str | None = Field(default=None, alias="roleTemplateId")
    role_template_version: int | None = Field(default=None, alias="roleTemplateVersion")


class ReviewMode(StrEnum):
    INDEPENDENT = "independent"
    ORIGINAL_PLANNER = "original_planner"


class CreateLocalSceneInput(_Base):
    name: str = Field(alias="name")
    description: str | None = Field(default=None, alias="description")
    roles: list[LocalRoleConfig] = Field(alias="roles")
    review_mode: ReviewMode | None = Field(default=None, alias="reviewMode")


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
    review_mode: ReviewMode | None = Field(default=None, alias="reviewMode")


class DirectoryEntry(_RemoteBase):
    """Directories only; no files, full path, recursive children or raw error details."""

    name: str = Field(alias="name", min_length=1, max_length=255, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    is_git_repository: bool = Field(alias="isGitRepository", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    directory_token: str = Field(alias="directoryToken", min_length=16, max_length=4096, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class DirectoryListingInput(_RemoteBase):
    """Missing directoryToken selects root itself. No path input. Default limit 50. Opaque signed Worker tokens bind root/version/store/real directory identity."""

    root_id: str = Field(alias="rootId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    root_version: int = Field(alias="rootVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    directory_token: str | None = Field(default=None, alias="directoryToken", min_length=16, max_length=4096, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    cursor: str | None = Field(default=None, alias="cursor", min_length=16, max_length=4096, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    limit: int | None = Field(default=None, alias="limit", ge=1, le=100, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})


class DirectoryListingPage(_RemoteBase):
    """One directory level, <=100 entries, <=1MiB JSON. Cursor pins listing identity/order and expires in 15 minutes. Recheck real paths for each entry."""

    root_id: str = Field(alias="rootId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    root_version: int = Field(alias="rootVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    directory_token: str = Field(alias="directoryToken", min_length=16, max_length=4096, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    entries: list[DirectoryEntry] = Field(alias="entries", min_length=0, max_length=100, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    has_more: bool = Field(alias="hasMore", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    next_cursor: str | None = Field(default=None, alias="nextCursor", min_length=16, max_length=4096, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


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


class LocalAuthorizedRoot(_RemoteBase):
    root_id: str = Field(alias="rootId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    display_name: str = Field(alias="displayName", max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    path: str = Field(alias="path", min_length=1, max_length=4096, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    version: int = Field(alias="version", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})


class LocalAuthorizedRootInput(_RemoteBase):
    """Only authenticated local API. Existing IDs kept; new IDs allocated by computer. No UNC/device namespaces; canonical path required."""

    root_id: str | None = Field(default=None, alias="rootId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    display_name: str = Field(alias="displayName", min_length=1, max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    path: str = Field(alias="path", min_length=1, max_length=4096, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class LocalAuthorizedRootsInput(_RemoteBase):
    """Atomic replace with CAS. Removed root IDs never reused; changed grants invalidate selection tokens immediately."""

    expected_version: int = Field(alias="expectedVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    roots: list[LocalAuthorizedRootInput] = Field(alias="roots", min_length=0, max_length=32, json_schema_extra={'wireNullable': False, 'wireType': 'array'})


class LocalAuthorizedRootsView(_RemoteBase):
    """Default roots=[] and version=1. Roots can only be configured on this computer."""

    version: int = Field(alias="version", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    roots: list[LocalAuthorizedRoot] = Field(alias="roots", min_length=0, max_length=32, json_schema_extra={'wireNullable': False, 'wireType': 'array'})


class LocalConnectionCodeView(_Base):
    code: str = Field(alias="code")
    expires_in_seconds: int = Field(alias="expiresInSeconds")


class NativeActivity(StrEnum):
    UNKNOWN = "unknown"
    LIKELY_ACTIVE = "likely_active"
    CLOSED_CONFIRMED = "closed_confirmed"


class NativeActivityEvidence(_RemoteBase):
    """Unknown is read-only. Positive matching live process or post-confirmation changes invalidate confirmation; absence alone never proves closure."""

    activity: NativeActivity = Field(alias="activity", json_schema_extra={'wireNullable': False, 'wireType': None})
    observed_at: str = Field(alias="observedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    process_match: Literal["present", "absent", "unknown"] = Field(alias="processMatch", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    recently_modified: bool = Field(alias="recentlyModified", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    terminal_closed_confirmed_at: str | None = Field(default=None, alias="terminalClosedConfirmedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class NativeAgentType(StrEnum):
    CLAUDE = "claude"
    CODEX = "codex"


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


class LocalConversationView(_Base):
    """ Missing conversationKind means scenario (requires existing scene fields). Native requires agentType/nativeSessionId and omits scene fields; exact vendor session binding remains local."""

    id: str = Field(alias="id")
    title: str = Field(alias="title")
    workspace_id: str = Field(alias="workspaceId")
    scene_id: LocalSceneId | None = Field(default=None, alias="sceneId")
    created_at: Timestamp = Field(alias="createdAt")
    updated_at: Timestamp = Field(alias="updatedAt")
    active_run_id: str | None = Field(default=None, alias="activeRunId")
    last_run_id: str | None = Field(default=None, alias="lastRunId")
    version: int | None = Field(default=None, alias="version")
    archived: bool | None = Field(default=None, alias="archived")
    last_run_status: TaskStatus | None = Field(default=None, alias="lastRunStatus")
    authority: Literal["local", "remote"] | None = Field(default=None, alias="authority")
    visibility: Literal["both", "pc_only", "mobile_only"] | None = Field(default=None, alias="visibility")
    busy: bool | None = Field(default=None, alias="busy")
    busy_observed_at: str | None = Field(default=None, alias="busyObservedAt")
    conversation_kind: Literal["scenario", "native"] | None = Field(default=None, alias="conversationKind")
    agent_type: NativeAgentType | None = Field(default=None, alias="agentType")
    native_session_id: str | None = Field(default=None, alias="nativeSessionId")
    native_activity: NativeActivityEvidence | None = Field(default=None, alias="nativeActivity")
    native_source_revision: str | None = Field(default=None, alias="nativeSourceRevision")


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


class LocalRoleTemplateView(_Base):
    id: str = Field(alias="id")
    name: str = Field(alias="name")
    base_role_id: LocalBaseRoleId = Field(alias="baseRoleId")
    instructions: str = Field(alias="instructions")
    version: int = Field(alias="version")
    created_at: Timestamp = Field(alias="createdAt")
    updated_at: Timestamp = Field(alias="updatedAt")


class LocalSceneView(_Base):
    id: LocalSceneId = Field(alias="id")
    name: str = Field(alias="name")
    description: str = Field(alias="description")
    read_only: bool = Field(alias="readOnly")
    version: int = Field(alias="version")
    roles: list[LocalRoleConfig] = Field(alias="roles")
    updated_at: Timestamp = Field(alias="updatedAt")
    review_mode: ReviewMode | None = Field(default=None, alias="reviewMode")
    is_builtin: bool | None = Field(default=None, alias="isBuiltin")


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
    phase: Literal["execution", "acceptance"] | None = Field(default=None, alias="phase")
    review_verdict: Literal["passed", "changes_requested", "insufficient_evidence"] | None = Field(default=None, alias="reviewVerdict")
    review_source_node_id: str | None = Field(default=None, alias="reviewSourceNodeId")
    review_evidence_id: str | None = Field(default=None, alias="reviewEvidenceId")


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
    """Scenario retains sceneSnapshot. Native uses a single bound Runtime/Agent and omits sceneSnapshot; no invented scenario roles. Existing taskId remains execution Task identity."""

    id: str = Field(alias="id")
    conversation_id: str = Field(alias="conversationId")
    message_id: str = Field(alias="messageId")
    task_id: str = Field(alias="taskId")
    scene_snapshot: LocalSceneView | None = Field(default=None, alias="sceneSnapshot")
    status: TaskStatus = Field(alias="status")
    created_at: Timestamp = Field(alias="createdAt")
    updated_at: Timestamp = Field(alias="updatedAt")
    error: str | None = Field(default=None, alias="error")
    task: TaskDetailView | None = Field(default=None, alias="task")
    conversation_kind: Literal["scenario", "native"] | None = Field(default=None, alias="conversationKind")
    agent_type: NativeAgentType | None = Field(default=None, alias="agentType")


class NativeClosureConfirmation(_RemoteBase):
    """Server-generated from authenticated explicit user action, persisted by Worker at admission and bound to source revision. No caller-supplied owner ID."""

    confirmation_id: str = Field(alias="confirmationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    confirmed_at: str = Field(alias="confirmedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    request_id: str = Field(alias="requestId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    source_revision: str = Field(alias="sourceRevision", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    terminal_closed_confirmed: Literal[True] = Field(alias="terminalClosedConfirmed", json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})


class NativeContinuationConfirmationInput(_RemoteBase):
    """Explicit renewed attestation if imported conversation detects external changes. Never override positive live-process evidence."""

    terminal_closed_confirmed: Literal[True] = Field(alias="terminalClosedConfirmed", json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    source_revision: str = Field(alias="sourceRevision", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class NativeFormatStatus(StrEnum):
    READABLE = "readable"
    UNSUPPORTED = "unsupported"


class NativeFormatView(_RemoteBase):
    """readable requires a tested version/profile readerId. unsupported requires sanitized reason; never guess a format."""

    status: NativeFormatStatus = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': None})
    reader_id: str | None = Field(default=None, alias="readerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    cli_version: str | None = Field(default=None, alias="cliVersion", max_length=80, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    reason: str | None = Field(default=None, alias="reason", max_length=300, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class NativeImportPayload(_RemoteBase):
    native_session_id: str = Field(alias="nativeSessionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_index_version: int = Field(alias="expectedIndexVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    source_revision: str = Field(alias="sourceRevision", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    confirmation: NativeClosureConfirmation = Field(alias="confirmation", json_schema_extra={'wireNullable': False, 'wireType': None})


class NativeMessagePart(_RemoteBase):
    """Normalized/filtered content only. A large message may span pages, with stable hash and ID. No reasoning, instruction prompts, raw tool arguments/results or attachments."""

    message_id: str = Field(alias="messageId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    role: Literal["user", "assistant", "tool_summary"] = Field(alias="role", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    text: str = Field(alias="text", max_length=16000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str | None = Field(default=None, alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    segment_index: int = Field(alias="segmentIndex", ge=0, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    segment_count: int = Field(alias="segmentCount", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    total_utf8_bytes: int = Field(alias="totalUtf8Bytes", ge=0, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    content_sha256: str = Field(alias="contentSha256", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class NativeMessagePage(_RemoteBase):
    """Ephemeral page <=1MiB encoded UTF-8. Newest messages first, segments within a message ascending. Do not render an incomplete message. before continues exclusively after the last part in this order."""

    native_session_id: str = Field(alias="nativeSessionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    source_revision: str = Field(alias="sourceRevision", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    snapshot_cursor: str = Field(alias="snapshotCursor", min_length=16, max_length=4096, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    items: list[NativeMessagePart] = Field(alias="items", min_length=0, max_length=100, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    has_more: bool = Field(alias="hasMore", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    before: str | None = Field(default=None, alias="before", min_length=16, max_length=4096, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class NativeReadInput(_RemoteBase):
    """Exact Worker index ID; limit is message parts, default 50 at HTTP boundary. Snapshot cursor bound to file identity/immutable cut and 15-minute expiry. sourceRevision is optional: initial reads capture current source; before alone pins the older snapshot cut. If both are supplied they must match. Server must not substitute the latest index revision for a cursor-bound revision."""

    native_session_id: str = Field(alias="nativeSessionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    source_revision: str | None = Field(default=None, alias="sourceRevision", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    limit: int = Field(alias="limit", ge=1, le=100, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    before: str | None = Field(default=None, alias="before", min_length=16, max_length=4096, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class NativeSessionIndex(_RemoteBase):
    """Worker-local opaque index ID, not a path or fuzzy CLI ID. Exact vendor ID is kept in the local binding. Redact before title truncation. No body, tool arguments or process IDs in index."""

    native_session_id: str = Field(alias="nativeSessionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    workspace_id: str = Field(alias="workspaceId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    agent_type: NativeAgentType = Field(alias="agentType", json_schema_extra={'wireNullable': False, 'wireType': None})
    title: str = Field(alias="title", max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    updated_at: str = Field(alias="updatedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    index_version: int = Field(alias="indexVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    source_revision: str = Field(alias="sourceRevision", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    format: NativeFormatView = Field(alias="format", json_schema_extra={'wireNullable': False, 'wireType': None})
    activity: NativeActivityEvidence = Field(alias="activity", json_schema_extra={'wireNullable': False, 'wireType': None})


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


class PickLocalDirectoryInput(_Base):
    initial_path: str | None = Field(default=None, alias="initialPath")


class PickLocalDirectoryView(_Base):
    cancelled: bool = Field(alias="cancelled")
    selected_path: str | None = Field(default=None, alias="selectedPath")


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


class RemoteAccountView(_RemoteBase):
    """Current authenticated account only. No ownerId/accountId selector is exposed."""

    login_name: str = Field(alias="loginName", min_length=1, max_length=128, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    display_name: str = Field(alias="displayName", max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteAnonymousSession(_RemoteBase):
    authenticated: Literal[False] = Field(alias="authenticated", json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})


class RemoteApiTokenScope(StrEnum):
    DEVICES_READ = "devices:read"
    DEVICES_MANAGE = "devices:manage"
    DEVICES_DELETE = "devices:delete"

    @classmethod
    def model_validate(cls, value):
        from pydantic import TypeAdapter
        return TypeAdapter(cls).validate_python(value)

    def model_dump(self, **kwargs):
        return self.value


class RemoteApiTokenCreateInput(_RemoteBase):
    """Cookie only. Trimmed name nonempty. Omitted expiry=90 days, max365 days from first issuance; duplicate scope values rejected."""

    name: str = Field(alias="name", min_length=1, max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    scopes: list[RemoteApiTokenScope] = Field(alias="scopes", min_length=1, max_length=3, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    expires_at: str | None = Field(default=None, alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteApiTokenView(_RemoteBase):
    """Metadata only. Prefix is public selector, never any secret bytes. Revoked takes precedence over expired."""

    token_id: str = Field(alias="tokenId", min_length=28, max_length=28, pattern='^pat_[0-9a-f]{24}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    name: str = Field(alias="name", min_length=1, max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    token_prefix: str = Field(alias="tokenPrefix", min_length=32, max_length=32, pattern='^hqr_pat_[0-9a-f]{24}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    scopes: list[RemoteApiTokenScope] = Field(alias="scopes", min_length=1, max_length=3, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    last_used_at: str | None = Field(default=None, alias="lastUsedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    status: Literal["active", "expired", "revoked"] = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    revoked_at: str | None = Field(default=None, alias="revokedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteApiTokenIssueReplayView(_RemoteBase):
    """200 same intent replay; no secret recovery or second token issuance. If first response was lost, revoke then create using a new key."""

    token: RemoteApiTokenView = Field(alias="token", json_schema_extra={'wireNullable': False, 'wireType': None})
    secret_available: Literal[False] = Field(alias="secretAvailable", json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})


class RemoteApiTokenIssuedView(_RemoteBase):
    """201 first issuance only; never store this full response in an idempotency cache."""

    token: RemoteApiTokenView = Field(alias="token", json_schema_extra={'wireNullable': False, 'wireType': None})
    secret_available: Literal[True] = Field(alias="secretAvailable", json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    secret: str = Field(alias="secret", min_length=76, max_length=76, pattern='^hqr_pat_[0-9a-f]{24}_[A-Za-z0-9_-]{43}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteApiTokenPage(_RemoteBase):
    """Opaque owner/filter-scoped cursor; hasMore=true requires nextCursor."""

    items: list[RemoteApiTokenView] = Field(alias="items", max_length=100, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    has_more: bool = Field(alias="hasMore", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    next_cursor: str | None = Field(default=None, alias="nextCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteApiTokenRevocationView(_RemoteBase):
    token_id: str = Field(alias="tokenId", min_length=28, max_length=28, pattern='^pat_[0-9a-f]{24}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    revoked_at: str = Field(alias="revokedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    status: Literal["revoked"] = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteApprovalDecisionPayload(_RemoteBase):
    """Worker looks up current pending approval/action/policy locally. Browser and server cannot supply a lower risk/action classification."""

    run_id: str = Field(alias="runId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    approval_id: str = Field(alias="approvalId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    decision: ApprovalDecision = Field(alias="decision", json_schema_extra={'wireNullable': False, 'wireType': None})
    reason: str | None = Field(default=None, alias="reason", max_length=1000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteApprovalDecisionCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["approval.decide"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteApprovalDecisionPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteApprovalDecisionInput(_RemoteBase):
    """Only current owner. approve on blocked action is forbidden in R1; reject does not grant execution permission."""

    decision: ApprovalDecision = Field(alias="decision", json_schema_extra={'wireNullable': False, 'wireType': None})
    reason: str | None = Field(default=None, alias="reason", max_length=1000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteResultRef(_RemoteBase):
    """D40: runId is LocalRun, the user-visible control handle. executionTaskId is the current per-run kernel Task; not a long-lived business Task. No Attempt identity."""

    run_id: str = Field(alias="runId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    execution_task_id: str | None = Field(default=None, alias="executionTaskId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    node_id: str | None = Field(default=None, alias="nodeId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    session_id: str | None = Field(default=None, alias="sessionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    parent_execution_task_id: str | None = Field(default=None, alias="parentExecutionTaskId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteWire1ErrorCode(StrEnum):
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
    REMOTE_AUTH_REQUIRED = "REMOTE_AUTH_REQUIRED"
    REMOTE_CSRF_REJECTED = "REMOTE_CSRF_REJECTED"
    REMOTE_DEVICE_OFFLINE = "REMOTE_DEVICE_OFFLINE"
    REMOTE_DEVICE_REVOKED = "REMOTE_DEVICE_REVOKED"
    REMOTE_DEVICE_AUTH_FAILED = "REMOTE_DEVICE_AUTH_FAILED"
    REMOTE_PAIRING_EXPIRED = "REMOTE_PAIRING_EXPIRED"
    REMOTE_PAIRING_CONFLICT = "REMOTE_PAIRING_CONFLICT"
    REMOTE_PAIRING_INVALID = "REMOTE_PAIRING_INVALID"
    REMOTE_COMMAND_EXPIRED = "REMOTE_COMMAND_EXPIRED"
    REMOTE_COMMAND_WITHDRAWN = "REMOTE_COMMAND_WITHDRAWN"
    REMOTE_WITHDRAWAL_UNCONFIRMED = "REMOTE_WITHDRAWAL_UNCONFIRMED"
    REMOTE_STORE_CHANGED = "REMOTE_STORE_CHANGED"
    REMOTE_EPOCH_STALE = "REMOTE_EPOCH_STALE"
    REMOTE_PROTOCOL_UNSUPPORTED = "REMOTE_PROTOCOL_UNSUPPORTED"
    REMOTE_EVENT_CONFLICT = "REMOTE_EVENT_CONFLICT"
    REMOTE_ACK_CONFLICT = "REMOTE_ACK_CONFLICT"
    REMOTE_SEQUENCE_GAP = "REMOTE_SEQUENCE_GAP"
    REMOTE_APPROVAL_FORBIDDEN = "REMOTE_APPROVAL_FORBIDDEN"
    CONVERSATION_AUTHORITY_MISMATCH = "CONVERSATION_AUTHORITY_MISMATCH"
    REMOTE_TARGET_MISMATCH = "REMOTE_TARGET_MISMATCH"
    REMOTE_SCENE_VERSION_MISMATCH = "REMOTE_SCENE_VERSION_MISMATCH"
    REMOTE_CURSOR_EXPIRED = "REMOTE_CURSOR_EXPIRED"
    REMOTE_CURSOR_INVALID = "REMOTE_CURSOR_INVALID"
    REMOTE_RATE_LIMITED = "REMOTE_RATE_LIMITED"
    REMOTE_FRAME_TOO_LARGE = "REMOTE_FRAME_TOO_LARGE"
    REMOTE_WITHDRAWAL_TOO_LATE = "REMOTE_WITHDRAWAL_TOO_LATE"
    REMOTE_PAIRING_IN_PROGRESS = "REMOTE_PAIRING_IN_PROGRESS"
    REMOTE_SERVER_UNREACHABLE = "REMOTE_SERVER_UNREACHABLE"
    REMOTE_SERVER_ORIGIN_INVALID = "REMOTE_SERVER_ORIGIN_INVALID"

    @classmethod
    def model_validate(cls, value):
        from pydantic import TypeAdapter
        return TypeAdapter(cls).validate_python(value)

    def model_dump(self, **kwargs):
        return self.value


class RemoteWire1ApprovalView(_RemoteBase):
    """Local Worker policy is authoritative. Mandatory blocked actions are git_push/deploy/delete/db_migrate plus locally declared actions; refusal reason code REMOTE_APPROVAL_FORBIDDEN. Rejection of a dangerous action may still be submitted remotely."""

    approval_id: str = Field(alias="approvalId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_ref: RemoteResultRef = Field(alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})
    action: DangerousAction = Field(alias="action", json_schema_extra={'wireNullable': False, 'wireType': None})
    target_summary: str = Field(alias="targetSummary", max_length=2000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    risk_level: RiskLevel = Field(alias="riskLevel", json_schema_extra={'wireNullable': False, 'wireType': None})
    status: ApprovalStatus = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': None})
    requested_at: str = Field(alias="requestedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    remote_approval_allowed: bool = Field(alias="remoteApprovalAllowed", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    worker_policy_revision: int = Field(alias="workerPolicyRevision", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    denial_code: RemoteWire1ErrorCode | None = Field(default=None, alias="denialCode", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteApprovalEvent(_RemoteBase):
    type: Literal["approval.state_changed"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteWire1ApprovalView = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteApprovalView(_RemoteBase):
    """Local Worker policy is authoritative. Mandatory blocked actions are git_push/deploy/delete/db_migrate plus locally declared actions; refusal reason code REMOTE_APPROVAL_FORBIDDEN. Rejection of a dangerous action may still be submitted remotely."""

    approval_id: str = Field(alias="approvalId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_ref: RemoteResultRef = Field(alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})
    action: DangerousAction = Field(alias="action", json_schema_extra={'wireNullable': False, 'wireType': None})
    target_summary: str = Field(alias="targetSummary", max_length=2000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    risk_level: RiskLevel = Field(alias="riskLevel", json_schema_extra={'wireNullable': False, 'wireType': None})
    status: ApprovalStatus = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': None})
    requested_at: str = Field(alias="requestedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    remote_approval_allowed: bool = Field(alias="remoteApprovalAllowed", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    worker_policy_revision: int = Field(alias="workerPolicyRevision", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    denial_code: ErrorCode | None = Field(default=None, alias="denialCode", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteAuthenticatedSession(_RemoteBase):
    authenticated: Literal[True] = Field(alias="authenticated", json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    account: RemoteAccountView = Field(alias="account", json_schema_extra={'wireNullable': False, 'wireType': None})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    csrf_token: str = Field(alias="csrfToken", min_length=32, max_length=256, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteAuthorizedRoot(_RemoteBase):
    """Opaque local grant identity. Full absolute root path is never exported."""

    root_id: str = Field(alias="rootId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    display_name: str = Field(alias="displayName", max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    version: int = Field(alias="version", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})


class RemoteError(_RemoteBase):
    """Sanitized error. No credential, raw environment, owner locator or arbitrary detail object."""

    code: ErrorCode = Field(alias="code", json_schema_extra={'wireNullable': False, 'wireType': None})
    message: str = Field(alias="message", max_length=2000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    retryable: bool = Field(alias="retryable", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})


class RemoteResourceResultRef(_RemoteBase):
    """workspace.register requires workspaceId only; native.import requires workspaceId/conversationId/nativeSessionId. IDs local on wire, owner-scoped in HTTP. No fake Task or Run."""

    workspace_id: str | None = Field(default=None, alias="workspaceId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str | None = Field(default=None, alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    native_session_id: str | None = Field(default=None, alias="nativeSessionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteControlRejected(_RemoteBase):
    """D41: Worker-only structured evidence, never parsed error text. Empty orphanProcessIds is not proof of no remaining process. A paused process may still exist."""

    outcome: Literal["rejected"] = Field(alias="outcome", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    execution_may_still_be_running: bool = Field(alias="executionMayStillBeRunning", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    orphan_process_ids: list[Annotated[int, Field(strict=True, ge=1, le=4294967295)]] = Field(alias="orphanProcessIds", max_length=256, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    reason: str = Field(alias="reason", min_length=1, max_length=2000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    evidence: Literal["adapter_refused", "worker_policy", "already_terminal"] = Field(alias="evidence", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    observed_at: str = Field(alias="observedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteControlUnconfirmed(_RemoteBase):
    """D41: Worker-only structured evidence, never parsed error text. Empty orphanProcessIds is not proof of no remaining process. A paused process may still exist."""

    outcome: Literal["unconfirmed"] = Field(alias="outcome", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    execution_may_still_be_running: Literal[True] = Field(alias="executionMayStillBeRunning", json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    orphan_process_ids: list[Annotated[int, Field(strict=True, ge=1, le=4294967295)]] = Field(alias="orphanProcessIds", max_length=256, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    reason: str = Field(alias="reason", min_length=1, max_length=2000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    evidence: Literal["missing_execution_handle", "delivery_unknown", "recovery_flag", "supervisor_unconfirmed"] = Field(alias="evidence", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    observed_at: str = Field(alias="observedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2ControlConfirmed(_RemoteBase):
    """D41: Worker-only structured evidence, never parsed error text. Empty orphanProcessIds is not proof of no remaining process. A paused process may still exist."""

    outcome: Literal["confirmed"] = Field(alias="outcome", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    execution_may_still_be_running: bool = Field(alias="executionMayStillBeRunning", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    orphan_process_ids: list[Annotated[int, Field(strict=True, ge=1, le=4294967295)]] = Field(alias="orphanProcessIds", max_length=0, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    reason: str = Field(alias="reason", min_length=1, max_length=2000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    evidence: Literal["adapter_confirmed", "node_boundary_paused", "already_terminal", "retry_enqueued", "supervisor_resumed", "inbox_tombstone", "metadata_committed"] = Field(alias="evidence", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    observed_at: str = Field(alias="observedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2ControlResult(RootModel[RemoteV2ControlConfirmed | RemoteControlRejected | RemoteControlUnconfirmed]):
    pass


class RemoteCommandView(_RemoteBase):
    """Three layers must be displayed separately: transport/delivery, Worker controlResult, execution status from RemoteRunView. No inference from disconnected transport or command.completed to task success. Resource commands omit conversationId; resourceRef appears after Worker commit and contains mapped public IDs. Read through existing GET commands; no fabricated run/sequence."""

    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str | None = Field(default=None, alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    type: Literal["run.submit", "run.pause", "run.resume", "run.cancel", "run.retry", "approval.decide", "command.withdraw", "conversation.update", "conversation.create", "native.import", "workspace.register"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_seq: int | None = Field(default=None, alias="conversationSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    status: Literal["queued", "accepted", "rejected", "completed", "failed"] = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    delivery_state: Literal["queued_online", "queued_offline", "sent", "acknowledged", "reconciliation_required", "awaiting_receipt", "granted"] = Field(alias="deliveryState", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    withdrawal_state: Literal["none", "requested", "confirmed", "denied"] = Field(alias="withdrawalState", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_online: bool = Field(alias="workerOnline", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    observed_at: str = Field(alias="observedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_status: Literal["succeeded", "cancelled", "confirmed", "retry_enqueued", "approval_consumed", "withdrawn", "failed", "rejected"] | None = Field(default=None, alias="resultStatus", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_ref: RemoteResultRef | None = Field(default=None, alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})
    control_result: RemoteV2ControlResult | None = Field(default=None, alias="controlResult", json_schema_extra={'wireNullable': False, 'wireType': None})
    error: RemoteError | None = Field(default=None, alias="error", json_schema_extra={'wireNullable': False, 'wireType': None})
    withdrawal_command_id: str | None = Field(default=None, alias="withdrawalCommandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    deliver_by: str | None = Field(default=None, alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    resource_ref: RemoteResourceResultRef | None = Field(default=None, alias="resourceRef", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteBrowserCommandEvent(_RemoteBase):
    """Owner-scoped browser event; ordering/resume is only by opaque serverCursor, never by payload Worker seq."""

    type: Literal["command.updated"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    server_cursor: str = Field(alias="serverCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    recorded_at: str = Field(alias="recordedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteCommandView = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteBrowserConversationDeleted(_RemoteBase):
    type: Literal["conversation.deleted"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    server_cursor: str = Field(alias="serverCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    recorded_at: str = Field(alias="recordedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteConversationView(_RemoteBase):
    """Worker is the sole writer. authority is legacy metadata, never a write gate. Omitted visibility=both, busy=false, busyFresh=false; targetWorkerId is the legacy workerId alias. Missing conversationKind means scenario (requires existing scene fields). Native requires agentType/nativeSessionId and omits scene fields; exact vendor session binding remains local."""

    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    authority: Literal["local", "remote"] = Field(alias="authority", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    title: str = Field(alias="title", max_length=200, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    workspace_id: str = Field(alias="workspaceId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    scene_id: str | None = Field(default=None, alias="sceneId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    scene_version: int | None = Field(default=None, alias="sceneVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    updated_at: str = Field(alias="updatedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str | None = Field(default=None, alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    visibility: Literal["both", "pc_only", "mobile_only"] | None = Field(default=None, alias="visibility", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    busy: bool | None = Field(default=None, alias="busy", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    busy_observed_at: str | None = Field(default=None, alias="busyObservedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    busy_fresh: bool | None = Field(default=None, alias="busyFresh", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    last_activity_at: str | None = Field(default=None, alias="lastActivityAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    archived: bool | None = Field(default=None, alias="archived", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    metadata_version: int | None = Field(default=None, alias="metadataVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    conversation_kind: Literal["scenario", "native"] | None = Field(default=None, alias="conversationKind", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    agent_type: NativeAgentType | None = Field(default=None, alias="agentType", json_schema_extra={'wireNullable': False, 'wireType': None})
    native_session_id: str | None = Field(default=None, alias="nativeSessionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    native_activity: NativeActivityEvidence | None = Field(default=None, alias="nativeActivity", json_schema_extra={'wireNullable': False, 'wireType': None})
    native_source_revision: str | None = Field(default=None, alias="nativeSourceRevision", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteBrowserConversationEvent(_RemoteBase):
    """Owner-scoped browser event; ordering/resume is only by opaque serverCursor, never by payload Worker seq."""

    type: Literal["conversation.updated"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    server_cursor: str = Field(alias="serverCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    recorded_at: str = Field(alias="recordedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteConversationView = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteMessageView(_RemoteBase):
    message_id: str = Field(alias="messageId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    role: Literal["user", "assistant", "system"] = Field(alias="role", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    text: str = Field(alias="text", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str | None = Field(default=None, alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    run_id: str | None = Field(default=None, alias="runId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    message_sequence: int | None = Field(default=None, alias="messageSequence", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    message_revision: int | None = Field(default=None, alias="messageRevision", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})


class RemoteBrowserMessageEvent(_RemoteBase):
    """Owner-scoped browser event; ordering/resume is only by opaque serverCursor, never by payload Worker seq."""

    type: Literal["message.appended"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    server_cursor: str = Field(alias="serverCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    recorded_at: str = Field(alias="recordedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteMessageView = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteBrowserStoreReset(_RemoteBase):
    type: Literal["store.reset"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    server_cursor: str = Field(alias="serverCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    recorded_at: str = Field(alias="recordedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteWire2ErrorCode(StrEnum):
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
    REMOTE_AUTH_REQUIRED = "REMOTE_AUTH_REQUIRED"
    REMOTE_CSRF_REJECTED = "REMOTE_CSRF_REJECTED"
    REMOTE_DEVICE_OFFLINE = "REMOTE_DEVICE_OFFLINE"
    REMOTE_DEVICE_REVOKED = "REMOTE_DEVICE_REVOKED"
    REMOTE_DEVICE_AUTH_FAILED = "REMOTE_DEVICE_AUTH_FAILED"
    REMOTE_PAIRING_EXPIRED = "REMOTE_PAIRING_EXPIRED"
    REMOTE_PAIRING_CONFLICT = "REMOTE_PAIRING_CONFLICT"
    REMOTE_PAIRING_INVALID = "REMOTE_PAIRING_INVALID"
    REMOTE_COMMAND_EXPIRED = "REMOTE_COMMAND_EXPIRED"
    REMOTE_COMMAND_WITHDRAWN = "REMOTE_COMMAND_WITHDRAWN"
    REMOTE_WITHDRAWAL_UNCONFIRMED = "REMOTE_WITHDRAWAL_UNCONFIRMED"
    REMOTE_STORE_CHANGED = "REMOTE_STORE_CHANGED"
    REMOTE_EPOCH_STALE = "REMOTE_EPOCH_STALE"
    REMOTE_PROTOCOL_UNSUPPORTED = "REMOTE_PROTOCOL_UNSUPPORTED"
    REMOTE_EVENT_CONFLICT = "REMOTE_EVENT_CONFLICT"
    REMOTE_ACK_CONFLICT = "REMOTE_ACK_CONFLICT"
    REMOTE_SEQUENCE_GAP = "REMOTE_SEQUENCE_GAP"
    REMOTE_APPROVAL_FORBIDDEN = "REMOTE_APPROVAL_FORBIDDEN"
    CONVERSATION_AUTHORITY_MISMATCH = "CONVERSATION_AUTHORITY_MISMATCH"
    REMOTE_TARGET_MISMATCH = "REMOTE_TARGET_MISMATCH"
    REMOTE_SCENE_VERSION_MISMATCH = "REMOTE_SCENE_VERSION_MISMATCH"
    REMOTE_CURSOR_EXPIRED = "REMOTE_CURSOR_EXPIRED"
    REMOTE_CURSOR_INVALID = "REMOTE_CURSOR_INVALID"
    REMOTE_RATE_LIMITED = "REMOTE_RATE_LIMITED"
    REMOTE_FRAME_TOO_LARGE = "REMOTE_FRAME_TOO_LARGE"
    REMOTE_WITHDRAWAL_TOO_LATE = "REMOTE_WITHDRAWAL_TOO_LATE"
    REMOTE_PAIRING_IN_PROGRESS = "REMOTE_PAIRING_IN_PROGRESS"
    REMOTE_SERVER_UNREACHABLE = "REMOTE_SERVER_UNREACHABLE"
    REMOTE_SERVER_ORIGIN_INVALID = "REMOTE_SERVER_ORIGIN_INVALID"
    REMOTE_CONVERSATION_BUSY = "REMOTE_CONVERSATION_BUSY"
    REMOTE_STATE_NOT_READY = "REMOTE_STATE_NOT_READY"
    REMOTE_SYNC_CONFLICT = "REMOTE_SYNC_CONFLICT"
    REMOTE_SYNC_DISABLED = "REMOTE_SYNC_DISABLED"
    REMOTE_DELIVERY_EXPIRED = "REMOTE_DELIVERY_EXPIRED"
    REMOTE_REVISION_REQUIRED = "REMOTE_REVISION_REQUIRED"
    REMOTE_SYNC_RESOURCE_LIMIT = "REMOTE_SYNC_RESOURCE_LIMIT"

    @classmethod
    def model_validate(cls, value):
        from pydantic import TypeAdapter
        return TypeAdapter(cls).validate_python(value)

    def model_dump(self, **kwargs):
        return self.value


class RemoteWire2ApprovalView(_RemoteBase):
    """Local Worker policy is authoritative. Mandatory blocked actions are git_push/deploy/delete/db_migrate plus locally declared actions; refusal reason code REMOTE_APPROVAL_FORBIDDEN. Rejection of a dangerous action may still be submitted remotely."""

    approval_id: str = Field(alias="approvalId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_ref: RemoteResultRef = Field(alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})
    action: DangerousAction = Field(alias="action", json_schema_extra={'wireNullable': False, 'wireType': None})
    target_summary: str = Field(alias="targetSummary", max_length=2000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    risk_level: RiskLevel = Field(alias="riskLevel", json_schema_extra={'wireNullable': False, 'wireType': None})
    status: ApprovalStatus = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': None})
    requested_at: str = Field(alias="requestedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    remote_approval_allowed: bool = Field(alias="remoteApprovalAllowed", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    worker_policy_revision: int = Field(alias="workerPolicyRevision", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    denial_code: RemoteWire2ErrorCode | None = Field(default=None, alias="denialCode", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV2ApprovalEvent(_RemoteBase):
    type: Literal["approval.state_changed"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteWire2ApprovalView = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteSceneSummary(_RemoteBase):
    """Worker scene index only; model/provider credential or installation/subscription data is not relayed."""

    scene_id: str = Field(alias="sceneId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    name: str = Field(alias="name", max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    version: int = Field(alias="version", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    read_only: bool = Field(alias="readOnly", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})


class RemoteWorkspaceSummary(_RemoteBase):
    """Worker-exported registered workspace index. displayPath is display-only; no server filesystem path resolution or remote arbitrary folder execution."""

    workspace_id: str = Field(alias="workspaceId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    name: str = Field(alias="name", max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    display_path: str = Field(alias="displayPath", max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    vcs: Vcs = Field(alias="vcs", json_schema_extra={'wireNullable': False, 'wireType': None})
    can_write: bool = Field(alias="canWrite", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})


class RemoteCatalogView(_RemoteBase):
    """Atomic bounded complete catalog for R1. Reject oversized catalogs instead of truncating; offline entries are last observed, not proof that paths still exist."""

    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    capability_revision: int = Field(alias="capabilityRevision", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    observed_at: str = Field(alias="observedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    workspaces: list[RemoteWorkspaceSummary] = Field(alias="workspaces", max_length=1000, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    scenes: list[RemoteSceneSummary] = Field(alias="scenes", max_length=1000, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    remotely_blocked_actions: list[DangerousAction] = Field(alias="remotelyBlockedActions", max_length=32, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2CatalogEvent(_RemoteBase):
    type: Literal["capability.changed"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteCatalogView = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV2CommandAccepted(_RemoteBase):
    """Durable inbox admission, not model/execution success. Duplicate immutable commands return the original receipt/event."""

    type: Literal["command.accepted"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    received_at: str = Field(alias="receivedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    status: Literal["accepted"] = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_ref: RemoteResultRef | None = Field(default=None, alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV2CommandCompleted(_RemoteBase):
    """Not universally task success. Retry completes on durable new execution reference; execute completes on actual terminal Run success/cancellation. Cancel/pause/resume require confirmed structured control result."""

    type: Literal["command.completed"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_status: Literal["succeeded", "cancelled", "confirmed", "retry_enqueued", "approval_consumed", "withdrawn"] = Field(alias="resultStatus", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_ref: RemoteResultRef | None = Field(default=None, alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})
    control_result: RemoteV2ControlConfirmed | None = Field(default=None, alias="controlResult", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteWire2Error(_RemoteBase):
    """Sanitized error. No credential, raw environment, owner locator or arbitrary detail object."""

    code: RemoteWire2ErrorCode = Field(alias="code", json_schema_extra={'wireNullable': False, 'wireType': None})
    message: str = Field(alias="message", max_length=2000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    retryable: bool = Field(alias="retryable", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})


class RemoteV2CommandFailed(_RemoteBase):
    """Failure after admission. A refused control is distinct from unconfirmed cancellation; do not infer that an Agent process has stopped."""

    type: Literal["command.failed"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_status: Literal["failed", "rejected"] = Field(alias="resultStatus", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    error: RemoteWire2Error = Field(alias="error", json_schema_extra={'wireNullable': False, 'wireType': None})
    result_ref: RemoteResultRef | None = Field(default=None, alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})
    control_result: RemoteControlRejected | None = Field(default=None, alias="controlResult", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV2CommandRejected(_RemoteBase):
    """Pre-admission rejection only. An expired sequenced submit consumes its ordered slot without execution."""

    type: Literal["command.rejected"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    received_at: str = Field(alias="receivedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    status: Literal["rejected"] = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    error: RemoteWire2Error = Field(alias="error", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV2ControlObserved(_RemoteBase):
    """D41: unconfirmed leaves command accepted and pending reconciliation. Run-scoped controls include resultRef/executionStatus. Before a Run exists (withdrawal reconciliation), omit both rather than invent an identity or execution state."""

    type: Literal["command.control_result"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_ref: RemoteResultRef | None = Field(default=None, alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})
    control_result: RemoteV2ControlResult = Field(alias="controlResult", json_schema_extra={'wireNullable': False, 'wireType': None})
    execution_status: TaskStatus | None = Field(default=None, alias="executionStatus", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteWorkerMessagePayload(_RemoteBase):
    """Worker may emit assistant/system messages, never impersonate a user or allocate conversationSeq."""

    message_id: str = Field(alias="messageId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    role: Literal["assistant", "system"] = Field(alias="role", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    text: str = Field(alias="text", max_length=32000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str | None = Field(default=None, alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    run_id: str | None = Field(default=None, alias="runId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2MessageEvent(_RemoteBase):
    type: Literal["message.appended"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteWorkerMessagePayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV2ProgressEvent(_RemoteBase):
    """Sanitized observable progress only. Never private model reasoning, raw provider auth, full environment, or credential files."""

    type: Literal["run.progress"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_ref: RemoteResultRef = Field(alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})
    message: str = Field(alias="message", max_length=4000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteRunStatePayload(_RemoteBase):
    """Worker execution facts only. Server derives workerOnline for browser RemoteRunView; Worker cannot declare server transport liveness."""

    run_id: str = Field(alias="runId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    execution_task_id: str | None = Field(default=None, alias="executionTaskId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    status: TaskStatus = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': None})
    observed_at: str = Field(alias="observedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    summary: str | None = Field(default=None, alias="summary", max_length=16000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    parent_execution_task_id: str | None = Field(default=None, alias="parentExecutionTaskId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2RunStateEvent(_RemoteBase):
    """Worker creates/binds LocalRun and execution Task using existing semantics; it does not invent long-lived Task or retryOfRunId."""

    type: Literal["run.state_changed"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteRunStatePayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV2SkipRecorded(_RemoteBase):
    """Worker records ordered skip in the same durable inbox ordering ledger as submits."""

    type: Literal["conversation.skip_recorded"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_seq: int = Field(alias="conversationSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})


class RemoteV2ExecutionEvent(RootModel[RemoteV2CommandAccepted | RemoteV2CommandRejected | RemoteV2CommandCompleted | RemoteV2CommandFailed | RemoteV2ControlObserved | RemoteV2RunStateEvent | RemoteV2MessageEvent | RemoteV2ApprovalEvent | RemoteV2ProgressEvent | RemoteV2CatalogEvent | RemoteV2SkipRecorded]):
    pass


class RemoteBrowserV2WorkerEvent(_RemoteBase):
    """Owner-scoped browser event; ordering/resume is only by opaque serverCursor, never by payload Worker seq."""

    type: Literal["worker.event"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    server_cursor: str = Field(alias="serverCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    recorded_at: str = Field(alias="recordedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteV2ExecutionEvent = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteCatalogEvent(_RemoteBase):
    type: Literal["capability.changed"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteCatalogView = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteCommandAccepted(_RemoteBase):
    """Durable inbox admission, not model/execution success. Duplicate immutable commands return the original receipt/event."""

    type: Literal["command.accepted"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    received_at: str = Field(alias="receivedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    status: Literal["accepted"] = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_ref: RemoteResultRef | None = Field(default=None, alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteControlConfirmed(_RemoteBase):
    """D41: Worker-only structured evidence, never parsed error text. Empty orphanProcessIds is not proof of no remaining process. A paused process may still exist."""

    outcome: Literal["confirmed"] = Field(alias="outcome", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    execution_may_still_be_running: bool = Field(alias="executionMayStillBeRunning", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    orphan_process_ids: list[Annotated[int, Field(strict=True, ge=1, le=4294967295)]] = Field(alias="orphanProcessIds", max_length=0, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    reason: str = Field(alias="reason", min_length=1, max_length=2000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    evidence: Literal["adapter_confirmed", "node_boundary_paused", "already_terminal", "retry_enqueued", "supervisor_resumed", "inbox_tombstone"] = Field(alias="evidence", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    observed_at: str = Field(alias="observedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteCommandCompleted(_RemoteBase):
    """Not universally task success. Retry completes on durable new execution reference; execute completes on actual terminal Run success/cancellation. Cancel/pause/resume require confirmed structured control result."""

    type: Literal["command.completed"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_status: Literal["succeeded", "cancelled", "confirmed", "retry_enqueued", "approval_consumed", "withdrawn"] = Field(alias="resultStatus", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_ref: RemoteResultRef | None = Field(default=None, alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})
    control_result: RemoteControlConfirmed | None = Field(default=None, alias="controlResult", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteWire1Error(_RemoteBase):
    """Sanitized error. No credential, raw environment, owner locator or arbitrary detail object."""

    code: RemoteWire1ErrorCode = Field(alias="code", json_schema_extra={'wireNullable': False, 'wireType': None})
    message: str = Field(alias="message", max_length=2000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    retryable: bool = Field(alias="retryable", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})


class RemoteCommandFailed(_RemoteBase):
    """Failure after admission. A refused control is distinct from unconfirmed cancellation; do not infer that an Agent process has stopped."""

    type: Literal["command.failed"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_status: Literal["failed", "rejected"] = Field(alias="resultStatus", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    error: RemoteWire1Error = Field(alias="error", json_schema_extra={'wireNullable': False, 'wireType': None})
    result_ref: RemoteResultRef | None = Field(default=None, alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})
    control_result: RemoteControlRejected | None = Field(default=None, alias="controlResult", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteCommandRejected(_RemoteBase):
    """Pre-admission rejection only. An expired sequenced submit consumes its ordered slot without execution."""

    type: Literal["command.rejected"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    received_at: str = Field(alias="receivedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    status: Literal["rejected"] = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    error: RemoteWire1Error = Field(alias="error", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteControlResult(RootModel[RemoteControlConfirmed | RemoteControlRejected | RemoteControlUnconfirmed]):
    pass


class RemoteControlObserved(_RemoteBase):
    """D41: unconfirmed leaves command accepted and pending reconciliation. Run-scoped controls include resultRef/executionStatus. Before a Run exists (withdrawal reconciliation), omit both rather than invent an identity or execution state."""

    type: Literal["command.control_result"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_ref: RemoteResultRef | None = Field(default=None, alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})
    control_result: RemoteControlResult = Field(alias="controlResult", json_schema_extra={'wireNullable': False, 'wireType': None})
    execution_status: TaskStatus | None = Field(default=None, alias="executionStatus", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteMessageEvent(_RemoteBase):
    type: Literal["message.appended"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteWorkerMessagePayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteProgressEvent(_RemoteBase):
    """Sanitized observable progress only. Never private model reasoning, raw provider auth, full environment, or credential files."""

    type: Literal["run.progress"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_ref: RemoteResultRef = Field(alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})
    message: str = Field(alias="message", max_length=4000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteRunStateEvent(_RemoteBase):
    """Worker creates/binds LocalRun and execution Task using existing semantics; it does not invent long-lived Task or retryOfRunId."""

    type: Literal["run.state_changed"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteRunStatePayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteSkipRecorded(_RemoteBase):
    """Worker records ordered skip in the same durable inbox ordering ledger as submits."""

    type: Literal["conversation.skip_recorded"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_seq: int = Field(alias="conversationSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})


class RemoteVisibleWorkerEvent(RootModel[RemoteCommandAccepted | RemoteCommandRejected | RemoteCommandCompleted | RemoteCommandFailed | RemoteControlObserved | RemoteRunStateEvent | RemoteMessageEvent | RemoteApprovalEvent | RemoteProgressEvent | RemoteCatalogEvent | RemoteSkipRecorded]):
    pass


class RemoteBrowserWorkerEvent(_RemoteBase):
    """Owner-scoped browser event; ordering/resume is only by opaque serverCursor, never by payload Worker seq."""

    type: Literal["worker.event"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    server_cursor: str = Field(alias="serverCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    recorded_at: str = Field(alias="recordedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteVisibleWorkerEvent = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteBrowserEvent(RootModel[RemoteBrowserWorkerEvent | RemoteBrowserCommandEvent | RemoteBrowserConversationEvent | RemoteBrowserMessageEvent | RemoteBrowserV2WorkerEvent | RemoteBrowserConversationDeleted | RemoteBrowserStoreReset]):
    pass


class RemoteBrowserEventPage(_RemoteBase):
    """GET after opaque serverCursor. Unknown/expired cursor requires snapshot; never silently reset to zero."""

    items: list[RemoteBrowserEvent] = Field(alias="items", max_length=200, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    next_server_cursor: str = Field(alias="nextServerCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    has_more: bool = Field(alias="hasMore", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})


class RemoteBrowserSessionView(RootModel[RemoteAuthenticatedSession | RemoteAnonymousSession]):
    pass


class RemoteRunControlPayload(_RemoteBase):
    """All controls address LocalRun. Optional nodeId is valid only for retry of an existing node within this run."""

    run_id: str = Field(alias="runId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    node_id: str | None = Field(default=None, alias="nodeId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    reason: str | None = Field(default=None, alias="reason", max_length=1000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteCancelCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["run.cancel"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteRunControlPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteCommandWithdrawalPayload(_RemoteBase):
    """Targets an in-flight submit command whose delivery/acceptance is uncertain. Worker persists a tombstone or stops its bound run; server must not claim success first."""

    target_command_id: str = Field(alias="targetCommandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    reason: str | None = Field(default=None, alias="reason", max_length=1000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_conversation_seq: int = Field(alias="targetConversationSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})


class RemoteCommandWithdrawalCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["command.withdraw"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteCommandWithdrawalPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemotePauseCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["run.pause"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteRunControlPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteResumeCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["run.resume"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteRunControlPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteRetryCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["run.retry"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteRunControlPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteRunSubmitPayload(_RemoteBase):
    """References registered Worker workspace and scene revision. No model account/config credentials, arbitrary executable, attachment or server filesystem path. An append message is another run.submit, not mutation of a running turn."""

    client_message_id: str = Field(alias="clientMessageId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    workspace_id: str = Field(alias="workspaceId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    scene_id: str = Field(alias="sceneId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    scene_version: int = Field(alias="sceneVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    session_mode: Literal["new", "continue"] = Field(alias="sessionMode", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    text: str = Field(alias="text", min_length=1, max_length=32000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteRunSubmitCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["run.submit"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_seq: int = Field(alias="conversationSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteRunSubmitPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteCommandEnvelope(RootModel[RemoteRunSubmitCommand | RemotePauseCommand | RemoteResumeCommand | RemoteCancelCommand | RemoteRetryCommand | RemoteApprovalDecisionCommand | RemoteCommandWithdrawalCommand]):
    pass


class RemoteCommandPage(_RemoteBase):
    """Bounded owner/resource-scoped page. hasMore=true requires nextCursor; cursor is not a Worker seq."""

    items: list[RemoteCommandView] = Field(alias="items", max_length=100, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    has_more: bool = Field(alias="hasMore", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    next_cursor: str | None = Field(default=None, alias="nextCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteCommandReceipt(RootModel[RemoteCommandAccepted | RemoteCommandRejected]):
    pass


class RemoteCommandWithdrawalInput(_RemoteBase):
    reason: str | None = Field(default=None, alias="reason", max_length=1000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteConversationGap(_RemoteBase):
    """Worker requests missing commands or skip records. Never run a later user message across a sequence gap."""

    type: Literal["conversation.gap"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_seq: int = Field(alias="expectedSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    received_seq: int = Field(alias="receivedSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})


class RemoteConversationPage(_RemoteBase):
    """Bounded owner/resource-scoped page. hasMore=true requires nextCursor; cursor is not a Worker seq."""

    items: list[RemoteConversationView] = Field(alias="items", max_length=100, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    has_more: bool = Field(alias="hasMore", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    next_cursor: str | None = Field(default=None, alias="nextCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteConversationSkip(_RemoteBase):
    """Durable ordered tombstone for a never-dispatched submit. Not an execution/control command; cannot be used to erase accepted work. Retain until gap replay/snapshot acknowledgement is safe."""

    type: Literal["conversation.skip"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_seq: int = Field(alias="conversationSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    reason: Literal["withdrawn_before_dispatch", "expired_before_dispatch"] = Field(alias="reason", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    recorded_at: str = Field(alias="recordedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteRunView(_RemoteBase):
    """Worker-owned execution projection. Offline does not change status. D40 maps LocalRun.taskId to executionTaskId only at remote boundary; existing LocalRunView is unchanged."""

    run_id: str = Field(alias="runId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    execution_task_id: str | None = Field(default=None, alias="executionTaskId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    status: TaskStatus = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': None})
    observed_at: str = Field(alias="observedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_online: bool = Field(alias="workerOnline", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    summary: str | None = Field(default=None, alias="summary", max_length=16000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    parent_execution_task_id: str | None = Field(default=None, alias="parentExecutionTaskId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteConversationSnapshot(_RemoteBase):
    """Consistent selected-conversation projection and cursor transaction. For larger history, fetch bounded resource pages while replaying events after this cursor. No whole-history batch or credential content."""

    conversation: RemoteConversationView = Field(alias="conversation", json_schema_extra={'wireNullable': False, 'wireType': None})
    server_cursor: str = Field(alias="serverCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    observed_at: str = Field(alias="observedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    runs: list[RemoteRunView] = Field(alias="runs", max_length=100, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    commands: list[RemoteCommandView] = Field(alias="commands", max_length=100, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    messages: list[RemoteMessageView] = Field(alias="messages", max_length=100, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    has_more: bool = Field(alias="hasMore", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    approvals: list[RemoteApprovalView] | None = Field(default=None, alias="approvals", max_length=100, json_schema_extra={'wireNullable': False, 'wireType': 'array'})


class RemoteCreateConversationInput(_RemoteBase):
    """Owner/device/workspace/scene references for a Worker-owned creation command. Requires online revision 2; 202 is a transport receipt, not a server-created conversation."""

    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    title: str = Field(alias="title", min_length=1, max_length=200, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    workspace_id: str = Field(alias="workspaceId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    scene_id: str = Field(alias="sceneId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    scene_version: int = Field(alias="sceneVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteDeviceDeletionView(_RemoteBase):
    """Deletes server resource/copies and revokes credentials, never claims local execution stopped."""

    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    deleted_at: str = Field(alias="deletedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    execution_may_still_be_running: Literal[True] = Field(alias="executionMayStillBeRunning", json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})


class RemoteDeviceView(_RemoteBase):
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    device_name: str = Field(alias="deviceName", max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    platform: Literal["windows", "linux", "darwin"] = Field(alias="platform", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    architecture: Literal["x86_64", "aarch64"] = Field(alias="architecture", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    status: Literal["online", "offline", "revoked", "reconciliation_required"] = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    capability_revision: int = Field(alias="capabilityRevision", ge=0, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    observed_at: str = Field(alias="observedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    last_seen_at: str | None = Field(default=None, alias="lastSeenAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    paired_at: str = Field(alias="pairedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    revoked_at: str | None = Field(default=None, alias="revokedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    online: bool | None = Field(default=None, alias="online", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    busy_snapshot_fresh: bool | None = Field(default=None, alias="busySnapshotFresh", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    supported_wire_revisions: list[Annotated[int, Field(strict=True, ge=1)]] | None = Field(default=None, alias="supportedWireRevisions", max_length=16, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    remote_access: Literal["enabled", "suspended"] | None = Field(default=None, alias="remoteAccess", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    display_name: str | None = Field(default=None, alias="displayName", min_length=1, max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    version: int | None = Field(default=None, alias="version", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    suspended_at: str | None = Field(default=None, alias="suspendedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteDevicePage(_RemoteBase):
    items: list[RemoteDeviceView] = Field(alias="items", max_length=100, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    has_more: bool = Field(alias="hasMore", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    next_cursor: str | None = Field(default=None, alias="nextCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteDevicePatchInput(_RemoteBase):
    """At least one change required. Empty/whitespace displayName clears the server alias; null invalid. Does not rename the Worker."""

    expected_version: int = Field(alias="expectedVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    remote_access: Literal["enabled", "suspended"] | None = Field(default=None, alias="remoteAccess", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    display_name: str | None = Field(default=None, alias="displayName", max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteDeviceRevocationView(_RemoteBase):
    """Revokes transport rights, does not claim execution was cancelled or stopped."""

    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    revoked_at: str = Field(alias="revokedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    status: Literal["revoked"] = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    execution_may_still_be_running: Literal[True] = Field(alias="executionMayStillBeRunning", json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})


class RemoteDeviceRevokeInput(_RemoteBase):
    reason: str | None = Field(default=None, alias="reason", max_length=1000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteEventPosition(_RemoteBase):
    """Highest durably committed contiguous event seq for this Worker store, never the largest observed seq."""

    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=0, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})


class RemoteEventAck(_RemoteBase):
    """Only advances after event persistence AND projection/browser-outbox commit; old store ack never trims new store outbox."""

    type: Literal["worker.events_ack"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    connection_id: str = Field(alias="connectionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    position: RemoteEventPosition = Field(alias="position", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteHttpErrorDetail(_RemoteBase):
    """Safe HTTP-only hints. fields contains schema/header names, not input values; currentVersion only after owner/resource authorization. No raw exception, credential, owner locator or request body."""

    fields: list[Annotated[str, Field(strict=True, min_length=1, max_length=128)]] | None = Field(default=None, alias="fields", max_length=32, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    current_version: int | None = Field(default=None, alias="currentVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    retry_after_seconds: int | None = Field(default=None, alias="retryAfterSeconds", ge=0, le=86400, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})


class RemoteHttpError(_RemoteBase):
    """HTTP-only error shape inside ApiEnvelope.error; detail does not extend any Worker error DTO."""

    code: ErrorCode = Field(alias="code", json_schema_extra={'wireNullable': False, 'wireType': None})
    message: str = Field(alias="message", max_length=2000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    retryable: bool = Field(alias="retryable", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    detail: RemoteHttpErrorDetail | None = Field(default=None, alias="detail", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteLinkFrozenView(_RemoteBase):
    """Local binding view; connectionStatus is transport only. Frozen blocks command delivery pending reconciliation, even when WSS is online."""

    state: Literal["frozen"] = Field(alias="state", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    server_origin: str = Field(alias="serverOrigin", min_length=8, max_length=2048, pattern='^(?:https://(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?|\\[[0-9A-Fa-f:]+\\])|http://(?:127\\.0\\.0\\.1|localhost))(?::(?:[1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?/?$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    device_name: str = Field(alias="deviceName", min_length=1, max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    connection_status: Literal["online", "connecting", "offline"] = Field(alias="connectionStatus", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    last_connected_at: Timestamp | None = Field(alias="lastConnectedAt", json_schema_extra={'wireNullable': True, 'wireType': None})
    last_error_code: ErrorCode | None = Field(default=None, alias="lastErrorCode", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteLinkPairedView(_RemoteBase):
    """Local binding view; connectionStatus is transport only. Paired does not imply WSS connected or execution succeeded."""

    state: Literal["paired"] = Field(alias="state", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    server_origin: str = Field(alias="serverOrigin", min_length=8, max_length=2048, pattern='^(?:https://(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?|\\[[0-9A-Fa-f:]+\\])|http://(?:127\\.0\\.0\\.1|localhost))(?::(?:[1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?/?$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    device_name: str = Field(alias="deviceName", min_length=1, max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    connection_status: Literal["online", "connecting", "offline"] = Field(alias="connectionStatus", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    last_connected_at: Timestamp | None = Field(alias="lastConnectedAt", json_schema_extra={'wireNullable': True, 'wireType': None})
    last_error_code: ErrorCode | None = Field(default=None, alias="lastErrorCode", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteLinkPairingInput(_RemoteBase):
    """Local authenticated pairing request. Worker creates/stores the device credential internally; client cannot supply or retrieve it. Changing server while already paired requires explicit unlink."""

    server_origin: str = Field(alias="serverOrigin", min_length=8, max_length=2048, pattern='^(?:https://(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?|\\[[0-9A-Fa-f:]+\\])|http://(?:127\\.0\\.0\\.1|localhost))(?::(?:[1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?/?$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    device_name: str = Field(alias="deviceName", min_length=1, max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteLinkPairingView(_RemoteBase):
    """A server challenge has been obtained. Short code only, never device secret. Expiry/cancel clears candidate credentials and returns unpaired."""

    state: Literal["pairing"] = Field(alias="state", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    server_origin: str = Field(alias="serverOrigin", min_length=8, max_length=2048, pattern='^(?:https://(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?|\\[[0-9A-Fa-f:]+\\])|http://(?:127\\.0\\.0\\.1|localhost))(?::(?:[1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?/?$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    device_name: str = Field(alias="deviceName", min_length=1, max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    pair_request_id: str = Field(alias="pairRequestId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    pair_code: str = Field(alias="pairCode", min_length=8, max_length=8, pattern='^[A-HJ-NP-Z2-9]{8}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: Timestamp = Field(alias="expiresAt", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteLinkRevokedView(_RemoteBase):
    """Local binding view; connectionStatus is transport only. Revocation fences reconnect; it does not stop or rewrite execution state."""

    state: Literal["revoked"] = Field(alias="state", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    server_origin: str = Field(alias="serverOrigin", min_length=8, max_length=2048, pattern='^(?:https://(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?|\\[[0-9A-Fa-f:]+\\])|http://(?:127\\.0\\.0\\.1|localhost))(?::(?:[1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?/?$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    device_name: str = Field(alias="deviceName", min_length=1, max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    connection_status: Literal["offline"] = Field(alias="connectionStatus", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    last_connected_at: Timestamp | None = Field(alias="lastConnectedAt", json_schema_extra={'wireNullable': True, 'wireType': None})
    last_error_code: ErrorCode | None = Field(default=None, alias="lastErrorCode", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteLinkUnpairedView(_RemoteBase):
    """Local binding absent. Optional origin may remain as non-secret preference; lastErrorCode may report unconfirmed best-effort server revocation. Existing remote conversations remain remote and locally read-only."""

    state: Literal["unpaired"] = Field(alias="state", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    server_origin: str | None = Field(default=None, alias="serverOrigin", min_length=8, max_length=2048, pattern='^(?:https://(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?|\\[[0-9A-Fa-f:]+\\])|http://(?:127\\.0\\.0\\.1|localhost))(?::(?:[1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?/?$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    last_error_code: ErrorCode | None = Field(default=None, alias="lastErrorCode", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteLinkView(RootModel[RemoteLinkUnpairedView | RemoteLinkPairingView | RemoteLinkPairedView | RemoteLinkRevokedView | RemoteLinkFrozenView]):
    pass


class RemoteLoginInput(_RemoteBase):
    login_name: str = Field(alias="loginName", min_length=1, max_length=128, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    password: str = Field(alias="password", min_length=1, max_length=1024, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteMessagePage(_RemoteBase):
    """Bounded owner/resource-scoped page. hasMore=true requires nextCursor; cursor is not a Worker seq."""

    items: list[RemoteMessageView] = Field(alias="items", max_length=100, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    has_more: bool = Field(alias="hasMore", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    next_cursor: str | None = Field(default=None, alias="nextCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteNativeImportInput(_RemoteBase):
    """Explicit audited closure confirmation, not permission to override a detected live process. Import copies history and binds exact vendor ID; never starts a model by itself."""

    terminal_closed_confirmed: Literal[True] = Field(alias="terminalClosedConfirmed", json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    expected_index_version: int = Field(alias="expectedIndexVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    source_revision: str = Field(alias="sourceRevision", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteNativeSessionView(_RemoteBase):
    """Owner-scoped public IDs mapped from Worker/store index. Offline metadata is stale evidence, never write permission."""

    native_session_id: str = Field(alias="nativeSessionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    workspace_id: str = Field(alias="workspaceId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    agent_type: NativeAgentType = Field(alias="agentType", json_schema_extra={'wireNullable': False, 'wireType': None})
    title: str = Field(alias="title", max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    updated_at: str = Field(alias="updatedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    index_version: int = Field(alias="indexVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    source_revision: str = Field(alias="sourceRevision", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    format: NativeFormatView = Field(alias="format", json_schema_extra={'wireNullable': False, 'wireType': None})
    activity: NativeActivityEvidence = Field(alias="activity", json_schema_extra={'wireNullable': False, 'wireType': None})
    worker_online: bool = Field(alias="workerOnline", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})


class RemoteNativeSessionPage(_RemoteBase):
    items: list[RemoteNativeSessionView] = Field(alias="items", min_length=0, max_length=100, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    has_more: bool = Field(alias="hasMore", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    next_cursor: str | None = Field(default=None, alias="nextCursor", min_length=16, max_length=4096, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteOmittedEvents(_RemoteBase):
    """Worker local event seq continuity without publishing local-only history. Covers inclusive [firstSeq,seq], firstSeq<=seq. Opaque tombstone only, no local conversation/path/model data. Cannot cover any already published event or remote-critical event; immutable bounded ranges are replayed whole. Persist range coverage before advancing contiguous ack."""

    type: Literal["events.omitted"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    first_seq: int = Field(alias="firstSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    reason: Literal["not_remote_visible"] = Field(alias="reason", json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemotePairingChallenge(_RemoteBase):
    """Five-minute one-use code; no device secret. Never put the code in a URL."""

    pair_request_id: str = Field(alias="pairRequestId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    pair_code: str = Field(alias="pairCode", min_length=8, max_length=8, pattern='^[A-HJ-NP-Z2-9]{8}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    status: Literal["pending"] = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemotePairingConfirmInput(_RemoteBase):
    pair_code: str = Field(alias="pairCode", min_length=8, max_length=8, pattern='^[A-HJ-NP-Z2-9]{8}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemotePairingPreview(_RemoteBase):
    """Authenticated browser preview for explicit device confirmation; does not claim or grant access."""

    pair_request_id: str = Field(alias="pairRequestId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    device_name: str = Field(alias="deviceName", max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    platform: Literal["windows", "linux", "darwin"] = Field(alias="platform", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    architecture: Literal["x86_64", "aarch64"] = Field(alias="architecture", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemotePairingPreviewInput(_RemoteBase):
    pair_code: str = Field(alias="pairCode", min_length=8, max_length=8, pattern='^[A-HJ-NP-Z2-9]{8}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemotePairingRequestInput(_RemoteBase):
    """Worker sends its locally generated 256-bit device secret only in Authorization header. Body contains no credential. Unclaimed requests are short-lived authentication challenges, not owner-visible devices."""

    device_name: str = Field(alias="deviceName", min_length=1, max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    platform: Literal["windows", "linux", "darwin"] = Field(alias="platform", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    architecture: Literal["x86_64", "aarch64"] = Field(alias="architecture", json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemotePairingStatusView(_RemoteBase):
    """Device-authenticated status poll scoped to this exact request/credential. Reveals no owner or raw credential."""

    pair_request_id: str = Field(alias="pairRequestId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    status: Literal["pending", "paired", "expired", "revoked"] = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteQueuedReceipt(_RemoteBase):
    """HTTP202 after command and server outbox commit. conversationSeq present only for run.submit. No fabricated runId before Worker assigns it."""

    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_seq: int | None = Field(default=None, alias="conversationSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    status: Literal["queued"] = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    delivery_state: Literal["queued_online", "queued_offline", "reconciliation_required"] = Field(alias="deliveryState", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_online: bool = Field(alias="workerOnline", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteResourceQueuedReceipt(_RemoteBase):
    """HTTP202 transport receipt only. No fabricated conversationId/runId or execution sequence. Poll existing GET /commands/{commandId}; authoritative result comes from Worker."""

    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    type: Literal["native.import", "workspace.register"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    status: Literal["queued"] = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    delivery_state: Literal["queued_online"] = Field(alias="deliveryState", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_online: Literal[True] = Field(alias="workerOnline", json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteRunControlInput(_RemoteBase):
    """Path runId is mandatory user-visible identity; only retry may supply nodeId. Does not allocate conversationSeq."""

    action: Literal["pause", "resume", "cancel", "retry"] = Field(alias="action", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    node_id: str | None = Field(default=None, alias="nodeId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    reason: str | None = Field(default=None, alias="reason", max_length=1000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str | None = Field(default=None, alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteRunPage(_RemoteBase):
    """Bounded owner/resource-scoped page. hasMore=true requires nextCursor; cursor is not a Worker seq."""

    items: list[RemoteRunView] = Field(alias="items", max_length=100, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    has_more: bool = Field(alias="hasMore", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    next_cursor: str | None = Field(default=None, alias="nextCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteSendMessageInput(_RemoteBase):
    """Computer orders messages. Offline rejects immediately; revision 2 requires a 30-second delivery grant. Legacy expiresAt cannot extend delivery deadline. Optional explicit re-confirmation for an imported native binding only; scenario rejects it. Native always resumes exact ID with sessionMode=continue."""

    client_message_id: str = Field(alias="clientMessageId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    text: str = Field(alias="text", min_length=1, max_length=32000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    session_mode: Literal["new", "continue"] = Field(alias="sessionMode", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str | None = Field(default=None, alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    native_confirmation: NativeContinuationConfirmationInput | None = Field(default=None, alias="nativeConfirmation", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteServerHeartbeat(_RemoteBase):
    """Heartbeat acknowledgement is not event ack. After 45 seconds without authenticated Worker traffic mark offline without modifying execution state."""

    type: Literal["server.heartbeat"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    connection_id: str = Field(alias="connectionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    received_at: str = Field(alias="receivedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteWorkerHelloAck(_RemoteBase):
    """Frozen delivery requires a reason. Store changes or ack regression require reconciliation; R1 exposes no automatic force-unfreeze API."""

    type: Literal["worker.hello_ack"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    connection_id: str = Field(alias="connectionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_delivery: Literal["ready", "frozen"] = Field(alias="commandDelivery", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    last_server_ack: RemoteEventPosition | None = Field(alias="lastServerAck", json_schema_extra={'wireNullable': True, 'wireType': None})
    pending_command_cursor: str = Field(alias="pendingCommandCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    heartbeat_interval_seconds: Literal[15] = Field(alias="heartbeatIntervalSeconds", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    offline_after_seconds: Literal[45] = Field(alias="offlineAfterSeconds", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    reason: RemoteWire1Error | None = Field(default=None, alias="reason", json_schema_extra={'wireNullable': False, 'wireType': None})
    server_time: str = Field(alias="serverTime", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteWorkerHelloRejected(_RemoteBase):
    type: Literal["worker.hello_rejected"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    error: RemoteWire1Error = Field(alias="error", json_schema_extra={'wireNullable': False, 'wireType': None})
    supported_wire_revisions: list[Annotated[int, Field(strict=True, ge=1, le=2147483647)]] = Field(alias="supportedWireRevisions", min_length=1, max_length=16, json_schema_extra={'wireNullable': False, 'wireType': 'array'})


class RemoteServerOutboundFrame(RootModel[RemoteWorkerHelloAck | RemoteWorkerHelloRejected | RemoteServerHeartbeat | RemoteEventAck | RemoteRunSubmitCommand | RemotePauseCommand | RemoteResumeCommand | RemoteCancelCommand | RemoteRetryCommand | RemoteApprovalDecisionCommand | RemoteCommandWithdrawalCommand | RemoteConversationSkip]):
    pass


class RemoteSyncConversation(_RemoteBase):
    """Worker local identifiers. Server namespaces by worker/store and maps browser IDs; visibility is display-only."""

    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    workspace_id: str = Field(alias="workspaceId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    scene_id: str = Field(alias="sceneId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    scene_version: int = Field(alias="sceneVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    title: str = Field(alias="title", max_length=200, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    updated_at: str = Field(alias="updatedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    archived: bool = Field(alias="archived", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    visibility: Literal["both", "pc_only", "mobile_only"] = Field(alias="visibility", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    metadata_version: int = Field(alias="metadataVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    authority: Literal["local", "remote"] = Field(alias="authority", json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteSyncConversationInput(_RemoteBase):
    """At least one mutable field; browser cannot update copy directly."""

    expected_version: int = Field(alias="expectedVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    title: str | None = Field(default=None, alias="title", min_length=1, max_length=200, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    archived: bool | None = Field(default=None, alias="archived", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    visibility: Literal["both", "pc_only", "mobile_only"] | None = Field(default=None, alias="visibility", json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteSyncConversationUpdate(_RemoteBase):
    """At least one title/archived/visibility change; Worker checks metadataVersion atomically."""

    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_version: int = Field(alias="expectedVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    title: str | None = Field(default=None, alias="title", min_length=1, max_length=200, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    archived: bool | None = Field(default=None, alias="archived", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    visibility: Literal["both", "pc_only", "mobile_only"] | None = Field(default=None, alias="visibility", json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteSyncMessagePage(_RemoteBase):
    """Newest first. before and snapshotCursor are opaque owner/device/conversation-scoped signed cursors. New items merge by messageId/revision; never by offset."""

    items: list[RemoteMessageView] = Field(alias="items", max_length=100, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    has_more: bool = Field(alias="hasMore", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    before: str | None = Field(default=None, alias="before", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    snapshot_cursor: str = Field(alias="snapshotCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteSyncMessageSegment(_RemoteBase):
    """Whole UTF-8 text, never truncated; 0-based contiguous segments. Immutable metadata per messageRevision, atomic publish only after digest/byte-count verification."""

    message_id: str = Field(alias="messageId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    message_sequence: int = Field(alias="messageSequence", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    message_revision: int = Field(alias="messageRevision", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    role: Literal["user", "assistant", "system"] = Field(alias="role", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    run_id: str | None = Field(default=None, alias="runId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    text: str = Field(alias="text", max_length=16000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    segment_index: int = Field(alias="segmentIndex", ge=0, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    segment_count: int = Field(alias="segmentCount", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    total_utf8_bytes: int = Field(alias="totalUtf8Bytes", ge=0, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    content_sha256: str = Field(alias="contentSha256", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteSyncRedactedSlot(_RemoteBase):
    """Only retired content slots, never admission/grant/control facts. Original identity and digest are retained, not rewritten."""

    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    original_type: Literal["sync.conversation.upserted", "sync.message.segment", "sync.run.state", "sync.backfill.progress", "message.appended"] = Field(alias="originalType", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    event_sha256: str = Field(alias="eventSha256", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteSyncRunState(_RemoteBase):
    run_id: str = Field(alias="runId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    status: TaskStatus = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': None})
    observed_at: str = Field(alias="observedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    execution_task_id: str | None = Field(default=None, alias="executionTaskId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    recovery_required: bool | None = Field(default=None, alias="recoveryRequired", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})


class RemoteSyncSettingsInput(_RemoteBase):
    mirror_enabled: bool = Field(alias="mirrorEnabled", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    expected_version: int = Field(alias="expectedVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})


class RemoteSyncSettingsView(_RemoteBase):
    """Global sync toggle, default true on initialization. Historical name mirrorEnabled does not mean read-only or handover."""

    mirror_enabled: bool = Field(alias="mirrorEnabled", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    version: int = Field(alias="version", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    sync_generation: int = Field(alias="syncGeneration", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})


class RemoteV2ApprovalDecisionCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["approval.decide"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteApprovalDecisionPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    local_conversation_id: str = Field(alias="localConversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2BackfillProgress(_RemoteBase):
    type: Literal["sync.backfill.progress"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sync_generation: int = Field(alias="syncGeneration", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    backfill_id: str = Field(alias="backfillId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    batch_index: int = Field(alias="batchIndex", ge=0, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    batch_event_count: int = Field(alias="batchEventCount", ge=0, le=100, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    snapshot_high_water: int = Field(alias="snapshotHighWater", ge=0, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    complete: bool = Field(alias="complete", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})


class RemoteV2BusySnapshot(_RemoteBase):
    type: Literal["sync.busy.snapshot"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    snapshot_id: str = Field(alias="snapshotId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    connection_id: str = Field(alias="connectionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    captured_at: str = Field(alias="capturedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    part_index: int = Field(alias="partIndex", ge=0, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    part_count: int = Field(alias="partCount", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    conversation_ids: list[Annotated[str, Field(strict=True, min_length=1, max_length=160)]] = Field(alias="conversationIds", max_length=100, json_schema_extra={'wireNullable': False, 'wireType': 'array'})


class RemoteV2CancelCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["run.cancel"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteRunControlPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    local_conversation_id: str = Field(alias="localConversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2CommandWithdrawalCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["command.withdraw"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteCommandWithdrawalPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    local_conversation_id: str = Field(alias="localConversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2ConversationCreateCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["conversation.create"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteCreateConversationInput = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    local_conversation_id: str = Field(alias="localConversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2ConversationUpdateCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["conversation.update"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteSyncConversationUpdate = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    local_conversation_id: str = Field(alias="localConversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2PauseCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["run.pause"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteRunControlPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    local_conversation_id: str = Field(alias="localConversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2ResumeCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["run.resume"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteRunControlPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    local_conversation_id: str = Field(alias="localConversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2RetryCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["run.retry"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteRunControlPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    local_conversation_id: str = Field(alias="localConversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2RunSubmitCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["run.submit"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_seq: int = Field(alias="conversationSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteRunSubmitPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    local_conversation_id: str = Field(alias="localConversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2CommandEnvelope(RootModel[RemoteV2RunSubmitCommand | RemoteV2PauseCommand | RemoteV2ResumeCommand | RemoteV2CancelCommand | RemoteV2RetryCommand | RemoteV2ApprovalDecisionCommand | RemoteV2CommandWithdrawalCommand | RemoteV2ConversationUpdateCommand | RemoteV2ConversationCreateCommand]):
    pass


class RemoteV2CommandReceipt(RootModel[RemoteV2CommandAccepted | RemoteV2CommandRejected]):
    pass


class RemoteV2CommandReceived(_RemoteBase):
    type: Literal["command.received"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_digest: str = Field(alias="commandDigest", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    received_at: str = Field(alias="receivedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2ContentRedaction(_RemoteBase):
    """Authenticated privacy coverage control, not a replacement immutable event. Bound to a durable reset/deletion fence. No new seq allocation; normal contiguous ACK only after all covered identities/digests and deletion are committed."""

    type: Literal["sync.content.redaction"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    redaction_id: str = Field(alias="redactionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sync_generation: int = Field(alias="syncGeneration", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    deletion_event_id: str = Field(alias="deletionEventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    deletion_seq: int = Field(alias="deletionSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    conversation_id: str | None = Field(default=None, alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    slots: list[RemoteSyncRedactedSlot] = Field(alias="slots", min_length=1, max_length=100, json_schema_extra={'wireNullable': False, 'wireType': 'array'})


class RemoteV2ConversationDeleted(_RemoteBase):
    type: Literal["sync.conversation.deleted"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sync_generation: int = Field(alias="syncGeneration", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    deleted_at: str = Field(alias="deletedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2ConversationGap(_RemoteBase):
    """Worker requests missing commands or skip records. Never run a later user message across a sequence gap."""

    type: Literal["conversation.gap"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_seq: int = Field(alias="expectedSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    received_seq: int = Field(alias="receivedSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})


class RemoteV2ConversationSkip(_RemoteBase):
    """Durable ordered tombstone for a never-dispatched submit. Not an execution/control command; cannot be used to erase accepted work. Retain until gap replay/snapshot acknowledgement is safe."""

    type: Literal["conversation.skip"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_seq: int = Field(alias="conversationSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    reason: Literal["withdrawn_before_dispatch", "expired_before_dispatch"] = Field(alias="reason", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    recorded_at: str = Field(alias="recordedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2ConversationUpserted(_RemoteBase):
    type: Literal["sync.conversation.upserted"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sync_generation: int = Field(alias="syncGeneration", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    payload: RemoteSyncConversation = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV2DeliveryGrant(_RemoteBase):
    """Explicit durable execution permission. Continuous event ACK is never permission. Late unconsumed grants expire; persisted grants are not reverted by server timers."""

    type: Literal["command.delivery_granted"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    received_event_id: str = Field(alias="receivedEventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_digest: str = Field(alias="commandDigest", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    granted_at: str = Field(alias="grantedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2EventAck(_RemoteBase):
    """Only advances after event persistence AND projection/browser-outbox commit; old store ack never trims new store outbox."""

    type: Literal["worker.events_ack"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    connection_id: str = Field(alias="connectionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    position: RemoteEventPosition = Field(alias="position", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV2MessageSegment(_RemoteBase):
    type: Literal["sync.message.segment"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sync_generation: int = Field(alias="syncGeneration", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    payload: RemoteSyncMessageSegment = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV2OmittedEvents(_RemoteBase):
    """Worker local event seq continuity without publishing local-only history. Covers inclusive [firstSeq,seq], firstSeq<=seq. Opaque tombstone only, no local conversation/path/model data. Cannot cover any already published event or remote-critical event; immutable bounded ranges are replayed whole. Persist range coverage before advancing contiguous ack."""

    type: Literal["events.omitted"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    first_seq: int = Field(alias="firstSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    reason: Literal["not_remote_visible"] = Field(alias="reason", json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2ServerHeartbeat(_RemoteBase):
    """Heartbeat acknowledgement is not event ack. After 45 seconds without authenticated Worker traffic mark offline without modifying execution state."""

    type: Literal["server.heartbeat"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    connection_id: str = Field(alias="connectionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    received_at: str = Field(alias="receivedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2WorkerHelloAck(_RemoteBase):
    """Frozen delivery requires a reason. Store changes or ack regression require reconciliation; R1 exposes no automatic force-unfreeze API."""

    type: Literal["worker.hello_ack"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    connection_id: str = Field(alias="connectionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_delivery: Literal["ready", "frozen"] = Field(alias="commandDelivery", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    last_server_ack: RemoteEventPosition | None = Field(alias="lastServerAck", json_schema_extra={'wireNullable': True, 'wireType': None})
    pending_command_cursor: str = Field(alias="pendingCommandCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    heartbeat_interval_seconds: Literal[15] = Field(alias="heartbeatIntervalSeconds", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    offline_after_seconds: Literal[45] = Field(alias="offlineAfterSeconds", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    reason: RemoteWire2Error | None = Field(default=None, alias="reason", json_schema_extra={'wireNullable': False, 'wireType': None})
    server_time: str = Field(alias="serverTime", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV2WorkerHelloRejected(_RemoteBase):
    type: Literal["worker.hello_rejected"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    error: RemoteWire2Error = Field(alias="error", json_schema_extra={'wireNullable': False, 'wireType': None})
    supported_wire_revisions: list[Annotated[int, Field(strict=True, ge=1, le=2147483647)]] = Field(alias="supportedWireRevisions", min_length=1, max_length=16, json_schema_extra={'wireNullable': False, 'wireType': 'array'})


class RemoteV2ServerOutboundFrame(RootModel[RemoteV2WorkerHelloAck | RemoteV2WorkerHelloRejected | RemoteV2ServerHeartbeat | RemoteV2EventAck | RemoteV2RunSubmitCommand | RemoteV2PauseCommand | RemoteV2ResumeCommand | RemoteV2CancelCommand | RemoteV2RetryCommand | RemoteV2ApprovalDecisionCommand | RemoteV2CommandWithdrawalCommand | RemoteV2ConversationUpdateCommand | RemoteV2ConversationCreateCommand | RemoteV2ConversationSkip | RemoteV2DeliveryGrant]):
    pass


class RemoteV2SyncReset(_RemoteBase):
    type: Literal["sync.reset"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sync_generation: int = Field(alias="syncGeneration", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})


class RemoteV2SyncedRunState(_RemoteBase):
    type: Literal["sync.run.state"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sync_generation: int = Field(alias="syncGeneration", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    payload: RemoteSyncRunState = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV2VisibleWorkerEvent(RootModel[RemoteV2CommandAccepted | RemoteV2CommandRejected | RemoteV2CommandCompleted | RemoteV2CommandFailed | RemoteV2ControlObserved | RemoteV2RunStateEvent | RemoteV2MessageEvent | RemoteV2ApprovalEvent | RemoteV2ProgressEvent | RemoteV2CatalogEvent | RemoteV2SkipRecorded | RemoteV2ConversationUpserted | RemoteV2MessageSegment | RemoteV2SyncedRunState | RemoteV2ConversationDeleted | RemoteV2SyncReset | RemoteV2BusySnapshot | RemoteV2BackfillProgress | RemoteV2CommandReceived]):
    pass


class RemoteV2WorkerEvent(RootModel[RemoteV2CommandAccepted | RemoteV2CommandRejected | RemoteV2CommandCompleted | RemoteV2CommandFailed | RemoteV2ControlObserved | RemoteV2RunStateEvent | RemoteV2MessageEvent | RemoteV2ApprovalEvent | RemoteV2ProgressEvent | RemoteV2CatalogEvent | RemoteV2SkipRecorded | RemoteV2ConversationUpserted | RemoteV2MessageSegment | RemoteV2SyncedRunState | RemoteV2ConversationDeleted | RemoteV2SyncReset | RemoteV2BusySnapshot | RemoteV2BackfillProgress | RemoteV2CommandReceived | RemoteV2OmittedEvents]):
    pass


class RemoteV2WorkerHeartbeat(_RemoteBase):
    """Sent every 15 seconds. It reports liveness only, not durable business-event progress."""

    type: Literal["worker.heartbeat"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    connection_id: str = Field(alias="connectionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sent_at: str = Field(alias="sentAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    last_server_ack: RemoteEventPosition | None = Field(alias="lastServerAck", json_schema_extra={'wireNullable': True, 'wireType': None})


class RemoteV2WorkerHello(_RemoteBase):
    """First frame after device-authenticated WSS. Same store preserves seq across boots; new store requires null ack. Credentials never appear in frames."""

    type: Literal["worker.hello"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[2] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    protocol_version: str = Field(alias="protocolVersion", min_length=5, max_length=128, pattern='^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(?:\\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    platform: Literal["windows", "linux", "darwin"] = Field(alias="platform", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    architecture: Literal["x86_64", "aarch64"] = Field(alias="architecture", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    capability_revision: int = Field(alias="capabilityRevision", ge=0, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    last_server_ack: RemoteEventPosition | None = Field(alias="lastServerAck", json_schema_extra={'wireNullable': True, 'wireType': None})


class RemoteV2WorkerOutboundFrame(RootModel[RemoteV2WorkerHello | RemoteV2WorkerHeartbeat | RemoteV2ConversationGap | RemoteV2CommandAccepted | RemoteV2CommandRejected | RemoteV2CommandCompleted | RemoteV2CommandFailed | RemoteV2ControlObserved | RemoteV2RunStateEvent | RemoteV2MessageEvent | RemoteV2ApprovalEvent | RemoteV2ProgressEvent | RemoteV2CatalogEvent | RemoteV2SkipRecorded | RemoteV2ConversationUpserted | RemoteV2MessageSegment | RemoteV2SyncedRunState | RemoteV2ConversationDeleted | RemoteV2SyncReset | RemoteV2BusySnapshot | RemoteV2BackfillProgress | RemoteV2CommandReceived | RemoteV2OmittedEvents | RemoteV2ContentRedaction]):
    pass


class RemoteV3ApprovalDecisionCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["approval.decide"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteApprovalDecisionPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    local_conversation_id: str = Field(alias="localConversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteWire3ErrorCode(StrEnum):
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
    REMOTE_AUTH_REQUIRED = "REMOTE_AUTH_REQUIRED"
    REMOTE_CSRF_REJECTED = "REMOTE_CSRF_REJECTED"
    REMOTE_DEVICE_OFFLINE = "REMOTE_DEVICE_OFFLINE"
    REMOTE_DEVICE_REVOKED = "REMOTE_DEVICE_REVOKED"
    REMOTE_DEVICE_AUTH_FAILED = "REMOTE_DEVICE_AUTH_FAILED"
    REMOTE_PAIRING_EXPIRED = "REMOTE_PAIRING_EXPIRED"
    REMOTE_PAIRING_CONFLICT = "REMOTE_PAIRING_CONFLICT"
    REMOTE_PAIRING_INVALID = "REMOTE_PAIRING_INVALID"
    REMOTE_COMMAND_EXPIRED = "REMOTE_COMMAND_EXPIRED"
    REMOTE_COMMAND_WITHDRAWN = "REMOTE_COMMAND_WITHDRAWN"
    REMOTE_WITHDRAWAL_UNCONFIRMED = "REMOTE_WITHDRAWAL_UNCONFIRMED"
    REMOTE_STORE_CHANGED = "REMOTE_STORE_CHANGED"
    REMOTE_EPOCH_STALE = "REMOTE_EPOCH_STALE"
    REMOTE_PROTOCOL_UNSUPPORTED = "REMOTE_PROTOCOL_UNSUPPORTED"
    REMOTE_EVENT_CONFLICT = "REMOTE_EVENT_CONFLICT"
    REMOTE_ACK_CONFLICT = "REMOTE_ACK_CONFLICT"
    REMOTE_SEQUENCE_GAP = "REMOTE_SEQUENCE_GAP"
    REMOTE_APPROVAL_FORBIDDEN = "REMOTE_APPROVAL_FORBIDDEN"
    CONVERSATION_AUTHORITY_MISMATCH = "CONVERSATION_AUTHORITY_MISMATCH"
    REMOTE_TARGET_MISMATCH = "REMOTE_TARGET_MISMATCH"
    REMOTE_SCENE_VERSION_MISMATCH = "REMOTE_SCENE_VERSION_MISMATCH"
    REMOTE_CURSOR_EXPIRED = "REMOTE_CURSOR_EXPIRED"
    REMOTE_CURSOR_INVALID = "REMOTE_CURSOR_INVALID"
    REMOTE_RATE_LIMITED = "REMOTE_RATE_LIMITED"
    REMOTE_FRAME_TOO_LARGE = "REMOTE_FRAME_TOO_LARGE"
    REMOTE_WITHDRAWAL_TOO_LATE = "REMOTE_WITHDRAWAL_TOO_LATE"
    REMOTE_PAIRING_IN_PROGRESS = "REMOTE_PAIRING_IN_PROGRESS"
    REMOTE_SERVER_UNREACHABLE = "REMOTE_SERVER_UNREACHABLE"
    REMOTE_SERVER_ORIGIN_INVALID = "REMOTE_SERVER_ORIGIN_INVALID"
    REMOTE_CONVERSATION_BUSY = "REMOTE_CONVERSATION_BUSY"
    REMOTE_STATE_NOT_READY = "REMOTE_STATE_NOT_READY"
    REMOTE_SYNC_CONFLICT = "REMOTE_SYNC_CONFLICT"
    REMOTE_SYNC_DISABLED = "REMOTE_SYNC_DISABLED"
    REMOTE_DELIVERY_EXPIRED = "REMOTE_DELIVERY_EXPIRED"
    REMOTE_REVISION_REQUIRED = "REMOTE_REVISION_REQUIRED"
    REMOTE_SYNC_RESOURCE_LIMIT = "REMOTE_SYNC_RESOURCE_LIMIT"
    REMOTE_QUERY_TIMEOUT = "REMOTE_QUERY_TIMEOUT"
    REMOTE_QUERY_TOO_LARGE = "REMOTE_QUERY_TOO_LARGE"
    NATIVE_SESSION_ACTIVE = "NATIVE_SESSION_ACTIVE"
    NATIVE_SESSION_UNSUPPORTED = "NATIVE_SESSION_UNSUPPORTED"
    NATIVE_SESSION_CHANGED = "NATIVE_SESSION_CHANGED"
    NATIVE_SESSION_WRITER_CONFLICT = "NATIVE_SESSION_WRITER_CONFLICT"
    REMOTE_ROOT_NOT_AUTHORIZED = "REMOTE_ROOT_NOT_AUTHORIZED"
    REMOTE_PATH_OUTSIDE_ROOT = "REMOTE_PATH_OUTSIDE_ROOT"
    REMOTE_DIRECTORY_CHANGED = "REMOTE_DIRECTORY_CHANGED"

    @classmethod
    def model_validate(cls, value):
        from pydantic import TypeAdapter
        return TypeAdapter(cls).validate_python(value)

    def model_dump(self, **kwargs):
        return self.value


class RemoteWire3ApprovalView(_RemoteBase):
    """Local Worker policy is authoritative. Mandatory blocked actions are git_push/deploy/delete/db_migrate plus locally declared actions; refusal reason code REMOTE_APPROVAL_FORBIDDEN. Rejection of a dangerous action may still be submitted remotely."""

    approval_id: str = Field(alias="approvalId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_ref: RemoteResultRef = Field(alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})
    action: DangerousAction = Field(alias="action", json_schema_extra={'wireNullable': False, 'wireType': None})
    target_summary: str = Field(alias="targetSummary", max_length=2000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    risk_level: RiskLevel = Field(alias="riskLevel", json_schema_extra={'wireNullable': False, 'wireType': None})
    status: ApprovalStatus = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': None})
    requested_at: str = Field(alias="requestedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    remote_approval_allowed: bool = Field(alias="remoteApprovalAllowed", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    worker_policy_revision: int = Field(alias="workerPolicyRevision", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    denial_code: RemoteWire3ErrorCode | None = Field(default=None, alias="denialCode", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3ApprovalEvent(_RemoteBase):
    type: Literal["approval.state_changed"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteWire3ApprovalView = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3BackfillProgress(_RemoteBase):
    type: Literal["sync.backfill.progress"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sync_generation: int = Field(alias="syncGeneration", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    backfill_id: str = Field(alias="backfillId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    batch_index: int = Field(alias="batchIndex", ge=0, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    batch_event_count: int = Field(alias="batchEventCount", ge=0, le=100, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    snapshot_high_water: int = Field(alias="snapshotHighWater", ge=0, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    complete: bool = Field(alias="complete", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})


class RemoteV3BusySnapshot(_RemoteBase):
    type: Literal["sync.busy.snapshot"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    snapshot_id: str = Field(alias="snapshotId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    connection_id: str = Field(alias="connectionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    captured_at: str = Field(alias="capturedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    part_index: int = Field(alias="partIndex", ge=0, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    part_count: int = Field(alias="partCount", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    conversation_ids: list[Annotated[str, Field(strict=True, min_length=1, max_length=160)]] = Field(alias="conversationIds", max_length=100, json_schema_extra={'wireNullable': False, 'wireType': 'array'})


class RemoteV3CancelCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["run.cancel"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteRunControlPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    local_conversation_id: str = Field(alias="localConversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3CatalogView(_RemoteBase):
    """Atomic bounded complete catalog for R1. Reject oversized catalogs instead of truncating; offline entries are last observed, not proof that paths still exist. Revision 3 producers include authorizedRoots, [] when none; omitted legacy HTTP field means no remote project browsing."""

    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    capability_revision: int = Field(alias="capabilityRevision", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    observed_at: str = Field(alias="observedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    workspaces: list[RemoteWorkspaceSummary] = Field(alias="workspaces", max_length=1000, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    scenes: list[RemoteSceneSummary] = Field(alias="scenes", max_length=1000, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    remotely_blocked_actions: list[DangerousAction] = Field(alias="remotelyBlockedActions", max_length=32, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    authorized_roots: list[RemoteAuthorizedRoot] | None = Field(default=None, alias="authorizedRoots", min_length=0, max_length=32, json_schema_extra={'wireNullable': False, 'wireType': 'array'})


class RemoteV3CatalogEvent(_RemoteBase):
    type: Literal["capability.changed"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteV3CatalogView = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3CommandAccepted(_RemoteBase):
    """Durable inbox admission, not model/execution success. Duplicate immutable commands return the original receipt/event. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command."""

    type: Literal["command.accepted"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str | None = Field(default=None, alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    received_at: str = Field(alias="receivedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    status: Literal["accepted"] = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_ref: RemoteResultRef | None = Field(default=None, alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3ControlConfirmed(_RemoteBase):
    """D41: Worker-only structured evidence, never parsed error text. Empty orphanProcessIds is not proof of no remaining process. A paused process may still exist."""

    outcome: Literal["confirmed"] = Field(alias="outcome", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    execution_may_still_be_running: bool = Field(alias="executionMayStillBeRunning", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    orphan_process_ids: list[Annotated[int, Field(strict=True, ge=1, le=4294967295)]] = Field(alias="orphanProcessIds", max_length=0, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    reason: str = Field(alias="reason", min_length=1, max_length=2000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    evidence: Literal["adapter_confirmed", "node_boundary_paused", "already_terminal", "retry_enqueued", "supervisor_resumed", "inbox_tombstone", "metadata_committed"] = Field(alias="evidence", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    observed_at: str = Field(alias="observedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3CommandCompleted(_RemoteBase):
    """Not universally task success. Retry completes on durable new execution reference; execute completes on actual terminal Run success/cancellation. Cancel/pause/resume require confirmed structured control result. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command."""

    type: Literal["command.completed"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str | None = Field(default=None, alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_status: Literal["succeeded", "cancelled", "confirmed", "retry_enqueued", "approval_consumed", "withdrawn"] = Field(alias="resultStatus", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_ref: RemoteResultRef | None = Field(default=None, alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})
    control_result: RemoteV3ControlConfirmed | None = Field(default=None, alias="controlResult", json_schema_extra={'wireNullable': False, 'wireType': None})
    resource_ref: RemoteResourceResultRef | None = Field(default=None, alias="resourceRef", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3CommandWithdrawalCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["command.withdraw"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteCommandWithdrawalPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    local_conversation_id: str = Field(alias="localConversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3ConversationCreateCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["conversation.create"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteCreateConversationInput = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    local_conversation_id: str = Field(alias="localConversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3ConversationUpdateCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["conversation.update"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteSyncConversationUpdate = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    local_conversation_id: str = Field(alias="localConversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3NativeImportCommand(_RemoteBase):
    type: Literal["native.import"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    request_id: str = Field(alias="requestId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: NativeImportPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3PauseCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["run.pause"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteRunControlPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    local_conversation_id: str = Field(alias="localConversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3ResumeCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["run.resume"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteRunControlPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    local_conversation_id: str = Field(alias="localConversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3RetryCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["run.retry"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteRunControlPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    local_conversation_id: str = Field(alias="localConversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3RunSubmitPayload(_RemoteBase):
    """Scenario retains sceneId/sceneVersion. Native requires conversationKind=native, agentType/nativeSessionId matching persisted binding and sessionMode=continue; omits scene fields. Confirmation optional only when an existing audited confirmation remains valid. No fuzzy IDs or new-session fallback."""

    client_message_id: str = Field(alias="clientMessageId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    workspace_id: str = Field(alias="workspaceId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    scene_id: str | None = Field(default=None, alias="sceneId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    scene_version: int | None = Field(default=None, alias="sceneVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    session_mode: Literal["new", "continue"] = Field(alias="sessionMode", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    text: str = Field(alias="text", min_length=1, max_length=32000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_kind: Literal["scenario", "native"] | None = Field(default=None, alias="conversationKind", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    agent_type: NativeAgentType | None = Field(default=None, alias="agentType", json_schema_extra={'wireNullable': False, 'wireType': None})
    native_session_id: str | None = Field(default=None, alias="nativeSessionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    native_confirmation: NativeClosureConfirmation | None = Field(default=None, alias="nativeConfirmation", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3RunSubmitCommand(_RemoteBase):
    """Immutable, owner-derived command identity. Only run.submit has conversationSeq. Deduplicate commandId plus exact normalized content; never execute twice."""

    type: Literal["run.submit"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_seq: int = Field(alias="conversationSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteV3RunSubmitPayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    local_conversation_id: str = Field(alias="localConversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteWorkspaceRegisterInput(_RemoteBase):
    """Register existing selected folder, not mkdir or init-git. Validate real path again at grant; identical local registration checks, including legitimate non-Git read-only workspaces."""

    root_id: str = Field(alias="rootId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    root_version: int = Field(alias="rootVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    directory_token: str = Field(alias="directoryToken", min_length=16, max_length=4096, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    name: str | None = Field(default=None, alias="name", min_length=1, max_length=120, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3WorkspaceRegisterCommand(_RemoteBase):
    type: Literal["workspace.register"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    request_id: str = Field(alias="requestId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteWorkspaceRegisterInput = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3CommandEnvelope(RootModel[RemoteV3RunSubmitCommand | RemoteV3PauseCommand | RemoteV3ResumeCommand | RemoteV3CancelCommand | RemoteV3RetryCommand | RemoteV3ApprovalDecisionCommand | RemoteV3CommandWithdrawalCommand | RemoteV3ConversationUpdateCommand | RemoteV3ConversationCreateCommand | RemoteV3NativeImportCommand | RemoteV3WorkspaceRegisterCommand]):
    pass


class RemoteWire3Error(_RemoteBase):
    """Sanitized error. No credential, raw environment, owner locator or arbitrary detail object."""

    code: RemoteWire3ErrorCode = Field(alias="code", json_schema_extra={'wireNullable': False, 'wireType': None})
    message: str = Field(alias="message", max_length=2000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    retryable: bool = Field(alias="retryable", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})


class RemoteV3CommandFailed(_RemoteBase):
    """Failure after admission. A refused control is distinct from unconfirmed cancellation; do not infer that an Agent process has stopped. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command."""

    type: Literal["command.failed"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str | None = Field(default=None, alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_status: Literal["failed", "rejected"] = Field(alias="resultStatus", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    error: RemoteWire3Error = Field(alias="error", json_schema_extra={'wireNullable': False, 'wireType': None})
    result_ref: RemoteResultRef | None = Field(default=None, alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})
    control_result: RemoteControlRejected | None = Field(default=None, alias="controlResult", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3CommandRejected(_RemoteBase):
    """Pre-admission rejection only. An expired sequenced submit consumes its ordered slot without execution. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command."""

    type: Literal["command.rejected"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str | None = Field(default=None, alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    received_at: str = Field(alias="receivedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    status: Literal["rejected"] = Field(alias="status", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    error: RemoteWire3Error = Field(alias="error", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3CommandReceipt(RootModel[RemoteV3CommandAccepted | RemoteV3CommandRejected]):
    pass


class RemoteV3CommandReceived(_RemoteBase):
    """ For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command."""

    type: Literal["command.received"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str | None = Field(default=None, alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_digest: str = Field(alias="commandDigest", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    received_at: str = Field(alias="receivedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3RedactedSlot(_RemoteBase):
    """Only retired content slots, never admission/grant/control facts. Original identity and digest are retained, not rewritten."""

    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    original_type: Literal["sync.conversation.upserted", "sync.message.segment", "sync.run.state", "sync.backfill.progress", "message.appended", "native.index.upserted"] = Field(alias="originalType", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    event_sha256: str = Field(alias="eventSha256", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3ContentRedaction(_RemoteBase):
    """Authenticated privacy coverage control, not a replacement immutable event. Bound to a durable reset/deletion fence. No new seq allocation; normal contiguous ACK only after all covered identities/digests and deletion are committed. native.index.deleted fences only that nativeSessionId; imported deletes the index, never the newly imported Hub conversation. sync.reset covers both kinds. No redaction of closure confirmation audit."""

    type: Literal["sync.content.redaction"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    redaction_id: str = Field(alias="redactionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sync_generation: int = Field(alias="syncGeneration", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    deletion_event_id: str = Field(alias="deletionEventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    deletion_seq: int = Field(alias="deletionSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    conversation_id: str | None = Field(default=None, alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    slots: list[RemoteV3RedactedSlot] = Field(alias="slots", min_length=1, max_length=100, json_schema_extra={'wireNullable': False, 'wireType': 'array'})
    native_session_id: str | None = Field(default=None, alias="nativeSessionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3ControlResult(RootModel[RemoteV3ControlConfirmed | RemoteControlRejected | RemoteControlUnconfirmed]):
    pass


class RemoteV3ControlObserved(_RemoteBase):
    """D41: unconfirmed leaves command accepted and pending reconciliation. Run-scoped controls include resultRef/executionStatus. Before a Run exists (withdrawal reconciliation), omit both rather than invent an identity or execution state. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command."""

    type: Literal["command.control_result"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str | None = Field(default=None, alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_ref: RemoteResultRef | None = Field(default=None, alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})
    control_result: RemoteV3ControlResult = Field(alias="controlResult", json_schema_extra={'wireNullable': False, 'wireType': None})
    execution_status: TaskStatus | None = Field(default=None, alias="executionStatus", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3ConversationDeleted(_RemoteBase):
    type: Literal["sync.conversation.deleted"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sync_generation: int = Field(alias="syncGeneration", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    deleted_at: str = Field(alias="deletedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3ConversationGap(_RemoteBase):
    """Worker requests missing commands or skip records. Never run a later user message across a sequence gap."""

    type: Literal["conversation.gap"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_seq: int = Field(alias="expectedSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    received_seq: int = Field(alias="receivedSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})


class RemoteV3ConversationSkip(_RemoteBase):
    """Durable ordered tombstone for a never-dispatched submit. Not an execution/control command; cannot be used to erase accepted work. Retain until gap replay/snapshot acknowledgement is safe."""

    type: Literal["conversation.skip"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_seq: int = Field(alias="conversationSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    reason: Literal["withdrawn_before_dispatch", "expired_before_dispatch"] = Field(alias="reason", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    recorded_at: str = Field(alias="recordedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3SyncConversation(_RemoteBase):
    """Worker local identifiers. Server namespaces by worker/store and maps browser IDs; visibility is display-only. Missing conversationKind means scenario (requires existing scene fields). Native requires agentType/nativeSessionId and omits scene fields; exact vendor session binding remains local."""

    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    workspace_id: str = Field(alias="workspaceId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    scene_id: str | None = Field(default=None, alias="sceneId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    scene_version: int | None = Field(default=None, alias="sceneVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    title: str = Field(alias="title", max_length=200, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    created_at: str = Field(alias="createdAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    updated_at: str = Field(alias="updatedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    archived: bool = Field(alias="archived", strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'boolean'})
    visibility: Literal["both", "pc_only", "mobile_only"] = Field(alias="visibility", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    metadata_version: int = Field(alias="metadataVersion", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    authority: Literal["local", "remote"] = Field(alias="authority", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_kind: Literal["scenario", "native"] | None = Field(default=None, alias="conversationKind", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    agent_type: NativeAgentType | None = Field(default=None, alias="agentType", json_schema_extra={'wireNullable': False, 'wireType': None})
    native_session_id: str | None = Field(default=None, alias="nativeSessionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    native_activity: NativeActivityEvidence | None = Field(default=None, alias="nativeActivity", json_schema_extra={'wireNullable': False, 'wireType': None})
    native_source_revision: str | None = Field(default=None, alias="nativeSourceRevision", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3ConversationUpserted(_RemoteBase):
    type: Literal["sync.conversation.upserted"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sync_generation: int = Field(alias="syncGeneration", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    payload: RemoteV3SyncConversation = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3DeliveryGrant(_RemoteBase):
    """Explicit durable execution permission. Continuous event ACK is never permission. Late unconsumed grants expire; persisted grants are not reverted by server timers. For native.import/workspace.register omit conversationId and correlate immutable commandId/digest. Existing conversation commands still require it; Worker validates against persisted command."""

    type: Literal["command.delivery_granted"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str | None = Field(default=None, alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    received_event_id: str = Field(alias="receivedEventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_digest: str = Field(alias="commandDigest", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    deliver_by: str = Field(alias="deliverBy", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    granted_at: str = Field(alias="grantedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3DirectoryQuery(_RemoteBase):
    type: Literal["query.directory.list"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    query_id: str = Field(alias="queryId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    request_id: str = Field(alias="requestId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    connection_id: str = Field(alias="connectionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: DirectoryListingInput = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3EventAck(_RemoteBase):
    """Only advances after event persistence AND projection/browser-outbox commit; old store ack never trims new store outbox."""

    type: Literal["worker.events_ack"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    connection_id: str = Field(alias="connectionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    position: RemoteEventPosition = Field(alias="position", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3MessageEvent(_RemoteBase):
    type: Literal["message.appended"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteWorkerMessagePayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3ProgressEvent(_RemoteBase):
    """Sanitized observable progress only. Never private model reasoning, raw provider auth, full environment, or credential files."""

    type: Literal["run.progress"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_ref: RemoteResultRef = Field(alias="resultRef", json_schema_extra={'wireNullable': False, 'wireType': None})
    message: str = Field(alias="message", max_length=4000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3RunStateEvent(_RemoteBase):
    """Worker creates/binds LocalRun and execution Task using existing semantics; it does not invent long-lived Task or retryOfRunId."""

    type: Literal["run.state_changed"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: RemoteRunStatePayload = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3SkipRecorded(_RemoteBase):
    """Worker records ordered skip in the same durable inbox ordering ledger as submits."""

    type: Literal["conversation.skip_recorded"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    conversation_seq: int = Field(alias="conversationSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})


class RemoteV3ExecutionEvent(RootModel[RemoteV3CommandAccepted | RemoteV3CommandRejected | RemoteV3CommandCompleted | RemoteV3CommandFailed | RemoteV3ControlObserved | RemoteV3RunStateEvent | RemoteV3MessageEvent | RemoteV3ApprovalEvent | RemoteV3ProgressEvent | RemoteV3CatalogEvent | RemoteV3SkipRecorded]):
    pass


class RemoteV3MessageSegment(_RemoteBase):
    type: Literal["sync.message.segment"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sync_generation: int = Field(alias="syncGeneration", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    payload: RemoteSyncMessageSegment = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3NativeConfirmationRecorded(_RemoteBase):
    type: Literal["native.closure.confirmed"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_id: str = Field(alias="commandId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    native_session_id: str = Field(alias="nativeSessionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    confirmation: NativeClosureConfirmation = Field(alias="confirmation", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3NativeIndexDeleted(_RemoteBase):
    type: Literal["native.index.deleted"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sync_generation: int = Field(alias="syncGeneration", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    native_session_id: str = Field(alias="nativeSessionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    workspace_id: str = Field(alias="workspaceId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    deleted_at: str = Field(alias="deletedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    reason: Literal["source_removed", "workspace_removed", "imported"] = Field(alias="reason", json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3NativeIndexUpserted(_RemoteBase):
    type: Literal["native.index.upserted"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sync_generation: int = Field(alias="syncGeneration", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    payload: NativeSessionIndex = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3NativeReadQuery(_RemoteBase):
    type: Literal["query.native.messages"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    query_id: str = Field(alias="queryId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    request_id: str = Field(alias="requestId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    connection_id: str = Field(alias="connectionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    target_worker_id: str = Field(alias="targetWorkerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expected_worker_store_id: str = Field(alias="expectedWorkerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    payload: NativeReadInput = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3OmittedEvents(_RemoteBase):
    """Worker local event seq continuity without publishing local-only history. Covers inclusive [firstSeq,seq], firstSeq<=seq. Opaque tombstone only, no local conversation/path/model data. Cannot cover any already published event or remote-critical event; immutable bounded ranges are replayed whole. Persist range coverage before advancing contiguous ack."""

    type: Literal["events.omitted"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    first_seq: int = Field(alias="firstSeq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    reason: Literal["not_remote_visible"] = Field(alias="reason", json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3QueryFailed(_RemoteBase):
    type: Literal["query.failed"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    query_id: str = Field(alias="queryId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    request_id: str = Field(alias="requestId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    connection_id: str = Field(alias="connectionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    error: RemoteWire3Error = Field(alias="error", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3QueryPayload(RootModel[NativeMessagePage | DirectoryListingPage]):
    pass


class RemoteV3QueryResultSegment(_RemoteBase):
    type: Literal["query.result.segment"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    query_id: str = Field(alias="queryId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    request_id: str = Field(alias="requestId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    connection_id: str = Field(alias="connectionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    result_type: Literal["native.messages", "directory.list"] = Field(alias="resultType", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    segment_index: int = Field(alias="segmentIndex", ge=0, le=127, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    segment_count: int = Field(alias="segmentCount", ge=1, le=128, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    total_utf8_bytes: int = Field(alias="totalUtf8Bytes", ge=1, le=1048576, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    content_sha256: str = Field(alias="contentSha256", min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    text: str = Field(alias="text", max_length=16000, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3ServerHeartbeat(_RemoteBase):
    """Heartbeat acknowledgement is not event ack. After 45 seconds without authenticated Worker traffic mark offline without modifying execution state."""

    type: Literal["server.heartbeat"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    connection_id: str = Field(alias="connectionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    received_at: str = Field(alias="receivedAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3WorkerHelloAck(_RemoteBase):
    """Frozen delivery requires a reason. Store changes or ack regression require reconciliation; R1 exposes no automatic force-unfreeze API."""

    type: Literal["worker.hello_ack"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    connection_id: str = Field(alias="connectionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    command_delivery: Literal["ready", "frozen"] = Field(alias="commandDelivery", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    last_server_ack: RemoteEventPosition | None = Field(alias="lastServerAck", json_schema_extra={'wireNullable': True, 'wireType': None})
    pending_command_cursor: str = Field(alias="pendingCommandCursor", min_length=16, max_length=2048, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    heartbeat_interval_seconds: Literal[15] = Field(alias="heartbeatIntervalSeconds", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    offline_after_seconds: Literal[45] = Field(alias="offlineAfterSeconds", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    reason: RemoteWire3Error | None = Field(default=None, alias="reason", json_schema_extra={'wireNullable': False, 'wireType': None})
    server_time: str = Field(alias="serverTime", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})


class RemoteV3WorkerHelloRejected(_RemoteBase):
    type: Literal["worker.hello_rejected"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    error: RemoteWire3Error = Field(alias="error", json_schema_extra={'wireNullable': False, 'wireType': None})
    supported_wire_revisions: list[Annotated[int, Field(strict=True, ge=1, le=2147483647)]] = Field(alias="supportedWireRevisions", min_length=1, max_length=16, json_schema_extra={'wireNullable': False, 'wireType': 'array'})


class RemoteV3ServerOutboundFrame(RootModel[RemoteV3WorkerHelloAck | RemoteV3WorkerHelloRejected | RemoteV3ServerHeartbeat | RemoteV3EventAck | RemoteV3RunSubmitCommand | RemoteV3PauseCommand | RemoteV3ResumeCommand | RemoteV3CancelCommand | RemoteV3RetryCommand | RemoteV3ApprovalDecisionCommand | RemoteV3CommandWithdrawalCommand | RemoteV3ConversationUpdateCommand | RemoteV3ConversationCreateCommand | RemoteV3NativeImportCommand | RemoteV3WorkspaceRegisterCommand | RemoteV3ConversationSkip | RemoteV3DeliveryGrant | RemoteV3NativeReadQuery | RemoteV3DirectoryQuery]):
    pass


class RemoteV3SyncReset(_RemoteBase):
    type: Literal["sync.reset"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sync_generation: int = Field(alias="syncGeneration", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})


class RemoteV3SyncedRunState(_RemoteBase):
    type: Literal["sync.run.state"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    event_id: str = Field(alias="eventId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    seq: int = Field(alias="seq", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    occurred_at: str = Field(alias="occurredAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sync_generation: int = Field(alias="syncGeneration", ge=1, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    payload: RemoteSyncRunState = Field(alias="payload", json_schema_extra={'wireNullable': False, 'wireType': None})


class RemoteV3VisibleWorkerEvent(RootModel[RemoteV3CommandAccepted | RemoteV3CommandRejected | RemoteV3CommandCompleted | RemoteV3CommandFailed | RemoteV3ControlObserved | RemoteV3RunStateEvent | RemoteV3MessageEvent | RemoteV3ApprovalEvent | RemoteV3ProgressEvent | RemoteV3CatalogEvent | RemoteV3SkipRecorded | RemoteV3ConversationUpserted | RemoteV3MessageSegment | RemoteV3SyncedRunState | RemoteV3ConversationDeleted | RemoteV3SyncReset | RemoteV3BusySnapshot | RemoteV3BackfillProgress | RemoteV3CommandReceived | RemoteV3NativeIndexUpserted | RemoteV3NativeIndexDeleted | RemoteV3NativeConfirmationRecorded]):
    pass


class RemoteV3WorkerEvent(RootModel[RemoteV3CommandAccepted | RemoteV3CommandRejected | RemoteV3CommandCompleted | RemoteV3CommandFailed | RemoteV3ControlObserved | RemoteV3RunStateEvent | RemoteV3MessageEvent | RemoteV3ApprovalEvent | RemoteV3ProgressEvent | RemoteV3CatalogEvent | RemoteV3SkipRecorded | RemoteV3ConversationUpserted | RemoteV3MessageSegment | RemoteV3SyncedRunState | RemoteV3ConversationDeleted | RemoteV3SyncReset | RemoteV3BusySnapshot | RemoteV3BackfillProgress | RemoteV3CommandReceived | RemoteV3NativeIndexUpserted | RemoteV3NativeIndexDeleted | RemoteV3NativeConfirmationRecorded | RemoteV3OmittedEvents]):
    pass


class RemoteV3WorkerHeartbeat(_RemoteBase):
    """Sent every 15 seconds. It reports liveness only, not durable business-event progress."""

    type: Literal["worker.heartbeat"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    connection_id: str = Field(alias="connectionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sent_at: str = Field(alias="sentAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    last_server_ack: RemoteEventPosition | None = Field(alias="lastServerAck", json_schema_extra={'wireNullable': True, 'wireType': None})


class RemoteV3WorkerHello(_RemoteBase):
    """First frame after device-authenticated WSS. Same store preserves seq across boots; new store requires null ack. Credentials never appear in frames."""

    type: Literal["worker.hello"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[3] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    protocol_version: str = Field(alias="protocolVersion", min_length=5, max_length=128, pattern='^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(?:\\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    platform: Literal["windows", "linux", "darwin"] = Field(alias="platform", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    architecture: Literal["x86_64", "aarch64"] = Field(alias="architecture", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    capability_revision: int = Field(alias="capabilityRevision", ge=0, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    last_server_ack: RemoteEventPosition | None = Field(alias="lastServerAck", json_schema_extra={'wireNullable': True, 'wireType': None})


class RemoteV3WorkerOutboundFrame(RootModel[RemoteV3WorkerHello | RemoteV3WorkerHeartbeat | RemoteV3ConversationGap | RemoteV3CommandAccepted | RemoteV3CommandRejected | RemoteV3CommandCompleted | RemoteV3CommandFailed | RemoteV3ControlObserved | RemoteV3RunStateEvent | RemoteV3MessageEvent | RemoteV3ApprovalEvent | RemoteV3ProgressEvent | RemoteV3CatalogEvent | RemoteV3SkipRecorded | RemoteV3ConversationUpserted | RemoteV3MessageSegment | RemoteV3SyncedRunState | RemoteV3ConversationDeleted | RemoteV3SyncReset | RemoteV3BusySnapshot | RemoteV3BackfillProgress | RemoteV3CommandReceived | RemoteV3NativeIndexUpserted | RemoteV3NativeIndexDeleted | RemoteV3NativeConfirmationRecorded | RemoteV3OmittedEvents | RemoteV3ContentRedaction | RemoteV3QueryResultSegment | RemoteV3QueryFailed]):
    pass


class RemoteWorkerEvent(RootModel[RemoteCommandAccepted | RemoteCommandRejected | RemoteCommandCompleted | RemoteCommandFailed | RemoteControlObserved | RemoteRunStateEvent | RemoteMessageEvent | RemoteApprovalEvent | RemoteProgressEvent | RemoteCatalogEvent | RemoteSkipRecorded | RemoteOmittedEvents]):
    pass


class RemoteWorkerHeartbeat(_RemoteBase):
    """Sent every 15 seconds. It reports liveness only, not durable business-event progress."""

    type: Literal["worker.heartbeat"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    connection_id: str = Field(alias="connectionId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    sent_at: str = Field(alias="sentAt", min_length=20, max_length=40, pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,9})?Z$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    last_server_ack: RemoteEventPosition | None = Field(alias="lastServerAck", json_schema_extra={'wireNullable': True, 'wireType': None})


class RemoteWorkerHello(_RemoteBase):
    """First frame after device-authenticated WSS. Same store preserves seq across boots; new store requires null ack. Credentials never appear in frames."""

    type: Literal["worker.hello"] = Field(alias="type", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    wire_revision: Literal[1] = Field(alias="wireRevision", json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    protocol_version: str = Field(alias="protocolVersion", min_length=5, max_length=128, pattern='^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(?:\\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?$', strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_id: str = Field(alias="workerId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_store_id: str = Field(alias="workerStoreId", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    worker_epoch: str = Field(alias="workerEpoch", min_length=1, max_length=160, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    platform: Literal["windows", "linux", "darwin"] = Field(alias="platform", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    architecture: Literal["x86_64", "aarch64"] = Field(alias="architecture", json_schema_extra={'wireNullable': False, 'wireType': 'string'})
    capability_revision: int = Field(alias="capabilityRevision", ge=0, le=9007199254740991, strict=True, json_schema_extra={'wireNullable': False, 'wireType': 'integer'})
    last_server_ack: RemoteEventPosition | None = Field(alias="lastServerAck", json_schema_extra={'wireNullable': True, 'wireType': None})


class RemoteWorkerOutboundFrame(RootModel[RemoteWorkerHello | RemoteWorkerHeartbeat | RemoteConversationGap | RemoteCommandAccepted | RemoteCommandRejected | RemoteCommandCompleted | RemoteCommandFailed | RemoteControlObserved | RemoteRunStateEvent | RemoteMessageEvent | RemoteApprovalEvent | RemoteProgressEvent | RemoteCatalogEvent | RemoteSkipRecorded | RemoteOmittedEvents]):
    pass


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
    review_mode: ReviewMode | None = Field(default=None, alias="reviewMode")
    name: str | None = Field(default=None, alias="name")
    description: str | None = Field(default=None, alias="description")


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
    """ Optional explicit re-confirmation for an imported native binding only; scenario rejects it. Native always resumes exact ID with sessionMode=continue."""

    client_message_id: str = Field(alias="clientMessageId")
    text: str = Field(alias="text")
    session_mode: Literal["new", "continue"] = Field(alias="sessionMode")
    native_confirmation: NativeContinuationConfirmationInput | None = Field(default=None, alias="nativeConfirmation")


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


class UpdateLocalConversationInput(_Base):
    """At least one non-null title, archived or visibility is required. Workspace, scene and session associations remain unchanged."""

    expected_version: int = Field(alias="expectedVersion")
    title: str | None = Field(default=None, alias="title")
    archived: bool | None = Field(default=None, alias="archived")
    visibility: Literal["both", "pc_only", "mobile_only"] | None = Field(default=None, alias="visibility")


class UpdateLocalRoleTemplateInput(_Base):
    expected_version: int = Field(alias="expectedVersion")
    name: str = Field(alias="name")
    instructions: str = Field(alias="instructions")


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
    "REMOTE_AUTH_REQUIRED": {"http": 401, "retryable": False},
    "REMOTE_CSRF_REJECTED": {"http": 403, "retryable": False},
    "REMOTE_DEVICE_OFFLINE": {"http": 409, "retryable": True},
    "REMOTE_DEVICE_REVOKED": {"http": 403, "retryable": False},
    "REMOTE_DEVICE_AUTH_FAILED": {"http": 401, "retryable": False},
    "REMOTE_PAIRING_EXPIRED": {"http": 410, "retryable": False},
    "REMOTE_PAIRING_CONFLICT": {"http": 409, "retryable": False},
    "REMOTE_PAIRING_INVALID": {"http": 404, "retryable": False},
    "REMOTE_COMMAND_EXPIRED": {"http": 410, "retryable": False},
    "REMOTE_COMMAND_WITHDRAWN": {"http": 409, "retryable": False},
    "REMOTE_WITHDRAWAL_UNCONFIRMED": {"http": 409, "retryable": False},
    "REMOTE_STORE_CHANGED": {"http": 409, "retryable": False},
    "REMOTE_EPOCH_STALE": {"http": 409, "retryable": False},
    "REMOTE_PROTOCOL_UNSUPPORTED": {"http": 409, "retryable": False},
    "REMOTE_EVENT_CONFLICT": {"http": 409, "retryable": False},
    "REMOTE_ACK_CONFLICT": {"http": 409, "retryable": False},
    "REMOTE_SEQUENCE_GAP": {"http": 409, "retryable": True},
    "REMOTE_APPROVAL_FORBIDDEN": {"http": 403, "retryable": False},
    "CONVERSATION_AUTHORITY_MISMATCH": {"http": 409, "retryable": False},
    "REMOTE_TARGET_MISMATCH": {"http": 409, "retryable": False},
    "REMOTE_SCENE_VERSION_MISMATCH": {"http": 409, "retryable": False},
    "REMOTE_CURSOR_EXPIRED": {"http": 410, "retryable": False},
    "REMOTE_CURSOR_INVALID": {"http": 400, "retryable": False},
    "REMOTE_RATE_LIMITED": {"http": 429, "retryable": True},
    "REMOTE_FRAME_TOO_LARGE": {"http": 413, "retryable": False},
    "REMOTE_WITHDRAWAL_TOO_LATE": {"http": 409, "retryable": False},
    "REMOTE_PAIRING_IN_PROGRESS": {"http": 409, "retryable": False},
    "REMOTE_SERVER_UNREACHABLE": {"http": 503, "retryable": True},
    "REMOTE_SERVER_ORIGIN_INVALID": {"http": 422, "retryable": False},
    "REMOTE_CONVERSATION_BUSY": {"http": 409, "retryable": True},
    "REMOTE_STATE_NOT_READY": {"http": 409, "retryable": True},
    "REMOTE_SYNC_CONFLICT": {"http": 409, "retryable": False},
    "REMOTE_SYNC_DISABLED": {"http": 409, "retryable": False},
    "REMOTE_DELIVERY_EXPIRED": {"http": 409, "retryable": True},
    "REMOTE_REVISION_REQUIRED": {"http": 409, "retryable": False},
    "REMOTE_SYNC_RESOURCE_LIMIT": {"http": 413, "retryable": False},
    "REMOTE_DEVICE_SUSPENDED": {"http": 409, "retryable": False},
    "REMOTE_API_TOKEN_INVALID": {"http": 401, "retryable": False},
    "REMOTE_API_TOKEN_EXPIRED": {"http": 401, "retryable": False},
    "REMOTE_API_TOKEN_SCOPE_INSUFFICIENT": {"http": 403, "retryable": False},
    "REMOTE_AUTH_AMBIGUOUS": {"http": 400, "retryable": False},
    "REMOTE_QUERY_TIMEOUT": {"http": 504, "retryable": True},
    "REMOTE_QUERY_TOO_LARGE": {"http": 413, "retryable": False},
    "NATIVE_SESSION_ACTIVE": {"http": 409, "retryable": False},
    "NATIVE_SESSION_UNSUPPORTED": {"http": 422, "retryable": False},
    "NATIVE_SESSION_CHANGED": {"http": 409, "retryable": False},
    "NATIVE_SESSION_WRITER_CONFLICT": {"http": 409, "retryable": False},
    "REMOTE_ROOT_NOT_AUTHORIZED": {"http": 403, "retryable": False},
    "REMOTE_PATH_OUTSIDE_ROOT": {"http": 403, "retryable": False},
    "REMOTE_DIRECTORY_CHANGED": {"http": 409, "retryable": False},
}
