// screenreader-mcp domain -- ReaderLogLevel: the reader's own log verbosity.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: entity. The optional per-session bump of the READER's diagnostic log
// level (protocol.md §3) -- not this server's logging, which never crosses the
// wire.
// BUILT BY: the agent, through 10b's connect_reader `log_level` parameter.
// READ BY: adapters/bridge/handshake.go, which sends it in `hello`.
//
// The values are the reader's, and the bridge restores the previous level at
// teardown on every path, so this is a temporary, real change to the reader's
// own logging rather than a filter private to the capture file.
package entities

import (
	"fmt"
	"strings"
)

// ReaderLogLevel is one of the reader's valid logging levels.
type ReaderLogLevel string

const (
	ReaderLogDebug        ReaderLogLevel = "debug"
	ReaderLogIO           ReaderLogLevel = "io"
	ReaderLogDebugWarning ReaderLogLevel = "debugwarning"
	ReaderLogInfo         ReaderLogLevel = "info"
)

// String is the wire spelling.
func (l ReaderLogLevel) String() string { return string(l) }

// ParseReaderLogLevel validates a level chosen by an agent. The error lists the
// valid values, so a wrong guess self-corrects in the same turn.
func ParseReaderLogLevel(value string) (ReaderLogLevel, error) {
	switch ReaderLogLevel(value) {
	case ReaderLogDebug, ReaderLogIO, ReaderLogDebugWarning, ReaderLogInfo:
		return ReaderLogLevel(value), nil
	default:
		valid := []string{
			string(ReaderLogDebug), string(ReaderLogIO),
			string(ReaderLogDebugWarning), string(ReaderLogInfo),
		}
		return "", fmt.Errorf("log level %q: want one of %s", value, strings.Join(valid, ", "))
	}
}
