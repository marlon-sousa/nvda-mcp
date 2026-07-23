// screenreader-mcp domain -- the Dispatcher's tests.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// The dispatcher's own behaviour is small, and one part of it carries weight: a
// tool call is usually how a dead connection is discovered FIRST, long before the
// next heartbeat, so the loss has to reach the controller from here or the gated
// tools stay advertised for a reader that is gone.
package tools_test

import (
	"encoding/json"
	"errors"
	"fmt"
	"testing"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/controllers/tools"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
	"github.com/marlon-sousa/screen-readers-mcp/server/fakes"
	"github.com/marlon-sousa/screen-readers-mcp/server/testsupport"
)

// scriptedTool is a tool that fails however a test tells it to.
//
// A stand-in rather than a real gated tool on purpose: what is under test is
// what the DISPATCHER does with a failure, so the failure should be stated
// outright instead of arranged through whichever real tool happens to reach the
// path.
type scriptedTool struct {
	err error
}

func (s *scriptedTool) Name() string                    { return "scripted" }
func (s *scriptedTool) Capability() entities.Capability { return entities.CapabilityGestures }
func (s *scriptedTool) Description() string             { return "a tool that fails on demand" }
func (s *scriptedTool) InputSchema() json.RawMessage    { return json.RawMessage(`{"type":"object"}`) }

func (s *scriptedTool) Execute(tools.ToolContext, json.RawMessage) (any, error) {
	if s.err != nil {
		return nil, s.err
	}
	return map[string]any{"ok": true}, nil
}

func dispatcherOver(control tools.ConnectionControl, list ...tools.Tool) *tools.Dispatcher {
	return tools.NewDispatcher(
		tools.NewRegistry(list...), control, fakes.NewFakeClock(), fakes.NewFakeLog(),
	)
}

func TestDispatchRunsTheNamedTool(t *testing.T) {
	control := fakes.NewFakeConnectionControl()
	control.SetListing(entities.BuildListing(
		[]entities.ConfiguredReader{{Name: "nvda"}}, nil,
	))
	dispatch := tools.NewDispatcher(
		tools.BuildRegistry(), control, fakes.NewFakeClock(), fakes.NewFakeLog(),
	)

	result, err := dispatch.Execute("list_readers", nil)
	if err != nil {
		t.Fatalf("Execute: %v", err)
	}
	if result == nil {
		t.Fatal("Execute returned no result")
	}
}

// Unreachable through the MCP adapter, which only dispatches names it took from
// the registry -- so reaching it means the wiring is wrong, not the agent.
func TestAnUnknownToolNameIsRejected(t *testing.T) {
	dispatch := dispatcherOver(fakes.NewFakeConnectionControl())

	_, err := dispatch.Execute("nonsense", nil)
	if !errors.Is(err, tools.ErrUnknownTool) {
		t.Errorf("Execute(nonsense) = %v, want ErrUnknownTool", err)
	}
}

// The context is built FRESH per call from the controller's current connection,
// so a tool can never be handed a session that ended between tools/list and now.
func TestTheContextCarriesTheControllersCurrentConnection(t *testing.T) {
	control := fakes.NewFakeConnectionControl()
	built := testsupport.NewConnection("nvda", entities.CapabilityGestures)
	control.SetConnection(built.Connection)

	tool := &scriptedTool{}
	if _, err := dispatcherOver(control, tool).Execute(tool.Name(), nil); err != nil {
		t.Fatalf("Execute: %v", err)
	}

	// With the connection dropped, the very same dispatcher must build a
	// context with no session -- proving the context is not captured once.
	if err := control.Disconnect(); err != nil {
		t.Fatalf("Disconnect: %v", err)
	}
	tool.err = &tools.CapabilityError{Tool: tool.Name(), Capability: entities.CapabilityGestures}
	if _, err := dispatcherOver(control, tool).Execute(tool.Name(), nil); err == nil {
		t.Error("the tool succeeded with no session")
	}
}

// The rule this controller exists for.
func TestALostConnectionSeenByAToolIsReportedToTheController(t *testing.T) {
	control := fakes.NewFakeConnectionControl()
	built := testsupport.NewConnection("nvda", entities.CapabilityGestures)
	control.SetConnection(built.Connection)

	tool := &scriptedTool{err: fmt.Errorf("pressGesture: %w", ports.ErrConnectionLost)}
	_, err := dispatcherOver(control, tool).Execute(tool.Name(), nil)

	if !errors.Is(err, ports.ErrConnectionLost) {
		t.Fatalf("Execute = %v, want the loss reported to the caller too", err)
	}
	if control.Verifies() != 1 {
		t.Errorf("the controller was told about the loss %d times, want once: "+
			"until it is told, the gated tools stay advertised for a reader that is gone",
			control.Verifies())
	}
}

// An ordinary refusal by a HEALTHY bridge must tear nothing down: protocol.md §3
// says an established session survives a failing command.
func TestAnOrdinaryToolFailureDoesNotReCheckTheConnection(t *testing.T) {
	control := fakes.NewFakeConnectionControl()
	built := testsupport.NewConnection("nvda", entities.CapabilityGestures)
	control.SetConnection(built.Connection)

	tool := &scriptedTool{err: errors.New("bridge refused pressGesture: unknown gesture id")}
	if _, err := dispatcherOver(control, tool).Execute(tool.Name(), nil); err == nil {
		t.Fatal("the refusal was not reported")
	}

	if control.Verifies() != 0 {
		t.Error("an ordinary refusal cost a ping round trip; only a lost " +
			"connection should trigger one")
	}
}
