// screenreader-mcp fakes -- FakeStateInspector: the StateInspector port double.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test double. MIRRORS domain/ports/state_inspector.go.
// USED BY: 10b's get_state tool controller tests.
//
// SetState is what makes the real use case testable: the reason this capability
// exists is that some reader actions answer with an earcon rather than words, so
// a test diffs two state snapshots across a gesture. The fake supports exactly
// that by letting the state change between reads.
package fakes

import (
	"sync"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// FakeStateInspector reports whatever state a test put there.
type FakeStateInspector struct {
	mu    sync.Mutex
	state ports.ReaderState
	err   error
}

var _ ports.StateInspector = (*FakeStateInspector)(nil)

// NewFakeStateInspector builds an inspector reporting a zero state.
func NewFakeStateInspector() *FakeStateInspector { return &FakeStateInspector{} }

// SetState is what the next read will report.
func (f *FakeStateInspector) SetState(state ports.ReaderState) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.state = state
}

// FailWith makes every read return err.
func (f *FakeStateInspector) FailWith(err error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.err = err
}

func (f *FakeStateInspector) State() (ports.ReaderState, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.err != nil {
		return ports.ReaderState{}, f.err
	}
	return f.state, nil
}
