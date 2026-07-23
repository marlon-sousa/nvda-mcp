// screenreader-mcp domain -- the Connection controller's tests.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// This controller owns the whole agent-initiated lifecycle, so most of spec
// 0013's acceptance criteria are decided here and proved here first: the gate
// (10), no connection the agent did not ask for (9), a second connect refused
// (7), a mismatch that reports rather than crashes (8), and both retraction
// paths (6).
package controllers_test

import (
	"errors"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/controllers"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
	"github.com/marlon-sousa/screen-readers-mcp/server/fakes"
	"github.com/marlon-sousa/screen-readers-mcp/server/testsupport"
)

// harness is the controller with every collaborator faked, plus the fakes
// themselves.
//
// A builder rather than a fixture, because every test customises something --
// which reader is configured, what the dialer does, which capabilities were
// announced. Fixtures suit uniform collaborators; builders suit scenarios
// (AGENTS.md).
type harness struct {
	controller *controllers.Connection
	dialer     *fakes.FakeSessionDialer
	publisher  *fakes.FakeToolPublisher
	clock      *fakes.FakeClock
	log        *fakes.FakeLog
}

// catalog is a gate shaped like the real one: the ungated four, plus one gated
// tool per capability so a test can see exactly which gate opened.
func catalog() entities.ToolCatalog {
	return entities.NewToolCatalog([]entities.ToolGate{
		{Name: "list_readers"},
		{Name: "connect_reader"},
		{Name: "disconnect_reader"},
		{Name: "status"},
		{Name: "get_speech", Capability: entities.CapabilitySpeech},
		{Name: "get_braille", Capability: entities.CapabilityBraille},
		{Name: "press_gesture", Capability: entities.CapabilityGestures},
	})
}

func newHarness(t *testing.T, readers ...entities.ConfiguredReader) *harness {
	t.Helper()
	if len(readers) == 0 {
		readers = []entities.ConfiguredReader{
			testsupport.Reader(t, "nvda", "pipe:nvdaMcpBridge", "tcp:127.0.0.1:8765"),
		}
	}

	built := &harness{
		dialer:    fakes.NewFakeSessionDialer(),
		publisher: fakes.NewFakeToolPublisher(),
		clock:     fakes.NewFakeClock(),
		log:       fakes.NewFakeLog(),
	}
	built.controller = controllers.NewConnection(
		fakes.NewFakeEndpointSource(readers...),
		fakes.NewFakeEndpointProbe(),
		built.dialer,
		built.publisher,
		catalog(),
		built.clock,
		built.log,
	)
	return built
}

// connected scripts a successful dial for a reader announcing these
// capabilities, and returns the connection's fakes.
func (h *harness) connected(reader string, announced ...entities.Capability) *testsupport.Connection {
	built := testsupport.NewConnection(reader, announced...)
	h.dialer.Returns(built.Connection)
	return built
}

func silent() ports.SessionOptions {
	return ports.SessionOptions{Mode: entities.CaptureSilent}
}

// Acceptance criterion 3, and the most important thing this controller does not
// do: building it dials nothing.
func TestAFreshControllerIsDisconnectedAndHasDialedNothing(t *testing.T) {
	h := newHarness(t)

	if state := h.controller.Status().State; state != entities.Disconnected {
		t.Errorf("state = %q, want disconnected", state)
	}
	if h.controller.Current() != nil {
		t.Error("a fresh controller has a connection")
	}
	if len(h.dialer.Calls()) != 0 {
		t.Error("a fresh controller dialed something")
	}
	if len(h.publisher.Published()) != 0 {
		t.Errorf("published = %v, want nothing until a session exists", h.publisher.Published())
	}
}

// Acceptance criterion 5 and the gate: connecting publishes exactly the tools
// the announced capabilities allow.
func TestConnectingPublishesTheToolsTheCapabilitiesAllow(t *testing.T) {
	h := newHarness(t)
	h.connected("nvda", entities.CapabilitySpeech, entities.CapabilityGestures)

	connection, err := h.controller.Connect("nvda", silent())
	if err != nil {
		t.Fatalf("Connect: %v", err)
	}

	if connection.Session.Reader.Name != "nvda" {
		t.Errorf("reader = %q, want nvda", connection.Session.Reader.Name)
	}
	if state := h.controller.Status().State; state != entities.Connected {
		t.Errorf("state = %q, want connected", state)
	}

	want := []string{"get_speech", "press_gesture"}
	if got := h.publisher.Published(); !slices.Equal(got, want) {
		t.Errorf("published = %v, want %v", got, want)
	}
}

// Acceptance criterion 10, first clause: a reader without braille never gets the
// braille tool. Keyed on the capability string and on nothing else -- the reader
// here is deliberately still called nvda.
func TestAReaderWithoutBrailleNeverGetsTheBrailleTool(t *testing.T) {
	h := newHarness(t)
	h.connected("nvda", entities.CapabilitySpeech)

	if _, err := h.controller.Connect("nvda", silent()); err != nil {
		t.Fatalf("Connect: %v", err)
	}

	if h.publisher.Has("get_braille") {
		t.Error("get_braille was advertised to a reader that never announced braille")
	}
}

// The ungated four are not the connection's to publish or retract: a disconnect
// that swept them up would leave the agent with no way back.
func TestConnectingNeverTouchesTheUngatedTools(t *testing.T) {
	h := newHarness(t)
	h.connected("nvda", testsupport.EveryCapability()...)

	if _, err := h.controller.Connect("nvda", silent()); err != nil {
		t.Fatalf("Connect: %v", err)
	}

	for _, name := range []string{"list_readers", "connect_reader", "disconnect_reader", "status"} {
		if slices.Contains(h.publisher.History(), "+"+name) {
			t.Errorf("the connection published the ungated tool %q", name)
		}
	}
}

// The session parameters are the agent's, and must reach the dialer as given.
func TestTheSessionParametersReachTheDialerUnchanged(t *testing.T) {
	h := newHarness(t)
	h.connected("nvda", entities.CapabilitySpeech)
	level := entities.ReaderLogDebug

	_, err := h.controller.Connect("nvda", ports.SessionOptions{
		Mode: entities.CaptureLive, LogLevel: &level,
	})
	if err != nil {
		t.Fatalf("Connect: %v", err)
	}

	calls := h.dialer.Calls()
	if len(calls) != 1 {
		t.Fatalf("dialed %d times, want once", len(calls))
	}
	if calls[0].Options.Mode != entities.CaptureLive {
		t.Errorf("mode = %q, want live", calls[0].Options.Mode)
	}
	if calls[0].Options.LogLevel == nil || *calls[0].Options.LogLevel != entities.ReaderLogDebug {
		t.Errorf("log level = %v, want debug", calls[0].Options.LogLevel)
	}
	// And the reader's endpoints, in declared order -- the user's transport
	// toggle made invisible.
	if len(calls[0].Reader.Endpoints) != 2 || calls[0].Reader.Endpoints[0].Kind != entities.TransportPipe {
		t.Errorf("endpoints = %v, want both, pipe first", calls[0].Reader.Endpoints)
	}
}

// Acceptance criterion 7.
func TestConnectingWhileConnectedIsAnErrorAndLeavesTheSessionAlone(t *testing.T) {
	h := newHarness(t)
	h.connected("nvda", entities.CapabilitySpeech)
	first, err := h.controller.Connect("nvda", silent())
	if err != nil {
		t.Fatalf("Connect: %v", err)
	}

	_, err = h.controller.Connect("nvda", silent())
	if err == nil {
		t.Fatal("a second connect succeeded")
	}
	if h.controller.Current() != first {
		t.Error("the live session was replaced; a second connect must leave it untouched")
	}
	if len(h.dialer.Calls()) != 1 {
		t.Errorf("dialed %d times, want once -- the second connect must not dial",
			len(h.dialer.Calls()))
	}
	if !h.publisher.Has("get_speech") {
		t.Error("the gated tools were disturbed by the refused connect")
	}
}

// The error lists the known names, so a wrong guess self-corrects in the same
// turn rather than costing a round trip to list_readers.
func TestAnUnknownReaderNamesTheOnesThatExist(t *testing.T) {
	h := newHarness(t,
		testsupport.Reader(t, "nvda", "pipe:nvdaMcpBridge"),
		testsupport.Reader(t, "jaws", "pipe:jawsMcpBridge"),
	)

	_, err := h.controller.Connect("narrator", silent())
	if err == nil {
		t.Fatal("connecting to an unknown reader succeeded")
	}
	if !strings.Contains(err.Error(), "nvda") || !strings.Contains(err.Error(), "jaws") {
		t.Errorf("error = %q, want the known readers listed", err)
	}
	// Acceptance criterion 9: an unknown name must not become a dial.
	if len(h.dialer.Calls()) != 0 {
		t.Error("an unknown reader was dialed")
	}
}

// Acceptance criterion 8: reported, not crashed, and the state says why for as
// long as it holds.
func TestAProtocolMismatchIsRecordedAsIncompatible(t *testing.T) {
	h := newHarness(t)
	h.dialer.FailWith(&ports.ProtocolMismatchError{BridgeVersion: 2, ServerVersions: []int{1}})

	_, err := h.controller.Connect("nvda", silent())
	if err == nil {
		t.Fatal("a protocol mismatch was reported as success")
	}

	status := h.controller.Status()
	if status.State != entities.Incompatible {
		t.Errorf("state = %q, want incompatible -- the remedy is to update one of "+
			"the two components, not to try again", status.State)
	}
	if !strings.Contains(status.Reason, "2") || !strings.Contains(status.Reason, "1") {
		t.Errorf("reason = %q, want both versions named", status.Reason)
	}
	if len(h.publisher.Published()) != 0 {
		t.Error("tools were published for a session that never began")
	}
}

// Any other failure leaves the state Disconnected with the reason attached --
// and, in particular, no retry.
func TestAFailedConnectIsDisconnectedWithAReasonAndNoRetry(t *testing.T) {
	h := newHarness(t)
	h.dialer.FailWith(errors.New(`reader "nvda": no endpoint answered`))

	if _, err := h.controller.Connect("nvda", silent()); err == nil {
		t.Fatal("a failed connect was reported as success")
	}

	status := h.controller.Status()
	if status.State != entities.Disconnected {
		t.Errorf("state = %q, want disconnected", status.State)
	}
	if status.Reason == "" {
		t.Error("reason is empty; the agent has to be told why")
	}
	if len(h.dialer.Calls()) != 1 {
		t.Errorf("dialed %d times, want once -- there is no retry policy here",
			len(h.dialer.Calls()))
	}
}

// Acceptance criterion 6, the polite path.
func TestDisconnectingSendsByeAndRetractsTheGatedTools(t *testing.T) {
	h := newHarness(t)
	built := h.connected("nvda", entities.CapabilitySpeech, entities.CapabilityBraille)
	if _, err := h.controller.Connect("nvda", silent()); err != nil {
		t.Fatalf("Connect: %v", err)
	}

	if err := h.controller.Disconnect(); err != nil {
		t.Fatalf("Disconnect: %v", err)
	}

	if built.Lifecycle.Byes() != 1 {
		t.Errorf("bye sent %d times, want once", built.Lifecycle.Byes())
	}
	if built.Lifecycle.Closes() != 1 {
		t.Errorf("closed %d times, want once", built.Lifecycle.Closes())
	}
	if got := h.publisher.Published(); len(got) != 0 {
		t.Errorf("published = %v, want everything retracted", got)
	}
	if h.controller.Current() != nil {
		t.Error("a session survived its own disconnect")
	}
	if state := h.controller.Status().State; state != entities.Disconnected {
		t.Errorf("state = %q, want disconnected", state)
	}
}

// Teardown is reached from several directions and none of them should have to
// check first.
func TestDisconnectingWithNoSessionIsHarmless(t *testing.T) {
	h := newHarness(t)

	if err := h.controller.Disconnect(); err != nil {
		t.Errorf("Disconnect with no session: %v", err)
	}
}

// A bridge that died a moment ago must still yield a clean disconnect: Bye
// treats an already-gone peer as success, so the agent is not handed a failure
// it can do nothing about.
func TestDisconnectingAnAlreadyDeadBridgeStillSucceeds(t *testing.T) {
	h := newHarness(t)
	built := h.connected("nvda", entities.CapabilitySpeech)
	if _, err := h.controller.Connect("nvda", silent()); err != nil {
		t.Fatalf("Connect: %v", err)
	}
	built.Lifecycle.FailByeWith(ports.ErrConnectionLost)

	if err := h.controller.Disconnect(); err != nil {
		t.Errorf("Disconnect: %v, want a clean disconnect anyway", err)
	}
	if got := h.publisher.Published(); len(got) != 0 {
		t.Errorf("published = %v, want everything retracted regardless", got)
	}
}

// Acceptance criterion 6, the observed-loss path.
func TestAnObservedLossRetractsTheToolsAndSaysWhy(t *testing.T) {
	h := newHarness(t)
	built := h.connected("nvda", entities.CapabilitySpeech)
	if _, err := h.controller.Connect("nvda", silent()); err != nil {
		t.Fatalf("Connect: %v", err)
	}
	built.Lifecycle.FailPingWith(ports.ErrConnectionLost)

	if err := h.controller.Verify(); !errors.Is(err, ports.ErrConnectionLost) {
		t.Fatalf("Verify = %v, want the loss reported", err)
	}

	if got := h.publisher.Published(); len(got) != 0 {
		t.Errorf("published = %v, want the gated tools retracted", got)
	}
	if h.controller.Current() != nil {
		t.Error("the connection survived a loss")
	}
	status := h.controller.Status()
	if status.State != entities.Disconnected {
		t.Errorf("state = %q, want disconnected", status.State)
	}
	if !strings.Contains(status.Reason, "lost") {
		t.Errorf("reason = %q, want it to say the connection was lost", status.Reason)
	}
}

// A refusal is not a death: protocol.md §3 says an established session survives
// a failing command, so nothing may be torn down.
func TestARefusedPingLeavesTheSessionStanding(t *testing.T) {
	h := newHarness(t)
	built := h.connected("nvda", entities.CapabilitySpeech)
	if _, err := h.controller.Connect("nvda", silent()); err != nil {
		t.Fatalf("Connect: %v", err)
	}
	built.Lifecycle.FailPingWith(errors.New("bridge refused ping: busy"))

	if err := h.controller.Verify(); err == nil {
		t.Fatal("the refusal was not reported")
	}

	if h.controller.Current() == nil {
		t.Error("a refusal ended the session; only a lost connection should")
	}
	if !h.publisher.Has("get_speech") {
		t.Error("a refusal retracted the gated tools")
	}
}

// Verifying with nothing connected is not a failed check.
func TestVerifyingWithNoSessionIsNotAFailure(t *testing.T) {
	h := newHarness(t)

	if err := h.controller.Verify(); err != nil {
		t.Errorf("Verify with no session = %v, want nil", err)
	}
}

// Acceptance criterion 6's last clause: a later connect republishes.
func TestReconnectingAfterALossPublishesAgain(t *testing.T) {
	h := newHarness(t)
	built := h.connected("nvda", entities.CapabilitySpeech)
	if _, err := h.controller.Connect("nvda", silent()); err != nil {
		t.Fatalf("Connect: %v", err)
	}
	built.Lifecycle.FailPingWith(ports.ErrConnectionLost)
	_ = h.controller.Verify()

	// A fresh session, as the bridge would serve after being restarted.
	h.connected("nvda", entities.CapabilitySpeech, entities.CapabilityBraille)
	if _, err := h.controller.Connect("nvda", silent()); err != nil {
		t.Fatalf("reconnecting: %v", err)
	}

	want := []string{"get_speech", "get_braille"}
	if got := h.publisher.Published(); !slices.Equal(got, want) {
		t.Errorf("published = %v, want %v", got, want)
	}
	if state := h.controller.Status().State; state != entities.Connected {
		t.Errorf("state = %q, want connected", state)
	}
}

// Retraction uses what was actually published, not the catalog's whole gated
// list: a reader that announced half the capabilities must not, on disconnect,
// cause tools that were never there to be withdrawn.
func TestRetractionWithdrawsOnlyWhatWasPublished(t *testing.T) {
	h := newHarness(t)
	h.connected("nvda", entities.CapabilitySpeech)
	if _, err := h.controller.Connect("nvda", silent()); err != nil {
		t.Fatalf("Connect: %v", err)
	}

	if err := h.controller.Disconnect(); err != nil {
		t.Fatalf("Disconnect: %v", err)
	}

	if slices.Contains(h.publisher.History(), "-get_braille") {
		t.Error("get_braille was retracted, though it was never published")
	}
	if !slices.Contains(h.publisher.History(), "-get_speech") {
		t.Error("get_speech was published and never retracted")
	}
}

// List joins the configured readers with the probe, and dials nothing to do it.
func TestListJoinsTheConfiguredReadersWithTheProbe(t *testing.T) {
	pipe := testsupport.Endpoint(t, "pipe:nvdaMcpBridge")
	reader := testsupport.Reader(t, "nvda", "pipe:nvdaMcpBridge", "tcp:127.0.0.1:8765")

	controller := controllers.NewConnection(
		fakes.NewFakeEndpointSource(reader),
		fakes.NewFakeEndpointProbe(pipe),
		fakes.NewFakeSessionDialer(),
		fakes.NewFakeToolPublisher(),
		catalog(),
		fakes.NewFakeClock(),
		fakes.NewFakeLog(),
	)

	listing := controller.List()

	if len(listing.Readers) != 1 || len(listing.Readers[0].Endpoints) != 2 {
		t.Fatalf("listing = %+v, want the one reader with both endpoints", listing)
	}
	if listing.Readers[0].Endpoints[0].Liveness != entities.Listening {
		t.Errorf("pipe = %q, want listening", listing.Readers[0].Endpoints[0].Liveness)
	}
	if listing.Readers[0].Endpoints[1].Liveness != entities.LivenessUnknown {
		t.Errorf("tcp = %q, want unknown", listing.Readers[0].Endpoints[1].Liveness)
	}
}

// The heartbeat keeps the CONNECTION honest. It sleeps on the Clock port, which
// is what makes it assertable at all: a fake's Sleep is an instant advance, so a
// schedule measured in tens of seconds is exercised in microseconds -- and no
// test ever calls time.Sleep.
func TestTheHeartbeatProvesTheConnectionOnASchedule(t *testing.T) {
	h := newHarness(t)
	built := h.connected("nvda", entities.CapabilitySpeech)
	if _, err := h.controller.Connect("nvda", silent()); err != nil {
		t.Fatalf("Connect: %v", err)
	}

	// Let it beat twice, then stop it from inside the third sleep -- the loop
	// re-checks stop after waking, so the third wait produces no ping.
	stop := make(chan struct{})
	sleeps := 0
	h.clock.OnSleep(func(d time.Duration) {
		if d != controllers.HeartbeatInterval {
			t.Errorf("slept %s, want the heartbeat interval %s", d, controllers.HeartbeatInterval)
		}
		sleeps++
		if sleeps == 3 {
			close(stop)
		}
	})

	h.controller.RunHeartbeat(stop)

	if built.Lifecycle.Pings() != 2 {
		t.Errorf("pinged %d times over three waits, want 2", built.Lifecycle.Pings())
	}
}

// The heartbeat is what notices a bridge that died quietly -- the agent may not
// call a tool for minutes, and until somebody notices, the gated tools are a
// promise about a reader that is gone.
func TestTheHeartbeatRetractsTheToolsWhenTheConnectionHasDied(t *testing.T) {
	h := newHarness(t)
	built := h.connected("nvda", entities.CapabilitySpeech)
	if _, err := h.controller.Connect("nvda", silent()); err != nil {
		t.Fatalf("Connect: %v", err)
	}
	built.Lifecycle.FailPingWith(ports.ErrConnectionLost)

	stop := make(chan struct{})
	sleeps := 0
	h.clock.OnSleep(func(time.Duration) {
		sleeps++
		if sleeps == 2 {
			close(stop)
		}
	})

	h.controller.RunHeartbeat(stop)

	if got := h.publisher.Published(); len(got) != 0 {
		t.Errorf("published = %v, want the gated tools retracted", got)
	}
	if h.controller.Current() != nil {
		t.Error("the dead connection is still recorded as live")
	}
}

// It runs for the PROCESS's lifetime, not a session's, so it must be harmless
// while nothing is connected rather than something to start and stop per connect.
func TestTheHeartbeatIsHarmlessWithNoSession(t *testing.T) {
	h := newHarness(t)

	stop := make(chan struct{})
	h.clock.OnSleep(func(time.Duration) { close(stop) })

	h.controller.RunHeartbeat(stop)

	if len(h.dialer.Calls()) != 0 {
		t.Error("the heartbeat dialed something; only the agent connects")
	}
}

// Shutting the process down ends a live session politely rather than dropping it
// on the bridge, which would leave the reader to notice by watchdog.
func TestClosingTheControllerEndsALiveSession(t *testing.T) {
	h := newHarness(t)
	built := h.connected("nvda", entities.CapabilitySpeech)
	if _, err := h.controller.Connect("nvda", silent()); err != nil {
		t.Fatalf("Connect: %v", err)
	}

	h.controller.Close()

	if built.Lifecycle.Byes() != 1 {
		t.Errorf("bye sent %d times on shutdown, want once", built.Lifecycle.Byes())
	}
}
