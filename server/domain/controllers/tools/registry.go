// screenreader-mcp domain -- Registry: the explicit tool list.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: the hand-written tool list, read top to bottom. Same reasoning as the
// bridge's command registry and as wiring.go: no decorator auto-registration, no
// container, no init() that appends to a package variable. What the server
// offers is answerable by reading one function.
// BUILT BY: wiring/wiring.go.
// USED BY: dispatcher.go (which tool), adapters/mcp/sdk_server.go (what to bind
// and publish), and Catalog() (the gate).
//
// THE REGISTRY IS THE SINGLE TOOL LIST. That is what the erased-params decision
// bought: because the MCP adapter has no per-tool code, there is no second place
// a tool has to be mentioned, and therefore no second place to forget. The gate
// is derived from this list rather than written beside it, for the same reason.
package tools

import "github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"

// Registry holds the tools, in publication order.
type Registry struct {
	tools  []Tool
	byName map[string]Tool
}

// BuildRegistry is the list. Adding a tool means adding a line here and a file
// beside this one -- nothing else, anywhere.
//
// The four ungated tools come first because they are the ones a fresh server
// advertises: discovery and connection have to exist before a reader does.
func BuildRegistry() *Registry {
	return NewRegistry(
		// Ungated: always advertised, before and after a session exists.
		&ListReaders{},
		&ConnectReader{},
		&DisconnectReader{},
		&Status{},

		// Gated on `speech`.
		&GetSpeech{},
		&GetLastSpeech{},
		&GetNextSpeechIndex{},
		&WaitForSpeech{},
		&WaitForSpeechToFinish{},

		// Gated on `braille`.
		&GetBraille{},

		// Gated on `gestures`.
		&PressGesture{},

		// Gated on `focus`.
		&GetFocusInfo{},

		// Gated on `state`.
		&GetState{},

		// Gated on `config`.
		&GetConfig{},
		&SetConfig{},
	)
}

// NewRegistry indexes an explicit list.
//
// BuildRegistry above is the PRODUCTION list and the only one wiring ever calls;
// this constructor exists so a test can compose a smaller one, which is what
// keeps a dispatcher test from having to reach for whichever real tool happens
// to exercise the path it is about.
func NewRegistry(list ...Tool) *Registry {
	byName := make(map[string]Tool, len(list))
	for _, tool := range list {
		byName[tool.Name()] = tool
	}
	return &Registry{tools: list, byName: byName}
}

// All is every tool, in registration order.
func (r *Registry) All() []Tool { return append([]Tool(nil), r.tools...) }

// Lookup finds a tool by name.
func (r *Registry) Lookup(name string) (Tool, bool) {
	tool, known := r.byName[name]
	return tool, known
}

// Catalog derives the capability gate from the list.
//
// Derived rather than declared, so that a tool cannot exist without the gate
// knowing what gates it: the failure this prevents is a new capability-gated
// tool that is advertised to every reader because somebody added the file and
// the registry line but not a catalog entry.
func (r *Registry) Catalog() entities.ToolCatalog {
	gates := make([]entities.ToolGate, 0, len(r.tools))
	for _, tool := range r.tools {
		gates = append(gates, entities.ToolGate{Name: tool.Name(), Capability: tool.Capability()})
	}
	return entities.NewToolCatalog(gates)
}
