package main

import (
	"context"
	"fmt"
	"hqagent.local/update-agent/product"
	"os"
	"os/signal"
)

func main() {
	if len(os.Args) == 2 && os.Args[1] == "--version" {
		fmt.Println(product.Version)
		return
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()
	if err := product.RunAgent(ctx); err != nil {
		fmt.Fprintln(os.Stderr, "Update Agent failed:", err)
		os.Exit(1)
	}
}
