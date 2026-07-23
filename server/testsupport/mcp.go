// screenreader-mcp testsupport -- a real MCP client driving the real server.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test scaffolding for the headless integration tier. Assembles the WHOLE
// production stack -- wiring, the SDK server, the tools, the domain, the
// JSON-lines client, a real transport leaf -- with only the BRIDGE faked, and
// hands the test an MCP client session to drive it through.
// USED BY: server/tests/integration/.
//
// The integration surface is the MCP BOUNDARY (spec 0013): these tests assert on
// what an MCP client sees -- tools/list, tools/call results, resource reads --
// and never on internal state. The SDK's in-memory transports let a real client
// drive a real server in one process, with no stdio.
//
// The bridge is reached over a real loopback socket rather than an in-memory
// pipe, so the composition under test is the production one all the way down,
// including config.Load and the TCP leaf. What this tier still cannot catch, and
// why 10c exists: the fake bridge encodes frames with the same adapters/wire
// package the server decodes them with, so a bug in the binding itself would
// have both sides wrong together, in agreement.
package testsupport

import (
	"context"
	"encoding/json"
	"net"
	"testing"
	"time"

	sdk "github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/marlon-sousa/screen-readers-mcp/server/wiring"
)

// MCPHarness is one running server and a client attached to it.
type MCPHarness struct {
	// Session is the MCP client's session: the only thing a test should
	// normally touch.
	Session *sdk.ClientSession

	// Server is the assembled process, for the rare assertion that is about
	// the composition rather than about what the client sees.
	Server *wiring.Server

	// Bridge is the fake bridge the server will dial, so a test can seed
	// command answers and assert on what the bridge was sent.
	Bridge *FakeBridge

	// ToolsChanged receives one value per tools/list_changed notification.
	ToolsChanged chan struct{}
}

// StartMCP builds the whole server around a fake bridge listening on loopback,
// and connects a client to it.
//
// The reader is configured through --reader, exactly as a user would override an
// endpoint, so the layered configuration is part of what is exercised.
func StartMCP(t *testing.T, options BridgeOptions) *MCPHarness {
	t.Helper()

	bridge := NewFakeBridge(options)
	address := listen(t, bridge)

	server, err := wiring.Build(wiring.Options{
		ReaderFlags: []string{"nvda=tcp:" + address},
	})
	if err != nil {
		t.Fatalf("building the server: %v", err)
	}
	t.Cleanup(server.Connection.Close)

	ctx := context.Background()
	clientTransport, serverTransport := sdk.NewInMemoryTransports()

	serverSession, err := server.MCP.Connect(ctx, serverTransport)
	if err != nil {
		t.Fatalf("connecting the server: %v", err)
	}
	t.Cleanup(func() { _ = serverSession.Close() })

	changed := make(chan struct{}, 32)
	client := sdk.NewClient(&sdk.Implementation{Name: "test-client", Version: "0"}, &sdk.ClientOptions{
		ToolListChangedHandler: func(context.Context, *sdk.ToolListChangedRequest) {
			// Buffered and non-blocking: a test that does not care about
			// the notification must not deadlock the SDK's reader.
			select {
			case changed <- struct{}{}:
			default:
			}
		},
	})

	session, err := client.Connect(ctx, clientTransport, nil)
	if err != nil {
		t.Fatalf("connecting the client: %v", err)
	}
	t.Cleanup(func() { _ = session.Close() })

	return &MCPHarness{
		Session: session, Server: server, Bridge: bridge, ToolsChanged: changed,
	}
}

// listen starts the fake bridge on a real loopback socket. Port 0, so parallel
// runs cannot collide.
func listen(t *testing.T, bridge *FakeBridge) string {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listening on loopback: %v", err)
	}
	t.Cleanup(func() { _ = listener.Close() })

	go func() {
		for {
			conn, err := listener.Accept()
			if err != nil {
				return
			}
			go bridge.Serve(conn)
		}
	}()
	return listener.Addr().String()
}

// ToolNames is what tools/list currently advertises.
func (h *MCPHarness) ToolNames(t *testing.T) []string {
	t.Helper()
	listing, err := h.Session.ListTools(context.Background(), nil)
	if err != nil {
		t.Fatalf("tools/list: %v", err)
	}
	names := make([]string, 0, len(listing.Tools))
	for _, tool := range listing.Tools {
		names = append(names, tool.Name)
	}
	return names
}

// Advertises reports whether one tool is currently in tools/list.
func (h *MCPHarness) Advertises(t *testing.T, name string) bool {
	t.Helper()
	for _, advertised := range h.ToolNames(t) {
		if advertised == name {
			return true
		}
	}
	return false
}

// ToolResult is one tools/call answer, as a client sees it.
type ToolResult struct {
	// Text is the result's text content -- the tool's JSON on success, the
	// error message when IsError.
	Text string

	// IsError says the tool failed. A failed tool is a RESULT, not a protocol
	// error, so that an agent can read the reason and self-correct.
	IsError bool
}

// Call makes a tools/call. Arguments may be nil for a tool that takes none,
// which is what a client actually sends.
func (h *MCPHarness) Call(t *testing.T, name string, arguments map[string]any) ToolResult {
	t.Helper()
	result, err := h.Session.CallTool(context.Background(), &sdk.CallToolParams{
		Name: name, Arguments: arguments,
	})
	if err != nil {
		t.Fatalf("tools/call %s: %v", name, err)
	}
	answer := ToolResult{IsError: result.IsError}
	if len(result.Content) > 0 {
		if text, ok := result.Content[0].(*sdk.TextContent); ok {
			answer.Text = text.Text
		}
	}
	return answer
}

// CallExpectingProtocolError makes a call that should fail at the JSON-RPC
// level -- the SDK's answer for a name it has never heard of.
func (h *MCPHarness) CallExpectingProtocolError(t *testing.T, name string) error {
	t.Helper()
	_, err := h.Session.CallTool(context.Background(), &sdk.CallToolParams{Name: name})
	if err == nil {
		t.Fatalf("tools/call %s succeeded; a protocol error was expected", name)
	}
	return err
}

// Decode unmarshals a successful result's JSON into a value.
func (r ToolResult) Decode(t *testing.T, into any) {
	t.Helper()
	if r.IsError {
		t.Fatalf("the call failed: %s", r.Text)
	}
	if err := json.Unmarshal([]byte(r.Text), into); err != nil {
		t.Fatalf("decoding %s: %v", r.Text, err)
	}
}

// Connect opens a session through the real connect_reader tool.
func (h *MCPHarness) Connect(t *testing.T) ToolResult {
	t.Helper()
	return h.Call(t, "connect_reader", map[string]any{"reader": "nvda", "mode": "silent"})
}

// ReadInfo reads screenreader://info.
func (h *MCPHarness) ReadInfo(t *testing.T) map[string]any {
	t.Helper()
	read, err := h.Session.ReadResource(context.Background(), &sdk.ReadResourceParams{
		URI: "screenreader://info",
	})
	if err != nil {
		t.Fatalf("reading screenreader://info: %v", err)
	}
	var document map[string]any
	if err := json.Unmarshal([]byte(read.Contents[0].Text), &document); err != nil {
		t.Fatalf("decoding the info resource: %v", err)
	}
	return document
}

// AwaitToolsChanged waits for a tools/list_changed notification.
//
// The SDK debounces the notification by a few milliseconds, so a test that
// asserted on tools/list immediately after connecting would be racing it. This
// is the one place a real timeout is used rather than the Clock port: what is
// being waited on is the SDK's own scheduling, which no injected clock reaches.
func (h *MCPHarness) AwaitToolsChanged(t *testing.T) {
	t.Helper()
	select {
	case <-h.ToolsChanged:
	case <-time.After(5 * time.Second):
		t.Fatal("no tools/list_changed notification arrived")
	}
}
