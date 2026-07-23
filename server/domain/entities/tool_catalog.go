// screenreader-mcp domain -- ToolCatalog: the capability gate.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: entity. A pure decision table -- a capability set goes in, tool names
// come out. This IS the gate spec 0013 describes; there is no second place where
// a tool's visibility is decided.
// BUILT BY: domain/controllers/tools/registry.go, from the one hand-written tool
// list. (SPEC AMENDMENT, rides in 10b: the layout summary's "Built by" column
// says connection.go. Deriving the gate from the registry instead is what keeps
// the two from drifting -- the registry is the single tool list, so a tool that
// exists is a tool the catalog knows about, by construction rather than by
// somebody remembering.)
// READ BY: domain/controllers/connection.go (which names to publish and retract)
// and adapters/mcp's backstop (what a retracted name was gated on).
//
// NO READER NAME APPEARS HERE, only capability strings. That is spec 0005's
// first chassis principle rendered as a type: "JAWS has no braille" is not
// something this file could express even if somebody wanted it to.
package entities

import "sort"

// ToolGate is one tool's entry: its name and what gates it.
type ToolGate struct {
	// Name is the tool's MCP name.
	Name string

	// Capability is the group a reader must announce for this tool to be
	// advertised. EMPTY means ungated -- the four discovery and connection
	// tools, which must be there before any reader is, since they are how a
	// reader gets connected in the first place.
	Capability Capability
}

// ToolCatalog is the whole table. Immutable once built.
type ToolCatalog struct {
	gates []ToolGate
	by    map[string]ToolGate
}

// NewToolCatalog builds the table. The order given is preserved, because it is
// the order the tool list is published in and a stable order is worth having
// wherever an agent or a diff reads the result.
func NewToolCatalog(gates []ToolGate) ToolCatalog {
	by := make(map[string]ToolGate, len(gates))
	for _, gate := range gates {
		by[gate.Name] = gate
	}
	return ToolCatalog{gates: append([]ToolGate(nil), gates...), by: by}
}

// Ungated is every tool that is advertised regardless of what is connected.
//
// These are published once, at startup, and never retracted: a server with no
// session must still be able to say what readers it knows and to open one.
func (c ToolCatalog) Ungated() []string {
	var names []string
	for _, gate := range c.gates {
		if gate.Capability == "" {
			names = append(names, gate.Name)
		}
	}
	return names
}

// Allowed is every GATED tool the announced capabilities permit.
//
// Ungated tools are deliberately absent from the answer: they are not the
// connection's to publish or retract, and including them would make a disconnect
// withdraw the very tools an agent needs to reconnect with.
func (c ToolCatalog) Allowed(announced Set) []string {
	var names []string
	for _, gate := range c.gates {
		if gate.Capability != "" && announced.Has(gate.Capability) {
			names = append(names, gate.Name)
		}
	}
	return names
}

// Gated is every gated tool this server has, whatever any reader announced.
//
// What it is for: retracting on a path where the announced set is no longer
// trustworthy, and answering the backstop's question "is this name one of ours?"
func (c ToolCatalog) Gated() []string {
	var names []string
	for _, gate := range c.gates {
		if gate.Capability != "" {
			names = append(names, gate.Name)
		}
	}
	return names
}

// CapabilityOf reports what gates a tool, and whether the catalog knows the name
// at all. Read by the MCP adapter's backstop, which must tell "a tool of ours
// that is currently retracted" from "a name that was never a tool".
func (c ToolCatalog) CapabilityOf(name string) (Capability, bool) {
	gate, known := c.by[name]
	return gate.Capability, known
}

// Capabilities is every capability the catalog gates something on, sorted. It
// answers "which capabilities does this server actually have tools for?", which
// is a different question from what a reader announced -- protocol.md §4 lets a
// bridge announce groups we have no tool for, and a reader deserves to be
// described honestly either way.
func (c ToolCatalog) Capabilities() []Capability {
	seen := map[Capability]struct{}{}
	var all []Capability
	for _, gate := range c.gates {
		if gate.Capability == "" {
			continue
		}
		if _, ok := seen[gate.Capability]; ok {
			continue
		}
		seen[gate.Capability] = struct{}{}
		all = append(all, gate.Capability)
	}
	sort.Slice(all, func(i, j int) bool { return all[i] < all[j] })
	return all
}
