// screenreader-mcp domain -- the list_readers tool.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: controller, one per tool. UNGATED -- advertised from startup, because a
// server with no session must still be able to say what it knows how to reach.
// USES: ConnectionControl.List, via ToolContext.
// LISTED BY: registry.go.
//
// Every reader this can ever return is known before the process starts: the
// answer comes from the layered endpoint configuration, never from what happens
// to be running. A pipe that is listening and belongs to no configured reader is
// absent from it -- which is spec 0013's determinism rule, and matters more given
// where this is heading, since a bridge is about to become something you
// provision rather than something you stumble upon.
package tools

import (
	"encoding/json"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
)

// ListReaders answers what readers exist and whether they look reachable.
type ListReaders struct{}

var _ Tool = (*ListReaders)(nil)

func (t *ListReaders) Name() string { return "list_readers" }

func (t *ListReaders) Capability() entities.Capability { return "" }

func (t *ListReaders) Description() string {
	return "List the screen readers this server knows how to reach, each with its " +
		"endpoints in the order connect_reader will try them, and whether a bridge " +
		"is listening there. Liveness is \"listening\" or \"not listening\" for a " +
		"named pipe, and \"unknown\" for TCP, which cannot be tested without " +
		"connecting. Takes no parameters. Call this first to learn the reader name " +
		"connect_reader wants."
}

func (t *ListReaders) InputSchema() json.RawMessage {
	return json.RawMessage(`{"type":"object","properties":{},"additionalProperties":false}`)
}

// listedEndpoint and listedReader are this tool's OUTPUT shape.
//
// Its own shape rather than marshalling the entity directly: what an agent reads
// is part of the tool's contract, so it should change only when we mean it to,
// not because a domain field was renamed.
type listedEndpoint struct {
	Endpoint string `json:"endpoint"`
	Liveness string `json:"liveness"`
}

type listedReader struct {
	Reader    string           `json:"reader"`
	Endpoints []listedEndpoint `json:"endpoints"`
}

type listReadersResult struct {
	Readers []listedReader `json:"readers"`
}

func (t *ListReaders) Execute(ctx ToolContext, _ json.RawMessage) (any, error) {
	listing := ctx.Control.List()

	result := listReadersResult{Readers: make([]listedReader, 0, len(listing.Readers))}
	for _, reader := range listing.Readers {
		listed := listedReader{
			Reader:    reader.Name,
			Endpoints: make([]listedEndpoint, 0, len(reader.Endpoints)),
		}
		for _, endpoint := range reader.Endpoints {
			listed.Endpoints = append(listed.Endpoints, listedEndpoint{
				// The endpoint's own spelling, which round-trips: what the
				// agent is shown is exactly what may be written back into a
				// --reader flag.
				Endpoint: endpoint.Endpoint.String(),
				Liveness: string(endpoint.Liveness),
			})
		}
		result.Readers = append(result.Readers, listed)
	}
	return result, nil
}
