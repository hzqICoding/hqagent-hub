//go:build windows

package updatekit

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

var kernel32 = syscall.NewLazyDLL("kernel32.dll")

func rejectLink(path string) error {
	p, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return err
	}
	a, err := syscall.GetFileAttributes(p)
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return err
	}
	if a&syscall.FILE_ATTRIBUTE_REPARSE_POINT != 0 {
		return fmt.Errorf("reparse point rejected")
	}
	return nil
}
func replaceFile(source, target string) error {
	s, err := syscall.UTF16PtrFromString(source)
	if err != nil {
		return err
	}
	t, err := syscall.UTF16PtrFromString(target)
	if err != nil {
		return err
	}
	r, _, err := kernel32.NewProc("MoveFileExW").Call(uintptr(unsafe.Pointer(s)), uintptr(unsafe.Pointer(t)), 0x1|0x8)
	if r == 0 {
		return err
	}
	return nil
}
func ConfigureChild(c *exec.Cmd) {
	c.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000}
}

func configureInstallerCommand(c *exec.Cmd, path string, args []string) {
	// NSIS parses the terminal /D value from the raw Windows command line;
	// unlike ordinary argv it must remain unquoted even when it contains spaces.
	if len(args) == 2 && args[0] == "/S" {
		c.SysProcAttr.CmdLine = syscall.EscapeArg(path) + " /S " + args[1]
	}
}

func powerShell(ctx context.Context, script string, env ...string) error {
	// Use the OS binary, never PATH or a executable supplied by a Plan.
	c := exec.CommandContext(ctx, filepath.Join(os.Getenv("SystemRoot"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe"), "-NoProfile", "-NonInteractive", "-Command", script)
	// A Go child started by pwsh 7 inherits its PSModulePath, which cannot load
	// Windows PowerShell 5 security cmdlets. Pin the OS module directory too.
	for _, entry := range os.Environ() {
		if !strings.HasPrefix(strings.ToUpper(entry), "PSMODULEPATH=") {
			c.Env = append(c.Env, entry)
		}
	}
	c.Env = append(c.Env, "PSModulePath="+filepath.Join(os.Getenv("SystemRoot"), "System32", "WindowsPowerShell", "v1.0", "Modules"))
	c.Env = append(c.Env, env...)
	ConfigureChild(c)
	if err := c.Run(); err != nil {
		return fmt.Errorf("Windows security operation failed: %w", err)
	}
	return nil
}

func SecurePath(path string, directory bool) error {
	if err := RejectLinks(path); err != nil {
		return err
	}
	token, err := syscall.OpenCurrentProcessToken()
	if err != nil {
		return err
	}
	defer token.Close()
	user, err := token.GetTokenUser()
	if err != nil {
		return err
	}
	sid, err := user.User.Sid.String()
	if err != nil {
		return err
	}
	inherit := ""
	if directory {
		inherit = "OICI"
	}
	sddl, err := syscall.UTF16PtrFromString("D:P(A;" + inherit + ";FA;;;" + sid + ")")
	if err != nil {
		return err
	}
	advapi := syscall.NewLazyDLL("advapi32.dll")
	var descriptor uintptr
	ok, _, err := advapi.NewProc("ConvertStringSecurityDescriptorToSecurityDescriptorW").Call(uintptr(unsafe.Pointer(sddl)), 1, uintptr(unsafe.Pointer(&descriptor)), 0)
	if ok == 0 {
		return err
	}
	defer kernel32.NewProc("LocalFree").Call(descriptor)
	p, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return err
	}
	// Set only a protected DACL. No audit/SACL or owner write is requested, so
	// ordinary current-user installs do not need SeSecurityPrivilege or UAC.
	ok, _, err = advapi.NewProc("SetFileSecurityW").Call(uintptr(unsafe.Pointer(p)), 0x4|0x80000000, descriptor)
	if ok == 0 {
		return err
	}
	return nil
}

// AcquireLock uses a kernel-held exclusive handle; crashes release it.
func AcquireLock(path string) (func(), error) {
	if err := RejectLinks(path); err != nil {
		return nil, err
	}
	p, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return nil, err
	}
	h, err := syscall.CreateFile(p, syscall.GENERIC_READ|syscall.GENERIC_WRITE, 0, nil, syscall.OPEN_ALWAYS, syscall.FILE_ATTRIBUTE_NORMAL, 0)
	if err != nil {
		return nil, fmt.Errorf("update process already running or lock unavailable: %w", err)
	}
	return func() { syscall.CloseHandle(h) }, nil
}

// Access denied is not evidence that a process has exited. All wait failures
// abort installation. Open handles also avoid confusing PID reuse while waiting.
func WaitPIDs(ctx context.Context, pids []int) error {
	var handles []syscall.Handle
	defer func() {
		for _, h := range handles {
			syscall.CloseHandle(h)
		}
	}()
	for _, pid := range pids {
		if pid <= 0 || pid == os.Getpid() {
			return fmt.Errorf("invalid wait pid")
		}
		h, err := syscall.OpenProcess(syscall.SYNCHRONIZE, false, uint32(pid))
		if err == syscall.Errno(87) {
			continue
		}
		if err != nil {
			return fmt.Errorf("cannot wait for process: %w", err)
		}
		handles = append(handles, h)
	}
	for _, h := range handles {
		for {
			if err := ctx.Err(); err != nil {
				return err
			}
			r, err := syscall.WaitForSingleObject(h, 100)
			if err != nil {
				return err
			}
			if r == syscall.WAIT_OBJECT_0 {
				break
			}
			if r != syscall.WAIT_TIMEOUT {
				return fmt.Errorf("unexpected process wait result")
			}
		}
	}
	return nil
}

type AuthenticodeVerifier struct{ TrustedThumbprints []string }

func (v AuthenticodeVerifier) VerifyCodeSignature(ctx context.Context, path string) error {
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	if len(v.TrustedThumbprints) == 0 {
		return fmt.Errorf("trusted Authenticode signer required")
	}
	allowed := ""
	for _, t := range v.TrustedThumbprints {
		if len(t) != 40 && len(t) != 64 {
			return fmt.Errorf("invalid signer thumbprint")
		}
		for _, r := range t {
			if !(r >= '0' && r <= '9' || r >= 'a' && r <= 'f' || r >= 'A' && r <= 'F') {
				return fmt.Errorf("invalid signer thumbprint")
			}
		}
		allowed += t + ";"
	}
	return powerShell(ctx, `$ErrorActionPreference='Stop'; $sig=Get-AuthenticodeSignature -LiteralPath $env:HQUPDATE_VERIFY_PATH; if ($sig.Status -ne 'Valid' -or $null -eq $sig.SignerCertificate -or $sig.SignerCertificate.Thumbprint -notin ($env:HQUPDATE_SIGNERS -split ';')) { exit 1 }`, "HQUPDATE_VERIFY_PATH="+path, "HQUPDATE_SIGNERS="+allowed)
}
