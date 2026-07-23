// screenreader-mcp domain -- the status tool's tests.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// The point of these is the round trip. `status` must answer with what the WIRE
// says rather than with what this process remembers, because a bridge can die
// unnoticed and because an idle agent loses its session by design (protocol.md
// §6). A status that reported cached state would be confidently wrong exactly
// when it mattered.
package tools_test

import (
	"encoding/json"
	"errors"
	"testing"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/controllers/tools"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
	"github.com/marlon-sousa/screen-readers-mcp/server/testsupport"
)

type statusAnswer struct {
	State     string `json:"state"`
	Reason    string `json:"reason"`
	Live      *bool  `json:"live"`
	LiveError string `json:"liveError"`
	Session   *struct {
		Reader        string   `json:"reader"`
		Endpoint      string   `json:"endpoint"`
		Capabilities  []string `json:"capabilities"`
		Mode          string   `json:"mode"`
		LogPath       string   `json:"logPath"`
		ReaderLogPath string   `json:"readerLogPath"`
	} `json:"session"`
}

func runStatus(t *testing.T, call *testsupport.ToolCall) statusAnswer {
	t.Helper()
	result, err := call.Run("")
	if err != nil {
		t.Fatalf("status: %v", err)
	}
	encoded, _ := json.Marshal(result)
	var answer statusAnswer
	if err := json.Unmarshal(encoded, &answer); err != nil {
		t.Fatalf("decoding the result: %v", err)
	}
	return answer
}

// Acceptance criterion 3: a fresh server says Disconnected and has dialed
// nothing.
func TestAFreshServerReportsDisconnectedAndDialedNothing(t *testing.T) {
	call := testsupport.NewToolCall(&tools.Status{})

	answer := runStatus(t, call)

	if answer.State != "disconnected" {
		t.Errorf("state = %q, want disconnected", answer.State)
	}
	if answer.Session != nil {
		t.Errorf("session = %+v, want none", answer.Session)
	}
	if len(call.Control.Connects()) != 0 {
		t.Error("status dialed something")
	}
}

// With no session there is nothing to ping, so `live` is absent rather than
// false: "there is no connection" and "the connection did not answer" are
// different answers.
func TestWithNoSessionThereIsNoRoundTripToReport(t *testing.T) {
	call := testsupport.NewToolCall(&tools.Status{})

	answer := runStatus(t, call)

	if answer.Live != nil {
		t.Errorf("live = %v, want absent when there is no session", *answer.Live)
	}
	if call.Control.Verifies() != 0 {
		t.Error("status pinged with no session to ping")
	}
}

func TestALiveSessionIsProvedByARealRoundTrip(t *testing.T) {
	call := testsupport.NewToolCall(&tools.Status{})
	built := testsupport.NewConnection("nvda", testsupport.EveryCapability()...)
	call.WithConnection(built.Connection)
	call.Control.SetStatus(entities.ConnectionStatus{State: entities.Connected})

	answer := runStatus(t, call)

	if call.Control.Verifies() != 1 {
		t.Errorf("Verify called %d times, want once -- the answer must be proof, "+
			"not possibly-stale local state", call.Control.Verifies())
	}
	if answer.Live == nil || !*answer.Live {
		t.Errorf("live = %v, want true", answer.Live)
	}
	if answer.State != "connected" {
		t.Errorf("state = %q, want connected", answer.State)
	}
	if answer.Session == nil {
		t.Fatal("session = nil, want the live session described")
	}
	if answer.Session.Reader != "nvda" || answer.Session.Endpoint != "pipe:nvdaMcpBridge" {
		t.Errorf("session = %+v, want the reader and endpoint that answered", *answer.Session)
	}
	if len(answer.Session.Capabilities) != 6 {
		t.Errorf("capabilities = %v, want all six", answer.Session.Capabilities)
	}
	if answer.Session.LogPath == "" || answer.Session.ReaderLogPath == "" {
		t.Error("both session log paths must be reported")
	}
}

// The case the round trip exists for: this process still believes it has a
// session, and the wire disagrees. The tool must report the truth rather than
// the belief -- and must not fail, because "the connection is gone" is the
// answer status was asked for.
func TestARoundTripThatFailsReportsTheLossRatherThanFailing(t *testing.T) {
	call := testsupport.NewToolCall(&tools.Status{})
	built := testsupport.NewConnection("nvda", testsupport.EveryCapability()...)
	call.WithConnection(built.Connection)
	call.Control.SetStatus(entities.ConnectionStatus{State: entities.Connected})
	call.Control.FailVerifyWith(ports.ErrConnectionLost)

	answer := runStatus(t, call)

	if answer.Live == nil || *answer.Live {
		t.Errorf("live = %v, want false", answer.Live)
	}
	if answer.LiveError == "" {
		t.Error("liveError is empty; the agent needs to know why the round trip failed")
	}
	// Verify records the loss, so the state read AFTERWARDS is the corrected
	// one and there is no session left to describe.
	if answer.State != "disconnected" {
		t.Errorf("state = %q, want the state Verify corrected it to", answer.State)
	}
	if answer.Session != nil {
		t.Errorf("session = %+v, want none once the loss was recorded", *answer.Session)
	}
}

// A protocol mismatch keeps the process up and `status` keeps saying why
// (acceptance criterion 8). Nothing is connected, so there is no round trip --
// the reason is the whole answer.
func TestAnIncompatibleBridgeKeepsBeingReported(t *testing.T) {
	call := testsupport.NewToolCall(&tools.Status{})
	mismatch := &ports.ProtocolMismatchError{BridgeVersion: 2, ServerVersions: []int{1}}
	call.Control.SetStatus(entities.ConnectionStatus{
		State: entities.Incompatible, Reason: mismatch.Error(),
	})

	answer := runStatus(t, call)

	if answer.State != "incompatible" {
		t.Errorf("state = %q, want incompatible", answer.State)
	}
	if answer.Reason == "" {
		t.Error("reason is empty; status must keep saying why")
	}
}

func TestStatusTakesNoParameters(t *testing.T) {
	call := testsupport.NewToolCall(&tools.Status{})

	if _, err := call.Run(""); err != nil {
		t.Errorf("a call with no arguments failed: %v", err)
	}
}

// A refusal is not a loss: a bridge that ANSWERED, however unhappily, is still
// there, so the session survives and status says so.
func TestARefusedPingStillLeavesTheSessionDescribed(t *testing.T) {
	call := testsupport.NewToolCall(&tools.Status{})
	built := testsupport.NewConnection("nvda", entities.CapabilitySpeech)
	call.WithConnection(built.Connection)
	call.Control.SetStatus(entities.ConnectionStatus{State: entities.Connected})

	call.Control.FailVerifyWith(errors.New("bridge refused ping: busy"))

	answer := runStatus(t, call)
	if answer.Session == nil {
		t.Error("a refused ping ended the session; only a lost connection should")
	}
	if answer.Live == nil || *answer.Live {
		t.Errorf("live = %v, want false -- the round trip did not succeed", answer.Live)
	}
}
