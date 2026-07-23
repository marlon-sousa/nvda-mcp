// screenreader-mcp domain -- decodeParams: the tools' shared argument decoding.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: a private helper shared by the tool controllers in this package. Not a
// role in its own right -- it is the one line of boilerplate erased params cost
// us, kept in one place rather than repeated fifteen times.
// USED BY: every tool that takes parameters.
package tools

import (
	"encoding/json"
	"fmt"
)

// decodeParams unmarshals a call's raw arguments.
//
// EMPTY IS VALID. A client calling a tool with no arguments sends no `arguments`
// member at all, so params arrives nil rather than as `{}` -- and a tool whose
// parameters are all optional must accept that rather than report a parse error
// for a perfectly ordinary call.
//
// A decode failure is reported with the raw text included, because the agent
// wrote it and can only fix what it can see.
func decodeParams(params json.RawMessage, into any) error {
	if len(params) == 0 {
		return nil
	}
	if err := json.Unmarshal(params, into); err != nil {
		return fmt.Errorf("could not read the arguments %s: %w", params, err)
	}
	return nil
}
