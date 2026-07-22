// screenreader-mcp fakes -- FakeSessionLifecycle: the SessionLifecycle double.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test double. MIRRORS the SessionLifecycle interface declared in
// domain/ports/session_dialer.go.
// USED BY: 10b's connection controller tests.
//
// This fake counts, and that is one of the few places where counting is right:
// "the heartbeat sent ping on schedule" and "disconnect_reader sent bye" are
// requirements ABOUT the interaction, so recording it is the assertion rather
// than a substitute for one.
package fakes

import (
	"sync"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// FakeSessionLifecycle records the lifecycle calls it received.
type FakeSessionLifecycle struct {
	mu      sync.Mutex
	pings   int
	byes    int
	closes  int
	pingErr error
	byeErr  error
}

var _ ports.SessionLifecycle = (*FakeSessionLifecycle)(nil)

// NewFakeSessionLifecycle builds a lifecycle that succeeds at everything.
func NewFakeSessionLifecycle() *FakeSessionLifecycle { return &FakeSessionLifecycle{} }

// FailPingWith makes Ping report err -- the connection dying under a heartbeat.
func (f *FakeSessionLifecycle) FailPingWith(err error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.pingErr = err
}

// FailByeWith makes Bye report err.
func (f *FakeSessionLifecycle) FailByeWith(err error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.byeErr = err
}

// Pings, Byes and Closes are the call counts.
func (f *FakeSessionLifecycle) Pings() int  { return f.count(&f.pings) }
func (f *FakeSessionLifecycle) Byes() int   { return f.count(&f.byes) }
func (f *FakeSessionLifecycle) Closes() int { return f.count(&f.closes) }

func (f *FakeSessionLifecycle) Ping() error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.pings++
	return f.pingErr
}

func (f *FakeSessionLifecycle) Bye() error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.byes++
	return f.byeErr
}

func (f *FakeSessionLifecycle) Close() error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.closes++
	return nil
}

func (f *FakeSessionLifecycle) count(field *int) int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return *field
}
