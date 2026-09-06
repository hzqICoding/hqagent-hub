package product

import (
	"os"
	"path/filepath"
	"time"

	"hqagent.local/protocol"
	kit "hqupdatekit.local/updatekit"
)

func ptr[T any](v T) *T { return &v }
func StateDTO(s kit.State) protocol.UpdateStateView {
	v := protocol.UpdateStateView{Phase: protocol.UpdatePhase(s.Status), CurrentVersion: s.CurrentVersion, Channel: protocol.UpdateChannel(s.Channel), CanInstallNow: s.Status == kit.StatusReadyToInstall, LastCheckedAt: time.Unix(0, 0).UTC().Format(time.RFC3339), ProtocolVersion: ptr(WireVersion)}
	if s.LastCheckedAt != nil {
		v.LastCheckedAt = s.LastCheckedAt.UTC().Format(time.RFC3339Nano)
	}
	if s.Release != nil {
		r := s.Release
		v.LatestVersion = &r.Version
		v.ReleaseNotes = &r.ReleaseNotes
		v.Mandatory = &r.Mandatory
		v.TargetKey = ptr("windows-amd64-installer")
	}
	if s.Progress != nil {
		p := s.Progress
		v.DownloadProgress = &p.Percent
		v.DownloadBytes = &p.DownloadedBytes
		v.TotalBytes = &p.TotalBytes
		v.SpeedBytesPerSecond = &p.BytesPerSecond
		v.EtaSeconds = &p.RemainingSeconds
	}
	if s.Error != nil {
		v.Error = ptr("update operation failed; inspect local diagnostics")
		v.ErrorCode = ptr(protocol.ErrorCodeInternal)
		if s.Error.Code == "UPDATE_VERIFY_FAILED" {
			v.ErrorCode = ptr(protocol.ErrorCodeUpdateVerifyFailed)
		}
	}
	return v
}
func ReleaseDTO(r kit.Release) protocol.ReleaseInfo {
	return protocol.ReleaseInfo{Version: r.Version, Channel: protocol.UpdateChannel(r.Channel), TargetKey: "windows-amd64-installer", PublishedAt: r.PublishedAt.UTC().Format(time.RFC3339Nano), SizeBytes: r.Package.Size, Sha256: r.Package.SHA256, Signature: &r.Package.Signature, SignatureAlgorithm: &r.Package.SignatureAlgorithm, KeyId: &r.Package.KeyID, Mandatory: r.Mandatory, MinimumSupportedVersion: &r.MinimumSupportedVersion, ReleaseNotes: &r.ReleaseNotes, InstallStrategy: ptr(protocol.InstallStrategyWindowsNsis)}
}
func ResultDTO(r kit.Result) protocol.UpdateResultView {
	v := protocol.UpdateResultView{SchemaVersion: 2, AppId: "hqagent-hub", FromVersion: r.FromVersion, ToVersion: r.ToVersion, Success: r.Success, FinishedAt: r.FinishedAt.UTC().Format(time.RFC3339Nano), Acknowledged: false, InstallStrategy: ptr(protocol.InstallStrategyWindowsNsis), HealthCheckPassed: ptr(r.Success), RolledBack: &r.RolledBack, RollbackSucceeded: &r.RollbackSucceeded}
	if r.Error != "" {
		v.Error = ptr("update failed; recovery details retained locally")
		v.ErrorCode = ptr(protocol.ErrorCodeInternal)
	}
	if r.RestoredDatabaseBackup != "" {
		v.RestoredDatabaseBackup = &r.RestoredDatabaseBackup
	}
	for _, h := range r.HealthChecks {
		v.HealthChecks = append(v.HealthChecks, protocol.HealthCheckOutcome{Type: h.Type, Component: ptr(h.Component), Passed: h.Passed, DurationMs: ptr(h.DurationMS)})
	}
	return v
}

type Store struct{ Policy kit.PlanPolicy }

func (s Store) Load() (kit.State, error) {
	var state kit.State
	err := kit.ReadJSON(filepath.Join(s.Policy.UpdatesDirectory, "private-state.json"), &state)
	if err == nil && state.Status == "succeeded" && state.Release != nil && state.Release.Version == Version {
		state.CurrentVersion = Version
	}
	return state, err
}
func (s Store) Save(state kit.State) error {
	if err := kit.AtomicJSON(filepath.Join(s.Policy.UpdatesDirectory, "private-state.json"), state); err != nil {
		return err
	}
	return kit.AtomicJSON(filepath.Join(s.Policy.UpdatesDirectory, "update-state.json"), StateDTO(state))
}
func (s Store) SaveResult(r kit.Result) error {
	if err := kit.AtomicJSON(filepath.Join(s.Policy.UpdatesDirectory, "recovery-diagnostic.json"), r); err != nil {
		return err
	}
	return kit.AtomicJSON(filepath.Join(s.Policy.UpdatesDirectory, "update-result.json"), ResultDTO(r))
}
func (s Store) SavePhase(phase string) error {
	state, err := s.Load()
	if err != nil {
		return err
	}
	state.Status = phase
	state.UpdatedAt = time.Now().UTC()
	return s.Save(state)
}
func (s Store) Result() (*protocol.UpdateResultView, error) {
	var result protocol.UpdateResultView
	err := kit.ReadJSON(filepath.Join(s.Policy.UpdatesDirectory, "update-result.json"), &result)
	if os.IsNotExist(err) {
		return nil, nil
	}
	return &result, err
}
