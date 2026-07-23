// screenreader-mcp domain -- the wait_for_speech tool.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: controller, one per tool. GATED on `speech`.
// USES: ports.SpeechReader, through ToolContext.Speech().
// LISTED BY: registry.go.
//
// NOT FINDING THE TEXT IS AN ANSWER, NOT A FAILURE. The result carries `found`,
// and a timeout returns `found: false` rather than an error -- because "the
// reader never said that" is frequently exactly what a test is checking, and an
// error would make the negative case indistinguishable from a broken connection.
package tools

import (
	"encoding/json"
	"errors"
	"time"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// WaitForSpeech blocks until matching speech appears.
type WaitForSpeech struct{}

var _ Tool = (*WaitForSpeech)(nil)

func (t *WaitForSpeech) Name() string { return "wait_for_speech" }

func (t *WaitForSpeech) Capability() entities.Capability { return entities.CapabilitySpeech }

func (t *WaitForSpeech) Description() string {
	return "Wait until the screen reader speaks something containing the given text, " +
		"or until the timeout elapses. Returns found=true with the matching text and " +
		"its index, or found=false if it never appeared -- NOT finding it is a normal " +
		"answer, not an error, so this is also how you assert that something was not " +
		"announced. Prefer this over polling get_speech in a loop."
}

func (t *WaitForSpeech) InputSchema() json.RawMessage {
	return json.RawMessage(`{
	"type": "object",
	"properties": {
		"text": {
			"type": "string",
			"description": "The text to wait for. Matched as a substring of one utterance."
		},
		"after_index": {
			"type": "integer",
			"minimum": 0,
			"description": "Only consider utterances at or after this index. Pass the value from get_next_speech_index taken before your action, so speech from before it cannot match."
		},
		"timeout": {
			"type": "number",
			"exclusiveMinimum": 0,
			"description": "How long to wait, in seconds. Omit to use the reader's own default."
		}
	},
	"required": ["text"],
	"additionalProperties": false
}`)
}

type waitForSpeechParams struct {
	Text string `json:"text"`

	// A POINTER, because the wire distinguishes "anywhere in what has been
	// captured" from "at or after index 0" -- and collapsing them here would
	// decide, on the agent's behalf, a question the contract keeps open.
	AfterIndex *int `json:"after_index"`

	Timeout float64 `json:"timeout"`
}

type waitForSpeechResult struct {
	Found bool   `json:"found"`
	Index int    `json:"index"`
	Text  string `json:"text"`
}

func (t *WaitForSpeech) Execute(ctx ToolContext, params json.RawMessage) (any, error) {
	speech, err := ctx.Speech()
	if err != nil {
		return nil, err
	}
	var request waitForSpeechParams
	if err := decodeParams(params, &request); err != nil {
		return nil, err
	}
	if request.Text == "" {
		// Refused here rather than at the bridge: waiting for the empty
		// string matches the first thing said, which is never what anyone
		// meant and would look like a working assertion.
		return nil, errors.New("text is required, and must not be empty")
	}

	wait := ports.SpeechWait{Text: request.Text, AfterIndex: request.AfterIndex}
	if request.Timeout > 0 {
		wait.Timeout = time.Duration(request.Timeout * float64(time.Second))
	}

	match, err := speech.WaitForSpeech(wait)
	if err != nil {
		return nil, err
	}
	return waitForSpeechResult{Found: match.Found, Index: match.Index, Text: match.Text}, nil
}
