//go:build integration

// screenreader-mcp tests -- the capability gate, over MCP.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: integration scenario, named after the USE CASE. Spec 0013's headless
// scenarios 1, 2 and 4, and acceptance criteria 5, 6 and 10 -- proved where they
// actually matter, at the MCP boundary, with everything below the client real
// except the bridge.
//
// The gate is keyed on CAPABILITY STRINGS and never on reader names, so every
// bridge below is called "nvda" and differs only in what `hello` announced. If
// any of these passed because of a reader name, that would be the bug.
package integration_test

import (
	"encoding/json"
	"errors"
	"slices"
	"strings"
	"testing"

	"github.com/marlon-sousa/screen-readers-mcp/server/adapters/wire"
	"github.com/marlon-sousa/screen-readers-mcp/server/testsupport"
)

// everyGatedTool is what a reader announcing all six capabilities should see.
var everyGatedTool = []string{
	"get_braille", "get_config", "get_focus_info", "get_last_speech",
	"get_next_speech_index", "get_speech", "get_state", "press_gesture",
	"set_config", "wait_for_speech", "wait_for_speech_to_finish",
}

// nvda is a bridge announcing exactly these capabilities and nothing else.
//
// The empty slice is made non-nil deliberately: BridgeOptions distinguishes "the
// test did not say" (nil, meaning all six) from "this reader announces none",
// and it is the second that the gate's hardest case needs.
func nvda(capabilities ...wire.Capability) testsupport.BridgeOptions {
	if capabilities == nil {
		capabilities = []wire.Capability{}
	}
	return testsupport.BridgeOptions{
		Reader:       wire.ReaderInfo{Name: "nvda", Version: "2026.1"},
		Capabilities: capabilities,
	}
}

// Scenario 1 in full: connect, the gated tools appear, call one, disconnect,
// they retract. Acceptance criteria 5 and 6.
func TestConnectingPublishesTheGatedToolsAndDisconnectingRetractsThem(t *testing.T) {
	h := testsupport.StartMCP(t, testsupport.BridgeOptions{
		Reader: wire.ReaderInfo{Name: "nvda", Version: "2026.1"},
	})

	if got := advertised(t, h); !slices.Equal(got, ungated) {
		t.Fatalf("tools/list = %v before connecting, want only the ungated four", got)
	}

	if got := h.Connect(t); got.IsError {
		t.Fatalf("connect_reader failed: %s", got.Text)
	}
	h.AwaitToolsChanged(t)

	want := append(append([]string{}, everyGatedTool...), ungated...)
	slices.Sort(want)
	if got := advertised(t, h); !slices.Equal(got, want) {
		t.Errorf("tools/list = %v, want every tool published %v", got, want)
	}

	// A real gated call, over the whole stack, answered by the bridge.
	h.Bridge.Handle(wire.CommandGetSpeech, func(json.RawMessage) (any, error) {
		return wire.SpeechResult{Text: "Edit  blank", FromIndex: 0, ToIndex: 1}, nil
	})
	speech := h.Call(t, "get_speech", map[string]any{"since_index": 0})
	if speech.IsError {
		t.Fatalf("get_speech failed: %s", speech.Text)
	}
	var window struct {
		Text    string `json:"text"`
		ToIndex int    `json:"toIndex"`
	}
	speech.Decode(t, &window)
	if window.Text != "Edit  blank" || window.ToIndex != 1 {
		t.Errorf("get_speech = %+v, want the bridge's own answer", window)
	}

	if got := h.Call(t, "disconnect_reader", nil); got.IsError {
		t.Fatalf("disconnect_reader failed: %s", got.Text)
	}
	h.AwaitToolsChanged(t)

	if got := advertised(t, h); !slices.Equal(got, ungated) {
		t.Errorf("tools/list = %v, want the gated tools retracted and the ungated "+
			"four left standing", got)
	}
}

// Scenario 2, and acceptance criterion 10 in both its clauses. The reader is
// still called nvda: only what it ANNOUNCED differs.
func TestAReaderWithoutBrailleNeverGetsTheBrailleToolAndSaysSoIfCalled(t *testing.T) {
	h := testsupport.StartMCP(t, nvda(
		wire.CapabilitySpeech, wire.CapabilityGestures, wire.CapabilityFocus,
	))
	if got := h.Connect(t); got.IsError {
		t.Fatalf("connect_reader: %s", got.Text)
	}
	h.AwaitToolsChanged(t)

	// First clause: not advertised.
	if h.Advertises(t, "get_braille") {
		t.Errorf("tools/list = %v, want no braille tool for a reader that never "+
			"announced braille", h.ToolNames(t))
	}
	// And the ones it did announce are there, so this is a gate and not a
	// blanket refusal.
	for _, name := range []string{"get_speech", "press_gesture", "get_focus_info"} {
		if !h.Advertises(t, name) {
			t.Errorf("%s is missing, though the reader announced its capability", name)
		}
	}
	if h.Advertises(t, "get_config") {
		t.Error("get_config was advertised, though the reader announced no config")
	}

	// Second clause: calling it anyway -- with a stale tool list, say -- gives
	// the structured capability error rather than the SDK's `unknown tool`.
	result := h.Call(t, "get_braille", map[string]any{"since_index": 0})
	if !result.IsError {
		t.Fatal("get_braille succeeded on a reader with no braille")
	}
	if !strings.Contains(result.Text, "braille") {
		t.Errorf("error = %q, want the missing capability named", result.Text)
	}
	if !strings.Contains(result.Text, "nvda") {
		t.Errorf("error = %q, want the connected reader named", result.Text)
	}
	if strings.Contains(result.Text, "unknown tool") {
		t.Errorf("error = %q, want a capability error rather than the SDK's "+
			"unknown-tool answer", result.Text)
	}
}

// A reader announcing nothing at all gets no gated tools, and the empty
// announcement is not mistaken for "announced everything".
func TestAReaderAnnouncingNothingGetsNoGatedTools(t *testing.T) {
	h := testsupport.StartMCP(t, nvda())
	if got := h.Connect(t); got.IsError {
		t.Fatalf("connect_reader: %s", got.Text)
	}

	if got := advertised(t, h); !slices.Equal(got, ungated) {
		t.Errorf("tools/list = %v, want only the ungated four", got)
	}
}

// protocol.md §4: an unknown capability string must be ignored rather than
// rejected -- the set can grow without breaking an older peer -- and it is still
// reported honestly, because a reader deserves describing even where this server
// has no tool for what it offers.
func TestAnUnknownAnnouncedCapabilityIsIgnoredButStillReported(t *testing.T) {
	h := testsupport.StartMCP(t, nvda(wire.CapabilitySpeech, wire.Capability("telepathy")))

	result := h.Connect(t)
	if result.IsError {
		t.Fatalf("an unknown capability broke the handshake: %s", result.Text)
	}
	h.AwaitToolsChanged(t)

	var connected struct {
		Capabilities []string `json:"capabilities"`
	}
	result.Decode(t, &connected)
	if !slices.Contains(connected.Capabilities, "telepathy") {
		t.Errorf("capabilities = %v, want the unknown one retained and reported",
			connected.Capabilities)
	}
	if !h.Advertises(t, "get_speech") {
		t.Error("the known capability was not honoured alongside the unknown one")
	}
}

// Calling a gated tool with NO session gives the other message -- "connect
// first" -- because the two situations need different actions from the agent.
func TestCallingAGatedToolWithNoSessionSaysToConnectFirst(t *testing.T) {
	h := testsupport.StartMCP(t, nvda(wire.CapabilitySpeech))

	result := h.Call(t, "get_speech", map[string]any{"since_index": 0})

	if !result.IsError {
		t.Fatal("get_speech succeeded with nothing connected")
	}
	if !strings.Contains(result.Text, "connect_reader") {
		t.Errorf("error = %q, want it to name the tool that fixes this", result.Text)
	}
}

// A name that was never a tool still gets the SDK's own protocol error: the
// backstop answers only for tools this server actually has.
func TestAGenuinelyUnknownToolIsStillAProtocolError(t *testing.T) {
	h := testsupport.StartMCP(t, nvda(wire.CapabilitySpeech))

	h.CallExpectingProtocolError(t, "make_coffee")
}

// Scenario 4: the connection dies mid-session. The in-flight call fails cleanly,
// the tools retract without anybody restarting anything, and a later
// connect_reader opens a fresh session.
func TestAConnectionThatDiesMidSessionRetractsTheToolsAndCanBeReopened(t *testing.T) {
	h := testsupport.StartMCP(t, nvda(testsupport.EveryWireCapability()...))
	if got := h.Connect(t); got.IsError {
		t.Fatalf("connect_reader: %s", got.Text)
	}
	h.AwaitToolsChanged(t)
	if !h.Advertises(t, "get_speech") {
		t.Fatal("the gated tools were never published")
	}

	// The bridge drops the connection while serving a command, which is what
	// a crashed reader looks like from here.
	h.Bridge.Handle(wire.CommandGetSpeech, func(json.RawMessage) (any, error) {
		h.Bridge.DropConnection()
		return wire.SpeechResult{}, nil
	})

	result := h.Call(t, "get_speech", map[string]any{"since_index": 0})
	if !result.IsError {
		t.Fatal("a call over a dead connection reported success")
	}
	h.AwaitToolsChanged(t)

	if h.Advertises(t, "get_speech") {
		t.Errorf("tools/list = %v, want the gated tools retracted once the "+
			"connection was seen to have gone", h.ToolNames(t))
	}
	var status struct {
		State  string `json:"state"`
		Reason string `json:"reason"`
	}
	h.Call(t, "status", nil).Decode(t, &status)
	if status.State != "disconnected" {
		t.Errorf("state = %q, want disconnected", status.State)
	}
	if status.Reason == "" {
		t.Error("reason is empty; status must say why the session ended")
	}

	// And the agent can open a fresh one when it chooses -- the server never
	// did so on its own.
	if got := h.Connect(t); got.IsError {
		t.Fatalf("reconnecting after a loss: %s", got.Text)
	}
	h.AwaitToolsChanged(t)
	if !h.Advertises(t, "get_speech") {
		t.Errorf("tools/list = %v, want the gated tools published again", h.ToolNames(t))
	}
}

// Reader vocabulary rides through as opaque data (spec 0005, principle 3): the
// gesture ids the agent sends reach the bridge unchanged, and the roles and
// states it gets back are the reader's own.
func TestReaderVocabularyPassesThroughUntouched(t *testing.T) {
	h := testsupport.StartMCP(t, nvda(testsupport.EveryWireCapability()...))
	if got := h.Connect(t); got.IsError {
		t.Fatalf("connect_reader: %s", got.Text)
	}
	h.AwaitToolsChanged(t)

	var pressed []string
	h.Bridge.Handle(wire.CommandPressGesture, func(params json.RawMessage) (any, error) {
		var request wire.PressGestureParams
		if err := json.Unmarshal(params, &request); err != nil {
			return nil, err
		}
		pressed = request.Gestures
		ok := true
		return wire.AckResult{OK: &ok}, nil
	})
	h.Bridge.Handle(wire.CommandGetFocusInfo, func(json.RawMessage) (any, error) {
		return wire.FocusInfoResult{
			Name:   "Text editor",
			Role:   "editableText",
			States: []string{"focusable", "focused"},
		}, nil
	})

	if got := h.Call(t, "press_gesture", map[string]any{
		"gestures": []string{"kb:NVDA+control+f7"},
	}); got.IsError {
		t.Fatalf("press_gesture failed: %s", got.Text)
	}
	if !slices.Equal(pressed, []string{"kb:NVDA+control+f7"}) {
		t.Errorf("the bridge received %v, want the id unchanged", pressed)
	}

	var focus struct {
		Role   string   `json:"role"`
		States []string `json:"states"`
	}
	h.Call(t, "get_focus_info", nil).Decode(t, &focus)
	if focus.Role != "editableText" || len(focus.States) != 2 {
		t.Errorf("focus = %+v, want the reader's own vocabulary unchanged", focus)
	}
}

// A bridge REFUSING a command is not a lost connection: protocol.md §3 says an
// established session survives a failing command, so the tools must stay.
func TestARefusedCommandDoesNotEndTheSession(t *testing.T) {
	h := testsupport.StartMCP(t, nvda(wire.CapabilityGestures))
	if got := h.Connect(t); got.IsError {
		t.Fatalf("connect_reader: %s", got.Text)
	}
	h.AwaitToolsChanged(t)

	h.Bridge.Handle(wire.CommandPressGesture, func(json.RawMessage) (any, error) {
		return nil, errUnknownGesture
	})

	result := h.Call(t, "press_gesture", map[string]any{"gestures": []string{"kb:nonsense"}})
	if !result.IsError {
		t.Fatal("a refused gesture reported success")
	}

	if !h.Advertises(t, "press_gesture") {
		t.Error("a refusal retracted the gated tools; only a lost connection should")
	}
	var status struct {
		State string `json:"state"`
	}
	h.Call(t, "status", nil).Decode(t, &status)
	if status.State != "connected" {
		t.Errorf("state = %q, want the session still connected after a refusal", status.State)
	}
}

// errUnknownGesture is a bridge refusing a command -- an ordinary failure the
// session survives, distinct from the connection going away.
var errUnknownGesture = errors.New("unknown gesture id")
