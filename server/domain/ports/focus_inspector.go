// screenreader-mcp domain -- the FocusInspector port (the `focus` capability).
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: domain port. The `focus` capability group (protocol.md §4).
// IMPLEMENTED BY: adapters/bridge/json_lines_client.go.
// USED BY: 10b's get_focus_info tool controller.
// HANDED OUT BY: the handshake, only when the reader announced `focus`.
package ports

// FocusInfo describes the reader's focus object.
//
// Role and states are reader-specific strings that pass through opaquely: NVDA
// says one thing and JAWS another, and the agent -- which knows the reader from
// `screenreader://info` -- is the party that interprets them.
type FocusInfo struct {
	Name   string
	Role   string
	States []string

	// Value and AppModule are pointers because the wire distinguishes "this
	// object has no value" (null) from "its value is the empty string", and
	// collapsing the two would lose a real answer.
	Value     *string
	AppModule *string
}

// FocusInspector reads the current focus.
type FocusInspector interface {
	FocusInfo() (FocusInfo, error)
}
