//go:build windows

package updatekit

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"syscall"
	"testing"
	"time"
)

// Only this test binary recognizes the simulator commands. No production
// command or trust configuration contains a simulator/signature bypass.
func TestMain(m *testing.M) {
	root := os.Getenv("HQUPDATE_JOB_SIM_ROOT")
	if root != "" && len(os.Args) > 1 {
		switch os.Args[1] {
		case "/S", "--job-parent", "--job-child", "--job-breakaway-probe":
			if err := installerJobSimulator(root, os.Args[1]); err != nil {
				fmt.Fprintln(os.Stderr, err)
				os.Exit(1)
			}
			os.Exit(0)
		}
	}
	os.Exit(m.Run())
}

func installerJobSimulator(root, mode string) error {
	if mode == "--job-breakaway-probe" {
		return os.WriteFile(filepath.Join(root, "escaped"), nil, 0600)
	}
	if mode == "--job-child" {
		if err := os.WriteFile(filepath.Join(root, "child.pid"), []byte(strconv.Itoa(os.Getpid())), 0600); err != nil {
			return err
		}
		if err := os.WriteFile(filepath.Join(root, "child-ready"), nil, 0600); err != nil {
			return err
		}
		for {
			if _, err := os.Stat(filepath.Join(root, "release-child")); err == nil {
				return nil
			}
			time.Sleep(10 * time.Millisecond)
		}
	}
	if err := os.WriteFile(filepath.Join(root, "parent.pid"), []byte(strconv.Itoa(os.Getpid())), 0600); err != nil {
		return err
	}
	exe, err := os.Executable()
	if err != nil {
		return err
	}
	if os.Getenv("HQUPDATE_JOB_SIM_MODE") == "breakaway" {
		probe := exec.Command(exe, "--job-breakaway-probe")
		ConfigureChild(probe)
		probe.SysProcAttr.CreationFlags |= 0x01000000 // deliberately request CREATE_BREAKAWAY_FROM_JOB
		if err := probe.Start(); !errors.Is(err, syscall.ERROR_ACCESS_DENIED) {
			if err == nil {
				_ = probe.Wait()
			}
			return fmt.Errorf("breakaway was not denied: %v", err)
		}
		return os.WriteFile(filepath.Join(root, "breakaway-denied"), nil, 0600)
	}
	if install := os.Getenv("HQUPDATE_JOB_SIM_INSTALL"); install != "" {
		if err := os.WriteFile(filepath.Join(install, "version"), []byte("partially-installed"), 0600); err != nil {
			return err
		}
	}
	child := exec.Command(exe, "--job-child")
	ConfigureChild(child)
	if err := child.Start(); err != nil {
		return err
	}
	defer child.Process.Release()
	deadline := time.Now().Add(10 * time.Second)
	for {
		if _, err := os.Stat(filepath.Join(root, "child-ready")); err == nil {
			return nil
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("child did not start")
		}
		time.Sleep(10 * time.Millisecond)
	}
}

func awaitSimulatorPID(t *testing.T, root, name string) int {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for {
		b, err := os.ReadFile(filepath.Join(root, name+".pid"))
		if err == nil {
			pid, err := strconv.Atoi(string(b))
			if err == nil && pid > 0 {
				return pid
			}
		}
		if time.Now().After(deadline) {
			t.Fatalf("%s pid not reported", name)
		}
		time.Sleep(10 * time.Millisecond)
	}
}

func TestInstallerJobWaitsForDescendantAfterParentExit(t *testing.T) {
	root := t.TempDir()
	t.Setenv("HQUPDATE_JOB_SIM_ROOT", root)
	exe, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	type outcome struct {
		code int
		err  error
	}
	done := make(chan outcome, 1)
	go func() {
		code, err := (ExecRunner{}).Run(ctx, exe, []string{"--job-parent"})
		done <- outcome{code, err}
	}()
	// Join the runner even on a failed assertion, so t.TempDir cannot race a
	// still-running process. The production job cleanup terminates descendants.
	joined := false
	defer func() {
		cancel()
		if !joined {
			<-done
		}
	}()
	parent := awaitSimulatorPID(t, root, "parent")
	_ = awaitSimulatorPID(t, root, "child")
	if err = WaitPIDs(ctx, []int{parent}); err != nil {
		t.Fatal(err)
	}
	select {
	case result := <-done:
		joined = true
		t.Fatalf("returned before descendant exit: %+v", result)
	default:
	}
	if err = os.WriteFile(filepath.Join(root, "release-child"), nil, 0600); err != nil {
		t.Fatal(err)
	}
	result := <-done
	joined = true
	if result.err != nil || result.code != 0 {
		t.Fatalf("result=%+v", result)
	}
	t.Log("process simulator: parent exited; runner remained blocked until descendant exit and Job ActiveProcesses=0")
}

func TestInstallerJobTimeoutPreservesBackupsWithoutOverwrite(t *testing.T) {
	plan, policy, _ := planFixture(t)
	root := t.TempDir()
	t.Setenv("HQUPDATE_JOB_SIM_ROOT", root)
	t.Setenv("HQUPDATE_JOB_SIM_INSTALL", policy.InstallDirectory)
	exe, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(exe)
	if err != nil {
		t.Fatal(err)
	}
	release, verifier := signedRelease(t, data)
	plan.Release = release
	if err = CopyFile(exe, plan.PackagePath); err != nil {
		t.Fatal(err)
	}
	if err = AtomicJSON(policy.PlanPath(), plan); err != nil {
		t.Fatal(err)
	}
	results := &resultRecorder{}
	helper := Helper{Policy: policy, Verifier: verifier, Strategy: NSISStrategy{Timeout: 5 * time.Second}, Results: results, Wait: func(context.Context, []int) error { return nil }, Health: healthFunc(func(context.Context, UpdatePlan, map[string]RunningProcess) error {
		t.Fatal("health ran before process convergence")
		return nil
	})}
	result, err := helper.Run(context.Background(), policy.PlanPath())
	// The Windows installer compatibility machinery may add another process;
	// containment is about every descendant, never an assumed exact count.
	if !errors.Is(err, ErrInstallerNotQuiescent) || !errors.Is(err, context.DeadlineExceeded) || !regexp.MustCompile(`installerExited=true activeProcesses=[1-9][0-9]*:`).MatchString(err.Error()) {
		t.Fatalf("timeout did not identify live descendant: %v", err)
	}
	if result.Success || result.RolledBack || result.RollbackSucceeded || results.value.Phase != StatusFailed {
		t.Fatalf("result=%+v", result)
	}
	live, readErr := os.ReadFile(filepath.Join(policy.InstallDirectory, "version"))
	if readErr != nil || string(live) != "partially-installed" {
		t.Fatalf("live installation overwritten: %q %v", live, readErr)
	}
	backups, _ := filepath.Glob(filepath.Join(policy.UpdatesDirectory, "backup", "transaction-*"))
	if len(backups) != 1 {
		t.Fatal("backup transaction missing")
	}
	for rel, want := range map[string]string{"program/version": "old", "hub.db": "snapshot", "installer.exe": "previous-installer", "config/config.json": "original"} {
		b, e := os.ReadFile(filepath.Join(backups[0], filepath.FromSlash(rel)))
		if e != nil || string(b) != want {
			t.Fatalf("backup %s: %q %v", rel, b, e)
		}
	}
	child := awaitSimulatorPID(t, root, "child")
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if err = WaitPIDs(ctx, []int{child}); err != nil {
		t.Fatal("job cleanup left descendant alive", err)
	}
	t.Logf("process simulator (not real NSIS): %v; backups retained, live files not restored; job cleanup terminated descendant", result.Error)
}

func TestInstallerJobDeniesDescendantBreakaway(t *testing.T) {
	root := t.TempDir()
	t.Setenv("HQUPDATE_JOB_SIM_ROOT", root)
	t.Setenv("HQUPDATE_JOB_SIM_MODE", "breakaway")
	exe, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	code, err := (ExecRunner{}).Run(ctx, exe, []string{"--job-parent"})
	if err != nil || code != 0 {
		t.Fatalf("code=%d err=%v", code, err)
	}
	if _, err = os.Stat(filepath.Join(root, "breakaway-denied")); err != nil {
		t.Fatal(err)
	}
	if _, err = os.Stat(filepath.Join(root, "escaped")); !os.IsNotExist(err) {
		t.Fatal("descendant escaped job")
	}
	t.Log("process simulator: descendant CREATE_BREAKAWAY_FROM_JOB rejected with access denied")
}
