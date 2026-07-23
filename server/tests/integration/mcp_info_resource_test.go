//go:build integration

// screenreader-mcp tests -- screenreader://info, over MCP.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: integration scenario. The resource is spec 0013's second capability
// mechanism -- SURFACE THE READER -- so what matters is that an agent reading it
// learns which reader it is driving and what that reader announced, at both ends
// of the connection lifecycle.
package integration_test

import (
	"testing"

	"github.com/marlon-sousa/screen-readers-mcp/server/adapters/wire"
	"github.com/marlon-sousa/screen-readers-mcp/server/testsupport"
)

// With nothing connected the resource still exists and says so: "nothing, and
// here is why" is an answer, and a missing resource is not.
func TestTheInfoResourceExistsBeforeAnythingIsConnected(t *testing.T) {
	h := testsupport.StartMCP(t, testsupport.BridgeOptions{})

	document := h.ReadInfo(t)

	if document["state"] != "disconnected" {
		t.Errorf("state = %v, want disconnected", document["state"])
	}
	if _, present := document["reader"]; present {
		t.Errorf("reader = %v, want absent when nothing is connected", document["reader"])
	}
}

// Acceptance criterion 5's second half.
func TestTheInfoResourceReportsTheConnectedReader(t *testing.T) {
	h := testsupport.StartMCP(t, testsupport.BridgeOptions{
		Reader: wire.ReaderInfo{Name: "nvda", Version: "2026.1"},
		Synth:  "espeak",
	})
	if got := h.Connect(t); got.IsError {
		t.Fatalf("connect_reader: %s", got.Text)
	}

	document := h.ReadInfo(t)

	if document["state"] != "connected" {
		t.Errorf("state = %v, want connected", document["state"])
	}
	if document["reader"] != "nvda" {
		t.Errorf("reader = %v, want nvda -- this is what lets the agent apply "+
			"what it already knows about the reader", document["reader"])
	}
	if document["readerVersion"] != "2026.1" {
		t.Errorf("readerVersion = %v, want 2026.1", document["readerVersion"])
	}
	if document["mode"] != "silent" {
		t.Errorf("mode = %v, want the capture mode in effect", document["mode"])
	}
	if document["synth"] != "espeak" {
		t.Errorf("synth = %v, want the reader's synthesizer", document["synth"])
	}

	capabilities, ok := document["capabilities"].([]any)
	if !ok || len(capabilities) == 0 {
		t.Fatalf("capabilities = %v, want what the reader announced", document["capabilities"])
	}

	// Both session artifacts are reported as PATHS. Their contents are
	// deliberately not exposed as resources in v1.
	if document["logPath"] == nil || document["readerLogPath"] == nil {
		t.Errorf("log paths = %v / %v, want both",
			document["logPath"], document["readerLogPath"])
	}
	if document["protocolVersion"] == nil {
		t.Error("protocolVersion is missing")
	}
}

// A reader that announced less is described honestly, without this server
// inventing capabilities on its behalf.
func TestTheInfoResourceReportsOnlyWhatTheReaderAnnounced(t *testing.T) {
	h := testsupport.StartMCP(t, testsupport.BridgeOptions{
		Capabilities: []wire.Capability{wire.CapabilitySpeech},
	})
	if got := h.Connect(t); got.IsError {
		t.Fatalf("connect_reader: %s", got.Text)
	}

	document := h.ReadInfo(t)

	capabilities, _ := document["capabilities"].([]any)
	if len(capabilities) != 1 || capabilities[0] != "speech" {
		t.Errorf("capabilities = %v, want exactly what hello announced", capabilities)
	}
}

// After a disconnect it goes back to describing nothing, rather than leaving a
// stale reader behind for the agent to trust.
func TestTheInfoResourceForgetsTheReaderOnDisconnect(t *testing.T) {
	h := testsupport.StartMCP(t, testsupport.BridgeOptions{})
	if got := h.Connect(t); got.IsError {
		t.Fatalf("connect_reader: %s", got.Text)
	}
	if got := h.Call(t, "disconnect_reader", nil); got.IsError {
		t.Fatalf("disconnect_reader: %s", got.Text)
	}

	document := h.ReadInfo(t)

	if document["state"] != "disconnected" {
		t.Errorf("state = %v, want disconnected", document["state"])
	}
	if _, present := document["reader"]; present {
		t.Errorf("reader = %v, want the reader forgotten", document["reader"])
	}
}
