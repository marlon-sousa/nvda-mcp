// screenreader-mcp tools -- tests for the wire binding generator.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// WHITE-BOX (`package main`, not `main_test`), and forced rather than chosen:
// the generator is a command, so its `run` is unexported and unreachable from an
// external test package. AGENTS.md allows white-box where an unexported helper
// deserves direct coverage and the header says why -- this is that case.
//
// WHY THESE TESTS EXIST, given the drift gate already regenerates and diffs the
// committed binding in CI: the gate only ever sees TODAY's schema. It proves the
// committed output matches the current input, and says nothing about whether the
// mapping is correct for input the contract does not have yet -- which is
// precisely when the mapper will next be exercised, during a protocol change,
// with attention elsewhere. Two mapping bugs were caught by eye while writing
// this generator (an optional-and-nullable field emitted as `**T`, and an
// initialism spelled `Io`); neither would have failed the build, vet,
// staticcheck or the drift gate.
//
// So the fixture in testdata/contract.json deliberately contains constructs the
// REAL v1 schema does not: an optional-and-nullable field, an array of $ref, an
// array of enum, an open value and an open object. Those are the paths that are
// unexercised today and will be reached without warning tomorrow.
package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const (
	fixtureSchema = "testdata/contract.json"
	goldenOutput  = "testdata/expected.go.txt"
)

// generateFixture runs the whole tool over the fixture and returns what it
// wrote. The whole tool, including gofmt, because formatting is part of the
// output the drift gate compares byte for byte.
func generateFixture(t *testing.T) string {
	t.Helper()
	out := filepath.Join(t.TempDir(), "fixture.go")
	if err := run(fixtureSchema, out, "fixture"); err != nil {
		t.Fatalf("generating from %s: %v", fixtureSchema, err)
	}
	produced, err := os.ReadFile(out)
	if err != nil {
		t.Fatalf("reading generated file: %v", err)
	}
	return string(produced)
}

// unaligned collapses gofmt's column padding to single spaces, so a test can
// assert on a field declaration without also pinning how wide its neighbours
// happen to be. Alignment is real output and the golden file keeps it; it is
// just not what these assertions are about.
func unaligned(source string) string {
	return strings.Join(strings.Fields(source), " ")
}

// The golden test. Any change to the mapping shows up here as a readable diff,
// in a fixture that is small enough to read -- unlike the real binding, where a
// mapping change and a contract change look alike.
func TestGeneratedOutputMatchesTheGoldenFile(t *testing.T) {
	produced := generateFixture(t)

	want, err := os.ReadFile(goldenOutput)
	if err != nil {
		t.Fatalf("reading %s: %v", goldenOutput, err)
	}
	if produced != string(want) {
		t.Errorf(
			"generated output differs from %s.\n"+
				"If the change is intended, regenerate the golden file:\n"+
				"  go -C server/tools/wiregen run . -schema %s -out %s -package fixture\n\n"+
				"--- got ---\n%s",
			goldenOutput, fixtureSchema, goldenOutput, produced,
		)
	}
}

// The bug that was caught by eye. A field that is BOTH nullable in the schema
// and absent from `required` must be one pointer, not two: `**T` expresses a
// third state ("present, but null") that the contract does not have, and it
// would marshal a nil inner pointer as `null` rather than omitting the key.
func TestAnOptionalNullableFieldIsASinglePointer(t *testing.T) {
	produced := generateFixture(t)

	if strings.Contains(produced, "**") {
		t.Errorf("generated output contains a double pointer:\n%s", produced)
	}
	if !strings.Contains(unaligned(produced), "OptionalNullable *int `json:\"optionalNullable,omitempty\"`") {
		t.Error("an optional, nullable integer did not come out as a single pointer with omitempty")
	}
}

// A field that is nullable but REQUIRED must stay in the encoding: `null` is the
// answer, and omitting the key would be a different answer.
func TestARequiredNullableFieldIsNotOmitted(t *testing.T) {
	produced := generateFixture(t)

	if !strings.Contains(unaligned(produced), "RequiredNullable *string `json:\"requiredNullable\"`") {
		t.Error("a required, nullable string was not emitted as a pointer without omitempty")
	}
}

// Shapes the contract deliberately leaves OPEN carry reader-specific vocabulary,
// so they must ride through as raw bytes rather than being decoded into
// something this server has an opinion about.
func TestOpenShapesBecomeRawJSON(t *testing.T) {
	produced := generateFixture(t)

	for _, want := range []string{
		"Opaque json.RawMessage `json:\"opaque\"`",
		"Bag json.RawMessage `json:\"bag\"`",
	} {
		if !strings.Contains(unaligned(produced), want) {
			t.Errorf("missing %q -- an open shape was given a concrete type", want)
		}
	}
}

// The version comes from the DOCUMENT, not from a constant in the generator: a
// fixture declaring protocolVersion 7 must produce 7, or the binding could
// silently claim to speak a version the contract never described.
func TestTheProtocolVersionComesFromTheSchema(t *testing.T) {
	produced := generateFixture(t)

	if !strings.Contains(produced, "const ProtocolVersion = 7") {
		t.Error("the fixture's protocolVersion 7 did not reach the generated constant")
	}
}

// An enum the naming table does not know is a HARD ERROR, not a fall-back to
// plain string. A new closed value set in the contract deserves a deliberate Go
// name, and failing the generator is how that decision gets asked for -- so this
// test guards a design choice that would otherwise rot silently into `string`.
func TestAnUnnamedEnumFailsTheGenerator(t *testing.T) {
	schema := filepath.Join(t.TempDir(), "unnamed_enum.json")
	contents := `{
		"protocolVersion": 1,
		"$defs": {
			"Thing": {
				"type": "object",
				"properties": {
					"colour": {"type": "string", "enum": ["red", "green"]}
				},
				"required": ["colour"],
				"additionalProperties": true
			}
		},
		"commands": {}
	}`
	if err := os.WriteFile(schema, []byte(contents), 0o644); err != nil {
		t.Fatalf("writing the fixture: %v", err)
	}

	err := run(schema, filepath.Join(t.TempDir(), "out.go"), "fixture")

	if err == nil {
		t.Fatal("an enum with no Go type name was accepted; it must fail loudly")
	}
	if !strings.Contains(err.Error(), "enumNames") {
		t.Errorf("error %q does not say where to add the name", err)
	}
}

// A field name whose leading run is an initialism is spelled in caps. The value
// is small; the reason to pin it is that `Io` versus `IO` is invisible in review
// and permanent in a published binding.
func TestLeadingInitialismsAreCapitalised(t *testing.T) {
	produced := generateFixture(t)

	for _, want := range []string{"ID int", "OK bool", "NVDALogPath string"} {
		if !strings.Contains(unaligned(produced), want) {
			t.Errorf("missing %q -- a leading initialism was not spelled in caps", want)
		}
	}
}

// The output must be gofmt-clean, since the drift gate compares bytes: an
// unformatted emission would diff on every run for reasons that have nothing to
// do with the contract.
func TestGeneratedOutputIsFormatted(t *testing.T) {
	produced := generateFixture(t)

	if strings.Contains(produced, "\t \t") || strings.Contains(produced, " \n") {
		t.Error("generated output carries stray whitespace; format.Source did not run")
	}
	if !strings.HasSuffix(produced, "}\n") {
		t.Error("generated output does not end in a single newline after the last declaration")
	}
}
