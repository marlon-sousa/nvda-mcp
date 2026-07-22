// screenreader-mcp domain -- ConnectionState: the session lifecycle states.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: entity. The state machine the one connection moves through, plus the
// reason string that goes with it.
// BUILT BY: 10b's domain/controllers/connection.go, which owns the transitions.
// READ BY: the `status` tool.
//
// There is deliberately NO Retrying state: the agent owns the connection, the
// server never dials on its own and never retries behind the agent's back
// (spec 0013, "Connection is agent-initiated -- no auto-connect, no backoff").
// A state that cannot be reached is a state nobody has to reason about.
package entities

// ConnectionState is where the one connection currently stands.
type ConnectionState string

const (
	// Disconnected is the starting state and the state after a clean
	// disconnect, an observed loss, or a failed connect.
	Disconnected ConnectionState = "disconnected"

	// Connecting is the window inside connect_reader: dialing the endpoints
	// in order and handshaking.
	Connecting ConnectionState = "connecting"

	// Connected means a `hello` succeeded and the gated tools are published.
	Connected ConnectionState = "connected"

	// Incompatible means a bridge answered but announced a protocol version
	// this server does not support. Distinct from Disconnected because the
	// remedy is different -- update one of the two components, not retry --
	// and because the process deliberately stays up so `status` can keep
	// saying so.
	Incompatible ConnectionState = "incompatible"
)

// String is the wire-visible spelling reported by `status`.
func (s ConnectionState) String() string { return string(s) }

// ConnectionStatus is a state together with why it holds. The reason is empty
// for the uneventful states and populated for the ones an agent must act on.
type ConnectionStatus struct {
	State  ConnectionState
	Reason string
}
