// screenreader-mcp testsupport -- a builder for a tool call's context.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test scaffolding. The direct analogue of the bridge's
// tests/support/context.py: because a tool controller sees only a ToolContext,
// it is exercised with NO connection controller, NO MCP server and NO bridge --
// a hand-built context and a call.
// USED BY: every tool controller's test.
package testsupport

import (
	"encoding/json"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/controllers/tools"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
	"github.com/marlon-sousa/screen-readers-mcp/server/fakes"
)

// ToolCall is a tool, the context it will be handed, and the fakes behind both.
type ToolCall struct {
	Tool    tools.Tool
	Context tools.ToolContext
	Control *fakes.FakeConnectionControl
	Clock   *fakes.FakeClock
	Log     *fakes.FakeLog
}

// NewToolCall wires one tool up against a fake control and no connection.
//
// The context's Tool name is taken from the tool itself, so a CapabilityError
// names the tool that actually failed rather than whatever the test remembered
// to type.
func NewToolCall(tool tools.Tool) *ToolCall {
	control := fakes.NewFakeConnectionControl()
	clock := fakes.NewFakeClock()
	log := fakes.NewFakeLog()

	return &ToolCall{
		Tool:    tool,
		Control: control,
		Clock:   clock,
		Log:     log,
		Context: tools.ToolContext{
			Tool:    tool.Name(),
			Control: control,
			Clock:   clock,
			Log:     log,
		},
	}
}

// WithConnection makes this the live session, on both the context and the fake
// control -- together, because a tool may read either and a test that set only
// one would be testing a state the real dispatcher never produces.
func (c *ToolCall) WithConnection(connection *ports.ReaderConnection) *ToolCall {
	c.Context.Connection = connection
	c.Control.SetConnection(connection)
	return c
}

// Run executes the tool with the given raw arguments. Pass "" for a call that
// sent no arguments at all, which is what a client does for a no-parameter tool
// -- the case a tool must tolerate rather than treat as a parse error.
func (c *ToolCall) Run(params string) (any, error) {
	var raw json.RawMessage
	if params != "" {
		raw = json.RawMessage(params)
	}
	return c.Tool.Execute(c.Context, raw)
}
