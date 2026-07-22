// screenreader-mcp -- the composition root.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: composition root. The ONLY place that knows both the ports and the
// adapters: it picks the adapters, stacks them, and hands the domain its
// collaborators.
// BUILT BY: cmd/screenreader-mcp/main.go, from the parsed flags.
//
// Read top to bottom, this file IS the answer to "who connects what". That is
// why there is no DI container: annotation-driven auto-wiring hides the graph
// and turns a wiring mistake the compiler would have caught into a runtime
// failure. If this ever gets genuinely hard to follow, it becomes an explicit
// hand-written file of factory functions -- same central place, zero
// dependencies.
//
// In 10a it builds everything up to and including a handshake-capable dialer.
// 10b extends it with the MCP server, the tool registry and the connection
// controller; the returned Server value is where those will hang.
package wiring

import (
	"github.com/marlon-sousa/screen-readers-mcp/server/adapters"
	"github.com/marlon-sousa/screen-readers-mcp/server/adapters/bridge"
	"github.com/marlon-sousa/screen-readers-mcp/server/adapters/discovery"
	"github.com/marlon-sousa/screen-readers-mcp/server/config"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// Options are what the command line decided.
type Options struct {
	// ConfigPath is --config.
	ConfigPath string

	// ReaderFlags are the repeated --reader values.
	ReaderFlags []string

	// Verbose turns on debug logging (to stderr, never stdout).
	Verbose bool
}

// Server is the assembled process: the domain's collaborators, built once and
// owned by the caller.
//
// An ordinary value, deliberately. There is NO package-level mutable state
// anywhere in server/ -- no global "current reader", no singleton, no init()
// side effect -- which is what keeps concurrent sessions reachable later as a
// map plus a routing parameter rather than an unpicking of globals.
type Server struct {
	// Endpoints is the resolved reader set.
	Endpoints ports.EndpointSource

	// Probe answers which configured endpoints are live.
	Probe ports.EndpointProbe

	// Dialer opens a session, and is called only when an agent asks.
	Dialer ports.SessionDialer

	// Clock and Log are handed to everything that needs them.
	Clock ports.Clock
	Log   ports.Log
}

// Build assembles the process.
//
// Note what it does NOT do: it dials nothing. The server starts, serves, and
// waits for the agent to open a session (spec 0013, "Connection is
// agent-initiated"), so building the dialer and using it are separate events.
func Build(opts Options) (*Server, error) {
	log := adapters.NewStderrLog(opts.Verbose)
	clock := adapters.NewSystemClock()

	// Layer 1-3 of the endpoint set: embedded defaults, then --config, then
	// --reader flags. Resolved now, so a bad configuration fails at startup.
	endpoints, err := config.Load(config.Options{
		ConfigPath:  opts.ConfigPath,
		ReaderFlags: opts.ReaderFlags,
	})
	if err != nil {
		return nil, err
	}

	// Liveness: the probe decides what a name in the namespace means; the
	// platform leaf underneath it only reads the namespace (or, off Windows,
	// reports an empty one).
	probe := discovery.NewPipeProbe(discovery.NewPipeDirectory())

	// The dialer: bridge.DialerFor chooses the transport leaf per endpoint,
	// and the handshake drives the ordered attempt and the `hello` exchange.
	dialer := bridge.NewHandshake(bridge.DialerFor, clock, log)

	return &Server{
		Endpoints: endpoints,
		Probe:     probe,
		Dialer:    dialer,
		Clock:     clock,
		Log:       log,
	}, nil
}
