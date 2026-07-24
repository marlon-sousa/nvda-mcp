//go:build conformance

// screenreader-mcp tests -- a whole session against the REAL Python bridge.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: conformance scenario, named after the use case, behind
// //go:build conformance so `go test ./...` stays fast and the Windows-only run
// opts in explicitly. Deliverable 19 of spec 0013.
// DRIVES: the built server binary over stdio (python_bridge_test.go), which
// dials the real NVDA bridge over a real transport.
//
// WHAT THIS TIER PROVES THAT NO OTHER TIER CAN. Two INDEPENDENT implementations
// of specs/wire/v1/ -- a generated Go binding and a hand-written Python module --
// agree about actual bytes. Every other tier's bridge is a Go fake that encodes
// with the same binding the server decodes with, so a bug in the binding is
// invisible there; both sides would be wrong together, in agreement. That is the
// same argument AGENTS.md makes about unit fakes never proving a real adapter
// behaves like its fake, one level up, and it is what replaced the same-bytes
// drift guarantee when the server stopped being Python.
//
// So the assertions below are deliberately about VALUES CROSSING THE WIRE --
// field names, enum spellings, index arithmetic, the shape of a result -- rather
// than about server behaviour, which the headless tier already covers with far
// better failure messages.
//
// Everything except the reader itself is real: NVDA is faked at the bridge's own
// AdapterFactory port, because what is under test here is the wire, not NVDA
// (that is entry 11's live run).
package conformance_test

import (
	"slices"
	"strings"
	"testing"

	"github.com/marlon-sousa/screen-readers-mcp/server/testsupport"
)

// What the harness on the far side announces and scripts. These are literals
// from bridges/nvda/tests/support/conformance_bridge.py: this tier is the seam
// between two languages, so the agreement is spelled out on both sides rather
// than shared through a constant neither could import.
const (
	readerName    = "nvda"
	readerVersion = "2026.1.0-conformance"
	scriptedKey   = "kb:NVDA+f7"
	firstLine     = "Elements list dialog"
	secondLine    = "Links radio button checked"
	brailleCells  = "elements lst dlg"
	fakeSynth     = "espeak"
)

// ungatedTools is what a server with no session advertises; gatedTools is what
// this bridge's announced capabilities must add. `announce` is announced too and
// gates nothing here -- there is no announce tool -- which is exactly the
// "ignore what you do not know" clause of protocol.md §4 being exercised against
// a real announcement rather than a scripted one.
var (
	ungatedTools = []string{"connect_reader", "disconnect_reader", "list_readers", "status"}

	gatedTools = []string{
		"get_braille",               // braille
		"get_last_speech",           // speech
		"get_next_speech_index",     // speech
		"get_speech",                // speech
		"press_gesture",             // gestures
		"wait_for_speech",           // speech
		"wait_for_speech_to_finish", // speech
	}

	// The bridge does not announce focus/state/config (it answers those with a
	// clean error until session E), so the gate must not advertise their tools.
	// This is the capability gate proven against a REAL announcement.
	unannouncedTools = []string{"get_config", "get_focus_info", "get_state", "set_config"}
)

// TestAWholeSessionOverLoopbackTCP is the conformance run over TCP. Its named
// pipe twin lives beside it, behind an additional `windows` tag.
func TestAWholeSessionOverLoopbackTCP(t *testing.T) {
	runWholeSession(t, "tcp")
}

// runWholeSession is the scenario spec 0013 deliverable 19 describes: handshake,
// a capability-gated tool list, one command per capability group, and a clean
// teardown -- repeated over each transport.
func runWholeSession(t *testing.T, transport string) {
	t.Helper()

	bridge := startPythonBridge(t, transport)
	harness := startServer(t, bridge.Endpoint)

	assertAdvertises(t, harness, ungatedTools, nil)

	session := connect(t, harness, bridge)
	harness.AwaitToolsChanged(t)
	assertAdvertises(t, harness, append(slices.Clone(ungatedTools), gatedTools...), unannouncedTools)

	exerciseGestures(t, harness)
	exerciseSpeech(t, harness)
	exerciseBraille(t, harness)
	assertStatusIsProvenOnTheWire(t, harness)
	assertInfoDescribesTheSession(t, harness, session)

	disconnect(t, harness)
	harness.AwaitToolsChanged(t)
	assertAdvertises(t, harness, ungatedTools, gatedTools)

	// A second session on the same bridge process: `bye` really did tear the
	// first one down, and the bridge went back to accepting. A teardown that
	// only looked clean from this side would fail here.
	connect(t, harness, bridge)
	harness.AwaitToolsChanged(t)
	disconnect(t, harness)
}

// connectedSession is connect_reader's answer -- everything `hello` established,
// after it has crossed the binding.
type connectedSession struct {
	Reader        string   `json:"reader"`
	ReaderVersion string   `json:"readerVersion"`
	Endpoint      string   `json:"endpoint"`
	Capabilities  []string `json:"capabilities"`
	Mode          string   `json:"mode"`
	Synth         string   `json:"synth"`
	LogPath       string   `json:"logPath"`
	ReaderLogPath string   `json:"readerLogPath"`
}

// connect performs the handshake and checks that every field the real bridge
// sent survived the crossing.
//
// This is the single densest assertion in the tier: `hello` carries a nested
// object, a string enum, a string array and an integer, so a binding that got
// any field NAME wrong -- `nvdaLogPath` rather than `readerLogPath`, `reader` as
// a string rather than an object -- fails here and nowhere else.
func connect(t *testing.T, harness *testsupport.MCPHarness, bridge *pythonBridge) connectedSession {
	t.Helper()

	result := harness.Connect(t)
	if result.IsError {
		t.Fatalf("connect_reader against the real bridge failed: %s\nthe bridge said:\n%s",
			result.Text, bridge.Stderr())
	}

	var session connectedSession
	result.Decode(t, &session)

	if session.Reader != readerName || session.ReaderVersion != readerVersion {
		t.Errorf("reader = %q %q, want %q %q as the real bridge announced it",
			session.Reader, session.ReaderVersion, readerName, readerVersion)
	}
	if session.Endpoint != bridge.Endpoint {
		t.Errorf("endpoint = %q, want the one the bridge is listening on, %q",
			session.Endpoint, bridge.Endpoint)
	}
	// The capture mode is a wire ENUM on both sides, spelled independently.
	if session.Mode != "silent" {
		t.Errorf("mode = %q, want the silent mode hello established", session.Mode)
	}
	if session.Synth != fakeSynth {
		t.Errorf("synth = %q, want %q", session.Synth, fakeSynth)
	}
	// Both log paths come back on fields the two sides name DIFFERENTLY
	// (`nvdaLogPath` on the wire, `readerLogPath` in domain vocabulary), so an
	// empty one here means the mapping, not the bridge.
	if session.LogPath == "" || session.ReaderLogPath == "" {
		t.Errorf("log paths = %q / %q, want both reported", session.LogPath, session.ReaderLogPath)
	}

	want := []string{"announce", "braille", "gestures", "speech"}
	got := slices.Clone(session.Capabilities)
	slices.Sort(got)
	if !slices.Equal(got, want) {
		t.Errorf("capabilities = %v, want %v exactly as the real bridge announces them", got, want)
	}
	return session
}

// disconnect ends the session politely and insists the bridge accepted the
// `bye`.
func disconnect(t *testing.T, harness *testsupport.MCPHarness) {
	t.Helper()
	if result := harness.Call(t, "disconnect_reader", nil); result.IsError {
		t.Fatalf("disconnect_reader: %s", result.Text)
	}
}

// exerciseGestures is the `gestures` capability group: opaque reader ids over
// the wire and back.
func exerciseGestures(t *testing.T, harness *testsupport.MCPHarness) {
	t.Helper()

	var pressed struct {
		Pressed []string `json:"pressed"`
	}
	harness.Call(t, "press_gesture", map[string]any{
		"gestures": []string{scriptedKey},
	}).Decode(t, &pressed)

	if !slices.Equal(pressed.Pressed, []string{scriptedKey}) {
		t.Errorf("pressed = %v, want the id passed through untouched", pressed.Pressed)
	}
}

// exerciseSpeech is the `speech` capability group, and the one place index
// arithmetic crosses the language boundary.
//
// The order matters and is the pattern the tools' own descriptions teach: take
// the next index BEFORE acting, act, then read from that index -- so what comes
// back is exactly what the action produced. If the two implementations disagreed
// about whether an index is inclusive, this would return the wrong lines rather
// than an error, which is precisely the class of bug a shared binding could
// never surface.
func exerciseSpeech(t *testing.T, harness *testsupport.MCPHarness) {
	t.Helper()

	var before struct {
		Index int `json:"index"`
	}
	harness.Call(t, "get_next_speech_index", nil).Decode(t, &before)

	harness.Call(t, "press_gesture", map[string]any{"gestures": []string{scriptedKey}})

	var waited struct {
		Found bool   `json:"found"`
		Index int    `json:"index"`
		Text  string `json:"text"`
	}
	harness.Call(t, "wait_for_speech", map[string]any{
		"text":        secondLine,
		"after_index": before.Index,
		"timeout":     5,
	}).Decode(t, &waited)
	if !waited.Found {
		t.Fatalf("wait_for_speech did not find %q after index %d", secondLine, before.Index)
	}
	if waited.Index < before.Index {
		t.Errorf("wait_for_speech matched at index %d, before the index it was told to start at (%d)",
			waited.Index, before.Index)
	}

	var finished struct {
		Finished bool `json:"finished"`
	}
	harness.Call(t, "wait_for_speech_to_finish", map[string]any{"timeout": 5}).Decode(t, &finished)
	if !finished.Finished {
		t.Error("wait_for_speech_to_finish reported the reader still speaking")
	}

	var captured struct {
		Text      string `json:"text"`
		FromIndex int    `json:"fromIndex"`
		ToIndex   int    `json:"toIndex"`
	}
	harness.Call(t, "get_speech", map[string]any{"since_index": before.Index}).Decode(t, &captured)
	for _, line := range []string{firstLine, secondLine} {
		if !strings.Contains(captured.Text, line) {
			t.Errorf("get_speech since %d = %q, want it to contain %q",
				before.Index, captured.Text, line)
		}
	}
	if captured.FromIndex != before.Index {
		t.Errorf("fromIndex = %d, want the index asked for (%d)", captured.FromIndex, before.Index)
	}
	if captured.ToIndex <= captured.FromIndex {
		t.Errorf("range [%d, %d) covers nothing, but two lines were spoken",
			captured.FromIndex, captured.ToIndex)
	}

	var last struct {
		Text  string `json:"text"`
		Index int    `json:"index"`
	}
	harness.Call(t, "get_last_speech", nil).Decode(t, &last)
	if !strings.Contains(last.Text, secondLine) {
		t.Errorf("get_last_speech = %q, want the last line spoken, %q", last.Text, secondLine)
	}
}

// exerciseBraille is the `braille` capability group. Braille has its own index
// space, so it is a separate crossing and not a variation on speech.
func exerciseBraille(t *testing.T, harness *testsupport.MCPHarness) {
	t.Helper()

	var captured struct {
		Text      string `json:"text"`
		FromIndex int    `json:"fromIndex"`
		ToIndex   int    `json:"toIndex"`
	}
	harness.Call(t, "get_braille", map[string]any{"since_index": 0}).Decode(t, &captured)

	if !strings.Contains(captured.Text, brailleCells) {
		t.Errorf("get_braille = %q, want it to contain %q", captured.Text, brailleCells)
	}
	if captured.ToIndex <= 0 {
		t.Errorf("braille range [%d, %d) covers nothing, but the display had content",
			captured.FromIndex, captured.ToIndex)
	}
}

// assertStatusIsProvenOnTheWire: `status` makes a real `ping` round trip while a
// session is live, so a true answer here is the real bridge answering, not this
// server remembering.
func assertStatusIsProvenOnTheWire(t *testing.T, harness *testsupport.MCPHarness) {
	t.Helper()

	var status struct {
		State string `json:"state"`
		Live  *bool  `json:"live"`
	}
	harness.Call(t, "status", nil).Decode(t, &status)

	if status.State != "connected" {
		t.Errorf("status state = %q, want connected", status.State)
	}
	if status.Live == nil || !*status.Live {
		t.Errorf("live = %v, want a ping the real bridge answered", status.Live)
	}
}

// assertInfoDescribesTheSession reads screenreader://info, the other surface the
// handshake's values reach an agent through.
func assertInfoDescribesTheSession(t *testing.T, harness *testsupport.MCPHarness, session connectedSession) {
	t.Helper()

	info := harness.ReadInfo(t)
	if info["reader"] != session.Reader {
		t.Errorf("info reader = %v, want %q", info["reader"], session.Reader)
	}
	if info["readerVersion"] != session.ReaderVersion {
		t.Errorf("info readerVersion = %v, want %q", info["readerVersion"], session.ReaderVersion)
	}
	// The protocol version the BRIDGE reported, which is the one field whose
	// disagreement would have failed the handshake outright.
	if version, ok := info["protocolVersion"].(float64); !ok || version <= 0 {
		t.Errorf("info protocolVersion = %v, want the version the bridge reported", info["protocolVersion"])
	}
}

// assertAdvertises checks tools/list holds everything in `want` and nothing in
// `absent`.
func assertAdvertises(t *testing.T, harness *testsupport.MCPHarness, want, absent []string) {
	t.Helper()

	advertised := harness.ToolNames(t)
	for _, name := range want {
		if !slices.Contains(advertised, name) {
			t.Errorf("tools/list = %v, want it to advertise %q", advertised, name)
		}
	}
	for _, name := range absent {
		if slices.Contains(advertised, name) {
			t.Errorf("tools/list advertises %q, which the reader's capabilities do not permit", name)
		}
	}
}
