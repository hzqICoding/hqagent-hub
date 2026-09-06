package updatekit

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func planFixture(t *testing.T) (UpdatePlan, PlanPolicy, *PackageVerifier) {
	t.Helper()
	root := t.TempDir()
	p := PlanPolicy{AppID: "product", TargetKey: "windows-amd64-installer", OS: "windows", Arch: "amd64", DataDirectory: filepath.Join(root, "data-root"), InstallDirectory: filepath.Join(root, "Programs", "product"), UpdatesDirectory: filepath.Join(root, "data-root", "updates"), ProtocolVersion: "1.0", AllowedExecutables: map[string]string{"core": "core.exe", "desktop": "desktop.exe", "update-agent": "agent.exe"}}
	for _, d := range []string{p.InstallDirectory, filepath.Join(p.DataDirectory, "config"), filepath.Join(p.DataDirectory, "data"), filepath.Join(p.UpdatesDirectory, "staging"), filepath.Join(p.UpdatesDirectory, "backup"), filepath.Join(p.UpdatesDirectory, "installed")} {
		if err := os.MkdirAll(d, 0700); err != nil {
			t.Fatal(err)
		}
	}
	packagePath := filepath.Join(p.UpdatesDirectory, "staging", "setup.exe")
	snapshot := filepath.Join(p.UpdatesDirectory, "backup", "before.db")
	installer := filepath.Join(p.UpdatesDirectory, "installed", "installer.exe")
	for path, data := range map[string]string{packagePath: "signed fake installer", snapshot: "snapshot", installer: "previous-installer", filepath.Join(p.InstallDirectory, "version"): "old", filepath.Join(p.DataDirectory, "config", "config.json"): "original", filepath.Join(p.DataDirectory, "data", "hub.db"): "snapshot"} {
		if err := os.WriteFile(path, []byte(data), 0600); err != nil {
			t.Fatal(err)
		}
	}
	r, v := signedRelease(t, []byte("signed fake installer"))
	plan := UpdatePlan{SchemaVersion: 2, AppID: p.AppID, CurrentVersion: "0.1.0", TargetVersion: "0.2.0", TargetKey: p.TargetKey, PackagePath: packagePath, InstallStrategy: "windows-nsis", InstallScope: "current-user", InstallDirectory: p.InstallDirectory, DataDirectory: p.DataDirectory, WaitPIDs: []int{101, 102, 103, 104}, Processes: []Process{{"desktop", 101}, {"core", 102}, {"update-agent", 103}, {"agent-worker", 104}}, Backup: BackupPlan{Database: true, Config: true, ProgramFiles: true, DatabaseSnapshot: snapshot, PreviousInstaller: installer}, Restart: []RestartCommand{{Component: "core", Command: "core.exe"}, {Component: "desktop", Command: "desktop.exe"}, {Component: "update-agent", Command: "agent.exe"}}, HealthChecks: []HealthCheck{{Type: "process", Component: "core", TimeoutSeconds: 1}, {Type: "protocol", ExpectedVersion: "1.0", TimeoutSeconds: 1}}, RollbackOnFailure: true, Release: r}
	if err := ValidatePlan(plan, p); err != nil {
		t.Fatal(err)
	}
	return plan, p, v
}
func TestPlanRejectsUntrustedPathsAndIncompleteSchema(t *testing.T) {
	plan, p, _ := planFixture(t)
	mutations := map[string]func(*UpdatePlan){"schema": func(x *UpdatePlan) { x.SchemaVersion = 1 }, "scope": func(x *UpdatePlan) { x.InstallScope = "system" }, "directory": func(x *UpdatePlan) { x.InstallDirectory = filepath.Dir(p.InstallDirectory) }, "data": func(x *UpdatePlan) { x.DataDirectory = filepath.Dir(p.DataDirectory) }, "package": func(x *UpdatePlan) { x.PackagePath = filepath.Join(p.InstallDirectory, "setup.exe") }, "snapshot": func(x *UpdatePlan) { x.Backup.DatabaseSnapshot = filepath.Join(p.DataDirectory, "data", "hub.db") }, "missing-backup": func(x *UpdatePlan) { x.Backup.Config = false }, "missing-worker": func(x *UpdatePlan) { x.WaitPIDs = x.WaitPIDs[:3] }, "missing-desktop": func(x *UpdatePlan) { x.Processes = x.Processes[1:]; x.WaitPIDs = x.WaitPIDs[1:] }, "command": func(x *UpdatePlan) { x.Restart[0].Command = "powershell.exe" }, "args": func(x *UpdatePlan) { x.Restart[0].Args = []string{"-Command", "anything"} }, "health": func(x *UpdatePlan) { x.HealthChecks = nil }, "downgrade": func(x *UpdatePlan) { x.TargetVersion = "0.0.1" }, "no-rollback": func(x *UpdatePlan) { x.RollbackOnFailure = false }}
	for name, mutate := range mutations {
		t.Run(name, func(t *testing.T) {
			b, _ := json.Marshal(plan)
			var bad UpdatePlan
			if err := json.Unmarshal(b, &bad); err != nil {
				t.Fatal(err)
			}
			mutate(&bad)
			if err := ValidatePlan(bad, p); err == nil {
				t.Fatal("unsafe plan accepted")
			}
		})
	}
	if err := AtomicJSON(p.PlanPath(), plan); err != nil {
		t.Fatal(err)
	}
	if _, err := ReadPlan(p.PlanPath(), p); err != nil {
		t.Fatal(err)
	}
	if _, err := ReadPlan(filepath.Join(p.DataDirectory, "external-plan.json"), p); err == nil {
		t.Fatal("uncontrolled Plan accepted")
	}
	b, _ := json.Marshal(plan)
	var extra map[string]any
	_ = json.Unmarshal(b, &extra)
	extra["shellCommand"] = "anything"
	if err := AtomicJSON(p.PlanPath(), extra); err != nil {
		t.Fatal(err)
	}
	if _, err := ReadPlan(p.PlanPath(), p); err == nil {
		t.Fatal("unknown Plan property accepted")
	}
}

type installFunc func(context.Context, UpdatePlan) error

func (installFunc) Name() string                                    { return "windows-nsis" }
func (f installFunc) Install(c context.Context, p UpdatePlan) error { return f(c, p) }

type fakeProcess struct {
	stopped bool
	fail    bool
}

func (p *fakeProcess) PID() int    { return 999 }
func (p *fakeProcess) Alive() bool { return !p.stopped }
func (p *fakeProcess) Stop(context.Context) error {
	if p.fail {
		return errors.New("cannot stop")
	}
	p.stopped = true
	return nil
}

type fakeLauncher struct{ failStop bool }

func (l fakeLauncher) Start(string, []string) (RunningProcess, error) {
	return &fakeProcess{fail: l.failStop}, nil
}

type healthFunc func(context.Context, UpdatePlan, map[string]RunningProcess) error

func (f healthFunc) Check(c context.Context, p UpdatePlan, processes map[string]RunningProcess) error {
	return f(c, p, processes)
}

type resultRecorder struct{ value Result }

func (r *resultRecorder) SaveResult(v Result) error { r.value = v; return nil }
func TestHelperWaitFailureNeverInstalls(t *testing.T) {
	plan, p, v := planFixture(t)
	if err := AtomicJSON(p.PlanPath(), plan); err != nil {
		t.Fatal(err)
	}
	called := false
	results := &resultRecorder{}
	h := Helper{Policy: p, Verifier: v, Strategy: installFunc(func(context.Context, UpdatePlan) error { called = true; return nil }), Health: healthFunc(func(context.Context, UpdatePlan, map[string]RunningProcess) error { return nil }), Results: results, Wait: func(context.Context, []int) error { return errors.New("worker still running") }}
	if _, err := h.Run(context.Background(), p.PlanPath()); err == nil || called {
		t.Fatal("installed despite failed process wait")
	}
	if results.value.Success {
		t.Fatal("false success result")
	}
}

func TestInstallerTimeoutDoesNotRaceUncontainedChildren(t *testing.T) {
	plan, p, v := planFixture(t)
	if err := AtomicJSON(p.PlanPath(), plan); err != nil {
		t.Fatal(err)
	}
	h := Helper{Policy: p, Verifier: v, Results: &resultRecorder{}, Wait: func(context.Context, []int) error { return nil }, Strategy: installFunc(func(context.Context, UpdatePlan) error { return ErrInstallerNotQuiescent }), Health: healthFunc(func(context.Context, UpdatePlan, map[string]RunningProcess) error {
		t.Fatal("health called after uncontained installer timeout")
		return nil
	})}
	result, err := h.Run(context.Background(), p.PlanPath())
	if !errors.Is(err, ErrInstallerNotQuiescent) || result.Success || result.RolledBack {
		t.Fatalf("result=%+v err=%v", result, err)
	}
	backups, _ := filepath.Glob(filepath.Join(p.UpdatesDirectory, "backup", "transaction-*", "hub.db"))
	if len(backups) != 1 {
		t.Fatal("recovery materials lost")
	}
}
func TestHelperHealthySuccessAndRollbackFailures(t *testing.T) {
	for _, mode := range []string{"healthy", "unhealthy", "installer-failure", "cannot-stop"} {
		t.Run(mode, func(t *testing.T) {
			plan, p, v := planFixture(t)
			if err := AtomicJSON(p.PlanPath(), plan); err != nil {
				t.Fatal(err)
			}
			results := &resultRecorder{}
			h := Helper{Policy: p, Verifier: v, Results: results, Launcher: fakeLauncher{failStop: mode == "cannot-stop"}, Wait: func(context.Context, []int) error { return nil }, Strategy: installFunc(func(ctx context.Context, p UpdatePlan) error {
				if err := os.WriteFile(filepath.Join(p.InstallDirectory, "version"), []byte("new"), 0600); err != nil {
					return err
				}
				if err := os.WriteFile(filepath.Join(p.DataDirectory, "data", "hub.db"), []byte("migrated"), 0600); err != nil {
					return err
				}
				if mode == "installer-failure" {
					return errors.New("NSIS aborted")
				}
				return nil
			}), Health: healthFunc(func(ctx context.Context, p UpdatePlan, processes map[string]RunningProcess) error {
				if mode != "healthy" && p.TargetVersion == "0.2.0" {
					return errors.New("new version unhealthy")
				}
				return nil
			})}
			result, err := h.Run(context.Background(), p.PlanPath())
			if mode == "healthy" {
				if err != nil || !result.Success || result.RolledBack {
					t.Fatalf("result=%+v err=%v", result, err)
				}
				return
			}
			if err == nil || result.Success {
				t.Fatal("failed upgrade reported success")
			}
			if mode == "cannot-stop" {
				if result.RollbackSucceeded || result.Phase != "rollback_failed" {
					t.Fatal(result)
				}
				b, _ := os.ReadFile(filepath.Join(p.InstallDirectory, "version"))
				if string(b) != "new" {
					t.Fatal("restored files while process still alive")
				}
				return
			}
			if !result.RollbackSucceeded || result.Phase != "rollback_succeeded" {
				t.Fatal(result)
			}
			b, _ := os.ReadFile(filepath.Join(p.InstallDirectory, "version"))
			if string(b) != "old" {
				t.Fatal("old program not restored")
			}
			b, _ = os.ReadFile(filepath.Join(p.DataDirectory, "data", "hub.db"))
			if string(b) != "snapshot" {
				t.Fatal("DB snapshot not restored")
			}
		})
	}
}
