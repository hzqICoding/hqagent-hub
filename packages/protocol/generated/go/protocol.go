// 此文件由 scripts/protocol/generate.py 生成，请勿手改。
// 改协议请改 packages/protocol/schema/ 或 registry/，然后重新运行:
//     pwsh scripts/protocol/generate.ps1

package protocol

import "encoding/json"

const Version = "0.11.0"

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
	ErrorCodeRemoteAuthRequired ErrorCode = "REMOTE_AUTH_REQUIRED"
	ErrorCodeRemoteCsrfRejected ErrorCode = "REMOTE_CSRF_REJECTED"
	ErrorCodeRemoteDeviceOffline ErrorCode = "REMOTE_DEVICE_OFFLINE"
	ErrorCodeRemoteDeviceRevoked ErrorCode = "REMOTE_DEVICE_REVOKED"
	ErrorCodeRemoteDeviceAuthFailed ErrorCode = "REMOTE_DEVICE_AUTH_FAILED"
	ErrorCodeRemotePairingExpired ErrorCode = "REMOTE_PAIRING_EXPIRED"
	ErrorCodeRemotePairingConflict ErrorCode = "REMOTE_PAIRING_CONFLICT"
	ErrorCodeRemotePairingInvalid ErrorCode = "REMOTE_PAIRING_INVALID"
	ErrorCodeRemoteCommandExpired ErrorCode = "REMOTE_COMMAND_EXPIRED"
	ErrorCodeRemoteCommandWithdrawn ErrorCode = "REMOTE_COMMAND_WITHDRAWN"
	ErrorCodeRemoteWithdrawalUnconfirmed ErrorCode = "REMOTE_WITHDRAWAL_UNCONFIRMED"
	ErrorCodeRemoteStoreChanged ErrorCode = "REMOTE_STORE_CHANGED"
	ErrorCodeRemoteEpochStale ErrorCode = "REMOTE_EPOCH_STALE"
	ErrorCodeRemoteProtocolUnsupported ErrorCode = "REMOTE_PROTOCOL_UNSUPPORTED"
	ErrorCodeRemoteEventConflict ErrorCode = "REMOTE_EVENT_CONFLICT"
	ErrorCodeRemoteAckConflict ErrorCode = "REMOTE_ACK_CONFLICT"
	ErrorCodeRemoteSequenceGap ErrorCode = "REMOTE_SEQUENCE_GAP"
	ErrorCodeRemoteApprovalForbidden ErrorCode = "REMOTE_APPROVAL_FORBIDDEN"
	ErrorCodeConversationAuthorityMismatch ErrorCode = "CONVERSATION_AUTHORITY_MISMATCH"
	ErrorCodeRemoteTargetMismatch ErrorCode = "REMOTE_TARGET_MISMATCH"
	ErrorCodeRemoteSceneVersionMismatch ErrorCode = "REMOTE_SCENE_VERSION_MISMATCH"
	ErrorCodeRemoteCursorExpired ErrorCode = "REMOTE_CURSOR_EXPIRED"
	ErrorCodeRemoteCursorInvalid ErrorCode = "REMOTE_CURSOR_INVALID"
	ErrorCodeRemoteRateLimited ErrorCode = "REMOTE_RATE_LIMITED"
	ErrorCodeRemoteFrameTooLarge ErrorCode = "REMOTE_FRAME_TOO_LARGE"
	ErrorCodeRemoteWithdrawalTooLate ErrorCode = "REMOTE_WITHDRAWAL_TOO_LATE"
	ErrorCodeRemotePairingInProgress ErrorCode = "REMOTE_PAIRING_IN_PROGRESS"
	ErrorCodeRemoteServerUnreachable ErrorCode = "REMOTE_SERVER_UNREACHABLE"
	ErrorCodeRemoteServerOriginInvalid ErrorCode = "REMOTE_SERVER_ORIGIN_INVALID"
	ErrorCodeRemoteConversationBusy ErrorCode = "REMOTE_CONVERSATION_BUSY"
	ErrorCodeRemoteStateNotReady ErrorCode = "REMOTE_STATE_NOT_READY"
	ErrorCodeRemoteSyncConflict ErrorCode = "REMOTE_SYNC_CONFLICT"
	ErrorCodeRemoteSyncDisabled ErrorCode = "REMOTE_SYNC_DISABLED"
	ErrorCodeRemoteDeliveryExpired ErrorCode = "REMOTE_DELIVERY_EXPIRED"
	ErrorCodeRemoteRevisionRequired ErrorCode = "REMOTE_REVISION_REQUIRED"
	ErrorCodeRemoteSyncResourceLimit ErrorCode = "REMOTE_SYNC_RESOURCE_LIMIT"
	ErrorCodeRemoteDeviceSuspended ErrorCode = "REMOTE_DEVICE_SUSPENDED"
	ErrorCodeRemoteApiTokenInvalid ErrorCode = "REMOTE_API_TOKEN_INVALID"
	ErrorCodeRemoteApiTokenExpired ErrorCode = "REMOTE_API_TOKEN_EXPIRED"
	ErrorCodeRemoteApiTokenScopeInsufficient ErrorCode = "REMOTE_API_TOKEN_SCOPE_INSUFFICIENT"
	ErrorCodeRemoteAuthAmbiguous ErrorCode = "REMOTE_AUTH_AMBIGUOUS"
	ErrorCodeRemoteQueryTimeout ErrorCode = "REMOTE_QUERY_TIMEOUT"
	ErrorCodeRemoteQueryTooLarge ErrorCode = "REMOTE_QUERY_TOO_LARGE"
	ErrorCodeNativeSessionActive ErrorCode = "NATIVE_SESSION_ACTIVE"
	ErrorCodeNativeSessionUnsupported ErrorCode = "NATIVE_SESSION_UNSUPPORTED"
	ErrorCodeNativeSessionChanged ErrorCode = "NATIVE_SESSION_CHANGED"
	ErrorCodeNativeSessionWriterConflict ErrorCode = "NATIVE_SESSION_WRITER_CONFLICT"
	ErrorCodeRemoteRootNotAuthorized ErrorCode = "REMOTE_ROOT_NOT_AUTHORIZED"
	ErrorCodeRemotePathOutsideRoot ErrorCode = "REMOTE_PATH_OUTSIDE_ROOT"
	ErrorCodeRemoteDirectoryChanged ErrorCode = "REMOTE_DIRECTORY_CHANGED"
	ErrorCodeAttachmentTooLarge ErrorCode = "ATTACHMENT_TOO_LARGE"
	ErrorCodeAttachmentTypeUnsupported ErrorCode = "ATTACHMENT_TYPE_UNSUPPORTED"
	ErrorCodeAttachmentCountExceeded ErrorCode = "ATTACHMENT_COUNT_EXCEEDED"
	ErrorCodeAttachmentQuotaExceeded ErrorCode = "ATTACHMENT_QUOTA_EXCEEDED"
	ErrorCodeAttachmentHashMismatch ErrorCode = "ATTACHMENT_HASH_MISMATCH"
	ErrorCodeAgentImageUnsupported ErrorCode = "AGENT_IMAGE_UNSUPPORTED"
	ErrorCodeAttachmentDownloadFailed ErrorCode = "ATTACHMENT_DOWNLOAD_FAILED"
	ErrorCodeAttachmentNotReady ErrorCode = "ATTACHMENT_NOT_READY"
	ErrorCodeAttachmentInUse ErrorCode = "ATTACHMENT_IN_USE"
	ErrorCodeAttachmentThumbnailUnavailable ErrorCode = "ATTACHMENT_THUMBNAIL_UNAVAILABLE"
	ErrorCodeAttachmentPreparationInterrupted ErrorCode = "ATTACHMENT_PREPARATION_INTERRUPTED"
	ErrorCodePiGuardUnavailable ErrorCode = "PI_GUARD_UNAVAILABLE"
	ErrorCodePiUncontrolledExtensions ErrorCode = "PI_UNCONTROLLED_EXTENSIONS"
	ErrorCodePiToolCallBlocked ErrorCode = "PI_TOOL_CALL_BLOCKED"
)

type RoleId = string

type PiGuardReason string

const (
	PiGuardReasonGuardNotLoaded PiGuardReason = "guard_not_loaded"
	PiGuardReasonUncontrolledExtensions PiGuardReason = "uncontrolled_extensions"
	PiGuardReasonPolicyUnavailable PiGuardReason = "policy_unavailable"
	PiGuardReasonToolInventoryChanged PiGuardReason = "tool_inventory_changed"
	PiGuardReasonGuardTimeout PiGuardReason = "guard_timeout"
	PiGuardReasonInvalidRequest PiGuardReason = "invalid_request"
	PiGuardReasonArgumentMismatch PiGuardReason = "argument_mismatch"
	PiGuardReasonPathOutsideScope PiGuardReason = "path_outside_scope"
	PiGuardReasonUnsupportedShell PiGuardReason = "unsupported_shell"
	PiGuardReasonApprovalRequired PiGuardReason = "approval_required"
	PiGuardReasonApprovalRejected PiGuardReason = "approval_rejected"
	PiGuardReasonApprovalExpired PiGuardReason = "approval_expired"
	PiGuardReasonReadOnlyTool PiGuardReason = "read_only_tool"
	PiGuardReasonToolNotAllowed PiGuardReason = "tool_not_allowed"
)

type RuntimeGuardView struct {
	Status string `json:"status"`
	Isolation string `json:"isolation"`
	CheckedAt string `json:"checkedAt"`
	PolicyRevision *string `json:"policyRevision,omitempty"`
	Reasons []PiGuardReason `json:"reasons"`
}

type AttachmentManifestItem struct {
	AttachmentId string `json:"attachmentId"`
	FileName string `json:"fileName"`
	Kind string `json:"kind"`
	MimeType string `json:"mimeType"`
	SizeBytes int64 `json:"sizeBytes"`
	Sha256 string `json:"sha256"`
}

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

type AttachmentLimits struct {
	ImageMaxBytes int64 `json:"imageMaxBytes"`
	FileMaxBytes int64 `json:"fileMaxBytes"`
	MessageMaxCount int64 `json:"messageMaxCount"`
	AccountQuotaBytes int64 `json:"accountQuotaBytes"`
	UnattachedTtlSeconds int64 `json:"unattachedTtlSeconds"`
	ImageMimeTypes []string `json:"imageMimeTypes"`
	FileExtensions []string `json:"fileExtensions"`
}

type RuntimeNativeAgentType string

const (
	RuntimeNativeAgentTypeClaude RuntimeNativeAgentType = "claude"
	RuntimeNativeAgentTypeCodex RuntimeNativeAgentType = "codex"
	RuntimeNativeAgentTypePi RuntimeNativeAgentType = "pi"
)

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

type LocalAuthorizedRoot struct {
	RootId string `json:"rootId"`
	DisplayName string `json:"displayName"`
	Path string `json:"path"`
	Version int64 `json:"version"`
}

type LocalAuthorizedRootInput struct {
	RootId *string `json:"rootId,omitempty"`
	DisplayName string `json:"displayName"`
	Path string `json:"path"`
}

type LocalImageProbeResults struct {
	New bool `json:"new"`
	Resume bool `json:"resume"`
	MixedFive bool `json:"mixedFive"`
	Cancel bool `json:"cancel"`
	Error bool `json:"error"`
}

type PiNativeReaderId string

const (
	PiNativeReaderIdPi.jsonl.v3.tree PiNativeReaderId = "pi.jsonl.v3.tree"
)

type PiNativeFormatProfile struct {
	ReaderId PiNativeReaderId `json:"readerId"`
	SessionVersion int64 `json:"sessionVersion"`
	Structure string `json:"structure"`
	BranchSelection string `json:"branchSelection"`
}

type RuntimeNativeUnsupportedReason string

const (
	RuntimeNativeUnsupportedReasonReaderNotImplemented RuntimeNativeUnsupportedReason = "reader_not_implemented"
	RuntimeNativeUnsupportedReasonUnsupportedVersion RuntimeNativeUnsupportedReason = "unsupported_version"
	RuntimeNativeUnsupportedReasonUnsupportedStructure RuntimeNativeUnsupportedReason = "unsupported_structure"
	RuntimeNativeUnsupportedReasonInvalidRecord RuntimeNativeUnsupportedReason = "invalid_record"
	RuntimeNativeUnsupportedReasonInvalidTree RuntimeNativeUnsupportedReason = "invalid_tree"
	RuntimeNativeUnsupportedReasonCurrentBranchUnavailable RuntimeNativeUnsupportedReason = "current_branch_unavailable"
)

type PiGuardCheckInput struct {
	Version int64 `json:"version"`
	RequestId string `json:"requestId"`
	SessionId string `json:"sessionId"`
	NodeId string `json:"nodeId"`
	ToolCallId string `json:"toolCallId"`
	ToolName string `json:"toolName"`
	PolicyRevision string `json:"policyRevision"`
	ToolInventorySha256 string `json:"toolInventorySha256"`
	ArgumentsJson string `json:"argumentsJson"`
	ArgumentsSha256 string `json:"argumentsSha256"`
	ExpiresAt string `json:"expiresAt"`
}

type PiGuardDecision struct {
	RequestId string `json:"requestId"`
	SessionId string `json:"sessionId"`
	ToolCallId string `json:"toolCallId"`
	ArgumentsSha256 string `json:"argumentsSha256"`
	PolicyRevision string `json:"policyRevision"`
	Decision string `json:"decision"`
	Reason *PiGuardReason `json:"reason,omitempty"`
	ApprovalId *string `json:"approvalId,omitempty"`
	ExpiresAt string `json:"expiresAt"`
}

type PiGuardHandshake struct {
	Version int64 `json:"version"`
	SessionId string `json:"sessionId"`
	GuardRevision string `json:"guardRevision"`
	PolicyRevision string `json:"policyRevision"`
	ToolInventorySha256 string `json:"toolInventorySha256"`
	Isolation string `json:"isolation"`
	ActiveTools []string `json:"activeTools"`
}

type PiImageTransport = string

type PiModelSelection struct {
	ModelId string `json:"modelId"`
}

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

type RemoteApiTokenScope string

const (
	RemoteApiTokenScopeDevices:read RemoteApiTokenScope = "devices:read"
	RemoteApiTokenScopeDevices:manage RemoteApiTokenScope = "devices:manage"
	RemoteApiTokenScopeDevices:delete RemoteApiTokenScope = "devices:delete"
)

type RemoteApiTokenCreateInput struct {
	Name string `json:"name"`
	Scopes []RemoteApiTokenScope `json:"scopes"`
	ExpiresAt *string `json:"expiresAt,omitempty"`
}

type RemoteApiTokenView struct {
	TokenId string `json:"tokenId"`
	Name string `json:"name"`
	TokenPrefix string `json:"tokenPrefix"`
	Scopes []RemoteApiTokenScope `json:"scopes"`
	CreatedAt string `json:"createdAt"`
	LastUsedAt *string `json:"lastUsedAt,omitempty"`
	ExpiresAt string `json:"expiresAt"`
	Status string `json:"status"`
	RevokedAt *string `json:"revokedAt,omitempty"`
}

type RemoteApiTokenIssueReplayView struct {
	Token RemoteApiTokenView `json:"token"`
	SecretAvailable bool `json:"secretAvailable"`
}

type RemoteApiTokenIssuedView struct {
	Token RemoteApiTokenView `json:"token"`
	SecretAvailable bool `json:"secretAvailable"`
	Secret string `json:"secret"`
}

type RemoteApiTokenPage struct {
	Items []RemoteApiTokenView `json:"items"`
	HasMore bool `json:"hasMore"`
	NextCursor *string `json:"nextCursor,omitempty"`
}

type RemoteApiTokenRevocationView struct {
	TokenId string `json:"tokenId"`
	RevokedAt string `json:"revokedAt"`
	Status string `json:"status"`
}

type RemoteAuthorizedRoot struct {
	RootId string `json:"rootId"`
	DisplayName string `json:"displayName"`
	Version int64 `json:"version"`
}

type RemoteDeviceDeletionView struct {
	WorkerId string `json:"workerId"`
	DeletedAt string `json:"deletedAt"`
	ExecutionMayStillBeRunning bool `json:"executionMayStillBeRunning"`
}

type RemoteDeviceView struct {
	WorkerId string `json:"workerId"`
	DeviceName string `json:"deviceName"`
	Platform string `json:"platform"`
	Architecture string `json:"architecture"`
	Status string `json:"status"`
	WorkerStoreId string `json:"workerStoreId"`
	CapabilityRevision int64 `json:"capabilityRevision"`
	ObservedAt string `json:"observedAt"`
	LastSeenAt *string `json:"lastSeenAt,omitempty"`
	PairedAt string `json:"pairedAt"`
	RevokedAt *string `json:"revokedAt,omitempty"`
	Online *bool `json:"online,omitempty"`
	BusySnapshotFresh *bool `json:"busySnapshotFresh,omitempty"`
	SupportedWireRevisions []int64 `json:"supportedWireRevisions,omitempty"`
	RemoteAccess *string `json:"remoteAccess,omitempty"`
	DisplayName *string `json:"displayName,omitempty"`
	Version *int64 `json:"version,omitempty"`
	SuspendedAt *string `json:"suspendedAt,omitempty"`
}

type RemoteDevicePage struct {
	Items []RemoteDeviceView `json:"items"`
	HasMore bool `json:"hasMore"`
	NextCursor *string `json:"nextCursor,omitempty"`
}

type RemoteDevicePatchInput struct {
	ExpectedVersion int64 `json:"expectedVersion"`
	RemoteAccess *string `json:"remoteAccess,omitempty"`
	DisplayName *string `json:"displayName,omitempty"`
}

type RemoteHttpErrorDetail struct {
	Fields []string `json:"fields,omitempty"`
	CurrentVersion *int64 `json:"currentVersion,omitempty"`
	RetryAfterSeconds *int64 `json:"retryAfterSeconds,omitempty"`
}

type RemoteHttpError struct {
	Code ErrorCode `json:"code"`
	Message string `json:"message"`
	Retryable bool `json:"retryable"`
	Detail *RemoteHttpErrorDetail `json:"detail,omitempty"`
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
