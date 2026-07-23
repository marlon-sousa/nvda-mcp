// screenreader-mcp adapters -- the capability backstop.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: adapter. Receiving middleware on `tools/call` that answers a call for a
// tool this server HAS but has not currently published.
// BUILT BY: sdk_server.go's Bind. DEPENDS ON: the ToolCatalog (is this name one
// of ours?) and the Dispatcher (the one route into the domain).
//
// WHY IT EXISTS (spec 0013's 10b delivery amendment 5). The tool list an agent
// holds is a snapshot, and the gate retracts tools when a session ends -- so a
// call for a retracted tool is an ordinary race, not a client bug. Left to the
// SDK, that call is answered `unknown tool "get_braille"`, which is true of the
// registration table and useless to the agent: it says nothing about whether the
// tool ever existed, whether the reader lacks the capability, or whether the
// session simply ended. Acceptance criterion 10 asks for a STRUCTURED capability
// error, and this is what makes the answer the same whether the tool was
// retracted a moment ago or the capability was never announced.
//
// It changes nothing else: a genuinely unknown name still gets the SDK's own
// error, and `tools/list` is untouched -- what is advertised remains exactly what
// the gate allowed.
package mcp

import (
	"context"

	sdk "github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/controllers/tools"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
)

// capabilityBackstop answers calls for known-but-unpublished tools.
//
// Note what it does NOT do: it does not decide what the error says. It runs the
// call through the same dispatcher an advertised tool would go through, and the
// tool's own ToolContext accessor produces the error -- so there is exactly one
// place in the server where "this reader cannot do that" is worded, and the
// answer cannot drift between the two routes.
func capabilityBackstop(catalog entities.ToolCatalog, dispatch *tools.Dispatcher) sdk.Middleware {
	return func(next sdk.MethodHandler) sdk.MethodHandler {
		return func(ctx context.Context, method string, request sdk.Request) (sdk.Result, error) {
			call, isCall := request.(*sdk.CallToolRequest)
			if method != "tools/call" || !isCall {
				return next(ctx, method, request)
			}

			// Published tools take the ordinary path. Only a name the
			// catalog knows AND the SDK does not currently have registered
			// reaches the dispatcher from here.
			if _, ours := catalog.CapabilityOf(call.Params.Name); !ours {
				return next(ctx, method, request)
			}
			if isRegistered(ctx, next, call) {
				return next(ctx, method, request)
			}

			return callResult(dispatch.Execute(call.Params.Name, call.Params.Arguments))
		}
	}
}

// isRegistered asks the SDK whether it currently advertises this tool, by
// listing.
//
// Asking rather than keeping a parallel set of published names: a second record
// of what is advertised is a second thing to keep correct, and this middleware
// exists precisely because the two could disagree. `tools/list` is a map lookup
// over a handful of entries, so the cost is nothing next to the round trip that
// is about to happen anyway.
func isRegistered(ctx context.Context, next sdk.MethodHandler, call *sdk.CallToolRequest) bool {
	listing, err := next(ctx, "tools/list", &sdk.ListToolsRequest{
		Session: call.Session,
		Params:  &sdk.ListToolsParams{},
	})
	if err != nil {
		// If the list cannot be had, assume the tool is there and let the
		// ordinary path answer: a diagnostic aid must never be the reason a
		// working call fails.
		return true
	}
	result, ok := listing.(*sdk.ListToolsResult)
	if !ok {
		return true
	}
	for _, tool := range result.Tools {
		if tool.Name == call.Params.Name {
			return true
		}
	}
	return false
}
