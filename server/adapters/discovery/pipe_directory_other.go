//go:build !windows

// screenreader-mcp adapters -- the pipe namespace stub (non-Windows).
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: LEAF adapter stub. Stands in for pipe_directory_windows.go where there
// is no named-pipe namespace to read.
// BUILT BY: wiring/wiring.go, same call site as the real leaf.
//
// An empty listing rather than an error, and the consequence is exactly right:
// PipeProbe finds no candidate live, and every endpoint reports liveness
// unknown. A host with no pipes can still list its readers and still connect
// over loopback TCP.
package discovery

import (
	discoveryports "github.com/marlon-sousa/screen-readers-mcp/server/adapters/discovery/ports"
)

// EmptyPipeDirectory is the namespace on a platform that has none.
type EmptyPipeDirectory struct{}

var _ discoveryports.PipeDirectory = (*EmptyPipeDirectory)(nil)

// NewPipeDirectory builds the platform's directory listing.
func NewPipeDirectory() *EmptyPipeDirectory { return &EmptyPipeDirectory{} }

// Names is always empty here.
func (d *EmptyPipeDirectory) Names() []string { return nil }
