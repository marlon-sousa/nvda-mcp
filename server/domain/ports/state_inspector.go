// screenreader-mcp domain -- the StateInspector port (the `state` capability).
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: domain port. The `state` capability group (protocol.md §4).
// IMPLEMENTED BY: adapters/bridge/json_lines_client.go.
// USED BY: 10b's get_state tool controller.
// HANDED OUT BY: the handshake, only when the reader announced `state`.
//
// Why this group exists at all, from the bridge's hard-won gotcha: a reader
// answers some actions with an earcon rather than words (NVDA+space toggling
// browse/focus mode), so a speech assertion has nothing to match. Two state
// snapshots across a gesture assert the toggle instead.
package ports

// ReaderState is queryable reader state. Values are reader-specific strings and
// pass through opaquely.
type ReaderState struct {
	// BrowseMode is a pointer because a reader with no such concept reports
	// null, which is a different answer from "some mode named empty".
	BrowseMode *string

	SpeechMode string
	SleepMode  bool
	InputHelp  bool
}

// StateInspector reads queryable reader state.
type StateInspector interface {
	State() (ReaderState, error)
}
