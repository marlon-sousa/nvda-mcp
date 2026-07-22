// screenreader-mcp tests -- the import boundaries.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: architecture test. Acceptance criterion 12: nothing under domain/
// imports adapters/wire or the MCP SDK.
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

// domainRoot is the tree that must stay pure, relative to this test file.
const domainRoot = "../../domain"

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
