// screenreader-mcp domain -- the Log port.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: domain port. Diagnostics, for the domain and the adapters alike.
// IMPLEMENTED BY: adapters/stderr_log.go (production), fakes/log.go (tests).
// USED BY: the bridge client and, in 10b, the connection controller.
//
// This port exists for ONE reason beyond taste: stdout carries MCP frames and
// nothing else, and a single stray fmt.Println corrupts the JSON-RPC stream.
// With a Log port injected, reaching os.Stdout is not something the domain can
// do by accident -- it has no reason to import fmt at all.
package ports

// Log is levelled diagnostics. Deliberately small: this is a router, and
// anything richer would be a logging framework in the domain's imports.
type Log interface {
	// Debugf is detail wanted only while diagnosing.
	Debugf(format string, args ...any)

	// Infof is the ordinary narrative: connected, disconnected, why.
	Infof(format string, args ...any)

	// Errorf is a failure the operator should see.
	Errorf(format string, args ...any)
}
