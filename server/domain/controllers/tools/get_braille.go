// screenreader-mcp domain -- the get_braille tool.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: controller, one per tool. GATED on `braille`.
// USES: ports.BrailleReader, through ToolContext.Braille().
// LISTED BY: registry.go.
//
// This is the tool the whole capability gate was designed around: a reader
// without braille never sees it advertised, because the handshake handed over no
// BrailleReader for it to reach. "JAWS has no braille" is a missing
// collaborator, not a runtime check somebody has to remember to write.
package tools

import (
	"encoding/json"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
)

// GetBraille reads captured braille since an index.
type GetBraille struct{}

var _ Tool = (*GetBraille)(nil)

func (t *GetBraille) Name() string { return "get_braille" }

func (t *GetBraille) Capability() entities.Capability { return entities.CapabilityBraille }

func (t *GetBraille) Description() string {
	return "Read what the screen reader has sent to the braille display since a given " +
		"index. Returns the text plus the half-open range [fromIndex, toIndex) it " +
		"covers, so toIndex is exactly the since_index to pass next. Braille is a " +
		"separate log from speech, with its own indices -- what is brailled is often " +
		"abbreviated differently from what is spoken, which is the point of checking " +
		"both."
}

func (t *GetBraille) InputSchema() json.RawMessage {
	return json.RawMessage(`{
	"type": "object",
	"properties": {
		"since_index": {
			"type": "integer",
			"minimum": 0,
			"description": "Read braille from this index onward. Use 0 for everything captured so far, or the toIndex of a previous call to continue where it left off. This index is NOT interchangeable with a speech index."
		}
	},
	"required": ["since_index"],
	"additionalProperties": false
}`)
}

func (t *GetBraille) Execute(ctx ToolContext, params json.RawMessage) (any, error) {
	braille, err := ctx.Braille()
	if err != nil {
		return nil, err
	}
	var request speechRangeParams
	if err := decodeParams(params, &request); err != nil {
		return nil, err
	}

	captured, err := braille.BrailleSince(request.SinceIndex)
	if err != nil {
		return nil, err
	}
	return speechRangeResult{
		Text:      captured.Text,
		FromIndex: captured.FromIndex,
		ToIndex:   captured.ToIndex,
	}, nil
}
