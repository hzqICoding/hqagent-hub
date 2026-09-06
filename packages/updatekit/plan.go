package updatekit

import (
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strings"
)

// UpdatePlan is HQUpdateKit's versioned disk contract, not a Hub API DTO.
// The trusted policy is supplied by the product, never loaded from this file.
type UpdatePlan struct {
	SchemaVersion     int              `json:"schemaVersion"`
	AppID             string           `json:"appId"`
	CurrentVersion    string           `json:"currentVersion"`
	TargetVersion     string           `json:"targetVersion"`
	TargetKey         string           `json:"targetKey"`
	PackagePath       string           `json:"packagePath"`
	InstallStrategy   string           `json:"installStrategy"`
	InstallScope      string           `json:"installScope"`
	InstallDirectory  string           `json:"installDirectory"`
	DataDirectory     string           `json:"dataDirectory"`
	WaitPIDs          []int            `json:"waitPids"`
	Processes         []Process        `json:"processes"`
	Backup            BackupPlan       `json:"backup"`
	Restart           []RestartCommand `json:"restart"`
	HealthChecks      []HealthCheck    `json:"healthChecks"`
	RollbackOnFailure bool             `json:"rollbackOnFailure"`
	Release           Release          `json:"release"`
}
type Process struct {
	Component string `json:"component"`
	PID       int    `json:"pid"`
}
type BackupPlan struct {
	Database          bool   `json:"database"`
	Config            bool   `json:"config"`
	ProgramFiles      bool   `json:"programFiles"`
	DatabaseSnapshot  string `json:"databaseSnapshot"`
	PreviousInstaller string `json:"previousInstaller"`
}
type RestartCommand struct {
	Component string   `json:"component"`
	Command   string   `json:"command"`
	Args      []string `json:"args,omitempty"`
}
type HealthCheck struct {
	Type            string `json:"type"`
	Component       string `json:"component,omitempty"`
	TimeoutSeconds  int    `json:"timeoutSeconds"`
	ExpectedVersion string `json:"expectedVersion,omitempty"`
}
type PlanPolicy struct {
	AppID, TargetKey, OS, Arch, InstallDirectory, DataDirectory, UpdatesDirectory string
	AllowedExecutables                                                            map[string]string
	ProtocolVersion                                                               string
}

func (p PlanPolicy) PlanPath() string { return filepath.Join(p.UpdatesDirectory, "update-plan.json") }

func ValidatePlan(plan UpdatePlan, policy PlanPolicy) error {
	if plan.SchemaVersion != 2 || plan.AppID != policy.AppID || plan.TargetKey != policy.TargetKey || plan.InstallStrategy != "windows-nsis" || plan.InstallScope != "current-user" || !plan.RollbackOnFailure {
		return fmt.Errorf("unsupported or incomplete Plan v2 policy")
	}
	for _, v := range []string{plan.CurrentVersion, plan.TargetVersion} {
		if _, err := ParseVersion(v); err != nil {
			return err
		}
	}
	if CompareVersions(plan.TargetVersion, plan.CurrentVersion) <= 0 {
		return fmt.Errorf("downgrade rejected")
	}
	if !samePath(plan.InstallDirectory, policy.InstallDirectory) || !samePath(plan.DataDirectory, policy.DataDirectory) {
		return fmt.Errorf("installation scope or directory mismatch")
	}
	for _, p := range []string{plan.InstallDirectory, plan.DataDirectory, policy.UpdatesDirectory} {
		if err := RejectLinks(p); err != nil {
			return err
		}
	}
	if err := Within(filepath.Join(policy.UpdatesDirectory, "staging"), plan.PackagePath); err != nil {
		return err
	}
	if !strings.EqualFold(filepath.Ext(plan.PackagePath), ".exe") {
		return fmt.Errorf("NSIS executable required")
	}
	if err := regular(plan.PackagePath); err != nil {
		return err
	}
	if plan.Release.Version != plan.TargetVersion {
		return fmt.Errorf("release version mismatch")
	}
	if err := ValidateRelease(plan.Release, AppMeta{AppID: policy.AppID, Version: plan.CurrentVersion, TargetKey: policy.TargetKey, OS: policy.OS, Arch: policy.Arch, InstallType: "installer"}, plan.Release.Channel); err != nil {
		return err
	}
	if !plan.Backup.Database || !plan.Backup.Config || !plan.Backup.ProgramFiles {
		return fmt.Errorf("all rollback materials required")
	}
	if err := Within(filepath.Join(policy.UpdatesDirectory, "backup"), plan.Backup.DatabaseSnapshot); err != nil {
		return err
	}
	if filepath.Ext(plan.Backup.DatabaseSnapshot) != ".db" {
		return fmt.Errorf("database snapshot required")
	}
	if err := regular(plan.Backup.DatabaseSnapshot); err != nil {
		return err
	}
	if !samePath(plan.Backup.PreviousInstaller, filepath.Join(policy.UpdatesDirectory, "installed", "installer.exe")) {
		return fmt.Errorf("previous installer path mismatch")
	}
	if err := RejectLinks(plan.Backup.PreviousInstaller); err != nil {
		return err
	}
	if err := regular(plan.Backup.PreviousInstaller); err != nil {
		return err
	}
	components := map[string]bool{}
	pids := map[int]bool{}
	for _, p := range plan.Processes {
		if p.PID <= 0 || pids[p.PID] {
			return fmt.Errorf("invalid or duplicate process")
		}
		switch p.Component {
		case "core", "desktop", "update-agent":
			if components[p.Component] {
				return fmt.Errorf("duplicate component")
			}
		case "agent-worker":
		default:
			return fmt.Errorf("unknown process component")
		}
		components[p.Component] = true
		pids[p.PID] = true
	}
	if !components["core"] || !components["desktop"] || !components["update-agent"] || len(plan.WaitPIDs) != len(pids) {
		return fmt.Errorf("incomplete process inventory")
	}
	for _, pid := range plan.WaitPIDs {
		if !pids[pid] {
			return fmt.Errorf("waitPids does not match process inventory")
		}
		delete(pids, pid)
	}
	seen := map[string]bool{}
	for _, r := range plan.Restart {
		if seen[r.Component] || r.Command == "" || r.Command != policy.AllowedExecutables[r.Component] || filepath.Base(r.Command) != r.Command {
			return fmt.Errorf("restart executable not allowed")
		}
		seen[r.Component] = true
		if len(r.Args) > 0 {
			return fmt.Errorf("arbitrary restart arguments rejected")
		}
	}
	if !seen["core"] || !seen["desktop"] || !seen["update-agent"] || len(seen) != 3 {
		return fmt.Errorf("restart inventory incomplete")
	}
	if len(plan.HealthChecks) != 2 {
		return fmt.Errorf("process and protocol health checks required")
	}
	if plan.HealthChecks[0].Type != "process" || plan.HealthChecks[0].Component != "core" || plan.HealthChecks[1].Type != "protocol" || plan.HealthChecks[1].ExpectedVersion != policy.ProtocolVersion {
		return fmt.Errorf("health check policy mismatch")
	}
	for _, h := range plan.HealthChecks {
		if h.TimeoutSeconds < 1 || h.TimeoutSeconds > 120 {
			return fmt.Errorf("health timeout invalid")
		}
	}
	return nil
}
func ReadPlan(path string, policy PlanPolicy) (UpdatePlan, error) {
	var plan UpdatePlan
	if !samePath(path, policy.PlanPath()) {
		return plan, fmt.Errorf("only controlled update-plan.json is accepted")
	}
	if err := ReadJSON(path, &plan); err != nil {
		return plan, err
	}
	return plan, ValidatePlan(plan, policy)
}
func samePath(a, b string) bool {
	return filepath.IsAbs(a) && filepath.IsAbs(b) && strings.EqualFold(filepath.Clean(a), filepath.Clean(b))
}
func regular(path string) error {
	i, e := os.Stat(path)
	if e != nil {
		return e
	}
	if !i.Mode().IsRegular() {
		return fmt.Errorf("regular file required")
	}
	return nil
}
func SameProcessInventory(a, b []Process) bool { return reflect.DeepEqual(a, b) }
