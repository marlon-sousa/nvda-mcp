// screenreader-mcp domain -- the EndpointSource port.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: domain port. Where the set of readers we know how to reach comes from.
// IMPLEMENTED BY: config/loader.go, which layers the embedded defaults, an
// optional --config file and --reader flags.
// USED BY: 10b's connection controller (list_readers, connect_reader).
//
// A port rather than a plain slice handed to the controller, because the SOURCE
// is the thing that may change: today it is three static layers resolved before
// the process serves anything, and a bridge-published source could be added
// later without the domain noticing. What must never change is the guarantee
// underneath it -- every reader this can ever return is known before the process
// starts, and nothing is invented at runtime.
package ports

import "github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"

// EndpointSource is the configured reader set.
type EndpointSource interface {
	// Readers returns every reader we know how to reach, each with its
	// endpoints in declared order.
	Readers() []entities.ConfiguredReader
}
