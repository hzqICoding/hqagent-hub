// 此文件由 scripts/protocol/generate.py 生成，请勿手改。
// 改协议请改 packages/protocol/schema/ 或 registry/，然后重新运行:
//     pwsh scripts/protocol/generate.ps1

package protocol

import "encoding/json"

const Version = "0.4.0"

type AdapterId = string

type Timestamp = string

type ErrorCode string

const (
	ErrorCodeBadRequest ErrorCode = "BAD_REQUEST"
	ErrorCodeValidationFailed ErrorCode = "VALIDATION_FAILED"
	ErrorCodeUnauthorized ErrorCode = "UNAUTHORIZED"
	ErrorCodeOriginNotAllowed ErrorCode = "ORIGIN_NOT_ALLOWED"
	ErrorCodeNotFound ErrorCode = "NOT_FOUND"
	ErrorCodeConflict ErrorCode = "CONFLICT"
	ErrorCodeIdempotencyMismatch ErrorCode = "IDEMPOTENCY_MISMATCH"
	ErrorCodeProtocolVersionMismatch ErrorCode = "PROTOCOL_VERSION_MISMATCH"
	ErrorCodeHubNotReady ErrorCode = "HUB_NOT_READY"
	ErrorCodeHubMaintenance ErrorCode = "HUB_MAINTENANCE"
	ErrorCodeEventCursorExpired ErrorCode = "EVENT_CURSOR_EXPIRED"
	ErrorCodeFeatureUnavailable ErrorCode = "FEATURE_UNAVAILABLE"
	ErrorCodeAgentNotFound ErrorCode = "AGENT_NOT_FOUND"
	ErrorCodeAgentOffline ErrorCode = "AGENT_OFFLINE"
	ErrorCodeAgentNotLoggedIn ErrorCode = "AGENT_NOT_LOGGED_IN"
	ErrorCodeAgentIncompatible ErrorCode = "AGENT_INCOMPATIBLE"
	ErrorCodeCapabilityMissing ErrorCode = "CAPABILITY_MISSING"
	ErrorCodeRoleUnresolved ErrorCode = "ROLE_UNRESOLVED"
	ErrorCodeSessionNotResumable ErrorCode = "SESSION_NOT_RESUMABLE"
	ErrorCodeTaskNotCancellable ErrorCode = "TASK_NOT_CANCELLABLE"
	ErrorCodeTaskActionInvalid ErrorCode = "TASK_ACTION_INVALID"
	ErrorCodeWorktreeBusy ErrorCode = "WORKTREE_BUSY"
	ErrorCodePathNotAllowed ErrorCode = "PATH_NOT_ALLOWED"
	ErrorCodeApprovalRequired ErrorCode = "APPROVAL_REQUIRED"
	ErrorCodeApprovalExpired ErrorCode = "APPROVAL_EXPIRED"
	ErrorCodeApprovalAlreadyDecided ErrorCode = "APPROVAL_ALREADY_DECIDED"
	ErrorCodeUpdateNotAvailable ErrorCode = "UPDATE_NOT_AVAILABLE"
	ErrorCodeUpdateBusy ErrorCode = "UPDATE_BUSY"
	ErrorCodeUpdateVerifyFailed ErrorCode = "UPDATE_VERIFY_FAILED"
	ErrorCodeUpdateDrainTimeout ErrorCode = "UPDATE_DRAIN_TIMEOUT"
	ErrorCodeInternal ErrorCode = "INTERNAL"
)

type RoleId = string

type AggregateType string

const (
	AggregateTypeAgent AggregateType = "agent"
	AggregateTypeTask AggregateType = "task"
	AggregateTypeSession AggregateType = "session"
	AggregateTypeApproval AggregateType = "approval"
	AggregateTypeUpdate AggregateType = "update"
	AggregateTypeSystem AggregateType = "system"
)

type ProtocolVersion = string

type UpdatePhase string

const (
	UpdatePhaseIdle UpdatePhase = "idle"
	UpdatePhaseChecking UpdatePhase = "checking"
	UpdatePhaseUpToDate UpdatePhase = "up_to_date"
	UpdatePhaseAvailable UpdatePhase = "available"
	UpdatePhaseDownloading UpdatePhase = "downloading"
	UpdatePhaseDownloaded UpdatePhase = "downloaded"
	UpdatePhaseVerifying UpdatePhase = "verifying"
	UpdatePhaseReadyToInstall UpdatePhase = "ready_to_install"
	UpdatePhaseDrainingTasks UpdatePhase = "draining_tasks"
	UpdatePhaseWaitingUser UpdatePhase = "waiting_user"
	UpdatePhaseInstalling UpdatePhase = "installing"
	UpdatePhaseHealthChecking UpdatePhase = "health_checking"
	UpdatePhaseSucceeded UpdatePhase = "succeeded"
	UpdatePhaseRollingBack UpdatePhase = "rolling_back"
	UpdatePhaseRollbackSucceeded UpdatePhase = "rollback_succeeded"
	UpdatePhaseRollbackFailed UpdatePhase = "rollback_failed"
	UpdatePhaseCancelled UpdatePhase = "cancelled"
	UpdatePhaseFailed UpdatePhase = "failed"
)

type DrainStep string

const (
	DrainStepStopAccepting DrainStep = "stop_accepting"
	DrainStepSaveSessions DrainStep = "save_sessions"
	DrainStepWaitRunningTasks DrainStep = "wait_running_tasks"
	DrainStepBackupData DrainStep = "backup_data"
	DrainStepReady DrainStep = "ready"
)

type ProcessDescriptor struct {
	Component string `json:"component"`
	Pid int64 `json:"pid"`
	Name *string `json:"name,omitempty"`
}

type DrainProgress struct {
	WaitPids []ProcessDescriptor `json:"waitPids,omitempty"`
	BackupCompleted *bool `json:"backupCompleted,omitempty"`
	Step DrainStep `json:"step"`
	ActiveTasksRemaining int64 `json:"activeTasksRemaining"`
	Percent int64 `json:"percent"`
	StartedAt *Timestamp `json:"startedAt,omitempty"`
	TimeoutAt *Timestamp `json:"timeoutAt,omitempty"`
	WaitingTaskIds []string `json:"waitingTaskIds,omitempty"`
}

type HubEvent struct {
	EventId string `json:"eventId"`
	Seq int64 `json:"seq"`
	OccurredAt Timestamp `json:"occurredAt"`
	AggregateType AggregateType `json:"aggregateType"`
	AggregateId string `json:"aggregateId"`
	Type string `json:"type"`
	Payload json.RawMessage `json:"payload"`
	ProtocolVersion ProtocolVersion `json:"protocolVersion"`
	TaskId *string `json:"taskId,omitempty"`
	NodeId *string `json:"nodeId,omitempty"`
	RoleId *RoleId `json:"roleId,omitempty"`
	AgentInstanceId *string `json:"agentInstanceId,omitempty"`
	AdapterId *AdapterId `json:"adapterId,omitempty"`
}

type HealthCheckOutcome struct {
	Type string `json:"type"`
	Component *string `json:"component,omitempty"`
	Passed bool `json:"passed"`
	Detail *string `json:"detail,omitempty"`
	DurationMs *int64 `json:"durationMs,omitempty"`
}

type HealthView struct {
	Status string `json:"status"`
	AppVersion string `json:"appVersion"`
	ProtocolVersion ProtocolVersion `json:"protocolVersion"`
	Pid int64 `json:"pid"`
	StartedAt Timestamp `json:"startedAt"`
}

type HubRuntimeDescriptor struct {
	SchemaVersion int64 `json:"schemaVersion"`
	InstanceId string `json:"instanceId"`
	Port int64 `json:"port"`
	Token string `json:"token"`
	Pid int64 `json:"pid"`
	BaseUrl string `json:"baseUrl"`
	AppVersion string `json:"appVersion"`
	ProtocolVersion ProtocolVersion `json:"protocolVersion"`
	StartedAt Timestamp `json:"startedAt"`
}

type InstallStrategy string

const (
	InstallStrategyWindowsNsis InstallStrategy = "windows-nsis"
	InstallStrategyWindowsMsi InstallStrategy = "windows-msi"
	InstallStrategyWindowsPortable InstallStrategy = "windows-portable"
	InstallStrategyMacosAppBundle InstallStrategy = "macos-app-bundle"
	InstallStrategyLinuxAppimage InstallStrategy = "linux-appimage"
	InstallStrategyLinuxDeb InstallStrategy = "linux-deb"
)

type UpdateChannel string

const (
	UpdateChannelStable UpdateChannel = "stable"
	UpdateChannelBeta UpdateChannel = "beta"
)

type ReleaseInfo struct {
	Version string `json:"version"`
	Channel UpdateChannel `json:"channel"`
	TargetKey string `json:"targetKey"`
	PublishedAt Timestamp `json:"publishedAt"`
	SizeBytes int64 `json:"sizeBytes"`
	Sha256 string `json:"sha256"`
	Signature *string `json:"signature,omitempty"`
	SignatureAlgorithm *string `json:"signatureAlgorithm,omitempty"`
	KeyId *string `json:"keyId,omitempty"`
	Mandatory bool `json:"mandatory"`
	MinimumSupportedVersion *string `json:"minimumSupportedVersion,omitempty"`
	ReleaseNotes *string `json:"releaseNotes,omitempty"`
	InstallStrategy *InstallStrategy `json:"installStrategy,omitempty"`
	RollbackCompatible *bool `json:"rollbackCompatible,omitempty"`
}

type UpdateActionInput struct {
	Action string `json:"action"`
	DeferMinutes *int64 `json:"deferMinutes,omitempty"`
	AllowTaskCancellation *bool `json:"allowTaskCancellation,omitempty"`
}

type UpdateAgentRuntimeDescriptor struct {
	SchemaVersion int64 `json:"schemaVersion"`
	InstanceId string `json:"instanceId"`
	Port int64 `json:"port"`
	Token string `json:"token"`
	Pid int64 `json:"pid"`
	BaseUrl string `json:"baseUrl"`
	AgentVersion string `json:"agentVersion"`
	StartedAt Timestamp `json:"startedAt"`
}

type UpdateResultView struct {
	SchemaVersion int64 `json:"schemaVersion"`
	AppId string `json:"appId"`
	FromVersion string `json:"fromVersion"`
	ToVersion string `json:"toVersion"`
	Channel *UpdateChannel `json:"channel,omitempty"`
	Success bool `json:"success"`
	FinishedAt Timestamp `json:"finishedAt"`
	InstallStrategy *InstallStrategy `json:"installStrategy,omitempty"`
	HealthChecks []HealthCheckOutcome `json:"healthChecks,omitempty"`
	HealthCheckPassed *bool `json:"healthCheckPassed,omitempty"`
	RolledBack *bool `json:"rolledBack,omitempty"`
	RollbackSucceeded *bool `json:"rollbackSucceeded,omitempty"`
	RestoredDatabaseBackup *string `json:"restoredDatabaseBackup,omitempty"`
	Error *string `json:"error,omitempty"`
	ErrorCode *ErrorCode `json:"errorCode,omitempty"`
	Acknowledged bool `json:"acknowledged"`
}

type UpdateCompletedPayload struct {
	Result UpdateResultView `json:"result"`
}

type UpdateDownloadProgressPayload struct {
	DownloadBytes int64 `json:"downloadBytes"`
	TotalBytes int64 `json:"totalBytes"`
	Percent float64 `json:"percent"`
	SpeedBytesPerSecond *int64 `json:"speedBytesPerSecond,omitempty"`
	EtaSeconds *int64 `json:"etaSeconds,omitempty"`
}

type UpdateHealthCheckPayload struct {
	Passed bool `json:"passed"`
	Checks []HealthCheckOutcome `json:"checks"`
}

type UpdateRollbackPayload struct {
	Reason string `json:"reason"`
	Succeeded *bool `json:"succeeded,omitempty"`
	RestoredDatabaseBackup *string `json:"restoredDatabaseBackup,omitempty"`
}

type UpdateStateView struct {
	Phase UpdatePhase `json:"phase"`
	CurrentVersion string `json:"currentVersion"`
	Channel UpdateChannel `json:"channel"`
	LatestVersion *string `json:"latestVersion,omitempty"`
	TargetKey *string `json:"targetKey,omitempty"`
	ReleaseNotes *string `json:"releaseNotes,omitempty"`
	Mandatory *bool `json:"mandatory,omitempty"`
	DownloadProgress *float64 `json:"downloadProgress,omitempty"`
	DownloadBytes *int64 `json:"downloadBytes,omitempty"`
	TotalBytes *int64 `json:"totalBytes,omitempty"`
	SpeedBytesPerSecond *int64 `json:"speedBytesPerSecond,omitempty"`
	EtaSeconds *int64 `json:"etaSeconds,omitempty"`
	DrainProgress *DrainProgress `json:"drainProgress,omitempty"`
	CanInstallNow bool `json:"canInstallNow"`
	DeferredUntil *Timestamp `json:"deferredUntil,omitempty"`
	LastCheckedAt Timestamp `json:"lastCheckedAt"`
	Error *string `json:"error,omitempty"`
	ErrorCode *ErrorCode `json:"errorCode,omitempty"`
	ProtocolVersion *ProtocolVersion `json:"protocolVersion,omitempty"`
}

type UpdateStateChangedPayload struct {
	State UpdateStateView `json:"state"`
	PreviousPhase *UpdatePhase `json:"previousPhase,omitempty"`
}

type UpdateVerificationCompletedPayload struct {
	Passed bool `json:"passed"`
	SizeMatched bool `json:"sizeMatched"`
	Sha256Matched bool `json:"sha256Matched"`
	SignatureValid bool `json:"signatureValid"`
	KeyId *string `json:"keyId,omitempty"`
	Error *string `json:"error,omitempty"`
}
