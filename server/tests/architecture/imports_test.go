// screenreader-mcp tests -- the import boundaries.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: architecture test. Two import boundaries that review would otherwise
// have to hold on its own: acceptance criterion 12 -- nothing under domain/
// imports adapters/wire or the MCP SDK -- and the rule that only tests may
// import the fakes.
//
// DELIBERATELY NOT BEHIND A BUILD TAG, unlike its neighbours in tests/. The
// tagged tiers are tagged because they are slow or platform-bound; this one
// parses a few dozen files in milliseconds and is a gate rather than a scenario.
// A boundary that is only checked when somebody remembers to pass -tags is a
// boundary that is not checked.
//
// Why it is worth a test at all, when review would catch it: the rule is what
// keeps a future wire v2 from rewriting the domain, and the failure mode is one
// convenient import in one file, added for a good local reason, months before
// anybody pays for it.
package architecture_test

import (
	"go/parser"
	"go/token"
	"io/fs"
	"path/filepath"
	"strings"
	"testing"
)

// The trees these rules walk, relative to this test file. domainRoot is what
// must stay pure; serverRoot is everything, for the rule about who may reach for
// a test double.
const (
	domainRoot = "../../domain"
	serverRoot = "../.."
)

// forbidden is what the domain may not reach for, with the reason attached to
// each so a failure explains itself rather than just pointing.
var forbidden = []struct {
	fragment string
	why      string
}{
	{
		fragment: "adapters/",
		why: "the domain speaks its own vocabulary; adapters map to and from it. " +
			"An import here would put the wire contract's shape into the domain, " +
			"and adding wire v2 would then rewrite the domain.",
	},
	{
		fragment: "modelcontextprotocol",
		why: "the MCP SDK is an adapter concern. The domain must not know it is " +
			"being driven over MCP at all.",
	},
	{
		fragment: "github.com/Microsoft/go-winio",
		why:      "named pipes are an operating-system detail that belongs in a leaf.",
	},
}

func TestDomainImportsNoAdaptersAndNoSDK(t *testing.T) {
	fileSet := token.NewFileSet()

	err := filepath.WalkDir(domainRoot, func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() || !strings.HasSuffix(path, ".go") {
			return nil
		}
		file, err := parser.ParseFile(fileSet, path, nil, parser.ImportsOnly)
		if err != nil {
			return err
		}
		for _, imported := range file.Imports {
			path := strings.Trim(imported.Path.Value, `"`)
			for _, rule := range forbidden {
				if strings.Contains(path, rule.fragment) {
					t.Errorf("%s imports %q\n%s", filepath.ToSlash(entry.Name()), path, rule.why)
				}
			}
		}
		return nil
	})
	if err != nil {
		t.Fatalf("walking %s: %v", domainRoot, err)
	}
}

// The test doubles are an importable package rather than _test.go files,
// because a fake is needed by the tests of SEVERAL packages -- FakeClock serves
// the bridge client, the handshake and the integration tier -- and a _test.go
// file cannot be imported from another package. The same is true of the
// builders in testsupport/.
//
// The price of that is two packages nothing structurally stops production code
// from importing. This is what stops it: a fake reaching the shipped binary
// would put scripted behaviour behind a port at runtime, which is the one
// failure a test double must never be able to cause.
//
// AMENDED IN 10b: testsupport/ is exempt as an IMPORTER of fakes -- its builders
// assemble port doubles into whole scenarios (a live session with these
// capabilities), which is exactly what it is for -- and is itself added to what
// production code may not import, so the exemption widens nothing.
func TestOnlyTestsImportTheTestPackages(t *testing.T) {
	fileSet := token.NewFileSet()
	testOnlyPackages := []string{
		"screen-readers-mcp/server/fakes",
		"screen-readers-mcp/server/testsupport",
	}

	err := filepath.WalkDir(serverRoot, func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() || !strings.HasSuffix(path, ".go") || strings.HasSuffix(path, "_test.go") {
			return nil
		}
		// testsupport/ and fakes/ are themselves test-only, so they may
		// reach for each other. Nothing else may reach for either.
		slashed := filepath.ToSlash(path)
		if strings.Contains(slashed, "/testsupport/") || strings.Contains(slashed, "/fakes/") {
			return nil
		}

		file, err := parser.ParseFile(fileSet, path, nil, parser.ImportsOnly)
		if err != nil {
			return err
		}
		for _, imported := range file.Imports {
			importPath := strings.Trim(imported.Path.Value, `"`)
			for _, testOnly := range testOnlyPackages {
				if strings.Contains(importPath, testOnly) {
					t.Errorf(
						"%s is not a test file and imports %q.\n"+
							"Test scaffolding must never be reachable from the shipped binary; "+
							"if production code needs this behaviour, it needs a real adapter.",
						slashed, importPath,
					)
				}
			}
		}
		return nil
	})
	if err != nil {
		t.Fatalf("walking %s: %v", serverRoot, err)
	}
}

// The walk above proves nothing if it walked nothing, which is exactly what
// would happen if the domain were ever moved and this path went stale.
func TestTheDomainTreeWasActuallyWalked(t *testing.T) {
	found := 0
	err := filepath.WalkDir(domainRoot, func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if !entry.IsDir() && strings.HasSuffix(path, ".go") {
			found++
		}
		return nil
	})
	if err != nil {
		t.Fatalf("walking %s: %v", domainRoot, err)
	}
	if found == 0 {
		t.Fatalf("no Go files found under %s; the boundary test is checking nothing", domainRoot)
	}
}
