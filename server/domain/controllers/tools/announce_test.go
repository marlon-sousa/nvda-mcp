// screenreader-mcp domain -- the announce tool's tests.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// Its own file rather than a sixth case in reader_tools_test.go: those are
// grouped around one shared property (reader vocabulary passes through
// opaquely), and this tool has a different subject entirely -- it addresses a
// human, and the thing worth protecting is that nothing but real text ever
// reaches them.
package tools_test

import (
	"errors"
	"testing"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/controllers/tools"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/testsupport"
)

func TestAnnounceSpeaksTheTextAndEchoesIt(t *testing.T) {
	built := testsupport.NewConnection("nvda", entities.CapabilityAnnounce)
	call := testsupport.NewToolCall(&tools.Announce{}).WithConnection(built.Connection)

	var spoken struct {
		Announced string `json:"announced"`
	}
	result, err := call.Run(`{"text":"I am stuck on a password field."}`)
	if err != nil {
		t.Fatalf("announce: %v", err)
	}
	decode(t, result, &spoken)

	said := built.Announcer.Announced()
	if len(said) != 1 || said[0] != "I am stuck on a password field." {
		t.Errorf("announced %v, want the text unchanged", said)
	}
	if spoken.Announced != "I am stuck on a password field." {
		t.Errorf("result = %q, want the text echoed", spoken.Announced)
	}
}

// An empty announcement is two cue beeps and then silence, which a tester reads
// as the one channel they are relying on having broken. It must not reach them.
func TestAnnounceRefusesEmptyAndWhitespaceText(t *testing.T) {
	for _, params := range []string{`{"text":""}`, `{"text":"   "}`, `{"text":"\n\t"}`} {
		built := testsupport.NewConnection("nvda", entities.CapabilityAnnounce)
		call := testsupport.NewToolCall(&tools.Announce{}).WithConnection(built.Connection)

		if _, err := call.Run(params); err == nil {
			t.Errorf("announce(%s) was accepted", params)
		}
		if said := built.Announcer.Announced(); len(said) != 0 {
			t.Errorf("announce(%s) reached the reader as %v", params, said)
		}
	}
}

// The gate, structurally: a bridge that cannot speak to a human never announces
// the capability, so the port was never handed over.
func TestAnnounceIsRefusedWhenTheReaderDidNotAnnounceIt(t *testing.T) {
	built := testsupport.NewConnection("nvda", entities.CapabilitySpeech)
	call := testsupport.NewToolCall(&tools.Announce{}).WithConnection(built.Connection)

	_, err := call.Run(`{"text":"hello"}`)

	var capability *tools.CapabilityError
	if !asCapabilityError(err, &capability) {
		t.Fatalf("announce = %v, want a *CapabilityError", err)
	}
	if capability.Capability != entities.CapabilityAnnounce {
		t.Errorf("Capability = %q, want announce", capability.Capability)
	}
	if capability.Reader != "nvda" {
		t.Errorf("Reader = %q, want the connected reader named", capability.Reader)
	}
}

func TestAnnounceWithNothingConnectedSaysToConnectFirst(t *testing.T) {
	call := testsupport.NewToolCall(&tools.Announce{})

	_, err := call.Run(`{"text":"hello"}`)

	var capability *tools.CapabilityError
	if !asCapabilityError(err, &capability) {
		t.Fatalf("announce = %v, want a *CapabilityError", err)
	}
	if capability.Reader != "" {
		t.Errorf("Reader = %q, want empty when nothing is connected", capability.Reader)
	}
}

// A bridge whose synth had gone would fail the command; the session survives it
// (protocol.md §3), so the tool must surface the error rather than swallow it.
func TestAnnounceSurfacesABridgeFailure(t *testing.T) {
	built := testsupport.NewConnection("nvda", entities.CapabilityAnnounce)
	call := testsupport.NewToolCall(&tools.Announce{}).WithConnection(built.Connection)
	built.Announcer.FailWith(errors.New("no synth loaded"))

	if _, err := call.Run(`{"text":"hello"}`); err == nil {
		t.Error("a failing announcement was reported as success")
	}
}
