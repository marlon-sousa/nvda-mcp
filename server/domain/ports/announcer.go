// screenreader-mcp domain -- the Announcer port (the `announce` capability).
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: domain port. The `announce` capability group (protocol.md §4).
// IMPLEMENTED BY: adapters/bridge/json_lines_client.go.
// USED BY: the announce tool controller.
// HANDED OUT BY: the handshake, only when the reader announced `announce`.
//
// This is the only port that reaches a HUMAN rather than the reader's state.
// Everything else here observes or drives a screen reader; this speaks to the
// person sitting in front of it, through the reader's real synthesizer and
// underneath whatever suppression the capture mode has in place. A reader whose
// bridge has no way to do that simply never announces the capability, and the
// tool is never advertised -- the same structural gate as braille, for the same
// reason.
package ports

// Announcer is everything the `announce` capability can be asked.
//
// No DTO: the wire's result is an acknowledgement, so there is nothing to
// surface beyond "it did not fail". A reader cannot report whether a human
// actually listened, and pretending otherwise would be a return value that
// invites a check nobody can honour.
type Announcer interface {
	// Announce speaks text to the human operating the reader.
	Announce(text string) error
}
