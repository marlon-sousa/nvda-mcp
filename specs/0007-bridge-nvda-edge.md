# Spec 0007 — bridge↔NVDA: connection stack, real adapters, spy synth (session C)

> **Silent-mode mechanism superseded by
> [spec 0008](0008-transparent-silent-capture.md) (2026-07-21).** The spy synth
> (`nvdaMcpSpy`), the `SynthSwapper`, and the fail-safe below were implemented in
> 9b, then replaced in 9c after live testing: silent mode now leaves the real
> synth loaded and intercepts speech at `filter_speechSequence` (transparent, and
> it cannot strand the user mute). 9a (the connection stack) and the 9c switch-on
> / packaging still stand. Read spec 0008 for the current silent-mode design.

Implementation contract for ROADMAP lane 1, entry 9 (session C). Authored on
the entry's branch per process; code starts only after this spec is agreed in
conversation. Like spec 0004, one spec covers the whole entry, delivered as
**three sequential PRs**, each judged against its slice:

- **9a** — the connection stack: headless, CI-provable.
- **9b** — the NVDA adapters: code only, the addon stays inert, judged on
  review plus the headless suites — no live surface yet.
- **9c** — plugin wiring, panic gesture, packaging, and the **live-NVDA
  checklist**.

The 9b/9c split (agreed 2026-07-19) exists to separate review-heavy adapter
code from checklist iteration: live-checklist findings land as small, visible
deltas on the small 9c PR — including fixes to 9b's already-merged adapters —
instead of churning inside one large PR that then needs re-review.

Every NVDA API named here was verified against the reference source
(`../nvda/source`, 2026.1) before writing, not recalled from memory. In-tree
precedent: NVDA's own `_remoteClient` captures speech via
`speech.extensions.pre_speechQueued` and braille via `braille.pre_writeCells`
(`_remoteClient/session.py:343-355`) — the exact pattern our live-mode
adapters use.

## Goal

After entry 7 the domain is complete and headless; after this entry a real
server can dial a real NVDA and run a real session. Three slices:

- **9a — the connection stack (headless):** the listening edge — a `Listener`
  seam with a TCP leaf, the `SocketTransport` leaf that spec 0002 designed
  for, and **`BridgeServer`**, the start/stop lifecycle controller with
  observable status that entry 9.1's control dialog will drive (agreed
  2026-07-18, recorded on the board). Proven end-to-end by a real-socket
  headless integration scenario in CI.
- **9b — the NVDA adapters:** the real adapters behind the 7a ports and the
  `nvdaMcpSpy` synth driver — the NVDA-importing files on pyright's ignore
  list, `spy_sink` strict-checked and unit-tested. Nothing is wired: the
  plugin does not build or start anything, so the addon's behavior when
  installed is unchanged and the "safe to leave installed" invariant holds
  trivially.
- **9c — the switch-on:** `plugin.py` wiring, the panic gesture, the scons
  package — and the manual live-NVDA checklist in the PR body, which is where
  the 9b adapters get their live proof.

## 9a — the connection stack

### New files and classes

| File | Role | Collaborators |
|---|---|---|
| `adapters/ports/listener.py` | adapter seam (`abc.ABC`) | **Listener**: `open()` binds and listens; `accept() -> Transport` blocks up to a poll window and raises `TimeoutError` when idle (mirroring the `Transport.recv` contract so the leaf is trivial); raises `ListenerClosed` (same file) once closed; `close()` idempotent, unblocks a pending `accept`; `endpoint: str` property (e.g. `"127.0.0.1:8765"`) — the status display 9.1 needs. |
| `adapters/tcp_listener.py` | leaf adapter (implements Listener) | Real `socket`: bind loopback only, `listen(1)`, `settimeout`, `accept()` wraps the connection in a `SocketTransport`. No decisions — ~20 lines, no unit tests (the 0002 leaf rule). |
| `adapters/socket_transport.py` | leaf adapter (implements the Transport seam) | Real connected socket: `recv` (`settimeout` → `TimeoutError`, `b""` at EOF), `sendall`, `close`. The leaf spec 0002 shaped its seam for; no decisions, no unit tests. |
| `adapters/bridge_server.py` | **adapter-layer controller** (named supporting construct) | **BridgeServer** + its DTOs **`ServerState`** (enum: `STOPPED`, `LISTENING`, `SESSION_ACTIVE`) and **`ServerStatus`** (frozen dataclass: state + endpoint). Holds the Listener seam and a `session_factory: Callable[[Transport], Session]`; owns the server thread. Built by `plugin.py` (production) / tests (fakes). Used by the plugin now, by 9.1's dialog next. |
| `tests/fakes/listener.py` | fake (subclasses Listener) | Scripted: connections (as fake transports), timeouts, closure; records `close()`. |
| `tests/unit/adapters/test_bridge_server.py` | unit tests (mirror) | Drives BridgeServer against the fake listener + a fake session factory. |
| `tests/integration/test_socket_session_roundtrip.py` | headless integration scenario | The real stack over a real socket — see acceptance. CI-runnable: sockets need no NVDA. |

Not in the domain, deliberately: BridgeServer's collaborators are adapter
seams (`Listener`, `Transport`) which the domain must never see, so it lives
in `adapters/` as the connection edge's orchestrator — same doctrine as
`JsonLinesChannel` (an upper adapter holding every decision, unit-tested
against a fake seam), one level further out. The Session and everything
behind it are untouched.

### BridgeServer semantics (the decisions its tests pin)

1. **Lifecycle:** `start()` spawns the server thread and moves
   `STOPPED → LISTENING`; `stop()` is idempotent, requests teardown of any
   active session (`Session.request_teardown` — the one cross-thread call the
   Session permits), closes the listener to unblock `accept`, joins the
   thread, and lands in `STOPPED`. `status` is a thread-safe snapshot
   (`ServerStatus`) — polled by tests today, by the 9.1 dialog tomorrow.
2. **One session at a time:** the loop is `accept → build session via the
   factory → session.run() inline on the server thread → back to accepting`
   (`LISTENING → SESSION_ACTIVE → LISTENING`). While a session runs nothing
   is accepted (`listen(1)` backlog holds or refuses a second dial). A
   session ending — `bye`, EOF, watchdog — returns the server to `LISTENING`
   without a restart: sequential sessions against one server must work.
3. **Failure posture:** an `accept` `TimeoutError` just polls again (it
   exists so `stop()` is prompt); `ListenerClosed` during `run` means
   `stop()` was called; an unexpected listener error stops the server rather
   than spinning. The session's own teardown promise (synth restore in
   `finally`) is the Session's job — BridgeServer never touches synths.

### 9a acceptance criteria

Unit (fake listener + fake factory): start reports `LISTENING` with the
endpoint; an accepted connection reports `SESSION_ACTIVE` and hands the
transport to the factory; session end returns to `LISTENING`; a second
connection then starts a second session; `stop()` while listening joins
promptly; `stop()` during an active session tears the session down (fake
swapper restored); `stop()` twice is safe; a listener fault stops the server.

Integration (`test_socket_session_roundtrip.py`): a real `TcpListener` on an
ephemeral loopback port + `BridgeServer` + `FakeAdapterFactory`; a client
socket dials and runs hello → echo → pressGesture/getSpeech → bye over real
TCP through `JsonLinesChannel`; asserts the scripted speech comes back, the
fake synth is restored, the server returns to `LISTENING`, and a **second**
dial-and-session succeeds; then `stop()`. pyright strict clean; nothing in 9a
imports NVDA; no additions to the ignore list.

## 9b — the NVDA adapters

### New files and classes

All `adapters/nvda_*.py` files and the spy driver go on pyright's **ignore
list** (hard invariant 4); `spy_sink.py` is pure and stays strict-checked and
unit-tested. `plugin.py` is untouched in this PR — wiring is 9c.

| File | Role | Collaborators |
|---|---|---|
| `adapters/spy_sink.py` | supporting construct (pure module-level rendezvous) | `set_sink(callable)` / `clear_sink()` / `notify(text_chunks)`: the spy synth driver (instantiated by NVDA, not by our wiring) delivers captured text to whoever registered — `NvdaSpySpeechSource` in practice. Pure Python: unit-tested headlessly (`tests/unit/adapters/test_spy_sink.py`). |
| `adapters/nvda_adapter_factory.py` | adapter (implements AdapterFactory) | `build(mode)` → `AdapterSet`: speech source silent/live per mode, plus braille source, synth swapper, gesture sender below. |
| `adapters/nvda_spy_speech_source.py` | adapter (implements SpeechSource, silent mode) | `start(buffer)` registers with `spy_sink` (text → `buffer.append`) and with `synthDriverHandler.synthDoneSpeaking` (`synthDriverHandler.py:599`, filtered to the spy synth) to drive the buffer's exact-finish bookkeeping. `stop()` unregisters both; idempotent. |
| `adapters/nvda_live_speech_source.py` | adapter (implements SpeechSource, live mode) | `speech.extensions.pre_speechQueued.register` (`speech/extensions.py:55`; notified `speechSequence=`, `priority=` — `speech/manager.py:248`): extracts the text items of each sequence into the buffer (elapsed-time finish heuristic is already the buffer's). `stop()` unregisters. |
| `adapters/nvda_braille_source.py` | adapter (implements BrailleSource) | `braille.pre_writeCells.register` (`braille.py:2339`; notified `cells=`, `rawText=`, `currentCellCount=` — `braille.py:2928`): appends `rawText` to the braille buffer. `stop()` unregisters. |
| `adapters/nvda_synth_swapper.py` | adapter (implements SynthSwapper) | The **Decided** fail-safe design (RFC 0001; AGENTS gotcha): `current_synth()` = `synthDriverHandler.getSynth().name`; `swap_to_spy()` = `setSynth("nvdaMcpSpy")` **plus** `config["speech"]["synth"] = "nvdaMcpSpy"` (so `post_configProfileSwitch` reloads resolve to the spy, `synthDriverHandler.py:566-584`) **plus** a `config.pre_configSave` guard writing the real name into saves **plus** patching `synthDriverHandler.getSynthInstance` (`:474`); returns the real synth's name. `restore()` reverses all four, idempotent — safe unconditionally in the Session's `finally`. |
| `adapters/nvda_gesture_sender.py` | adapter (implements GestureSender) | `press(id)`: `KeyboardInputGesture.fromName(id)` (`keyboardHandler.py:702`; any raise → `GestureError`), then `inputCore.manager.emulateGesture` (`inputCore.py:705`) marshalled to the main thread via `wx.CallAfter`, the session thread blocking on a `threading.Event` with a timeout (timeout → `GestureError`). NVDA's own injected-key path waits on an injection-done event (`keyboardHandler.py:696-699`), so blocking semantics hold at the OS layer too. |
| `addon/synthDrivers/nvdaMcpSpy.py` | NVDA synth driver (the spy) | Modeled line-for-line on NVDA's `synthDrivers/silence.py` (SynthDriver subclass: `name`, `description`, `check() -> True`, `supportedSettings = frozenset()`, `_availableVoices`, `speak`, `cancel`): `speak(sequence)` extracts text items → `spy_sink.notify`, and notifies `synthDriverHandler.synthIndexReached` for each `IndexCommand` then `synthDoneSpeaking` (`synthDriverHandler.py:595,599`) so NVDA's speech manager keeps advancing — the determinism silent mode exists for. Imports the sink as `globalPlugins.nvdaMcpBridge.adapters.spy_sink` — legitimate: `addonHandler.Addon.addToPackagePath` extends both `globalPlugins` and `synthDrivers` with the addon's dirs (`addonHandler/__init__.py:718-736`). |
### Capabilities become honest

Entry 8 shipped `hello` advertising all six capabilities as a placeholder.
This entry narrows the bridge's announced set to what it actually serves —
`speech`, `braille`, `gestures` — since `focus`/`state`/`config` commands
answer `NotImplementedHandler` until session E (which widens the set again
when it lands the handlers). Small wire-visible change in
`build_command_registry` + test updates; the schema itself is unchanged (the
`Capability` enum keeps all six members).

### 9b acceptance criteria

`spy_sink` unit-tested (`tests/unit/adapters/test_spy_sink.py`); registry
capability-narrowing reflected in `test_hello`/`test_session`/`test_wiring`
and both integration scenarios; pyright ignore list extended by exactly the
new NVDA-edge files; all suites and the schema drift gate green (no schema
change expected); `plugin.py` untouched — installing this build changes no
NVDA behavior.

## 9c — wiring, panic gesture, packaging + the live checklist

### New files and classes

| File | Role | Collaborators |
|---|---|---|
| `plugin.py` (grows) | the NVDA edge | On init: builds `NvdaAdapterFactory`, `TcpListener` (loopback, `DEFAULT_PORT`), and `BridgeServer` with a session factory closing over `wiring.build_session` (nvda version from `buildVersion.version`; transcripts under `<configPath>/nvdaMcpBridge`); starts the server. `script_panic` (default gesture `kb:NVDA+control+shift+b`, reassignable via Input Gestures): `server.stop()` — which tears down any session and thereby restores the synth — then `ui.message` confirms. `terminate()`: `server.stop()`. |

Plus the packaging touches: buildVars/manifest so the scons build contains
`synthDrivers/nvdaMcpSpy.py` and the synced `protocol.py`.

Checklist findings that require adapter fixes ride this PR as amendments to
the (already merged) 9b files — small, visible deltas with a one-line why —
per the process rule; findings that need real iteration become 9.x board
entries.

### Manual live-NVDA checklist (copied into the 9c PR body)

1. Addon builds (`scons`), installs, NVDA restarts clean; bridge listening
   (verified by a probe `hello` from desktop Python).
2. Silent session end-to-end from a desktop Python client: hello (silent)
   swaps to the spy — NVDA goes quiet; `pressGesture` `kb:NVDA+f7` opens the
   elements list and its speech is captured with sane indexes;
   `waitForSpeechToFinish` returns promptly (exact-finish via
   `synthDoneSpeaking`); `bye` restores the previous synth and voice — NVDA
   talks again.
3. Fail-safe: kill the client process mid-session (no `bye`) — watchdog fires
   and the synth is restored. Switch config profiles during a silent session
   — the spy survives (`post_configProfileSwitch` defense). Save config
   during a silent session (NVDA+control+c) — the saved file names the real
   synth, not the spy.
4. Live session: hello (live) — real synth keeps talking while speech is
   captured; braille capture shows `rawText` (braille viewer suffices).
5. `hello` reports the real `reader.version` (matches About NVDA) and
   capabilities `speech`/`braille`/`gestures`.
6. Panic gesture during a silent session: session ends, synth restored,
   confirmation message spoken. NVDA shutdown during a session: clean exit,
   synth config intact on next start.
7. Sequential sessions: run checklist item 2 twice without touching NVDA.

### 9c acceptance criteria

All suites green (the automated surface of this PR is small by design); the
scons artifact contains `synthDrivers/nvdaMcpSpy.py` and the synced
`protocol.py`; every checklist box ticked — the `no unchecked checkboxes`
gate holds the PR until then.

## Out of scope

- The control dialog, config persistence, auto-start, and the named-pipe
  transport — entry 9.1 (its Listener seam and `ServerStatus` are built here
  precisely so 9.1 is GUI + config only).
- Remote TCP — deferred behind its own security entry (**Decided**,
  2026-07-18): the listener binds loopback only.
- `getFocusInfo` / `getState` / `getConfig` / `setConfig` handlers — session
  E, which also re-widens the advertised capabilities.
- Any server-side (lane 2) change.

## Definition of done

Three PRs, in order, each green: 9a (connection stack + scenarios), 9b (NVDA
adapters, addon still inert), 9c (wiring + packaging + completed checklist).
The 9c PR flips ROADMAP entry 9 to Done. Amendments forced by implementation
or the live checklist ride in the PR that hits them, with a one-line why;
checklist findings that need real iteration become 9.x board entries.
