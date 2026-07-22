// screenreader-mcp adapters -- the PipeDirectory seam.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: adapter seam -- a port BETWEEN adapters, invisible to the domain.
// IMPLEMENTED BY: adapters/discovery/pipe_directory_windows.go (the real
// namespace) and pipe_directory_other.go (an empty list), plus a fake in tests.
// USED BY: adapters/discovery/pipe_probe.go, which holds every decision about
// what a name in that listing means.
//
// The seam exists so the one interesting rule -- a configured pipe name is
// matched against the listing, and a name in the listing NEVER becomes an
// endpoint -- is unit-tested against a scripted listing, while the file that
// touches the OS has nothing in it to get wrong.
package ports

// PipeDirectory is the raw named-pipe namespace.
type PipeDirectory interface {
	// Names returns the pipe names currently present, without any path
	// prefix. Best effort: an unreadable namespace is an empty list, not an
	// error, because "we could not look" and "nothing is listening" lead to
	// the same honest answer -- liveness unknown or not listening, never a
	// failed tool call.
	Names() []string
}
