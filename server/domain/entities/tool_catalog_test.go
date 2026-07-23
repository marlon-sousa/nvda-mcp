// screenreader-mcp domain -- ToolCatalog's tests.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// Black-box (package entities_test), exercising the gate through the surface the
// connection controller uses.
//
// The catalog is where acceptance criterion 10's first clause is decided -- "a
// tool whose capability is absent is NOT advertised" -- so these tests are the
// gate's own proof, and the integration tier's no-braille scenario is the proof
// that the decision actually reaches the wire.
package entities_test

import (
	"slices"
	"testing"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
)

// A catalog shaped like the real one: four ungated tools plus a few gated ones
// spanning three capabilities, one of which has two tools.
func catalog() entities.ToolCatalog {
	return entities.NewToolCatalog([]entities.ToolGate{
		{Name: "list_readers"},
		{Name: "connect_reader"},
		{Name: "disconnect_reader"},
		{Name: "status"},
		{Name: "get_speech", Capability: entities.CapabilitySpeech},
		{Name: "get_last_speech", Capability: entities.CapabilitySpeech},
		{Name: "get_braille", Capability: entities.CapabilityBraille},
		{Name: "press_gesture", Capability: entities.CapabilityGestures},
	})
}

func TestTheUngatedToolsAreTheOnesNoCapabilityGates(t *testing.T) {
	want := []string{"list_readers", "connect_reader", "disconnect_reader", "status"}
	if got := catalog().Ungated(); !slices.Equal(got, want) {
		t.Errorf("Ungated() = %v, want %v", got, want)
	}
}

// The gate itself: a reader without braille never gets the braille tool.
func TestOnlyToolsTheAnnouncedCapabilitiesPermitAreAllowed(t *testing.T) {
	announced := entities.NewSet([]string{"speech", "gestures"})

	want := []string{"get_speech", "get_last_speech", "press_gesture"}
	if got := catalog().Allowed(announced); !slices.Equal(got, want) {
		t.Errorf("Allowed(speech+gestures) = %v, want %v", got, want)
	}
}

// The ungated four must survive a disconnect: they are how an agent reconnects,
// so a gate that swept them up would strand it.
func TestAllowedNeverIncludesTheUngatedTools(t *testing.T) {
	everything := entities.NewSet([]string{"speech", "braille", "gestures", "focus", "state", "config"})

	for _, name := range catalog().Allowed(everything) {
		if slices.Contains(catalog().Ungated(), name) {
			t.Errorf("Allowed() returned the ungated tool %q; a disconnect would retract it", name)
		}
	}
}

// A reader that announced nothing gets no gated tools at all -- and, in
// particular, the empty announcement is not mistaken for "announced everything".
func TestAReaderAnnouncingNothingGetsNoGatedTools(t *testing.T) {
	if got := catalog().Allowed(entities.NewSet(nil)); len(got) != 0 {
		t.Errorf("Allowed(nothing) = %v, want none", got)
	}
}

// protocol.md §4: an unknown capability string must be ignored, not rejected and
// not treated as matching something.
func TestAnUnknownAnnouncedCapabilityAdvertisesNothing(t *testing.T) {
	announced := entities.NewSet([]string{"telepathy"})

	if got := catalog().Allowed(announced); len(got) != 0 {
		t.Errorf("Allowed(unknown) = %v, want none", got)
	}
}

func TestGatedIsEveryGatedToolWhateverWasAnnounced(t *testing.T) {
	want := []string{"get_speech", "get_last_speech", "get_braille", "press_gesture"}
	if got := catalog().Gated(); !slices.Equal(got, want) {
		t.Errorf("Gated() = %v, want %v", got, want)
	}
}

// The backstop's question: is this name one of ours, and what gated it?
func TestCapabilityOfDistinguishesOurToolsFromStrangers(t *testing.T) {
	capability, known := catalog().CapabilityOf("get_braille")
	if !known || capability != entities.CapabilityBraille {
		t.Errorf("CapabilityOf(get_braille) = %q, %v; want braille, true", capability, known)
	}

	capability, known = catalog().CapabilityOf("list_readers")
	if !known || capability != "" {
		t.Errorf("CapabilityOf(list_readers) = %q, %v; want ungated, true", capability, known)
	}

	if _, known := catalog().CapabilityOf("nonsense"); known {
		t.Error("CapabilityOf(nonsense) claimed to know a tool that does not exist")
	}
}

func TestCapabilitiesAreTheDistinctGatesSorted(t *testing.T) {
	want := []entities.Capability{
		entities.CapabilityBraille, entities.CapabilityGestures, entities.CapabilitySpeech,
	}
	if got := catalog().Capabilities(); !slices.Equal(got, want) {
		t.Errorf("Capabilities() = %v, want %v", got, want)
	}
}

// The catalog must not be a window onto its caller's slice: a table that could
// be edited after it was built is not a decision table.
func TestTheCatalogCopiesTheGatesItWasGiven(t *testing.T) {
	gates := []entities.ToolGate{{Name: "get_braille", Capability: entities.CapabilityBraille}}
	built := entities.NewToolCatalog(gates)

	gates[0].Name = "mutated"

	if got := built.Gated(); !slices.Equal(got, []string{"get_braille"}) {
		t.Errorf("Gated() = %v after the caller edited its slice; want the built table", got)
	}
}
