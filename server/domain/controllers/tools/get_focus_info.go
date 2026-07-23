// screenreader-mcp domain -- the get_focus_info tool.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: controller, one per tool. GATED on `focus`.
// USES: ports.FocusInspector, through ToolContext.Focus().
// LISTED BY: registry.go.
//
// Role and state strings are the READER's vocabulary and pass through opaquely.
// The agent knows what NVDA means by "editableText" and what JAWS means by its
// own spelling; this server does not, and must not learn.
package tools

import (
	"encoding/json"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
)

// GetFocusInfo reads the focus object.
type GetFocusInfo struct{}

var _ Tool = (*GetFocusInfo)(nil)

func (t *GetFocusInfo) Name() string { return "get_focus_info" }

func (t *GetFocusInfo) Capability() entities.Capability { return entities.CapabilityFocus }

func (t *GetFocusInfo) Description() string {
	return "Describe the object the screen reader currently has focus on: its name, " +
		"role, states, value and owning application. Role and state strings are the " +
		"READER's own vocabulary, not a normalised one -- read screenreader://info to " +
		"learn which reader you are driving. Use this to check where you are before " +
		"acting, and to assert what a control reports about itself. Takes no " +
		"parameters."
}

func (t *GetFocusInfo) InputSchema() json.RawMessage {
	return json.RawMessage(`{"type":"object","properties":{},"additionalProperties":false}`)
}

// focusResult keeps Value and AppModule as pointers, because the wire
// distinguishes "this object has no value" from "its value is the empty string",
// and collapsing the two would throw away a real answer.
type focusResult struct {
	Name      string   `json:"name"`
	Role      string   `json:"role"`
	States    []string `json:"states"`
	Value     *string  `json:"value"`
	AppModule *string  `json:"appModule"`
}

func (t *GetFocusInfo) Execute(ctx ToolContext, _ json.RawMessage) (any, error) {
	focus, err := ctx.Focus()
	if err != nil {
		return nil, err
	}

	info, err := focus.FocusInfo()
	if err != nil {
		return nil, err
	}
	states := info.States
	if states == nil {
		// An empty list rather than JSON null: "this object has no states" is
		// an answer an agent can iterate over without a special case.
		states = []string{}
	}
	return focusResult{
		Name:      info.Name,
		Role:      info.Role,
		States:    states,
		Value:     info.Value,
		AppModule: info.AppModule,
	}, nil
}
