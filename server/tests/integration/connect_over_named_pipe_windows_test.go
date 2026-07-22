//go:build integration && windows

// screenreader-mcp tests -- connecting to a bridge over a real named pipe.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: integration scenario, Windows only -- the real-transport tier for the
// pipe leaf, which is the transport the NVDA bridge ships listening on by
// default. Its non-Windows sibling is simply absent, which is what the build tag
// is for: the module still builds and unit-tests everywhere.
//
// This is the only place the pipe leaf and the pipe scan are exercised against a
// real namespace, and it is worth having separately from the TCP scenario
// because they fail differently: a pipe is a filesystem-shaped object with its
// own naming and its own liveness story.
package integration_test

import (
	"testing"

	winio "github.com/Microsoft/go-winio"
	"github.com/marlon-sousa/screen-readers-mcp/server/adapters/discovery"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
	"github.com/marlon-sousa/screen-readers-mcp/server/testsupport"
)

// listenPipe starts the fake bridge on a real named pipe and returns the bare
// name, as a configured endpoint would spell it.
//
// The name carries the test's own suffix so a run cannot collide with a real
// bridge installed on the machine -- and, just as importantly, so this test can
// never be satisfied by one.
func listenPipe(t *testing.T, fake *testsupport.FakeBridge, name string) string {
	t.Helper()
	listener, err := winio.ListenPipe(`\\.\pipe\`+name, nil)
	if err != nil {
		t.Fatalf("listening on pipe %s: %v", name, err)
	}
	t.Cleanup(func() { listener.Close() })

	go func() {
		for {
			conn, err := listener.Accept()
			if err != nil {
				return
			}
			go fake.Serve(conn)
		}
	}()
	return name
}

func TestASessionIsEstablishedOverARealNamedPipe(t *testing.T) {
	fake := testsupport.NewFakeBridge(testsupport.BridgeOptions{})
	name := listenPipe(t, fake, "screenreaderMcpTestBridge")

	connection, err := newHandshake().Dial(
		testsupport.Reader(t, "nvda", "pipe:"+name),
		ports.SessionOptions{Mode: entities.CaptureSilent},
	)
	if err != nil {
		t.Fatalf("Dial: %v", err)
	}
	t.Cleanup(func() { connection.Lifecycle.Close() })

	if err := connection.Lifecycle.Ping(); err != nil {
		t.Errorf("Ping over a real pipe: %v", err)
	}
}

// The probe against the real namespace: a configured pipe that is listening is
// reported live, and one that is not is not. This is acceptance criterion 4
// against the actual OS rather than a scripted listing.
func TestTheProbeSeesARealListeningPipe(t *testing.T) {
	fake := testsupport.NewFakeBridge(testsupport.BridgeOptions{})
	name := listenPipe(t, fake, "screenreaderMcpProbeTestBridge")

	probe := discovery.NewPipeProbe(discovery.NewPipeDirectory())
	listening := testsupport.Endpoint(t, "pipe:"+name)
	absent := testsupport.Endpoint(t, "pipe:screenreaderMcpNoSuchBridge")

	live := probe.Live([]entities.Endpoint{listening, absent})

	if len(live) != 1 || live[0] != listening {
		t.Errorf("live = %v, want exactly the pipe that is listening", live)
	}
}
