//go:build !windows

package updatekit

import (
	"context"
	"fmt"
	"os"
	"os/exec"
)

func rejectLink(path string) error {
	i, e := os.Lstat(path)
	if os.IsNotExist(e) {
		return nil
	}
	if e != nil {
		return e
	}
	if i.Mode()&os.ModeSymlink != 0 {
		return fmt.Errorf("symlink rejected")
	}
	return nil
}
func replaceFile(a, b string) error { return os.Rename(a, b) }
func ConfigureChild(c *exec.Cmd)    {}
func runInstallerProcess(context.Context, string, []string) (int, error) {
	return -1, fmt.Errorf("NSIS process containment requires Windows")
}
func SecurePath(p string, d bool) error {
	if d {
		return os.Chmod(p, 0700)
	}
	return os.Chmod(p, 0600)
}
func AcquireLock(p string) (func(), error) {
	return nil, fmt.Errorf("process locks require Windows in phase 1")
}
func WaitPIDs(context.Context, []int) error {
	return fmt.Errorf("process waiting requires Windows in phase 1")
}

type AuthenticodeVerifier struct{ TrustedThumbprints []string }

func (AuthenticodeVerifier) VerifyCodeSignature(context.Context, string) error {
	return fmt.Errorf("Authenticode requires Windows")
}
