package main

import (
	"context"
	"flag"
	"fmt"
	"hqagent.local/update-agent/product"
	kit "hqupdatekit.local/updatekit"
	"os"
	"path/filepath"
)

func main() {
	plan := flag.String("plan", "", "controlled Update Plan v2 path")
	version := flag.Bool("version", false, "print product version")
	flag.Parse()
	if *version {
		fmt.Println(product.Version)
		return
	}
	if err := run(*plan); err != nil {
		fmt.Fprintln(os.Stderr, "Updater failed:", err)
		os.Exit(1)
	}
}
func run(path string) error {
	p, err := product.Policy(os.Getenv("LOCALAPPDATA"))
	if err != nil {
		return err
	}
	// Validate the controlled plan before reading any rollback material.
	if _, err = kit.ReadPlan(path, p); err != nil {
		return err
	}
	exe, err := os.Executable()
	if err != nil {
		return err
	}
	if err = kit.Within(filepath.Join(p.UpdatesDirectory, "helper"), exe); err != nil {
		return fmt.Errorf("Updater must run from the controlled helper directory")
	}
	release, err := kit.AcquireLock(filepath.Join(p.UpdatesDirectory, "updater.lock"))
	if err != nil {
		return err
	}
	defer release()
	_, verifier, err := product.LoadTrust(p)
	if err != nil {
		return err
	}
	store := product.Store{Policy: p}
	helper := kit.Helper{Policy: p, Verifier: verifier, Strategy: kit.NSISStrategy{}, Health: product.HealthProbe{Policy: p}, Results: store, States: store}
	_, err = helper.Run(context.Background(), path)
	return err
}
