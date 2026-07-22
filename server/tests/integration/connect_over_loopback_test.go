//go:build integration

// screenreader-mcp tests -- connecting to a bridge over real loopback TCP.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: integration scenario, named after the USE CASE rather than a file, and
// behind //go:build integration so `go test ./...` stays fast. CI runs it
// explicitly with -tags integration, on every platform.
//
// What this tier adds over the unit tests: the TCP LEAF is real. The unit tests
// prove the client's decisions against a fake seam, which by construction cannot
// prove that a real socket behaves like that fake -- the poll deadline, short
// reads, EOF on close. Here the bytes cross a genuine loopback connection, and
// the composition (endpoint parsing -> DialerFor -> leaf -> client -> handshake)
// is the production one.
//
// What it still cannot catch, and why 10c exists: the peer is a Go fake using
// the same generated binding as the server, so a bug in the binding itself would
// have both sides wrong together, in agreement.
package integration_test

import (
	"encoding/json"
	"net"
	"testing"

	"github.com/marlon-sousa/screen-readers-mcp/server/adapters/bridge"
	"github.com/marlon-sousa/screen-readers-mcp/server/adapters/wire"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
	"github.com/marlon-sousa/screen-readers-mcp/server/fakes"
	"github.com/marlon-sousa/screen-readers-mcp/server/testsupport"
)

// listenLoopback starts the fake bridge on a real loopback socket and returns
// its endpoint spec. Port 0 so parallel runs cannot collide.
func listenLoopback(t *testing.T, fake *testsupport.FakeBridge) string {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listening on loopback: %v", err)
	}
	t.Cleanup(func() { listener.Close() })

	go func() {
		for {
			conn, err := listener.Accept()
			if err != nil {
				return
			}
			go fake.Serve(conn)
		}
	}()
	return "tcp:" + listener.Addr().String()
}

func newHandshake() *bridge.Handshake {
	// The production dialer factory: real endpoint decisions, real leaves.
	return bridge.NewHandshake(bridge.DialerFor, fakes.NewFakeClock(), fakes.NewFakeLog())
}

func TestASessionIsEstablishedOverRealLoopbackTCP(t *testing.T) {
	fake := testsupport.NewFakeBridge(testsupport.BridgeOptions{
		Reader: wire.ReaderInfo{Name: "nvda", Version: "2026.1"},
	})
	spec := listenLoopback(t, fake)

	connection, err := newHandshake().Dial(
		testsupport.Reader(t, "nvda", spec),
		ports.SessionOptions{Mode: entities.CaptureSilent},
	)
	if err != nil {
		t.Fatalf("Dial: %v", err)
	}
	t.Cleanup(func() { connection.Lifecycle.Close() })

	if connection.Session.Reader.Name != "nvda" {
		t.Errorf("reader = %q, want the one hello announced", connection.Session.Reader.Name)
	}
	if connection.Endpoint.String() != spec {
		t.Errorf("answered by %s, want %s", connection.Endpoint, spec)
	}
}

// A whole command round trip over the real socket, including a result decoded
// back into domain vocabulary.
func TestACommandRoundTripsOverRealLoopbackTCP(t *testing.T) {
	fake := testsupport.NewFakeBridge(testsupport.BridgeOptions{})
	fake.Handle(wire.CommandGetSpeech, func(params json.RawMessage) (any, error) {
		return wire.SpeechResult{Text: "Edit  blank", FromIndex: 0, ToIndex: 1}, nil
	})
	spec := listenLoopback(t, fake)

	connection, err := newHandshake().Dial(
		testsupport.Reader(t, "nvda", spec),
		ports.SessionOptions{Mode: entities.CaptureSilent},
	)
	if err != nil {
		t.Fatalf("Dial: %v", err)
	}
	t.Cleanup(func() { connection.Lifecycle.Close() })

	speech, err := connection.Speech.SpeechSince(0)
	if err != nil {
		t.Fatalf("SpeechSince: %v", err)
	}
	if speech.Text != "Edit  blank" || speech.ToIndex != 1 {
		t.Errorf("speech = %+v, want the bridge's own answer", speech)
	}
}

// A dead first endpoint must not cost the agent its connection: the second is
// dialed and the result says which one answered. Both endpoints are sockets
// here so the scenario runs on every platform.
func TestADeadFirstEndpointFallsThroughToTheSecond(t *testing.T) {
	fake := testsupport.NewFakeBridge(testsupport.BridgeOptions{})
	live := listenLoopback(t, fake)

	// A port that was listening and is not any more is the closest portable
	// stand-in for a bridge that was switched to the other transport.
	dead, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listening: %v", err)
	}
	deadSpec := "tcp:" + dead.Addr().String()
	dead.Close()

	connection, err := newHandshake().Dial(
		testsupport.Reader(t, "nvda", deadSpec, live),
		ports.SessionOptions{Mode: entities.CaptureSilent},
	)
	if err != nil {
		t.Fatalf("Dial: %v", err)
	}
	t.Cleanup(func() { connection.Lifecycle.Close() })

	if connection.Endpoint.String() != live {
		t.Errorf("answered by %s, want the second endpoint %s", connection.Endpoint, live)
	}
}

// Bye ends the session politely; the bridge sees it, which is what makes a
// disconnect distinguishable from a crash on the bridge's side.
func TestDisconnectingSendsBye(t *testing.T) {
	fake := testsupport.NewFakeBridge(testsupport.BridgeOptions{})
	spec := listenLoopback(t, fake)

	connection, err := newHandshake().Dial(
		testsupport.Reader(t, "nvda", spec),
		ports.SessionOptions{Mode: entities.CaptureSilent},
	)
	if err != nil {
		t.Fatalf("Dial: %v", err)
	}

	if err := connection.Lifecycle.Bye(); err != nil {
		t.Fatalf("Bye: %v", err)
	}
	if err := connection.Lifecycle.Close(); err != nil {
		t.Fatalf("Close: %v", err)
	}
	if !fake.SawBye() {
		t.Error("the bridge never saw bye")
	}
}
