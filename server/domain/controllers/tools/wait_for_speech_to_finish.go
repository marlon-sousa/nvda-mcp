// screenreader-mcp domain -- the wait_for_speech_to_finish tool.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: controller, one per tool. GATED on `speech`.
// USES: ports.SpeechReader, through ToolContext.Speech().
// LISTED BY: registry.go.
package tools

import (
	"encoding/json"
	"time"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
)

// WaitForSpeechToFinish blocks until speech settles.
type WaitForSpeechToFinish struct{}

var _ Tool = (*WaitForSpeechToFinish)(nil)

func (t *WaitForSpeechToFinish) Name() string { return "wait_for_speech_to_finish" }

func (t *WaitForSpeechToFinish) Capability() entities.Capability { return entities.CapabilitySpeech }

func (t *WaitForSpeechToFinish) Description() string {
	return "Wait until the screen reader has stopped speaking, or until the timeout " +
		"elapses. Returns finished=true if speech settled and false if it was still " +
		"going -- neither is an error. Use this after an action that produces a long " +
		"announcement, before reading it back, so you do not capture half of it."
}

func (t *WaitForSpeechToFinish) InputSchema() json.RawMessage {
	return json.RawMessage(`{
	"type": "object",
	"properties": {
		"timeout": {
			"type": "number",
			"exclusiveMinimum": 0,
			"description": "How long to wait, in seconds. Omit to use the reader's own default."
		}
	},
	"additionalProperties": false
}`)
}

type waitToFinishParams struct {
	Timeout float64 `json:"timeout"`
}

type waitToFinishResult struct {
	Finished bool `json:"finished"`
}

func (t *WaitForSpeechToFinish) Execute(ctx ToolContext, params json.RawMessage) (any, error) {
	speech, err := ctx.Speech()
	if err != nil {
		return nil, err
	}
	var request waitToFinishParams
	if err := decodeParams(params, &request); err != nil {
		return nil, err
	}

	// Zero means "the reader's own default": the contract owns that value, so
	// this server does not duplicate it into the request.
	var timeout time.Duration
	if request.Timeout > 0 {
		timeout = time.Duration(request.Timeout * float64(time.Second))
	}

	finished, err := speech.WaitForSpeechToFinish(timeout)
	if err != nil {
		return nil, err
	}
	return waitToFinishResult{Finished: finished}, nil
}
