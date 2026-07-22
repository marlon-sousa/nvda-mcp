// screenreader-mcp domain -- the EndpointProbe port.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: domain port. Liveness of endpoints we already know about.
// IMPLEMENTED BY: adapters/discovery/pipe_probe.go.
// USED BY: 10b's connection controller, which joins the answer with the
// configured readers via entities.BuildListing.
//
// Note the direction, which is the whole point: this port is handed the
// endpoints to ask about and answers which of THOSE are live. It is not a
// discovery mechanism and cannot return an endpoint nobody configured. Spec
// 0013 is explicit about why -- inferring a reader from a name found in the
// pipe namespace would make the server's reader set depend on whatever happens
// to be running, on a string any same-user process can choose, and would build
// exactly the zero-configuration path that the planned shared-secret model has
// to take away again.
package ports

import "github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"

// EndpointProbe answers what can be known about an endpoint without dialing it.
//
// Without dialing, deliberately: the bridge serves one session at a time, so a
// probing connection would occupy the slot the agent is about to want.
type EndpointProbe interface {
	// Live returns the subset of candidates that have a bridge listening.
	//
	// An endpoint absent from the answer is either not listening or not
	// knowable -- the caller distinguishes them by kind, since only pipes can
	// be answered for.
	Live(candidates []entities.Endpoint) []entities.Endpoint
}
