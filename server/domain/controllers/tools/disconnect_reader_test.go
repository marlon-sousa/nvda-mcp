// screenreader-mcp domain -- the disconnect_reader tool's tests.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
package tools_test

import (
	"encoding/json"
	"testing"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/controllers/tools"
	"github.com/marlon-sousa/screen-readers-mcp/server/testsupport"
)

func TestDisconnectEndsTheLiveSession(t *testing.T) {
	call := testsupport.NewToolCall(&tools.DisconnectReader{})
	built := testsupport.NewConnection("nvda", testsupport.EveryCapability()...)
	call.WithConnection(built.Connection)

	result, err := call.Run("")
	if err != nil {
		t.Fatalf("disconnect_reader: %v", err)
	}
	if call.Control.Disconnects() != 1 {
		t.Errorf("Disconnect called %d times, want once", call.Control.Disconnects())
	}

	var got struct {
		Disconnected bool   `json:"disconnected"`
		Reader       string `json:"reader"`
	}
	encoded, _ := json.Marshal(result)
	if err := json.Unmarshal(encoded, &got); err != nil {
		t.Fatalf("decoding the result: %v", err)
	}
	if !got.Disconnected || got.Reader != "nvda" {
		t.Errorf("result = %+v, want the ended session named", got)
	}
}

// Not an error with nothing connected: teardown is reached from several
// directions and none of them should have to check first. But the answer still
// distinguishes the two cases, because "there was nothing to end" is a fact an
// agent may want.
func TestDisconnectingWithNoSessionIsNotAFailure(t *testing.T) {
	call := testsupport.NewToolCall(&tools.DisconnectReader{})

	result, err := call.Run("")
	if err != nil {
		t.Fatalf("disconnect_reader with no session: %v", err)
	}

	var got struct {
		Disconnected bool   `json:"disconnected"`
		Reader       string `json:"reader"`
	}
	encoded, _ := json.Marshal(result)
	if err := json.Unmarshal(encoded, &got); err != nil {
		t.Fatalf("decoding the result: %v", err)
	}
	if got.Disconnected {
		t.Error("claimed to have disconnected a session that was never there")
	}
	if got.Reader != "" {
		t.Errorf("reader = %q, want none named", got.Reader)
	}
}

func TestDisconnectTakesNoParameters(t *testing.T) {
	call := testsupport.NewToolCall(&tools.DisconnectReader{})

	if _, err := call.Run(""); err != nil {
		t.Errorf("a call with no arguments failed: %v", err)
	}
}
