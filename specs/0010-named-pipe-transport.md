# Spec 0010 — bridge: named-pipe transport leaf

Implementation contract for ROADMAP lane 1, entry 9.1a (split off entry 9.1,
agreed 2026-07-21). Authored on the entry's branch per process; the spec rides
in the implementing PR.

> **Amended 2026-07-21, same PR.** Originally `plugin.py` was to stay
> untouched, with the default switch deferred to 9.1b (see the "Out of scope"
> bullet this strikes). Once the leaf was headlessly proven, it was also
> proven against a real, running NVDA (`tests/integration/test_live_nvda_pipe_e2e.py`
> — handshake, silent-mode capture, sequential sessions, all over the pipe),
> and `plugin.py` was flipped to the named pipe on the strength of that
> result rather than waiting for 9.1b. `TcpListener` stays in the tree,
> unwired, as the compat leaf 9.1b's config combo will offer alongside the
> pipe. This narrows 9.1b to the control dialog, the connection-mode combo,
> and config persistence — it no longer needs to *make* the default switch,
> only let a user override it.

## Goal

Entry 9.1 originally bundled three things behind one PR: the control-UI
dialog, config persistence, and a named-pipe `Listener`/`Transport` leaf. That
coupling is unnecessary — the transport leaf has no UI dependency, and
splitting it out gives the GUI PR a smaller, already-proven seam to wire a
combo box to. This entry delivers **only** the leaf: a `NamedPipeListener`
and `NamedPipeTransport` implementing the exact same `Listener`/`Transport`
seams `TcpListener`/`SocketTransport` already implement (spec 0007, 9a), so
either can be handed to `BridgeServer` interchangeably. `plugin.py` now
builds the named-pipe listener (see the amendment above); *persisting* a
user's choice between the two transports, and a UI to make it, stays entry
9.1b's job.

Why a leaf, not a "leaf with no unit tests" the way `tcp_listener.py` /
`socket_transport.py` are: those two are literally decision-free (settimeout
already gives the exact contract). Windows named pipes are not — connecting,
polling, and cancelling require overlapped I/O — so correctness here is
proven by real usage: a headless integration test that runs an actual
Windows named pipe end to end, the same tier of proof 9a's
`test_socket_session_roundtrip.py` gave the TCP leaf. No NVDA import; it runs
in CI (`bridge` job, `windows-latest`) exactly like the socket scenario.

## Design

### Wire-level: `DEFAULT_PIPE_NAME`

`shared/nvda_mcp_wire/protocol.py` gains one constant, next to
`DEFAULT_PORT`:

```python
DEFAULT_PIPE_NAME: Final = r"\\.\pipe\nvdaMcpBridge"
```

Added to `__all__`, unit-tested in `shared/tests/unit/test_protocol.py`
alongside the `DEFAULT_PORT` assertion. `specs/wire/v1/protocol.md` §1
("Transport and framing") is amended to describe the named pipe as a second
listening option a Windows bridge may offer, alongside loopback TCP — both
still local-machine-only, matching the existing "never a routable interface"
decision. No schema change: the transport a bridge listens on is not part of
the JSON-lines wire shapes.

### Security posture — **Decided**

A named pipe is reachable by any local process by name, and by remote
machines via `\\host\pipe\name` unless rejected — the pipe analogue of "never
bind a routable interface." `NamedPipeListener` closes both holes:

- `PIPE_REJECT_REMOTE_CLIENTS` on every pipe instance (the remote-access
  door, closed the same way loopback-only binding closes it for TCP).
- A security descriptor restricting the pipe's DACL to the owner (the SDDL
  string `"D:(A;;GA;;;OW)"` — Generic All to `OWNER RIGHTS` only, no other
  ACE, so every other local account is denied by omission), built once via
  `ConvertStringSecurityDescriptorToSecurityDescriptorW` (`advapi32`) and
  reused for every instance the listener creates. Same reasoning as the
  loopback bind: the bridge can inject keystrokes and read config, so a
  same-machine other-user process must not be able to dial in.

### New files and classes

All under `bridgeAddon/`, ctypes + stdlib only (hard invariant 1 does not
apply here — that invariant is about `protocol.py` specifically — but the
addon as a whole stays free of third-party dependencies by convention, and
ctypes calling `kernel32`/`advapi32` keeps that convention).

| File | Role | Collaborators |
|---|---|---|
| `adapters/named_pipe_listener.py` | leaf adapter (implements the `Listener` seam) | **NamedPipeListener**: `open()` builds the owner-only security descriptor once and arms the first pipe instance (`CreateNamedPipeW` + overlapped `ConnectNamedPipe`); `accept()` waits on the pending instance's event up to the poll window (`WaitForSingleObject`), raises `TimeoutError` on `WAIT_TIMEOUT`, confirms via `GetOverlappedResult`, wraps the connected handle in a `NamedPipeTransport`, and **eagerly arms the next instance** before returning — the pipe analogue of TCP's `listen(1)` backlog letting one client queue while a session runs. `close()` is idempotent: cancels the pending instance (`CancelIoEx`), closes its handle/event, frees the security descriptor. `endpoint` returns the pipe name. |
| `adapters/named_pipe_transport.py` | leaf adapter (implements the `Transport` seam) | **NamedPipeTransport**: wraps one connected pipe `HANDLE` (either side — a listener's accepted instance or a client's dialed handle). `recv()`: overlapped `ReadFile`, waits on its own event up to the poll window, `TimeoutError` on timeout (cancelling the read via `CancelIoEx` first so it does not complete later into a stale buffer), `b""` on `ERROR_BROKEN_PIPE`/`ERROR_PIPE_NOT_CONNECTED`/`ERROR_NO_DATA`/`ERROR_OPERATION_ABORTED` (the pipe analogue of `SocketTransport`'s "peer gone → EOF"). `sendall()`: overlapped `WriteFile`, waits indefinitely (`GetOverlappedResult(..., bWait=True)`) — same blocking-until-sent contract as a real socket's `sendall`. `close()` is idempotent: cancels any pending I/O, disconnects (server side only; a no-op failure on the client side, ignored), closes the handle and both events. Also exports **`dial(pipe_name, timeout) -> NamedPipeTransport`**, the client-side counterpart (`CreateFileW` with `FILE_FLAG_OVERLAPPED`, retrying on `ERROR_PIPE_BUSY` via `WaitNamedPipeW` until `timeout`) — used by the integration test's client end and by anything that later dials the bridge over a pipe, exactly as `socket.create_connection` plays that role for the TCP scenario today. |
| `tests/integration/test_named_pipe_session_roundtrip.py` | headless integration scenario | The real stack over a real named pipe, on a **unique per-test pipe name** (`\\.\pipe\nvdaMcpBridge-test-<uuid>`, the pipe analogue of TCP's ephemeral port 0) — otherwise a line-for-line mirror of `test_socket_session_roundtrip.py`: hello → echo → pressGesture/getSpeech → bye, sequential sessions on one server, an idle server stopping promptly, and an abruptly-closed client not taking the server down. `NamedPipeListener` + `NamedPipeTransport.dial` stand in for `TcpListener` + `socket.create_connection`; everything else (`BridgeServer`, `FakeAdapterFactory`, `JsonLinesChannel`) is identical, proving the seam is truly interchangeable. |
| `tests/integration/test_live_nvda_pipe_e2e.py` | live-NVDA integration scenario (per the amendment) | Mirrors `test_live_nvda_e2e.py`, dialling `DEFAULT_PIPE_NAME` with `named_pipe_transport.dial` instead of a TCP socket. Skips (not fails) when nothing is listening on the pipe, same as the TCP version does for its socket. Proved the handshake, silent-mode gesture capture, and sequential sessions against a real, running NVDA before `plugin.py`'s default was flipped. |

`wiring.py` and `bridge_server.py` are untouched (`Listener` is already their
seam, satisfied by either leaf); the GUI (none exists yet) is entry 9.1b's
job, now narrowed to letting a user *override* the pipe default, not choose
it from scratch.

## Out of scope

- The control dialog, the connection-mode combo, config persistence,
  auto-start — entry 9.1b, now that this entry has already built, proven, and
  wired in the pipe default it will let a user override.
- The MCP server dialling a pipe (`BridgeClient`, lane 2) — noted on the
  board as a small follow-up once a `BridgeClient` exists at all (entry 10,
  not yet started).
- Any wire schema change.

## Acceptance criteria

1. `DEFAULT_PIPE_NAME` added to `shared/nvda_mcp_wire/protocol.py` and
   asserted in `shared/tests/unit/test_protocol.py`; `specs/wire/v1/protocol.md`
   §1 amended; the schema drift gate stays green (no schema change).
2. `NamedPipeListener`/`NamedPipeTransport` implement the `Listener`/
   `Transport` seams exactly (`adapters/ports/listener.py`,
   `adapters/ports/transport.py`) — pyright strict clean, no new entries on
   the NVDA-edge ignore list (nothing here imports NVDA; ctypes is stdlib).
3. `test_named_pipe_session_roundtrip.py` green on CI (`windows-latest`,
   real named pipe, no NVDA): the same session lifecycle TCP's 9a scenario
   proves — sequential sessions on one server, idle-stop is prompt, an
   abruptly-closed client does not take the server down — plus a poll-timeout
   assertion (`accept()`/`recv()` raise `TimeoutError` when idle, matching
   the TCP leaf's documented contract) that the TCP scenario does not need
   because sockets already guarantee it.
4. Per the amendment: `plugin.py` now builds `NamedPipeListener(protocol.DEFAULT_PIPE_NAME)`
   instead of `TcpListener`. An installed addon now listens on the pipe, not
   loopback TCP — a real behavior change, deliberately made in this PR on the
   strength of criterion 5.
5. `test_live_nvda_pipe_e2e.py` — a live-NVDA scenario, run ad hoc against a
   real, running NVDA (not a CI job; it skips without a bridge listening,
   same as `test_live_nvda_e2e.py`) — passed: `hello` reports the real
   `reader`/`capabilities`/`synth`, a silent-mode gesture is captured, and two
   sequential sessions succeed on one server, all over the pipe. This is the
   evidence the amendment above is made on; it is exploratory verification
   run once during review, not a repeatable merge gate the way the headless
   suite is.

## Definition of done

Merged with green CI (`shared`, `bridge` — `server` untouched); ROADMAP entry
9.1 split into **9.1a** (this entry, including the live-proven default
switch, flipped to Done by this PR) and **9.1b** (the control dialog +
config + override UI, unblocked by this PR, Spec: none yet).
