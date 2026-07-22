// screenreader-mcp domain -- the Clock port.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: domain port. What the domain needs from the world about time.
// IMPLEMENTED BY: adapters/system_clock.go (production), fakes/clock.go (tests).
// USED BY: the bridge client's request deadlines and, in 10b, the connection
// controller's heartbeat.
//
// Time is injected, never patched (AGENTS.md): a fake's Sleep is an instant
// advance, so a 30-second timeout is exercised in microseconds and no test ever
// calls time.Sleep.
package ports

import "time"

// Clock is monotonic time plus sleeping, injected wherever time is read or
// waited on.
type Clock interface {
	// Now is a monotonic reading; only differences between readings are
	// meaningful, so a fake is free to start wherever it likes.
	Now() time.Time

	// Sleep blocks for d. A fake advances its own Now instead of blocking.
	Sleep(d time.Duration)
}
