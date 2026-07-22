// screenreader-mcp domain -- CaptureMode: how speech is captured for a session.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: entity. The domain's spelling of the wire's capture mode, fixed once at
// `hello` for the whole session (protocol.md §4).
// BUILT BY: the agent, through 10b's connect_reader parameter; carried into the
// handshake as part of ports.SessionOptions.
// READ BY: adapters/bridge/handshake.go (which maps it to the wire enum) and
// reader_session.go (which records the mode the bridge confirmed).
//
// Its own file, and its own type distinct from the generated wire enum, for the
// reason spec 0013 gives: if the domain used the wire's enum, adding wire v2
// would rewrite the domain.
package entities

import "fmt"

// CaptureMode is `silent` or `live`.
type CaptureMode string

const (
	// CaptureSilent captures speech deterministically while the user hears
	// nothing. The bridge restores speech on every teardown path.
	CaptureSilent CaptureMode = "silent"

	// CaptureLive leaves the real synth speaking and captures by observation,
	// so ordering and timing are best-effort.
	CaptureLive CaptureMode = "live"
)

// String is the wire spelling, which is also what an agent passes.
func (m CaptureMode) String() string { return string(m) }

// ParseCaptureMode validates a mode chosen by an agent, so an unknown value
// fails at the tool boundary with a listing of what is valid, rather than
// travelling to the bridge to be rejected there.
func ParseCaptureMode(value string) (CaptureMode, error) {
	switch CaptureMode(value) {
	case CaptureSilent:
		return CaptureSilent, nil
	case CaptureLive:
		return CaptureLive, nil
	default:
		return "", fmt.Errorf("capture mode %q: want %q or %q", value, CaptureSilent, CaptureLive)
	}
}
