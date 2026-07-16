# AGENTS.md — working in nvda-mcp

Operating manual for anyone (human or agent) developing this repo. For *what
we're building and why*, read the design specs in [`specs/`](specs/) — start
with [`0001-agent-driven-nvda-over-mcp.md`](specs/0001-agent-driven-nvda-over-mcp.md).

## What this is

An MCP server that lets an AI agent **drive NVDA** (the screen reader): send
keyboard gestures, read back what NVDA speaks/brailles, and introspect its
state. First use case: functional testing of NVDA add-ons; the primitives are
general.

```
MCP client (Claude Code, ...)        │ MCP over stdio
        ▼
mcpServer/   nvda-mcp Python package  │ JSON-lines over TCP, 127.0.0.1 only
        ▼
bridgeAddon/ nvdaMcpBridge NVDA addon (global plugin + spy synth driver)
```

The two halves are separate processes and meet **only at the loopback socket**,
so the server survives NVDA restarts and NVDA's embedded Python never hosts the
asyncio MCP server.

## Layout

| Dir | What | Host / Python |
|---|---|---|
| `shared/` | Canonical **stdlib-only** wire protocol (`nvda-mcp-wire`). Envelope + per-command dataclasses + `from_dict` validator + JSON-lines helpers. Unit-tested once. | desktop CPython |
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

Bridge (`bridgeAddon/addon/globalPlugins/nvdaMcpBridge/`):
`domain/controllers/session.py`; entities `speech_buffer.py` /
`braille_buffer.py`; adapters `json_lines_channel.py`, `file_transcript.py`,
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
  dependencies are exactly the ports it lists.
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
| leaf adapters (`real_clock.py`, `text_file_writer.py`, `socket_transport.py`) | They make no decisions; there is nothing `open()` doesn't already guarantee. If you are adding a test here, you have put a decision in a leaf — move it up. |
| `plugin.py` | The NVDA edge. Covered by the integration tests, not units. |

**Fakes mirror the ports they stand in for**, same one-class-per-file rule and
no re-export facade: `tests/fakes/clock.py` ↔ `domain/ports/clock.py`, imported
as `from fakes.clock import FakeClock`.

**`tests/integration/` is named after the USE CASE, not the file** — these prove
a whole scenario end to end (e.g. `test_silent_session_restores_synth.py`),
need a live NVDA, and are the only place that proves a *real* adapter behaves
like its fake. Milestone 6.

Keep test module basenames unique across the tree (pytest's prepend import mode
requires it). Mirroring gives that for free, since source basenames are unique.

### Doubles are hand-written stateful fakes, not mocks

One per port, in `tests/fakes.py`, each **subclassing its ABC** — so a fake that
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

## Workflow

Built in **modular sessions**, one PR each, so context stays small and fresh
sessions cold-start cheaply. Merge order follows dependencies: **A (foundation)
→ then B (bridge core) and D (server) in parallel → C (bridge↔NVDA) → E
(introspection + real-world) → F (packaging)**. Each session only needs the
merged code + the spec + this file. See the spec's Milestones section.

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
- **NVDA reference source is `../nvda/source`** (2026.1). Consult it for APIs
  rather than guessing; only `source/` is needed. It is a **reference only** —
  not a build/CI/type-check dependency. Adapter files that import NVDA go in
  pyright's `ignore` list (see the ports & adapters section); the domain they
  serve stays fully strict-checked.
