// screenreader-mcp fakes -- FakeAnnouncer: the Announcer port double.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test double. MIRRORS domain/ports/announcer.go.
// USED BY: the announce tool controller tests.
//
// This one records, for the same reason FakeGestureSender does: the call has no
// return value worth asserting on, so "what was announced, in order" IS the
// requirement. A spy inside a hand-written fake, not a mock framework.
package fakes

import (
	"sync"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// FakeAnnouncer records what it was asked to say.
type FakeAnnouncer struct {
	mu        sync.Mutex
	announced []string
	err       error
}

var _ ports.Announcer = (*FakeAnnouncer)(nil)

// NewFakeAnnouncer builds an announcer that accepts everything.
func NewFakeAnnouncer() *FakeAnnouncer { return &FakeAnnouncer{} }

// FailWith makes every announcement return err, as a bridge whose synth had
// gone would.
func (f *FakeAnnouncer) FailWith(err error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.err = err
}

// Announced is everything said, in order.
func (f *FakeAnnouncer) Announced() []string {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]string(nil), f.announced...)
}

func (f *FakeAnnouncer) Announce(text string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.err != nil {
		return f.err
	}
	f.announced = append(f.announced, text)
	return nil
}
