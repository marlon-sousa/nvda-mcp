# Spec 0011 — bridge: control UI + connection config (entry 9.1b)

Implementation contract for ROADMAP lane 1, entry 9.1b (split off entry 9.1,
agreed 2026-07-21). Authored on the entry's branch per process; the spec rides
in the implementing PR.

## Goal

After 9.1a the named pipe is the hardcoded default and `plugin.py` builds a
`NamedPipeListener` unconditionally. A user who wants loopback TCP instead has
no way to choose it — and no UI at all to see whether the bridge is running,
start or stop it, or have it auto-start on NVDA load.

This entry delivers three things that together give the user control:

1. **A bridge dialog** — NVDA menu → Tools → "NVDA MCP Bridge…" — showing the
   current status (stopped / listening / session active) with the connection
   mode and endpoint, a connection-mode combo (named pipe / loopback TCP /
   remote TCP greyed out), Start and Stop buttons, and an auto-start checkbox.
2. **Config persistence** — the connection mode and auto-start preference are
   saved to a plain `config.ini` file under the NVDA user config directory,
   independent of NVDA's profile-switching `config.conf` (see Decided).
3. **Config-driven listener choice** — `plugin.py` reads the persisted mode on
   load and builds the matching `Listener` (named pipe or loopback TCP), and
   auto-starts only when the user has asked for it.

The pipe is already the default (9.1a); this entry lets a user *override* it
back to loopback TCP and control the server's lifecycle without reloading the
addon or editing code.

## Decided

- **One dialog, not a settings panel.** NVDA settings panels (multi-page
  Preferences) are for static configuration consumed at next load. This dialog
  controls a *running* server — Start and Stop are immediate actions, and the
  status indicator is live — so a standalone dialog reached from the Tools menu
  is the right surface. The two persisted values (mode and auto-start) ride in
  the same dialog because they belong with the thing they control; splitting them
  into a separate Preferences panel would scatter the bridge's controls across
  two places for no user benefit.
- **Profile-independent config: a plain `config.ini`, not NVDA's
  `config.conf`.** NVDA's `config.conf` is profile-aware — switching profiles
  resets it to the active profile's values. The bridge's connection mode and
  auto-start preference are machine-wide settings; they should survive a profile
  switch unchanged. A plain `configparser`-backed `.ini` file under
  `<configPath>\nvdaMcpBridge\config\config.ini` — sibling to the logs directory
  the bridge already owns — achieves profile independence with stdlib only and
  no NVDA config-spec registration.
- **Connection mode is an enum, not a free-form string.** `ConnectionMode` is a
  `StrEnum` in the domain (pure, testable), with two active members —
  `NAMED_PIPE` and `LOOPBACK_TCP` — plus `REMOTE_TCP` defined but unreachable
  from the UI (the combo shows it greyed out). This gives the deferred security
  entry a natural place to land without a data migration.
- **The dialog lives in `views/`, not `adapters/`.** It is not an adapter — it
  does not implement any domain port. It is a **driving actor** that consumes
  ports (the `BridgeConfig` port for persistence, plus `BridgeServer` directly
  for lifecycle) the same way a domain controller does. It lives at the package
  root, sibling to `domain/` and `adapters/`, because its dependency surface is
  the full NVDA GUI stack (wx, `gui`, `logHandler`) — outside the domain
  boundary but not behind a seam either. `plugin.py` activates it by
  constructing it with real dependencies and showing it from the menu.
- **Port injection, not global imports.** `BridgeDialog.__init__` receives a
  `BridgeConfig` port and a `BridgeServer` instance — `plugin.py` is the
  composition root that wires the real ones. This keeps the dialog testable
  against a `FakeBridgeConfig` and decoupled from where the config file lives.
- **Status polling via `wx.Timer`.** The dialog polls `BridgeServer.status`
  every 500 ms so the status line reflects state changes (e.g. a client
  connecting moves `LISTENING → SESSION_ACTIVE`). The timer starts when the
  dialog opens and stops when it closes; no background thread.
- **Start is a retry path.** If the initial `server.start()` in `plugin.py`
  failed (e.g. pipe name collision), the dialog shows `STOPPED` and the Start
  button lets the user try again — same `start()` call, same bind-failure
  surface (error logged; dialog stays open, status stays `STOPPED`).
- **All user-visible strings go through `_()` with translator comments.**
  Every label, button, combo entry, status text, and message shown to the user
  is wrapped in NVDA's `_()` translation function and preceded by a
  `# Translators:` comment on its own line, following the pattern already used
  in `plugin.py` (the panic gesture's description and confirmation message).
  The `scriptCategory` is already translated; the menu item and every string in
  the dialog follow the same convention. No bare English strings in the UI.
- **No new wire command or protocol change.** This is purely local UI + config;
  the bridge's wire surface is unchanged.

## Deliverables

All under `bridgeAddon/` unless noted. Every module carries the mandatory ROLE
header.

### 1. `domain/entities/connection_mode.py` — the pure enum

**Role:** entity. A `StrEnum` the domain, views, and adapters all import (it
lives in `domain/` so it stays pure; `protocol.py` does NOT need it — the wire
does not know about transports).

```python
class ConnectionMode(StrEnum):
    NAMED_PIPE = "namedPipe"
    LOOPBACK_TCP = "loopbackTcp"
    REMOTE_TCP = "remoteTcp"  # defined but unreachable from the UI until its security entry lands

DEFAULT: Final = ConnectionMode.NAMED_PIPE
```

Unit-tested in `tests/unit/domain/entities/test_connection_mode.py`: asserts the
three members, that `DEFAULT` is `NAMED_PIPE`, and that the string values match.

### 2. `domain/ports/bridge_config.py` — the persistence port

**Role:** port (`abc.ABC`). The contract the dialog (and `plugin.py`) read/write
persisted preferences through — without knowing they're an `.ini` file.

```python
class BridgeConfig(ABC):

    @abstractmethod
    def get_connection_mode(self) -> ConnectionMode: ...
    @abstractmethod
    def set_connection_mode(self, mode: ConnectionMode) -> None: ...

    @abstractmethod
    def get_auto_start(self) -> bool: ...
    @abstractmethod
    def set_auto_start(self, value: bool) -> None: ...
```

No signalling types needed — the four methods are the whole contract. Methods
that read return sensible defaults (`DEFAULT`, `True`) when no file exists yet;
methods that write create the directory and file on first save.

### 3. `adapters/ini_bridge_config.py` — the `.ini` adapter

**Role:** adapter (implements `BridgeConfig`). Uses stdlib `configparser` to
read/write `<configPath>\nvdaMcpBridge\config\config.ini`. Imports
`globalVars` from NVDA for the config path — on pyright's ignore list.

```python
class IniBridgeConfig(BridgeConfig):
    """Bridge preferences backed by a profile-independent config.ini."""

    def __init__(self, config_dir: str) -> None: ...
```

File layout on disk:

```
<configPath>\nvdaMcpBridge\
  config\
    config.ini        # [nvdaMcpBridge] section; two keys
  session-*.log       # transcripts (existing, spec 0003)
  nvda-log-*.log      # NVDA log captures (existing, spec 0009)
```

`config.ini` format:

```ini
[nvdaMcpBridge]
connectionMode = namedPipe
autoStart = true
```

`get_connection_mode()` validates the read value against `ConnectionMode`
members; an unrecognised value logs a warning via `logHandler.log` and returns
`DEFAULT`. Reads return defaults when the file or section is absent (first run).
Writes create parent directories if needed (`os.makedirs`).

No unit test file (deliberate — it makes no decisions beyond what `configparser`
already guarantees; covered by the live-NVDA checklist). The port's ABC and
pyright strict check ensure the signature matches.

### 4. `tests/fakes/bridge_config.py` — the fake

**Role:** fake (subclasses `BridgeConfig`). An in-memory `dict` backend: `{mode:
ConnectionMode, auto_start: bool}`, initialised with defaults. Used by any test
that constructs a `BridgeDialog` (if we add headless dialog tests later) and by
tests that exercise `plugin.py`'s config-driven listener choice.

```python
class FakeBridgeConfig(BridgeConfig):
    def __init__(self, *, mode: ConnectionMode = DEFAULT, auto_start: bool = True) -> None: ...
```

Mirrors the one-class-per-file rule: `tests/fakes/bridge_config.py` ↔
`domain/ports/bridge_config.py`.

### 5. `views/__init__.py` — package doc

**Role:** documentation. Carries a module-level docstring explaining what
`views/` is:

```
"""Driving actors that consume ports and adapter-layer objects.

Views live outside the domain (they import wx, NVDA's GUI, and other
NVDA-edge modules) but are NOT adapters — they do not implement any
domain port. They receive their dependencies through constructor
injection, the same pattern as domain controllers, and are activated
by the composition root (plugin.py).
"""
```

No re-exports.

### 6. `views/bridge_dialog.py` — the wx dialog

**Role:** driving actor (view). A `wx.Dialog` subclass. Imports wx, NVDA `gui`,
`logHandler.log`, and `BridgeServer` from the adapter layer — on pyright's
ignore list. Receives a `BridgeConfig` port and a `BridgeServer` via constructor
injection.

```python
def build_listener(mode: ConnectionMode) -> Listener:
    """The single mode→Listener factory. Pure: neither NamedPipeListener
    nor TcpListener imports NVDA. Lives here so the view owns the mapping;
    imported by plugin.py for the initial construction on load."""
    ...

class BridgeDialog(wx.Dialog):
    """NVDA Tools → NVDA MCP Bridge… dialog.
    Title set via _("NVDA MCP Bridge") in __init__,
    with the # Translators: comment for the dialog title.
    """

    def __init__(
        self,
        parent: wx.Window,
        server: BridgeServer,
        config: BridgeConfig,
    ) -> None: ...
```

**Layout** (top to bottom, single column, all controls keyboard-reachable):

1. **Status group** (static box):
   - # Translators: Label for the bridge status section in the NVDA MCP Bridge dialog.
   - Static box label: `_("Bridge status")`
   - Status label: shows state **and** connection mode explicitly, composed by
     a small pure helper `_status_text(state, mode, endpoint) -> str` that
     returns translatable strings (each wrapped in `_()` with its own
     `# Translators:` comment). Examples of the composed output:
     - # Translators: Shown in the bridge dialog when the server is stopped.
       `_("Stopped")`
     - # Translators: Shown in the bridge dialog when listening on the named pipe. {endpoint} is the pipe name.
       `_("Listening — Named pipe ({endpoint})").format(endpoint=...)`
     - # Translators: Shown in the bridge dialog when listening on loopback TCP. {endpoint} is the host:port.
       `_("Listening — Loopback TCP ({endpoint})").format(endpoint=...)`
     - # Translators: Shown in the bridge dialog when a session is active on the named pipe. {endpoint} is the pipe name.
       `_("Session active — Named pipe ({endpoint})").format(endpoint=...)`
     - # Translators: Shown in the bridge dialog when a session is active on loopback TCP. {endpoint} is the host:port.
       `_("Session active — Loopback TCP ({endpoint})").format(endpoint=...)`
   - A `wx.Timer` (500 ms) polls `self._server.status` and refreshes this label
     and the Start/Stop button enabled state.

2. **Connection mode** (static box):
   - # Translators: Label for the connection mode section in the NVDA MCP Bridge dialog.
   - Static box label: `_("Connection")`
   - # Translators: Label above the connection mode combo box.
   - Combo label: `_("Accept connections via:")`
   - A `wx.Choice` (combo box) with three entries:
     - # Translators: Connection mode option: local named pipe.
       `_("Local: named pipe (recommended)")` → `NAMED_PIPE`
     - # Translators: Connection mode option: local loopback TCP.
       `_("Local: loopback TCP")` → `LOOPBACK_TCP`
     - # Translators: Connection mode option: remote TCP (currently unavailable).
       `_("Remote: TCP/IP")` → `REMOTE_TCP`, **disabled** (`Enable(False)`)

3. **Auto-start** (checkbox):
   - # Translators: Checkbox in the bridge dialog to start the bridge automatically when NVDA loads.
   - `_("Start bridge automatically when NVDA loads")` — persisted immediately
     on toggle via `self._config.set_auto_start(value)` (no OK/Apply needed;
     it is a standalone preference).

4. **Button row** (horizontal, right-aligned):
   - **Start** — # Translators: Button in the bridge dialog to start the server.
     `_("&Start")` — enabled only when state is `STOPPED`. Calls
     `plugin.rebuild_server(mode)` (see item 8) — the dialog does NOT own the
     server rebuild; the composition root does.
   - **Stop** — # Translators: Button in the bridge dialog to stop the server.
     `_("St&op")` — enabled when state is not `STOPPED`. Calls
     `self._server.stop()`.
   - **Close** — # Translators: Button in the bridge dialog to close the dialog.
     `_("&Close")` — closes the dialog. Does NOT stop the server.

The dialog is **modal** (consistent with NVDA's own Tools-menu dialogs like the
Log Viewer). `BridgeServer.stop()` blocks until the server thread joins, so
pressing Stop may pause the UI briefly; the timer keeps the status label live.

**Mode-switch on Start, not on combo change.** The combo records the user's
*preference*; the actual listener rebuild and server restart happen only when
Start is pressed. This avoids tearing down a running session because the user
browsed the combo. If the server is running and the user picks a different mode
then presses Start, the dialog calls `plugin.rebuild_server(new_mode)`, which
stops the current server, persists the mode, builds a new listener, creates a
new `BridgeServer`, and starts it.

### 7. `build_listener()` — the shared factory

A module-level function in `views/bridge_dialog.py` (imported by `plugin.py`):

```python
def build_listener(mode: ConnectionMode) -> Listener:
    if mode is ConnectionMode.NAMED_PIPE:
        return NamedPipeListener(protocol.DEFAULT_PIPE_NAME)
    if mode is ConnectionMode.LOOPBACK_TCP:
        return TcpListener("127.0.0.1", protocol.DEFAULT_PORT)
    raise ValueError(f"Unsupported connection mode: {mode}")
```

Pure — neither leaf constructor imports NVDA. Lives in `views/` because the
view owns the mode→transport mapping conceptually; `plugin.py` imports it for
the initial load path. Single source of truth.

### 8. `plugin.py` changes

The plugin's `__init__` currently builds a hardcoded `NamedPipeListener`. After
this entry it reads persisted config and injects dependencies into the view:

```python
def __init__(self) -> None:
    super().__init__()
    config_dir = os.path.join(_bridge_logs_dir(), "config")
    self._config = IniBridgeConfig(config_dir)
    self._server = BridgeServer(
        build_listener(self._config.get_connection_mode()),
        _make_session_factory(...),
    )
    self._register_tools_menu_item()   # guarded, removed in terminate()
    if self._config.get_auto_start():
        try:
            self._server.start()
        except Exception:
            log.error(...)

def rebuild_server(self, mode: ConnectionMode) -> None:
    """Stop the current server (if running), persist the new mode,
    build a fresh BridgeServer with the matching listener, and start it.
    Called by BridgeDialog when the user changes mode and presses Start."""
    self._server.stop()
    self._config.set_connection_mode(mode)
    new_listener = build_listener(mode)
    self._server = BridgeServer(new_listener, _make_session_factory(...))
    self._server.start()

def _show_bridge_dialog(self) -> None:
    """Open the bridge control dialog, injecting real dependencies."""
    dlg = BridgeDialog(gui.mainFrame, self._server, self._config)
    dlg.ShowModal()
    dlg.Destroy()
```

Key points:
- `rebuild_server(mode)` is a public method the dialog calls — it is the one
  place that orchestrates a mode switch, so the dialog never touches
  `BridgeServer` construction directly.
- `_show_bridge_dialog()` constructs the dialog with the real `BridgeServer`
  and `IniBridgeConfig` — it is the composition root for the view.
- The menu item calls `_show_bridge_dialog()`.
- `script_panic` and `terminate()` are unchanged (they already call
  `self._server.stop()`).

### 9. Menu registration

A menu item is added to NVDA's Tools menu
(`gui.mainFrame.sysTrayIcon.toolsMenu`), following the `_remoteClient/menu.py`
pattern:

- # Translators: Menu item in NVDA's Tools menu to open the NVDA MCP Bridge dialog.
- Label: `_("NVDA MCP &Bridge…")`
- Registered in `plugin.py`'s `__init__` via a private
  `_register_tools_menu_item()` method, guarded so reloads don't double-add.
- Bound to `_show_bridge_dialog`.
- Removed in `terminate()`.

### 10. Test updates

| File | What changes |
|---|---|
| `tests/unit/domain/entities/test_connection_mode.py` | New: asserts members, `DEFAULT`, string values. |
| `tests/fakes/bridge_config.py` | New: in-memory `FakeBridgeConfig`, mirroring the port. |
| `tests/unit/adapters/test_bridge_server.py` | Unchanged (BridgeServer already takes any Listener). |
| `tests/integration/test_named_pipe_session_roundtrip.py` | Unchanged. |
| `tests/integration/test_socket_session_roundtrip.py` | Unchanged. |

No new integration scenario: the dialog is GUI-only and proven by the live-NVDA
checklist; `IniBridgeConfig` is a leaf with no decisions to unit-test. The
`FakeBridgeConfig` enables future headless dialog tests if we ever add them, and
it earns its keep now by keeping the fake set complete (every port has a fake).

### 11. Packaging

No new files to add to `buildVars.pythonSources` — the recursive `**/*.py` glob
already covers the new `views/`, `domain/entities/`, `domain/ports/`, and
`adapters/` files. No new dependencies; `configparser` is stdlib; wx comes from
NVDA's runtime.

## Class/file layout summary

| File | Role | Collaborators |
|---|---|---|
| `domain/entities/connection_mode.py` | entity | `ConnectionMode(StrEnum)` + `DEFAULT`. Pure, no collaborators. |
| `domain/ports/bridge_config.py` | port (`abc.ABC`) | `BridgeConfig`: four abstract methods for mode + auto-start persistence. No signalling types. |
| `adapters/ini_bridge_config.py` | adapter (implements `BridgeConfig`) | `IniBridgeConfig`: `configparser`-backed, reads/writes `<configPath>\nvdaMcpBridge\config\config.ini`. Imports `globalVars` (NVDA edge). |
| `views/__init__.py` | documentation | Package docstring explaining the `views/` role. |
| `views/bridge_dialog.py` | driving actor (view) | `BridgeDialog(wx.Dialog)`: receives `BridgeConfig` + `BridgeServer` via constructor. Also exports `build_listener(mode)` — the single mode→Listener factory, imported by `plugin.py`. |
| `tests/fakes/bridge_config.py` | fake (subclasses `BridgeConfig`) | `FakeBridgeConfig`: in-memory dict backend with defaults. |
| `tests/unit/domain/entities/test_connection_mode.py` | unit test (new) | Tests the enum members, `DEFAULT`, and string values. |
| `plugin.py` (modified) | the NVDA edge (already exists) | Grows: constructs `IniBridgeConfig`, uses `build_listener` for initial listener choice, respects `auto_start`, registers the Tools menu item, exposes `rebuild_server()` and `_show_bridge_dialog()`. |

## Acceptance criteria

Automated (CI, `bridge` job):

1. `test_connection_mode.py` green; pyright strict clean on the domain (the new
   entity + port).
2. All existing bridge suites green — the new code paths in `plugin.py` are
   exercised by the existing headless integration scenarios (the session
   round-trip tests still pass regardless of which Listener is built).
3. The `no unchecked checkboxes` gate stays green (the live-NVDA checklist below
   is in the PR body).

Manual live-NVDA checklist (this PR's body, per AGENTS.md):

1. **Dialog opens:** NVDA → Tools → "NVDA MCP Bridge…" opens the dialog. Status
   shows "Listening — Named pipe (\\.\pipe\nvdaMcpBridge)" (pipe is the default;
   auto-start is on, so the server is already running).
2. **Status live:** connect a client — status changes to "Session active — Named
   pipe (\\.\pipe\nvdaMcpBridge)". Disconnect — returns to "Listening — …".
3. **Stop:** press Stop — status shows "Stopped"; a client cannot connect. Press
   Start — status returns to "Listening — …"; a client connects again.
4. **Mode switch:** change combo to "Local: loopback TCP", press Start — status
   shows "Listening — Loopback TCP (127.0.0.1:8765)"; a TCP client connects.
   Switch back to named pipe, press Start — pipe client connects again.
5. **Auto-start off:** uncheck auto-start, close dialog, restart NVDA — the
   bridge is stopped (status "Stopped"). Re-enable and restart — listening again.
6. **Remote TCP greyed out:** the third combo entry is visible but disabled.
7. **Panic gesture still works:** `NVDA+control+shift+b` stops the server; the
   dialog's status updates to "Stopped" (the timer is still running).
8. **Mode persists:** set loopback TCP, close dialog, reopen — combo shows
   loopback TCP. Restart NVDA — the bridge listens on TCP.
9. **Profile independence:** switch NVDA config profiles while the bridge is
   listening — the connection mode and auto-start preference are unchanged (the
   bridge does not restart or flip modes). The `config.ini` file is untouched by
   profile switches.
10. **First run:** delete `config.ini`, restart NVDA — the bridge listens on the
    named pipe (defaults) and a fresh `config.ini` is written.

## Out of scope

- Remote TCP — deferred behind its own security entry (ROADMAP 9.1b note).
  `ConnectionMode.REMOTE_TCP` exists in the enum so the deferred entry has a
  place to land without a data migration, and the combo's third row is the
  placeholder for it.
- A settings panel in NVDA Preferences — **Decided** above: this is a live
  control dialog, not a static settings page.
- Server-level access control, authentication tokens, remote security model —
  the remote-TCP entry's job.
- Lane 2 (`BridgeClient`) learning to dial a named pipe — a small follow-up once
  entry 10 exists (already noted on the ROADMAP).
- Any wire protocol or schema change.

## Definition of done

Merged with green CI; ROADMAP entry 9.1b flipped to Done by this PR; the manual
checklist above completed in the PR body.
