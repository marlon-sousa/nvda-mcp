// screenreader-mcp -- the entry point.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: entry point ONLY. Parse flags, hand them to wiring, run. No logic lives
// here -- anything that looks like a decision belongs in wiring or below it.
// BUILDS: wiring.Server.
//
// STDOUT DISCIPLINE: stdout carries MCP JSON-RPC frames and nothing else. The
// two flags that print (--version, --print-default-config) are the deliberate
// exceptions -- they print and EXIT, so no frame ever shares the stream with
// them. Every other word this process says goes to stderr through the Log port.
package main

import (
	"flag"
	"fmt"
	"os"

	"github.com/marlon-sousa/screen-readers-mcp/server/config"
	"github.com/marlon-sousa/screen-readers-mcp/server/version"
	"github.com/marlon-sousa/screen-readers-mcp/server/wiring"
)

// readerFlags collects a repeatable --reader, preserving the order given: within
// one reader, that order is the order its endpoints are tried in.
type readerFlags []string

func (f *readerFlags) String() string { return fmt.Sprint(*f) }

func (f *readerFlags) Set(value string) error {
	*f = append(*f, value)
	return nil
}

func main() {
	var readers readerFlags
	flag.Var(&readers, "reader",
		"name=spec endpoint override, repeatable and highest precedence "+
			"(e.g. nvda=pipe:nvdaMcpBridge or talkback=tcp:127.0.0.1:9010)")
	configPath := flag.String("config", "",
		"path to a JSON file replacing or extending the embedded reader defaults")
	printDefaults := flag.Bool("print-default-config", false,
		"print the embedded reader defaults and exit")
	showVersion := flag.Bool("version", false, "print the version and exit")
	verbose := flag.Bool("verbose", false, "log debug detail to stderr")
	flag.Parse()

	// Deliberately NO --capture-mode and no --reader-log-level: the wire
	// contract fixes both at `hello` for the session's lifetime, so they are
	// connect_reader parameters chosen by the agent that knows what the
	// session is for -- not flags chosen by whoever wrote the host config.

	if *showVersion {
		fmt.Println(version.Version)
		return
	}
	if *printDefaults {
		os.Stdout.Write(config.DefaultsJSON())
		return
	}

	server, err := wiring.Build(wiring.Options{
		ConfigPath:  *configPath,
		ReaderFlags: readers,
		Verbose:     *verbose,
	})
	if err != nil {
		fmt.Fprintf(os.Stderr, "screenreader-mcp: %v\n", err)
		os.Exit(1)
	}

	// 10a stops here: the module, the wire binding, the endpoint config and
	// the bridge client are in place and proven headlessly, but there is no
	// MCP surface yet -- that is 10b. Reported on stderr and exiting non-zero,
	// because an MCP host launching this today would otherwise sit waiting for
	// a server that is never going to speak.
	server.Log.Errorf(
		"no MCP surface yet: 10a delivers the bridge client only (spec 0013). "+
			"%d reader(s) configured.", len(server.Endpoints.Readers()))
	os.Exit(1)
}
