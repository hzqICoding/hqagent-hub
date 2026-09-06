package product

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"hqagent.local/protocol"
	kit "hqupdatekit.local/updatekit"
)

func TestActualAgentProcessLifecycleAndTokenRotation(t *testing.T) {
	root := t.TempDir()
	t.Setenv("HQUPDATE_E2E_LOCAL", root)
	t.Setenv("LOCALAPPDATA", root)
	p, err := Policy(root)
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
	ota := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = io.WriteString(w, `{"updateAvailable":false,"release":null}`)
	}))
	defer ota.Close()
	config := TrustConfig{ManifestBaseURL: ota.URL, Channel: "beta", TrustedKeys: map[string]string{"hqagent-lifecycle": base64.StdEncoding.EncodeToString(pub)}, DefaultKeyID: "hqagent-lifecycle", AuthenticodeThumbprints: []string{strings.Repeat("0", 40)}}
	if err = kit.AtomicJSON(filepath.Join(p.DataDirectory, "config", "update-trust.json"), config); err != nil {
		t.Fatal(err)
	}
	exe, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	var lastToken, lastInstance string
	for run := 0; run < 2; run++ {
		if err = os.Remove(filepath.Join(root, "stop-service")); err != nil && !os.IsNotExist(err) {
			t.Fatal(err)
		}
		command := exec.Command(exe, "--w6-agent-service")
		kit.ConfigureChild(command)
		var output strings.Builder
		command.Stdout = &output
		command.Stderr = &output
		if err = command.Start(); err != nil {
			t.Fatal(err)
		}
		done := make(chan error, 1)
		go func() { done <- command.Wait() }()
		finished := false
		stop := func() {
			if finished {
				return
			}
			_ = os.WriteFile(filepath.Join(root, "stop-service"), nil, 0600)
			select {
			case err := <-done:
				finished = true
				if err != nil {
					t.Errorf("Agent failed: %v %s", err, output.String())
				}
			case <-time.After(12 * time.Second):
				_ = command.Process.Kill()
				<-done
				finished = true
				t.Error("Agent did not shut down within deadline")
			}
		}
		t.Cleanup(stop)
		var d protocol.UpdateAgentRuntimeDescriptor
		deadline := time.Now().Add(5 * time.Second)
		for {
			err = kit.ReadJSON(filepath.Join(p.DataDirectory, "runtime", "update-agent.json"), &d)
			if err == nil {
				break
			}
			if time.Now().After(deadline) {
				stop()
				t.Fatal("Agent descriptor did not appear", err)
			}
			time.Sleep(20 * time.Millisecond)
		}
		if len(d.Token) != 43 || d.Token == lastToken || d.InstanceId == lastInstance || d.Pid != int64(command.Process.Pid) {
			stop()
			t.Fatal("invalid descriptor rotation")
		}
		lastToken = d.Token
		lastInstance = d.InstanceId
		client := &http.Client{Timeout: 3 * time.Second}
		response, err := client.Get(d.BaseUrl + "/internal/v1/state")
		if err != nil {
			stop()
			t.Fatal(err)
		}
		body, _ := io.ReadAll(response.Body)
		response.Body.Close()
		if response.StatusCode != 401 || strings.Contains(string(body), d.Token) {
			stop()
			t.Fatal("unauthorized response")
		}
		req, _ := http.NewRequest("POST", d.BaseUrl+"/internal/v1/check", nil)
		req.Header.Set("Authorization", "Bearer "+d.Token)
		response, err = client.Do(req)
		if err != nil {
			stop()
			t.Fatal(err)
		}
		body, _ = io.ReadAll(response.Body)
		response.Body.Close()
		if response.StatusCode != 200 || !strings.Contains(string(body), "up_to_date") || strings.Contains(string(body), d.Token) {
			stop()
			t.Fatalf("check result: %d %s", response.StatusCode, body)
		}
		duplicate := exec.Command(exe, "--w6-agent-service")
		kit.ConfigureChild(duplicate)
		if err = duplicate.Run(); err == nil {
			stop()
			t.Fatal("duplicate Agent started")
		}
		stop()
		if _, err = os.Stat(filepath.Join(p.DataDirectory, "runtime", "update-agent.json")); !os.IsNotExist(err) {
			t.Fatal("descriptor not removed on exit")
		}
	}
	t.Log("real RunAgent in separate processes: two clean starts/stops, authenticated check, 401 without token, instance/token rotation, duplicate-instance rejection, descriptor cleanup")
}
