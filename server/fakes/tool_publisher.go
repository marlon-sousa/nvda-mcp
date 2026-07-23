// screenreader-mcp fakes -- FakeToolPublisher: the ToolPublisher port double.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test double. MIRRORS domain/ports/tool_publisher.go.
// USED BY: the connection controller's tests.
//
// This one keeps the ADVERTISED SET rather than a call log, and that is the
// point: the requirement is "which tools can the agent see now?", not "which
// calls were made". Asserting on the set means a test still passes when the
// controller reaches the same advertised state by a different route, and still
// fails when a retraction is missed -- which a call log would let slide as long
// as the call happened at all.
package fakes

import (
	"slices"
	"sync"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// FakeToolPublisher tracks what is currently advertised.
type FakeToolPublisher struct {
	mu        sync.Mutex
	published []string
	history   []string
}

var _ ports.ToolPublisher = (*FakeToolPublisher)(nil)

// NewFakeToolPublisher builds a publisher advertising nothing.
func NewFakeToolPublisher() *FakeToolPublisher { return &FakeToolPublisher{} }

// Published is what is advertised right now, in publication order.
func (p *FakeToolPublisher) Published() []string {
	p.mu.Lock()
	defer p.mu.Unlock()
	return append([]string(nil), p.published...)
}

// Has reports whether one tool is advertised.
func (p *FakeToolPublisher) Has(name string) bool {
	return slices.Contains(p.Published(), name)
}

// History is every publish and retract, in order, spelled `+name` / `-name`.
// For the rare assertion that is genuinely about the sequence -- that tools were
// retracted before a reconnect republished them, say.
func (p *FakeToolPublisher) History() []string {
	p.mu.Lock()
	defer p.mu.Unlock()
	return append([]string(nil), p.history...)
}

func (p *FakeToolPublisher) Publish(names []string) {
	p.mu.Lock()
	defer p.mu.Unlock()
	for _, name := range names {
		if !slices.Contains(p.published, name) {
			p.published = append(p.published, name)
		}
		p.history = append(p.history, "+"+name)
	}
}

func (p *FakeToolPublisher) Retract(names []string) {
	p.mu.Lock()
	defer p.mu.Unlock()
	for _, name := range names {
		// Retracting something that is not advertised is deliberately not an
		// error, so the fake must tolerate it exactly as the real adapter
		// does -- teardown runs on several paths.
		p.published = slices.DeleteFunc(p.published, func(published string) bool {
			return published == name
		})
		p.history = append(p.history, "-"+name)
	}
}
