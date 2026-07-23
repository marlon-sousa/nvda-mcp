// screenreader-mcp domain -- Connection: the session lifecycle controller.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: controller. Owns the whole agent-initiated connection lifecycle: List,
// Connect, Disconnect, loss detection, and the heartbeat.
// DEPENDS ON (all ports): EndpointSource, EndpointProbe, SessionDialer,
// ToolPublisher, Clock, Log -- plus the ToolCatalog entity, which decides which
// names to publish.
// BUILT BY: wiring/wiring.go. USED BY: the four ungated tool controllers,
// through the narrow ConnectionControl interface they declare.
//
// THE ONLY STATEFUL THING IN THIS PROCESS, and it is an ordinary value owned by
// wiring -- not a package global, no init() side effect, no singleton. That is
// the constraint that keeps concurrent sessions reachable later as a map plus a
// routing parameter rather than as an unpicking of globals.
//
// NO RETRY POLICY AND NO BACKOFF. A failed connect returns the error to the
// agent and leaves the state Disconnected. A background retry loop was
// considered and rejected: it buys "the tools are there when you look" at the
// price of connection state changing under the agent mid-task, a reconnect
// racing a teardown, and a give-up policy nobody asked for.
package controllers

import (
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// HeartbeatInterval is how often the connection is proved real while a session
// is live.
//
// It keeps the CONNECTION honest without keeping an idle SESSION alive: the
// bridge's heartbeat watchdog is reset by any message, but its command
// inactivity watchdog is deliberately not reset by `ping` (protocol.md §6). An
// abandoned session therefore still ends, which is the contract working as
// intended.
const HeartbeatInterval = 20 * time.Second

// Connection is the one connection's lifecycle.
type Connection struct {
	endpoints ports.EndpointSource
	probe     ports.EndpointProbe
	dialer    ports.SessionDialer
	publisher ports.ToolPublisher
	catalog   entities.ToolCatalog
	clock     ports.Clock
	log       ports.Log

	// Everything below is the state, and the mutex is not optional: the
	// heartbeat goroutine and a tool call reach it at the same time.
	mu         sync.Mutex
	status     entities.ConnectionStatus
	connection *ports.ReaderConnection
	published  []string
}

// NewConnection builds the controller, disconnected and having dialed nothing.
func NewConnection(
	endpoints ports.EndpointSource,
	probe ports.EndpointProbe,
	dialer ports.SessionDialer,
	publisher ports.ToolPublisher,
	catalog entities.ToolCatalog,
	clock ports.Clock,
	log ports.Log,
) *Connection {
	return &Connection{
		endpoints: endpoints,
		probe:     probe,
		dialer:    dialer,
		publisher: publisher,
		catalog:   catalog,
		clock:     clock,
		log:       log,
		status:    entities.ConnectionStatus{State: entities.Disconnected},
	}
}

// List joins the configured readers with the probe's answer.
//
// It DIALS NOTHING. The bridge serves one session at a time, so a probing
// connection would occupy the very slot the agent is about to want -- which is
// why a TCP endpoint honestly reports "unknown" rather than being tested.
func (c *Connection) List() entities.ReaderListing {
	readers := c.endpoints.Readers()

	var candidates []entities.Endpoint
	for _, reader := range readers {
		candidates = append(candidates, reader.Endpoints...)
	}
	return entities.BuildListing(readers, c.probe.Live(candidates))
}

// Connect opens the one session.
func (c *Connection) Connect(readerName string, opts ports.SessionOptions) (*ports.ReaderConnection, error) {
	reader, err := c.find(readerName)
	if err != nil {
		return nil, err
	}

	c.mu.Lock()
	if c.connection != nil {
		live := c.connection.Session.Reader.Name
		c.mu.Unlock()
		// An error rather than a silent switch: switching would pull the
		// session out from under whatever multi-step task is using it, and
		// the agent that wanted a different reader can say so explicitly.
		return nil, fmt.Errorf(
			"a session with %q is already live; call disconnect_reader first", live)
	}
	c.status = entities.ConnectionStatus{State: entities.Connecting}
	c.mu.Unlock()

	connection, err := c.dialer.Dial(reader, opts)
	if err != nil {
		c.recordFailure(err)
		return nil, err
	}

	// The gate. Names come from the catalog, keyed on what `hello` announced
	// and on nothing else -- no reader name reaches this decision.
	names := c.catalog.Allowed(connection.Session.Capabilities)

	c.mu.Lock()
	c.connection = connection
	c.published = names
	c.status = entities.ConnectionStatus{State: entities.Connected}
	c.mu.Unlock()

	c.publisher.Publish(names)
	c.log.Infof("connected to %q over %s; published %d tool(s)",
		connection.Session.Reader.Name, connection.Endpoint, len(names))
	return connection, nil
}

// Disconnect ends the session politely and retracts the gated tools.
//
// Not an error when nothing is connected: teardown is reached from several
// directions and none of them should have to check first.
func (c *Connection) Disconnect() error {
	c.mu.Lock()
	connection := c.connection
	c.mu.Unlock()

	if connection == nil {
		return nil
	}

	// `bye` first, then the drop. Bye already treats an already-gone peer as
	// success, so a bridge that died a moment ago still yields a clean
	// disconnect rather than an error the agent can do nothing about.
	byeErr := connection.Lifecycle.Bye()
	closeErr := connection.Lifecycle.Close()

	c.clear(entities.ConnectionStatus{State: entities.Disconnected})

	if byeErr != nil {
		c.log.Debugf("bye failed on disconnect: %v", byeErr)
	}
	if closeErr != nil {
		c.log.Debugf("closing the connection failed: %v", closeErr)
	}
	return nil
}

// Status is the recorded state and why it holds.
func (c *Connection) Status() entities.ConnectionStatus {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.status
}

// Current is the live connection, or nil.
func (c *Connection) Current() *ports.ReaderConnection {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.connection
}

// Verify makes a real round trip and records a loss it finds.
//
// This is the method that makes `status` proof rather than memory, and it is
// also what a tool call falls back on when it discovers the connection has gone.
// Nil when there is nothing to verify: "no session" is not a failed check.
func (c *Connection) Verify() error {
	c.mu.Lock()
	connection := c.connection
	c.mu.Unlock()

	if connection == nil {
		return nil
	}

	err := connection.Lifecycle.Ping()
	if err == nil {
		return nil
	}
	if errors.Is(err, ports.ErrConnectionLost) {
		c.lose(err)
		return err
	}
	// A bridge that ANSWERED, with a refusal, is still there: protocol.md §3
	// says an established session survives a failing command, so this must
	// not tear anything down.
	c.log.Debugf("ping was refused but the connection is alive: %v", err)
	return err
}

// RunHeartbeat proves the connection real on a schedule, until stop is closed.
//
// Run by wiring in a goroutine rather than started implicitly on connect. Two
// reasons: a loop nobody can step is a loop no test can assert on -- this one
// sleeps on the Clock port, so a fake drives it deterministically -- and the
// heartbeat's lifetime is the PROCESS's, not a session's, so starting and
// stopping it per connect would be bookkeeping with nothing to gain.
func (c *Connection) RunHeartbeat(stop <-chan struct{}) {
	for {
		select {
		case <-stop:
			return
		default:
		}

		c.clock.Sleep(HeartbeatInterval)

		select {
		case <-stop:
			return
		default:
		}

		// Verify is a no-op with no session, so the loop needs no state of
		// its own and cannot disagree with the controller about whether one
		// is live.
		_ = c.Verify()
	}
}

// Close is the process shutting down: end the session if there is one, without
// asking the agent.
func (c *Connection) Close() {
	_ = c.Disconnect()
}

// find resolves a reader name against the configured set.
func (c *Connection) find(name string) (entities.ConfiguredReader, error) {
	readers := c.endpoints.Readers()
	for _, reader := range readers {
		if reader.Name == name {
			return reader, nil
		}
	}

	// The error LISTS the known names, so an agent that guessed wrong
	// self-corrects in the same turn rather than spending one on list_readers.
	known := make([]string, 0, len(readers))
	for _, reader := range readers {
		known = append(known, reader.Name)
	}
	if len(known) == 0 {
		return entities.ConfiguredReader{}, fmt.Errorf(
			"unknown reader %q: no readers are configured", name)
	}
	return entities.ConfiguredReader{}, fmt.Errorf(
		"unknown reader %q: known readers are %v", name, known)
}

// recordFailure records why a connect did not happen.
//
// A protocol mismatch gets its own state, because the remedy is different --
// update one of the two components rather than try again -- and because the
// process deliberately stays up so `status` can keep saying so.
func (c *Connection) recordFailure(err error) {
	state := entities.Disconnected

	var mismatch *ports.ProtocolMismatchError
	if errors.As(err, &mismatch) {
		state = entities.Incompatible
	}

	c.mu.Lock()
	defer c.mu.Unlock()
	c.status = entities.ConnectionStatus{State: state, Reason: err.Error()}
	c.log.Errorf("connect failed: %v", err)
}

// lose records an observed connection loss: the tools go away and the state says
// why. The agent is free to connect again whenever it chooses -- this server
// will not do it on its own.
func (c *Connection) lose(cause error) {
	c.mu.Lock()
	connection := c.connection
	c.mu.Unlock()

	if connection == nil {
		return
	}
	_ = connection.Lifecycle.Close()

	c.clear(entities.ConnectionStatus{
		State:  entities.Disconnected,
		Reason: fmt.Sprintf("the connection to %q was lost: %v", connection.Session.Reader.Name, cause),
	})
	c.log.Infof("connection to %q lost: %v", connection.Session.Reader.Name, cause)
}

// clear drops the session and retracts whatever was published for it.
//
// The retraction uses the names that were actually PUBLISHED rather than the
// catalog's full gated list, so a reader that announced half the capabilities
// does not, on disconnect, cause a retraction of tools that were never there.
func (c *Connection) clear(status entities.ConnectionStatus) {
	c.mu.Lock()
	names := c.published
	c.connection = nil
	c.published = nil
	c.status = status
	c.mu.Unlock()

	if len(names) > 0 {
		c.publisher.Retract(names)
	}
}
