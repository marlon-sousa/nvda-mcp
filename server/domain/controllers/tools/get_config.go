// screenreader-mcp domain -- the get_config tool.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: controller, one per tool. GATED on `config`.
// USES: ports.ConfigAccessor, through ToolContext.Config().
// LISTED BY: registry.go.
//
// BOTH THE KEY PATH AND THE VALUE ARE OPAQUE. The path is a route into the
// reader's own configuration tree, whose shape only the reader and the agent
// know; the value is arbitrary JSON, carried as a raw message so it round-trips
// byte for byte without this server ever deciding what type it is.
package tools

import (
	"encoding/json"
	"errors"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
)

// GetConfig reads one reader configuration value.
type GetConfig struct{}

var _ Tool = (*GetConfig)(nil)

func (t *GetConfig) Name() string { return "get_config" }

func (t *GetConfig) Capability() entities.Capability { return entities.CapabilityConfig }

func (t *GetConfig) Description() string {
	return "Read one value from the screen reader's own configuration, addressed by a " +
		"key path into its config tree. The path and the value are the READER's -- " +
		"for NVDA, [\"speech\", \"symbolLevel\"] or [\"braille\", \"translationTable\"]. " +
		"Read screenreader://info to learn which reader you are driving. Use this to " +
		"record a setting before changing it, so you can put it back."
}

func (t *GetConfig) InputSchema() json.RawMessage {
	return json.RawMessage(`{
	"type": "object",
	"properties": {
		"key_path": {
			"type": "array",
			"items": {"type": "string"},
			"minItems": 1,
			"description": "The path into the reader's configuration tree, outermost key first. Reader-specific (NVDA example: [\"speech\", \"symbolLevel\"])."
		}
	},
	"required": ["key_path"],
	"additionalProperties": false
}`)
}

type configParams struct {
	KeyPath []string        `json:"key_path"`
	Value   json.RawMessage `json:"value"`
}

// configResult carries the value as a raw message, so what the reader holds
// reaches the agent unchanged -- no number becoming a float, no re-ordering.
type configResult struct {
	Value json.RawMessage `json:"value"`
}

func (t *GetConfig) Execute(ctx ToolContext, params json.RawMessage) (any, error) {
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

	value, err := config.GetConfig(request.KeyPath)
	if err != nil {
		return nil, err
	}
	return configResult{Value: value}, nil
}
