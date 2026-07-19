# AGENTS.md — working in nvda-mcp

Operating manual for anyone (human or agent) developing this repo. For *what
we're building and why*, read the design specs in [`specs/`](specs/) — start
with [`0001-agent-driven-nvda-over-mcp.md`](specs/0001-agent-driven-nvda-over-mcp.md).
For *what to do now*, read [`ROADMAP.md`](ROADMAP.md) — the status board; its
first non-Done entry is the next step, and its Spec field says whether that
step is a spec conversation or implementation.

## What this is

An MCP server that lets an AI agent **drive NVDA** (the screen reader): send
keyboard gestures, read back what NVDA speaks/brailles, and introspect its
state. First use case: functional testing of NVDA add-ons; the primitives are
general.

Direction ([spec 0005](specs/0005-multi-reader-direction.md), **Decided**):
the server is a **reader-agnostic chassis** — NVDA is the first bridge, not
the identity. A "bridge" is whatever implements the wire contract for one
screen reader (JAWS and TalkBack sketches live in the spec). The server core
never special-cases a reader; reader identity is announced by `hello` and
surfaced, reader vocabulary rides through as opaque data, and the repo stays
a monorepo until a second bridge is real.

The chain, top to bottom — each item talks only to the next:

1. An MCP client (Claude Code, …) speaks MCP over stdio to the server.
2. `mcpServer/` — the `nvda-mcp` Python package — speaks JSON lines over TCP,
   127.0.0.1 only, to the bridge.
3. `bridgeAddon/` — the `nvdaMcpBridge` NVDA addon (global plugin + spy synth
   driver) — drives NVDA itself.

The two halves are separate processes and meet **only at the loopback socket**,
so the server survives NVDA restarts and NVDA's embedded Python never hosts the
asyncio MCP server.

## Layout

| Dir | What | Host / Python |
|---|---|---|
| `shared/` | Canonical **stdlib-only** wire protocol (`nvda-mcp-wire`). Envelope + per-command dataclasses + `from_dict` validator + JSON-lines helpers, plus `schema.py` (generates the published `specs/wire/v1/schema.json` from the dataclasses; **not** synced into the addon). Unit-tested once. | desktop CPython |
| `mcpServer/` | The MCP server (`nvda-mcp`): MCP tool → bridge command → result. FastMCP/stdio. | desktop CPython ≥3.11 |
| `bridgeAddon/` | The NVDA addon, built with scons. Inert until a session connects. | NVDA's embedded CPython 3.13 |
| `specs/` | Numbered design specs (RFC-style `NNNN-title.md`). | — |

## Internal architecture — ports & adapters (bridge AND server)

**Both** the bridge addon and the MCP server use the same **hexagonal**
(ports-and-adapters) design. The bridge's side-effecting edge is NVDA; the
server's is the MCP/stdio SDK and the TCP socket to the bridge — same shape,
learn it once.

**Every class has exactly one of four roles.** This is the vocabulary — if you
cannot name a new class's role, it is in the wrong place:

| Role | Lives in | What it is |
|---|---|---|
| **port** | `domain/ports/` | An `abc.ABC` the domain needs from the outside world. |
| **controller** | `domain/controllers/` | An orchestrator. Handed the ports it needs by `wiring.py`; runs a whole use case, driving entities and calling out through ports. **The answer to "who connects what".** |
| **entity** | `domain/entities/` | A stateful thing the app reasons about. Pure — never does IO. |
| **adapter** | `adapters/` | A concrete implementation of a port. The only place NVDA / the MCP SDK / the OS / real IO lives. |

"Pure Python" does **not** mean "domain". JSON-lines framing is pure and still
belongs in an adapter, because it is none of the three domain roles — it lives
behind the `MessageChannel` port, so the Session's collaborators are *only*
ports.

```
<package>/
  __init__.py     # entry point ONLY. The bridge's exposes GlobalPlugin lazily
                  # via a module-level __getattr__, so importing the package
                  # does NOT import NVDA (tests import the domain directly).
  domain/         # PURE core: no NVDA / no MCP SDK / no sockets / no JSON.
    ports/        #   ONE PORT PER FILE (abc.ABC + @abstractmethod); a port's own
                  #   DTO / signalling types live in its file. No re-exports.
    controllers/  #   the orchestrators, one per file
    entities/     #   the pure stateful model, one class per file
  adapters/       # the ONLY place NVDA / the MCP SDK / the OS / real IO lives
    ports/        #   seams BETWEEN adapters (the domain never sees these)
    ...           #   one class per file (private helpers may share the file)
  wiring.py       # composition root: picks adapters, stacks them, hands the
                  # controller its ports. Stays PURE so it is type-checked.
```

Bridge (`bridgeAddon/addon/globalPlugins/nvdaMcpBridge/`): the Session
lifecycle in `domain/controllers/session.py` (+ `teardown_reason.py`), the
per-command handlers under `domain/controllers/commands/` (see "Command
handlers" below); entities `speech_buffer.py` / `braille_buffer.py`; ports
`adapter_factory.py` (+ `AdapterSet`), `speech_source.py`, `braille_source.py`,
`synth_swapper.py`, `gesture_sender.py`, plus `clock.py`, `message_channel.py`,
`transcript.py`; adapters `json_lines_channel.py`, `file_transcript.py`,
`text_file_writer.py`, `real_clock.py`, with `nvda_*.py` + `socket_transport.py`
in session C. `protocol.py` (the synced shared wire module) sits at the package
root, and `plugin.py` is the NVDA edge. Server (session D): `domain/` holds the
tool translator + a `BridgeClient` port; adapters hold the FastMCP/stdio server
and the real TCP bridge client.

Rules that keep this honest:

- **Every module header states its ROLE and its relationships**, not just what
  the code does: which port it implements, what it depends on, who builds it,
  who uses it. If a reader has to ask "what is this class for and who connects
  it?", the header has failed — that question is the review test.
- **Adapters are LAYERED so the untestable part shrinks to a leaf.** An adapter
  may depend on another adapter, but only through a seam in `adapters/ports/` —
  never on a concrete adapter. The upper adapter holds every decision and is
  unit-tested against a fake seam; the **leaf** makes no decisions and does
  nothing but call the OS, so there is nothing to unit-test in it:

  | Decisions (tested vs a fake) | Seam | Leaf (untestable, ~15 lines) |
  |---|---|---|
  | `FileTranscript` — transcript vocabulary | `FileWriter` | `TextFileWriter` — real `open`/`write` |
  | `JsonLinesChannel` — framing + encode | `Transport` | `SocketTransport` — real socket |

  If you are tempted to put a decision in a leaf, it belongs one layer up.

- **Ports are `abc.ABC`s with `@abstractmethod`** (not `Protocol`): an
  incomplete adapter fails at construction, and the interface itself can't be
  instantiated. The domain depends only on ports; adapters subclass and
  implement them; **`wiring.py` is the only place that knows both.**
- **One interface/class per file, and NO re-export facades.** Each port,
  controller, entity and adapter is its own file; a small private helper may
  share its owner's file (e.g. `_LineReader` inside `json_lines_channel.py`). A
  **DTO or signalling type lives in the same file as the port/adapter that owns
  it** (`AdapterSet` with `AdapterFactory`; `Timeout`/`ChannelClosed` with
  `MessageChannel`). Import each from its own file
  (`from ..ports.clock import Clock`) — the `__init__.py` files carry
  documentation, never re-exports, so every import names its file and a module's
  dependencies are exactly the ports it lists. This applies to
  `shared/nvda_mcp_wire` too: import from `nvda_mcp_wire.protocol`, so both
  halves address the wire contract through a module named `protocol`.
- **No DI container library.** `wiring.py` read top-to-bottom *is* the answer to
  "who connects what"; annotation-driven auto-wiring hides that graph and turns
  compile-time wiring errors into runtime ones inside NVDA. `dependency-injector`
  is additionally disqualified: it is Cython-compiled and ships platform wheels
  (the `pydantic-core` objection), and any third-party lib risks a collision in
  NVDA's shared `sys.modules`. If wiring ever gets genuinely hard to follow,
  promote it to an explicit hand-written `container.py` of factory functions —
  same central place, zero dependencies, still checked by pyright.
- **Mode (silent/live) is only known after `hello`.** Do not build
  mode-specific adapters up front. `wiring.py` injects an **`AdapterFactory`
  port**; `Session` reads `hello`, then calls `factory.build(mode)` for the
  adapter set. No "configure the adapter after constructing it".
- **Enumerations are `enum`, never class-of-`Final`-constants.** Wire enums
  (`CaptureMode`, `Command`) are `enum.StrEnum` in `protocol.py` (members are
  `str`, so JSON stays plain); domain-only enums (`TeardownReason`) are plain
  `enum.Enum`. `Request.cmd` stays a raw `str` so an unknown command yields a
  clean error instead of a validation crash.
- **The NVDA/SDK edge is exempt from the type checker; the domain is not.** We
  do **not** vendor stubs and do **not** depend on the NVDA source. Instead the
  side-effecting adapter files (those importing NVDA, plus the bridge's
  `plugin.py`) are listed in pyright's `ignore`, so their unresolved imports
  raise nothing. This is safe precisely *because* the domain is pure and fully
  strict-checked and those thin edge files are validated by the milestone-6
  live-NVDA integration tests. Keep edge files thin — real logic belongs in the
  checked domain.

## Command handlers — the dispatch layer — **Decided**

The `Session` is a controller, but it does two jobs and delegates one. Session
**lifecycle** — the handshake, the heartbeat/inactivity watchdogs, and the
teardown that restores the synth on every path — stays in
`domain/controllers/session.py`. Per-command work lives in
`domain/controllers/commands/`, one **`CommandHandler`** (an `abc.ABC`) per wire
command, one file each, mirrored one-for-one by a test. This keeps the Session
small and lets a command be added or tested in isolation.

- **A handler is a controller.** It orchestrates one use case over
  ports/entities and returns a wire result, or **raises** to fail it — a
  `CommandError` for its own errors, a `protocol.ValidationError` for bad
  params, `GestureError` from the port. The Session centralises everything
  else: it wraps the result in a `Response` with the request id, turns any
  raise into an error reply, and owns the watchdog bookkeeping. Handlers never
  touch the channel, the loop, or teardown.
- **Handlers see only a `SessionContext`, never the Session.** The context
  (`commands/session_context.py`) is the per-session bundle — clock,
  transcript, the speech/braille buffers, the `AdapterSet` — plus exactly one
  lifecycle capability, `close(reason)`. A command that must end the session
  (`bye`, and session C's panic path) calls `close`; it cannot reach lifecycle
  internals. Because a handler needs only a hand-built context, it is
  unit-tested with **no Session and no run loop** (`tests/support/context.py`
  builds one from fakes).
- **The registry is an explicit map, not a container.**
  `commands/registry.py`'s `build_command_registry(...)` is a hand-written
  `command → handler` dict, read top to bottom — the same reason `wiring.py` is
  explicit (no DI container, no decorator auto-registration). Handlers are
  stateless singletons; the per-session state is the context passed to
  `execute`. **`hello` is the exception:** it is the bootstrap command that
  *builds* the session, so it is wired with the `AdapterFactory` and the NVDA
  version and populates the context — the Session no longer knows the factory
  at all.
- **Dispatch policy is declared on the handler, not special-cased in the
  loop.** `resets_inactivity` (false only for `ping`) and
  `available_before_hello` (true only for `hello`) are class attributes the
  dispatcher reads, so the one loop needs no `if cmd == ...`.
- **One dispatch loop.** The Session runs a single `while self._reason is None:`
  loop over a pre-hello/established state: pre-hello only `hello` is accepted
  and any failure ends the handshake; established, the session is tolerant (an
  error reply, keep going). A `TIMEOUT` sets no reason and polls again; every
  real exit sets the reason. (This replaced the two poll loops the first cut
  had.)

## Testing

The domain is pure, so it is unit-tested headlessly under desktop Python with
its ports faked. The rules below come with their reasoning, because each looks
like a style preference and is actually a correctness argument.

### Where a test lives — `tests/unit/` mirrors the source tree

**`tests/unit/` is a mirror of the package, file for file**, so the path alone
answers "which test covers this file?" and "where do I add a test for this?":

```
addon/globalPlugins/nvdaMcpBridge/domain/entities/speech_buffer.py
tests/unit/domain/entities/test_speech_buffer.py
```

The mirror applies per package, not just to the bridge:
`shared/tests/unit/test_protocol.py` ↔ `nvda_mcp_wire/protocol.py`; the
server adopts the same layout with its hexagonal restructure (session D).

One test module per source module — **do not** let a test module cover its
neighbours. (The rule earns its keep immediately: one `test_speech_buffer.py`
was quietly testing three units — the base, speech and braille — so the base's
index bookkeeping got tested through whichever subclass was handy. Mirroring
forced it into `test_indexed_buffer.py`, which now tests the base's contract
through a minimal stub subclass, while each buffer tests only what it adds.)

**A source file with no test file is a deliberate statement, not an omission:**

| No test file | Why |
|---|---|
| `domain/ports/*.py` | ABCs — no behaviour to test. |
| `domain/controllers/commands/command_handler.py` | The handler ABC + `CommandError` — an interface, like a port. (`session_context.py` and `registry.py` DO carry behaviour and are tested.) |
| leaf adapters (`real_clock.py`, `text_file_writer.py`, `socket_transport.py`) | They make no decisions; there is nothing `open()` doesn't already guarantee. If you are adding a test here, you have put a decision in a leaf — move it up. |
| `plugin.py` | The NVDA edge. Covered by the integration tests, not units. |

**Fakes mirror the ports they stand in for**, same one-class-per-file rule and
no re-export facade: `tests/fakes/clock.py` ↔ `domain/ports/clock.py`, imported
as `from fakes.clock import FakeClock`. Test scaffolding that is **not** a port
double — builders, helpers — lives in a sibling `tests/support/` package
(`from support.context import make_context`), so `fakes/` stays exactly the port
doubles and nothing else.

**`tests/integration/` is named after the USE CASE, not the file** — these prove
a whole scenario end to end. Two kinds live here. **Headless** scenarios drive
the real session stack (real dispatch, real JSON-lines framing) over a
`LoopbackTransport` with a fake NVDA, no socket and no NVDA — so they **run in
CI** like any unit test (e.g. `test_wire_session_roundtrip.py`, the recipe lane
2 builds on). **Live-NVDA** scenarios (e.g. `test_silent_session_restores_synth.py`)
need a real NVDA and are the only place that proves a *real* adapter behaves
like its fake; those are milestone 6 and do not run in CI.

Keep test module basenames unique across the tree (pytest's prepend import mode
requires it). Mirroring gives that for free, since source basenames are unique.

### Doubles are hand-written stateful fakes, not mocks

One per port, in `tests/fakes/` (one file per fake, mirroring the port's
file), each **subclassing its ABC** — so a fake that
forgets a method fails at construction exactly as the real NVDA adapter would.

The domain drives its collaborators through *real protocols* (wait loops, index
reads, state transitions) and asserts on resulting behaviour, so the doubles
need **behaviour**, not call-recording. A `Mock` returns a `Mock` for every
call, so you would hand-script return values per test — re-implementing the
collaborator, badly, and exercising less. `create_autospec`'s selling point
(catching contract drift) is already covered here by the **ABCs at runtime** plus
**pyright strict in CI**.

The cost is real and accepted: fakes are code we maintain. What they cannot
prove is that the *real* adapter behaves like the fake — only that signatures
match. That guarantee comes from the milestone-6 live-NVDA integration tests,
not from the unit doubles.

### Fixtures for uniform collaborators; builder helpers for scenarios

**Use a fixture when every test wants the same thing** ("a buffer on the fake
clock"). The point is not DRY — it is that a fixture makes a *relationship*
structural. `clock` (conftest) plus `speech(clock)` guarantees the buffer's
clock **is** the one the test advances. Hand-wiring that per test permits:

```python
clock = FakeClock()
buf = SpeechBuffer(FakeClock())   # a DIFFERENT clock
clock.advance(2.0)                # advances nothing the buffer can see
```

which passes silently and asserts nothing. The fixture makes that unwritable.

Prefer a **named variant fixture** (`silent_speech`) over a factory fixture
(`make_speech(exact=True)`) when there are only a couple of variants — a name
reads better than an argument.

**Do NOT reach for a fixture when each test customises construction.** The
session tests vary the swapper (one that raises on restore), the gesture sender
(one that rejects an id), the `SessionConfig`, the transport script — that is a
**builder helper** (`run_session(...)` with optional overrides), not a fixture.
Fixtures suit uniform collaborators; builders suit per-test scenarios. Forcing
fixtures there means one fixture per permutation.

**A fixture lives at the narrowest scope that serves it** — that is what the
mirrored tree buys us:

| Used by | Lives in |
|---|---|
| one test module | that module (`speech`, `silent_speech`, `braille`) |
| sibling modules in one directory | a `conftest.py` beside them |
| everything | `tests/conftest.py` (`clock`) — also the harness bootstrap |

Promote a fixture only when a second module actually needs it; do not start at
the root. Function scope (the default) is what we want: a fresh instance per
test, no state leaking between them.

**Why fixtures are fine when we rejected a DI container** (they are both
injection with the same "where does this come from?" indirection): pytest never
ships in the addon, the dependency is *visible in the test signature*, and a
missing fixture fails at collection with a clear message. None of the container
objections — a compiled binary inside NVDA, a `sys.modules` collision, hiding
the *production* graph, runtime failures inside NVDA — apply. Explicit wiring in
production; fixtures in tests.

### Time is injected, never patched

`FakeClock.sleep` is an **instant advance**, so a 5-second timeout test runs in
microseconds. This is also why `freezegun` / `time-machine` are the wrong tool
here: they patch the global clock but leave `time.sleep` real, so the wait loops
would still sleep for real — and patching globals under a `Clock` port would
make the port pointless for testing.

## Hard invariants — do not break

1. **`shared/nvda_mcp_wire/protocol.py` stays stdlib-only.** It is copied
   *verbatim* into the addon (`bridgeAddon/sync_shared.py`) and runs inside
   NVDA's interpreter, sharing `sys.modules` with every other addon. No
   third-party imports, ever. (pydantic etc. were considered and rejected —
   see the spec.) The server may use third-party libs; the shared module may
   not.
2. **The addon never edits its copied `protocol.py`.** Edit the canonical file
   in `shared/`; the copy under `bridgeAddon/addon/globalPlugins/nvdaMcpBridge/`
   is a gitignored build artifact regenerated by `sync_shared.py`.
3. **The addon must be safe to leave installed.** Inert while no session is
   active: no synth swap, no side-effecting hooks. Every silent-mode teardown
   path restores the user's real synth in a `finally` (a crashed harness must
   never leave a blind user with a mute screen reader).
4. **Type hints everywhere, enforced by pyright (strict).** CI fails on type
   errors. The pure **domain is fully strict-checked; the NVDA/SDK edge is
   not** — the side-effecting adapter files (and the bridge's `plugin.py`) are
   in pyright's `ignore` list, so their unresolved NVDA imports raise nothing.
   There is **no NVDA source dependency and no vendored stubs**; the `../nvda`
   checkout is a reference for reading real code, nothing more. (The edge is
   validated by the milestone-6 live-NVDA integration tests.)
5. **The domain never imports NVDA.** Everything under
   `nvdaMcpBridge/domain/` (and `protocol.py`) is pure Python, unit-tested
   headlessly. Only `nvdaMcpBridge/adapters/` may import `speech`,
   `synthDriverHandler`, `inputCore`, `config`, `api`, `braille`, … If you
   reach for an NVDA import in the domain, you're on the wrong side of a port.
6. **Decided means decided.** Items marked **Decided** — in this file,
   ROADMAP.md, or a spec's agreed sections — are settled. Do not relitigate
   them silently; to change one, propose it explicitly and update the doc in
   the same PR that implements the change.
7. **All documentation and communication must be screen-reader friendly:** no
   ASCII-art diagrams, no box-drawing flowcharts. Prose, numbered lists,
   headings, and tables only. (Indented path listings in code blocks are fine;
   arrows-and-pipes drawings are not.)

## Dev commands

Requires [uv](https://docs.astral.sh/uv/). **The bare `python` launcher on this
machine is broken** (it points at a non-existent Python310) — always use `uv
run` or `py -3.13`, never `python`.

```sh
# shared wire contract (no NVDA needed)
uv run --directory shared pytest
uv run --directory shared pyright

# MCP server (no NVDA needed; tests use a fake bridge)
uv run --directory mcpServer pytest
uv run --directory mcpServer pyright

# NVDA addon: copy the shared module in, then run headless tests + pyright.
# No NVDA checkout needed — the domain is pure; the NVDA edge is in pyright's
# ignore list (no stubs, no source dependency).
py -3.13 bridgeAddon/sync_shared.py
uv run --directory bridgeAddon pytest       # headless domain tests
uv run --directory bridgeAddon pyright
cd bridgeAddon && scons        # build the .nvda-addon (needs the NVDA build deps)
```

House style follows the NVDA addon convention: **tab indentation**, ruff line
length 110 (`W191`/tab warnings from a default editor ruff are expected and
ignored via per-package config).

## Workflow — **Decided**

Built in **modular sessions** of one or more short PRs, so context stays small
and fresh sessions cold-start cheaply. Merge order follows dependencies: **A
(foundation) → then B (bridge core) and D (server) in parallel → C
(bridge↔NVDA) → E (introspection + real-world) → F (packaging)**. Each session
only needs the merged code + its spec + this file.

[`ROADMAP.md`](ROADMAP.md) is the status board and owns execution state:

- **Spec before code.** Every board entry is implemented against a spec agreed
  in conversation first. The spec is written on the implementing PR's branch
  and merges with the PR — it does not land on main separately. Code on that
  branch starts only after the spec is approved in conversation; the PR is
  judged against its spec. If implementation forces a spec amendment, the
  amendment rides in the same PR. (Process-level doc changes — this file,
  ROADMAP.md's rules — are still approved in conversation and may land
  directly on main.)
- **A spec MUST include the class/file layout — Decided.** Before any code, the
  spec enumerates every file/class the PR will add, each with its one-line
  **role** (port / controller / entity / adapter, or a named supporting
  construct — e.g. a *parameter object* like `SessionContext`) and its
  collaborators (which ports/entities it holds, who builds it, who calls it).
  This layout is the review gate for the **decomposition itself** — it is where
  "if you cannot name a class's role, it is in the wrong place" gets applied in
  the spec conversation, so structural mistakes are caught *before* code, not
  after the first implementation. The kinds of mistakes this exists to catch,
  learned the hard way: a single class doing two roles (the `Session` was both
  lifecycle *and* a flat command dispatcher — each command is really its own
  controller); a holder mislabelled (`SessionContext` is a parameter object,
  not an adapter — it does no IO). If the layout changes while coding, the
  amendment rides in the PR with a one-line why.
- **The implementing PR flips its own ROADMAP.md entry to Done**, so the board
  is correct on main the moment the PR merges — no separate bookkeeping
  commit.
- **Lanes:** bridge (lane 1) and server (lane 2) may run in parallel — at most
  one open PR per lane.
- **Manual live-NVDA checklists live in the implementing PR's body as
  checkboxes** — one item per check; findings written inline on the unchecked
  item (NVDA version, expected vs observed). There is no separate findings
  document; findings that require changes become iteration entries in
  ROADMAP.md. The `no unchecked checkboxes` CI job
  (`.github/workflows/checklist.yml`) fails while the PR body has an unchecked
  box, so an unfinished checklist cannot merge once that job is in the
  required status checks.

## Gotchas learned the hard way

- **Silent-mode synth swap fights config profiles.** NVDA reloads the synth
  from `config["speech"]["synth"]` on *every* `config.post_configProfileSwitch`
  (`synthDriverHandler.py:420`, `566-584`). The naive
  `setSynth(spy, isFallback=True)` leaves config pointing at the real synth, so
  the first profile switch rips the spy out. Fix: set config's synth name to
  the spy, guard `config.pre_configSave`, and patch
  `synthDriverHandler.getSynthInstance`. See the spec's fail-safe section.
- **NVDA answers on non-speech channels.** Some actions (e.g. NVDA+space
  toggling browse/focus mode) signal via an earcon/beep, not words, so speech
  assertions have nothing to match. Use `getState` (browse/focus mode, speech
  mode, sleep, input help) to assert those.
- **CI job names are short and stable (`shared`, `server`, `bridge`) — don't
  "improve" them.** Branch protection matches required status checks by the
  literal job name, so a descriptive name couples the merge gate to the job's
  contents. Renaming `bridge (pyright against NVDA source)` once the NVDA
  checkout was gone parked every PR on *"Expected — waiting for status to be
  reported"* forever: the job passed, just under a new name, and only a repo
  settings edit could unblock it. Put the detail in **step** names, which are
  free to change. If a job name ever must change, update
  `repos/<owner>/<repo>/branches/main/protection/required_status_checks` in the
  same breath — push the workflow first, let it report, then flip the setting.
- **NVDA reference source is `../nvda/source`** (2026.1). Consult it for APIs
  rather than guessing; only `source/` is needed. It is a **reference only** —
  not a build/CI/type-check dependency. Adapter files that import NVDA go in
  pyright's `ignore` list (see the ports & adapters section); the domain they
  serve stays fully strict-checked.
