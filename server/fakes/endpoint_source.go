// screenreader-mcp fakes -- FakeEndpointSource: the EndpointSource double.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test double. MIRRORS domain/ports/endpoint_source.go.
// USED BY: 10b's connection controller tests.
package fakes

import (
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// FakeEndpointSource returns a fixed reader set.
type FakeEndpointSource struct {
	readers []entities.ConfiguredReader
}

var _ ports.EndpointSource = (*FakeEndpointSource)(nil)

// NewFakeEndpointSource builds a source over these readers, in this order --
// the order is load-bearing, so a test states it explicitly.
func NewFakeEndpointSource(readers ...entities.ConfiguredReader) *FakeEndpointSource {
	return &FakeEndpointSource{readers: readers}
}

func (f *FakeEndpointSource) Readers() []entities.ConfiguredReader {
	return append([]entities.ConfiguredReader(nil), f.readers...)
}
