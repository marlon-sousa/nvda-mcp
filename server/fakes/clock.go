// screenreader-mcp fakes -- FakeClock: the Clock port double.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test double. MIRRORS domain/ports/clock.go, one fake per port, one file
// each (AGENTS.md).
// USED BY: tests only. Never linked into the shipped binary's call graph --
// wiring builds adapters/system_clock.go instead.
//
// Hand-written and stateful, not a mock framework: the compile-time assertion
// below is what gomock's generated doubles exist to provide, and the domain
// drives its collaborators through real protocols (deadline arithmetic, wait
// loops), so a double that returns scripted values per call would exercise
// less, not more.
package fakes

import (
	"sync"
	"time"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// FakeClock is a clock that only moves when a test tells it to. Sleep is an
// instant advance, so a 30-second timeout runs in microseconds.
//
// Safe for concurrent use: the bridge client's reader loop and its caller both
// read the clock.
type FakeClock struct {
	mu      sync.Mutex
	now     time.Time
	slept   []time.Duration
	onSleep func(d time.Duration)
}

var _ ports.Clock = (*FakeClock)(nil)

// NewFakeClock starts at a fixed, arbitrary instant -- only differences matter.
func NewFakeClock() *FakeClock {
	return &FakeClock{now: time.Date(2026, time.July, 22, 12, 0, 0, 0, time.UTC)}
}

// Now returns the fake's current instant.
func (c *FakeClock) Now() time.Time {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.now
}

// Sleep advances the fake clock instead of blocking, and records the duration
// so a test can assert on a backoff or poll cadence when the cadence *is* the
// requirement.
func (c *FakeClock) Sleep(d time.Duration) {
	c.mu.Lock()
	c.now = c.now.Add(d)
	c.slept = append(c.slept, d)
	hook := c.onSleep
	c.mu.Unlock()
	if hook != nil {
		hook(d)
	}
}

// Advance moves the clock forward without recording a sleep, for tests that
// simulate time passing outside the code under test.
func (c *FakeClock) Advance(d time.Duration) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.now = c.now.Add(d)
}

// Slept is every duration passed to Sleep, in order.
func (c *FakeClock) Slept() []time.Duration {
	c.mu.Lock()
	defer c.mu.Unlock()
	return append([]time.Duration(nil), c.slept...)
}

// OnSleep registers a hook run after each Sleep advances the clock -- the seam
// a test uses to make something happen "while" the code under test waits (a
// frame arriving, a peer closing).
func (c *FakeClock) OnSleep(hook func(d time.Duration)) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.onSleep = hook
}
