package updatekit

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

type testCodeSignature struct{ err error }

func (v testCodeSignature) VerifyCodeSignature(context.Context, string) error { return v.err }

type testSettings struct{}

func (testSettings) UpdateSettings() Settings { return Settings{Channel: "beta"} }

type memoryStore struct {
	mu      sync.Mutex
	state   State
	present bool
	fail    bool
}

func (m *memoryStore) Load() (State, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if !m.present {
		return State{}, os.ErrNotExist
	}
	return cloneState(m.state), nil
}
func (m *memoryStore) Save(s State) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.fail {
		return errors.New("disk full")
	}
	m.state = cloneState(s)
	m.present = true
	return nil
}
func signedRelease(t *testing.T, data []byte) (Release, *PackageVerifier) {
	t.Helper()
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256(data)
	r := Release{Version: "0.2.0", Channel: "beta", PublishedAt: time.Now().UTC(), Package: Package{Type: "installer", OS: "windows", Arch: "amd64", TargetKey: "windows-amd64-installer", URL: "http://127.0.0.1/package.exe", Size: int64(len(data)), SHA256: hex.EncodeToString(digest[:]), Signature: base64.StdEncoding.EncodeToString(ed25519.Sign(priv, digest[:])), KeyID: "hqagent-test", SignatureAlgorithm: "ed25519-sha256"}}
	v, err := NewTrustedVerifier(map[string]ed25519.PublicKey{"hqagent-test": pub}, "hqagent-test", testCodeSignature{})
	if err != nil {
		t.Fatal(err)
	}
	return r, v
}
func testMeta() AppMeta {
	return AppMeta{AppID: "hqagent-hub", Version: "0.1.0", InstallType: "installer", TargetKey: "windows-amd64-installer", OS: "windows", Arch: "amd64"}
}
func TestDoubleTrustAndTampering(t *testing.T) {
	data := []byte("fake Tauri NSIS payload")
	r, v := signedRelease(t, data)
	p := filepath.Join(t.TempDir(), "setup.exe")
	if err := os.WriteFile(p, data, 0600); err != nil {
		t.Fatal(err)
	}
	if err := v.Verify(context.Background(), r, p); err != nil {
		t.Fatal(err)
	}
	for _, kind := range []string{"hash", "signature", "key", "algorithm", "size", "os-trust"} {
		t.Run(kind, func(t *testing.T) {
			bad := r
			copyV := *v
			switch kind {
			case "hash":
				bad.Package.SHA256 = strings.Repeat("0", 64)
			case "signature":
				bad.Package.Signature = base64.StdEncoding.EncodeToString(make([]byte, 64))
			case "key":
				bad.Package.KeyID = "other-product"
			case "algorithm":
				bad.Package.SignatureAlgorithm = "none"
			case "size":
				bad.Package.Size++
			case "os-trust":
				copyV.codeSignature = testCodeSignature{errors.New("wrong publisher")}
			}
			if err := copyV.Verify(context.Background(), bad, p); err == nil {
				t.Fatal("unsafe package accepted")
			}
		})
	}
	if err := os.WriteFile(p, []byte("tampered"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := v.Verify(context.Background(), r, p); err == nil {
		t.Fatal("tampered package accepted")
	}
}
func TestRangeResumeAndMalformedResponse(t *testing.T) {
	data := "abcdefghij"
	for _, mode := range []string{"range", "restart", "bad-range", "truncated", "oversized", "complete-part"} {
		t.Run(mode, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Header.Get("Range") != "bytes=3-" {
					t.Errorf("missing resume range")
				}
				switch mode {
				case "bad-range":
					w.Header().Set("Content-Range", "bytes 1-9/10")
					w.WriteHeader(206)
					fmt.Fprint(w, data[3:])
				case "range":
					w.Header().Set("Content-Range", "bytes 3-9/10")
					w.WriteHeader(206)
					fmt.Fprint(w, data[3:])
				case "truncated":
					fmt.Fprint(w, "ab")
				case "oversized":
					fmt.Fprint(w, data+"x")
				default:
					fmt.Fprint(w, data)
				}
			}))
			defer server.Close()
			path := filepath.Join(t.TempDir(), "package.exe")
			partial := data[:3]
			if mode == "complete-part" {
				partial = data
			}
			if err := os.WriteFile(path+".part", []byte(partial), 0600); err != nil {
				t.Fatal(err)
			}
			err := NewHTTPDownloader().Download(context.Background(), Package{URL: server.URL, Size: 10}, path, nil)
			bad := mode == "bad-range" || mode == "truncated" || mode == "oversized"
			if (err != nil) != bad {
				t.Fatalf("error=%v", err)
			}
			if !bad {
				b, e := os.ReadFile(path)
				if e != nil || string(b) != data {
					t.Fatalf("data=%q err=%v", b, e)
				}
			}
		})
	}
}
func TestManifestTargetAndReleaseValidation(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("targetKey") != "windows-amd64-installer" || r.URL.Query().Get("appId") != "hqagent-hub" {
			t.Error("exact target query missing")
		}
		fmt.Fprint(w, `{"updateAvailable":false,"release":null}`)
	}))
	defer server.Close()
	c, err := NewHTTPManifestClient(server.URL)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = c.Check(context.Background(), CheckRequest{AppID: "hqagent-hub", TargetKey: "windows-amd64-installer"}); err != nil {
		t.Fatal(err)
	}
	r, _ := signedRelease(t, []byte("p"))
	for _, kind := range []string{"target", "arch", "os", "channel", "http"} {
		bad := r
		switch kind {
		case "target":
			bad.Package.TargetKey = "other-product"
		case "arch":
			bad.Package.Arch = "arm64"
		case "os":
			bad.Package.OS = "linux"
		case "channel":
			bad.Channel = "stable"
		case "http":
			bad.Package.URL = "http://example.com/setup.exe"
		}
		if err := ValidateRelease(bad, testMeta(), "beta"); err == nil {
			t.Fatalf("accepted %s", kind)
		}
	}
}

type blockedDownloader struct{ started, release chan struct{} }

func (b blockedDownloader) Download(ctx context.Context, p Package, path string, f func(DownloadProgress)) error {
	close(b.started)
	<-b.release
	return ctx.Err()
}
func TestCancelDoesNotAllowStaleDownloadToOverwriteNextOperation(t *testing.T) {
	r, v := signedRelease(t, []byte("payload"))
	b := blockedDownloader{make(chan struct{}), make(chan struct{})}
	s, err := NewService(Options{Meta: testMeta(), Config: testSettings{}, Client: &FakeManifestClient{CheckResult: CheckResponse{UpdateAvailable: true, Release: &r}}, Downloader: b, Verifier: v, Store: &memoryStore{}, StagingDirectory: t.TempDir()})
	if err != nil {
		t.Fatal(err)
	}
	if err = s.Check(context.Background()); err != nil {
		t.Fatal(err)
	}
	done := make(chan error, 1)
	go func() { done <- s.Download(context.Background()) }()
	<-b.started
	if err = s.Cancel(); err != nil {
		t.Fatal(err)
	}
	if err = s.Check(context.Background()); !errors.Is(err, ErrBusy) {
		t.Fatalf("operation unlocked too early: %v", err)
	}
	close(b.release)
	<-done
	if s.State().Status != StatusCancelled {
		t.Fatal(s.State().Status)
	}
	if err = s.Check(context.Background()); err != nil {
		t.Fatal(err)
	}
}
func TestRestoreReverifiesAndPersistenceFailsClosed(t *testing.T) {
	dir := t.TempDir()
	r, v := signedRelease(t, []byte("original"))
	path := filepath.Join(dir, "setup.exe")
	if err := os.WriteFile(path, []byte("tampered"), 0600); err != nil {
		t.Fatal(err)
	}
	store := &memoryStore{present: true, state: State{Status: StatusReadyToInstall, CurrentVersion: "0.1.0", Channel: "beta", Release: &r, PackagePath: path}}
	o := Options{Meta: testMeta(), Config: testSettings{}, Client: &FakeManifestClient{}, Verifier: v, Store: store, StagingDirectory: dir}
	s, err := NewService(o)
	if err != nil {
		t.Fatal(err)
	}
	if s.State().Status != StatusFailed {
		t.Fatal("restored tampered package marked ready")
	}
	store.mu.Lock()
	store.fail = true
	store.mu.Unlock()
	if err = s.Check(context.Background()); err == nil {
		t.Fatal("ignored persistence failure")
	}
}

type recordingRunner struct {
	code int
	err  error
	args []string
	path string
}

func (r *recordingRunner) Run(ctx context.Context, path string, args []string) (int, error) {
	r.args = args
	r.path = path
	return r.code, r.err
}
func TestNSISArgumentsAndExitCodes(t *testing.T) {
	for _, code := range []int{0, 1, 2, 3010, 1603} {
		r := &recordingRunner{code: code}
		err := (NSISStrategy{Runner: r}).Install(context.Background(), UpdatePlan{PackagePath: "setup.exe", InstallScope: "current-user", InstallStrategy: "windows-nsis", InstallDirectory: `C:\Users\User Name\AppData\Local\Programs\HQAgent-Hub`})
		if (err == nil) != (code == 0) {
			t.Fatalf("code %d error %v", code, err)
		}
		if len(r.args) != 2 || r.args[0] != "/S" || !strings.HasPrefix(r.args[1], "/D=") {
			t.Fatal(r.args)
		}
	}
}
func TestPathRejectionAndAtomicState(t *testing.T) {
	root := t.TempDir()
	for _, path := range []string{filepath.Join(root, "..", "escape.exe"), filepath.Join(root, "setup.exe:stream"), filepath.Join(root, "NUL.exe")} {
		if err := Within(root, path); err == nil {
			t.Fatal("accepted", path)
		}
	}
	path := filepath.Join(root, "state.json")
	if err := AtomicJSON(path, map[string]string{"phase": "ready"}); err != nil {
		t.Fatal(err)
	}
	if err := AtomicJSON(path, map[string]string{"phase": "succeeded"}); err != nil {
		t.Fatal(err)
	}
	var got map[string]string
	if err := ReadJSON(path, &got); err != nil || got["phase"] != "succeeded" {
		t.Fatal(got, err)
	}
}
func TestSemverOrdering(t *testing.T) {
	for _, value := range []string{"01.0.0", "1.0.0-01", "1.0.0+", "1.0.0/../../x", "1.0.0-alpha..1"} {
		if _, err := ParseVersion(value); err == nil {
			t.Fatal("invalid version accepted", value)
		}
	}
	for _, pair := range [][2]string{{"1.0.0-beta.2", "1.0.0-beta.10"}, {"1.0.0-beta", "1.0.0"}, {"1.0.0", "2.0.0"}} {
		if CompareVersions(pair[0], pair[1]) >= 0 {
			t.Fatal(pair)
		}
	}
}
