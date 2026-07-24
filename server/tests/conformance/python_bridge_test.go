//go:build conformance

// screenreader-mcp tests -- starting the REAL Python bridge, and the real server.
// Copyright (C) 2026 Marlon Brandao de Sousa. GPL-2. See COPYING.txt.
//
// ROLE: scaffolding for the conformance tier. It launches the two processes the
// scenarios need -- the real NVDA bridge (Python) and the real MCP server (the
// built Go binary) -- and hands back the seam between them.
// USED BY: the scenarios beside it. It lives in a _test.go file rather than in
// testsupport/ because nothing outside this tier may have it: testsupport/ is
// where the FAKE bridge lives, and these two must never be alternatives to each
// other.
//
// WHY THIS TIER EXISTS, and the one rule that matters here. Every other test of
// this server drives a Go fake bridge that ENCODES with the same generated
// binding the server DECODES with, so a bug in the binding itself is invisible
// to them: both sides would be wrong together, in agreement. Only the real
// Python bridge can catch that, which makes this the successor to the same-bytes
// guarantee the two halves had while both were Python.
//
// Therefore: FAILING TO REACH THE REAL BRIDGE IS A HARD FAILURE, never a skip
// and never a fall-back. A conformance run that quietly used the Go fake would
// be worse than no conformance run at all -- it would assert the guarantee
// without providing it. Every path below that cannot reach Python calls
// t.Fatalf, and no code here can construct a fake.
package conformance_test

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"testing"
	"time"

	sdk "github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/marlon-sousa/screen-readers-mcp/server/testsupport"
)

// bridgeStartTimeout bounds how long the Python bridge may take to report the
// endpoint it is listening on. Generous, because a cold CI runner pays for
// interpreter startup on the first run; bounded, because a hang here would
// otherwise burn the whole job's time budget before saying anything useful.
const bridgeStartTimeout = 60 * time.Second

// pythonBridge is one running real bridge.
type pythonBridge struct {
	// Endpoint is what the bridge is listening on, spelled the way the
	// server's --reader flag wants it (`tcp:127.0.0.1:53422`, `pipe:name`).
	Endpoint string

	command *exec.Cmd
	stdin   io.WriteCloser
	stderr  *syncBuffer
}

// startPythonBridge launches bridges/nvda/tests/support/conformance_bridge.py on
// one transport and waits for it to report its endpoint.
//
// The protocol with the harness is deliberately one line of JSON on stdout, and
// stdin EOF to stop: the driver is in another language, so anything richer would
// be a second protocol to keep in sync with the one this tier exists to test.
func startPythonBridge(t *testing.T, transport string) *pythonBridge {
	t.Helper()

	script := repoPath(t, "bridges", "nvda", "tests", "support", "conformance_bridge.py")
	interpreter := pythonInterpreter(t)

	arguments := append(append([]string{}, interpreter[1:]...), script, "--transport", transport)
	command := exec.Command(interpreter[0], arguments...)
	// Run from the bridge directory so the harness's own relative paths (the
	// shared-module sync it performs) resolve the way they do under pytest.
	command.Dir = repoPath(t, "bridges", "nvda")

	stdout, err := command.StdoutPipe()
	if err != nil {
		t.Fatalf("the real bridge's stdout: %v", err)
	}
	stdin, err := command.StdinPipe()
	if err != nil {
		t.Fatalf("the real bridge's stdin: %v", err)
	}
	stderr := &syncBuffer{}
	command.Stderr = stderr

	if err := command.Start(); err != nil {
		t.Fatalf("starting the real bridge (%s): %v", strings.Join(command.Args, " "), err)
	}

	bridge := &pythonBridge{command: command, stdin: stdin, stderr: stderr}
	t.Cleanup(func() { bridge.stop(t) })

	bridge.Endpoint = awaitEndpoint(t, bridge, stdout)
	t.Logf("the real Python bridge is listening on %s", bridge.Endpoint)
	return bridge
}

// awaitEndpoint reads the harness's one announcement line.
func awaitEndpoint(t *testing.T, bridge *pythonBridge, stdout io.Reader) string {
	t.Helper()

	type announcement struct {
		Endpoint string `json:"endpoint"`
		line     string
		err      error
	}
	announced := make(chan announcement, 1)
	go func() {
		reader := bufio.NewReader(stdout)
		line, err := reader.ReadString('\n')
		result := announcement{line: line, err: err}
		if err == nil {
			err = json.Unmarshal([]byte(line), &result)
			result.err = err
		}
		announced <- result
	}()

	select {
	case result := <-announced:
		if result.err != nil {
			t.Fatalf("the real bridge never announced an endpoint (%v).\nIt said: %q\nstderr:\n%s",
				result.err, result.line, bridge.stderr.String())
		}
		if result.Endpoint == "" {
			t.Fatalf("the real bridge announced an empty endpoint: %q\nstderr:\n%s",
				result.line, bridge.stderr.String())
		}
		return result.Endpoint
	case <-time.After(bridgeStartTimeout):
		t.Fatalf("the real bridge did not report an endpoint within %s.\nstderr:\n%s",
			bridgeStartTimeout, bridge.stderr.String())
		return ""
	}
}

// stop closes the harness's stdin, which is its stop signal, and waits for it.
func (b *pythonBridge) stop(t *testing.T) {
	t.Helper()
	_ = b.stdin.Close()

	done := make(chan error, 1)
	go func() { done <- b.command.Wait() }()
	select {
	case <-done:
	case <-time.After(15 * time.Second):
		_ = b.command.Process.Kill()
		<-done
		t.Errorf("the real bridge did not exit when its stdin closed.\nstderr:\n%s", b.stderr.String())
	}
}

// Stderr is what the bridge has written to stderr so far, for a failing test to
// print. A conformance failure is usually about the far side, so the far side's
// own account of it is the first thing worth having.
func (b *pythonBridge) Stderr() string { return b.stderr.String() }

// pythonInterpreter finds a Python 3.13 to run the bridge with, and FAILS THE
// TEST if there is none.
//
// The candidates differ per machine -- CI puts `python` on PATH via
// setup-python; a Windows developer box may only have the `py` launcher, and
// this project's own AGENTS.md records a machine whose bare `python` is broken --
// so each candidate is PROBED by running it rather than assumed from its name.
// CONFORMANCE_PYTHON overrides the list entirely, as a space-separated command.
func pythonInterpreter(t *testing.T) []string {
	t.Helper()

	if override := os.Getenv("CONFORMANCE_PYTHON"); strings.TrimSpace(override) != "" {
		candidate := strings.Fields(override)
		if err := probePython(candidate); err != nil {
			t.Fatalf("CONFORMANCE_PYTHON=%q cannot run the bridge: %v", override, err)
		}
		return candidate
	}

	candidates := [][]string{{"python"}, {"python3.13"}, {"python3"}}
	if runtime.GOOS == "windows" {
		candidates = append(candidates, []string{"py", "-3.13"})
	}

	var refused []string
	for _, candidate := range candidates {
		if err := probePython(candidate); err != nil {
			refused = append(refused, fmt.Sprintf("  %s: %v", strings.Join(candidate, " "), err))
			continue
		}
		return candidate
	}
	t.Fatalf("no Python 3.13 interpreter could run the real bridge, so this run would "+
		"prove nothing about the wire contract. Tried:\n%s\n"+
		"Set CONFORMANCE_PYTHON to a working interpreter command.",
		strings.Join(refused, "\n"))
	return nil
}

// probePython checks one candidate by making it report its own version. The
// bridge is stdlib-only, so a bare interpreter of the right version is the whole
// requirement -- there is nothing to install.
func probePython(candidate []string) error {
	arguments := append(append([]string{}, candidate[1:]...),
		"-c", "import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)")
	command := exec.Command(candidate[0], arguments...)
	if output, err := command.CombinedOutput(); err != nil {
		return fmt.Errorf("%w (%s)", err, strings.TrimSpace(string(output)))
	}
	return nil
}

// startServer builds the server BINARY and drives it over stdio, exactly as an
// MCP host would.
//
// The binary rather than an in-process composition, because this tier is the one
// place where "does the thing we ship interoperate?" is the question: the stdio
// adapter, the flag parsing and the artifact itself are all part of the answer,
// and a stray write to stdout would corrupt the frames and fail here rather than
// in somebody's editor.
func startServer(t *testing.T, endpoint string) *testsupport.MCPHarness {
	t.Helper()

	binary := buildServer(t)
	command := exec.Command(binary, "--reader", "nvda="+endpoint, "--verbose")
	stderr := &syncBuffer{}
	command.Stderr = stderr
	t.Cleanup(func() {
		if t.Failed() {
			t.Logf("the server said, on stderr:\n%s", stderr.String())
		}
	})

	return testsupport.AttachMCP(t, &sdk.CommandTransport{Command: command})
}

// buildServer compiles the released binary into the test's own temporary
// directory.
//
// Built per test rather than once into a package-level variable: there is no
// package-level mutable state anywhere in server/ (spec 0013, acceptance
// criterion 11), and the build cache makes the repeat cost a link, not a
// compile.
func buildServer(t *testing.T) string {
	t.Helper()

	binary := filepath.Join(t.TempDir(), "screenreader-mcp")
	if runtime.GOOS == "windows" {
		binary += ".exe"
	}
	build := exec.Command("go", "build", "-o", binary, "./cmd/screenreader-mcp")
	build.Dir = repoPath(t, "server")
	build.Env = append(os.Environ(), "CGO_ENABLED=0")
	if output, err := build.CombinedOutput(); err != nil {
		t.Fatalf("building the server: %v\n%s", err, output)
	}
	return binary
}

// repoPath resolves a path from the repository root, which is three levels above
// this package.
func repoPath(t *testing.T, elements ...string) string {
	t.Helper()
	root, err := filepath.Abs(filepath.Join("..", "..", ".."))
	if err != nil {
		t.Fatalf("locating the repository root: %v", err)
	}
	path := filepath.Join(append([]string{root}, elements...)...)
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("%s is missing: %v", path, err)
	}
	return path
}

// syncBuffer collects a child process's stderr while the test reads it from
// another goroutine.
type syncBuffer struct {
	mutex  sync.Mutex
	buffer bytes.Buffer
}

func (b *syncBuffer) Write(p []byte) (int, error) {
	b.mutex.Lock()
	defer b.mutex.Unlock()
	return b.buffer.Write(p)
}

func (b *syncBuffer) String() string {
	b.mutex.Lock()
	defer b.mutex.Unlock()
	return b.buffer.String()
}
