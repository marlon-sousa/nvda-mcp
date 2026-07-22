// screenreader-mcp domain -- the SessionDialer port.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: domain port. Dial one reader's bridge and complete the handshake.
// IMPLEMENTED BY: adapters/bridge/handshake.go.
// USED BY: 10b's connection controller, driven by the connect_reader tool. The
// server NEVER dials on its own -- no auto-connect, no retry loop, no backoff --
// so every call to Dial is one the agent asked for.
//
// SPEC AMENDMENT (rides in 10a, per the workflow rule): spec 0013's deliverable
// 2 describes this port as returning "a ReaderSession value". Delivery needs one
// thing more -- the caller must also be handed the live collaborators to serve
// tool calls with, and something to end the session with -- so Dial returns a
// ReaderConnection: the session description, which endpoint answered, the
// capability ports, and a SessionLifecycle. The capability ports being FIELDS
// that are nil when unannounced is what makes the capability gate structural,
// which was the reason for splitting the ports in the first place.
// SessionLifecycle lives in this file rather than in an eighth port file because
// it is the dialer's own signalling type -- what Dial hands back -- exactly as
// AGENTS.md places a port's DTOs with the port.
package ports

import (
	"fmt"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
)

// SessionOptions are the per-session parameters the wire fixes at `hello` for
// the session's whole lifetime (protocol.md §3, §4).
//
// They are parameters and not CLI flags precisely because of that: under
// auto-connect they would have to be chosen by whoever wrote the MCP host
// config, before anyone knew what the session was for. As connect_reader
// parameters they are chosen per session by the party that knows what it is
// about to do.
type SessionOptions struct {
	// Mode fixes how speech is captured for the session.
	Mode entities.CaptureMode

	// LogLevel optionally raises the READER's own diagnostic verbosity for
	// the session. Nil leaves it unchanged.
	LogLevel *entities.ReaderLogLevel
}

// SessionLifecycle is what a live session can be asked beyond its capabilities:
// the lifecycle and diagnostic commands, which belong to no capability group and
// are always available once the handshake has completed (protocol.md §4).
type SessionLifecycle interface {
	// Ping proves the connection is real right now. It resets the bridge's
	// heartbeat watchdog but deliberately NOT its command-inactivity
	// watchdog, so a keepalive cannot mask an abandoned session -- which is
	// why an idle agent still loses its session, by design.
	Ping() error

	// Bye asks the bridge to end the session cleanly. Sent by
	// disconnect_reader; the bridge restores speech on this path as on every
	// other.
	Bye() error

	// Close drops the connection without asking. Safe to call after Bye, and
	// after a loss, so teardown paths need no bookkeeping to avoid a double
	// close.
	Close() error
}

// ReaderConnection is one live session: what was established, and what may be
// asked of it.
//
// The capability ports are nil exactly when the reader did not announce the
// matching capability. That is deliberate and load-bearing: "this reader has no
// braille" is a collaborator that was never handed over, not a boolean somebody
// must remember to check.
type ReaderConnection struct {
	// Session is what `hello` established, including which reader answered.
	Session entities.ReaderSession

	// Endpoint is the one that actually answered, out of the reader's
	// declared endpoints. Reported back to the agent, because with a bridge
	// that can be toggled between pipe and TCP, "which one answered" is a
	// real answer and not an implementation detail.
	Endpoint entities.Endpoint

	// Lifecycle is always present.
	Lifecycle SessionLifecycle

	// The capability ports. Nil unless announced.
	Speech   SpeechReader
	Braille  BrailleReader
	Gestures GestureSender
	Focus    FocusInspector
	State    StateInspector
	Config   ConfigAccessor
}

// SessionDialer opens a session with one configured reader.
type SessionDialer interface {
	// Dial tries the reader's endpoints IN DECLARED ORDER and completes the
	// handshake with the first that answers.
	//
	// It returns an error rather than retrying: a failed connect leaves the
	// caller Disconnected and tells the agent why, and the agent decides
	// whether to try again.
	Dial(reader entities.ConfiguredReader, opts SessionOptions) (*ReaderConnection, error)
}

// ProtocolMismatchError is a bridge answering with a wire version this server
// does not support.
//
// Its own error type, and owned by this port, because it is the one connection
// failure with a different remedy: not "try again" but "update one of the two
// components". The caller reports it, records the Incompatible state, and keeps
// the process alive -- restarting the add-on and connecting again then fixes it
// without restarting the MCP host.
type ProtocolMismatchError struct {
	// BridgeVersion is what the bridge announced.
	BridgeVersion int

	// ServerVersions is every version this server supports. A set, not a
	// single constant, so that accepting more than one later is a change to
	// data rather than to control flow (spec 0013, "The domain never speaks
	// wire types").
	ServerVersions []int
}

func (e *ProtocolMismatchError) Error() string {
	return fmt.Sprintf(
		"bridge speaks wire protocol version %d; this server supports %v",
		e.BridgeVersion, e.ServerVersions,
	)
}
