// screenreader-mcp fakes -- FakeSessionDialer: the SessionDialer port double.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test double. MIRRORS domain/ports/session_dialer.go.
// USED BY: 10b's connection controller tests.
//
// It records every Dial, which is the assertion behind the rule that matters
// most in this whole server: NO connection attempt is ever made that the agent
// did not ask for. A dialer that counts is how "the server never dials on its
// own" stops being a claim and becomes a test.
package fakes

import (
	"sync"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// DialRequest is one recorded call.
type DialRequest struct {
	Reader  entities.ConfiguredReader
	Options ports.SessionOptions
}

// FakeSessionDialer hands back a scripted connection, or a scripted failure.
type FakeSessionDialer struct {
	mu         sync.Mutex
	connection *ports.ReaderConnection
	err        error
	calls      []DialRequest
}

var _ ports.SessionDialer = (*FakeSessionDialer)(nil)

// NewFakeSessionDialer builds a dialer that fails until told otherwise, so a
// test cannot connect by accident.
func NewFakeSessionDialer() *FakeSessionDialer { return &FakeSessionDialer{} }

// Returns makes the next dials succeed with this connection.
func (f *FakeSessionDialer) Returns(connection *ports.ReaderConnection) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.connection = connection
	f.err = nil
}

// FailWith makes the next dials fail with err -- including, deliberately, a
// *ports.ProtocolMismatchError, which the caller must treat differently.
func (f *FakeSessionDialer) FailWith(err error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.connection = nil
	f.err = err
}

// Calls is every dial that was attempted, in order.
func (f *FakeSessionDialer) Calls() []DialRequest {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]DialRequest(nil), f.calls...)
}

func (f *FakeSessionDialer) Dial(reader entities.ConfiguredReader, opts ports.SessionOptions) (*ports.ReaderConnection, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls = append(f.calls, DialRequest{Reader: reader, Options: opts})
	if f.err != nil {
		return nil, f.err
	}
	if f.connection == nil {
		return nil, errNothingScripted
	}
	return f.connection, nil
}
