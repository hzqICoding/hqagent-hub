// Package product contains only HQAgent-Hub policy, generated DTO mappings and
// Local Hub integration. The update workflow lives in HQUpdateKit.
package product

import (
	"crypto/ed25519"
	"encoding/base64"
	"fmt"
	"os"
	"path/filepath"
	"runtime"

	kit "hqupdatekit.local/updatekit"
)

var Version = "0.1.0" // W7 injects the root product VERSION using -ldflags -X.
const WireVersion = "1.0"

type TrustConfig struct {
	ManifestBaseURL         string            `json:"manifestBaseUrl"`
	Channel                 string            `json:"channel"`
	TrustedKeys             map[string]string `json:"trustedKeys"`
	DefaultKeyID            string            `json:"defaultKeyId"`
	AuthenticodeThumbprints []string          `json:"authenticodeThumbprints"`
}

func (c TrustConfig) UpdateSettings() kit.Settings { return kit.Settings{Channel: c.Channel} }
func Policy(localAppData string) (kit.PlanPolicy, error) {
	if !filepath.IsAbs(localAppData) {
		return kit.PlanPolicy{}, fmt.Errorf("LOCALAPPDATA must be absolute")
	}
	root := filepath.Join(localAppData, "HQAgent-Hub")
	p := kit.PlanPolicy{AppID: "hqagent-hub", TargetKey: "windows-amd64-installer", OS: "windows", Arch: "amd64", InstallDirectory: filepath.Join(localAppData, "Programs", "HQAgent-Hub"), DataDirectory: root, UpdatesDirectory: filepath.Join(root, "updates"), ProtocolVersion: WireVersion, AllowedExecutables: map[string]string{"core": "hqagent-core.exe", "desktop": "hqagent-desktop.exe", "update-agent": "hqagent-update-agent.exe"}}
	for _, path := range []string{p.DataDirectory, p.InstallDirectory} {
		if err := kit.RejectLinks(path); err != nil {
			return p, err
		}
	}
	return p, nil
}
func PrepareDirectories(p kit.PlanPolicy) error {
	// Nothing under the install directory is created or written by the Agent.
	for _, path := range []string{p.DataDirectory, filepath.Join(p.DataDirectory, "runtime"), filepath.Join(p.DataDirectory, "config"), p.UpdatesDirectory, filepath.Join(p.UpdatesDirectory, "staging"), filepath.Join(p.UpdatesDirectory, "backup"), filepath.Join(p.UpdatesDirectory, "installed")} {
		if err := kit.RejectLinks(path); err != nil {
			return err
		}
		if err := os.MkdirAll(path, 0700); err != nil {
			return err
		}
		if err := kit.SecurePath(path, true); err != nil {
			return err
		}
	}
	return nil
}
func LoadTrust(p kit.PlanPolicy) (TrustConfig, *kit.PackageVerifier, error) {
	var c TrustConfig
	err := kit.ReadJSON(filepath.Join(p.DataDirectory, "config", "update-trust.json"), &c)
	if err != nil {
		return c, nil, err
	}
	if c.Channel != "stable" && c.Channel != "beta" {
		return c, nil, fmt.Errorf("invalid update channel")
	}
	keys := map[string]ed25519.PublicKey{}
	for id, value := range c.TrustedKeys {
		raw, e := base64.StdEncoding.DecodeString(value)
		if e != nil {
			return c, nil, fmt.Errorf("invalid public key")
		}
		keys[id] = ed25519.PublicKey(raw)
	}
	v, err := kit.NewTrustedVerifier(keys, c.DefaultKeyID, kit.AuthenticodeVerifier{TrustedThumbprints: c.AuthenticodeThumbprints})
	return c, v, err
}
func Meta() kit.AppMeta {
	return kit.AppMeta{AppID: "hqagent-hub", Version: Version, InstallType: "installer", TargetKey: "windows-amd64-installer", OS: runtime.GOOS, Arch: runtime.GOARCH}
}
