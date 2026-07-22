// screenreader-mcp testsupport -- builders for configured readers.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test scaffolding, NOT a port double -- doubles live in fakes/ and this
// package is deliberately everything else, so fakes/ stays exactly the port
// doubles and nothing more (AGENTS.md).
// USED BY: any test that needs a reader or an endpoint spelled the way a user
// would spell it.
package testsupport

import (
	"testing"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
)

// Endpoint parses one `pipe:name` / `tcp:host:port` spec, failing the test if it
// is malformed.
//
// Tests write the SPEC STRING rather than an Endpoint literal on purpose: it is
// the spelling that appears in defaults.json, --config and --reader, so a test
// exercises the same parsing a user's configuration goes through.
func Endpoint(t testing.TB, spec string) entities.Endpoint {
	t.Helper()
	endpoint, err := entities.ParseEndpoint(spec)
	if err != nil {
		t.Fatalf("endpoint %q: %v", spec, err)
	}
	return endpoint
}

// Reader builds a configured reader from endpoint specs, in the order given --
// which is the order connect_reader will try them in.
func Reader(t testing.TB, name string, specs ...string) entities.ConfiguredReader {
	t.Helper()
	endpoints := make([]entities.Endpoint, 0, len(specs))
	for _, spec := range specs {
		endpoints = append(endpoints, Endpoint(t, spec))
	}
	return entities.ConfiguredReader{Name: name, Endpoints: endpoints}
}
