package updatekit

import (
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"io"
	"os"
	"strings"
)

type Verifier interface {
	Verify(context.Context, Release, string) error
}

type CodeSignatureVerifier interface {
	VerifyCodeSignature(context.Context, string) error
}

type PackageVerifier struct {
	trustedKeys   map[string]ed25519.PublicKey
	defaultKeyID  string
	codeSignature CodeSignatureVerifier
}

// Keys belong to one product. No key, algorithm or signature is taken on trust
// from the downloaded manifest. The legacy default allows the current OTA API
// (which omits keyId and signatureAlgorithm) to migrate without sharing keys.
func NewTrustedVerifier(keys map[string]ed25519.PublicKey, defaultKeyID string, code CodeSignatureVerifier) (*PackageVerifier, error) {
	if len(keys) == 0 || code == nil {
		return nil, fmt.Errorf("both OTA and OS trust are required")
	}
	v := &PackageVerifier{trustedKeys: map[string]ed25519.PublicKey{}, defaultKeyID: defaultKeyID, codeSignature: code}
	for id, k := range keys {
		if id == "" || len(k) != ed25519.PublicKeySize {
			return nil, fmt.Errorf("invalid trusted key")
		}
		v.trustedKeys[id] = append(ed25519.PublicKey(nil), k...)
	}
	if defaultKeyID != "" && v.trustedKeys[defaultKeyID] == nil {
		return nil, fmt.Errorf("unknown default key")
	}
	return v, nil
}

func (v *PackageVerifier) Verify(ctx context.Context, release Release, packagePath string) error {
	if release.Package.SignatureAlgorithm != "" && release.Package.SignatureAlgorithm != "ed25519-sha256" {
		return fmt.Errorf("unsupported signature algorithm")
	}
	id := release.Package.KeyID
	if id == "" {
		id = v.defaultKeyID
	}
	publicKey := v.trustedKeys[id]
	if len(publicKey) != ed25519.PublicKeySize {
		return fmt.Errorf("untrusted signing key")
	}
	info, err := os.Stat(packagePath)
	if err != nil {
		return err
	}
	if !info.Mode().IsRegular() || release.Package.Size <= 0 || info.Size() != release.Package.Size {
		return fmt.Errorf("package size mismatch: expected %d, got %d", release.Package.Size, info.Size())
	}
	file, err := os.Open(packagePath)
	if err != nil {
		return err
	}
	defer file.Close()
	hash := sha256.New()
	buffer := make([]byte, 256<<10)
	for {
		if err := ctx.Err(); err != nil {
			return err
		}
		count, readErr := file.Read(buffer)
		if count > 0 {
			_, _ = hash.Write(buffer[:count])
		}
		if readErr == io.EOF {
			break
		}
		if readErr != nil {
			return readErr
		}
	}
	digest := hash.Sum(nil)
	if !strings.EqualFold(hex.EncodeToString(digest), strings.TrimSpace(release.Package.SHA256)) {
		return fmt.Errorf("package SHA-256 mismatch")
	}
	signature, err := base64.StdEncoding.DecodeString(release.Package.Signature)
	if err != nil || len(signature) != ed25519.SignatureSize {
		return fmt.Errorf("invalid package signature")
	}
	if !ed25519.Verify(publicKey, digest, signature) {
		return fmt.Errorf("package signature verification failed")
	}
	return v.codeSignature.VerifyCodeSignature(ctx, packagePath)
}
