// screenreader-mcp domain -- the GestureSender port (the `gestures` capability).
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: domain port. The `gestures` capability group (protocol.md §4).
// IMPLEMENTED BY: adapters/bridge/json_lines_client.go.
// USED BY: 10b's press_gesture tool controller.
// HANDED OUT BY: the handshake, only when the reader announced `gestures`.
package ports

// GestureSender presses reader gestures.
type GestureSender interface {
	// PressGestures presses the given gesture ids in order, blocking until
	// each has been processed.
	//
	// The ids are OPAQUE (spec 0005 principle 3): `kb:NVDA+f7` means
	// something to NVDA and to the agent, and nothing to this server, which
	// routes the string without interpreting it. That is what keeps the
	// chassis reader-agnostic -- a JAWS gesture vocabulary needs no code
	// change here.
	PressGestures(ids []string) error
}
