// Kynetic AI — Go CLI Entry Point
//
// This binary replaces the legacy Python Click-based CLI.
// It provides a single, zero-dependency static executable (~8 MB)
// with sub-2ms startup time and full feature parity.
//
// Usage:
//
//	kynetic [command] [flags]
//
// Build:
//
//	go build -ldflags="-w -s" -o kynetic ./main.go
package main

import "github.com/kynetic-ai/kynetic-cli/cmd"

func main() {
	cmd.Execute()
}
