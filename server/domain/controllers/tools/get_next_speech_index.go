// screenreader-mcp domain -- the get_next_speech_index tool.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: controller, one per tool. GATED on `speech`.
// USES: ports.SpeechReader, through ToolContext.Speech().
// LISTED BY: registry.go.
//
// This is the tool that makes speech assertions precise rather than hopeful:
// note "now", act, then read only what the action produced. Without it a caller
// has to guess how much of the log predates its own gesture.
package tools

import (
	"encoding/json"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
)

// GetNextSpeechIndex reports where the next utterance will land.
type GetNextSpeechIndex struct{}

var _ Tool = (*GetNextSpeechIndex)(nil)

func (t *GetNextSpeechIndex) Name() string { return "get_next_speech_index" }

func (t *GetNextSpeechIndex) Capability() entities.Capability { return entities.CapabilitySpeech }

func (t *GetNextSpeechIndex) Description() string {
	return "Get the index the NEXT captured utterance will take -- a bookmark for " +
		"\"now\". Call this before pressing a gesture, then pass the value as " +
		"get_speech's since_index (or wait_for_speech's after_index) to read only " +
		"what your action caused, with nothing from before it. Takes no parameters."
}

func (t *GetNextSpeechIndex) InputSchema() json.RawMessage {
	return json.RawMessage(`{"type":"object","properties":{},"additionalProperties":false}`)
}

type nextIndexResult struct {
	Index int `json:"index"`
}

func (t *GetNextSpeechIndex) Execute(ctx ToolContext, _ json.RawMessage) (any, error) {
	speech, err := ctx.Speech()
	if err != nil {
		return nil, err
	}

	index, err := speech.NextSpeechIndex()
	if err != nil {
		return nil, err
	}
	return nextIndexResult{Index: index}, nil
}
