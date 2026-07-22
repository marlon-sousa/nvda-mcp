// screenreader-mcp adapters -- StderrLog: the Log leaf.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: LEAF adapter. IMPLEMENTS the Log domain port by writing to stderr, and
// nothing else.
// BUILT BY: wiring/wiring.go.
// USED BY: everything that logs, through the port.
//
// STDERR, NEVER STDOUT. stdout carries MCP JSON-RPC frames and nothing else, so
// a single line written to the wrong stream corrupts the protocol the agent is
// speaking. That is the reason this adapter exists at all rather than the domain
// calling fmt.Println: the destination is decided once, here, where it can be
// seen.
//
// No test file beside it: it makes no decisions beyond the level prefix.
package adapters

import (
	"fmt"
	"io"
	"os"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// StderrLog writes levelled lines to stderr.
type StderrLog struct {
	out     io.Writer
	verbose bool
}

var _ ports.Log = (*StderrLog)(nil)

// NewStderrLog builds the production log. Debug lines are suppressed unless
// verbose, so an ordinary run stays quiet enough to read.
func NewStderrLog(verbose bool) *StderrLog {
	return &StderrLog{out: os.Stderr, verbose: verbose}
}

func (l *StderrLog) Debugf(format string, args ...any) {
	if !l.verbose {
		return
	}
	l.write("debug", format, args...)
}

func (l *StderrLog) Infof(format string, args ...any) { l.write("info", format, args...) }

func (l *StderrLog) Errorf(format string, args ...any) { l.write("error", format, args...) }

func (l *StderrLog) write(level, format string, args ...any) {
	fmt.Fprintf(l.out, "screenreader-mcp %s: %s\n", level, fmt.Sprintf(format, args...))
}
