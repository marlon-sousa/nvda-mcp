// screenreader-mcp fakes -- FakeTransport: the Transport seam double.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test double. MIRRORS adapters/ports/transport.go -- the seam, not a
// domain port, so this is what lets the JSON-lines client's decisions be tested
// with no socket and no pipe.
// USED BY: adapters/bridge tests.
//
// Scriptable in the three ways the contract can behave: bytes arrive, the peer
// vanishes (EOF), or the transport fails outright. Anything NOT scripted is an
// idle read, reported as the seam's os.ErrDeadlineExceeded -- which is also what
// lets a timeout test run: each idle read advances the injected fake clock by
// one PollInterval, exactly as a real leaf would have spent that long blocking.
package fakes

import (
	"io"
	"os"
	"sync"

	adapterports "github.com/marlon-sousa/screen-readers-mcp/server/adapters/ports"
)

// step is one scripted event on the read side.
type step struct {
	data []byte
	err  error
}

// FakeTransport is a scriptable byte pipe.
type FakeTransport struct {
	mu      sync.Mutex
	clock   *FakeClock
	steps   []step
	written []byte
	closed  bool
	onWrite func(request []byte)
}

var _ adapterports.Transport = (*FakeTransport)(nil)

// NewFakeTransport builds a transport whose idle reads advance clock. A nil
// clock is allowed for tests that never wait.
func NewFakeTransport(clock *FakeClock) *FakeTransport {
	return &FakeTransport{clock: clock}
}

// QueueRead schedules bytes to be delivered. They need not align with frame
// boundaries -- splitting a frame across two queued chunks is exactly how the
// reassembly is tested.
func (t *FakeTransport) QueueRead(data []byte) {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.steps = append(t.steps, step{data: data})
}

// QueueLine schedules one complete JSON-lines frame.
func (t *FakeTransport) QueueLine(line string) {
	t.QueueRead([]byte(line + "\n"))
}

// QueueEOF schedules the peer closing cleanly.
func (t *FakeTransport) QueueEOF() {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.steps = append(t.steps, step{err: io.EOF})
}

// QueueError schedules a transport failure -- a reset, a broken pipe.
func (t *FakeTransport) QueueError(err error) {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.steps = append(t.steps, step{err: err})
}

// OnWrite registers a responder run after each complete write, with the bytes
// just written.
//
// This is how a test scripts a conversation rather than a monologue: the
// responder inspects the request and queues the matching reply, so ids and
// ordering are exercised instead of assumed.
func (t *FakeTransport) OnWrite(respond func(request []byte)) {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.onWrite = respond
}

func (t *FakeTransport) Read(p []byte) (int, error) {
	t.mu.Lock()
	if len(t.steps) == 0 {
		clock := t.clock
		t.mu.Unlock()
		if clock != nil {
			clock.Advance(adapterports.PollInterval)
		}
		return 0, os.ErrDeadlineExceeded
	}
	next := t.steps[0]
	if next.err != nil {
		t.steps = t.steps[1:]
		t.mu.Unlock()
		return 0, next.err
	}
	n := copy(p, next.data)
	if n == len(next.data) {
		t.steps = t.steps[1:]
	} else {
		t.steps[0].data = next.data[n:]
	}
	t.mu.Unlock()
	return n, nil
}

func (t *FakeTransport) Write(p []byte) (int, error) {
	t.mu.Lock()
	if t.closed {
		t.mu.Unlock()
		return 0, os.ErrClosed
	}
	t.written = append(t.written, p...)
	respond := t.onWrite
	request := append([]byte(nil), p...)
	t.mu.Unlock()
	if respond != nil {
		respond(request)
	}
	return len(p), nil
}

func (t *FakeTransport) Close() error {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.closed = true
	return nil
}

// Written is every byte the client has written, in order.
func (t *FakeTransport) Written() []byte {
	t.mu.Lock()
	defer t.mu.Unlock()
	return append([]byte(nil), t.written...)
}

// Closed reports whether the client closed the transport -- the assertion for
// "a protocol fault ends the connection".
func (t *FakeTransport) Closed() bool {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.closed
}
