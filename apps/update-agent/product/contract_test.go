package product

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"hqagent.local/protocol"
	kit "hqupdatekit.local/updatekit"
)

// The generated DTO is the only wire type. These checks additionally compare
// required fields and additionalProperties against the actual frozen schemas.
func checkSchemaFields(t *testing.T, file, definition string, value any) {
	t.Helper()
	path := filepath.Join("..", "..", "..", "packages", "protocol", "schema", file)
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var schema struct {
		Defs map[string]struct {
			Required   []string                   `json:"required"`
			Properties map[string]json.RawMessage `json:"properties"`
		} `json:"$defs"`
	}
	if err = json.Unmarshal(b, &schema); err != nil {
		t.Fatal(err)
	}
	encoded, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	var fields map[string]json.RawMessage
	if err = json.Unmarshal(encoded, &fields); err != nil {
		t.Fatal(err)
	}
	def, ok := schema.Defs[definition]
	if !ok {
		t.Fatal("definition missing", definition)
	}
	for _, key := range def.Required {
		if _, ok := fields[key]; !ok {
			t.Error("required field missing", key)
		}
	}
	for key := range fields {
		if _, ok := def.Properties[key]; !ok {
			t.Error("undeclared field", key)
		}
	}
}
func TestGeneratedDTOContracts(t *testing.T) {
	state := StateDTO(kit.State{Status: kit.StatusReadyToInstall, CurrentVersion: "0.1.0", Channel: "beta"})
	checkSchemaFields(t, "update-state.json", "UpdateStateView", state)
	result := ResultDTO(kit.Result{FromVersion: "0.1.0", ToVersion: "0.2.0", Phase: "rollback_succeeded", RolledBack: true, RollbackSucceeded: true, FinishedAt: time.Now().UTC()})
	checkSchemaFields(t, "update-result.json", "UpdateResultView", result)
	token, err := randomID()
	if err != nil {
		t.Fatal(err)
	}
	id, err := randomID()
	if err != nil {
		t.Fatal(err)
	}
	descriptor := protocol.UpdateAgentRuntimeDescriptor{SchemaVersion: 1, InstanceId: id, Port: 34567, Token: token, Pid: 123, BaseUrl: "http://127.0.0.1:34567", AgentVersion: Version, StartedAt: time.Now().UTC().Format(time.RFC3339Nano)}
	checkSchemaFields(t, "runtime-descriptor.json", "UpdateAgentRuntimeDescriptor", descriptor)
	if len(token) != 43 || token == id {
		t.Fatal("token entropy/rotation failed")
	}
	t.Logf("generated protocol package: %s; HTTP protocolVersion: %s", protocol.Version, WireVersion)
}
func TestPrivateAPIAuthorizationAndNoCredentialLeak(t *testing.T) {
	local := t.TempDir()
	p, err := Policy(local)
	if err != nil {
		t.Fatal(err)
	}
	if err = PrepareDirectories(p); err != nil {
		t.Fatal(err)
	}
	pub, _, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	verifier, err := kit.NewTrustedVerifier(map[string]ed25519.PublicKey{"test": pub}, "test", testOSSignature{})
	if err != nil {
		t.Fatal(err)
	}
	store := Store{Policy: p}
	service, err := kit.NewService(kit.Options{Meta: Meta(), Config: TrustConfig{Channel: "beta"}, Client: &kit.FakeManifestClient{}, Verifier: verifier, Store: store, StagingDirectory: filepath.Join(p.UpdatesDirectory, "staging")})
	if err != nil {
		t.Fatal(err)
	}
	token := strings.Repeat("z", 43)
	server := &Server{Service: service, Store: store, Policy: p, Host: "127.0.0.1:23456", Token: token}
	handler := server.Handler()
	for _, tc := range []struct {
		name, auth, origin, host, remote, path string
		status                                 int
	}{
		{"no token", "", "", "127.0.0.1:23456", "127.0.0.1:32100", "/internal/v1/state", 401},
		{"bad token", "Bearer wrong", "", "127.0.0.1:23456", "127.0.0.1:32100", "/internal/v1/state", 401},
		{"browser", "Bearer " + token, "https://evil.example", "127.0.0.1:23456", "127.0.0.1:32100", "/internal/v1/state", 401},
		{"DNS rebinding", "Bearer " + token, "", "evil.example:23456", "127.0.0.1:32100", "/internal/v1/state", 401},
		{"remote", "Bearer " + token, "", "127.0.0.1:23456", "192.0.2.1:32100", "/internal/v1/state", 401},
		{"Hub", "Bearer " + token, "", "127.0.0.1:23456", "127.0.0.1:32100", "/internal/v1/state", 200},
		{"events capability gap", "Bearer " + token, "", "127.0.0.1:23456", "127.0.0.1:32100", "/internal/v1/events", 501},
		{"missing result", "Bearer " + token, "", "127.0.0.1:23456", "127.0.0.1:32100", "/internal/v1/result", 204},
	} {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest("GET", "http://"+tc.host+tc.path, nil)
			req.Host = tc.host
			req.RemoteAddr = tc.remote
			req.Header.Set("Authorization", tc.auth)
			req.Header.Set("Origin", tc.origin)
			w := httptest.NewRecorder()
			handler.ServeHTTP(w, req)
			if w.Code != tc.status {
				t.Fatalf("status %d body %s", w.Code, w.Body.String())
			}
			if strings.Contains(w.Body.String(), token) {
				t.Fatal("token leaked")
			}
		})
	}
	if err = store.SaveResult(kit.Result{FromVersion: "0.1.0", ToVersion: "0.2.0", FinishedAt: time.Now().UTC(), RolledBack: true, RollbackSucceeded: true}); err != nil {
		t.Fatal(err)
	}
	req := httptest.NewRequest("GET", "http://127.0.0.1:23456/internal/v1/result", nil)
	req.RemoteAddr = "127.0.0.1:32100"
	req.Header.Set("Authorization", "Bearer "+token)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)
	var result protocol.UpdateResultView
	if err = json.Unmarshal(w.Body.Bytes(), &result); err != nil || result.SchemaVersion != 2 || result.Success {
		t.Fatalf("raw Result DTO lost: %s %v", w.Body.String(), err)
	}
}
func TestHubDrainIsConsumedAndIncompleteInventoryRejected(t *testing.T) {
	p, err := Policy(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if err = PrepareDirectories(p); err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+strings.Repeat("h", 43) {
			t.Error("Hub credential missing")
		}
		if r.URL.Path != "/internal/drain/state" {
			t.Error("unexpected write before drain ready", r.URL.Path)
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"success": true, "data": protocol.DrainProgress{Step: protocol.DrainStepWaitRunningTasks, Percent: 45, ActiveTasksRemaining: 1, BackupCompleted: ptr(false)}})
	}))
	defer server.Close()
	var port int
	if _, err = fmt.Sscanf(server.URL, "http://127.0.0.1:%d", &port); err != nil {
		t.Fatal(err)
	}
	d := protocol.HubRuntimeDescriptor{SchemaVersion: 1, InstanceId: "test-hub-instance", Port: int64(port), Token: strings.Repeat("h", 43), Pid: 123, BaseUrl: server.URL, AppVersion: Version, ProtocolVersion: WireVersion, StartedAt: time.Now().UTC().Format(time.RFC3339Nano)}
	if err = kit.AtomicJSON(filepath.Join(p.DataDirectory, "runtime", "hub.json"), d); err != nil {
		t.Fatal(err)
	}
	if err = (HubClient{Policy: p, AgentPID: 234}).Prepare(context.Background(), kit.Release{}, ""); err == nil {
		t.Fatal("installed with running tasks")
	}
	if _, err = os.Stat(p.PlanPath()); !os.IsNotExist(err) {
		t.Fatal("Plan produced before drain")
	}
}
