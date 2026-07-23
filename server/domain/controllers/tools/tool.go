// screenreader-mcp domain -- the Tool interface and CapabilityError.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: the interface every tool controller implements, plus its own signalling
// type. An interface, like a port -- so no test file beside it (AGENTS.md).
// IMPLEMENTED BY: one file per tool in this directory, mirroring the bridge's
// one-handler-per-command decomposition.
// LISTED BY: registry.go. RUN BY: dispatcher.go. BOUND BY: adapters/mcp.
//
// PARAMS ARE ERASED AND EACH TOOL DECLARES ITS OWN SCHEMA (spec 0013,
// deliverable 16). Not typed input structs with SDK-generated schemas: a uniform
// domain Tool interface has to erase those types anyway, which would force a
// line of per-tool binding code into the MCP adapter and leave the tool list
// existing in two places, free to drift. With erased params the adapter has ZERO
// per-tool code, the registry is the single list, and the gate is a filter over
// it. The price is hand-written schemas -- which are agent-facing text we would
// be hand-tuning regardless, and which are most of what a tool file actually
// says.
package tools

import (
	"encoding/json"
	"fmt"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
)

// Tool is one MCP tool, as the domain understands it: a name, the agent-facing
// contract, and a use case to run.
//
// Implementations are STATELESS singletons. Every scrap of per-call state
// arrives in the ToolContext -- the direct analogue of the bridge's
// SessionContext, and the reason a tool can be tested with no server, no SDK and
// no connection.
type Tool interface {
	// Name is the MCP tool name, and the key the registry and catalog use.
	Name() string

	// Capability is the group a reader must announce for this tool to be
	// advertised. EMPTY means ungated.
	Capability() entities.Capability

	// Description is what the agent reads to decide whether to call this.
	// Along with InputSchema it is the tool's real content: this server's
	// usability mostly lives in these two strings.
	Description() string

	// InputSchema is a hand-written JSON Schema object, always of
	// `"type": "object"`. Passed to the SDK verbatim.
	InputSchema() json.RawMessage

	// Execute runs the use case and returns the value to be marshalled as the
	// call's result, or an error to fail the call with.
	//
	// params is the raw arguments the client sent, unvalidated and possibly
	// empty -- a client calling a no-parameter tool sends no arguments at all,
	// so a tool must tolerate nil rather than assume `{}`.
	Execute(ctx ToolContext, params json.RawMessage) (any, error)
}

// CapabilityError is a tool being asked for something the live reader cannot do
// -- or being asked at all when no reader is connected.
//
// Its own type, and structured, because it is acceptance criterion 10's second
// clause: the tool list is a snapshot, so a call can always arrive for a
// capability that has since gone, and the agent needs to be told which of the
// two situations it is in. "Connect first" and "this reader does not do that"
// have completely different remedies.
type CapabilityError struct {
	// Tool is the tool that was called.
	Tool string

	// Capability is what it needed. Empty when the tool is ungated and the
	// problem is simply that nothing is connected.
	Capability entities.Capability

	// Reader is the name of the reader currently connected, or empty when
	// none is -- which is what distinguishes the two messages below.
	Reader string
}

func (e *CapabilityError) Error() string {
	if e.Reader == "" {
		return fmt.Sprintf(
			"%s needs a connected reader, and none is: call connect_reader first",
			e.Tool)
	}
	return fmt.Sprintf(
		"%s needs the %q capability, which the connected reader %q did not announce",
		e.Tool, e.Capability, e.Reader)
}
