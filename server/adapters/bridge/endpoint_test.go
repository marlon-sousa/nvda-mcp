// screenreader-mcp adapters -- tests for endpoint.go.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// Nothing here dials: DialerFor decides WHETHER an endpoint may be reached and
// returns how, so the decisions are testable with no OS involved. That the leaf
// underneath then works is the real-transport tier's job, not this one's.
package bridge_test

import (
	"runtime"
	"strings"
	"testing"

	"github.com/marlon-sousa/screen-readers-mcp/server/adapters/bridge"
	"github.com/marlon-sousa/screen-readers-mcp/server/testsupport"
)

func TestDialerForAcceptsLoopbackTCP(t *testing.T) {
	for _, spec := range []string{"tcp:127.0.0.1:8765", "tcp:localhost:8765", "tcp:[::1]:8765"} {
		t.Run(spec, func(t *testing.T) {
			dial, err := bridge.DialerFor(testsupport.Endpoint(t, spec))
			if err != nil {
				t.Fatalf("DialerFor(%s): %v", spec, err)
			}
			if dial == nil {
				t.Error("no dialer returned for an acceptable endpoint")
			}
		})
	}
}

// The wire contract says the connection is always local-machine-only, and remote
// TCP is deferred behind its own security spec. Enforcing it here means a config
// file cannot quietly turn this server into something that reaches across a
// network.
func TestDialerForRefusesNonLoopbackTCP(t *testing.T) {
	for _, spec := range []string{"tcp:192.168.1.10:8765", "tcp:example.com:8765", "tcp:0.0.0.0:8765"} {
		t.Run(spec, func(t *testing.T) {
			_, err := bridge.DialerFor(testsupport.Endpoint(t, spec))
			if err == nil {
				t.Fatalf("DialerFor(%s) succeeded; only loopback endpoints may be dialed", spec)
			}
			if !strings.Contains(err.Error(), spec[len("tcp:"):]) {
				t.Errorf("error %q does not name the endpoint that was refused", err)
			}
		})
	}
}

// The failure is raised where the configuration is READ, not when an agent asks
// to connect, and it says what to do instead.
func TestDialerForPipeDependsOnThePlatform(t *testing.T) {
	dial, err := bridge.DialerFor(testsupport.Endpoint(t, "pipe:nvdaMcpBridge"))

	if runtime.GOOS == "windows" {
		if err != nil {
			t.Fatalf("DialerFor(pipe) on Windows: %v", err)
		}
		if dial == nil {
			t.Error("no dialer returned for a pipe endpoint on Windows")
		}
		return
	}
	if err == nil {
		t.Fatal("DialerFor(pipe) succeeded on a platform with no named pipes")
	}
	if !strings.Contains(err.Error(), "tcp") {
		t.Errorf("error %q does not point at the alternative", err)
	}
}
