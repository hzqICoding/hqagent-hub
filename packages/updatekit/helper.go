package updatekit

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"time"
)

type InstallerStrategy interface {
	Name() string
	Install(context.Context, UpdatePlan) error
}
type CommandRunner interface {
	Run(context.Context, string, []string) (int, error)
}
type ExecRunner struct{}

// A killed NSIS parent may have left a child uninstaller running. Until the
// product bundle's process-tree containment is validated, preserve backups and
// report this capability gap instead of racing that child during restoration.
var ErrInstallerNotQuiescent = errors.New("installer process tree could not be proven stopped")

func (ExecRunner) Run(ctx context.Context, path string, args []string) (int, error) {
	c := exec.CommandContext(ctx, path, args...)
	ConfigureChild(c)
	configureInstallerCommand(c, path, args)
	err := c.Run()
	if ctx.Err() != nil {
		return -1, errors.Join(ErrInstallerNotQuiescent, ctx.Err())
	}
	if err == nil {
		return 0, nil
	}
	var exit *exec.ExitError
	if errors.As(err, &exit) {
		return exit.ExitCode(), nil
	}
	return -1, err
}

type NSISStrategy struct {
	Runner  CommandRunner
	Timeout time.Duration
}

func (NSISStrategy) Name() string { return "windows-nsis" }
func (n NSISStrategy) Install(ctx context.Context, p UpdatePlan) error {
	if p.InstallScope != "current-user" || p.InstallStrategy != n.Name() {
		return fmt.Errorf("unsupported NSIS installation scope")
	}
	if n.Runner == nil {
		n.Runner = ExecRunner{}
	}
	if n.Timeout <= 0 {
		n.Timeout = 10 * time.Minute
	}
	ctx, cancel := context.WithTimeout(ctx, n.Timeout)
	defer cancel()
	// NSIS /D must be the last argument. /S is case-sensitive. No Inno flags,
	// no /R (installer must not restart outside the helper's supervision), no
	// elevation verb. The bundle itself must be built with currentUser scope.
	code, err := n.Runner.Run(ctx, p.PackagePath, []string{"/S", "/D=" + p.InstallDirectory})
	if err != nil {
		return err
	}
	switch code {
	case 0:
		return nil
	case 1:
		return fmt.Errorf("NSIS installation cancelled")
	case 2:
		return fmt.Errorf("NSIS installation aborted")
	default:
		return fmt.Errorf("NSIS installation failed with exit code %d", code)
	}
}

type RunningProcess interface {
	PID() int
	Alive() bool
	Stop(context.Context) error
}
type ProcessLauncher interface {
	Start(string, []string) (RunningProcess, error)
}
type ExecLauncher struct{}
type execProcess struct {
	cmd  *exec.Cmd
	done chan struct{}
	mu   sync.Mutex
	err  error
}

func (ExecLauncher) Start(path string, args []string) (RunningProcess, error) {
	c := exec.Command(path, args...)
	c.Dir = filepath.Dir(path)
	ConfigureChild(c)
	if err := c.Start(); err != nil {
		return nil, err
	}
	p := &execProcess{cmd: c, done: make(chan struct{})}
	go func() { err := c.Wait(); p.mu.Lock(); p.err = err; p.mu.Unlock(); close(p.done) }()
	return p, nil
}
func (p *execProcess) PID() int { return p.cmd.Process.Pid }
func (p *execProcess) Alive() bool {
	select {
	case <-p.done:
		return false
	default:
		return true
	}
}
func (p *execProcess) Stop(ctx context.Context) error {
	if !p.Alive() {
		return nil
	}
	if err := p.cmd.Process.Kill(); err != nil && !errors.Is(err, os.ErrProcessDone) {
		return err
	}
	select {
	case <-p.done:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

type HealthOutcome struct {
	Type, Component, Detail string
	Passed                  bool
	DurationMS              int64
}
type Result struct {
	FromVersion, ToVersion, Phase, Error, RestoredDatabaseBackup string
	Success, RolledBack, RollbackSucceeded                       bool
	FinishedAt                                                   time.Time
	HealthChecks                                                 []HealthOutcome
}
type ResultSink interface{ SaveResult(Result) error }
type HelperStateSink interface{ SavePhase(string) error }
type HealthProbe interface {
	Check(context.Context, UpdatePlan, map[string]RunningProcess) error
}
type Helper struct {
	Policy      PlanPolicy
	Verifier    Verifier
	Strategy    InstallerStrategy
	Launcher    ProcessLauncher
	Health      HealthProbe
	Results     ResultSink
	States      HelperStateSink
	Wait        func(context.Context, []int) error
	WaitTimeout time.Duration
}

func (h Helper) Run(ctx context.Context, planPath string) (result Result, returned error) {
	plan, err := ReadPlan(planPath, h.Policy)
	if err != nil {
		return result, err
	}
	if h.Verifier == nil || h.Strategy == nil || h.Health == nil || h.Results == nil || h.Strategy.Name() != plan.InstallStrategy {
		return result, fmt.Errorf("helper dependencies incomplete")
	}
	if h.Launcher == nil {
		h.Launcher = ExecLauncher{}
	}
	if h.Wait == nil {
		h.Wait = WaitPIDs
	}
	if h.WaitTimeout <= 0 {
		h.WaitTimeout = 60 * time.Second
	}
	result = Result{FromVersion: plan.CurrentVersion, ToVersion: plan.TargetVersion, Phase: StatusFailed}
	defer func() {
		result.FinishedAt = time.Now().UTC()
		if returned != nil {
			result.Error = returned.Error()
		}
		returned = errors.Join(returned, h.Results.SaveResult(result))
		if h.States != nil {
			returned = errors.Join(returned, h.States.SavePhase(result.Phase))
		}
	}()
	if err = h.Verifier.Verify(ctx, plan.Release, plan.PackagePath); err != nil {
		return result, err
	}
	waitCtx, cancel := context.WithTimeout(ctx, h.WaitTimeout)
	err = h.Wait(waitCtx, plan.WaitPIDs)
	cancel()
	if err != nil {
		return result, err
	}
	// Recheck every path and both signatures after the wait: a deferred package
	// is never trusted merely because it was previously verified by the Agent.
	if err = ValidatePlan(plan, h.Policy); err != nil {
		return result, err
	}
	if err = h.Verifier.Verify(ctx, plan.Release, plan.PackagePath); err != nil {
		return result, err
	}
	backup, err := h.backup(plan)
	if err != nil {
		return result, err
	}
	if h.States != nil {
		if err = h.States.SavePhase(StatusInstalling); err != nil {
			return result, err
		}
	}
	started := map[string]RunningProcess{}
	err = h.Strategy.Install(ctx, plan)
	if errors.Is(err, ErrInstallerNotQuiescent) {
		result.Phase = StatusFailed
		return result, err
	}
	if err == nil {
		err = h.start(plan, started)
	}
	if err == nil {
		result.Phase = "health_checking"
		if h.States != nil {
			err = h.States.SavePhase(result.Phase)
		}
		if err == nil {
			begin := time.Now()
			healthCtx, healthCancel := context.WithTimeout(ctx, time.Duration(plan.HealthChecks[1].TimeoutSeconds)*time.Second)
			err = h.Health.Check(healthCtx, plan, started)
			healthCancel()
			result.HealthChecks = []HealthOutcome{{Type: "protocol", Component: "core", Passed: err == nil, DurationMS: time.Since(begin).Milliseconds()}}
		}
	}
	if err == nil {
		// Advance the rollback installer only after healthy startup.
		err = CopyFile(plan.PackagePath, plan.Backup.PreviousInstaller)
		if err == nil {
			result.Success = true
			result.Phase = "succeeded"
			return result, nil
		}
	}
	installationErr := err
	result.RolledBack = true
	result.Phase = "rolling_back"
	if h.States != nil {
		_ = h.States.SavePhase(result.Phase)
	}
	// Rollback has its own deadline: cancellation of the upgrade must not cancel
	// recovery and leave the machine with migrated data and a broken program.
	recoveryCtx, recoveryCancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer recoveryCancel()
	for _, p := range started {
		if stopErr := p.Stop(recoveryCtx); stopErr != nil {
			result.Phase = "rollback_failed"
			return result, errors.Join(installationErr, stopErr)
		}
	}
	if err = h.restore(plan, backup); err != nil {
		result.Phase = "rollback_failed"
		return result, errors.Join(installationErr, err)
	}
	result.RestoredDatabaseBackup = filepath.Base(plan.Backup.DatabaseSnapshot)
	oldPlan := plan
	oldPlan.TargetVersion = plan.CurrentVersion
	oldStarted := map[string]RunningProcess{}
	if err = h.start(oldPlan, oldStarted); err == nil {
		err = h.Health.Check(recoveryCtx, oldPlan, oldStarted)
	}
	if err != nil {
		for _, p := range oldStarted {
			_ = p.Stop(recoveryCtx)
		}
		result.Phase = "rollback_failed"
		return result, errors.Join(installationErr, err)
	}
	result.RollbackSucceeded = true
	result.Phase = "rollback_succeeded"
	return result, installationErr
}
func (h Helper) start(p UpdatePlan, started map[string]RunningProcess) error {
	for _, r := range p.Restart {
		path := filepath.Join(p.InstallDirectory, r.Command)
		if err := Within(p.InstallDirectory, path); err != nil {
			return err
		}
		proc, err := h.Launcher.Start(path, r.Args)
		if err != nil {
			return err
		}
		started[r.Component] = proc
	}
	return nil
}
func (h Helper) backup(p UpdatePlan) (string, error) {
	root, err := os.MkdirTemp(filepath.Join(h.Policy.UpdatesDirectory, "backup"), "transaction-")
	if err != nil {
		return "", err
	}
	if err = SecurePath(root, true); err != nil {
		return "", err
	}
	if err = CopyTree(p.InstallDirectory, filepath.Join(root, "program")); err != nil {
		return "", err
	}
	if err = CopyTree(filepath.Join(p.DataDirectory, "config"), filepath.Join(root, "config")); err != nil {
		return "", err
	}
	if err = CopyFile(p.Backup.DatabaseSnapshot, filepath.Join(root, "hub.db")); err != nil {
		return "", err
	}
	if err = CopyFile(p.Backup.PreviousInstaller, filepath.Join(root, "installer.exe")); err != nil {
		return "", err
	}
	return root, nil
}
func (h Helper) restore(p UpdatePlan, root string) error {
	if err := Within(filepath.Join(h.Policy.UpdatesDirectory, "backup"), root); err != nil {
		return err
	}
	// Rename the failed trees into recovery storage rather than deleting files;
	// this also removes new-version-only files from the restored installation.
	for _, item := range []struct{ live, backup, label string }{{p.InstallDirectory, filepath.Join(root, "program"), "failed-program"}, {filepath.Join(p.DataDirectory, "config"), filepath.Join(root, "config"), "failed-config"}} {
		if err := RejectLinks(item.live); err != nil {
			return err
		}
		if _, err := os.Stat(item.live); err == nil {
			if err = os.Rename(item.live, filepath.Join(root, item.label)); err != nil {
				return err
			}
		} else if !os.IsNotExist(err) {
			return err
		}
		if err := CopyTree(item.backup, item.live); err != nil {
			return err
		}
	}
	data := filepath.Join(p.DataDirectory, "data")
	if err := RejectLinks(data); err != nil {
		return err
	}
	// Old WAL/SHM must not be replayed over a restored SQLite Backup snapshot.
	for _, name := range []string{"hub.db", "hub.db-wal", "hub.db-shm"} {
		path := filepath.Join(data, name)
		if err := RejectLinks(path); err != nil {
			return err
		}
		if _, err := os.Stat(path); err == nil {
			if err = os.Rename(path, filepath.Join(root, "failed-"+name)); err != nil {
				return err
			}
		} else if !os.IsNotExist(err) {
			return err
		}
	}
	if err := CopyFile(filepath.Join(root, "hub.db"), filepath.Join(data, "hub.db")); err != nil {
		return err
	}
	return CopyFile(filepath.Join(root, "installer.exe"), p.Backup.PreviousInstaller)
}

// LaunchHelper preserves the source helper-copy approach: the running updater
// lives outside the installation being replaced and receives only a Plan path.
func LaunchHelper(source string, policy PlanPolicy) error {
	if err := Within(policy.InstallDirectory, source); err != nil {
		return err
	}
	dir := filepath.Join(policy.UpdatesDirectory, "helper")
	if err := RejectLinks(dir); err != nil {
		return err
	}
	if err := os.MkdirAll(dir, 0700); err != nil {
		return err
	}
	if err := SecurePath(dir, true); err != nil {
		return err
	}
	copy := filepath.Join(dir, filepath.Base(source))
	if err := CopyFile(source, copy); err != nil {
		return err
	}
	c := exec.Command(copy, "--plan", policy.PlanPath())
	ConfigureChild(c)
	if err := c.Start(); err != nil {
		return err
	}
	return c.Process.Release()
}
