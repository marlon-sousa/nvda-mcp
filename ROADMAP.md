# nvda-mcp — Roadmap and Status Board

Companion to [`AGENTS.md`](AGENTS.md) (operating manual) and [`specs/`](specs/)
(design specs). This document owns build order **and execution status**. It is
the answer to "what should we do now?" — and it lives in the repo, so a fresh
session or a new contributor answers that question without anyone's private
notes.

## How to use this board — **Decided**

- **Finding the next step:** take the first entry in a lane below that is not
  marked Done, respecting the lane rules. Its "Spec" field tells you what kind
  of work comes next:
  - **Spec: none yet** → the next step is a spec conversation, not code. Branch
    off main for the entry, write the spec there (`specs/NNNN-title.md`) with
    Marlon, and get it agreed in conversation. The spec **must include the
    class/file layout** — every class to be added, its role, and its
    collaborators — so the decomposition is reviewed before code (see AGENTS.md,
    "Spec before code"). The spec rides in the implementing PR on that branch —
    it does not land on main separately — and the PR updates the entry's Spec
    field. Never code ahead of an agreed spec: implementation starts on the
    branch only after the spec is approved in conversation.
  - **Spec: exists** → implement it in a PR judged against the spec (branch off
    main; short PR: one component + its port(s) + tests, per AGENTS.md).
- **Marking done:** the implementing PR flips its own entry to
  "Done (PR #n, date)" as part of the PR. The mark becomes true on main exactly
  when the PR merges — no separate bookkeeping commit.
- **Lanes:** lane 1 (bridge) and lane 2 (server) may run in parallel — at most
  one open PR per lane, never two in the same lane. Order within a lane is
  strict. (Entries 5 and 6 predate this rule and are grandfathered; from here
  on it holds.)
- **Manual live-NVDA checklists** and their results live in the implementing
  PR's body as checkboxes; findings are written inline on the unchecked item
  (NVDA version, expected vs observed) and spawn new iteration entries here.
  The `no unchecked checkboxes` CI job keeps an unfinished checklist from
  merging.
- **Grandfathering:** entries merged before this board existed are backfilled
  as Done with their historical PR numbers, with RFC 0001 as their spec.
  In-flight PRs at the time the board landed also run under RFC 0001; every
  entry after them gets its own spec file.

## Session map

The sessions come from
[RFC 0001](specs/0001-agent-driven-nvda-over-mcp.md), Milestones: **A**
foundation → **B** bridge core (headless) → **C** bridge↔NVDA (needs live
NVDA) → **D** MCP server (headless; parallel to B/C) → **E** introspection +
real-world → **F** packaging. Each board entry belongs to one session.
[Spec 0005](specs/0005-multi-reader-direction.md) (the multi-reader direction
RFC, agreed 2026-07-18) added one cross-cutting wire entry to lane 1 (entry 8,
a headless B follow-up) and amended the scope of entries 9 and 12.

## Status board — lane 1: bridge

1. **Done** — A, foundation: shared wire protocol + tests, server and addon
   scaffolds, CI, GPL-2.0-or-later licensing. Spec: RFC 0001. Merged as PR #1
   (2026-07-13).
2. **Done** — B, wire enumerations as real enums (`StrEnum` in `protocol.py`).
   Spec: RFC 0001. Merged as PR #3 (2026-07-15).
3. **Done** — B, hexagonal architecture agreed for bridge AND server (docs
   only; the rules now in AGENTS.md). Spec: RFC 0001 + AGENTS.md. Merged as
   PR #4 (2026-07-15).
4. **Done** — B, headless foundation + buffer entities; drops the NVDA source
   dependency (pyright ignore list for the NVDA edge). Spec: RFC 0001. Merged
   as PR #5 (2026-07-15).
5. **Done** — B, MessageChannel port + JSON-lines adapter: the Session's
   whole-message I/O seam, framing behind the Transport adapter seam. Spec:
   [0002-bridge-message-channel.md](specs/0002-bridge-message-channel.md)
   (retroactive, rides in the PR). Merged as PR #6 (2026-07-17).
6. **Done** — B, Transcript port + file transcript stack: the session's
   human-readable record, vocabulary tested against a fake writer, real IO in
   a decision-free leaf. Spec:
   [0003-bridge-transcript.md](specs/0003-bridge-transcript.md) (retroactive,
   rides in the PR). Merged as PR #7 (2026-07-17).
7. B, session controller — split into two sequential PRs, one spec:
   [0004-bridge-session-controller.md](specs/0004-bridge-session-controller.md)
   (rides in PR 7a's branch).
   - **7a** — **Done (PR #9, 2026-07-17)**: five domain ports (`AdapterFactory`
     — mode known only after `hello` — speech/braille sources, synth swapper,
     gesture sender), `Session` (handshake, dispatch, heartbeat + inactivity
     watchdogs, teardown that always restores the synth), the scriptable
     fakes, session unit tests.
   - **7b** — **Done (PR #10, 2026-07-18)**, closes session B: `echo` wire
     command + `EchoHandler`, `wiring.py` (`build_session`), `LoopbackTransport`,
     and the headless wire-level scenario — the integration surface lane 2
     tests against.
8. **Done (PR #11, 2026-07-18)** — B follow-up (headless; added by
   [spec 0005](specs/0005-multi-reader-direction.md)), wire: the published
   contract — `hello` announces `reader` (name + version) and `capabilities`
   (replacing `nvdaVersion`), a `COMMAND_SHAPES` table in `protocol.py`, a JSON
   Schema generated from the dataclasses (`specs/wire/v1/schema.json`) with a CI
   drift gate, and the hand-written prose semantics doc
   (`specs/wire/v1/protocol.md`). Spec:
   [0006-wire-published-contract.md](specs/0006-wire-published-contract.md)
   (rides in the PR).
9. **Done** — C, bridge↔NVDA: real NVDA adapters (`adapters/nvda_*.py`),
   `synthDrivers/nvdaMcpSpy.py`, the `socket_transport.py`/`tcp_listener.py`
   accept stack, plugin wiring, panic gesture, scons build. Real adapters supply
   the live `reader`/`capabilities` values for the `hello` fields entry 8 adds.
   The listener is a **start/stop lifecycle controller** (`BridgeServer`) with
   observable status (stopped / listening on endpoint / session active) — the
   seam entry 9.1's control dialog drives — not a fire-and-forget loop
   (agreed 2026-07-18). Spec:
   [0007-bridge-nvda-edge.md](specs/0007-bridge-nvda-edge.md) (agreed
   2026-07-19; delivered as three sequential PRs, the split agreed 2026-07-19
   to keep checklist iteration on a small final PR). Scope: RFC 0001
   milestones 1–3; the fail-safe synth restoration design (config name swap,
   `pre_configSave` guard, `getSynthInstance` patch) is **Decided** in RFC 0001.
   - **9a** — **Done (PR #12, 2026-07-20)**: the headless connection stack —
     `Listener` seam + `TcpListener`, `SocketTransport`, and `BridgeServer`,
     proven by a real-socket integration scenario in CI.
   - **9b** — **Done (PR #13, 2026-07-20)**: the NVDA adapters (`nvda_*.py`) +
     `nvdaMcpSpy` spy synth (addon still inert), the pure `spy_sink` seam
     unit-tested, and the announced capabilities narrowed to
     speech/braille/gestures.
   - **9c** — **Done (PR #14, 2026-07-21)**: the switch-on — `plugin.py`
     wiring, the panic gesture (`kb:NVDA+control+shift+b`), packaging verified,
     and the live-NVDA checklist run with Marlon at the keyboard (results in
     the PR body). Live testing **pivoted the silent-mode mechanism**: the spy
     synth + `SynthSwapper` + RFC 0001 fail-safe (9b) were replaced by
     transparent capture at `filter_speechSequence` (the real synth stays
     loaded; it cannot strand the user mute), and the PR added session beeps,
     the `announce` hint command, crashed-client resilience, and a build
     dependency fix. See [spec 0008](specs/0008-transparent-silent-capture.md).
9.1. C follow-up, bridge control UI + connection config (agreed 2026-07-18):
   an NVDA menu → Tools entry opening a bridge dialog — connection-mode combo
   (Local: named pipe; Remote: TCP/IP, **greyed out** — see below), status
   indicator showing the accepting endpoint, Start/Stop buttons driving entry
   9's lifecycle controller, and an auto-start checkbox — all persisted to
   NVDA config. Adds the named-pipe transport leaf (ctypes, stdlib-only)
   behind the existing Transport seam; loopback TCP stays available as a
   config-only compat path (no UI) until the server dials pipes, then
   retires. The wire spec's transport section (`specs/wire/v1/protocol.md`
   §1) is amended in this PR. **Remote TCP is deferred — Decided**: it is
   remote keystroke injection (`pressGesture`) and config write (`setConfig`),
   so enabling it is a future entry with its own security spec (explicit
   warning + bridge-generated access token presented in `hello`); until then
   the combo shows it disabled. Needs live NVDA (GUI checklist). Spec: none
   yet → specify first, after entry 9's spec.
9.2. C follow-up, NVDA log capture per session (agreed 2026-07-21): every
   session tees NVDA's own log to a fresh, session-scoped file for `hello` to
   teardown, so debugging an add-on no longer needs manual before/after
   markers in `nvda.log`. `hello` gains an optional `logLevel` to temporarily
   raise NVDA's own logging verbosity for the session (restored at
   teardown), alongside the always-on capture. A second, parallel artifact
   to the existing transcript (spec 0003) — NVDA's real diagnostic log, not
   the bridge's domain vocabulary. Needs live NVDA (checklist: capture file
   distinct from `nvda.log`, `logLevel` surfaces DEBUG lines, level restored
   after teardown). Spec:
   [0009-nvda-log-capture.md](specs/0009-nvda-log-capture.md) (agreed
   2026-07-21).

## Status board — lane 2: server (headless; may run parallel to lane 1)

10. D, MCP server: FastMCP/stdio adapter, v1 MCP tools, `BridgeClient` port,
    unit tests against a fake bridge + in-memory MCP client tests. Spec: none
    yet → specify first. Scope sketch: RFC 0001 component 2 + milestone 4;
    same hexagonal organization as the bridge (AGENTS.md), and the restructure
    adopts the `tests/unit/` mirror layout. The spec must encode the
    reader-agnostic chassis principles of
    [spec 0005](specs/0005-multi-reader-direction.md) (no reader conditionals;
    reader identity surfaced; reader vocabulary as opaque data; bridge
    endpoint as composition-root config). Once entry 9.1 lands, a small
    lane-2 follow-up teaches the `BridgeClient` endpoint config to dial the
    named pipe as well as TCP.

## Convergence (requires C and D both Done)

11. E, introspection + real-world: focus/braille/config tools; end-to-end run
    against EnhancedFindDialog with Claude Code as the MCP client. Needs live
    NVDA. Spec: none yet → specify when unblocked. Scope sketch: RFC 0001
    milestones 5–6. The live-NVDA integration tests here are what prove each
    real adapter behaves like its fake — findings spawn iteration entries
    (E.1, E.2, …) in this board.
12. F, packaging/release: scons `.nvda-addon` artifact, server distribution,
    GitHub release workflow. Spec: none yet → specify when reached. Scope
    sketch: RFC 0001 milestone 7, plus the decision list from
    [spec 0005](specs/0005-multi-reader-direction.md): server implementation
    language (Python + PyInstaller vs a Go port judged against the published
    wire contract), umbrella Windows installer vs per-channel-only
    distribution (NVDA add-on store stays canonical for the add-on), and an
    `.mcpb` bundle for Claude Desktop users.

## Principles — **Decided**

- PRs are short: one component + its port(s) + unit tests; nothing lands
  untested. Session B's split into PRs #3–#7 is the template — a "session" is
  a context boundary, not a PR size.
- Spec before code: every entry not grandfathered above is implemented against
  a spec agreed in conversation before any implementation is written, and the
  spec includes the class/file layout (roles + collaborators) so the
  decomposition is caught in review, not after code. The spec file rides in the
  implementing PR's branch and merges with it. If implementation forces a spec
  amendment, the amendment rides in the same PR.
- Items marked **Decided** here, in AGENTS.md, or in a spec's agreed sections
  are settled. Do not relitigate them silently; to change one, propose it
  explicitly and update the doc in the same PR that implements the change.
