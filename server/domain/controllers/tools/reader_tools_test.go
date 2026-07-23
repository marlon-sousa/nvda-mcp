// screenreader-mcp domain -- the braille, gesture, focus, state and config
// tools' tests.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// Grouped like their speech siblings, and for the same reason: each of these is
// a thin controller over one port, and what is worth asserting is the group's
// shared property -- that reader vocabulary passes through OPAQUELY, and that
// the gate refuses when the capability was not announced. Split per file, the
// opacity argument would be five near-identical tests with the point lost
// between them.
package tools_test

import (
	"errors"
	"testing"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/controllers/tools"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
	"github.com/marlon-sousa/screen-readers-mcp/server/testsupport"
)

// asCapabilityError is errors.As with the awkwardness in one place. Shared with
// speech_tools_test.go.
func asCapabilityError(err error, into **tools.CapabilityError) bool {
	return errors.As(err, into)
}

func TestGetBrailleReturnsAHalfOpenWindow(t *testing.T) {
	built := testsupport.NewConnection("nvda", entities.CapabilityBraille)
	call := testsupport.NewToolCall(&tools.GetBraille{}).WithConnection(built.Connection)
	built.Braille.Braille("edt blnk", "docs lst")

	var window struct {
		Text      string `json:"text"`
		FromIndex int    `json:"fromIndex"`
		ToIndex   int    `json:"toIndex"`
	}
	result, err := call.Run(`{"since_index":1}`)
	if err != nil {
		t.Fatalf("get_braille: %v", err)
	}
	decode(t, result, &window)

	if window.Text != "docs lst" {
		t.Errorf("text = %q, want only what was brailled since index 1", window.Text)
	}
	if window.FromIndex != 1 || window.ToIndex != 2 {
		t.Errorf("range = [%d,%d), want [1,2)", window.FromIndex, window.ToIndex)
	}
}

// Gesture ids are the READER's syntax and this server routes them without
// interpreting them -- which is what keeps the chassis reader-agnostic.
func TestPressGesturePassesOpaqueIdsThroughInOrder(t *testing.T) {
	built := testsupport.NewConnection("nvda", entities.CapabilityGestures)
	call := testsupport.NewToolCall(&tools.PressGesture{}).WithConnection(built.Connection)

	var pressed struct {
		Pressed []string `json:"pressed"`
	}
	result, err := call.Run(`{"gestures":["kb:NVDA+control+f7","kb:downArrow"]}`)
	if err != nil {
		t.Fatalf("press_gesture: %v", err)
	}
	decode(t, result, &pressed)

	sent := built.Gestures.Pressed()
	if len(sent) != 1 || len(sent[0]) != 2 {
		t.Fatalf("pressed %v, want one call with both ids", sent)
	}
	if sent[0][0] != "kb:NVDA+control+f7" || sent[0][1] != "kb:downArrow" {
		t.Errorf("pressed %v, want the ids unchanged and in order", sent[0])
	}
	if len(pressed.Pressed) != 2 {
		t.Errorf("result = %v, want the pressed ids echoed", pressed.Pressed)
	}
}

func TestPressGestureRefusesAnEmptyList(t *testing.T) {
	built := testsupport.NewConnection("nvda", entities.CapabilityGestures)
	call := testsupport.NewToolCall(&tools.PressGesture{}).WithConnection(built.Connection)

	if _, err := call.Run(`{"gestures":[]}`); err == nil {
		t.Error("pressing an empty gesture list was accepted")
	}
	if len(built.Gestures.Pressed()) != 0 {
		t.Error("an empty list reached the reader")
	}
}

// A reader that rejects an id reports it, and the tool does not dress that up as
// success.
func TestPressGestureReportsARejectedId(t *testing.T) {
	built := testsupport.NewConnection("nvda", entities.CapabilityGestures)
	call := testsupport.NewToolCall(&tools.PressGesture{}).WithConnection(built.Connection)
	built.Gestures.FailWith(errors.New("bridge refused pressGesture: unknown gesture id"))

	if _, err := call.Run(`{"gestures":["kb:NVDA+nonsense"]}`); err == nil {
		t.Error("a rejected gesture was reported as success")
	}
}

// Role and state strings are the reader's own vocabulary; the pointers preserve
// the wire's distinction between "no value" and "the empty string".
func TestGetFocusInfoPassesReaderVocabularyThrough(t *testing.T) {
	built := testsupport.NewConnection("nvda", entities.CapabilityFocus)
	call := testsupport.NewToolCall(&tools.GetFocusInfo{}).WithConnection(built.Connection)

	value := ""
	appModule := "notepad"
	built.Focus.SetFocus(ports.FocusInfo{
		Name:      "Text editor",
		Role:      "editableText",
		States:    []string{"focusable", "focused", "multiLine"},
		Value:     &value,
		AppModule: &appModule,
	})

	var focus struct {
		Name      string   `json:"name"`
		Role      string   `json:"role"`
		States    []string `json:"states"`
		Value     *string  `json:"value"`
		AppModule *string  `json:"appModule"`
	}
	result, err := call.Run("")
	if err != nil {
		t.Fatalf("get_focus_info: %v", err)
	}
	decode(t, result, &focus)

	if focus.Role != "editableText" || len(focus.States) != 3 {
		t.Errorf("focus = %+v, want the reader's own role and states unchanged", focus)
	}
	// The empty string is a VALUE and must survive as one, distinct from null.
	if focus.Value == nil || *focus.Value != "" {
		t.Errorf("value = %v, want the empty string preserved rather than nulled", focus.Value)
	}
	if focus.AppModule == nil || *focus.AppModule != "notepad" {
		t.Errorf("appModule = %v, want notepad", focus.AppModule)
	}
}

// A focus object with no states reports an empty list rather than null, so an
// agent can iterate without a special case.
func TestGetFocusInfoReportsNoStatesAsAnEmptyList(t *testing.T) {
	built := testsupport.NewConnection("nvda", entities.CapabilityFocus)
	call := testsupport.NewToolCall(&tools.GetFocusInfo{}).WithConnection(built.Connection)
	built.Focus.SetFocus(ports.FocusInfo{Name: "Pane", Role: "pane"})

	var focus struct {
		States *[]string `json:"states"`
	}
	result, err := call.Run("")
	if err != nil {
		t.Fatalf("get_focus_info: %v", err)
	}
	decode(t, result, &focus)

	if focus.States == nil {
		t.Fatal("states = null, want an empty list")
	}
	if len(*focus.States) != 0 {
		t.Errorf("states = %v, want empty", *focus.States)
	}
}

// The use case this capability exists for: some actions are signalled by a beep,
// so a test diffs two state snapshots across a gesture.
func TestGetStateSnapshotsCanBeDiffedAcrossAnAction(t *testing.T) {
	built := testsupport.NewConnection("nvda", entities.CapabilityState)
	call := testsupport.NewToolCall(&tools.GetState{}).WithConnection(built.Connection)

	browse := "browse"
	built.State.SetState(ports.ReaderState{BrowseMode: &browse, SpeechMode: "talk"})

	var before struct {
		BrowseMode *string `json:"browseMode"`
	}
	result, err := call.Run("")
	if err != nil {
		t.Fatalf("get_state: %v", err)
	}
	decode(t, result, &before)

	focus := "focus"
	built.State.SetState(ports.ReaderState{BrowseMode: &focus, SpeechMode: "talk"})

	var after struct {
		BrowseMode *string `json:"browseMode"`
	}
	result, err = call.Run("")
	if err != nil {
		t.Fatalf("get_state: %v", err)
	}
	decode(t, result, &after)

	if before.BrowseMode == nil || after.BrowseMode == nil {
		t.Fatalf("browseMode = %v then %v, want both reported", before.BrowseMode, after.BrowseMode)
	}
	if *before.BrowseMode == *after.BrowseMode {
		t.Error("the two snapshots are identical; the toggle would be invisible")
	}
}

// A reader with no such concept reports null, which is a different answer from
// "a mode whose name is empty".
func TestGetStateReportsAnAbsentBrowseModeAsNull(t *testing.T) {
	built := testsupport.NewConnection("jaws", entities.CapabilityState)
	call := testsupport.NewToolCall(&tools.GetState{}).WithConnection(built.Connection)
	built.State.SetState(ports.ReaderState{SpeechMode: "talk"})

	var state struct {
		BrowseMode *string `json:"browseMode"`
	}
	result, err := call.Run("")
	if err != nil {
		t.Fatalf("get_state: %v", err)
	}
	decode(t, result, &state)

	if state.BrowseMode != nil {
		t.Errorf("browseMode = %q, want null for a reader with no such mode", *state.BrowseMode)
	}
}

// Config values are opaque JSON and must round-trip byte for byte: this server
// never decides what type a reader's setting is.
func TestConfigValuesRoundTripAsOpaqueJSON(t *testing.T) {
	built := testsupport.NewConnection("nvda", entities.CapabilityConfig)
	built.Config.Put([]string{"speech", "symbolLevel"}, "100")

	read := testsupport.NewToolCall(&tools.GetConfig{}).WithConnection(built.Connection)
	var got struct {
		Value any `json:"value"`
	}
	result, err := read.Run(`{"key_path":["speech","symbolLevel"]}`)
	if err != nil {
		t.Fatalf("get_config: %v", err)
	}
	decode(t, result, &got)
	if got.Value != float64(100) {
		t.Errorf("value = %v, want the reader's own 100", got.Value)
	}

	// A write returns what the reader NOW holds, which is not always what was
	// sent -- so the assertion is on reading it back, not on the echo.
	write := testsupport.NewToolCall(&tools.SetConfig{}).WithConnection(built.Connection)
	if _, err := write.Run(`{"key_path":["speech","symbolLevel"],"value":{"nested":[1,2]}}`); err != nil {
		t.Fatalf("set_config: %v", err)
	}
	result, err = read.Run(`{"key_path":["speech","symbolLevel"]}`)
	if err != nil {
		t.Fatalf("get_config: %v", err)
	}
	var complex struct {
		Value map[string]any `json:"value"`
	}
	decode(t, result, &complex)
	if len(complex.Value["nested"].([]any)) != 2 {
		t.Errorf("value = %v, want the structure preserved exactly", complex.Value)
	}
}

func TestConfigToolsRequireAKeyPath(t *testing.T) {
	built := testsupport.NewConnection("nvda", entities.CapabilityConfig)

	read := testsupport.NewToolCall(&tools.GetConfig{}).WithConnection(built.Connection)
	if _, err := read.Run(`{"key_path":[]}`); err == nil {
		t.Error("get_config accepted an empty key path")
	}

	write := testsupport.NewToolCall(&tools.SetConfig{}).WithConnection(built.Connection)
	if _, err := write.Run(`{"value":1}`); err == nil {
		t.Error("set_config accepted a call with no key path")
	}
}

// An ABSENT value is a malformed call; an explicit JSON null is a value a reader
// may legitimately be asked to store. Writing null in place of the first would
// be this server guessing.
func TestSetConfigDistinguishesAnAbsentValueFromAnExplicitNull(t *testing.T) {
	built := testsupport.NewConnection("nvda", entities.CapabilityConfig)
	call := testsupport.NewToolCall(&tools.SetConfig{}).WithConnection(built.Connection)

	if _, err := call.Run(`{"key_path":["speech","rate"]}`); err == nil {
		t.Error("set_config accepted a call with no value")
	}
	if _, err := call.Run(`{"key_path":["speech","rate"],"value":null}`); err != nil {
		t.Errorf("set_config refused an explicit null: %v", err)
	}
}

// The gate, for every remaining tool: the capability it names is the one the
// error reports, so an agent is told exactly what the reader is missing.
func TestEveryGatedToolNamesTheCapabilityItNeeds(t *testing.T) {
	// A reader that announced nothing at all.
	built := testsupport.NewConnection("nvda")

	gated := []struct {
		tool       tools.Tool
		capability entities.Capability
	}{
		{&tools.GetBraille{}, entities.CapabilityBraille},
		{&tools.PressGesture{}, entities.CapabilityGestures},
		{&tools.GetFocusInfo{}, entities.CapabilityFocus},
		{&tools.GetState{}, entities.CapabilityState},
		{&tools.GetConfig{}, entities.CapabilityConfig},
		{&tools.SetConfig{}, entities.CapabilityConfig},
	}
	for _, gate := range gated {
		t.Run(gate.tool.Name(), func(t *testing.T) {
			call := testsupport.NewToolCall(gate.tool).WithConnection(built.Connection)

			_, err := call.Run(`{"since_index":0,"gestures":["x"],"key_path":["a"],"value":1}`)
			if err == nil {
				t.Fatal("the tool ran for a reader that announced nothing")
			}
			var capability *tools.CapabilityError
			if !asCapabilityError(err, &capability) {
				t.Fatalf("error = %v, want a *CapabilityError", err)
			}
			if capability.Capability != gate.capability {
				t.Errorf("capability = %q, want %q", capability.Capability, gate.capability)
			}
			if capability.Reader != "nvda" {
				t.Errorf("reader = %q, want the connected reader named", capability.Reader)
			}
		})
	}
}

// The capability check comes FIRST, before the arguments are even read: a tool
// the reader cannot serve should say so, not complain about a parameter.
func TestTheCapabilityCheckPrecedesArgumentValidation(t *testing.T) {
	built := testsupport.NewConnection("nvda", entities.CapabilitySpeech)
	call := testsupport.NewToolCall(&tools.PressGesture{}).WithConnection(built.Connection)

	_, err := call.Run(`{"gestures":[]}`)

	var capability *tools.CapabilityError
	if !asCapabilityError(err, &capability) {
		t.Fatalf("error = %v, want the capability error rather than the argument one", err)
	}
}
