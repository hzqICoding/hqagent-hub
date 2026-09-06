package product

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"hqagent.local/protocol"
	kit "hqupdatekit.local/updatekit"
)

// This is an OS-process E2E with a Go executable that simulates a Tauri NSIS
// bundle. Only Authenticode is substituted in the test binary. Production
// commands have no bypass flag. Real NSIS/certificate acceptance is separate.
type testOSSignature struct{}

func (testOSSignature) VerifyCodeSignature(context.Context, string) error { return nil }
func TestMain(m *testing.M) {
	root := os.Getenv("HQUPDATE_E2E_LOCAL")
	if root != "" && len(os.Args) > 1 {
		mode := os.Args[1]
		if mode == "/S" || mode == "--w6-helper" || mode == "--w6-worker" || mode == "--w6-agent-service" {
			if err := testChild(root, mode); err != nil {
				fmt.Fprintln(os.Stderr, err)
				os.Exit(1)
			}
			os.Exit(0)
		}
	}
	if root != "" && strings.HasPrefix(strings.ToLower(filepath.Base(os.Args[0])), "hqagent-") {
		if err := testChild(root, "component"); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		os.Exit(0)
	}
	os.Exit(m.Run())
}
func testChild(root, mode string) error {
	p, err := Policy(root)
	if err != nil {
		return err
	}
	if mode == "--w6-agent-service" {
		ctx, cancel := context.WithCancel(context.Background())
		defer cancel()
		go func() {
			for {
				if _, err := os.Stat(filepath.Join(root, "stop-service")); err == nil {
					cancel()
					return
				}
				select {
				case <-ctx.Done():
					return
				case <-time.After(20 * time.Millisecond):
				}
			}
		}()
		return RunAgent(ctx)
	}
	if mode == "/S" {
		directory := strings.TrimPrefix(strings.Join(os.Args[2:], " "), "/D=")
		if directory != p.InstallDirectory {
			return fmt.Errorf("NSIS current-user /D mismatch: %s", directory)
		}
		for _, name := range []string{"hqagent-core.exe", "hqagent-desktop.exe", "hqagent-update-agent.exe"} {
			if err = kit.CopyFile(os.Args[0], filepath.Join(directory, name)); err != nil {
				return err
			}
		}
		for path, content := range map[string]string{filepath.Join(directory, "version.txt"): "0.2.0", filepath.Join(directory, "new-only.txt"): "new", filepath.Join(p.DataDirectory, "config", "settings.json"): "migrated-config", filepath.Join(p.DataDirectory, "data", "hub.db"): "migrated-db", filepath.Join(p.DataDirectory, "data", "hub.db-wal"): "new-wal"} {
			if err = os.WriteFile(path, []byte(content), 0600); err != nil {
				return err
			}
		}
		return nil
	}
	if mode == "--w6-helper" {
		pub, err := base64.StdEncoding.DecodeString(os.Getenv("HQUPDATE_E2E_PUBLIC"))
		if err != nil {
			return err
		}
		verifier, err := kit.NewTrustedVerifier(map[string]ed25519.PublicKey{"hqagent-hub-e2e": pub}, "hqagent-hub-e2e", testOSSignature{})
		if err != nil {
			return err
		}
		store := Store{Policy: p}
		helper := kit.Helper{Policy: p, Verifier: verifier, Strategy: kit.NSISStrategy{}, Health: HealthProbe{Policy: p}, Results: store, States: store, WaitTimeout: 10 * time.Second}
		result, err := helper.Run(context.Background(), p.PlanPath())
		if !result.RollbackSucceeded {
			return fmt.Errorf("rollback failed: %+v %v", result, err)
		}
		return nil
	}
	pid := os.Getpid()
	record := filepath.Join(p.DataDirectory, "runtime", "test-"+strconv.Itoa(pid)+".pid")
	if err = os.WriteFile(record, []byte(strconv.Itoa(pid)), 0600); err != nil {
		return err
	}
	stop := filepath.Join(root, "stop-all")
	if mode == "--w6-worker" {
		stop = filepath.Join(root, "stop-old")
	}
	if mode == "component" && strings.EqualFold(filepath.Base(os.Args[0]), "hqagent-core.exe") {
		version, err := os.ReadFile(filepath.Join(p.InstallDirectory, "version.txt"))
		if err != nil {
			return err
		}
		listener, err := net.Listen("tcp4", "127.0.0.1:0")
		if err != nil {
			return err
		}
		defer listener.Close()
		port := listener.Addr().(*net.TCPAddr).Port
		status := "ok"
		if string(version) == "0.2.0" {
			status = "broken"
		}
		d := protocol.HubRuntimeDescriptor{SchemaVersion: 1, InstanceId: "test-instance-" + strconv.Itoa(pid), Port: int64(port), Token: strings.Repeat("t", 43), Pid: int64(pid), BaseUrl: fmt.Sprintf("http://127.0.0.1:%d", port), AppVersion: string(version), ProtocolVersion: WireVersion, StartedAt: time.Now().UTC().Format(time.RFC3339Nano)}
		if err = kit.AtomicJSON(filepath.Join(p.DataDirectory, "runtime", "hub.json"), d); err != nil {
			return err
		}
		server := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			_ = json.NewEncoder(w).Encode(protocol.HealthView{Status: status, AppVersion: string(version), ProtocolVersion: WireVersion, Pid: int64(pid), StartedAt: d.StartedAt})
		}), ReadHeaderTimeout: time.Second}
		defer server.Close()
		go server.Serve(listener)
	}
	for {
		if _, err = os.Stat(stop); err == nil {
			return nil
		}
		time.Sleep(20 * time.Millisecond)
	}
}
func TestE2EFakeTauriProcessesNSISAndAutomaticRollback(t *testing.T) {
	if os.Getenv("GOOS") == "linux" {
		t.Skip("Windows process acceptance")
	}
	local := filepath.Join(t.TempDir(), "Local AppData")
	t.Setenv("HQUPDATE_E2E_LOCAL", local)
	p, err := Policy(local)
	if err != nil {
		t.Fatal(err)
	}
	if err = PrepareDirectories(p); err != nil {
		t.Fatal(err)
	}
	for _, d := range []string{p.InstallDirectory, filepath.Join(p.DataDirectory, "data")} {
		if err = os.MkdirAll(d, 0700); err != nil {
			t.Fatal(err)
		}
	}
	exe, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"hqagent-core.exe", "hqagent-desktop.exe", "hqagent-update-agent.exe"} {
		if err = kit.CopyFile(exe, filepath.Join(p.InstallDirectory, name)); err != nil {
			t.Fatal(err)
		}
	}
	previous := filepath.Join(p.UpdatesDirectory, "installed", "installer.exe")
	if err = kit.CopyFile(exe, previous); err != nil {
		t.Fatal(err)
	}
	snapshot := filepath.Join(p.UpdatesDirectory, "backup", "hub-before.db")
	for path, content := range map[string]string{filepath.Join(p.InstallDirectory, "version.txt"): "0.1.0", filepath.Join(p.DataDirectory, "config", "settings.json"): "original-config", filepath.Join(p.DataDirectory, "data", "hub.db"): "original-db", snapshot: "original-db"} {
		if err = os.WriteFile(path, []byte(content), 0600); err != nil {
			t.Fatal(err)
		}
	}
	t.Cleanup(func() {
		_ = os.WriteFile(filepath.Join(local, "stop-all"), nil, 0600)
		_ = os.WriteFile(filepath.Join(local, "stop-old"), nil, 0600)
		entries, _ := filepath.Glob(filepath.Join(p.DataDirectory, "runtime", "test-*.pid"))
		pids := []int{}
		for _, entry := range entries {
			b, _ := os.ReadFile(entry)
			pid, _ := strconv.Atoi(string(b))
			if pid > 0 {
				pids = append(pids, pid)
			}
		}
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if e := kit.WaitPIDs(ctx, pids); e != nil {
			t.Error("test process cleanup", e)
		}
	})
	var processes []kit.Process
	var waitPids []int
	var old []*exec.Cmd
	defer func() {
		_ = os.WriteFile(filepath.Join(local, "stop-old"), nil, 0600)
		for _, c := range old {
			_ = c.Wait()
		}
	}()
	for _, component := range []string{"desktop", "core", "update-agent", "agent-worker", "agent-worker"} {
		cmd := exec.Command(exe, "--w6-worker")
		kit.ConfigureChild(cmd)
		if err = cmd.Start(); err != nil {
			t.Fatal(err)
		}
		old = append(old, cmd)
		waitPids = append(waitPids, cmd.Process.Pid)
		processes = append(processes, kit.Process{Component: component, PID: cmd.Process.Pid})
	}
	data, err := os.ReadFile(exe)
	if err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256(data)
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	t.Setenv("HQUPDATE_E2E_PUBLIC", base64.StdEncoding.EncodeToString(pub))
	r := kit.Release{Version: "0.2.0", Channel: "beta", PublishedAt: time.Now().UTC(), Package: kit.Package{Type: "installer", OS: "windows", Arch: "amd64", TargetKey: p.TargetKey, Size: int64(len(data)), SHA256: hex.EncodeToString(digest[:]), Signature: base64.StdEncoding.EncodeToString(ed25519.Sign(priv, digest[:])), SignatureAlgorithm: "ed25519-sha256", KeyID: "hqagent-hub-e2e"}}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		if req.URL.Path == "/api/v1/updates/check" {
			if req.URL.Query().Get("targetKey") != p.TargetKey {
				t.Error("targetKey missing")
			}
			_ = json.NewEncoder(w).Encode(kit.CheckResponse{UpdateAvailable: true, Release: &r})
			return
		}
		_, _ = w.Write(data)
	}))
	defer server.Close()
	r.Package.URL = server.URL + "/package.exe"
	client, err := kit.NewHTTPManifestClient(server.URL)
	if err != nil {
		t.Fatal(err)
	}
	verifier, err := kit.NewTrustedVerifier(map[string]ed25519.PublicKey{"hqagent-hub-e2e": pub}, "hqagent-hub-e2e", testOSSignature{})
	if err != nil {
		t.Fatal(err)
	}
	store := Store{Policy: p}
	service, err := kit.NewService(kit.Options{Meta: Meta(), Config: TrustConfig{Channel: "beta"}, Client: client, Verifier: verifier, Store: store, StagingDirectory: filepath.Join(p.UpdatesDirectory, "staging")})
	if err != nil {
		t.Fatal(err)
	}
	if err = service.Check(context.Background()); err != nil {
		t.Fatal(err)
	}
	t.Log("check: available; targetKey matched")
	if err = service.Download(context.Background()); err != nil {
		t.Fatal(err)
	}
	if service.State().Status != kit.StatusReadyToInstall {
		t.Fatal(service.State())
	}
	t.Log("download: ready_to_install; SHA-256 + Ed25519 verified (test OS-signature adapter)")
	plan := MakePlan(p, r, service.State().PackagePath, processes, waitPids, snapshot)
	plan.HealthChecks[1].TimeoutSeconds = 1
	if err = kit.ValidatePlan(plan, p); err != nil {
		t.Fatal(err)
	}
	if err = kit.AtomicJSON(p.PlanPath(), plan); err != nil {
		t.Fatal(err)
	}
	t.Log("Plan v2: Desktop/Core/Update Agent + 2 Workers; current-user directories validated")
	helperDir := filepath.Join(p.UpdatesDirectory, "helper")
	if err = os.MkdirAll(helperDir, 0700); err != nil {
		t.Fatal(err)
	}
	helperExe := filepath.Join(helperDir, "e2e-updater.exe")
	if err = kit.CopyFile(exe, helperExe); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	command := exec.CommandContext(ctx, helperExe, "--w6-helper")
	kit.ConfigureChild(command)
	var output strings.Builder
	command.Stdout = &output
	command.Stderr = &output
	if err = command.Start(); err != nil {
		t.Fatal(err)
	}
	time.Sleep(150 * time.Millisecond)
	version, _ := os.ReadFile(filepath.Join(p.InstallDirectory, "version.txt"))
	if string(version) != "0.1.0" {
		t.Fatal("installer ran while waitPids were alive")
	}
	if err = os.WriteFile(filepath.Join(local, "stop-old"), nil, 0600); err != nil {
		t.Fatal(err)
	}
	if err = command.Wait(); err != nil {
		t.Fatalf("helper: %v\n%s", err, output.String())
	}
	t.Log("independent Helper: waited for all 5 processes; executed /S and terminal /D")
	result, err := store.Result()
	if err != nil {
		t.Fatal(err)
	}
	if result == nil || result.Success || result.RolledBack == nil || !*result.RolledBack || result.RollbackSucceeded == nil || !*result.RollbackSucceeded {
		t.Fatalf("result=%+v", result)
	}
	for path, want := range map[string]string{filepath.Join(p.InstallDirectory, "version.txt"): "0.1.0", filepath.Join(p.DataDirectory, "config", "settings.json"): "original-config", filepath.Join(p.DataDirectory, "data", "hub.db"): "original-db"} {
		b, e := os.ReadFile(path)
		if e != nil || string(b) != want {
			t.Fatalf("restore %s: %q %v", path, b, e)
		}
	}
	for _, path := range []string{filepath.Join(p.InstallDirectory, "new-only.txt"), filepath.Join(p.DataDirectory, "data", "hub.db-wal")} {
		if _, err = os.Stat(path); !os.IsNotExist(err) {
			t.Fatalf("new-version residue: %s", path)
		}
	}
	archives, _ := filepath.Glob(filepath.Join(p.UpdatesDirectory, "backup", "transaction-*", "installer.exe"))
	if len(archives) != 1 {
		t.Fatal("previous installer not retained")
	}
	t.Log("health: new core unhealthy; automatic rollback restored program/config/DB snapshot, removed new WAL, restarted healthy 0.1.0; generated Result DTO persisted")
}
