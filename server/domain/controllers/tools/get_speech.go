// screenreader-mcp domain -- the get_speech tool.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: controller, one per tool. GATED on `speech`.
// USES: ports.SpeechReader, obtained through ToolContext.Speech() -- which is
// the capability check, and the only way to reach the port.
// LISTED BY: registry.go.
package tools

import (
	"encoding/json"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
)

// GetSpeech reads captured speech since an index.
type GetSpeech struct{}

var _ Tool = (*GetSpeech)(nil)

func (t *GetSpeech) Name() string { return "get_speech" }

func (t *GetSpeech) Capability() entities.Capability { return entities.CapabilitySpeech }

func (t *GetSpeech) Description() string {
	return "Read what the screen reader has spoken since a given index. Returns the " +
		"text plus the half-open range [fromIndex, toIndex) it covers, so toIndex is " +
		"exactly the since_index to pass next -- no overlap, no gap. The usual " +
		"pattern is: call get_next_speech_index, do something, then call this with " +
		"that index to read only what your action produced."
}

func (t *GetSpeech) InputSchema() json.RawMessage {
	return json.RawMessage(`{
	"type": "object",
	"properties": {
		"since_index": {
			"type": "integer",
			"minimum": 0,
			"description": "Read speech from this index onward. Use 0 for everything captured so far, or the toIndex of a previous call to continue where it left off."
		}
	},
	"required": ["since_index"],
	"additionalProperties": false
}`)
}

type speechRangeParams struct {
	SinceIndex int `json:"since_index"`
}

type speechRangeResult struct {
	Text      string `json:"text"`
	FromIndex int    `json:"fromIndex"`
	ToIndex   int    `json:"toIndex"`
}

func (t *GetSpeech) Execute(ctx ToolContext, params json.RawMessage) (any, error) {
	speech, err := ctx.Speech()
	if err != nil {
		return nil, err
	}
	var request speechRangeParams
	if err := decodeParams(params, &request); err != nil {
		return nil, err
	}

	captured, err := speech.SpeechSince(request.SinceIndex)
	if err != nil {
		return nil, err
	}
	return speechRangeResult{
		Text:      captured.Text,
		FromIndex: captured.FromIndex,
		ToIndex:   captured.ToIndex,
	}, nil
}
