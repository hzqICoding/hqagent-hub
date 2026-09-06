package product

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"path/filepath"
	"strconv"
	"time"

	"hqagent.local/protocol"
	kit "hqupdatekit.local/updatekit"
)

type HubClient struct {
	Policy   kit.PlanPolicy
	AgentPID int
}

func (h HubClient) request(ctx context.Context, method, path string, out any) error {
	var d protocol.HubRuntimeDescriptor
	if err := kit.ReadJSON(filepath.Join(h.Policy.DataDirectory, "runtime", "hub.json"), &d); err != nil {
		return err
	}
	if d.SchemaVersion != 1 || d.Port < 1024 || d.Port > 65535 || d.Pid <= 0 || len(d.Token) < 43 || d.BaseUrl != "http://127.0.0.1:"+strconv.FormatInt(d.Port, 10) || d.ProtocolVersion != WireVersion {
		return fmt.Errorf("invalid Hub descriptor")
	}
	r, err := http.NewRequestWithContext(ctx, method, d.BaseUrl+path, nil)
	if err != nil {
		return err
	}
	r.Header.Set("Authorization", "Bearer "+d.Token)
	client := &http.Client{Transport: &http.Transport{Proxy: nil}, Timeout: 10 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	defer client.CloseIdleConnections()
	response, err := client.Do(r)
	if err != nil {
		return fmt.Errorf("Hub unavailable")
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return fmt.Errorf("Hub rejected update coordination")
	}
	// W1's API envelope is not generated for Go yet. Decode its container as
	// raw fields; all domain payloads below use generated protocol DTOs.
	var envelope map[string]json.RawMessage
	if err = json.NewDecoder(io.LimitReader(response.Body, 2<<20)).Decode(&envelope); err != nil {
		return err
	}
	if !bytes.Equal(bytes.TrimSpace(envelope["success"]), []byte("true")) {
		return fmt.Errorf("Hub coordination failed")
	}
	return json.Unmarshal(envelope["data"], out)
}

func (h HubClient) Prepare(ctx context.Context, r kit.Release, path string) error {
	var drain protocol.DrainProgress
	if err := h.request(ctx, "GET", "/internal/drain/state", &drain); err != nil {
		return err
	}
	if drain.Step != protocol.DrainStepReady || drain.BackupCompleted == nil || !*drain.BackupCompleted || drain.ActiveTasksRemaining != 0 || drain.Percent != 100 {
		return fmt.Errorf("Hub drain/backup is not ready")
	}
	processes := []kit.Process{}
	pids := []int{}
	hasSelf := false
	for _, p := range drain.WaitPids {
		if p.Component == "update-agent" && p.Pid == int64(h.AgentPID) {
			hasSelf = true
		}
		processes = append(processes, kit.Process{Component: p.Component, PID: int(p.Pid)})
		pids = append(pids, int(p.Pid))
	}
	if !hasSelf {
		return fmt.Errorf("drain must include this Update Agent")
	}
	// Consume W1's SQLite Backup API. Do not copy an open hub.db or infer a
	// snapshot by choosing the newest filename in a directory.
	var backup map[string]json.RawMessage
	if err := h.request(ctx, "POST", "/internal/backup/database", &backup); err != nil {
		return err
	}
	var snapshot string
	var complete bool
	if err := json.Unmarshal(backup["backupPath"], &snapshot); err != nil {
		return err
	}
	if err := json.Unmarshal(backup["backupCompleted"], &complete); err != nil || !complete {
		return fmt.Errorf("consistent database backup required")
	}
	plan := MakePlan(h.Policy, r, path, processes, pids, snapshot)
	if err := kit.ValidatePlan(plan, h.Policy); err != nil {
		return err
	}
	if err := kit.AtomicJSON(h.Policy.PlanPath(), plan); err != nil {
		return err
	}
	return kit.LaunchHelper(filepath.Join(h.Policy.InstallDirectory, "hqagent-updater.exe"), h.Policy)
}
func MakePlan(p kit.PlanPolicy, r kit.Release, path string, processes []kit.Process, pids []int, snapshot string) kit.UpdatePlan {
	return kit.UpdatePlan{SchemaVersion: 2, AppID: p.AppID, CurrentVersion: Version, TargetVersion: r.Version, TargetKey: p.TargetKey, PackagePath: path, InstallStrategy: "windows-nsis", InstallScope: "current-user", InstallDirectory: p.InstallDirectory, DataDirectory: p.DataDirectory, WaitPIDs: pids, Processes: processes, Backup: kit.BackupPlan{Database: true, Config: true, ProgramFiles: true, DatabaseSnapshot: snapshot, PreviousInstaller: filepath.Join(p.UpdatesDirectory, "installed", "installer.exe")}, Restart: []kit.RestartCommand{{Component: "core", Command: p.AllowedExecutables["core"]}, {Component: "update-agent", Command: p.AllowedExecutables["update-agent"]}, {Component: "desktop", Command: p.AllowedExecutables["desktop"]}}, HealthChecks: []kit.HealthCheck{{Type: "process", Component: "core", TimeoutSeconds: 30}, {Type: "protocol", ExpectedVersion: WireVersion, TimeoutSeconds: 30}}, RollbackOnFailure: true, Release: r}
}
