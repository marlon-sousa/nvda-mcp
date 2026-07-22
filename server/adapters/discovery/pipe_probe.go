// screenreader-mcp adapters -- PipeProbe: the EndpointProbe.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: adapter. IMPLEMENTS the domain's EndpointProbe port: of the endpoints it
// is handed, which have a bridge listening.
// DEPENDS ON: the PipeDirectory seam (adapters/discovery/ports), never the OS
// directly.
// BUILT BY: wiring/wiring.go.
// USED BY: 10b's connection controller, for list_readers.
//
// The decision this file holds is small and important: it walks the CANDIDATES
// and asks the listing about each, never the other way round. A pipe that is
// listening but belongs to no configured reader is therefore invisible here and
// cannot be connected to -- spec 0013's determinism rule, and the reason the
// method takes candidates instead of returning discoveries.
//
// It never dials. The bridge accepts one session at a time, so a probe that
// connected would occupy the slot the agent is about to ask for.
package discovery

import (
	"strings"

	discoveryports "github.com/marlon-sousa/screen-readers-mcp/server/adapters/discovery/ports"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// PipeProbe answers liveness for pipe endpoints by reading the namespace.
type PipeProbe struct {
	directory discoveryports.PipeDirectory
}

var _ ports.EndpointProbe = (*PipeProbe)(nil)

// NewPipeProbe builds the probe over a directory listing.
func NewPipeProbe(directory discoveryports.PipeDirectory) *PipeProbe {
	return &PipeProbe{directory: directory}
}

// Live returns the candidates that have a bridge listening.
//
// Only pipe endpoints can appear: a TCP endpoint cannot be tested without
// connecting, so it is simply absent and the caller reports it as unknown. The
// listing is read ONCE per call, so every candidate is judged against the same
// snapshot rather than against a namespace that may change between two of them.
func (p *PipeProbe) Live(candidates []entities.Endpoint) []entities.Endpoint {
	present := map[string]struct{}{}
	for _, name := range p.directory.Names() {
		// Windows pipe names are case-insensitive, so the comparison is
		// too -- otherwise a user who wrote `NvdaMcpBridge` in a config file
		// would be told nothing is listening while their bridge is running.
		present[strings.ToLower(name)] = struct{}{}
	}

	var live []entities.Endpoint
	for _, candidate := range candidates {
		if candidate.Kind != entities.TransportPipe {
			continue
		}
		if _, ok := present[strings.ToLower(candidate.Address)]; ok {
			live = append(live, candidate)
		}
	}
	return live
}
