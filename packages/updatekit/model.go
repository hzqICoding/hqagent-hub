package updatekit

import "time"

const (
	StatusIdle           = "idle"
	StatusChecking       = "checking"
	StatusUpToDate       = "up_to_date"
	StatusAvailable      = "available"
	StatusDownloading    = "downloading"
	StatusDownloaded     = "downloaded"
	StatusVerifying      = "verifying"
	StatusReadyToInstall = "ready_to_install"
	StatusInstalling     = "installing"
	StatusRestarting     = "restarting"
	StatusCancelled      = "cancelled"
	StatusFailed         = "failed"
)

type Package struct {
	TargetKey          string `json:"targetKey,omitempty"`
	SignatureAlgorithm string `json:"signatureAlgorithm,omitempty"`
	KeyID              string `json:"keyId,omitempty"`
	Type               string `json:"type"`
	OS                 string `json:"os"`
	Arch               string `json:"arch"`
	URL                string `json:"url"`
	Size               int64  `json:"size"`
	SHA256             string `json:"sha256"`
	Signature          string `json:"signature"`
}

type Release struct {
	Version                 string    `json:"version"`
	Build                   string    `json:"build"`
	Channel                 string    `json:"channel"`
	PublishedAt             time.Time `json:"publishedAt"`
	Mandatory               bool      `json:"mandatory"`
	MinimumSupportedVersion string    `json:"minimumSupportedVersion,omitempty"`
	Title                   string    `json:"title"`
	ReleaseNotes            string    `json:"releaseNotes,omitempty"`
	ReleaseNotesURL         string    `json:"releaseNotesUrl,omitempty"`
	Package                 Package   `json:"package"`
}

// ChangelogItem is the client-facing release-note projection. Package URLs,
// hashes and signatures stay on Release because the history dialog does not
// need artifact credentials or download metadata.
type ChangelogItem struct {
	Version     string `json:"version"`
	Build       string `json:"build"`
	ReleaseDate string `json:"releaseDate"`
	Channel     string `json:"channel"`
	IsCurrent   bool   `json:"isCurrent"`
	Title       string `json:"title"`
	Content     string `json:"content"`
}

type CheckRequest struct {
	TargetKey      string `json:"targetKey"`
	AppID          string `json:"appId"`
	CurrentVersion string `json:"currentVersion"`
	Channel        string `json:"channel"`
	OS             string `json:"os"`
	Arch           string `json:"arch"`
	InstallType    string `json:"installType"`
}

type CheckResponse struct {
	UpdateAvailable bool      `json:"updateAvailable"`
	ServerTime      time.Time `json:"serverTime"`
	Release         *Release  `json:"release"`
}

type CheckCommand struct {
	Manual  bool   `json:"manual"`
	Channel string `json:"channel,omitempty"`
}

type DownloadCommand struct {
	Version string `json:"version,omitempty"`
}

type InstallCommand struct {
	Confirmed           bool `json:"confirmed"`
	StopRunningTasks    bool `json:"stopRunningTasks"`
	RestartAfterInstall bool `json:"restartAfterInstall"`
}

type DownloadProgress struct {
	DownloadedBytes  int64   `json:"downloadedBytes"`
	TotalBytes       int64   `json:"totalBytes"`
	Percent          float64 `json:"percent"`
	BytesPerSecond   int64   `json:"bytesPerSecond"`
	RemainingSeconds int64   `json:"remainingSeconds"`
}

type StateError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
	Detail  string `json:"detail,omitempty"`
}

type State struct {
	Status         string            `json:"status"`
	CurrentVersion string            `json:"currentVersion"`
	Channel        string            `json:"channel"`
	InstallType    string            `json:"installType"`
	Release        *Release          `json:"release,omitempty"`
	Progress       *DownloadProgress `json:"progress,omitempty"`
	PackagePath    string            `json:"packagePath,omitempty"`
	LastCheckedAt  *time.Time        `json:"lastCheckedAt,omitempty"`
	UpdatedAt      time.Time         `json:"updatedAt"`
	Error          *StateError       `json:"error,omitempty"`
}

// UpdateResult is written by the independent updater and consumed by the new
// application process on its next startup. AcknowledgedAt allows the frontend
// to present the result exactly once without deleting diagnostic evidence.
type UpdateResult struct {
	Success         bool       `json:"success"`
	PreviousVersion string     `json:"previousVersion,omitempty"`
	Version         string     `json:"version"`
	FinishedAt      time.Time  `json:"finishedAt"`
	Error           string     `json:"error,omitempty"`
	AcknowledgedAt  *time.Time `json:"acknowledgedAt,omitempty"`
}
