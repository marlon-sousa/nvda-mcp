// screenreader-mcp domain -- the get_last_speech tool.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: controller, one per tool. GATED on `speech`.
// USES: ports.SpeechReader, through ToolContext.Speech().
// LISTED BY: registry.go.
package tools

import (
	"encoding/json"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
)

// GetLastSpeech reads the most recent utterance.
type GetLastSpeech struct{}

var _ Tool = (*GetLastSpeech)(nil)

func (t *GetLastSpeech) Name() string { return "get_last_speech" }

func (t *GetLastSpeech) Capability() entities.Capability { return entities.CapabilitySpeech }

func (t *GetLastSpeech) Description() string {
	return "Read the single most recent thing the screen reader spoke, and the index " +
		"it occupies. Use this when you only care about the latest announcement -- " +
		"after moving focus, say. Use get_speech when you need everything that was " +
		"said across a sequence of actions. Takes no parameters."
}

func (t *GetLastSpeech) InputSchema() json.RawMessage {
	return json.RawMessage(`{"type":"object","properties":{},"additionalProperties":false}`)
}

type lastSpeechResult struct {
	Text  string `json:"text"`
	Index int    `json:"index"`
}

func (t *GetLastSpeech) Execute(ctx ToolContext, _ json.RawMessage) (any, error) {
	speech, err := ctx.Speech()
	if err != nil {
		return nil, err
	}

	last, err := speech.LastSpeech()
	if err != nil {
		return nil, err
	}
	return lastSpeechResult{Text: last.Text, Index: last.Index}, nil
}
