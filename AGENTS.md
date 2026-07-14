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

```
<package>/
  __init__.py     # entry point ONLY. The bridge's exposes GlobalPlugin lazily
                  # via a module-level __getattr__, so importing the package
                  # does NOT import NVDA (tests import the domain directly).
  domain/         # PURE core: no NVDA / no MCP SDK / no sockets. Headless-tested.
    ports/        #   the abstract interfaces, ONE PORT PER FILE (abc.ABC +
                  #   @abstractmethod); a port's own DTO lives in its file;
                  #   __init__.py re-exports them all
    <controller>.py    #   the state machine / translator
    ...           #   pure value objects + logic
  adapters/       # the ONLY place NVDA / the MCP SDK / the OS / real IO lives
    ...           #   one class per file (private helpers may share the file)
  wiring.py       # composition root: binds ports→adapters, builds the controller
```

Bridge (`bridgeAddon/addon/globalPlugins/nvdaMcpBridge/`): `domain/session.py`
(controller), `domain/speech_buffer.py`, `domain/framing.py`; adapters
`real_clock.py` now, `nvda_*.py` + `socket_transport.py` in session C;
`protocol.py` (the synced shared wire module) sits at the package root. Server
(session D): `domain/` holds the tool translator + a `BridgeClient` port;
adapters hold the FastMCP/stdio server and the real TCP bridge client.

Rules that keep this honest:

- **Ports are `abc.ABC`s with `@abstractmethod`** (not `Protocol`): an
  incomplete adapter fails at construction, and the interface itself can't be
  instantiated. The domain depends only on ports; adapters subclass and
  implement them; **`wiring.py` is the only place that knows both.**
- **One interface/class per file.** Each **port** is its own file in
  `domain/ports/`; each **adapter** is its own file in `adapters/` (a small
  private helper may share its adapter's file). A **DTO lives in the same file
  as the port or adapter that owns it** (e.g. `AdapterSet` sits with
  `AdapterFactory`). `domain/ports/__init__.py` re-exports every port so callers
  write `from ..ports import X` without caring which file it lives in. This
  keeps the seam list scannable and diffs small as sessions C–F add adapters.
- **Test doubles are hand-written stateful fakes** (in `tests/`), one per port,
  each subclassing its ABC — not `unittest.mock`. The domain drives its
  collaborators through real protocols (read loops, index reads, state
  transitions), so the doubles need behaviour, not call-recording; mocks would
  re-script return values per test and exercise less. Signature/contract drift
  is already caught by the ABCs (runtime) + pyright strict (CI); behavioural
  conformance of the *real* adapters is proven by the milestone-6 live-NVDA
  integration tests, not by the unit doubles.
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
