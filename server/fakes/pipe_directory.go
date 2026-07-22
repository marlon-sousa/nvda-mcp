// screenreader-mcp fakes -- FakePipeDirectory: the PipeDirectory seam double.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test double. MIRRORS adapters/discovery/ports/pipe_directory.go.
// USED BY: adapters/discovery tests.
//
// A scripted namespace is what lets the interesting rule be tested on any
// platform: that a listed pipe nobody configured is never reported, and never
// becomes something an agent can connect to.
package fakes

import discoveryports "github.com/marlon-sousa/screen-readers-mcp/server/adapters/discovery/ports"

// FakePipeDirectory returns a fixed listing.
type FakePipeDirectory struct {
	names []string
}

var _ discoveryports.PipeDirectory = (*FakePipeDirectory)(nil)

// NewFakePipeDirectory builds a directory listing exactly these names.
func NewFakePipeDirectory(names ...string) *FakePipeDirectory {
	return &FakePipeDirectory{names: names}
}

func (d *FakePipeDirectory) Names() []string {
	return append([]string(nil), d.names...)
}
