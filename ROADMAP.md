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
  - **Spec: none yet** → the next step is a spec conversation, not code. Write
    the spec with Marlon, get it agreed in conversation, land it on main
    (`specs/NNNN-title.md`), and update the entry's Spec field in the same
    commit. Never code ahead of an agreed spec.
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
7. B, session controller: `Session` (handshake, dispatch, heartbeat +
   inactivity watchdogs, teardown that always restores the synth),
   `AdapterFactory` port (mode known only after `hello`), `wiring.py`. Spec:
   none yet → specify first. Scope sketch: RFC 0001 session + fail-safe
   sections; AGENTS.md architecture rules.
8. C, bridge↔NVDA: real NVDA adapters (`adapters/nvda_*.py`),
   `synthDrivers/nvdaMcpSpy.py`, `socket_transport.py` + accept loop, plugin
   wiring, panic gesture, scons build. Needs live NVDA with Marlon at the
   keyboard; results recorded as a checklist in the PR body. Spec: none yet →
   specify first. Scope sketch: RFC 0001 milestones 1–3; the fail-safe synth
   restoration design (config name swap, `pre_configSave` guard,
   `getSynthInstance` patch) is already **Decided** in RFC 0001.

## Status board — lane 2: server (headless; may run parallel to lane 1)

9. D, MCP server: FastMCP/stdio adapter, v1 MCP tools, `BridgeClient` port,
   unit tests against a fake bridge + in-memory MCP client tests. Spec: none
   yet → specify first. Scope sketch: RFC 0001 component 2 + milestone 4; same
   hexagonal organization as the bridge (AGENTS.md), and the restructure
   adopts the `tests/unit/` mirror layout.

## Convergence (requires C and D both Done)

10. E, introspection + real-world: focus/braille/config tools; end-to-end run
    against EnhancedFindDialog with Claude Code as the MCP client. Needs live
    NVDA. Spec: none yet → specify when unblocked. Scope sketch: RFC 0001
    milestones 5–6. The live-NVDA integration tests here are what prove each
    real adapter behaves like its fake — findings spawn iteration entries
    (E.1, E.2, …) in this board.
11. F, packaging/release: scons `.nvda-addon` artifact, PyInstaller zip for
    the server, GitHub release workflow. Spec: none yet → specify when
    reached. Scope sketch: RFC 0001 milestone 7.

## Principles — **Decided**

- PRs are short: one component + its port(s) + unit tests; nothing lands
  untested. Session B's split into PRs #3–#7 is the template — a "session" is
  a context boundary, not a PR size.
- Spec before code: every entry not grandfathered above is implemented against
  a spec agreed in conversation and landed on main first. If implementation
  forces a spec amendment, the amendment rides in the implementing PR.
- Items marked **Decided** here, in AGENTS.md, or in a spec's agreed sections
  are settled. Do not relitigate them silently; to change one, propose it
  explicitly and update the doc in the same PR that implements the change.
