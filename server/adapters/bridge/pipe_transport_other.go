//go:build !windows

// screenreader-mcp adapters -- the named-pipe Transport stub (non-Windows).
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: LEAF adapter stub. Stands in for pipe_transport_windows.go where the OS
// has no named pipes, so the module builds and unit-tests everywhere.
// BUILT BY: adapters/bridge/endpoint.go, same call site as the real leaf.
//
// This is not merely CI convenience (spec 0013): a VoiceOver or TalkBack bridge
// implies a non-Windows server host, and the endpoint set is composition-root
// config, so a server that cannot compile without pipes would be a server that
// cannot be ported.
//
// It fails at endpoint CONSTRUCTION rather than at dial time, so a
// pipe endpoint configured on a platform that has none is reported when the
// configuration is read -- with a message that says what to use instead --
// rather than at the moment an agent asks to connect.
package bridge

import (
	"fmt"

	adapterports "github.com/marlon-sousa/screen-readers-mcp/server/adapters/ports"
)

func pipeDialer(name string) (adapterports.Dialer, error) {
	return nil, fmt.Errorf(
		"pipe endpoint %q: named pipes are Windows-only; configure a loopback tcp endpoint instead",
		name,
	)
}
