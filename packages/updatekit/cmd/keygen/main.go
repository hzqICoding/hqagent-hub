// keygen creates an independent product release key. Private output belongs on
// an offline release workstation, never under the source checkout.
package main

import (
	"crypto/ed25519"
	"crypto/rand"
	"crypto/x509"
	"encoding/base64"
	"encoding/pem"
	"flag"
	"fmt"
	kit "hqupdatekit.local/updatekit"
	"os"
	"path/filepath"
)

func main() {
	path := flag.String("private", "", "new private PEM outside the source checkout")
	flag.Parse()
	if err := generate(*path); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
func generate(path string) error {
	if !filepath.IsAbs(path) {
		return fmt.Errorf("absolute private-key output required")
	}
	if err := kit.RejectLinks(path); err != nil {
		return err
	}
	for p := filepath.Dir(path); ; p = filepath.Dir(p) {
		if _, err := os.Stat(filepath.Join(p, ".git")); err == nil {
			return fmt.Errorf("private keys must be outside a Git checkout")
		}
		if filepath.Dir(p) == p {
			break
		}
	}
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		return err
	}
	if err := kit.SecurePath(filepath.Dir(path), true); err != nil {
		return err
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	defer f.Close()
	if err = kit.SecurePath(path, false); err != nil {
		return err
	}
	public, private, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return err
	}
	der, err := x509.MarshalPKCS8PrivateKey(private)
	if err != nil {
		return err
	}
	if err = pem.Encode(f, &pem.Block{Type: "PRIVATE KEY", Bytes: der}); err != nil {
		return err
	}
	if err = f.Sync(); err != nil {
		return err
	}
	fmt.Println("hqagent-hub-test:", base64.StdEncoding.EncodeToString(public))
	return nil
}
