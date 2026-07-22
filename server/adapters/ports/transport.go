// screenreader-mcp adapters -- the Transport seam.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: adapter seam -- a port BETWEEN adapters. The domain never sees this
// file; it is what lets the JSON-lines client hold every decision while the
// bytes come from a leaf that makes none (AGENTS.md, "adapters are LAYERED so
// the untestable part shrinks to a leaf").
// IMPLEMENTED BY: adapters/bridge/tcp_transport.go and
// adapters/bridge/pipe_transport_windows.go (leaves), fakes/transport.go.
// USED BY: adapters/bridge/json_lines_client.go, through this interface only --
// never a concrete transport.
//
// The package is named `ports` so the directory mirrors the bridge's
// `adapters/ports/`; importers that also need the domain's ports alias this one
// as `adapterports`.
package ports

import (
	"io"
	"time"
)

// Transport is a byte pipe to one bridge, with a POLL contract on Read.
//
// The poll contract is the whole reason this seam is not plain
// io.ReadWriteCloser. A blocking Read cannot be abandoned, so a bridge that
// accepts a connection and then says nothing would hang the server forever.
// Instead every leaf applies a short read deadline and reports an idle read as
// os.ErrDeadlineExceeded, so the client above can compare its own deadline
// against the injected Clock and give up on its own terms. Callers detect it
// with errors.Is(err, os.ErrDeadlineExceeded); io.EOF still means the peer is
// gone for good.
//
// This mirrors the bridge's own Transport, whose recv raises TimeoutError when
// idle -- same shape on both sides of the wire, learn it once.
type Transport interface {
	io.ReadWriteCloser
}

// Dialer opens one Transport to one endpoint.
//
// A function type rather than an interface: a dialer has exactly one method and
// no state worth naming, and every implementation is a closure over an already
// parsed endpoint built by adapters/bridge/endpoint.go.
type Dialer func() (Transport, error)

// PollInterval is how long a leaf lets a Read sit idle before reporting
// os.ErrDeadlineExceeded.
//
// It is a constant of the seam rather than a knob per leaf so that "how often
// does the client get a chance to notice its deadline?" has one answer. Short
// enough that a cancelled wait is not felt, long enough that an idle session
// is not a spin loop.
const PollInterval = 50 * time.Millisecond
