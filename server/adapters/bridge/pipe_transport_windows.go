//go:build windows

// screenreader-mcp adapters -- the named-pipe Transport leaf (Windows).
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: LEAF adapter. IMPLEMENTS the Transport seam over a real Windows named
// pipe, and does nothing else.
// BUILT BY: adapters/bridge/endpoint.go, which owns every decision about which
// endpoint is dialed at all.
// USED BY: adapters/bridge/json_lines_client.go, through the seam.
//
// go-winio rather than os.OpenFile: a pipe handle opened the plain way is not
// overlapped, so it cannot carry a read deadline, and the seam's poll contract
// is exactly a read deadline. go-winio is pure Go, so CGO_ENABLED=0 and the
// single statically linked artifact survive.
//
// No test file beside it, and nothing here to test: the decisions are one layer
// up, and what remains is the OS.
package bridge

import (
	"net"
	"time"

	winio "github.com/Microsoft/go-winio"
	adapterports "github.com/marlon-sousa/screen-readers-mcp/server/adapters/ports"
)

// pipePrefix is the OS spelling of the pipe namespace. It lives in the leaf
// because it is an operating-system detail: a domain Endpoint carries the bare
// name a user configured (`nvdaMcpBridge`), and this is the only place that
// knows what Windows requires in front of it.
const pipePrefix = `\\.\pipe\`

// pipeTransport is one connected named pipe.
type pipeTransport struct {
	conn net.Conn
}

var _ adapterports.Transport = (*pipeTransport)(nil)

// pipeDialer returns a Dialer for one pipe name.
func pipeDialer(name string) (adapterports.Dialer, error) {
	path := pipePrefix + name
	return func() (adapterports.Transport, error) {
		timeout := DefaultConnectTimeout
		conn, err := winio.DialPipe(path, &timeout)
		if err != nil {
			return nil, err
		}
		return &pipeTransport{conn: conn}, nil
	}, nil
}

// Read applies the seam's poll deadline, so an idle read surfaces as
// os.ErrDeadlineExceeded rather than blocking forever.
func (t *pipeTransport) Read(p []byte) (int, error) {
	if err := t.conn.SetReadDeadline(time.Now().Add(adapterports.PollInterval)); err != nil {
		return 0, err
	}
	return t.conn.Read(p)
}

func (t *pipeTransport) Write(p []byte) (int, error) { return t.conn.Write(p) }

func (t *pipeTransport) Close() error { return t.conn.Close() }
