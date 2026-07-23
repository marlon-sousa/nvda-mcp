//go:build integration

// screenreader-mcp tests -- the agent-driven connection lifecycle, over MCP.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: integration scenario, named after the USE CASE. Behind
// //go:build integration like its neighbours; CI runs it with -tags integration
// on every platform.
//
// This is the headless tier spec 0013 says carries most of the weight, and what
// it asserts on is WHAT AN MCP CLIENT SEES -- tools/list, tools/call results,
// resource reads -- never internal state. Everything below the client is real:
// wiring, the SDK server, the tool controllers, the domain, the JSON-lines
// client and a real loopback socket. Only the bridge is a fake, and it speaks
// real wire frames.
//
// The capability GATE's scenarios -- the gated tools appearing and retracting, a
// reader without braille, the retracted-tool backstop -- arrive with the gated
// tools themselves, in the last of 10b's three PRs. What is proved here is
// everything that does not depend on one existing.
package integration_test

import (
	"slices"
	"strings"
	"testing"

	"github.com/marlon-sousa/screen-readers-mcp/server/adapters/wire"
	"github.com/marlon-sousa/screen-readers-mcp/server/testsupport"
)

// ungated is what a server with no session must advertise, and exactly that.
var ungated = []string{"connect_reader", "disconnect_reader", "list_readers", "status"}

func advertised(t *testing.T, h *testsupport.MCPHarness) []string {
	t.Helper()
	names := h.ToolNames(t)
	slices.Sort(names)
	return names
}

// Acceptance criterion 3.
func TestAFreshServerAdvertisesOnlyTheUngatedToolsAndHasDialedNothing(t *testing.T) {
	h := testsupport.StartMCP(t, testsupport.BridgeOptions{})

	if names := advertised(t, h); !slices.Equal(names, ungated) {
		t.Errorf("tools/list = %v, want exactly %v", names, ungated)
	}

	// Acceptance criterion 9: nothing was dialed, so the bridge saw nothing.
	if got := h.Bridge.Received(); len(got) != 0 {
		t.Errorf("the bridge was sent %v before any agent asked", got)
	}

	var status struct {
		State string `json:"state"`
		Live  *bool  `json:"live"`
	}
	h.Call(t, "status", nil).Decode(t, &status)
	if status.State != "disconnected" {
		t.Errorf("status state = %q, want disconnected", status.State)
	}
	if status.Live != nil {
		t.Errorf("live = %v, want absent when there is no session to ping", *status.Live)
	}
}

// Acceptance criterion 3's second half: the readers are reported from the
// configured set, and reporting them dials nothing.
func TestListReadersReportsTheConfiguredReadersWithoutDialing(t *testing.T) {
	h := testsupport.StartMCP(t, testsupport.BridgeOptions{})

	var listing struct {
		Readers []struct {
			Reader    string `json:"reader"`
			Endpoints []struct {
				Endpoint string `json:"endpoint"`
				Liveness string `json:"liveness"`
			} `json:"endpoints"`
		} `json:"readers"`
	}
	h.Call(t, "list_readers", nil).Decode(t, &listing)

	if len(listing.Readers) != 1 || listing.Readers[0].Reader != "nvda" {
		t.Fatalf("readers = %+v, want the one configured reader", listing.Readers)
	}
	// A TCP endpoint cannot be tested without connecting, and connecting
	// would occupy the single session slot the agent is about to want.
	if listing.Readers[0].Endpoints[0].Liveness != "unknown" {
		t.Errorf("liveness = %q, want unknown for a TCP endpoint",
			listing.Readers[0].Endpoints[0].Liveness)
	}
	if got := h.Bridge.Received(); len(got) != 0 {
		t.Errorf("list_readers dialed the bridge: %v", got)
	}
}

// Connecting really does reach the bridge and complete a handshake, and what
// comes back describes the session the wire established.
func TestConnectingHandshakesAndDescribesTheSession(t *testing.T) {
	h := testsupport.StartMCP(t, testsupport.BridgeOptions{
		Reader: wire.ReaderInfo{Name: "nvda", Version: "2026.1"},
	})

	result := h.Connect(t)
	if result.IsError {
		t.Fatalf("connect_reader failed: %s", result.Text)
	}

	var connected struct {
		Reader        string   `json:"reader"`
		ReaderVersion string   `json:"readerVersion"`
		Endpoint      string   `json:"endpoint"`
		Capabilities  []string `json:"capabilities"`
		Mode          string   `json:"mode"`
		LogPath       string   `json:"logPath"`
		ReaderLogPath string   `json:"readerLogPath"`
	}
	result.Decode(t, &connected)

	if connected.Reader != "nvda" || connected.ReaderVersion != "2026.1" {
		t.Errorf("reader = %q %q, want what hello announced",
			connected.Reader, connected.ReaderVersion)
	}
	if !strings.HasPrefix(connected.Endpoint, "tcp:") {
		t.Errorf("endpoint = %q, want the one that answered", connected.Endpoint)
	}
	// Acceptance criterion 5: the mode reported is the one hello established.
	if connected.Mode != "silent" {
		t.Errorf("mode = %q, want silent", connected.Mode)
	}
	if connected.LogPath == "" || connected.ReaderLogPath == "" {
		t.Error("both session log paths must be reported")
	}
	if got := h.Bridge.Received(); len(got) == 0 || got[0] != wire.CommandHello {
		t.Errorf("the bridge was sent %v; hello must come first", got)
	}
}

// `status` makes a real round trip while a session is live, so its answer is
// proof rather than possibly-stale local state.
func TestStatusProvesALiveSessionOnTheWire(t *testing.T) {
	h := testsupport.StartMCP(t, testsupport.BridgeOptions{
		Reader: wire.ReaderInfo{Name: "nvda", Version: "2026.1"},
	})
	if got := h.Connect(t); got.IsError {
		t.Fatalf("connect_reader: %s", got.Text)
	}

	var status struct {
		State   string `json:"state"`
		Live    *bool  `json:"live"`
		Session *struct {
			Reader string `json:"reader"`
		} `json:"session"`
	}
	h.Call(t, "status", nil).Decode(t, &status)

	if status.State != "connected" {
		t.Errorf("state = %q, want connected", status.State)
	}
	if status.Live == nil || !*status.Live {
		t.Errorf("live = %v, want true", status.Live)
	}
	if status.Session == nil || status.Session.Reader != "nvda" {
		t.Errorf("session = %+v, want the live session described", status.Session)
	}
	if !slices.Contains(h.Bridge.Received(), wire.CommandPing) {
		t.Error("status answered without a round trip; it must ask the wire")
	}
}

// Acceptance criterion 7: a second connect is refused and the live session is
// left untouched.
func TestConnectingWhileConnectedIsRefused(t *testing.T) {
	h := testsupport.StartMCP(t, testsupport.BridgeOptions{})
	if got := h.Connect(t); got.IsError {
		t.Fatalf("connect_reader failed: %s", got.Text)
	}

	second := h.Connect(t)
	if !second.IsError {
		t.Fatal("a second connect_reader succeeded")
	}
	if !strings.Contains(second.Text, "disconnect_reader") {
		t.Errorf("error = %q, want it to say what to do instead", second.Text)
	}

	// The session survived: status still describes it.
	var status struct {
		State string `json:"state"`
	}
	h.Call(t, "status", nil).Decode(t, &status)
	if status.State != "connected" {
		t.Errorf("state = %q after a refused connect, want the session untouched", status.State)
	}
}

// Disconnecting is polite -- the bridge sees `bye` -- and the ungated four
// survive it, since they are how the agent gets back.
func TestDisconnectingSendsByeAndLeavesTheUngatedToolsStanding(t *testing.T) {
	h := testsupport.StartMCP(t, testsupport.BridgeOptions{})
	if got := h.Connect(t); got.IsError {
		t.Fatalf("connect_reader: %s", got.Text)
	}

	if got := h.Call(t, "disconnect_reader", nil); got.IsError {
		t.Fatalf("disconnect_reader failed: %s", got.Text)
	}

	if !h.Bridge.SawBye() {
		t.Error("the bridge never saw bye")
	}
	if names := advertised(t, h); !slices.Equal(names, ungated) {
		t.Errorf("tools/list = %v, want the ungated four to survive", names)
	}
}

// Scenario 3, and acceptance criterion 8: reported, not fatal.
func TestAProtocolMismatchIsReportedAndTheServerKeepsRunning(t *testing.T) {
	h := testsupport.StartMCP(t, testsupport.BridgeOptions{ProtocolVersion: 99})

	result := h.Connect(t)
	if !result.IsError {
		t.Fatal("a protocol mismatch connected successfully")
	}
	if !strings.Contains(result.Text, "99") {
		t.Errorf("error = %q, want both versions named", result.Text)
	}

	// The process is alive, still serving, and still saying why.
	var status struct {
		State  string `json:"state"`
		Reason string `json:"reason"`
	}
	h.Call(t, "status", nil).Decode(t, &status)
	if status.State != "incompatible" {
		t.Errorf("state = %q, want incompatible", status.State)
	}
	if !strings.Contains(status.Reason, "99") {
		t.Errorf("reason = %q, want it to keep naming the versions", status.Reason)
	}
}

// An unknown reader errors with the known names, so a wrong guess self-corrects
// in the same turn -- and does not become a dial.
func TestAnUnknownReaderNamesTheOnesThatExist(t *testing.T) {
	h := testsupport.StartMCP(t, testsupport.BridgeOptions{})

	result := h.Call(t, "connect_reader", map[string]any{
		"reader": "narrator", "mode": "silent",
	})
	if !result.IsError {
		t.Fatal("connecting to an unknown reader succeeded")
	}
	if !strings.Contains(result.Text, "nvda") {
		t.Errorf("error = %q, want the known readers listed", result.Text)
	}
	if got := h.Bridge.Received(); len(got) != 0 {
		t.Errorf("an unknown reader was dialed: %v", got)
	}
}

// Reconnecting after a disconnect opens a fresh session.
func TestReconnectingAfterADisconnectOpensAFreshSession(t *testing.T) {
	h := testsupport.StartMCP(t, testsupport.BridgeOptions{})

	if got := h.Connect(t); got.IsError {
		t.Fatalf("connect_reader: %s", got.Text)
	}
	if got := h.Call(t, "disconnect_reader", nil); got.IsError {
		t.Fatalf("disconnect_reader: %s", got.Text)
	}
	if got := h.Connect(t); got.IsError {
		t.Fatalf("reconnecting: %s", got.Text)
	}

	var status struct {
		State string `json:"state"`
	}
	h.Call(t, "status", nil).Decode(t, &status)
	if status.State != "connected" {
		t.Errorf("state = %q, want connected again", status.State)
	}
}

// A tool failure is a RESULT with IsError, not a JSON-RPC error, so an agent can
// read the reason and self-correct within the turn.
func TestAToolFailureIsAReadableResultRatherThanAProtocolError(t *testing.T) {
	h := testsupport.StartMCP(t, testsupport.BridgeOptions{})

	result := h.Call(t, "connect_reader", map[string]any{
		"reader": "nvda", "mode": "whispered",
	})
	if !result.IsError {
		t.Fatal("an invalid capture mode was accepted")
	}
	if !strings.Contains(result.Text, "silent") {
		t.Errorf("error = %q, want the valid modes listed in a readable result", result.Text)
	}
}
