// screenreader-mcp domain -- the ToolPublisher port.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: domain port. How the domain changes the set of tools an MCP client is
// offered.
// IMPLEMENTED BY: adapters/mcp/sdk_server.go, which adds and removes them on
// the SDK server (the SDK then emits `tools/list_changed` on its own).
// USED BY: domain/controllers/connection.go -- the only caller, because
// publication is a consequence of the connection lifecycle and of nothing else.
//
// This port is what keeps the MCP SDK out of the domain. The domain's whole
// vocabulary for "the agent can see this tool now" is a list of NAMES: it does
// not know what a tool registration looks like, that a notification is sent, or
// that MCP is the protocol on the other side at all.
//
// It deliberately does not return errors. Publishing cannot fail at the point of
// use -- the adapter validates every tool's schema once, when it is built, so a
// malformed schema is a startup failure with a name attached rather than a
// mid-session surprise the domain would have no useful response to.
package ports

// ToolPublisher owns the advertised tool set.
type ToolPublisher interface {
	// Publish advertises exactly these tools in addition to whatever is
	// already advertised. Called on a successful `hello` with the names the
	// ToolCatalog gate allowed for the announced capabilities.
	Publish(names []string)

	// Retract withdraws these tools. Called on disconnect and on an observed
	// connection loss -- the two paths that end a session -- so the tool list
	// an agent sees is never a promise about a reader that is no longer there.
	//
	// Retracting a name that is not advertised is not an error: teardown runs
	// on several paths and none of them should have to work out first whether
	// another one got there already.
	Retract(names []string)
}
