// screenreader-mcp adapters -- SystemClock: the Clock leaf.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: LEAF adapter. IMPLEMENTS the Clock domain port with the real clock,
// and nothing else.
// BUILT BY: wiring/wiring.go.
// USED BY: everything that reads time, through the port -- never directly.
//
// There is no test file beside this on purpose (AGENTS.md): a leaf makes no
// decisions, and there is nothing here that the standard library does not
// already guarantee. If you find yourself wanting to test this file, a decision
// has leaked down into it and belongs one layer up.
package adapters

import (
	"time"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// SystemClock reads the real monotonic clock and really sleeps.
type SystemClock struct{}

var _ ports.Clock = (*SystemClock)(nil)

// NewSystemClock builds the production Clock.
func NewSystemClock() *SystemClock { return &SystemClock{} }

// Now returns the current time, which carries Go's monotonic reading.
func (c *SystemClock) Now() time.Time { return time.Now() }

// Sleep really blocks. Only production code reaches this.
func (c *SystemClock) Sleep(d time.Duration) { time.Sleep(d) }
