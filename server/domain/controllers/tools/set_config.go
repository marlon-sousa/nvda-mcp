// screenreader-mcp domain -- the set_config tool.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: controller, one per tool. GATED on `config`.
// USES: ports.ConfigAccessor, through ToolContext.Config().
// LISTED BY: registry.go.
//
// It returns WHAT THE READER NOW HOLDS, which is not always what was sent: a
// reader may normalise, clamp or reject part of a value. Echoing the request
// instead would let a silently-adjusted setting look like a successful write.
package tools

import (
	"encoding/json"
	"errors"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
)

// SetConfig writes one reader configuration value.
type SetConfig struct{}

var _ Tool = (*SetConfig)(nil)

func (t *SetConfig) Name() string { return "set_config" }

func (t *SetConfig) Capability() entities.Capability { return entities.CapabilityConfig }

func (t *SetConfig) Description() string {
	return "Write one value into the screen reader's own configuration, addressed by a " +
		"key path into its config tree. Returns the value the reader now holds, which " +
		"may differ from what was sent if the reader normalised it. The path and the " +
		"value are the READER's vocabulary. This changes a live setting for a real " +
		"user's screen reader: read it with get_config first and put it back when you " +
		"are done."
}

func (t *SetConfig) InputSchema() json.RawMessage {
	return json.RawMessage(`{
	"type": "object",
	"properties": {
		"key_path": {
			"type": "array",
			"items": {"type": "string"},
			"minItems": 1,
			"description": "The path into the reader's configuration tree, outermost key first. Reader-specific (NVDA example: [\"speech\", \"symbolLevel\"])."
		},
		"value": {
			"description": "The value to write. Any JSON the reader accepts for this key -- a string, number, boolean, object or array."
		}
	},
	"required": ["key_path", "value"],
	"additionalProperties": false
}`)
}

func (t *SetConfig) Execute(ctx ToolContext, params json.RawMessage) (any, error) {
	config, err := ctx.Config()
	if err != nil {
		return nil, err
	}
	var request configParams
	if err := decodeParams(params, &request); err != nil {
		return nil, err
	}
	if len(request.KeyPath) == 0 {
		return nil, errors.New("key_path is required, and must name at least one key")
	}
	if len(request.Value) == 0 {
		// Distinguished from a JSON null, which IS a value a reader may
		// legitimately be asked to store: an absent `value` is a malformed
		// call, and writing null in its place would be this server guessing.
		return nil, errors.New("value is required; pass null explicitly to write a null")
	}

	written, err := config.SetConfig(request.KeyPath, request.Value)
	if err != nil {
		return nil, err
	}
	return configResult{Value: written}, nil
}
