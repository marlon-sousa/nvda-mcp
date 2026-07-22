// screenreader-mcp domain -- Capability and Set: the capability vocabulary.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: entity. The pure vocabulary of "what can this reader do", built from
// what `hello` announced.
// BUILT BY: adapters/bridge/handshake.go, from the wire's capability strings.
// READ BY: adapters/bridge/handshake.go (which capability ports to hand out)
// and, in 10b, domain/entities/tool_catalog.go (the tool gate).
//
// This is domain vocabulary, not wire vocabulary: adapters/wire has its own
// generated capability constants and the handshake maps between them, which is
// what keeps the domain free of the binding (spec 0013, "the domain never
// speaks wire types").
package entities

import "sort"

// Capability names one command group a reader may support.
//
// A reader difference is a capability, never a protocol version: JAWS having no
// braille is this type's business, not the handshake's.
type Capability string

// The groups the wire contract defines (protocol.md §4). A bridge may announce
// strings beyond these -- the NVDA bridge announces `announce` as well -- and a
// consumer must ignore what it does not know, so Set retains unknown members
// rather than dropping or rejecting them.
const (
	CapabilitySpeech   Capability = "speech"
	CapabilityBraille  Capability = "braille"
	CapabilityGestures Capability = "gestures"
	CapabilityFocus    Capability = "focus"
	CapabilityState    Capability = "state"
	CapabilityConfig   Capability = "config"
)

// Set is an immutable set of announced capabilities.
//
// A zero Set is a valid empty set -- a reader that announced nothing supports
// nothing, which Has reports correctly without a nil check at every call site.
type Set struct {
	members map[Capability]struct{}
}

// NewSet builds the set a bridge announced. Duplicates collapse; unknown
// strings are kept, so All() reports the reader honestly even where this
// server has no tool for a member.
func NewSet(announced []string) Set {
	members := make(map[Capability]struct{}, len(announced))
	for _, name := range announced {
		members[Capability(name)] = struct{}{}
	}
	return Set{members: members}
}

// Has reports whether the reader announced c.
func (s Set) Has(c Capability) bool {
	_, ok := s.members[c]
	return ok
}

// All returns every announced capability, sorted, including ones this server
// has no tool for. Sorted because it reaches an agent and a diff, and both
// deserve a stable order.
func (s Set) All() []Capability {
	all := make([]Capability, 0, len(s.members))
	for c := range s.members {
		all = append(all, c)
	}
	sort.Slice(all, func(i, j int) bool { return all[i] < all[j] })
	return all
}

// Strings is All as plain strings, for the places that report the set outward.
func (s Set) Strings() []string {
	all := s.All()
	out := make([]string, len(all))
	for i, c := range all {
		out[i] = string(c)
	}
	return out
}
