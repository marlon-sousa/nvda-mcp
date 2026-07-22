// screenreader-mcp config -- Loader: the layered endpoint set.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: adapter. IMPLEMENTS the domain's EndpointSource port by layering the
// embedded defaults, an optional --config file, and --reader flags.
// DEPENDS ON: a FileReader seam declared in this file, so every decision here is
// unit-tested without touching disk.
// BUILT BY: wiring/wiring.go, from the parsed flags.
// USED BY: 10b's connection controller (list_readers, connect_reader).
//
// The defaults are EMBEDDED rather than shipped as a sidecar file, and spec 0013
// gives three reasons: the point of a statically linked binary is one artifact,
// an MCP host launches the server with an unspecified working directory (so an
// on-disk default would have to be resolved against the executable path -- a
// classic works-in-my-shell failure), and .mcpb bundling stays trivial with a
// single file. Discoverability is preserved by --print-default-config, which
// emits these exact bytes for the user to redirect and edit.
//
// Everything this can ever return is therefore known before the process starts.
// Nothing is invented at runtime, and no endpoint enters the set by being found.
package config

import (
	_ "embed"
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/ports"
)

// defaultsJSON is the shipped endpoint set: every reader we ship a bridge for,
// each naming every place that bridge is known to listen, in order.
//
//go:embed defaults.json
var defaultsJSON []byte

// DefaultsJSON returns the embedded defaults verbatim, for
// --print-default-config. A copy, because handing out the embedded slice would
// let a caller scribble on package state.
func DefaultsJSON() []byte {
	out := make([]byte, len(defaultsJSON))
	copy(out, defaultsJSON)
	return out
}

// FileReader reads a config file.
//
// A seam, so the layering rules below are tested as pure decisions: os.ReadFile
// in production, a map in tests. It is a function type because it has one method
// and no state.
type FileReader func(path string) ([]byte, error)

// document is the on-disk shape of both the embedded defaults and a --config
// file, so a user can start from --print-default-config and edit it.
type document struct {
	Readers []documentReader `json:"readers"`
}

type documentReader struct {
	Name      string   `json:"name"`
	Endpoints []string `json:"endpoints"`
}

// Options are the layers above the embedded defaults, in increasing precedence.
type Options struct {
	// ConfigPath is --config: a JSON file replacing or extending the
	// defaults. Empty means none.
	ConfigPath string

	// ReaderFlags are the raw --reader values, `name=spec`, in the order
	// they were given.
	ReaderFlags []string

	// ReadFile reads the config file. Nil means os.ReadFile.
	ReadFile FileReader
}

// Loader is a resolved reader set.
//
// Resolved ONCE, at construction: the layering happens while the process is
// starting, so a bad config file fails before the server serves anything, and
// so `list_readers` cannot answer differently from one minute to the next.
type Loader struct {
	readers []entities.ConfiguredReader
}

var _ ports.EndpointSource = (*Loader)(nil)

// Load resolves the three layers, lowest precedence first.
//
// The rule at each layer is per-READER replacement rather than a merge of
// endpoint lists: a reader named by a higher layer takes that layer's endpoints
// entirely, and a reader nobody mentions keeps the layer below's. Merging would
// make it impossible to REMOVE a shipped default -- a user who moved their
// bridge to a different pipe would still have the old one tried first, and would
// have no way to say otherwise.
//
// Order is preserved throughout: within a reader, endpoints stay in the order
// they were declared, because that is the order connect_reader tries them in.
// New readers are appended in the order they first appear.
func Load(opts Options) (*Loader, error) {
	readFile := opts.ReadFile
	if readFile == nil {
		readFile = os.ReadFile
	}

	var defaults document
	if err := json.Unmarshal(defaultsJSON, &defaults); err != nil {
		return nil, fmt.Errorf("embedded defaults: %w", err)
	}
	readers, err := toReaders(defaults)
	if err != nil {
		return nil, fmt.Errorf("embedded defaults: %w", err)
	}

	if opts.ConfigPath != "" {
		raw, err := readFile(opts.ConfigPath)
		if err != nil {
			return nil, fmt.Errorf("reading %s: %w", opts.ConfigPath, err)
		}
		var fromFile document
		if err := json.Unmarshal(raw, &fromFile); err != nil {
			return nil, fmt.Errorf("%s: %w", opts.ConfigPath, err)
		}
		overrides, err := toReaders(fromFile)
		if err != nil {
			return nil, fmt.Errorf("%s: %w", opts.ConfigPath, err)
		}
		for _, reader := range overrides {
			readers = replaceReader(readers, reader)
		}
	}

	fromFlags, err := readersFromFlags(opts.ReaderFlags)
	if err != nil {
		return nil, err
	}
	for _, reader := range fromFlags {
		readers = replaceReader(readers, reader)
	}

	return &Loader{readers: readers}, nil
}

// Readers returns the resolved set. A copy of the slice, so a caller cannot
// reorder the one thing whose order is load-bearing.
func (l *Loader) Readers() []entities.ConfiguredReader {
	out := make([]entities.ConfiguredReader, len(l.readers))
	copy(out, l.readers)
	return out
}

// toReaders parses one document's endpoint specs.
func toReaders(doc document) ([]entities.ConfiguredReader, error) {
	readers := make([]entities.ConfiguredReader, 0, len(doc.Readers))
	for _, entry := range doc.Readers {
		if entry.Name == "" {
			return nil, fmt.Errorf("a reader has no name")
		}
		if len(entry.Endpoints) == 0 {
			return nil, fmt.Errorf("reader %q has no endpoints", entry.Name)
		}
		endpoints := make([]entities.Endpoint, 0, len(entry.Endpoints))
		for _, spec := range entry.Endpoints {
			endpoint, err := entities.ParseEndpoint(spec)
			if err != nil {
				return nil, fmt.Errorf("reader %q: %w", entry.Name, err)
			}
			endpoints = append(endpoints, endpoint)
		}
		readers = append(readers, entities.ConfiguredReader{Name: entry.Name, Endpoints: endpoints})
	}
	return readers, nil
}

// readersFromFlags turns repeated `--reader name=spec` values into readers.
//
// Repeating a name ADDS an endpoint to that reader, in flag order, so a
// one-off override can still name a pipe and a socket. The whole flag layer for
// a given name then replaces that reader, which is what makes `--reader
// nvda=tcp:127.0.0.1:9000` mean "only there" rather than "there as well as the
// two shipped defaults".
func readersFromFlags(flags []string) ([]entities.ConfiguredReader, error) {
	var order []string
	byName := map[string][]entities.Endpoint{}

	for _, flag := range flags {
		name, spec, found := strings.Cut(flag, "=")
		if !found || name == "" || spec == "" {
			return nil, fmt.Errorf("--reader %q: want name=spec, e.g. nvda=pipe:nvdaMcpBridge", flag)
		}
		endpoint, err := entities.ParseEndpoint(spec)
		if err != nil {
			return nil, fmt.Errorf("--reader %q: %w", flag, err)
		}
		if _, seen := byName[name]; !seen {
			order = append(order, name)
		}
		byName[name] = append(byName[name], endpoint)
	}

	readers := make([]entities.ConfiguredReader, 0, len(order))
	for _, name := range order {
		readers = append(readers, entities.ConfiguredReader{Name: name, Endpoints: byName[name]})
	}
	return readers, nil
}

// replaceReader overrides a reader of the same name in place, keeping its
// position, or appends it. Position is kept so that adding an override does not
// silently reorder what `list_readers` shows.
func replaceReader(readers []entities.ConfiguredReader, override entities.ConfiguredReader) []entities.ConfiguredReader {
	for i, existing := range readers {
		if existing.Name == override.Name {
			readers[i] = override
			return readers
		}
	}
	return append(readers, override)
}
