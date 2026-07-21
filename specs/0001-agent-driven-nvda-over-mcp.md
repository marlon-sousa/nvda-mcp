# RFC 0001 — Agent-driven NVDA over MCP

MCP server that lets an AI agent **drive NVDA**: send keyboard gestures, read
back what NVDA speaks (and brailles), and introspect its state. These are
general-purpose primitives for agent-driven NVDA workflows; the **first use
case that motivates this spec is functional testing of NVDA add-ons** —
replacing manual functional testing — and the milestones below build toward it.
Later specs (`specs/NNNN-*.md`) cover further use cases and features.

## Constraints and decisions (agreed)

- Targets **live installed copies of NVDA**, not source checkouts. The test
  infrastructure therefore ships as an **addon**.
- **Minimum NVDA version: 2026.1** (`minimumNVDAVersion = 2026.1.0`,
  `lastTestedNVDAVersion = 2026.1.0`). 2026.1 is an addon API compat break
  point (`addonAPIVersion.BACK_COMPAT_TO = (2026, 1, 0)`), so nothing older
  could load the addon anyway. Reference source: `../nvda` (2026.1.0dev).
- Two speech-capture modes, chosen per session:
  - **silent** (default): a bundled spy synth driver replaces the real synth
    for the duration of the session. Deterministic, fast (no audio pacing),
    CI-friendly. Captures what would actually be heard.
  - **live**: hook `speech.extensions.pre_speechQueued`; the real synth keeps
    talking. Zero disruption to the tester. Captures what NVDA *intended* to
    say (including speech later canceled) — modes may legitimately differ.
- The addon is **inert while no session is active**: no synth swap, no hooks
  with side effects. Safe to leave permanently installed.
- MCP transport: **stdio** only, for now.

## Architecture

The chain, top to bottom — each item talks only to the next:

1. An MCP client (Claude Code, …) speaks MCP over stdio to the server.
2. The `nvda-mcp` server — a Python package on the official `mcp` SDK
   (FastMCP) — speaks JSON lines over TCP, 127.0.0.1 only, to the bridge.
3. The `nvda-mcp-bridge` — an NVDA addon (global plugin + spy synth driver) —
   drives NVDA itself.

Why split: the MCP server survives NVDA restarts (restarting NVDA is itself a
test operation), and NVDA's embedded Python is a poor host for an asyncio MCP
stdio server. Mirrors the architecture of NVDA's own system tests
(`../nvda/tests/system/libraries/SystemTestSpy/`) and the integrated remote
client (`../nvda/source/_remoteClient/`).

## Component 1: `bridgeAddon/` — the NVDA addon

Addon name `nvdaMcpBridge`, scaffolded from `C:\projects\AddonTemplate`
(sconstruct + buildVars.py + manifest.ini.tpl). Use the sconstruct variant
from `C:\projects\TimerForNVDA`, which additionally expands a root
`README.tpl.md` — `${addon_version}`, `${addon_name}`, `${addon_url}`, … are
substituted from `buildVars.py`'s `addon_info` at build time, producing
`README.md` and the addon's bundled HTML docs from a single source.

### `globalPlugins/nvdaMcpBridge/__init__.py`

- **Socket server**: JSON-lines over TCP, bound to `127.0.0.1`, default port
  8765 (configurable via addon config). Daemon thread, started at plugin init;
  accepting a connection is what starts a *session*.
- **Session lifecycle**:
  - Handshake (first message): `{"cmd": "hello", "mode": "silent"|"live",
    "protocolVersion": 1}`.
  - Single client at a time; reject concurrent connects.
  - A session spans a whole test scenario (many commands), e.g. navigate to
    an app, exercise it, read results — not a single keystroke. The agent
    opens/closes it explicitly via the MCP tools.
  - Teardown on: clean close, socket error, heartbeat timeout (no message for
    30 s — MCP server pings), **command-inactivity timeout** (no real command,
    pings excluded, for 2 min — configurable; guards against an agent that
    opened a session and forgot it), addon terminate, panic gesture. Teardown
    always restores the synth and unregisters all hooks (in `finally`).
- **Speech buffer**: indexed, append-only list guarded by an RLock — port of
  `NVDASpyLib` from `speechSpyGlobalPlugin.py`. Index-based access
  (`get since index`, `wait for text after index`, `reset`) is what makes
  speech assertions race-free.
- **Capture wiring**:
  - silent mode: save current synth name, then make NVDA *believe* the spy is
    the configured synth (set `config.conf["speech"]["synth"] = "nvdaMcpSpy"`)
    **and** load it — see the profile-switch guard below for why merely
    `setSynth("nvdaMcpSpy", isFallback=True)` is not enough. Buffer is fed by
    the spy synth's `post_speech` action; `synthDoneSpeaking` gives exact
    "speech finished" (no 1-second heuristic needed).
  - live mode: register `speech.extensions.pre_speechQueued` → buffer;
    "finished" falls back to the elapsed-time heuristic.
  - both modes: `braille.pre_writeCells` → braille buffer.
- **Input**: port `emulateKeyPress` from `speechSpyGlobalPlugin.py:518`
  verbatim — `KeyboardInputGesture.fromName(id)` +
  `inputCore.manager.emulateGesture(gesture)`, then block until processed
  (marker function through `queueHandler.eventQueue`, then wait for
  `watchdog.isCoreAsleep()`). This triggers addon scripts exactly like a real
  keypress and falls through to the OS when unbound.
- **Introspection**: focus / navigator object info via `api.getFocusObject()`
  (name, role, states, value, appModule name), config get/set (port of
  `set_configValue`).
- **State snapshot** (`getState`): queryable NVDA state that an agent asserts
  on but that is *not* carried by speech — because NVDA may answer with an
  earcon/beep instead of words (e.g. NVDA+space toggles browse/focus mode;
  `browseMode.reportPassThrough` plays `focusMode.wav`/`browseMode.wav` when
  `passThroughAudioIndication` is on, so there is nothing to match in the
  speech buffer). Returns:
  - `browseMode`: `"browse"` / `"focus"` / `null` — from the focus object's
    `treeInterceptor.passThrough` (`True` = focus mode), `null` when the focus
    has no browse-mode document.
  - `speechMode`: `"talk"` / `"beeps"` / `"off"` / `"onDemand"` — from
    `speech.getState().speechMode`.
  - `sleepMode`: focus `appModule.sleepMode`.
  - `inputHelp`: `inputCore.manager.isInputHelpActive`.
  Config-independent and unambiguous: `getState` → gesture → `getState` and
  diff. (Generalizing capture to audio cues — hooking `tones.beep` /
  `nvwave.playWaveFile` into an indexed buffer so beeps/earcons/custom addon
  sounds become assertable events — was considered and **deferred**; add it
  only if state snapshots prove insufficient.)

### `synthDrivers/nvdaMcpSpy.py`

Adapted from `../nvda/tests/system/libraries/SystemTestSpy/speechSpySynthDriver.py`
(GPL-2, same license the addon must carry). Swallows audio, honors
`IndexCommand` / `synthDoneSpeaking` notifications instantly, fires a local
`post_speech` extension point consumed by the global plugin. Addons may ship
`synthDrivers/` packages (`addonHandler.Addon.addToPackagePath`).

### Fail-safe synth restoration (silent mode) — non-negotiable

> **Superseded by [spec 0008](0008-transparent-silent-capture.md)
> (2026-07-21).** Silent mode no longer swaps the synth at all: it leaves the
> real synth loaded and intercepts speech at `filter_speechSequence`, so this
> whole fail-safe is moot (there is nothing to restore). The design below is
> kept for history; it was implemented in 9b, found fragile (a main-thread /
> server-thread `setSynth` race could leave the user mute) and non-transparent
> in 9c live testing, and replaced. Read spec 0008 for the current mechanism.

A crashed harness must never leave a blind tester with a mute screen reader:

1. Synth swap is session-scoped; restore in `finally` on every teardown path
   (disconnect, error, heartbeat timeout, plugin terminate).
2. **Profile-switch survival + config-persistence guard** (revised after
   reading 2026.1 source — the naive approach actively self-destructs):
   `synthDriverHandler.initialize()` registers `handlePostConfigProfileSwitch`
   on `config.post_configProfileSwitch` (`synthDriverHandler.py:420`). On every
   profile switch it compares `config.conf["speech"]["synth"]` against the
   loaded `_curSynth.name` and, if they differ, calls `setSynth(conf["synth"])`
   — tearing down whatever is loaded and reloading the config's synth
   (`synthDriverHandler.py:566-584`). Profile switches are frequent
   (app-specific profiles fire on focus change, say-all, manual toggles).
   Therefore `setSynth("nvdaMcpSpy", isFallback=True)` — which leaves
   `config["synth"]` = the real synth — makes `conf["synth"] != _curSynth.name`
   permanently true, so the *first* profile switch rips the spy out mid-session.
   The isFallback trick is the bug, not the guard. Instead, defend in three
   layers (silent mode only):
   1. **Make config agree**: set `config.conf["speech"]["synth"] = "nvdaMcpSpy"`
      for the session (what NVDA's own system tests do via a test profile), so
      the common-case reconciliation is a no-op, not a teardown.
   2. **Guard the save, not the write**: register `config.pre_configSave` to
      swap the real synth name back into config for the duration of the save,
      then restore `"nvdaMcpSpy"` — so the spy never persists to disk.
   3. **Defeat synth-changing profiles**: monkeypatch
      `synthDriverHandler.getSynthInstance` (`synthDriverHandler.py:474`) for
      the session so *any* synth NVDA loads returns the spy wrapper — capture
      then survives even a profile that stores a different synth, with no audio
      blip. (A self-registered `post_configProfileSwitch` handler that
      re-forces the spy is a lighter alternative if we prefer not to patch.)
   Teardown reverses all three in `finally` on every path: remove the
   `getSynthInstance` patch, unregister guards, restore
   `config["speech"]["synth"]` to the saved real name, `setSynth(realName)`.
3. Heartbeat: no client traffic for 30 s → assume harness death → restore.
4. **Panic gesture**: global plugin script (default e.g. NVDA+shift+escape,
   remappable) that force-restores the synth and drops the session, so
   recovery never depends on the harness.
5. **Command-inactivity timeout** (see session lifecycle): heartbeat proves
   the harness process is alive, not that the agent is still testing; if no
   real command arrives for the configured window, restore and close the
   session. A well-behaved agent simply reconnects.

### Session transcript log

The bridge writes a plain-text transcript per session so the tester can
follow what happened after the fact (essential in silent mode, where the
run is an audio blackout):

- One timestamped line per event, commands interleaved with captured speech:
  gestures sent, speech sequences (joined text), session open/close/teardown
  reason, mode, synth swap/restore.
- Written bridge-side so it is complete even if the agent never fetched some
  speech; flushed per line so a crash loses nothing.
- Location: `<addon config dir>\logs\session-<timestamp>.log`, keep last N
  sessions (configurable). The `hello` response returns the log path, and the
  MCP server surfaces it to the agent/user.

### Wire protocol (JSON lines)

Request `{"id": n, "cmd": str, "params": {...}}` →
`{"id": n, "result": ...}` or `{"id": n, "error": {"message": str}}`.

Commands (v1): `hello`, `ping`, `pressGesture`, `getSpeech` (since index),
`getLastSpeech`, `getNextSpeechIndex`, `waitForSpeech`,
`waitForSpeechToFinish`, `getBraille` (since index), `getFocusInfo`,
`getState`, `getConfig`, `setConfig`, `bye`.

## Component 2: `mcpServer/` — the MCP server

Python ≥ 3.11 package `nvda-mcp`, official `mcp` SDK, FastMCP, stdio
transport. Thin translator: MCP tool call → bridge command → result. Owns the
heartbeat ping while connected; reconnects on demand (e.g. after an NVDA
restart); closes the bridge session when its own stdio closes (MCP client
exited), so ending the conversation always restores speech.

MCP tools (v1):

| Tool | Notes |
|---|---|
| `nvda_connect(mode="silent", port=8765)` | opens session; returns NVDA version, current synth |
| `nvda_disconnect()` | restores synth, ends session |
| `nvda_send_keys(gestures: list[str])` | NVDA gesture ids, e.g. `"NVDA+f7"`, `"control+shift+downArrow"`; blocks until processed |
| `nvda_get_speech(since_index: int | None)` | joined text; also returns raw index range |
| `nvda_get_last_speech()` | |
| `nvda_reset_speech_index() -> int` | bookmark before an action |
| `nvda_wait_for_speech(text, after_index=None, timeout=5)` | |
| `nvda_wait_for_speech_to_finish(timeout=5)` | |
| `nvda_do(gestures: list[str]) -> str` | convenience: reset index → send keys → wait finish → return speech since index. The primary tool agents should use; makes wrong sequencing impossible |
| `nvda_get_braille()` | |
| `nvda_get_focus_info()` | |
| `nvda_get_state()` | queryable state NVDA may signal by sound not speech: `browseMode` (`"browse"`/`"focus"`/`null`), `speechMode`, `sleepMode`, `inputHelp`. Diff across a gesture to assert mode toggles |
| `nvda_set_config(key_path: list[str], value)` / `nvda_get_config(key_path)` | |

## Repository layout

```
nvda-mcp/
  specs/            # Numbered design specs (this file is 0001)
  shared/           # Canonical stdlib-only wire protocol (nvda-mcp-wire)
  bridgeAddon/      # NVDA addon, scaffolded from AddonTemplate:
                    #   sconstruct (TimerForNVDA variant), buildVars.py,
                    #   manifest.ini.tpl, README.tpl.md, addon/...
  mcpServer/        # Python package: pyproject.toml, src/nvda_mcp/
```

## Testing & typing strategy

**Type hints everywhere, enforced in CI (pyright).** Both halves use the same
hexagonal split, so the **pure domain is fully strict-checked and the
side-effecting edge is exempt**: the bridge's NVDA-importing adapters (and
`plugin.py`) — and, on the server, the MCP-SDK/socket adapters if needed — are
listed in pyright's `ignore`, so unresolved edge imports raise nothing. There
is **no NVDA source checkout and no vendored stubs** (the `../nvda` tree stays
a reference for reading real code). This is safe because the whole domain
type-checks as pure Python and the thin edge is validated by the milestone-6
live-NVDA integration tests. Optionally, a non-blocking CI job could later
type-check the edge against a real sparse `nvda/source` purely to flag drift.

**Shared protocol module is stdlib-only**: dataclasses plus one small
generic `from_dict` validator (walks `typing.get_type_hints`, clear errors
on missing/mistyped fields), so bridge and server share the same file
verbatim (the addon build copies it in) and it is unit-tested once.
Vendoring pydantic into the addon was **considered and rejected**: pydantic
v2's engine is a compiled Rust extension (`pydantic-core`) that would tie
the addon to NVDA's exact Python version/architecture, and NVDA addons
share one `sys.modules` — another addon importing a different pydantic
first would silently win. The server may still use pydantic internally
(FastMCP already does for tool arguments); only the shared wire module
must stay stdlib-only.

**Server tests** (pytest, no NVDA required):
- `protocol` — round-trips, malformed input, unknown commands.
- `bridge_client` against a **fake bridge**: an in-process asyncio TCP server
  speaking the real wire protocol with scripted responses/faults (delays,
  errors, mid-request disconnect). Covers id correlation, heartbeat cadence,
  timeouts, reconnect after NVDA restart, close-on-stdio-close. The fake
  bridge doubles as an executable spec; its scenarios can later be replayed
  against the real bridge as contract tests.
- MCP tool layer over the SDK's **in-memory client↔server streams** (no
  subprocess): full path MCP call → server → fake bridge. Pin the behaviors
  that would fail silently: `nvda_do` command ordering (reset → press →
  wait-finish → get), version-mismatch error clarity, index bookkeeping.

**Bridge tests — ports and adapters (hexagonal).** The addon is organized as
domain / ports / adapters / wiring (see AGENTS.md for the layout and rules):

- **`domain/`** is pure and NVDA-free, split by **role** so the path says what a
  file is: `controllers/` (the `Session` orchestrator — handed its ports, drives
  the entities), `entities/` (the indexed speech/braille buffers + wait logic),
  and `ports/` (the `abc.ABC` seams: message channel, speech source, synth
  swapper, gesture sender, clock, transcript, adapter factory). It is
  unit-tested headlessly under desktop Python 3.13 (matching NVDA 2026.1) with
  injected fakes (fake clock, scripted fake channel ⇒ assert restore ran on a
  dropped connection). Note "pure" ≠ "domain": JSON-lines framing is pure and
  still lives in an adapter, behind the `MessageChannel` port, so the
  controller's collaborators are *only* ports.
- **`adapters/`** is the only place NVDA is imported (`speech`,
  `synthDriverHandler`, `inputCore`, `config`, `api`, `braille`, …), one class
  per file. Adapters are **layered** so the untestable surface shrinks to a
  leaf: an adapter may depend on another only through a seam in
  `adapters/ports/` (`FileTranscript`→`FileWriter`→`TextFileWriter`;
  `JsonLinesChannel`→`Transport`→`SocketTransport`). The upper adapter holds
  every decision and is unit-tested against a fake seam; the leaf just calls the
  OS. The **synth swapper** owns not just swap/restore but the whole
  silent-mode defense — `config["speech"]["synth"]` agreement, the
  `config.pre_configSave` guard, and the `getSynthInstance` patch /
  profile-switch survival (see fail-safe restoration).
- **`wiring.py`** is the composition root that binds ports to adapters. Because
  the capture mode is only known after `hello`, it injects an **`AdapterFactory`
  port**; the `Session` reads `hello`, then asks the factory to build the
  mode-specific adapter set (no configure-after-construction). Transcript
  logging is part of the same wiring.

The state machine drives its combined restore on every teardown path; fakes
let us assert "after a simulated profile switch, the spy is still active and
restore still ran" without NVDA. The adapter classes themselves are
deliberately *not* unit-tested with NVDA mocks (false confidence); they are
covered by integration tests against a real NVDA launched with `-c <profile>`
(milestone 6, system-test pattern).

Tests accompany each milestone rather than arriving at the end.

## Milestones

1. **Bridge skeleton** — manifest (min 2026.1), global plugin, socket server,
   `hello`/`ping`/`getSpeech` in **live** mode only. Validate with a throwaway
   Python client against a real NVDA 2026.1: press keys by hand, read speech.
2. **Silent mode** — spy synth, session synth swap, all four restoration
   paths, panic gesture. Test every failure path deliberately (kill client,
   save config mid-session, restart NVDA).
3. **Input** — `pressGesture` with block-until-processed; verify an addon
   script fires and unbound keys reach the focused app.
4. **MCP server** — `nvda-mcp` package with the v1 tools; wire into Claude
   Code via stdio; first agent-driven smoke test (Notepad: type, arrow around,
   assert speech).
5. **Introspection** — focus info, braille, **state snapshot** (`getState`:
   browse/focus mode, speech mode, sleep, input help), config get/set.
6. **Real-world validation** — script an EnhancedFindDialog functional test
   end-to-end through the MCP; fix ergonomics that surface.
7. **Packaging & docs** — one GitHub release per tag carries **both
   artifacts**, built in lockstep by a GitHub Action:
   - the scons-built `.nvda-addon` (like the other addons);
   - the **CI-packaged server**: a PyInstaller **one-dir build shipped as a
     zip** (`nvda-mcp-server-<version>.zip`; no Python/uv prerequisite for
     users, and one-dir avoids the Defender/SmartScreen false positives that
     one-file exes attract), plus the wheel as a secondary artifact for
     pip/CI consumers. Dependencies are frozen from a committed `uv.lock`,
     so the shipped dependency tree is exactly what CI resolved — no
     install-time resolution on user machines (deliberately **no PyPI, no
     uvx** in the user-facing story).

   User setup: install the addon, download the zip, extract, then
   `claude mcp add nvda -- <extracted>\nvda-mcp-server.exe`. The **addon's
   bundled README carries the exact matching download URL and that command**:
   `README.tpl.md` expands
   `${addon_url}/releases/download/${addon_version}/nvda-mcp-server-${addon_version}.zip`
   at build time (the TimerForNVDA trick), so the help page installed with
   the addon — readable from NVDA's add-on store — always points at the
   server build that pairs with it. Alternatively (or additionally), ship a
   **separate agent-oriented setup file** in the addon (e.g.
   `mcp-setup.md`, generated from its own `.tpl.md` with the same
   variables): the README keeps a short human note, while the setup file
   holds the machine-actionable details — versioned download URL, exact
   `claude mcp add` command, ready-to-paste `.mcp.json` snippet — so an AI
   agent pointed at the installed addon can configure the MCP client itself.
   The `hello` `protocolVersion` check
   rejects mismatched bridge/server pairs with a self-explanatory error. The
   server never runs on NVDA's embedded Python — only the bridge does; they
   meet only at the TCP socket.

   Dev workflow (us) stays source-based:
   `claude mcp add --scope user nvda -- uv run --directory C:\projects\nvda-mcp\mcpServer nvda-mcp`
   (edits picked up next launch); optional committed `.mcp.json` in addon
   repos for per-project discovery.

   Known trade-off: unsigned PyInstaller one-file exes can trip
   Defender/SmartScreen false positives; fallbacks are one-dir-as-zip,
   reporting the false positive, code-signing later — and the wheel.
   Optional ergonomic: addon settings panel shows/copies the exact
   `claude mcp add` command for the matching version. README with agent
   usage guidance (incl. the `nvda_do` pattern and silent-mode safety
   notes).

## Risks / open points

- **Port conflict / multiple NVDA instances** (e.g. secure-desktop copy): bind
  failure → log and stay inert. Only one bridge active per machine for v1.
- **Background speech noise**: focus events from unrelated apps land in the
  buffer. Index bookmarks mitigate; document that tests should keep focus in
  the app under test.
- **Security**: loopback-only bind. The bridge can inject keystrokes — treat
  as a development tool. Optional shared-secret token (file in addon config
  dir, readable only by the same user) deferred until needed.
- **Typing literal text** (vs gestures) into apps: needs `SendInput` unicode
  injection; deferred, `pressGesture` per character covers early needs.
- **NVDA lifecycle tools** (`nvda_launch` with isolated profile, `nvda_quit`)
  deferred — v1 attaches to the running NVDA.
