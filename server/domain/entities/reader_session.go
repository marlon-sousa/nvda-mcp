// screenreader-mcp domain -- ReaderSession: what `hello` established.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: entity. The immutable description of the one live session: which reader
// answered, what it can do, and where its two log files are.
// BUILT BY: adapters/bridge/handshake.go, mapping the wire's HelloResult into
// domain vocabulary.
// READ BY: 10b's `status` tool and the `screenreader://info` resource, and by
// the tool controllers that need the reader's identity.
//
// This is where spec 0005's principle 2 lands: the server never asks "is this
// NVDA?", it just hands the agent the reader's name and version and lets the
// agent apply what it already knows about that reader.
package entities

// ReaderIdentity is which screen reader answered. Its own type rather than two
// loose strings, because identity travels together everywhere it goes.
type ReaderIdentity struct {
	Name    string
	Version string
}

// ReaderSession is the established session, as `hello` described it.
type ReaderSession struct {
	// Reader is the identity the bridge announced. The sole authority on
	// which reader answered -- never inferred from the endpoint that was
	// dialed.
	Reader ReaderIdentity

	// Capabilities is what this bridge announced it can serve.
	Capabilities Set

	// Mode is the capture mode now in effect, which the bridge confirmed.
	// Fixed for the session's lifetime.
	Mode CaptureMode

	// Synth is the reader's current speech synthesizer.
	Synth string

	// LogPath is this session's human-readable transcript, written by the
	// bridge.
	LogPath string

	// ReaderLogPath is this session's capture of the READER's own diagnostic
	// log. The wire calls this field `nvdaLogPath`; the domain does not carry
	// a reader's name in a field name.
	ReaderLogPath string

	// ProtocolVersion is the wire version the bridge answered with. Recorded
	// rather than assumed, so a mismatch can be reported naming both sides.
	ProtocolVersion int
}
