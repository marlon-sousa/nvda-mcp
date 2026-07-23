// screenreader-mcp domain -- ToolContext and ConnectionControl.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: parameter object (ToolContext) plus the narrow interface it exposes the
// connection lifecycle through (ConnectionControl). NOT an adapter -- it does no
// IO; it is the per-call bundle a tool is handed, exactly as the bridge's
// SessionContext is.
// BUILT BY: dispatcher.go, freshly per call.
// USED BY: every tool in this directory.
//
// ConnectionControl is declared HERE, in the consumer, rather than exported from
// the connection controller: the four ungated tools need precisely these six
// operations and nothing else, and declaring the interface where it is used is
// what stops "the tools can reach the controller" from becoming "the tools can
// reach anything the controller can". It is the same instinct as the bridge's
// SessionContext exposing exactly one lifecycle capability, `close(reason)`.
package tools

import (
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// ConnectionControl is the connection lifecycle, as the four ungated tools need
// it. Satisfied by domain/controllers/connection.go.
type ConnectionControl interface {
	// List joins the configured readers with what the probe could learn
	// about their endpoints, without dialing anything.
	List() entities.ReaderListing

	// Connect tries the named reader's endpoints in declared order and
	// completes the handshake, publishing the gated tools on success.
	// Errors -- it never retries and never falls back to a different reader.
	Connect(readerName string, opts ports.SessionOptions) (*ports.ReaderConnection, error)

	// Disconnect sends `bye` and retracts the gated tools.
	Disconnect() error

	// Status is the recorded state and why it holds.
	Status() entities.ConnectionStatus

	// Current is the live connection, or nil when there is none.
	Current() *ports.ReaderConnection

	// Verify makes a real `ping` round trip, and RECORDS a loss it finds --
	// retracting the tools and updating the state. That is what lets `status`
	// answer with what the wire says rather than with what this process
	// remembers. Nil error means the connection is real right now; nil is
	// also the answer when there is no session to verify.
	Verify() error
}

// ToolContext is everything one tool call may touch.
//
// The capability ports are reached through the accessor METHODS below rather
// than as fields. That is deliverable 16's "every tool still checks and returns
// a structured error", rendered so that forgetting is not expressible: a gated
// tool has no other way to obtain its collaborator, so the check happens on
// every path by construction.
type ToolContext struct {
	// Tool is the name of the tool being run, so an error can say which one.
	Tool string

	// Control is the connection lifecycle, for the four ungated tools.
	Control ConnectionControl

	// Connection is the live session, or nil when none. Read directly by the
	// tools that report ON a session (status) rather than act through one.
	Connection *ports.ReaderConnection

	// Clock and Log are the ambient collaborators.
	Clock ports.Clock
	Log   ports.Log
}

// Session is the live ReaderSession, or a CapabilityError when nothing is
// connected. For tools that need the reader's identity rather than a capability.
func (c ToolContext) Session() (entities.ReaderSession, error) {
	if c.Connection == nil {
		return entities.ReaderSession{}, c.missing("")
	}
	return c.Connection.Session, nil
}

// Speech is the `speech` capability, or a structured error.
func (c ToolContext) Speech() (ports.SpeechReader, error) {
	if c.Connection == nil || c.Connection.Speech == nil {
		return nil, c.missing(entities.CapabilitySpeech)
	}
	return c.Connection.Speech, nil
}

// Braille is the `braille` capability, or a structured error.
func (c ToolContext) Braille() (ports.BrailleReader, error) {
	if c.Connection == nil || c.Connection.Braille == nil {
		return nil, c.missing(entities.CapabilityBraille)
	}
	return c.Connection.Braille, nil
}

// Gestures is the `gestures` capability, or a structured error.
func (c ToolContext) Gestures() (ports.GestureSender, error) {
	if c.Connection == nil || c.Connection.Gestures == nil {
		return nil, c.missing(entities.CapabilityGestures)
	}
	return c.Connection.Gestures, nil
}

// Focus is the `focus` capability, or a structured error.
func (c ToolContext) Focus() (ports.FocusInspector, error) {
	if c.Connection == nil || c.Connection.Focus == nil {
		return nil, c.missing(entities.CapabilityFocus)
	}
	return c.Connection.Focus, nil
}

// State is the `state` capability, or a structured error.
func (c ToolContext) State() (ports.StateInspector, error) {
	if c.Connection == nil || c.Connection.State == nil {
		return nil, c.missing(entities.CapabilityState)
	}
	return c.Connection.State, nil
}

// Config is the `config` capability, or a structured error.
func (c ToolContext) Config() (ports.ConfigAccessor, error) {
	if c.Connection == nil || c.Connection.Config == nil {
		return nil, c.missing(entities.CapabilityConfig)
	}
	return c.Connection.Config, nil
}

// missing builds the error, naming the connected reader when there is one --
// which is what tells "nothing is connected" apart from "this reader cannot do
// that", two situations with entirely different remedies.
func (c ToolContext) missing(capability entities.Capability) *CapabilityError {
	failure := &CapabilityError{Tool: c.Tool, Capability: capability}
	if c.Connection != nil {
		failure.Reader = c.Connection.Session.Reader.Name
	}
	return failure
}
