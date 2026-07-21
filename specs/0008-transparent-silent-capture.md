# Spec 0008 — transparent silent capture via NVDA's speech filter

Status: **agreed in conversation, 2026-07-21**, and implemented in the entry-9c
PR (#14) that carries this file. This spec **supersedes** the silent-mode
mechanism designed in RFC 0001 ("Fail-safe synth restoration") and
[spec 0007](0007-bridge-nvda-edge.md) (the spy synth + `SynthSwapper`): those
were merged in entry 9b (PR #13); the 9c live-NVDA checklist surfaced the reasons
to replace them, and this entry does so. It also lands two operator features
(session beeps, the `announce` hint channel) and two bug fixes the live testing
exposed. Written to the same discipline as the other specs — prose and tables,
NVDA APIs verified against `../nvda/source` (2026.1) before writing.

## Why the pivot — the spy-synth approach was fragile and non-transparent

RFC 0001 made NVDA go silent by **swapping the user's synth for a bundled spy
driver** (`nvdaMcpSpy`) and defending that swap against config-profile switches
with three layers (config-name agreement, a `pre_configSave` guard, a
`getSynthInstance` patch). Entry 9b implemented it. Live testing (9c) found two
problems, one of them the cardinal one:

1. **It can leave a blind user mute.** NVDA loads/unloads synths on its **main
   thread**; the bridge Session runs on its **server thread**. When an
   app-specific config profile switched during a silent session (frequent — they
   fire on focus change), NVDA's main-thread synth reload raced the bridge's
   server-thread `setSynth`, and NVDA was left holding a dead synth: **silent
   with no way back but a manual restart.** This is the exact invariant the
   fail-safe existed to protect, defeated by the mechanism's own thread model.
2. **It is not transparent.** Other add-ons (and NVDA's own dialogs) could see
   that the configured synth had become `nvdaMcpSpy`. Marlon's requirement
   (2026-07-21): *as far as NVDA and any add-on can tell, the configured synth
   must still be valid and active* — the capture must be invisible.

## The decision — intercept speech, never touch the synth

**Decided.** Silent mode leaves the real synth (espeak/ibmeci/…) **loaded and
active** and instead **intercepts speech before it reaches the synth**:

- NVDA's `speech.speak()` passes every sequence through
  `speech.extensions.filter_speechSequence` (`speech/speech.py:1096`) and returns
  early if a filter empties it (`:1101`). The silent speech source **registers a
  filter that captures the sequence into the buffer and returns it emptied** — no
  audio, synth untouched.
- **Transparency falls out for free:** `getSynth()` still returns the user's real
  synth; nothing swaps, terminates, or renames it. NVDA and every add-on see
  their configured synth, valid and active.
- **The mute-bug class disappears:** we never call `setSynth`, never write
  `config["speech"]["synth"]`, never patch `getSynthInstance`. Config-profile
  switches are irrelevant to us, so there is no main-thread/server-thread race to
  lose.
- **"Restore" cannot fail:** ending a session just **unregisters the filter** and
  speech flows again instantly. There is no synth reload to go wrong. And because
  NVDA holds extension-point handlers by **weak reference**, if the addon ever
  dies the filter drops on its own — the tester cannot be stranded. If the filter
  handler itself raises, `Filter.apply` keeps the original sequence
  (`extensionPoints/__init__.py`), so a bug there **fails toward speech, not
  silence**.

Live mode is unchanged in spirit: it registers on `pre_speechQueued` and does
**not** suppress, so the real synth keeps talking while we observe.

Trade-off accepted: with full suppression there is no synth "done speaking"
signal, so silent mode drops the spy's exact-finish and uses the
`SpeechBuffer`'s elapsed-time heuristic (~1 s) — the same one live mode always
used. A future refinement could strip only the audible parts of the sequence
(keeping `IndexCommand`s) to recover exact-finish while staying silent; it is not
needed for functional testing.

## What this removes and supersedes

Deleted from the bridge (all merged in 9b):

- `adapters/nvda_synth_swapper.py` and the `domain/ports/synth_swapper.py` port.
- `synthDrivers/nvdaMcpSpy.py` (the spy driver) and `adapters/spy_sink.py` (its
  pure rendezvous), plus `adapters/nvda_spy_speech_source.py`.
- The three-layer fail-safe in RFC 0001 §"Fail-safe synth restoration" — now
  **superseded**: there is nothing to fail-safe, because the synth is never
  touched. `AdapterSet` drops `synth_swapper`; the Session teardown no longer
  restores a synth (stopping the speech source is the whole of it).

`hello` reports the real synth name (read via the `Announcer`, below) and never
swaps; the Session no longer records a `swapped_real`.

## New files and classes

| File | Role | Notes |
|---|---|---|
| `adapters/nvda_silent_speech_source.py` | adapter (SpeechSource, silent) | registers/unregisters the `filter_speechSequence` capture-and-suppress handler |
| `domain/ports/session_signals.py` + `adapters/nvda_session_signals.py` | port + adapter | `session_started`/`session_ended` audible cues (NVDA `tones`, spaced via `wx.CallLater`), heard even while suppressed. Two ascending on establish, two descending at teardown. |
| `domain/ports/announcer.py` + `adapters/nvda_announcer.py` | port + adapter | the bridge's line to the **real, loaded** synth: `current_synth()` (the hello name) and `announce(text)` — speaks a hint straight through `getSynth().speak()`, which bypasses the suppression filter, so the tester hears it **even in silent mode**, preceded by two cue beeps. |
| `domain/controllers/commands/announce.py` | command handler | wires the `announce` wire command to the Announcer |
| `adapters/nvda_main_thread.py` | edge helper | `run_on_main` — marshals every NVDA mutation (tones, synth reads/speak) onto NVDA's main thread (fire-and-forget for teardown paths so a main-thread caller cannot deadlock) |

`SessionSignals` and `Announcer` are injected through `wiring.build_session`
(like the `AdapterFactory`) and reach handlers via the `SessionContext`.

## Wire contract change (amends the published v1 contract)

Adds one command and one capability to `shared/nvda_mcp_wire/protocol.py` (and the
generated `specs/wire/v1/schema.json`):

- `Command.ANNOUNCE = "announce"`, params `AnnounceParams{text: str}`, result
  `AckResult` — a **bridge→human** hint channel, not agent-facing data.
- `Capability.ANNOUNCE = "announce"`, added to the NVDA bridge's advertised set
  (`speech`, `braille`, `gestures`, `announce`).

v1 has no external consumers yet, so this is an in-place amendment (per
`specs/wire/v1/protocol.md`), no version bump.

## Bug fixes the 9c live testing surfaced (independent of the pivot)

1. **A crashed client must not kill the server.** `SocketTransport.recv` let
   `ConnectionResetError` (a client crash RSTs the socket) propagate; the Session
   loop only caught `ChannelClosed`, so it escaped up and killed the
   `BridgeServer` accept loop — a crashed *client* took down the *bridge*. Fix:
   the transport leaf maps any socket error other than the idle timeout to `b""`
   (an abrupt reset is an abrupt EOF), and `BridgeServer` wraps each session so no
   session fault can ever break the accept loop. Regression-tested headlessly
   (including a real `SO_LINGER`-0 RST mid-session).
2. **The build shipped stale adapters.** `buildVars.pythonSources` used the
   AddonTemplate's non-recursive `globalPlugins/nvdaMcpBridge/*.py`; sconstruct
   turns each source into a build dependency, so edits under `adapters/` or
   `domain/` changed no tracked dependency and `scons` reported "up to date"
   without repackaging — even though the build action rglobs the whole tree.
   This addon is a hexagonal **package**, not the flat single-module addon the
   template assumes. Fix: the recursive glob `**/*.py`.

## Definition of done

Implemented in the entry-9c PR (#14) that carries this spec. Headless suites,
pyright strict, ruff, and the schema drift gate all green; the pivot's NVDA edge
is proven by the 9c live-NVDA checklist (silent capture with the real synth still
loaded, the `announce` hint audible mid-silence, the session beeps, a
config-profile switch mid-session as a non-event, panic, NVDA shutdown, and — as
a bonus — a client crash the server survives). This spec's decision (intercept,
do not swap) is **Decided**; RFC 0001's fail-safe section is superseded here.
