# Spec 0009 — bridge: NVDA log capture per session

Agreed 2026-07-21 (conversation). ROADMAP lane 1, entry 9.2 (a C follow-up,
alongside entry 9.1).

## Goal

Diagnosing an add-on bug today means a manual ritual: place a marker in NVDA's
log, run the repro, place another marker, copy the slice out, paste it for
analysis. `nvda.log` covers NVDA's whole run — every add-on, every app, since
the last restart — so the marker is the only way to find the needle.

This gives the agent that slice automatically. Every bridge session tees
NVDA's own log to a fresh, private, session-scoped file for exactly its
duration — `hello` to teardown — so there is no haystack to search: the file
*is* the session. `hello` may also request a bumped log level (e.g. `DEBUG`)
for the session, for when the default level does not carry enough detail.

This is deliberately **not** the existing session transcript (spec 0003):
the transcript is the bridge's own domain vocabulary (gestures/speech/session
events) for reconstructing a silent-mode run; this is NVDA's real diagnostic
log — tracebacks, add-on `log.debug()` calls, internal warnings — verbatim,
untouched, just scoped to the session. Two artifacts, two paths, both handed
to the agent at `hello`.

## Decided

- **Always on, no new wire command.** Every session gets a capture file,
  exactly like every session gets a transcript — tied to the same `hello`/
  teardown boundary, no separate start/stop command. `logLevel` is an
  additional, optional knob on `hello`, not a precondition for capture to
  happen at all.
- **The level, if requested, is a real (if temporary) change to NVDA's own
  logging**, not a private filter on the capture file alone. Python's
  `logging` only hands a record to any handler once the *logger* has decided
  to emit it (`Logger.isEnabledFor`), so raising verbosity for the session
  necessarily raises it for `nvda.log` too, for the session's duration. This
  is documented, not hidden: `hello`'s `logLevel` says so, and
  `specs/wire/v1/protocol.md` states it. The previous level is always
  restored at teardown, on every exit path (crash, timeout, panic) — the same
  fail-safe-restore shape already used for the synth (spec 0008) and the
  transcript.
- **Levels offered are exactly NVDA's own valid logging levels** (see
  `logHandler.py`: `DEBUG`, `IO`, `DEBUGWARNING`, `INFO` — the values NVDA's
  own logging-level config accepts, besides `OFF`, which would disable
  logging and makes no sense to *request*). No invented levels.
- **NVDA installs its own handler and level on `log.root`** (the root
  logger), not on the `"nvda"` logger instance itself (`logHandler.py`,
  `_setupLogging`: `log.root.addHandler(...)`, `log.root.setLevel(...)`) —
  because `log` is a named child logger at `NOTSET`, inheriting its effective
  level from the root. The new handler and any level change must land on
  `log.root` too, or capture would silently see nothing.

## Deliverables

All under `bridgeAddon/` unless noted. Every module carries the mandatory
ROLE header.

1. `shared/nvda_mcp_wire/protocol.py` (canonical; synced into the addon by
   `sync_shared.py`, never edited there directly):
   - `LogLevel(StrEnum)` — `DEBUG`, `IO`, `DEBUGWARNING`, `INFO`.
   - `HelloParams` gains `logLevel: LogLevel | None = None` — unset means
     "leave NVDA's level alone".
   - `HelloResult` gains `nvdaLogPath: str` — absolute path to this session's
     NVDA-log capture, alongside the existing `logPath` (the transcript).
   - No `COMMAND_SHAPES` change (the `hello` entry already points at these
     dataclasses); the generated `specs/wire/v1/schema.json` is regenerated
     and `specs/wire/v1/protocol.md` §3 documents the two new fields plus the
     logger-level caveat above.
2. `domain/ports/log_capture.py` — the **LogCapture** port (`abc.ABC`),
   parallel to `Transcript`: `path` (the capture file, valid after `start`),
   `start(level: protocol.LogLevel | None)`, `stop()`. `stop()` must be safe
   to call even if `start()` was never called (teardown calls it
   unconditionally, like the transcript's `session_closed`).
3. `adapters/nvda_log_capture.py` — **NvdaLogCapture**, the port's one real
   implementation. Imports `logHandler` (NVDA), so it is on pyright's
   `nvda_*.py` ignore glob already — no `pyproject.toml` change needed. Picks
   a fresh `nvda-log-<stamp>.log` under a directory (naming/pruning mirrors
   `file_transcript.py`'s `create_session_log`, `keep=20` default, a
   `nvda-log-*.log` glob so pruning never touches `session-*.log`), attaches
   a `logging.FileHandler` (NVDA's own `Formatter`, for output that reads
   like a slice of `nvda.log`) to `log.root`, remembers/restores
   `log.root`'s previous level. A **stateless-per-construction, reused
   singleton**: built once in `plugin.py` like `NvdaSessionSignals`/
   `NvdaAnnouncer` (the bridge serves one session at a time — AGENTS.md), not
   freshly constructed per connection; `start()`/`stop()` reset its
   per-session state each time. No unit test file (deliberate — it imports
   NVDA and makes no decisions pyright can check; covered by the live-NVDA
   checklist below, same table entry as `nvda_session_signals.py`).
4. `tests/fakes/log_capture.py` — **FakeLogCapture**, subclassing the port,
   mirroring `FakeTranscript`'s shape exactly: records `("start", level)` /
   `("stop",)` into `events`, a `fail_on` set for teardown-robustness tests.
5. `domain/controllers/commands/session_context.py` — **SessionContext**
   gains a `log_capture: LogCapture` constructor parameter and public
   attribute, alongside `transcript`.
6. `domain/controllers/session.py` — **Session** gains a `log_capture:
   LogCapture` constructor parameter (last positional, after `announcer`),
   stored and handed into the `SessionContext` it builds. `_teardown()` gains
   one new guarded step, `self._guard(self._log_capture.stop)` — placed
   first, so a bumped level is held no longer than it must be, before the
   adapter-stop/transcript/signals/channel steps.
7. `domain/controllers/commands/hello.py` — **HelloHandler.execute** calls
   `ctx.log_capture.start(params.logLevel)` right after `ctx.transcript.open()`
   (so a version mismatch, which raises first, never starts it — mirrors the
   transcript exactly) and returns `nvdaLogPath=ctx.log_capture.path` in the
   `HelloResult`.
8. `wiring.py` — **build_session** gains a `log_capture: LogCapture`
   parameter (last positional, after `announcer`; `TYPE_CHECKING`-only import
   of the port, same as `Announcer`/`SessionSignals` — wiring.py stays pure),
   passed straight into `Session(...)`.
9. `plugin.py` — constructs `NvdaLogCapture(logs_dir)` once alongside
   `NvdaSessionSignals()`/`NvdaAnnouncer()` and passes it to every
   `build_session` call via `make_session`. `_transcripts_dir()` is renamed
   `_bridge_logs_dir()` (its docstring updated) since it now homes both
   artifacts — same directory, distinguished by filename prefix
   (`session-*.log` vs `nvda-log-*.log`), so each stack's pruning only ever
   touches its own files.
10. Test updates (no new behaviour, just threading the new collaborator
    through): `tests/support/context.py` (`make_context` gains an optional
    `log_capture` param), `tests/unit/domain/controllers/commands/test_hello.py`,
    `tests/unit/domain/controllers/test_session.py` (`run_session` builder +
    a teardown-robustness test mirroring the transcript's), 
    `tests/unit/domain/controllers/commands/test_session_context.py`,
    `tests/integration/test_wire_session_roundtrip.py`,
    `tests/integration/test_socket_session_roundtrip.py`, and
    `shared/tests/unit/test_protocol.py` (the new `LogLevel` enum, the
    optional `logLevel` field, `nvdaLogPath` in `HelloResult`'s
    serialize-all-fields / round-trip tests).

## Acceptance criteria

Automated, on `shared`, `server`, and `bridge` CI jobs (plus the wire-schema
drift gate and the checklist gate staying green):

1. `hello` without `logLevel` still starts capture (file created, no level
   change) and reports `nvdaLogPath`.
2. `hello` with `logLevel` set changes `log.root`'s level for the session and
   restores it at teardown (proved through the port/fake in `bridge`; the
   real `log.root` interaction is edge-only, proved live).
3. Teardown stops capture on every exit path, including when an earlier
   teardown step raises — mirroring `test_teardown_stops_capture_even_when_the_transcript_raises_on_close`.
4. `LogCapture.stop()` is a no-op if `start()` was never called (version
   mismatch never opens the transcript *or* starts capture).
5. Wire schema regeneration (`uv run --python 3.13 python -m nvda_mcp_wire.schema`)
   leaves `specs/wire/v1/schema.json` unchanged from what's committed (i.e. is
   committed correctly the first time).
6. pyright strict is clean on the domain; `nvda_log_capture.py` needs no new
   ignore-list entry (already covered by the `nvda_*.py` glob).

Manual live-NVDA checklist (this PR's body, per AGENTS.md): confirms a real
session produces a `nvda-log-*.log` file distinct from `nvda.log`, that
requesting `logLevel="debug"` actually surfaces DEBUG-level lines that are
normally absent at the default level, and that `nvda.log` itself returns to
its prior verbosity after the session ends.

## Out of scope

- A dedicated start/stop command for finer-than-one-session granularity
  (explicitly deferred in conversation — timestamps inside an already
  session-scoped file give equivalent slicing for free; revisit only if that
  proves insufficient in practice).
- Exposing `logLevel`/`nvdaLogPath` through the MCP server's tool surface —
  lane 2, a follow-up once this lands.
- Remote/pipe transport, capability negotiation changes — unrelated.

## Definition of done

Merged with green CI; ROADMAP entry 9.2 flipped to Done by this PR; the
manual checklist above completed in the PR body.
