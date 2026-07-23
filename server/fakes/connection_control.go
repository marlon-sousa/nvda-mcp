// screenreader-mcp fakes -- FakeConnectionControl: the ConnectionControl double.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test double. MIRRORS the ConnectionControl interface declared in
// domain/controllers/tools/tool_context.go -- an interface declared by its
// consumer rather than a port in domain/ports/, but a collaborator the domain
// depends on all the same, so its double belongs here with the others.
// USED BY: the four ungated tool controllers' tests, which exercise a tool with
// no real controller, no dialer and no connection.
//
// It records connects and disconnects, which is legitimate here for the same
// reason FakeSessionDialer records dials: "no connection attempt is ever made
// that the agent did not ask for" is a requirement ABOUT the interaction.
package fakes

import (
	"errors"
	"sync"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/controllers/tools"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// ConnectRequest is one recorded Connect.
type ConnectRequest struct {
	Reader  string
	Options ports.SessionOptions
}

// FakeConnectionControl is a scripted connection lifecycle.
type FakeConnectionControl struct {
	mu sync.Mutex

	listing    entities.ReaderListing
	status     entities.ConnectionStatus
	connection *ports.ReaderConnection
	connectErr error
	disconnErr error
	verifyErr  error

	connects    []ConnectRequest
	disconnects int
	verifies    int
}

var _ tools.ConnectionControl = (*FakeConnectionControl)(nil)

// NewFakeConnectionControl builds a control that is disconnected and knows no
// readers, so a test states everything it relies on.
func NewFakeConnectionControl() *FakeConnectionControl {
	return &FakeConnectionControl{
		status: entities.ConnectionStatus{State: entities.Disconnected},
	}
}

// SetListing is what List will answer.
func (f *FakeConnectionControl) SetListing(listing entities.ReaderListing) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.listing = listing
}

// SetStatus is what Status will answer.
func (f *FakeConnectionControl) SetStatus(status entities.ConnectionStatus) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.status = status
}

// SetConnection makes this the live connection, as a successful connect would.
func (f *FakeConnectionControl) SetConnection(connection *ports.ReaderConnection) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.connection = connection
	f.connectErr = nil
}

// FailConnectWith makes Connect report err and leaves nothing connected.
func (f *FakeConnectionControl) FailConnectWith(err error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.connectErr = err
}

// FailDisconnectWith makes Disconnect report err.
func (f *FakeConnectionControl) FailDisconnectWith(err error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.disconnErr = err
}

// FailVerifyWith makes Verify report err -- the round trip finding a dead
// connection, which is what `status` must surface rather than swallow.
func (f *FakeConnectionControl) FailVerifyWith(err error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.verifyErr = err
}

// Connects, Disconnects and Verifies are the recorded interactions.
func (f *FakeConnectionControl) Connects() []ConnectRequest {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]ConnectRequest(nil), f.connects...)
}

func (f *FakeConnectionControl) Disconnects() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.disconnects
}

func (f *FakeConnectionControl) Verifies() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.verifies
}

func (f *FakeConnectionControl) List() entities.ReaderListing {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.listing
}

func (f *FakeConnectionControl) Connect(readerName string, opts ports.SessionOptions) (*ports.ReaderConnection, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.connects = append(f.connects, ConnectRequest{Reader: readerName, Options: opts})
	if f.connectErr != nil {
		return nil, f.connectErr
	}
	if f.connection == nil {
		return nil, errNothingScripted
	}
	f.status = entities.ConnectionStatus{State: entities.Connected}
	return f.connection, nil
}

func (f *FakeConnectionControl) Disconnect() error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.disconnects++
	if f.disconnErr != nil {
		return f.disconnErr
	}
	f.connection = nil
	f.status = entities.ConnectionStatus{State: entities.Disconnected}
	return nil
}

func (f *FakeConnectionControl) Status() entities.ConnectionStatus {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.status
}

func (f *FakeConnectionControl) Current() *ports.ReaderConnection {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.connection
}

// Verify mirrors the real controller's contract where it matters: a LOST
// connection is recorded -- the session goes and the state says why -- while any
// other failure leaves the session standing, because a bridge that answered with
// a refusal is still there (protocol.md §3). A fake that dropped the session on
// every error would let a tool get away with treating a refusal as a death.
func (f *FakeConnectionControl) Verify() error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.verifies++
	if f.verifyErr == nil {
		return nil
	}
	if errors.Is(f.verifyErr, ports.ErrConnectionLost) {
		f.connection = nil
		f.status = entities.ConnectionStatus{State: entities.Disconnected, Reason: f.verifyErr.Error()}
	}
	return f.verifyErr
}
