// screenreader-mcp domain -- the five speech tools' tests.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ONE TEST FILE FOR FIVE TOOLS, deliberately, and it is the one place this
// package departs from "one test module per source module" (AGENTS.md). The
// reason is that these five are a single capability GROUP over a single port,
// and the properties worth asserting are properties of the group: the half-open
// index window that makes toIndex the next since_index, and the fact that "not
// found" is an answer rather than a failure. Splitting them five ways would
// scatter one argument across five files and make the shared index arithmetic
// look like five unrelated details.
package tools_test

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/controllers/tools"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/testsupport"
)

// speechCall wires one speech tool against a reader that announced `speech`,
// and returns the call plus the fake speech log behind it.
func speechCall(t *testing.T, tool tools.Tool) (*testsupport.ToolCall, *testsupport.Connection) {
	t.Helper()
	built := testsupport.NewConnection("nvda", entities.CapabilitySpeech)
	return testsupport.NewToolCall(tool).WithConnection(built.Connection), built
}

func decode(t *testing.T, value any, into any) {
	t.Helper()
	encoded, err := json.Marshal(value)
	if err != nil {
		t.Fatalf("marshalling the result: %v", err)
	}
	if err := json.Unmarshal(encoded, into); err != nil {
		t.Fatalf("decoding %s: %v", encoded, err)
	}
}

// The half-open window: [fromIndex, toIndex), so toIndex is exactly the
// since_index to pass next, with no overlap and no gap (protocol.md §7).
func TestGetSpeechReturnsAHalfOpenWindowThatChainsCleanly(t *testing.T) {
	call, built := speechCall(t, &tools.GetSpeech{})
	built.Speech.Speak("Edit  blank", "Documents  list")

	var first struct {
		Text      string `json:"text"`
		FromIndex int    `json:"fromIndex"`
		ToIndex   int    `json:"toIndex"`
	}
	result, err := call.Run(`{"since_index":0}`)
	if err != nil {
		t.Fatalf("get_speech: %v", err)
	}
	decode(t, result, &first)

	if first.FromIndex != 0 || first.ToIndex != 2 {
		t.Errorf("range = [%d,%d), want [0,2)", first.FromIndex, first.ToIndex)
	}
	if !strings.Contains(first.Text, "Edit") || !strings.Contains(first.Text, "Documents") {
		t.Errorf("text = %q, want both utterances", first.Text)
	}

	// Continuing from toIndex sees only what happened since.
	built.Speech.Speak("Button")
	var second struct {
		Text      string `json:"text"`
		FromIndex int    `json:"fromIndex"`
		ToIndex   int    `json:"toIndex"`
	}
	result, err = call.Run(`{"since_index":2}`)
	if err != nil {
		t.Fatalf("get_speech: %v", err)
	}
	decode(t, result, &second)

	if second.Text != "Button" {
		t.Errorf("text = %q, want only what was said after the first read", second.Text)
	}
	if second.FromIndex != 2 || second.ToIndex != 3 {
		t.Errorf("range = [%d,%d), want [2,3)", second.FromIndex, second.ToIndex)
	}
}

// The bookmark pattern the whole speech group is built around: note "now", act,
// read only what the action produced.
func TestGetNextSpeechIndexBookmarksNow(t *testing.T) {
	call, built := speechCall(t, &tools.GetNextSpeechIndex{})
	built.Speech.Speak("before one", "before two")

	var bookmark struct {
		Index int `json:"index"`
	}
	result, err := call.Run("")
	if err != nil {
		t.Fatalf("get_next_speech_index: %v", err)
	}
	decode(t, result, &bookmark)

	if bookmark.Index != 2 {
		t.Errorf("index = %d, want the index the NEXT utterance will take", bookmark.Index)
	}
}

func TestGetLastSpeechReturnsTheMostRecentUtterance(t *testing.T) {
	call, built := speechCall(t, &tools.GetLastSpeech{})
	built.Speech.Speak("first", "second", "third")

	var last struct {
		Text  string `json:"text"`
		Index int    `json:"index"`
	}
	result, err := call.Run("")
	if err != nil {
		t.Fatalf("get_last_speech: %v", err)
	}
	decode(t, result, &last)

	if last.Text != "third" || last.Index != 2 {
		t.Errorf("last = %q at %d, want \"third\" at 2", last.Text, last.Index)
	}
}

func TestWaitForSpeechReportsAMatch(t *testing.T) {
	call, built := speechCall(t, &tools.WaitForSpeech{})
	built.Speech.Speak("Edit  blank", "Save  button")

	var match struct {
		Found bool   `json:"found"`
		Index int    `json:"index"`
		Text  string `json:"text"`
	}
	result, err := call.Run(`{"text":"Save"}`)
	if err != nil {
		t.Fatalf("wait_for_speech: %v", err)
	}
	decode(t, result, &match)

	if !match.Found || match.Index != 1 {
		t.Errorf("match = %+v, want found at index 1", match)
	}
}

// NOT finding it is an ANSWER. This is also how an agent asserts that something
// was never announced, so an error here would make the negative case
// indistinguishable from a broken connection.
func TestWaitForSpeechReportsANonMatchWithoutFailing(t *testing.T) {
	call, built := speechCall(t, &tools.WaitForSpeech{})
	built.Speech.Speak("Edit  blank")

	var match struct {
		Found bool `json:"found"`
	}
	result, err := call.Run(`{"text":"never said"}`)
	if err != nil {
		t.Fatalf("wait_for_speech reported a non-match as a failure: %v", err)
	}
	decode(t, result, &match)

	if match.Found {
		t.Error("found = true for text that was never spoken")
	}
}

// after_index is a POINTER on the wire: "anywhere in what has been captured" is
// a different request from "at or after index 0", and this tool must not decide
// that on the agent's behalf.
func TestWaitForSpeechPassesAfterIndexThroughOnlyWhenGiven(t *testing.T) {
	call, built := speechCall(t, &tools.WaitForSpeech{})
	built.Speech.Speak("Edit  blank")

	if _, err := call.Run(`{"text":"Edit"}`); err != nil {
		t.Fatalf("wait_for_speech: %v", err)
	}
	if waits := built.Speech.Waits(); len(waits) != 1 || waits[0].AfterIndex != nil {
		t.Errorf("afterIndex = %v, want unset when the agent did not ask", waits[0].AfterIndex)
	}

	if _, err := call.Run(`{"text":"Edit","after_index":0}`); err != nil {
		t.Fatalf("wait_for_speech: %v", err)
	}
	waits := built.Speech.Waits()
	if len(waits) != 2 || waits[1].AfterIndex == nil || *waits[1].AfterIndex != 0 {
		t.Errorf("afterIndex = %v, want 0 passed through explicitly", waits[1].AfterIndex)
	}
}

// Waiting for the empty string matches the first thing said, which is never what
// anyone meant and would look like a working assertion.
func TestWaitForSpeechRefusesAnEmptyText(t *testing.T) {
	call, _ := speechCall(t, &tools.WaitForSpeech{})

	if _, err := call.Run(`{"text":""}`); err == nil {
		t.Error("waiting for the empty string was accepted")
	}
	if _, err := call.Run(""); err == nil {
		t.Error("waiting with no text at all was accepted")
	}
}

// A timeout is seconds on the wire and a Duration in the domain; omitting it
// means the reader's own default, which the contract owns.
func TestWaitTimeoutsAreSecondsAndOptional(t *testing.T) {
	call, built := speechCall(t, &tools.WaitForSpeech{})
	built.Speech.Speak("Edit")

	if _, err := call.Run(`{"text":"Edit","timeout":2.5}`); err != nil {
		t.Fatalf("wait_for_speech: %v", err)
	}
	waits := built.Speech.Waits()
	if waits[0].Timeout.Seconds() != 2.5 {
		t.Errorf("timeout = %s, want 2.5s", waits[0].Timeout)
	}

	if _, err := call.Run(`{"text":"Edit"}`); err != nil {
		t.Fatalf("wait_for_speech: %v", err)
	}
	if got := built.Speech.Waits()[1].Timeout; got != 0 {
		t.Errorf("timeout = %s, want zero so the reader applies its own default", got)
	}
}

func TestWaitForSpeechToFinishReportsWhetherSpeechSettled(t *testing.T) {
	call, built := speechCall(t, &tools.WaitForSpeechToFinish{})

	var answer struct {
		Finished bool `json:"finished"`
	}
	result, err := call.Run("")
	if err != nil {
		t.Fatalf("wait_for_speech_to_finish: %v", err)
	}
	decode(t, result, &answer)
	if !answer.Finished {
		t.Error("finished = false for a reader that has settled")
	}

	// Still speaking is an answer too, not a failure.
	built.Speech.SetFinished(false)
	result, err = call.Run(`{"timeout":1}`)
	if err != nil {
		t.Fatalf("wait_for_speech_to_finish: %v", err)
	}
	decode(t, result, &answer)
	if answer.Finished {
		t.Error("finished = true for a reader that was still speaking")
	}
}

// The gate, for all five: a reader that announced no speech hands over no
// SpeechReader, so every one of them refuses with the structured error.
func TestEverySpeechToolRefusesAReaderWithoutSpeech(t *testing.T) {
	built := testsupport.NewConnection("jaws", entities.CapabilityBraille)

	speechTools := []tools.Tool{
		&tools.GetSpeech{}, &tools.GetLastSpeech{}, &tools.GetNextSpeechIndex{},
		&tools.WaitForSpeech{}, &tools.WaitForSpeechToFinish{},
	}
	for _, tool := range speechTools {
		t.Run(tool.Name(), func(t *testing.T) {
			call := testsupport.NewToolCall(tool).WithConnection(built.Connection)

			_, err := call.Run(`{"since_index":0,"text":"anything"}`)
			if err == nil {
				t.Fatal("the tool ran for a reader with no speech capability")
			}
			var capability *tools.CapabilityError
			if !asCapabilityError(err, &capability) {
				t.Fatalf("error = %v, want a *CapabilityError", err)
			}
			if capability.Capability != entities.CapabilitySpeech {
				t.Errorf("capability = %q, want speech", capability.Capability)
			}
		})
	}
}
