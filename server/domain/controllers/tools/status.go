// screenreader-mcp domain -- the status tool.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: controller, one per tool. UNGATED.
// USES: ConnectionControl.Status, .Current and .Verify, via ToolContext.
// LISTED BY: registry.go.
//
// WHEN A SESSION IS LIVE THIS MAKES A REAL `ping` ROUND TRIP, so the answer is
// proof rather than possibly-stale local state. Two things make that worth the
// round trip. A bridge can die without this server noticing, since it only finds
// out when it next speaks. And an idle agent LOSES ITS SESSION BY DESIGN: the
// bridge's command-inactivity watchdog is deliberately not reset by `ping`
// (protocol.md §6), so a keepalive cannot mask an abandoned session -- which
// means "am I still connected?" is a question this server genuinely cannot
// answer from memory.
//
// This is also why `ping` is not a tool of its own: what an agent wants from it
// is "is this connection real right now?", which is exactly this answer.
package tools

import (
	"encoding/json"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
)

// Status reports the connection.
type Status struct{}

var _ Tool = (*Status)(nil)

func (t *Status) Name() string { return "status" }

func (t *Status) Capability() entities.Capability { return "" }

func (t *Status) Description() string {
	return "Report the screen reader connection: its state, why it is in that " +
		"state, and the current session if there is one. When a session is live " +
		"this makes a real round trip to the reader, so the answer is proof rather " +
		"than a cached guess -- an idle session can be dropped by the reader's own " +
		"inactivity watchdog. Takes no parameters."
}

func (t *Status) InputSchema() json.RawMessage {
	return json.RawMessage(`{"type":"object","properties":{},"additionalProperties":false}`)
}

// statusSession is the live session as the agent sees it.
type statusSession struct {
	Reader        string   `json:"reader"`
	ReaderVersion string   `json:"readerVersion"`
	Endpoint      string   `json:"endpoint"`
	Capabilities  []string `json:"capabilities"`
	Mode          string   `json:"mode"`
	Synth         string   `json:"synth"`
	LogPath       string   `json:"logPath"`
	ReaderLogPath string   `json:"readerLogPath"`
	ProtocolVer   int      `json:"protocolVersion"`
}

type statusResult struct {
	State  string `json:"state"`
	Reason string `json:"reason,omitempty"`

	// Live is the outcome of the round trip: true when the reader answered,
	// false when it did not, and absent when there was no session to ask.
	Live *bool `json:"live,omitempty"`

	// LiveError is why the round trip failed, when it did.
	LiveError string `json:"liveError,omitempty"`

	Session *statusSession `json:"session,omitempty"`
}

func (t *Status) Execute(ctx ToolContext, _ json.RawMessage) (any, error) {
	// Verify FIRST: it re-checks the wire and records a loss it finds, so the
	// state read afterwards is the corrected one rather than the one this
	// process happened to be holding. Its error is reported, not returned --
	// "the connection is gone" is the answer status was asked for, not a
	// failure of the tool.
	var (
		live      *bool
		liveError string
	)
	if ctx.Connection != nil {
		err := ctx.Control.Verify()
		answered := err == nil
		live = &answered
		if err != nil {
			liveError = err.Error()
		}
	}

	recorded := ctx.Control.Status()
	result := statusResult{
		State:     recorded.State.String(),
		Reason:    recorded.Reason,
		Live:      live,
		LiveError: liveError,
	}

	// Re-read the connection AFTER Verify: if the round trip discovered a
	// loss, there is no session left to describe.
	if connection := ctx.Control.Current(); connection != nil {
		session := connection.Session
		result.Session = &statusSession{
			Reader:        session.Reader.Name,
			ReaderVersion: session.Reader.Version,
			Endpoint:      connection.Endpoint.String(),
			Capabilities:  session.Capabilities.Strings(),
			Mode:          session.Mode.String(),
			Synth:         session.Synth,
			LogPath:       session.LogPath,
			ReaderLogPath: session.ReaderLogPath,
			ProtocolVer:   session.ProtocolVersion,
		}
	}
	return result, nil
}
