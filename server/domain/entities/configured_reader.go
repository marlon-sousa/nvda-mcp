// screenreader-mcp domain -- ConfiguredReader: one reader we know how to reach.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: entity. A reader name plus every endpoint its bridge is known to listen
// on, IN DECLARED ORDER. Immutable value.
// BUILT BY: config/loader.go, layering embedded defaults, --config and
// --reader; never by the pipe scanner. Spec 0013 is explicit that an endpoint
// found in the namespace is not a reader: what may be connected to is what was
// configured, and nothing else.
// READ BY: adapters/bridge/handshake.go (tries the endpoints in order),
// reader_listing.go, and in 10b the connection controller.
//
// The order is the point. Spec 0011's dialog lets a user switch the NVDA bridge
// between pipe and loopback TCP, so a single endpoint would be wrong whenever
// they had; trying them in declared order makes the agent's model "connect to
// nvda" rather than "pick a transport".
package entities

// ConfiguredReader is one reader and its ordered endpoints.
type ConfiguredReader struct {
	Name      string
	Endpoints []Endpoint
}
