// screenreader-mcp testsupport -- builders for a live ReaderConnection.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: test scaffolding, NOT a port double -- doubles live in fakes/ and this
// package is deliberately everything else (AGENTS.md).
// USED BY: the connection controller's tests and the tool controllers' tests,
// both of which need "a session with these capabilities" without a bridge.
//
// A builder rather than a fixture, because every test customises it: which
// capabilities were announced is the variable the whole capability gate turns
// on, so it is stated per test rather than defaulted somewhere out of sight.
package testsupport

import (
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
	"github.com/marlon-sousa/screen-readers-mcp/server/fakes"
)

// Connection is a live session with fake collaborators behind it.
//
// The capability ports are handed over EXACTLY for the capabilities named, and
// left nil otherwise -- mirroring what the real handshake does, which is what
// makes "this reader has no braille" a missing collaborator here too rather than
// a flag a test sets.
type Connection struct {
	// Connection is what the code under test is given.
	Connection *ports.ReaderConnection

	// The fakes behind it, for seeding answers and asserting on interaction.
	// Each is nil unless its capability was announced.
	Lifecycle *fakes.FakeSessionLifecycle
	Speech    *fakes.FakeSpeechReader
	Braille   *fakes.FakeBrailleReader
	Gestures  *fakes.FakeGestureSender
	Focus     *fakes.FakeFocusInspector
	State     *fakes.FakeStateInspector
	Config    *fakes.FakeConfigAccessor
}

// NewConnection builds a session for a reader announcing exactly these
// capabilities.
//
// The endpoint and identity are fixed and unremarkable on purpose: a test that
// cares about them says so by reading them back, and one that does not is not
// made to invent them.
func NewConnection(reader string, announced ...entities.Capability) *Connection {
	names := make([]string, len(announced))
	for i, capability := range announced {
		names[i] = string(capability)
	}
	set := entities.NewSet(names)

	built := &Connection{Lifecycle: fakes.NewFakeSessionLifecycle()}
	built.Connection = &ports.ReaderConnection{
		Session: entities.ReaderSession{
			Reader:          entities.ReaderIdentity{Name: reader, Version: "1.0"},
			Capabilities:    set,
			Mode:            entities.CaptureSilent,
			Synth:           "fakesynth",
			LogPath:         `C:\logs\session.log`,
			ReaderLogPath:   `C:\logs\reader.log`,
			ProtocolVersion: 1,
		},
		Endpoint:  entities.Endpoint{Kind: entities.TransportPipe, Address: reader + "McpBridge"},
		Lifecycle: built.Lifecycle,
	}

	if set.Has(entities.CapabilitySpeech) {
		built.Speech = fakes.NewFakeSpeechReader()
		built.Connection.Speech = built.Speech
	}
	if set.Has(entities.CapabilityBraille) {
		built.Braille = fakes.NewFakeBrailleReader()
		built.Connection.Braille = built.Braille
	}
	if set.Has(entities.CapabilityGestures) {
		built.Gestures = fakes.NewFakeGestureSender()
		built.Connection.Gestures = built.Gestures
	}
	if set.Has(entities.CapabilityFocus) {
		built.Focus = fakes.NewFakeFocusInspector()
		built.Connection.Focus = built.Focus
	}
	if set.Has(entities.CapabilityState) {
		built.State = fakes.NewFakeStateInspector()
		built.Connection.State = built.State
	}
	if set.Has(entities.CapabilityConfig) {
		built.Config = fakes.NewFakeConfigAccessor()
		built.Connection.Config = built.Config
	}
	return built
}

// EveryCapability is the six groups the wire contract defines, for the tests
// whose subject is not the gate.
func EveryCapability() []entities.Capability {
	return []entities.Capability{
		entities.CapabilitySpeech, entities.CapabilityBraille, entities.CapabilityGestures,
		entities.CapabilityFocus, entities.CapabilityState, entities.CapabilityConfig,
	}
}
