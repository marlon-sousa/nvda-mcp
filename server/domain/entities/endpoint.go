// screenreader-mcp domain -- Endpoint: one place a bridge may listen.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: entity. An immutable value, plus the parsing of the `pipe:<name>` /
// `tcp:<host>:<port>` spelling used in defaults.json, --config and --reader.
// BUILT BY: config/loader.go (from the layered sources), via wiring.
// READ BY: adapters/bridge/endpoint.go (which turns one into a Dialer),
// adapters/discovery/pipe_probe.go (liveness), reader_listing.go.
//
// Parsing lives here and not in the adapter because it is pure syntax, and the
// same string spelling appears in three places (embedded defaults, config file,
// flag) that must agree. What the adapter keeps is the part that needs to know
// about the OS: whether a host is acceptable to dial, and whether this platform
// has named pipes at all.
package entities

import (
	"fmt"
	"strings"
)

// TransportKind is how a bridge is reached.
type TransportKind string

const (
	// TransportPipe is a Windows named pipe, addressed by its bare name
	// (`nvdaMcpBridge`), never the `\\.\pipe\` prefix -- the prefix is an OS
	// spelling and belongs in the leaf.
	TransportPipe TransportKind = "pipe"

	// TransportTCP is a loopback socket, addressed as `host:port`.
	TransportTCP TransportKind = "tcp"
)

// Endpoint is one place a bridge is known to listen. Immutable value.
type Endpoint struct {
	Kind    TransportKind
	Address string
}

// ParseEndpoint reads the `<kind>:<address>` spelling.
//
// Cut rather than Split on purpose: a TCP address contains its own colon, so
// only the FIRST one separates the kind from the address.
func ParseEndpoint(spec string) (Endpoint, error) {
	kind, address, found := strings.Cut(spec, ":")
	if !found || address == "" {
		return Endpoint{}, fmt.Errorf("endpoint %q: want pipe:<name> or tcp:<host>:<port>", spec)
	}
	switch TransportKind(kind) {
	case TransportPipe:
		return Endpoint{Kind: TransportPipe, Address: address}, nil
	case TransportTCP:
		if !strings.Contains(address, ":") {
			return Endpoint{}, fmt.Errorf("endpoint %q: tcp needs <host>:<port>", spec)
		}
		return Endpoint{Kind: TransportTCP, Address: address}, nil
	default:
		return Endpoint{}, fmt.Errorf("endpoint %q: unknown transport %q", spec, kind)
	}
}

// String is the round-trip of ParseEndpoint, so what an agent is shown is
// exactly what may be written back into a --reader flag.
func (e Endpoint) String() string { return string(e.Kind) + ":" + e.Address }
