// screenreader-mcp adapters -- endpoint dialing decisions.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: adapter. Turns a domain Endpoint into a Dialer over the right leaf, and
// refuses the endpoints we will not dial.
// BUILT BY: adapters/bridge/handshake.go, once per endpoint it tries.
// USED BY: the leaves it selects -- tcp_transport.go and
// pipe_transport_{windows,other}.go.
//
// The decisions live here rather than in a leaf, which is the whole layering
// rule: WHICH host is acceptable and WHETHER this platform has named pipes are
// judgements, so they are unit-tested here against no OS at all, while the
// leaves below make no judgement and do nothing but call it.
package bridge

import (
	"fmt"
	"net"
	"time"

	adapterports "github.com/marlon-sousa/screen-readers-mcp/server/adapters/ports"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
)

// DefaultConnectTimeout bounds a single dial attempt.
//
// Short on purpose: these are local endpoints, so a bridge that is listening
// answers immediately, and a reader whose first endpoint is dead should fall
// through to its second quickly rather than making the agent wait.
const DefaultConnectTimeout = 2 * time.Second

// DialerFor returns how to reach one endpoint, or explains why we will not.
//
// The error is returned at BUILD time rather than at dial time so that a
// misconfigured endpoint is reported before anything is attempted, and so the
// message can name the endpoint the user actually wrote.
func DialerFor(endpoint entities.Endpoint) (adapterports.Dialer, error) {
	switch endpoint.Kind {
	case entities.TransportPipe:
		return pipeDialer(endpoint.Address)

	case entities.TransportTCP:
		if err := requireLoopback(endpoint.Address); err != nil {
			return nil, err
		}
		address := endpoint.Address
		return func() (adapterports.Transport, error) {
			return dialTCP(address, DefaultConnectTimeout)
		}, nil

	default:
		return nil, fmt.Errorf("endpoint %s: unknown transport %q", endpoint, endpoint.Kind)
	}
}

// requireLoopback refuses anything but the local machine.
//
// The wire contract says the connection is always local-machine-only and never
// a routable interface (protocol.md §1), and remote TCP is deferred on the
// bridge side behind its own security spec. Enforcing it on the dialing side
// too means a config file cannot quietly turn this server into something that
// reaches across a network -- and the failure is a clear message rather than a
// connection that half works.
func requireLoopback(address string) error {
	host, port, err := net.SplitHostPort(address)
	if err != nil {
		return fmt.Errorf("tcp endpoint %q: want <host>:<port>: %w", address, err)
	}
	if port == "" {
		return fmt.Errorf("tcp endpoint %q: no port", address)
	}
	if host == "localhost" {
		return nil
	}
	ip := net.ParseIP(host)
	if ip == nil {
		return fmt.Errorf("tcp endpoint %q: host must be a loopback address or localhost", address)
	}
	if !ip.IsLoopback() {
		return fmt.Errorf("tcp endpoint %q: only loopback endpoints may be dialed", address)
	}
	return nil
}
