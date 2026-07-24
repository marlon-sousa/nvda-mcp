//go:build conformance && windows

// screenreader-mcp tests -- the same whole session, over a REAL named pipe.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: conformance scenario, Windows only -- the named-pipe half of spec 0013's
// deliverable 19 ("repeated over loopback TCP"). Its body is deliberately the
// same function its TCP twin calls, because the transport is the ONLY thing that
// differs and that symmetry is the proof: whatever the pipe leaf does to the
// bytes, it does not change what the two implementations agree about.
//
// Windows only because both leaves are: the server's pipe transport is
// //go:build windows, and the bridge's is ctypes/Win32. The named pipe is what
// the NVDA bridge ships listening on by default, so this is the transport the
// real installation actually uses -- the TCP run is the fallback spec 0011's
// dialog lets a user switch to.
package conformance_test

import "testing"

func TestAWholeSessionOverARealNamedPipe(t *testing.T) {
	runWholeSession(t, "pipe")
}
