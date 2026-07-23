// screenreader-mcp adapters -- Server: the go-sdk stdio server.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: adapter. IMPLEMENTS domain/ports/tool_publisher.go by adding and
// removing tools on the SDK server, which then emits `tools/list_changed` on its
// own. Also the process's MCP endpoint: it serves stdio in production and an
// in-memory transport in the headless tests.
// DEPENDS ON: the go-sdk, the tool registry, the dispatcher, and a SessionSource
// for the info resource.
// BUILT BY: wiring/wiring.go. USED BY: domain/controllers/connection.go, through
// the ToolPublisher port -- which is all the domain knows of any of this.
//
// WIRING ORDER, and why Bind is separate from New: the connection controller
// needs a publisher, the dispatcher needs the controller, and this server needs
// the dispatcher. Rather than break that ring with a setter nobody can see, the
// server is CONSTRUCTED with the registry alone (which is enough to validate
// every schema and to know every name), and BOUND once the dispatcher exists.
//
// STDOUT DISCIPLINE: stdout carries MCP frames and nothing else. The SDK's own
// logger defaults to discarding, and this file hands it nothing else; every word
// this adapter says goes through the Log port to stderr.
package mcp

import (
	"context"
	"errors"
	"io"
	"sync"

	sdk "github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/controllers/tools"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
	"github.com/marlon-sousa/screen-readers-mcp/server/version"
)

// Server is the MCP endpoint and the tool publisher.
type Server struct {
	sdk      *sdk.Server
	registry *tools.Registry
	log      ports.Log

	mu    sync.Mutex
	bound *tools.Dispatcher
}

var _ ports.ToolPublisher = (*Server)(nil)

// NewServer builds the SDK server and validates every tool's schema.
//
// Nothing is registered yet: the ungated tools go on at Bind, and the gated ones
// only when a reader announces their capability.
func NewServer(registry *tools.Registry, log ports.Log) (*Server, error) {
	for _, tool := range registry.All() {
		if err := validateSchema(tool); err != nil {
			return nil, err
		}
	}

	return &Server{
		sdk: sdk.NewServer(&sdk.Implementation{
			Name:    "screenreader-mcp",
			Version: version.Version,
		}, nil),
		registry: registry,
		log:      log,
	}, nil
}

// Bind registers the ungated tools, the capability backstop and the info
// resource, and makes the server ready to serve.
//
// Only the UNGATED tools are registered here. That is acceptance criterion 3: a
// freshly started server advertises exactly the four discovery and connection
// tools, and has dialed nothing.
func (s *Server) Bind(dispatch *tools.Dispatcher, sessions SessionSource) {
	s.mu.Lock()
	s.bound = dispatch
	s.mu.Unlock()

	catalog := s.registry.Catalog()
	for _, name := range catalog.Ungated() {
		s.add(name, dispatch)
	}

	s.sdk.AddReceivingMiddleware(capabilityBackstop(catalog, dispatch))
	s.addInfoResource(sessions)
}

// Publish advertises the named tools. Called by the connection controller on a
// successful handshake, with the names the gate allowed.
func (s *Server) Publish(names []string) {
	dispatch := s.dispatcher()
	if dispatch == nil {
		// Unreachable in practice -- publication only happens because of a
		// tool call, and there are no tool calls before Bind -- so this is
		// the loud version of a wiring mistake rather than a tolerated state.
		s.log.Errorf("tools were published before the MCP server was bound; this is a wiring fault")
		return
	}
	for _, name := range names {
		s.add(name, dispatch)
	}
	s.log.Debugf("published %d tool(s): %v", len(names), names)
}

// Retract withdraws them. Removing a tool that is not registered is not an
// error, which is what lets every teardown path call this without first working
// out whether another one got there already.
func (s *Server) Retract(names []string) {
	s.sdk.RemoveTools(names...)
	s.log.Debugf("retracted %d tool(s): %v", len(names), names)
}

// Run serves MCP over stdio until the host closes it.
//
// Only stdin EOF ends the process (spec 0013): a bridge problem never does, so a
// reader that died is something the agent is told about and can reconnect to,
// not something that takes the MCP host's server down with it.
//
// EOF IS SUCCESS. The SDK reports the host closing stdin as an error, because in
// general a session ending is one; here it is the single expected end of life,
// and reporting it as a failure would leave every ordinary shutdown looking like
// a crash in the host's log.
func (s *Server) Run(ctx context.Context) error {
	err := s.sdk.Run(ctx, &sdk.StdioTransport{})
	if err == nil || errors.Is(err, io.EOF) {
		return nil
	}
	return err
}

// Connect serves one client over an already-made transport.
//
// The seam the headless integration tier drives: a real MCP client and this real
// server, in one process, over the SDK's in-memory transports -- no stdio, no
// sockets, and what the tests assert on is what an MCP client SEES.
func (s *Server) Connect(ctx context.Context, transport sdk.Transport) (*sdk.ServerSession, error) {
	return s.sdk.Connect(ctx, transport, nil)
}

// add registers one tool by name.
func (s *Server) add(name string, dispatch *tools.Dispatcher) {
	tool, known := s.registry.Lookup(name)
	if !known {
		// Only reachable if the catalog and the registry disagreed, which
		// Registry.Catalog makes impossible by deriving one from the other.
		s.log.Errorf("cannot register unknown tool %q", name)
		return
	}
	s.sdk.AddTool(declare(tool), handlerFor(dispatch, name))
}

func (s *Server) dispatcher() *tools.Dispatcher {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.bound
}
