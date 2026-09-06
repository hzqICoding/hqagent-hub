package updatekit

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

// Within checks lexical containment and every existing ancestor for links.
// It does not authorize a root: callers supply product-owned absolute roots.
func Within(root, path string) error {
	if !filepath.IsAbs(root) || !filepath.IsAbs(path) {
		return fmt.Errorf("absolute paths required")
	}
	r, err := filepath.Rel(root, path)
	if err != nil || r == ".." || strings.HasPrefix(r, ".."+string(filepath.Separator)) {
		return fmt.Errorf("path outside controlled directory")
	}
	if err := RejectLinks(root); err != nil {
		return err
	}
	return RejectLinks(path)
}

func RejectLinks(path string) error {
	if !filepath.IsAbs(path) {
		return fmt.Errorf("absolute path required")
	}
	clean := filepath.Clean(path)
	for p := clean; ; p = filepath.Dir(p) {
		if err := rejectLink(p); err != nil {
			return err
		}
		if filepath.Dir(p) == p {
			break
		}
	}
	// Reject Windows alternate data streams, device names and path aliases.
	for _, part := range strings.FieldsFunc(strings.TrimPrefix(clean, filepath.VolumeName(clean)), func(r rune) bool { return r == '/' || r == '\\' }) {
		stem := strings.ToUpper(strings.SplitN(part, ".", 2)[0])
		if strings.ContainsAny(part, ":\x00\r\n\"<>|?*") || strings.TrimRight(part, " .") != part || stem == "CON" || stem == "NUL" || stem == "PRN" || stem == "AUX" || (len(stem) == 4 && (strings.HasPrefix(stem, "COM") || strings.HasPrefix(stem, "LPT")) && stem[3] >= '0' && stem[3] <= '9') {
			return fmt.Errorf("unsafe path component")
		}
	}
	return nil
}

func ReadJSON(path string, value any) error {
	if err := RejectLinks(path); err != nil {
		return err
	}
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	b, err := io.ReadAll(io.LimitReader(f, (2<<20)+1))
	if err != nil {
		return err
	}
	if len(b) > 2<<20 {
		return fmt.Errorf("JSON size limit")
	}
	d := json.NewDecoder(bytes.NewReader(b))
	d.DisallowUnknownFields()
	if err := d.Decode(value); err != nil {
		return err
	}
	if err := d.Decode(new(any)); err != io.EOF {
		return fmt.Errorf("trailing JSON")
	}
	return nil
}

// AtomicJSON never exposes a partially written token or removes the old state
// before replacement. The temporary file is secured before it receives data.
func AtomicJSON(path string, value any) error {
	if err := RejectLinks(path); err != nil {
		return err
	}
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	if err = os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		return err
	}
	f, err := os.CreateTemp(filepath.Dir(path), ".update-*")
	if err != nil {
		return err
	}
	name := f.Name()
	defer os.Remove(name)
	if err = SecurePath(name, false); err != nil {
		f.Close()
		return err
	}
	if _, err = f.Write(data); err != nil {
		f.Close()
		return err
	}
	if err = f.Sync(); err != nil {
		f.Close()
		return err
	}
	if err = f.Close(); err != nil {
		return err
	}
	return replaceFile(name, path)
}

// CopyFile is extracted from the old helper with checked links and atomic
// replacement. It is shared by helper staging, program backup and DB restore.
func CopyFile(source, target string) error {
	if err := RejectLinks(source); err != nil {
		return err
	}
	if err := RejectLinks(target); err != nil {
		return err
	}
	in, err := os.Open(source)
	if err != nil {
		return err
	}
	defer in.Close()
	info, err := in.Stat()
	if err != nil {
		return err
	}
	if !info.Mode().IsRegular() {
		return fmt.Errorf("regular file required")
	}
	if err = os.MkdirAll(filepath.Dir(target), 0700); err != nil {
		return err
	}
	out, err := os.CreateTemp(filepath.Dir(target), ".copy-*")
	if err != nil {
		return err
	}
	defer os.Remove(out.Name())
	if _, err = io.Copy(out, in); err != nil {
		out.Close()
		return err
	}
	if err = out.Chmod(info.Mode().Perm()); err != nil {
		out.Close()
		return err
	}
	if err = out.Sync(); err != nil {
		out.Close()
		return err
	}
	if err = out.Close(); err != nil {
		return err
	}
	return replaceFile(out.Name(), target)
}

func CopyTree(source, target string) error {
	if err := RejectLinks(source); err != nil {
		return err
	}
	if err := RejectLinks(target); err != nil {
		return err
	}
	return filepath.WalkDir(source, func(path string, entry os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if err = RejectLinks(path); err != nil {
			return err
		}
		rel, err := filepath.Rel(source, path)
		if err != nil {
			return err
		}
		dst := filepath.Join(target, rel)
		if entry.IsDir() {
			return os.MkdirAll(dst, 0700)
		}
		return CopyFile(path, dst)
	})
}
