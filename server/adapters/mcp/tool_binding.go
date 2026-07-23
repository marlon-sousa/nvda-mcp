// screenreader-mcp adapters -- binding a domain Tool to the SDK.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: adapter. Maps a domain Tool onto the go-sdk's tool registration, and a
// tool result onto an MCP call result.
// BUILT BY / USED BY: sdk_server.go, which is the only caller.
// DEPENDS ON: the go-sdk and domain/controllers/tools. Nothing here reaches the
// bridge or the wire.
//
// THIS FILE IS THE WHOLE OF THE PER-TOOL BINDING, and it is generic: there is
// one bind function and no per-tool code anywhere in this package. That is what
// spec 0013's erased-params decision bought, and it is why the registry can be
// the single tool list -- there is no second place a tool has to be mentioned.
//
// It uses the SDK's NON-GENERIC registration path, (*mcp.Server).AddTool, whose
// handler receives raw json.RawMessage arguments and whose Tool.InputSchema
// accepts a hand-written schema verbatim. The top-level generic mcp.AddTool
// would derive a schema from a per-tool Go struct, which a uniform domain Tool
// interface has to erase again -- forcing exactly the per-tool binding code this
// design exists to avoid.
package mcp

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	sdk "github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/controllers/tools"
)

// declare turns a domain Tool into the SDK's description of it.
func declare(tool tools.Tool) *sdk.Tool {
	return &sdk.Tool{
		Name:        tool.Name(),
		Description: tool.Description(),
		InputSchema: tool.InputSchema(),
	}
}

// validateSchema checks a tool's hand-written schema before anything is
// registered.
//
// The SDK PANICS on a schema that is not a JSON object schema, at the moment the
// tool is added -- which for a gated tool is mid-session, on a successful
// handshake, in a goroutine serving an agent. Checking every tool once at
// startup turns that into a startup error naming the tool.
func validateSchema(tool tools.Tool) error {
	var schema map[string]any
	if err := json.Unmarshal(tool.InputSchema(), &schema); err != nil {
		return fmt.Errorf("tool %q: its input schema is not valid JSON: %w", tool.Name(), err)
	}
	if schema["type"] != "object" {
		return fmt.Errorf(`tool %q: its input schema must have "type": "object", got %v`,
			tool.Name(), schema["type"])
	}
	return nil
}

// handlerFor is the one handler every tool is registered with.
//
// It closes over the tool NAME rather than the tool, so that both routes into
// the domain -- an ordinary call and the backstop's retracted-tool path -- go
// through the same dispatcher and produce the same errors.
func handlerFor(dispatch *tools.Dispatcher, name string) sdk.ToolHandler {
	return func(_ context.Context, request *sdk.CallToolRequest) (*sdk.CallToolResult, error) {
		return callResult(dispatch.Execute(name, request.Params.Arguments))
	}
}

// callResult maps a domain answer onto MCP's.
//
// A tool failure becomes a RESULT with IsError set, not a protocol error. That
// is the SDK's own guidance and it matters here more than usual: an agent can
// see the content of an errored result and self-correct within the turn --
// connect first, ask a reader that has braille -- whereas a JSON-RPC error is a
// transport-level fault it can only report.
func callResult(value any, failure error) (*sdk.CallToolResult, error) {
	if failure != nil {
		// A wiring mistake is ours, not the agent's, so it surfaces as a
		// protocol error rather than as advice the agent cannot act on.
		if errors.Is(failure, tools.ErrUnknownTool) {
			return nil, failure
		}
		return &sdk.CallToolResult{
			Content: []sdk.Content{&sdk.TextContent{Text: failure.Error()}},
			IsError: true,
		}, nil
	}

	encoded, err := json.Marshal(value)
	if err != nil {
		return nil, fmt.Errorf("encoding the tool result: %w", err)
	}
	// Both forms, deliberately: StructuredContent for a client that can use
	// it, and the same JSON as text for the many that read content only.
	return &sdk.CallToolResult{
		Content:           []sdk.Content{&sdk.TextContent{Text: string(encoded)}},
		StructuredContent: value,
	}, nil
}
