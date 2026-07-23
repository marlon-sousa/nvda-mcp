// screenreader-mcp domain -- the disconnect_reader tool.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: controller, one per tool. UNGATED -- it survives the disconnect it
// performs, along with the other three.
// USES: ConnectionControl.Disconnect, via ToolContext.
// LISTED BY: registry.go.
//
// This is the only path that sends `bye`, which is why `bye` is not a tool of
// its own (spec 0013): a second route to the same effect would let an agent end
// a session without this server updating its own state, leaving the gated tools
// advertised for a reader that has already been told the session is over.
package tools

import (
	"encoding/json"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
)

// DisconnectReader ends the one session.
type DisconnectReader struct{}

var _ Tool = (*DisconnectReader)(nil)

func (t *DisconnectReader) Name() string { return "disconnect_reader" }

func (t *DisconnectReader) Capability() entities.Capability { return "" }

func (t *DisconnectReader) Description() string {
	return "End the current screen reader session and withdraw the capability-gated " +
		"tools. The reader restores anything it changed for the session -- speech " +
		"and its own log level. Takes no parameters, and is not an error when no " +
		"session is live. Reconnect with connect_reader; the new session starts " +
		"fresh, with new logs and speech indices starting over."
}

func (t *DisconnectReader) InputSchema() json.RawMessage {
	return json.RawMessage(`{"type":"object","properties":{},"additionalProperties":false}`)
}

// disconnectResult tells the agent what the call actually did, since "there was
// nothing to disconnect" is a different fact from "a live session was ended"
// even though neither is a failure.
type disconnectResult struct {
	Disconnected bool   `json:"disconnected"`
	Reader       string `json:"reader,omitempty"`
}

func (t *DisconnectReader) Execute(ctx ToolContext, _ json.RawMessage) (any, error) {
	// Read before disconnecting: afterwards there is nothing left to name.
	reader := ""
	if ctx.Connection != nil {
		reader = ctx.Connection.Session.Reader.Name
	}

	if err := ctx.Control.Disconnect(); err != nil {
		return nil, err
	}
	return disconnectResult{Disconnected: reader != "", Reader: reader}, nil
}
