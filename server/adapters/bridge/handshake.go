// screenreader-mcp adapters -- Handshake: the SessionDialer.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: adapter. IMPLEMENTS the domain's SessionDialer port: try one reader's
// endpoints in declared order, complete `hello` with the first that answers, and
// hand back a ReaderConnection carrying exactly the capability ports that reader
// announced.
// DEPENDS ON: a dialer factory (adapters/bridge/endpoint.go in production, a
// fake in tests), the JSON-lines client, the generated wire binding, and the
// Clock and Log ports.
// BUILT BY: wiring/wiring.go.
// USED BY: 10b's connection controller, and only ever because an agent asked --
// this server never dials on its own.
//
// This is the one place that maps `hello`'s wire result into domain vocabulary,
// and the one place that compares protocol versions.
package bridge

import (
	"errors"
	"fmt"

	adapterports "github.com/marlon-sousa/screen-readers-mcp/server/adapters/ports"
	"github.com/marlon-sousa/screen-readers-mcp/server/adapters/wire"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// DialerFactory turns an endpoint into a way to reach it.
//
// A seam rather than a direct call to DialerFor, so that the ordered-endpoint
// policy in this file is unit-tested against scripted connections with no OS
// involved. Production wiring passes DialerFor.
type DialerFactory func(entities.Endpoint) (adapterports.Dialer, error)

// Handshake dials and completes `hello`.
type Handshake struct {
	dialerFor DialerFactory
	clock     ports.Clock
	log       ports.Log
}

var _ ports.SessionDialer = (*Handshake)(nil)

// NewHandshake builds the dialer. Stateless between calls: everything a session
// needs lives in the ReaderConnection it returns, so there is no "current
// reader" anywhere in this process.
func NewHandshake(dialerFor DialerFactory, clock ports.Clock, log ports.Log) *Handshake {
	return &Handshake{dialerFor: dialerFor, clock: clock, log: log}
}

// Dial tries each of the reader's endpoints in declared order.
//
// The order is the user's transport toggle made invisible: spec 0011's dialog
// switches the NVDA bridge between named pipe and loopback TCP, and trying both
// in the order the reader declared them means neither the agent nor the user has
// to configure anything when it is switched.
func (h *Handshake) Dial(reader entities.ConfiguredReader, opts ports.SessionOptions) (*ports.ReaderConnection, error) {
	if opts.Mode == "" {
		// Not defaulted here: the capture mode is fixed for the session's
		// whole lifetime, so the party that knows what the session is for
		// chooses it. An adapter inventing a default would be that choice
		// made by the wrong layer.
		return nil, errors.New("capture mode is required")
	}
	if len(reader.Endpoints) == 0 {
		return nil, fmt.Errorf("reader %q has no configured endpoints", reader.Name)
	}

	var failures []error
	for _, endpoint := range reader.Endpoints {
		connection, err := h.dialOne(endpoint, opts)
		if err == nil {
			h.log.Infof("connected to %q over %s", connection.Session.Reader.Name, endpoint)
			return connection, nil
		}

		var mismatch *ports.ProtocolMismatchError
		if errors.As(err, &mismatch) {
			// A bridge ANSWERED; the disagreement is about versions, not
			// about reachability. Trying the next endpoint would most
			// likely reach the same bridge over its other transport and
			// bury the real answer under a second, vaguer failure.
			return nil, err
		}
		h.log.Debugf("reader %q: endpoint %s did not answer: %v", reader.Name, endpoint, err)
		failures = append(failures, fmt.Errorf("%s: %w", endpoint, err))
	}
	return nil, fmt.Errorf("reader %q: no endpoint answered: %w", reader.Name, errors.Join(failures...))
}

// dialOne opens one endpoint and completes the handshake over it.
func (h *Handshake) dialOne(endpoint entities.Endpoint, opts ports.SessionOptions) (*ports.ReaderConnection, error) {
	dial, err := h.dialerFor(endpoint)
	if err != nil {
		return nil, err
	}
	transport, err := dial()
	if err != nil {
		return nil, err
	}
	client := NewJSONLinesClient(transport, h.clock, h.log)
	connection, err := h.hello(client, endpoint, opts)
	if err != nil {
		// Nothing was established, so nothing is owed a `bye`; dropping the
		// connection is both the correct teardown and the one that cannot
		// hang waiting for a peer that is already unhappy.
		_ = client.Close()
		return nil, err
	}
	return connection, nil
}

// hello sends the handshake and turns its reply into domain vocabulary.
func (h *Handshake) hello(client *JSONLinesClient, endpoint entities.Endpoint, opts ports.SessionOptions) (*ports.ReaderConnection, error) {
	params := wire.HelloParams{
		Mode:            wire.CaptureMode(opts.Mode),
		ProtocolVersion: wire.ProtocolVersion,
	}
	if opts.LogLevel != nil {
		level := wire.LogLevel(*opts.LogLevel)
		params.LogLevel = &level
	}

	var result wire.HelloResult
	if err := client.call(wire.CommandHello, params, &result, DefaultCallTimeout); err != nil {
		return nil, err
	}

	if !wire.Supports(result.ProtocolVersion) {
		return nil, &ports.ProtocolMismatchError{
			BridgeVersion:  result.ProtocolVersion,
			ServerVersions: wire.SupportedVersions(),
		}
	}

	announced := make([]string, len(result.Capabilities))
	for i, capability := range result.Capabilities {
		// Unknown capability strings survive as members of the domain set
		// (protocol.md §4 says a consumer must ignore what it does not
		// know, which is not the same as discarding it): the set is what
		// `screenreader://info` reports, and a reader deserves to be
		// described honestly even where this server has no tool to match.
		announced[i] = string(capability)
	}
	capabilities := entities.NewSet(announced)

	session := entities.ReaderSession{
		Reader: entities.ReaderIdentity{
			Name:    result.Reader.Name,
			Version: result.Reader.Version,
		},
		Capabilities:    capabilities,
		Mode:            entities.CaptureMode(result.Mode),
		Synth:           result.Synth,
		LogPath:         result.LogPath,
		ReaderLogPath:   result.NVDALogPath,
		ProtocolVersion: result.ProtocolVersion,
	}

	connection := &ports.ReaderConnection{
		Session:   session,
		Endpoint:  endpoint,
		Lifecycle: client,
	}
	// The capability gate, expressed structurally: a port is handed over only
	// when the reader announced it, so a reader without braille yields a nil
	// collaborator rather than a method that exists and fails.
	if capabilities.Has(entities.CapabilitySpeech) {
		connection.Speech = client
	}
	if capabilities.Has(entities.CapabilityBraille) {
		connection.Braille = client
	}
	if capabilities.Has(entities.CapabilityGestures) {
		connection.Gestures = client
	}
	if capabilities.Has(entities.CapabilityFocus) {
		connection.Focus = client
	}
	if capabilities.Has(entities.CapabilityState) {
		connection.State = client
	}
	if capabilities.Has(entities.CapabilityConfig) {
		connection.Config = client
	}
	return connection, nil
}
