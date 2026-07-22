// screenreader-mcp adapters -- tests for pipe_probe.go.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// Runs on every platform, because the OS is behind the PipeDirectory seam: what
// is tested here is the DECISION about a listing, which is the only thing in the
// discovery adapter worth testing.
package discovery_test

import (
	"testing"

	"github.com/google/go-cmp/cmp"
	"github.com/marlon-sousa/screen-readers-mcp/server/adapters/discovery"
	"github.com/marlon-sousa/screen-readers-mcp/server/domain/entities"
	"github.com/marlon-sousa/screen-readers-mcp/server/fakes"
	"github.com/marlon-sousa/screen-readers-mcp/server/testsupport"
)

func TestLiveReportsAConfiguredPipeThatIsListening(t *testing.T) {
	probe := discovery.NewPipeProbe(fakes.NewFakePipeDirectory("nvdaMcpBridge", "chrome.sync"))
	candidates := []entities.Endpoint{testsupport.Endpoint(t, "pipe:nvdaMcpBridge")}

	got := probe.Live(candidates)

	if diff := cmp.Diff(candidates, got); diff != "" {
		t.Errorf("live endpoints (-want +got):\n%s", diff)
	}
}

func TestLiveOmitsAConfiguredPipeThatIsAbsent(t *testing.T) {
	probe := discovery.NewPipeProbe(fakes.NewFakePipeDirectory("chrome.sync"))

	got := probe.Live([]entities.Endpoint{testsupport.Endpoint(t, "pipe:nvdaMcpBridge")})

	if len(got) != 0 {
		t.Errorf("live = %v, want nothing", got)
	}
}

// The rule the whole file exists for: the probe answers about CANDIDATES. A pipe
// in the namespace that nobody configured can never come back from it, so it can
// never become something an agent connects to -- which is what keeps the reader
// set from depending on whatever happens to be running, on a name any same-user
// process could have chosen.
func TestLiveNeverInventsAnEndpointFromTheNamespace(t *testing.T) {
	probe := discovery.NewPipeProbe(fakes.NewFakePipeDirectory("jawsMcpBridge", "nvdaMcpBridge"))

	got := probe.Live([]entities.Endpoint{testsupport.Endpoint(t, "pipe:nvdaMcpBridge")})

	if len(got) != 1 || got[0].Address != "nvdaMcpBridge" {
		t.Errorf("live = %v, want only the endpoint that was asked about", got)
	}
}

// Windows pipe names are case-insensitive. A user who wrote the name with a
// different capitalisation in a config file must not be told nothing is
// listening while their bridge is running.
func TestLiveMatchesPipeNamesCaseInsensitively(t *testing.T) {
	probe := discovery.NewPipeProbe(fakes.NewFakePipeDirectory("nvdaMcpBridge"))

	got := probe.Live([]entities.Endpoint{testsupport.Endpoint(t, "pipe:NVDAMcpBridge")})

	if len(got) != 1 {
		t.Errorf("live = %v, want the endpoint matched regardless of case", got)
	}
}

// TCP liveness cannot be known without connecting, and connecting would take the
// bridge's one session slot. The probe therefore says nothing about sockets, and
// the listing turns that silence into "unknown".
func TestLiveIgnoresTCPEndpoints(t *testing.T) {
	probe := discovery.NewPipeProbe(fakes.NewFakePipeDirectory("nvdaMcpBridge"))

	got := probe.Live([]entities.Endpoint{testsupport.Endpoint(t, "tcp:127.0.0.1:8765")})

	if len(got) != 0 {
		t.Errorf("live = %v, want nothing: a socket cannot be probed", got)
	}
}
