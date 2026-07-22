// screenreader-mcp testsupport -- FakeBridge: a bridge speaking real wire frames.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test scaffolding. A whole fake BRIDGE -- not a port double -- serving
// the real JSON-lines contract over an in-memory net.Pipe, so a test can drive
// the real client, the real framing and the real handshake with no socket, no
// named pipe and no NVDA.
// USED BY: the headless integration tier (server/tests/), which is the tier that
// runs on every platform in CI.
//
// WHAT THIS TIER STRUCTURALLY CANNOT CATCH, and why 10c exists: this bridge
// encodes frames with the SAME adapters/wire package the server decodes them
// with, so a bug in the binding itself is invisible here -- both sides would be
// wrong together, in agreement. Only the real Python bridge can catch that. It
// is AGENTS.md's point about a fake never proving the real adapter behaves like
// it, one level up.
package testsupport

import (
	"bufio"
	"encoding/json"
	"errors"
	"io"
	"net"
	"sync"
	"time"

	adapterports "github.com/marlon-sousa/screen-readers-mcp/server/adapters/ports"
	"github.com/marlon-sousa/screen-readers-mcp/server/adapters/wire"
)

// BridgeOptions describe the bridge a test wants to face.
type BridgeOptions struct {
	// Reader is the identity `hello` announces. Zero value announces a
	// generic reader, so a test that is not about identity need not say.
	Reader wire.ReaderInfo

	// Capabilities is what `hello` announces. Nil announces all six groups;
	// an EMPTY non-nil slice announces none, which is how "a reader without
	// braille" is expressed.
	Capabilities []wire.Capability

	// ProtocolVersion is what `hello` answers with. Zero means this
	// server's own version; anything else is the protocol-mismatch
	// scenario.
	ProtocolVersion int

	// Synth, LogPath and ReaderLogPath fill out the `hello` reply.
	Synth         string
	LogPath       string
	ReaderLogPath string
}

// FakeBridge serves the wire contract over one connection.
type FakeBridge struct {
	opts BridgeOptions

	mu       sync.Mutex
	handlers map[wire.Command]func(params json.RawMessage) (any, error)
	received []wire.Command
	byeSeen  bool
}

// NewFakeBridge builds a bridge that answers the lifecycle commands, plus
// whatever handlers a test adds.
func NewFakeBridge(opts BridgeOptions) *FakeBridge {
	if opts.Reader.Name == "" {
		opts.Reader = wire.ReaderInfo{Name: "fakereader", Version: "1.0"}
	}
	if opts.Capabilities == nil {
		opts.Capabilities = []wire.Capability{
			wire.CapabilitySpeech, wire.CapabilityBraille, wire.CapabilityGestures,
			wire.CapabilityFocus, wire.CapabilityState, wire.CapabilityConfig,
		}
	}
	if opts.ProtocolVersion == 0 {
		opts.ProtocolVersion = wire.ProtocolVersion
	}
	if opts.Synth == "" {
		opts.Synth = "fakesynth"
	}
	if opts.LogPath == "" {
		opts.LogPath = `C:\logs\session.log`
	}
	if opts.ReaderLogPath == "" {
		opts.ReaderLogPath = `C:\logs\reader.log`
	}
	return &FakeBridge{opts: opts, handlers: map[wire.Command]func(json.RawMessage) (any, error){}}
}

// Handle registers the answer to one command. The result is marshalled as the
// command's `result`; an error becomes an error response, which the contract
// says an established session survives.
func (b *FakeBridge) Handle(cmd wire.Command, fn func(params json.RawMessage) (any, error)) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.handlers[cmd] = fn
}

// Received is every command the bridge was sent, in order.
func (b *FakeBridge) Received() []wire.Command {
	b.mu.Lock()
	defer b.mu.Unlock()
	return append([]wire.Command(nil), b.received...)
}

// SawBye reports whether the session was ended politely rather than dropped.
func (b *FakeBridge) SawBye() bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.byeSeen
}

// Connect returns a transport wired to this bridge over an in-memory pipe, and
// the bridge starts serving on the other end.
//
// net.Pipe rather than a loopback socket: no port to allocate, no firewall
// prompt, no flake, and it still supports the read deadlines the Transport seam
// requires -- so what is exercised is the real framing, not a shortcut around
// it.
func (b *FakeBridge) Connect() adapterports.Transport {
	client, server := net.Pipe()
	go b.serve(server)
	return &connTransport{conn: client}
}

// Serve runs the session loop on a connection the caller accepted.
//
// Exported for the real-transport tier: those tests put this same bridge behind
// a genuine loopback listener or named pipe, so the only thing that changes
// between tiers is the bytes' route, never the peer's behaviour.
func (b *FakeBridge) Serve(conn net.Conn) { b.serve(conn) }

// serve is the bridge's session loop: one JSON object per line, one response
// per request, in order.
func (b *FakeBridge) serve(conn net.Conn) {
	defer conn.Close()
	lines := bufio.NewScanner(conn)
	for lines.Scan() {
		var request wire.Request
		if err := json.Unmarshal(lines.Bytes(), &request); err != nil {
			return // a malformed line is a protocol fault; drop the session
		}
		command := wire.Command(request.Cmd)

		b.mu.Lock()
		b.received = append(b.received, command)
		handler, hasHandler := b.handlers[command]
		if command == wire.CommandBye {
			b.byeSeen = true
		}
		b.mu.Unlock()

		var (
			result any
			err    error
		)
		switch {
		case command == wire.CommandHello:
			result = b.helloResult()
		case command == wire.CommandPing, command == wire.CommandBye:
			ok := true
			result = wire.AckResult{OK: &ok}
		case hasHandler:
			result, err = handler(request.Params)
		default:
			// An unknown command is an error RESPONSE, not a framing fault:
			// the session continues (protocol.md §2).
			err = errors.New("unknown command " + request.Cmd)
		}

		if writeErr := b.respond(conn, request.ID, result, err); writeErr != nil {
			return
		}
		if command == wire.CommandBye {
			return
		}
	}
}

func (b *FakeBridge) helloResult() wire.HelloResult {
	return wire.HelloResult{
		ProtocolVersion: b.opts.ProtocolVersion,
		Reader:          b.opts.Reader,
		Capabilities:    b.opts.Capabilities,
		Mode:            wire.CaptureModeSilent,
		Synth:           b.opts.Synth,
		LogPath:         b.opts.LogPath,
		NVDALogPath:     b.opts.ReaderLogPath,
	}
}

func (b *FakeBridge) respond(conn net.Conn, id int, result any, failure error) error {
	response := wire.Response{ID: id}
	if failure != nil {
		response.Error = &wire.ErrorInfo{Message: failure.Error()}
	} else if result != nil {
		encoded, err := json.Marshal(result)
		if err != nil {
			return err
		}
		response.Result = encoded
	}
	line, err := json.Marshal(response)
	if err != nil {
		return err
	}
	_, err = conn.Write(append(line, '\n'))
	return err
}

// connTransport adapts a net.Conn to the Transport seam, applying the seam's
// poll deadline exactly as the production leaves do.
//
// It mirrors adapters/bridge's leaves rather than reusing them because those are
// unexported: they are leaves precisely so that nobody depends on them, and a
// six-line mirror here is cheaper than exporting them for a test.
type connTransport struct {
	conn net.Conn
}

func (t *connTransport) Read(p []byte) (int, error) {
	if err := t.conn.SetReadDeadline(time.Now().Add(adapterports.PollInterval)); err != nil {
		return 0, err
	}
	n, err := t.conn.Read(p)
	if err != nil && errors.Is(err, io.ErrClosedPipe) {
		return n, io.EOF
	}
	return n, err
}

func (t *connTransport) Write(p []byte) (int, error) { return t.conn.Write(p) }

func (t *connTransport) Close() error { return t.conn.Close() }
