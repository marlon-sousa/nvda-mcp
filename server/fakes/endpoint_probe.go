// screenreader-mcp fakes -- FakeEndpointProbe: the EndpointProbe double.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test double. MIRRORS domain/ports/endpoint_probe.go.
// USED BY: 10b's connection controller tests.
//
// It intersects what a test declared live with the candidates it is handed,
// rather than returning the declared set outright. That keeps the fake honest
// about the port's contract -- the probe answers about CANDIDATES, and can never
// hand back an endpoint nobody asked about.
package fakes

import (
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// FakeEndpointProbe reports a fixed set of endpoints as live.
type FakeEndpointProbe struct {
	live map[entities.Endpoint]struct{}
}

var _ ports.EndpointProbe = (*FakeEndpointProbe)(nil)

// NewFakeEndpointProbe declares which endpoints have a bridge listening.
func NewFakeEndpointProbe(live ...entities.Endpoint) *FakeEndpointProbe {
	set := make(map[entities.Endpoint]struct{}, len(live))
	for _, endpoint := range live {
		set[endpoint] = struct{}{}
	}
	return &FakeEndpointProbe{live: set}
}

func (f *FakeEndpointProbe) Live(candidates []entities.Endpoint) []entities.Endpoint {
	var live []entities.Endpoint
	for _, candidate := range candidates {
		if _, ok := f.live[candidate]; ok {
			live = append(live, candidate)
		}
	}
	return live
}
