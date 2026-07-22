//go:build windows

// screenreader-mcp adapters -- the pipe namespace leaf (Windows).
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: LEAF adapter. IMPLEMENTS the PipeDirectory seam by reading the Windows
// named-pipe namespace, and does nothing else.
// BUILT BY: wiring/wiring.go, handed to PipeProbe.
//
// Reading `\\.\pipe\` as a directory is what makes liveness knowable without
// dialing, which matters because the bridge serves one session at a time. There
// is no test file: what a name in the listing MEANS is decided one layer up, in
// pipe_probe.go, which is tested against a scripted listing.
package discovery

import (
	"os"

	discoveryports "github.com/marlon-sousa/screen-readers-mcp/server/adapters/discovery/ports"
)

// pipeNamespace is the directory the named-pipe namespace is exposed as.
const pipeNamespace = `\\.\pipe\`

// WindowsPipeDirectory lists the named pipes present on this machine.
type WindowsPipeDirectory struct{}

var _ discoveryports.PipeDirectory = (*WindowsPipeDirectory)(nil)

// NewPipeDirectory builds the platform's directory listing.
func NewPipeDirectory() *WindowsPipeDirectory { return &WindowsPipeDirectory{} }

// Names lists the namespace, or nothing if it cannot be read.
func (d *WindowsPipeDirectory) Names() []string {
	entries, err := os.ReadDir(pipeNamespace)
	if err != nil {
		return nil
	}
	names := make([]string, 0, len(entries))
	for _, entry := range entries {
		names = append(names, entry.Name())
	}
	return names
}
