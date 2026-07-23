// screenreader-mcp domain -- the Registry's tests.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// The registry is the single tool list, so these tests are mostly about that
// claim holding: what it lists is what the gate knows, and every tool it lists
// is complete enough to be bound to the SDK without the adapter checking
// anything.
package tools_test

import (
	"encoding/json"
	"slices"
	"testing"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/controllers/tools"
)

func TestTheUngatedFourAreAlwaysRegistered(t *testing.T) {
	registry := tools.BuildRegistry()

	for _, name := range []string{"list_readers", "connect_reader", "disconnect_reader", "status"} {
		tool, known := registry.Lookup(name)
		if !known {
			t.Errorf("%s is not registered", name)
			continue
		}
		if tool.Capability() != "" {
			t.Errorf("%s is gated on %q; the four discovery tools must be ungated, "+
				"or an agent could not reconnect after a disconnect", name, tool.Capability())
		}
	}
}

// The wire's lifecycle and diagnostic commands are deliberately NOT tools (spec
// 0013): `bye` is what disconnect_reader sends, `ping` is what status' round
// trip is, and `echo` answers a developer's question rather than an agent's.
// Every advertised tool is tokens in every agent request, so this is a real cost.
func TestPingEchoAndByeAreNotTools(t *testing.T) {
	registry := tools.BuildRegistry()

	for _, name := range []string{"ping", "echo", "bye"} {
		if _, known := registry.Lookup(name); known {
			t.Errorf("%q is registered as a tool; spec 0013 says it must not be", name)
		}
	}
}

// The gate is DERIVED from the list, so a tool cannot exist without the catalog
// knowing what gates it.
func TestTheCatalogCoversExactlyTheRegisteredTools(t *testing.T) {
	registry := tools.BuildRegistry()
	catalog := registry.Catalog()

	for _, tool := range registry.All() {
		capability, known := catalog.CapabilityOf(tool.Name())
		if !known {
			t.Errorf("%s is registered but the catalog does not know it", tool.Name())
		}
		if capability != tool.Capability() {
			t.Errorf("%s is gated on %q in the catalog and %q on the tool",
				tool.Name(), capability, tool.Capability())
		}
	}

	registered := make([]string, 0, len(registry.All()))
	for _, tool := range registry.All() {
		registered = append(registered, tool.Name())
	}
	for _, name := range append(catalog.Ungated(), catalog.Gated()...) {
		if !slices.Contains(registered, name) {
			t.Errorf("the catalog knows %q, which is not a registered tool", name)
		}
	}
}

// Every tool must be bindable as it stands: the MCP adapter has zero per-tool
// code, so anything wrong with a tool's own declaration has to fail here rather
// than at the first call.
func TestEveryToolIsCompleteEnoughToBind(t *testing.T) {
	for _, tool := range tools.BuildRegistry().All() {
		t.Run(tool.Name(), func(t *testing.T) {
			if tool.Name() == "" {
				t.Error("has no name")
			}
			if len(tool.Description()) < 40 {
				t.Errorf("description is %d characters; it is the agent-facing "+
					"contract and most of what this tool is for",
					len(tool.Description()))
			}

			var schema map[string]any
			if err := json.Unmarshal(tool.InputSchema(), &schema); err != nil {
				t.Fatalf("input schema is not valid JSON: %v", err)
			}
			// The SDK REJECTS a tool whose input schema is not an object
			// schema, and it does so by panicking at registration -- so this
			// assertion is the difference between a clear test failure and a
			// crash at startup.
			if schema["type"] != "object" {
				t.Errorf(`input schema type = %v, want "object"`, schema["type"])
			}
		})
	}
}

// Names are the registry's keys and the SDK's, so a duplicate would silently
// shadow a tool rather than fail.
func TestToolNamesAreUnique(t *testing.T) {
	seen := map[string]bool{}
	for _, tool := range tools.BuildRegistry().All() {
		if seen[tool.Name()] {
			t.Errorf("%q is registered twice", tool.Name())
		}
		seen[tool.Name()] = true
	}
}

func TestLookupDoesNotInventTools(t *testing.T) {
	if _, known := tools.BuildRegistry().Lookup("nonsense"); known {
		t.Error("Lookup found a tool that does not exist")
	}
}
