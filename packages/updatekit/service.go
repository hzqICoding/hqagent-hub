package updatekit

import (
	"context"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"
)

type AppMeta struct{ AppID, Version, InstallType, TargetKey, OS, Arch string }
type Settings struct{ Channel string }
type ConfigProvider interface{ UpdateSettings() Settings }
type EventSink interface{ Publish(string, State) error }
type StateStore interface {
	Load() (State, error)
	Save(State) error
}
type JSONStateStore struct{ Path string }

func (s JSONStateStore) Load() (State, error) {
	var v State
	err := ReadJSON(s.Path, &v)
	return v, err
}
func (s JSONStateStore) Save(v State) error { return AtomicJSON(s.Path, v) }

var ErrBusy = errors.New("update operation already active")

type Options struct {
	Meta             AppMeta
	Config           ConfigProvider
	Client           ManifestClient
	Downloader       Downloader
	Verifier         Verifier
	Store            StateStore
	Events           EventSink
	StagingDirectory string
}

// Service follows the source update service's check/download/verify/recovery
// workflow. Persistence is synchronous and checked. A cancellation keeps the
// operation locked until the old goroutine exits, preventing stale writes.
type Service struct {
	mu      sync.Mutex
	state   State
	options Options
	busy    bool
	cancel  context.CancelFunc
}

func NewService(o Options) (*Service, error) {
	if o.Config == nil || o.Client == nil || o.Verifier == nil || o.Store == nil {
		return nil, fmt.Errorf("update dependencies required")
	}
	if o.Downloader == nil {
		o.Downloader = NewHTTPDownloader()
	}
	if err := RejectLinks(o.StagingDirectory); err != nil {
		return nil, err
	}
	s := &Service{options: o, state: State{Status: StatusIdle, CurrentVersion: o.Meta.Version, Channel: o.Config.UpdateSettings().Channel, InstallType: o.Meta.InstallType, UpdatedAt: time.Now().UTC()}}
	stored, err := o.Store.Load()
	if err == nil && stored.CurrentVersion == o.Meta.Version {
		s.state = stored
		if stored.Status == StatusReadyToInstall {
			err = Within(o.StagingDirectory, stored.PackagePath)
			if err == nil && stored.Release != nil {
				err = ValidateRelease(*stored.Release, o.Meta, stored.Channel)
			} else if err == nil {
				err = fmt.Errorf("stored release missing")
			}
			if err == nil {
				ctx, cancel := context.WithTimeout(context.Background(), time.Minute)
				err = o.Verifier.Verify(ctx, *stored.Release, stored.PackagePath)
				cancel()
			}
			if err != nil {
				s.state.Status = StatusFailed
				s.state.Error = &StateError{Code: "UPDATE_VERIFY_FAILED", Message: "stored package verification failed"}
			}
		} else {
			switch stored.Status {
			case StatusChecking, StatusDownloading, StatusDownloaded, StatusVerifying, StatusInstalling, "draining_tasks", "health_checking", "rolling_back":
				s.state.Status = StatusFailed
				s.state.Error = &StateError{Code: "INTERNAL", Message: "update interrupted; inspect recovery result"}
			}
		}
	} else if err != nil && !errors.Is(err, errors.ErrUnsupported) {
		// A missing file is a first start; malformed files are surfaced below.
		if !os.IsNotExist(err) {
			return nil, err
		}
	}
	if err = o.Store.Save(s.state); err != nil {
		return nil, err
	}
	return s, nil
}
func (s *Service) State() State { s.mu.Lock(); defer s.mu.Unlock(); return cloneState(s.state) }
func cloneState(v State) State {
	if v.Release != nil {
		x := *v.Release
		v.Release = &x
	}
	if v.Progress != nil {
		x := *v.Progress
		v.Progress = &x
	}
	if v.Error != nil {
		x := *v.Error
		v.Error = &x
	}
	return v
}
func (s *Service) persistLocked(event string) error {
	s.state.UpdatedAt = time.Now().UTC()
	if err := s.options.Store.Save(s.state); err != nil {
		s.state.Status = StatusFailed
		s.state.Error = &StateError{Code: "INTERNAL", Message: "state persistence failed"}
		return err
	}
	if s.options.Events != nil {
		return s.options.Events.Publish(event, cloneState(s.state))
	}
	return nil
}
func (s *Service) begin(parent context.Context, status string) (context.Context, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.busy {
		return nil, ErrBusy
	}
	if s.state.Status == StatusInstalling {
		return nil, ErrBusy
	}
	if status == StatusDownloading && (s.state.Release == nil || (s.state.Status != StatusAvailable && s.state.Status != StatusCancelled && s.state.Status != StatusFailed)) {
		return nil, fmt.Errorf("no downloadable release")
	}
	if status == "draining_tasks" && (s.state.Release == nil || s.state.Status != StatusReadyToInstall) {
		return nil, fmt.Errorf("package not ready")
	}
	ctx, cancel := context.WithCancel(parent)
	s.busy = true
	s.cancel = cancel
	s.state.Status = status
	s.state.Error = nil
	if err := s.persistLocked("update.state.changed"); err != nil {
		s.busy = false
		s.cancel = nil
		cancel()
		return nil, err
	}
	return ctx, nil
}
func (s *Service) finish(status string, err error) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.cancel != nil {
		s.cancel()
	}
	s.cancel = nil
	s.busy = false
	if s.state.Status == StatusCancelled {
		status = StatusCancelled
		err = nil
	}
	s.state.Status = status
	if err != nil {
		s.state.Error = &StateError{Code: "UPDATE_VERIFY_FAILED", Message: "update operation failed"}
	}
	return errors.Join(err, s.persistLocked("update.state.changed"))
}
func (s *Service) request() CheckRequest {
	o := s.options
	return CheckRequest{AppID: o.Meta.AppID, CurrentVersion: o.Meta.Version, Channel: o.Config.UpdateSettings().Channel, TargetKey: o.Meta.TargetKey, OS: o.Meta.OS, Arch: o.Meta.Arch, InstallType: o.Meta.InstallType}
}
func (s *Service) Check(parent context.Context) error {
	ctx, err := s.begin(parent, StatusChecking)
	if err != nil {
		return err
	}
	req := s.request()
	response, err := s.options.Client.Check(ctx, req)
	if err != nil {
		return s.finish(StatusFailed, err)
	}
	if response.UpdateAvailable && response.Release == nil {
		return s.finish(StatusFailed, fmt.Errorf("manifest release missing"))
	}
	if response.Release != nil {
		if err = ValidateRelease(*response.Release, s.options.Meta, req.Channel); err != nil {
			return s.finish(StatusFailed, err)
		}
	}
	s.mu.Lock()
	now := time.Now().UTC()
	s.state.LastCheckedAt = &now
	s.state.Release = nil
	s.state.PackagePath = ""
	s.state.Channel = req.Channel
	status := StatusUpToDate
	if response.UpdateAvailable && CompareVersions(response.Release.Version, s.options.Meta.Version) > 0 {
		v := *response.Release
		if v.MinimumSupportedVersion != "" && CompareVersions(s.options.Meta.Version, v.MinimumSupportedVersion) < 0 {
			v.Mandatory = true
		}
		s.state.Release = &v
		status = StatusAvailable
	}
	s.mu.Unlock()
	return s.finish(status, nil)
}
func (s *Service) Download(parent context.Context) error {
	s.mu.Lock()
	valid := s.state.Release != nil && (s.state.Status == StatusAvailable || s.state.Status == StatusCancelled || s.state.Status == StatusFailed)
	s.mu.Unlock()
	if !valid {
		return fmt.Errorf("no downloadable release")
	}
	ctx, err := s.begin(parent, StatusDownloading)
	if err != nil {
		return err
	}
	s.mu.Lock()
	release := *s.state.Release
	s.mu.Unlock()
	if err = ValidateRelease(release, s.options.Meta, release.Channel); err != nil {
		return s.finish(StatusFailed, err)
	}
	// Never use remote filename/version text to build a local path.
	target := filepath.Join(s.options.StagingDirectory, release.Package.SHA256+".exe")
	var persistErr error
	err = s.options.Downloader.Download(ctx, release.Package, target, func(p DownloadProgress) {
		s.mu.Lock()
		defer s.mu.Unlock()
		if s.state.Status != StatusDownloading {
			return
		}
		s.state.Progress = &p
		if e := s.persistLocked("update.download.progress"); e != nil {
			persistErr = e
			s.cancel()
		}
	})
	if err != nil || persistErr != nil {
		return s.finish(StatusFailed, errors.Join(err, persistErr))
	}
	for _, phase := range []string{StatusDownloaded, StatusVerifying} {
		s.mu.Lock()
		if ctx.Err() != nil {
			s.mu.Unlock()
			return s.finish(StatusCancelled, nil)
		}
		s.state.Status = phase
		s.state.PackagePath = target
		err = s.persistLocked("update.state.changed")
		s.mu.Unlock()
		if err != nil {
			return s.finish(StatusFailed, err)
		}
	}
	if err = s.options.Verifier.Verify(ctx, release, target); err != nil {
		return s.finish(StatusFailed, err)
	}
	return s.finish(StatusReadyToInstall, nil)
}
func (s *Service) Cancel() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if !s.busy || s.cancel == nil || s.state.Status == StatusInstalling || s.state.Status == "draining_tasks" {
		return fmt.Errorf("no cancellable operation")
	}
	s.cancel()
	s.state.Status = StatusCancelled
	return s.persistLocked("update.state.changed")
}
func (s *Service) Releases(ctx context.Context) ([]Release, error) {
	return s.options.Client.Releases(ctx, s.request())
}

// PrepareInstall holds the same operation gate as downloads/checks and verifies
// again before invoking the product's drain/plan/helper coordinator.
func (s *Service) PrepareInstall(ctx context.Context, prepare func(context.Context, Release, string) error) error {
	s.mu.Lock()
	ready := s.state.Status == StatusReadyToInstall && s.state.Release != nil
	state := cloneState(s.state)
	s.mu.Unlock()
	if !ready {
		return fmt.Errorf("package not ready")
	}
	ctx, err := s.begin(ctx, "draining_tasks")
	if err != nil {
		return err
	}
	if err = Within(s.options.StagingDirectory, state.PackagePath); err == nil {
		err = s.options.Verifier.Verify(ctx, *state.Release, state.PackagePath)
	}
	if err == nil {
		err = prepare(ctx, *state.Release, state.PackagePath)
	}
	if err != nil {
		return s.finish(StatusFailed, err)
	}
	return s.finish(StatusInstalling, nil)
}
func ValidateRelease(r Release, m AppMeta, channel string) error {
	if _, err := ParseVersion(r.Version); err != nil {
		return err
	}
	if channel != "stable" && channel != "beta" || r.Channel != channel || r.Package.OS != m.OS || r.Package.Arch != m.Arch || r.Package.Type != m.InstallType {
		return fmt.Errorf("release channel/platform/type mismatch")
	}
	// Legacy OTA responses lack targetKey; the request still selects it exactly.
	if r.Package.TargetKey != "" && r.Package.TargetKey != m.TargetKey {
		return fmt.Errorf("release targetKey mismatch")
	}
	if r.MinimumSupportedVersion != "" {
		if _, err := ParseVersion(r.MinimumSupportedVersion); err != nil {
			return err
		}
	}
	digest, err := hex.DecodeString(r.Package.SHA256)
	if err != nil || len(digest) != 32 || r.Package.Size <= 0 || r.Package.Signature == "" {
		return fmt.Errorf("release security metadata missing")
	}
	return ValidateURL(r.Package.URL)
}
