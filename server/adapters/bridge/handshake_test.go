// screenreader-mcp adapters -- tests for handshake.go.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// Black-box (package bridge_test), driving the real handshake against
// testsupport's fake bridge over an in-memory pipe: real framing, real `hello`,
// no OS. The dialer factory is the seam that makes the ordered-endpoint policy
// testable -- a scripted factory decides which endpoint "answers".
package bridge_test

import (
	"errors"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"
	"github.com/marlon-sousa/screen-readers-mcp/server/adapters/bridge"
	adapterports "github.com/marlon-sousa/screen-readers-mcp/server/adapters/ports"
	"github.com/marlon-sousa/screen-readers-mcp/server/adapters/wire"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
	"github.com/marlon-sousa/screen-readers-mcp/server/fakes"
	"github.com/marlon-sousa/screen-readers-mcp/server/testsupport"
)

// answeredBy scripts which endpoints have something listening: an endpoint in
// the map is served by that bridge, and any other endpoint refuses the dial.
func answeredBy(bridges map[string]*testsupport.FakeBridge) bridge.DialerFactory {
	return func(endpoint entities.Endpoint) (adapterports.Dialer, error) {
		fake, ok := bridges[endpoint.String()]
		if !ok {
			return nil, errors.New("connection refused")
		}
		return func() (adapterports.Transport, error) { return fake.Connect(), nil }, nil
	}
}

func newHandshake(t testing.TB, bridges map[string]*testsupport.FakeBridge) *bridge.Handshake {
	t.Helper()
	return bridge.NewHandshake(answeredBy(bridges), fakes.NewFakeClock(), fakes.NewFakeLog())
}

func silent() ports.SessionOptions {
	return ports.SessionOptions{Mode: entities.CaptureSilent}
}

func TestDialEstablishesASessionFromHello(t *testing.T) {
	fake := testsupport.NewFakeBridge(testsupport.BridgeOptions{
		Reader:        wire.ReaderInfo{Name: "nvda", Version: "2026.1"},
		Synth:         "espeak",
		LogPath:       `C:\logs\session.log`,
		ReaderLogPath: `C:\logs\nvda.log`,
	})
	handshake := newHandshake(t, map[string]*testsupport.FakeBridge{"pipe:nvdaMcpBridge": fake})

	connection, err := handshake.Dial(testsupport.Reader(t, "nvda", "pipe:nvdaMcpBridge"), silent())
	if err != nil {
		t.Fatalf("Dial: %v", err)
	}

	want := entities.ReaderIdentity{Name: "nvda", Version: "2026.1"}
	if diff := cmp.Diff(want, connection.Session.Reader); diff != "" {
		t.Errorf("reader identity (-want +got):\n%s", diff)
	}
	if connection.Session.Synth != "espeak" {
		t.Errorf("synth = %q, want the reader's own", connection.Session.Synth)
	}
	// The wire calls this `nvdaLogPath`; the domain does not carry a reader's
	// name in a field name, and the mapping is this adapter's job.
	if connection.Session.ReaderLogPath != `C:\logs\nvda.log` {
		t.Errorf("reader log path = %q", connection.Session.ReaderLogPath)
	}
	if got := fake.Received(); len(got) == 0 || got[0] != wire.CommandHello {
		t.Errorf("first command = %v, want hello to be sent first", got)
	}
}

// The capability gate, made structural: a reader without braille yields a nil
// collaborator, so there is nothing for a braille tool to be built from.
func TestDialHandsOverOnlyTheAnnouncedCapabilities(t *testing.T) {
	fake := testsupport.NewFakeBridge(testsupport.BridgeOptions{
		Capabilities: []wire.Capability{wire.CapabilitySpeech, wire.CapabilityGestures},
	})
	handshake := newHandshake(t, map[string]*testsupport.FakeBridge{"pipe:reader": fake})

	connection, err := handshake.Dial(testsupport.Reader(t, "reader", "pipe:reader"), silent())
	if err != nil {
		t.Fatalf("Dial: %v", err)
	}

	if connection.Speech == nil {
		t.Error("speech was announced but no SpeechReader was handed over")
	}
	if connection.Gestures == nil {
		t.Error("gestures were announced but no GestureSender was handed over")
	}
	if connection.Braille != nil {
		t.Error("braille was NOT announced but a BrailleReader was handed over")
	}
	if connection.Config != nil {
		t.Error("config was NOT announced but a ConfigAccessor was handed over")
	}
	if connection.Lifecycle == nil {
		t.Error("the lifecycle belongs to no capability group and must always be present")
	}
}

// Acceptance criterion 4a: switching the bridge's transport in its dialog needs
// no server configuration. The first endpoint refuses, the second answers, and
// the result says which one did.
func TestDialFallsThroughToTheNextEndpointInDeclaredOrder(t *testing.T) {
	fake := testsupport.NewFakeBridge(testsupport.BridgeOptions{})
	handshake := newHandshake(t, map[string]*testsupport.FakeBridge{"tcp:127.0.0.1:8765": fake})

	reader := testsupport.Reader(t, "nvda", "pipe:nvdaMcpBridge", "tcp:127.0.0.1:8765")
	connection, err := handshake.Dial(reader, silent())
	if err != nil {
		t.Fatalf("Dial: %v", err)
	}

	if connection.Endpoint.String() != "tcp:127.0.0.1:8765" {
		t.Errorf("answered by %s, want the second declared endpoint", connection.Endpoint)
	}
}

func TestDialReportsEveryEndpointThatFailed(t *testing.T) {
	handshake := newHandshake(t, nil)

	reader := testsupport.Reader(t, "nvda", "pipe:nvdaMcpBridge", "tcp:127.0.0.1:8765")
	_, err := handshake.Dial(reader, silent())

	if err == nil {
		t.Fatal("Dial succeeded with nothing listening")
	}
	for _, endpoint := range []string{"pipe:nvdaMcpBridge", "tcp:127.0.0.1:8765"} {
		if !strings.Contains(err.Error(), endpoint) {
			t.Errorf("error %q does not name the failed endpoint %s", err, endpoint)
		}
	}
}

// Acceptance criterion 8: a version disagreement is a REPORTED failure naming
// both versions, never a crash -- and the remaining endpoints are not tried,
// because a bridge answered and the problem is not reachability.
func TestDialReportsAProtocolMismatchAndStopsTrying(t *testing.T) {
	fake := testsupport.NewFakeBridge(testsupport.BridgeOptions{ProtocolVersion: 99})
	other := testsupport.NewFakeBridge(testsupport.BridgeOptions{})
	handshake := newHandshake(t, map[string]*testsupport.FakeBridge{
		"pipe:nvdaMcpBridge": fake,
		"tcp:127.0.0.1:8765": other,
	})

	reader := testsupport.Reader(t, "nvda", "pipe:nvdaMcpBridge", "tcp:127.0.0.1:8765")
	_, err := handshake.Dial(reader, silent())

	var mismatch *ports.ProtocolMismatchError
	if !errors.As(err, &mismatch) {
		t.Fatalf("Dial error = %v, want a *ports.ProtocolMismatchError", err)
	}
	if mismatch.BridgeVersion != 99 {
		t.Errorf("bridge version = %d, want the one it announced", mismatch.BridgeVersion)
	}
	if diff := cmp.Diff([]int{wire.ProtocolVersion}, mismatch.ServerVersions); diff != "" {
		t.Errorf("server versions (-want +got):\n%s", diff)
	}
	if len(other.Received()) != 0 {
		t.Error("the second endpoint was dialed after a bridge answered with a bad version")
	}
}

// The capture mode is fixed for the session's lifetime, so the party that knows
// what the session is for chooses it. An adapter inventing a default would be
// that choice made by the wrong layer.
func TestDialRefusesToInventACaptureMode(t *testing.T) {
	fake := testsupport.NewFakeBridge(testsupport.BridgeOptions{})
	handshake := newHandshake(t, map[string]*testsupport.FakeBridge{"pipe:reader": fake})

	_, err := handshake.Dial(testsupport.Reader(t, "reader", "pipe:reader"), ports.SessionOptions{})

	if err == nil {
		t.Fatal("Dial succeeded with no capture mode")
	}
	if len(fake.Received()) != 0 {
		t.Error("a request was sent despite the missing capture mode")
	}
}

func TestDialRejectsAReaderWithNoEndpoints(t *testing.T) {
	handshake := newHandshake(t, nil)

	_, err := handshake.Dial(entities.ConfiguredReader{Name: "nvda"}, silent())

	if err == nil {
		t.Fatal("Dial succeeded for a reader with nowhere to dial")
	}
}

// An unknown capability string survives into the session, so the info resource
// can describe the reader honestly (protocol.md §4: ignore, which is not the
// same as discard).
func TestDialRetainsUnknownCapabilities(t *testing.T) {
	fake := testsupport.NewFakeBridge(testsupport.BridgeOptions{
		Capabilities: []wire.Capability{wire.CapabilitySpeech, "teleportation"},
	})
	handshake := newHandshake(t, map[string]*testsupport.FakeBridge{"pipe:reader": fake})

	connection, err := handshake.Dial(testsupport.Reader(t, "reader", "pipe:reader"), silent())
	if err != nil {
		t.Fatalf("Dial: %v", err)
	}

	want := []string{"speech", "teleportation"}
	if diff := cmp.Diff(want, connection.Session.Capabilities.Strings()); diff != "" {
		t.Errorf("capabilities (-want +got):\n%s", diff)
	}
}
