// screenreader-mcp adapters -- TCPTransport: a Transport leaf.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: LEAF adapter. IMPLEMENTS the Transport seam (adapters/ports) over a
// real loopback TCP connection, and does nothing else.
// BUILT BY: adapters/bridge/endpoint.go, which is where the decisions live --
// which host is acceptable, how the address is spelled.
// USED BY: adapters/bridge/json_lines_client.go, through the seam.
//
// No test file beside it on purpose (AGENTS.md): there is nothing here that
// net.Conn does not already guarantee. The one line that looks like a decision,
// the read deadline, is the seam's own PollInterval constant applied verbatim.
package bridge

import (
	"net"
	"time"

	adapterports "github.com/marlon-sousa/screen-readers-mcp/server/adapters/ports"
)

// tcpTransport is one connected loopback socket.
type tcpTransport struct {
	conn net.Conn
}

var _ adapterports.Transport = (*tcpTransport)(nil)

// dialTCP opens a connection to an already-validated loopback address.
func dialTCP(address string, connectTimeout time.Duration) (adapterports.Transport, error) {
	conn, err := net.DialTimeout("tcp", address, connectTimeout)
	if err != nil {
		return nil, err
	}
	return &tcpTransport{conn: conn}, nil
}

// Read applies the seam's poll deadline, so an idle read surfaces as
// os.ErrDeadlineExceeded rather than blocking forever. net.Conn already reports
// a passed deadline that way, so the contract falls out for free.
func (t *tcpTransport) Read(p []byte) (int, error) {
	if err := t.conn.SetReadDeadline(time.Now().Add(adapterports.PollInterval)); err != nil {
		return 0, err
	}
	return t.conn.Read(p)
}

func (t *tcpTransport) Write(p []byte) (int, error) { return t.conn.Write(p) }

func (t *tcpTransport) Close() error { return t.conn.Close() }
