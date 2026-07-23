// screenreader-mcp domain -- Dispatcher: one tool call, as a use case.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: controller. Builds the per-call ToolContext, runs the named tool, and
// applies the one rule every call shares.
// DEPENDS ON: the Registry (which tool), ConnectionControl (the live session and
// the lifecycle), and the Clock and Log ports.
// BUILT BY: wiring/wiring.go. USED BY: adapters/mcp -- both for an ordinary
// tools/call and for the backstop's retracted-tool path, so there is exactly one
// route from an MCP request to a tool.
//
// SPEC AMENDMENT (rides in 10b): this file is not in the reviewed layout. It
// exists because two things have to happen around every call and neither belongs
// where it would otherwise land. Building the context is per-call assembly the
// MCP adapter should not be doing; noticing that a call died of a LOST
// CONNECTION, and telling the controller so, is a domain decision that would
// otherwise sit in the adapter or be repeated in fifteen tools.
package tools

import (
	"encoding/json"
	"errors"
	"fmt"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// Dispatcher runs tool calls.
//
// Stateless between calls: the context is built fresh each time from the
// controller's current connection, so a tool can never be handed a session that
// ended between the client's tools/list and this call.
type Dispatcher struct {
	registry *Registry
	control  ConnectionControl
	clock    ports.Clock
	log      ports.Log
}

// NewDispatcher builds the dispatcher.
func NewDispatcher(registry *Registry, control ConnectionControl, clock ports.Clock, log ports.Log) *Dispatcher {
	return &Dispatcher{registry: registry, control: control, clock: clock, log: log}
}

// ErrUnknownTool is a call for a name no tool in the registry has. It should be
// unreachable through the MCP adapter, which only ever dispatches names it took
// from the registry -- so if it is ever returned, the wiring is wrong rather
// than the agent.
var ErrUnknownTool = errors.New("no such tool")

// Execute runs one call.
//
// The loss check afterwards is the rule this controller exists for: a tool call
// is usually how a dead connection is discovered first (the agent acts long
// before the next heartbeat), and until somebody tells the connection controller,
// the gated tools stay advertised for a reader that is gone. Guarded on the
// sentinel, so an ordinary refusal by a healthy bridge -- which protocol.md §3
// says the session survives -- costs nothing and tears nothing down.
func (d *Dispatcher) Execute(name string, params json.RawMessage) (any, error) {
	tool, known := d.registry.Lookup(name)
	if !known {
		return nil, fmt.Errorf("%w: %q", ErrUnknownTool, name)
	}

	result, err := tool.Execute(d.context(name), params)
	if err != nil && errors.Is(err, ports.ErrConnectionLost) {
		d.log.Infof("tool %q found the connection gone; re-checking it", name)
		// Verify pings, fails the same way, and RECORDS the loss: the tools
		// retract and the state says why. Its own error is not this call's
		// answer -- the caller asked about the tool, not about the ping.
		_ = d.control.Verify()
	}
	return result, err
}

// context is the per-call bundle.
func (d *Dispatcher) context(name string) ToolContext {
	return ToolContext{
		Tool:       name,
		Control:    d.control,
		Connection: d.control.Current(),
		Clock:      d.clock,
		Log:        d.log,
	}
}
