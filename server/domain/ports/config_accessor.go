// screenreader-mcp domain -- the ConfigAccessor port (the `config` capability).
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: domain port. The `config` capability group (protocol.md §4).
// IMPLEMENTED BY: adapters/bridge/json_lines_client.go.
// USED BY: 10b's get_config and set_config tool controllers.
// HANDED OUT BY: the handshake, only when the reader announced `config`.
package ports

import "encoding/json"

// ConfigAccessor reads and writes the reader's own configuration.
//
// Both the key path and the value are OPAQUE. A key path is a path into the
// reader's config tree, whose shape only the reader and the agent know; a value
// is arbitrary JSON, carried as json.RawMessage so it round-trips byte-for-byte
// without this server ever deciding what type it is. That is encoding/json from
// the standard library, not the generated binding -- the domain still speaks no
// wire types.
type ConfigAccessor interface {
	// GetConfig reads one value.
	GetConfig(keyPath []string) (json.RawMessage, error)

	// SetConfig writes one value and returns what the reader now holds,
	// which is not always what was sent -- a reader may normalise it.
	SetConfig(keyPath []string, value json.RawMessage) (json.RawMessage, error)
}
