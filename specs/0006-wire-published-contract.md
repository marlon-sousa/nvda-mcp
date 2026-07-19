# Spec 0006 — wire: the published contract + capability-aware `hello`

Implementation contract for ROADMAP lane 1, entry 8 (headless B follow-up),
derived from the multi-reader direction RFC
([spec 0005](0005-multi-reader-direction.md)). Authored on the entry's branch
per process; code starts only after this spec is agreed in conversation, and
the spec merges with the implementing PR.

## Goal

Turn the wire contract into the two artifacts spec 0005 decided on:

1. The Python module stays the canonical implementation (same-bytes sharing,
   unchanged), but `hello` learns to announce **which reader answered and
   what it can do** — the multi-reader capability story, in the contract from
   birth.
2. A **published contract** appears under `specs/wire/v1/`: a hand-written
   prose semantics document plus a JSON Schema **generated from the
   dataclasses**, with a CI drift gate so the schema can never disagree with
   the code. This is the artifact a future non-Python bridge author consumes.

Everything here is headless; nothing touches NVDA.

## Wire changes (protocol v1, pre-release amendment — no bump)

Protocol v1 has no external consumers yet (spec 0005), so these amendments
are free. All in `shared/nvda_mcp_wire/protocol.py`, which stays
**stdlib-only** (hard invariant 1):

1. **`ReaderInfo`** — frozen dataclass: `name: str` (e.g. `"nvda"`),
   `version: str`.
2. **`Capability`** — `StrEnum`, the closed set of announced abilities, one
   per command group: `SPEECH = "speech"`, `BRAILLE = "braille"`,
   `GESTURES = "gestures"`, `FOCUS = "focus"`, `STATE = "state"`,
   `CONFIG = "config"`. The NVDA bridge advertises all six. The prose spec
   directs non-Python implementations to **ignore unknown capability
   strings** (forward compatibility); on the Python side the closed-set
   validation is safe precisely because both halves share the same bytes —
   revisited if/when the contract is externalized.
3. **`HelloResult`** — `nvdaVersion: str` is **replaced** by
   `reader: ReaderInfo`, and `capabilities: list[Capability]` is added.
   (Dropping rather than deprecating `nvdaVersion` is deliberate: pre-release
   v1 is amendable, and a reader-named field contradicts spec 0005.)
4. **`CommandShape`** — frozen dataclass (`params: type | None`,
   `result: type`) — plus **`COMMAND_SHAPES: Mapping[Command, CommandShape]`**:
   the contract's own statement of which payload types belong to which
   command. Today that knowledge lives implicitly in the bridge's handler
   registry; making it contract data is what lets the schema be generated
   (and lets either half validate payloads generically later).

## The schema generator

`shared/nvda_mcp_wire/schema.py` — a pure builder,
`build_wire_schema() -> dict[str, Any]`, walking `COMMAND_SHAPES` and the
dataclass type hints (the same `get_type_hints` machinery `from_dict`
validates with, run in the other direction) to emit one JSON Schema
(draft 2020-12, standard vocabulary only) describing:

- the `Request`/`Response` envelope,
- per-command `params` and `result` schemas keyed by wire command name,
- enums as closed `enum` lists, optionals/unions, nested dataclasses,
  `list`/`dict` shapes — exactly the constructs `_coerce` understands.

Output is **deterministic** (stable key order) so the committed file diffs
cleanly. `python -m nvda_mcp_wire.schema` prints the canonical JSON to
stdout; the committed artifact is `specs/wire/v1/schema.json`. The module is
stdlib-only like its sibling and is **never synced into the addon**
(`sync_shared.py` copies `protocol.py` only — unchanged).

## The prose document

`specs/wire/v1/protocol.md`, hand-written — the semantics the schema cannot
carry, each currently living only in code, tests, or specs 0002/0004:

1. Transport and framing: JSON lines, UTF-8, one object per line, loopback
   TCP, default port.
2. Envelope: request ids, exactly-one-of `result`/`error`, unknown command →
   error reply (session survives), malformed line → error (session survives).
3. Handshake: `hello` first, version equality check, capture-mode selection,
   what `HelloResult` announces (`reader`, `capabilities`, synth, log path),
   mismatch behaviour (handshake fails, session ends).
4. Capabilities: meaning of each member, the ignore-unknown rule, and that a
   command outside the announced set fails with a normal error reply.
5. Index semantics: monotonic speech/braille indices, half-open
   `[fromIndex, toIndex)` ranges, `sinceIndex` queries, the wait commands'
   timeout behaviour.
6. Liveness: `ping`, heartbeat and inactivity watchdogs, `bye`, and the
   teardown promise (synth restored on every path).
7. Versioning policy: `PROTOCOL_VERSION` equality for now; pre-release v1
   amendment rule; extra-fields-ignored tolerance; the ignore-unknown
   capability rule as the one forward-compatibility carve-out.

## CI drift gate

The `shared` job gains one **step** (job names are load-bearing — gotchas
section — so no new job): regenerate the schema and `git diff --exit-code
specs/wire/v1/schema.json`. Code changed without regenerating → red.

## Bridge-side changes

- `domain/controllers/commands/hello.py` — wired with `reader: ReaderInfo`
  and `capabilities: list[Capability]` instead of `nvda_version: str`; fills
  the new `HelloResult` fields. No other handler changes.
- `wiring.py` — `build_session` carries the reader info and the full NVDA
  capability list to the hello handler.
- The addon's `protocol.py` copy is regenerated by `sync_shared.py` as usual
  (gitignored build artifact, no repo change).

## Class/file layout (roles + collaborators)

| File | Status | Role | Collaborators |
|---|---|---|---|
| `shared/nvda_mcp_wire/protocol.py` | amended | canonical wire contract (data + validator) | adds `ReaderInfo`, `Capability`, `CommandShape` + `COMMAND_SHAPES`; amends `HelloResult`. Consumed by both halves and by `schema.py`. |
| `shared/nvda_mcp_wire/schema.py` | new | supporting construct: pure schema builder (`build_wire_schema()`), stdout emitter under `__main__` only | reads `protocol.py`'s dataclasses and `COMMAND_SHAPES`; used by CI and by whoever regenerates the committed schema. No IO outside `__main__`. |
| `specs/wire/v1/protocol.md` | new | published contract, prose half | hand-written; versioned by `PROTOCOL_VERSION`. |
| `specs/wire/v1/schema.json` | new (generated, committed) | published contract, parseable half | emitted by `schema.py`; guarded by the CI drift step. |
| `shared/tests/unit/test_schema.py` | new | unit tests (mirror of `schema.py`) | asserts envelope + per-command coverage, determinism, closed enums, optional/nested handling. |
| `shared/tests/unit/test_protocol.py` | amended | unit tests (mirror of `protocol.py`) | `ReaderInfo` round-trip, `Capability` validation, `COMMAND_SHAPES` covers every `Command` member. |
| `bridgeAddon/.../commands/hello.py` | amended | command handler (bootstrap) | now holds `ReaderInfo` + capability list; builds the enriched `HelloResult`. |
| `bridgeAddon/.../wiring.py` | amended | composition root | passes reader/capabilities to the hello handler. |
| `bridgeAddon/tests/unit/.../test_hello.py` | amended | unit tests (mirror) | asserts the new fields. |
| `bridgeAddon/tests/integration/test_wire_session_roundtrip.py` | amended | headless integration scenario | asserts `reader`/`capabilities` arrive over the wire. |
| `.github/workflows/` (`shared` job) | amended | CI drift gate step | regenerate + diff the committed schema. |

No new ports, controllers, entities, or adapters — the entry is contract data
plus one pure builder.

## Acceptance criteria

1. `hello` over the headless wire scenario returns
   `reader == {"name": "nvda", "version": <wired value>}` and all six
   capabilities; `nvdaVersion` is gone from the wire.
2. A test proves `COMMAND_SHAPES` has an entry for every `Command` member, so
   a new command cannot be added without declaring its shapes (and thereby
   appearing in the schema).
3. `python -m nvda_mcp_wire.schema` output is byte-identical to the committed
   `specs/wire/v1/schema.json`, and the CI drift step fails when it is not.
4. The generated schema validates representative frames: a valid
   `HelloResult` payload passes; a payload with an unknown `CaptureMode` or a
   missing required field fails. (Asserted structurally in
   `test_schema.py` — no third-party JSON-Schema validator is added to
   `shared/`.)
5. `protocol.py` and `schema.py` import nothing outside the stdlib.
6. `specs/wire/v1/protocol.md` covers the seven numbered semantics areas
   above.
7. pyright strict and all test suites green on the `shared` and `bridge`
   jobs; no new pyright-ignore entries.

No manual NVDA checklist: no NVDA-facing surface.

## Out of scope

- Schema-first code generation, or making the schema canonical — revisited
  when the first non-Python bridge author arrives (spec 0005).
- Renaming the `nvda_mcp_wire` package — deferred until the repository name
  is decided, so both rename once.
- Capability *enforcement* in the bridge dispatcher (rejecting commands
  outside the announced set) — the NVDA bridge announces everything, so
  enforcement has no observable effect until a partial-capability bridge
  exists; the prose spec states the rule, session C+ implements it if needed.
- Real `reader.version` values from NVDA (session C wires those); server-side
  consumption of `capabilities` (session D).
- Publishing the contract anywhere beyond the repo (release assets / Pages —
  spec 0005's split trigger).

## Definition of done

Merged with green CI; ROADMAP entry 8 flipped to Done by the implementing PR;
any amendment this spec needs during review or implementation rides in the
same PR with a one-line why.
