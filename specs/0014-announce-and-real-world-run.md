# Spec 0014 — expose `announce`, and the real-world run (entry 11)

Status: **drafted 2026-07-23, awaiting review.** Not yet agreed in
conversation; entry 11a's code was written alongside this draft at Marlon's
explicit request, and the draft is judged before it merges, not after.

Covers board entry 11, delivered as two sequential PRs: **11a** exposes the
`announce` command at the MCP server, and **11b** is the end-to-end run against
EnhancedFindDialog with Claude Code as the MCP client. They share one spec
because 11a exists to serve 11b: the run is the first time an agent drives a
real add-on with a human in the room, and the agent having *no way to say
anything to that human* is the gap 11a closes.

## Goal

Prove the whole stack against a real add-on and a real user, and fix the one
thing that discovery showed was missing before that run is worth doing.

## Why this comes before introspection — **proposed**

Entry 11 originally bundled introspection with the real-world run. A discovery
pass on 2026-07-23 found they are nearly independent, and that the run is the
one that should go first:

1. **The run is not blocked.** The capability gate derives the advertised tool
   set from what `hello` announced, and the NVDA bridge announces
   speech/braille/gestures/announce today. So an agent connecting right now gets
   the four ungated tools, the five speech tools, `getBraille` and
   `pressGesture`. Press a gesture, read what was spoken — that *is* the loop the
   run exists to exercise, and it is the loop EnhancedFindDialog needs tested.
2. **Introspection is smaller than it looked, and is lane 1 only.** Its whole
   server half shipped in 10b. See [spec 0015](0015-bridge-introspection.md).
3. **Findings should shape what follows.** The board already says the run's
   findings spawn iteration entries. Running first means 11.1, 11.2 and 11.3 are
   informed by a real session instead of by speculation — which matters most for
   11.2, where the question "is a reply dialog needed, or is an acknowledgement
   gesture enough?" is genuinely open and a single real run answers it.

## The run is `live` mode, attended — **proposed, and load-bearing**

This is the decision the ordering rests on, so it is stated before the
deliverables rather than buried in the checklist.

In `silent` mode the capture filter empties every speech sequence, so **all** of
NVDA's speech is suppressed, not just the app under test. An agent that
announces "I am stuck on a password field" is then telling the tester something
they cannot act on: they cannot hear their way to another window to reply, they
cannot hear what they type, and their only exit is the panic gesture
(`NVDA+control+shift+b`), which stops the entire bridge and ends the session.
Announce, alone, in silent mode, reports a problem while removing the means to
solve it.

In `live` mode the real synth keeps speaking and capture is by observation
(`pre_speechQueued`, no suppression). The tester hears the app under test, hears
themselves alt-tab to the agent's window, and replies there normally. Everything
the run needs to prove — gestures land, speech is captured, indices behave — is
mode-independent, and the two things that are not (suppression, restoration) were
already proven by the 9c and 9.1a live checklists.

So: **run 11b in `live`, with the tester at the keyboard.** Silent-plus-unattended
is the configuration that genuinely needs a human-in-the-loop channel, and that
is [spec 0016](0016-human-in-the-loop.md), scheduled after this run precisely so
the run can say what it should contain.

This does mean `announce` is a *convenience* during 11b rather than a
prerequisite — in live mode the agent could equally write to its own chat and be
read there. It is still 11a and still first, for three reasons: it costs five
files, none of them on the wire; the bridge half has been sitting complete and
unreachable since 9c, which is a defect independent of any run; and the first
silent session, whenever it happens, needs it to exist already.

## Decided — the announce exposure

### The bridge half is done; only the server is missing

Spec 0008 landed `Command.ANNOUNCE`, `AnnounceParams`, `Capability.ANNOUNCE`,
the `Announcer` port, `NvdaAnnouncer` and `AnnounceHandler`. The bridge
advertises `announce` in `NVDA_CAPABILITIES` and serves it. `NvdaAnnouncer`
speaks through `synthDriverHandler.getSynth().speak()` directly, which is *below*
`speech.speak()` and therefore below the `filter_speechSequence` suppression
hook — which is why a hint is audible in silent mode — preceded by two cue beeps.

The generated Go binding already carries `CommandAnnounce`,
`CapabilityAnnounce` and `AnnounceParams`, because it is generated from the same
`protocol.py`. **So the wire does not change and `schema.json` does not change.**
The drift gate and the conformance job are untouched.

What is missing is only the server's own vocabulary and surface:
`domain/entities/capability.go` has no `CapabilityAnnounce`, the handshake
therefore maps it to nothing, `ReaderConnection` has no field to hold it, there
is no port, no client method, and no tool. The capability arrives from `hello`
and — correctly, per `NewSet`'s "unknown strings survive" rule — is reported by
`screenreader://info` and then ignored.

### `announce` is a capability-gated tool like any other

It gets a port, a nil-when-unannounced field on `ReaderConnection`, and a
`ToolContext` accessor, exactly as `braille` and `gestures` do. No special case.
A reader whose bridge cannot speak to the user simply never announces
`announce`, and the tool is never advertised — the same structural gate, for the
same reason.

### The tool is named `announce`, not `say` or `notify`

It matches the wire command name, as every other tool does (`get_braille` /
`getBraille`, `press_gesture` / `pressGesture`). The snake_case/camelCase split
between MCP tool names and wire command names is already the convention.

### The description carries the operational warning

The tool's `Description()` is agent-facing text and is most of what the tool
really is. It must say the three things an agent cannot infer from the schema:
that this reaches a **human**, audibly, and is not a logging channel; that it is
audible even in `silent` mode, which is the only reason it exists; and — the one
that prevents a bad session — that in `silent` mode the human **cannot reply and
cannot navigate**, so an announcement there should tell them to press the panic
gesture rather than ask them a question. Until 11.2 lands there is no reply
channel, and the agent must not be led to believe otherwise.

## Class/file layout — 11a

All under `server/`. Six files touched, two of them tests.

### 1. `domain/ports/announcer.go` — new port

- **Role:** domain port. The `announce` capability group.
- **Collaborators:** implemented by `adapters/bridge/json_lines_client.go`;
  handed out by `adapters/bridge/handshake.go` only when the reader announced
  `announce`; used by the `announce` tool through `ToolContext.Announcer()`.
- **Shape:** `type Announcer interface { Announce(text string) error }`. No DTO —
  the command's result is `AckResult` and there is nothing in it worth
  surfacing beyond "it did not fail".

### 2. `domain/entities/capability.go` — one constant

- Add `CapabilityAnnounce Capability = "announce"` to the existing const block,
  and amend the block's doc comment, which currently reads that the NVDA bridge
  announces `announce` *beyond* the groups the contract defines. It is a defined
  group as of spec 0008; the comment is stale in the same way protocol.md §4 is
  (below).

### 3. `domain/ports/session_dialer.go` — one field

- `ReaderConnection` gains `Announcer Announcer`, nil exactly when the reader did
  not announce the capability. No behaviour, no constructor change.

### 4. `domain/controllers/tools/tool_context.go` — one accessor

- `func (c ToolContext) Announcer() (ports.Announcer, error)`, following the
  existing six verbatim: nil connection or nil port yields
  `c.missing(entities.CapabilityAnnounce)`.

### 5. `domain/controllers/tools/announce.go` — new controller

- **Role:** controller, one per tool. Gated on `announce`.
- **Collaborators:** `ports.Announcer` via `ToolContext.Announcer()`; listed by
  `registry.go`.
- **Params:** `{ "text": string }`, required, `additionalProperties: false`.
  Rejects empty/whitespace text with a plain error — an empty announcement is two
  cue beeps and silence, which reads to the tester as a malfunction.
- **Result:** `{ "announced": text }`, echoing what was spoken. Same reasoning as
  `press_gesture` echoing its ids: there is no return value from the reader, so
  the only useful confirmation is that this exact string reached it.

### 6. `adapters/bridge/json_lines_client.go` — one method

- `func (c *JSONLinesClient) Announce(text string) error`, a `call` of
  `wire.CommandAnnounce` with `wire.AnnounceParams{Text: text}` and
  `DefaultCallTimeout`. Result discarded (`AckResult` is `{ok: true}`).
- Added to the compile-time port-satisfaction proof block at the top of the file.

### 7. `adapters/bridge/handshake.go` — one gate line

- `if capabilities.Has(entities.CapabilityAnnounce) { connection.Announcer = client }`.

### 8. `domain/controllers/tools/registry.go` — one line

- `&Announce{}` in `BuildRegistry`, in its own "Gated on `announce`" group after
  `press_gesture`. `Catalog()` derives the gate from the list, so nothing else
  changes.

### 9. `fakes/announcer.go` — new fake

- **Role:** test double, mirroring `ports.Announcer`. A recorder, like
  `FakeGestureSender` and for the same stated reason: the call has no return
  value worth asserting on, so "what was announced, in order" is the requirement.
- `Announced() []string`, `FailWith(error)`, mutex-guarded.

### 10. Test updates

- `domain/controllers/tools/announce_test.go` — the tool: happy path reaches the
  port with the exact text; empty and whitespace-only text rejected before the
  port is touched; no connection yields a `CapabilityError` naming
  `announce`; a reader connected *without* the capability yields a
  `CapabilityError` naming the reader.
- `testsupport/` — the existing connection/tool builders gain the announcer
  wherever they assemble a full-capability `ReaderConnection`.
- The handshake test that asserts which ports are handed over for a given
  announced set gains `announce`.
- The MCP integration test that asserts the advertised tool list gains
  `announce` in the gated set.

## Deliverables — 11b, the run

11b adds no production code. Its deliverable is the checklist, run against a
real NVDA with the tester at the keyboard, and the iteration entries its
findings spawn.

Setup: NVDA 2026.1.x with the bridge add-on installed and the server started;
Claude Code as the MCP client over stdio; EnhancedFindDialog installed as the
add-on under test; `connect_reader` with `mode: "live"`.

The checklist lives in the PR body as checkboxes, per AGENTS.md. Proposed items:

1. `list_readers` finds NVDA without dialing; `connect_reader` handshakes over
   the named pipe and reports which endpoint answered.
2. `screenreader://info` reports reader `nvda`, the real NVDA version, the live
   synth name, and the announced capability set.
3. The advertised tool list is exactly the ungated four plus speech, braille,
   gestures and announce — and does **not** include focus/state/config, which
   the bridge does not announce.
4. `announce` is heard: two cue beeps then the text, through the real synth.
5. Bookmark with `get_next_speech_index`, `press_gesture` to open
   EnhancedFindDialog, `get_speech` from the bookmark returns exactly that
   dialog's announcements and nothing that preceded them.
6. `wait_for_speech` finds an expected string and returns its index; the same
   call with `after_index` past it returns `found: false` at the timeout rather
   than a lost connection.
7. Half-open ranges hold across three consecutive `get_speech` calls: no
   overlap, no gap.
8. `get_braille` returns the display line, and its indices are independent of the
   speech indices.
9. A full EnhancedFindDialog interaction — open, type a term, move between
   results, close — is driven end to end from the agent and its announcements
   are read back correctly.
10. A tool call after `disconnect_reader` returns the "connect first" error, and
    the gated tools are retracted from the list.
11. The session transcript and the NVDA log capture both exist, are distinct
    files, and cover exactly this session.
12. `status` after an idle period past the bridge's inactivity window reports the
    loss honestly rather than a stale "connected".

Findings are written inline on the unchecked item (NVDA version, expected vs
observed) and become E.n entries in ROADMAP.md.

## Documentation this PR must also correct

[`specs/wire/v1/protocol.md`](wire/v1/protocol.md) is stale in three places,
all of them things an agent or a future bridge author would be misled by, and
all in the sections 11a touches:

- **§4, capture modes.** Still says `silent` means "a bundled spy synthesizer
  replaces the reader's real synth for the session" and that the bridge "must
  restore the real synth on every teardown path". Spec 0008 replaced that
  mechanism fifteen PRs ago: nothing is swapped, capture and suppression happen
  at `filter_speechSequence`, and teardown unregisters a filter.
- **§6, teardown.** Repeats "in `silent` mode that means putting the user's real
  synthesizer back."
- **§4, capability table.** Omits `announce` entirely, though `protocol.py` has
  had `Capability.ANNOUNCE` since 9c and the NVDA bridge advertises it. The
  table's closing line, "The NVDA bridge announces all six", is wrong in both
  directions — it announces four of these seven today.

Also stale, and corrected here: `CaptureMode.SILENT`'s docstring in
`shared/nvda_mcp_wire/protocol.py` ("Bundled spy synth replaces the real
synth"). Docstring only — no shape change, so `schema.json` does not move.

## Out of scope

- Any reply channel from the human back to the agent — [spec 0016](0016-human-in-the-loop.md).
- Suspending suppression mid-session — [spec 0016](0016-human-in-the-loop.md).
- `getFocusInfo`/`getState`/`getConfig`/`setConfig` — [spec 0015](0015-bridge-introspection.md).
- Any wire or `schema.json` change. If 11a finds it needs one, that is a signal
  the design is wrong, not a licence to amend.

## Definition of done

**11a:** the six production files above, the fake, the tests; Go vet, the Go
suite, and the conformance job green. The conformance job is the meaningful one
here — it runs the built binary against the real Python bridge, so it proves the
new tool reaches a real `AnnounceHandler` over a real pipe, not a Go fake.

**11b:** every checkbox in the PR body checked or annotated with a finding, the
`no unchecked checkboxes` job green, and any finding that requires a change
recorded as an E.n entry in ROADMAP.md.
