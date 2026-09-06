package product

import (
	"context"
	"crypto/rand"
	"crypto/subtle"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"sync"
	"time"

	"hqagent.local/protocol"
	kit "hqupdatekit.local/updatekit"
)

type Server struct {
	Service     *kit.Service
	Store       Store
	Policy      kit.PlanPolicy
	Prepare     func(context.Context, kit.Release, string) error
	Token, Host string
	Shutdown    func()
	gate        sync.Mutex
	Lifetime    context.Context
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /internal/v1/state", func(w http.ResponseWriter, r *http.Request) { s.write(w, StateDTO(s.Service.State())) })
	mux.HandleFunc("POST /internal/v1/check", func(w http.ResponseWriter, r *http.Request) {
		s.command(w, r, func(ctx context.Context) error { return s.Service.Check(ctx) }, false)
	})
	mux.HandleFunc("POST /internal/v1/download", func(w http.ResponseWriter, r *http.Request) {
		s.command(w, r, func(ctx context.Context) error { return s.Service.Download(ctx) }, true)
	})
	mux.HandleFunc("POST /internal/v1/cancel", func(w http.ResponseWriter, r *http.Request) {
		if err := s.Service.Cancel(); err != nil {
			http.Error(w, "UPDATE_BUSY", 409)
			return
		}
		w.WriteHeader(200)
	})
	mux.HandleFunc("POST /internal/v1/install", func(w http.ResponseWriter, r *http.Request) {
		if !s.gate.TryLock() {
			http.Error(w, "UPDATE_BUSY", 409)
			return
		}
		defer s.gate.Unlock()
		if s.Prepare == nil {
			http.Error(w, "FEATURE_UNAVAILABLE", 501)
			return
		}
		if err := s.Service.PrepareInstall(r.Context(), s.Prepare); err != nil {
			http.Error(w, "UPDATE_VERIFY_FAILED", 422)
			return
		}
		w.WriteHeader(200)
		if f, ok := w.(http.Flusher); ok {
			f.Flush()
		}
		if s.Shutdown != nil {
			go s.Shutdown()
		}
	})
	mux.HandleFunc("GET /internal/v1/result", func(w http.ResponseWriter, r *http.Request) {
		v, err := s.Store.Result()
		if err != nil {
			http.Error(w, "INTERNAL", 500)
			return
		}
		if v == nil {
			w.WriteHeader(204)
			return
		}
		s.write(w, v)
	})
	mux.HandleFunc("GET /internal/v1/releases", func(w http.ResponseWriter, r *http.Request) {
		items, err := s.Service.Releases(r.Context())
		if err != nil {
			http.Error(w, "INTERNAL", 502)
			return
		}
		views := []protocol.ReleaseInfo{}
		for _, item := range items {
			views = append(views, ReleaseDTO(item))
		}
		s.write(w, views)
	})
	mux.HandleFunc("GET /internal/v1/events", func(w http.ResponseWriter, r *http.Request) {
		// Frozen OpenAPI does not specify media type, event envelope or cursor.
		// Do not invent a competing wire contract. See T-W6-updatekit.md.
		http.Error(w, "FEATURE_UNAVAILABLE", 501)
	})
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		host, _, err := net.SplitHostPort(r.RemoteAddr)
		if err != nil || host != "127.0.0.1" || r.Host != s.Host || r.Header.Get("Origin") != "" {
			http.Error(w, "UNAUTHORIZED", 401)
			return
		}
		if subtle.ConstantTimeCompare([]byte(r.Header.Get("Authorization")), []byte("Bearer "+s.Token)) != 1 {
			http.Error(w, "UNAUTHORIZED", 401)
			return
		}
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		r.Body = http.MaxBytesReader(w, r.Body, 64<<10)
		mux.ServeHTTP(w, r)
	})
}
func (s *Server) write(w http.ResponseWriter, value any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(value)
}
func (s *Server) command(w http.ResponseWriter, r *http.Request, operation func(context.Context) error, background bool) {
	if !s.gate.TryLock() {
		http.Error(w, "UPDATE_BUSY", 409)
		return
	}
	if !background {
		defer s.gate.Unlock()
		if err := operation(r.Context()); err != nil {
			http.Error(w, "UPDATE_VERIFY_FAILED", 422)
			return
		}
		s.write(w, StateDTO(s.Service.State()))
		return
	}
	ctx := s.Lifetime
	if ctx == nil {
		ctx = context.Background()
	}
	done := make(chan error, 1)
	before := s.Service.State().UpdatedAt
	go func() { defer s.gate.Unlock(); done <- operation(ctx) }()
	// Return the persisted downloading state, not a stale available snapshot.
	tick := time.NewTicker(time.Millisecond)
	defer tick.Stop()
	for {
		select {
		case err := <-done:
			if err != nil {
				http.Error(w, "UPDATE_VERIFY_FAILED", 422)
				return
			}
			s.write(w, StateDTO(s.Service.State()))
			return
		case <-tick.C:
			state := s.Service.State()
			if state.UpdatedAt.After(before) {
				s.write(w, StateDTO(state))
				return
			}
		case <-r.Context().Done():
			return
		}
	}
}
func randomID() (string, error) {
	v := make([]byte, 32)
	if _, err := rand.Read(v); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(v), nil
}
func RunAgent(ctx context.Context) error {
	p, err := Policy(os.Getenv("LOCALAPPDATA"))
	if err != nil {
		return err
	}
	if err = PrepareDirectories(p); err != nil {
		return err
	}
	release, err := kit.AcquireLock(filepath.Join(p.DataDirectory, "runtime", "update-agent.lock"))
	if err != nil {
		return err
	}
	defer release()
	// A replacement Agent can be launched while the updater is health-checking.
	// Keep this process alive but do not overwrite its state/result files until
	// the independent updater has released its kernel-held transaction lock.
	for {
		unlock, e := kit.AcquireLock(filepath.Join(p.UpdatesDirectory, "updater.lock"))
		if e == nil {
			unlock()
			break
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(100 * time.Millisecond):
		}
	}
	c, verifier, err := LoadTrust(p)
	if err != nil {
		return err
	}
	client, err := kit.NewHTTPManifestClient(c.ManifestBaseURL)
	if err != nil {
		return err
	}
	store := Store{Policy: p}
	service, err := kit.NewService(kit.Options{Meta: Meta(), Config: c, Client: client, Verifier: verifier, Store: store, StagingDirectory: filepath.Join(p.UpdatesDirectory, "staging")})
	if err != nil {
		return err
	}
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		return err
	}
	defer listener.Close()
	port := listener.Addr().(*net.TCPAddr).Port
	if port < 1024 {
		return fmt.Errorf("high port required")
	}
	token, err := randomID()
	if err != nil {
		return err
	}
	instance, err := randomID()
	if err != nil {
		return err
	}
	host := "127.0.0.1:" + strconv.Itoa(port)
	d := protocol.UpdateAgentRuntimeDescriptor{SchemaVersion: 1, InstanceId: instance, Port: int64(port), Token: token, Pid: int64(os.Getpid()), BaseUrl: "http://" + host, AgentVersion: Version, StartedAt: time.Now().UTC().Format(time.RFC3339Nano)}
	descriptorPath := filepath.Join(p.DataDirectory, "runtime", "update-agent.json")
	if err = kit.AtomicJSON(descriptorPath, d); err != nil {
		return err
	}
	defer os.Remove(descriptorPath)
	life, cancel := context.WithCancel(ctx)
	defer cancel()
	s := &Server{Service: service, Store: store, Policy: p, Token: token, Host: host, Lifetime: life, Prepare: (HubClient{Policy: p, AgentPID: os.Getpid()}).Prepare, Shutdown: cancel}
	httpServer := &http.Server{Handler: s.Handler(), ReadHeaderTimeout: 5 * time.Second, IdleTimeout: 30 * time.Second, MaxHeaderBytes: 16 << 10}
	done := make(chan error, 1)
	go func() { done <- httpServer.Serve(listener) }()
	select {
	case err = <-done:
		if err != http.ErrServerClosed {
			return err
		}
	case <-life.Done():
	}
	stop, stopCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer stopCancel()
	return httpServer.Shutdown(stop)
}
