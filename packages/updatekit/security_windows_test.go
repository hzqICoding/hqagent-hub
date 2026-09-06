//go:build windows

package updatekit

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestCurrentUserOnlyProtectedACLAndExclusiveLock(t *testing.T) {
	dir := t.TempDir()
	if err := SecurePath(dir, true); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dir, "descriptor.json")
	if err := AtomicJSON(path, map[string]string{"value": "not-a-secret"}); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	script := `$ErrorActionPreference='Stop'; $acl=Get-Acl -LiteralPath $env:HQUPDATE_ACL_PATH; $sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value; if (!$acl.AreAccessRulesProtected -or @($acl.Access).Count -ne 1 -or $acl.Access[0].IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value -ne $sid) { exit 1 }`
	if err := powerShell(ctx, script, "HQUPDATE_ACL_PATH="+path); err != nil {
		c := exec.Command(filepath.Join(os.Getenv("SystemRoot"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe"), "-NoProfile", "-Command", `Get-Acl -LiteralPath $env:HQUPDATE_ACL_PATH | Format-List AreAccessRulesProtected,AccessToString,Sddl`)
		c.Env = append(os.Environ(), "HQUPDATE_ACL_PATH="+path)
		b, _ := c.CombinedOutput()
		t.Fatalf("%v\n%s", err, b)
	}
	unlock, err := AcquireLock(filepath.Join(dir, "process.lock"))
	if err != nil {
		t.Fatal(err)
	}
	defer unlock()
	if release, err := AcquireLock(filepath.Join(dir, "process.lock")); err == nil {
		release()
		t.Fatal("second process lock accepted")
	}
	t.Log("descriptor DACL protected; exactly one current-user SID ACE; duplicate lock denied")
}
func TestAuthenticodeRejectsUnsignedExecutable(t *testing.T) {
	exe, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	verifier := AuthenticodeVerifier{TrustedThumbprints: []string{"0000000000000000000000000000000000000000"}}
	if err = verifier.VerifyCodeSignature(ctx, exe); err == nil {
		t.Fatal("unsigned/wrong signer executable accepted")
	}
	t.Log("production Authenticode verifier rejected unsigned/wrong-publisher test executable")
}

func TestAuthenticodeAcceptsPinnedOperatingSystemSigner(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	exe := filepath.Join(os.Getenv("SystemRoot"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
	output := filepath.Join(t.TempDir(), "thumbprint.txt")
	if err := powerShell(ctx, `$ErrorActionPreference='Stop'; $sig=Get-AuthenticodeSignature -LiteralPath $env:HQUPDATE_VERIFY_PATH; if ($sig.Status -ne 'Valid') { exit 1 }; [System.IO.File]::WriteAllText($env:HQUPDATE_THUMBPRINT_OUT,$sig.SignerCertificate.Thumbprint)`, "HQUPDATE_VERIFY_PATH="+exe, "HQUPDATE_THUMBPRINT_OUT="+output); err != nil {
		t.Fatal(err)
	}
	thumb, err := os.ReadFile(output)
	if err != nil {
		t.Fatal(err)
	}
	v := AuthenticodeVerifier{TrustedThumbprints: []string{strings.TrimSpace(string(thumb))}}
	if err = v.VerifyCodeSignature(ctx, exe); err != nil {
		t.Fatal(err)
	}
	t.Log("production Authenticode verifier accepted an OS-signed binary with its exact configured signer pin")
}
func TestJunctionCannotRedirectControlledPaths(t *testing.T) {
	root := t.TempDir()
	target := t.TempDir()
	link := filepath.Join(root, "redirect")
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := powerShell(ctx, `$ErrorActionPreference='Stop'; New-Item -ItemType Junction -Path $env:HQUPDATE_LINK -Target $env:HQUPDATE_TARGET | Out-Null`, "HQUPDATE_LINK="+link, "HQUPDATE_TARGET="+target); err != nil {
		t.Fatal(err)
	}
	if err := Within(root, filepath.Join(link, "setup.exe")); err == nil {
		t.Fatal("junction accepted")
	}
	t.Log("Windows junction rejected before package access")
}
