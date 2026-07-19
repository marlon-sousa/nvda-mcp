# nvda-mcp wire protocol — v1

The published contract between an **MCP server** and a **screen-reader bridge**.
This is the human half of the contract; [`schema.json`](schema.json) beside it is
the machine half, generated from the reference Python implementation
(`shared/nvda_mcp_wire/protocol.py`) so shapes and prose cannot disagree.

A bridge author in any language implements this document plus the schema. The
NVDA bridge (`bridgeAddon/`) is the reference implementation; JAWS and TalkBack
bridges are anticipated (see
[spec 0005](../../0005-multi-reader-direction.md)) and would speak this same
contract with reader-specific values.

`protocolVersion` for this document is **1**. It is a pre-release version with no
external consumers yet, so it may still be amended in place; once a non-Python
bridge depends on it, changes go through a version bump.

## 1. Transport and framing

- The bridge **listens**; the server **dials**. The connection is a TCP socket
  bound to loopback (`127.0.0.1`) only — never a routable interface. (An Android
  TalkBack bridge is the anticipated exception, reached over an `adb`-forwarded
  or Wi-Fi socket; it is still the listener.)
- Default port: **8765** (`DEFAULT_PORT`).
- Framing is **JSON Lines**: each message is one JSON **object**, UTF-8 encoded,
  serialized without embedded newlines, terminated by a single `\n`. A reader
  reassembles chunks into newline-delimited frames and must drain any complete
  buffered lines before polling the socket again, so a message that already
  arrived is never lost to a later idle timeout.
- One object per line. A line that is not a JSON object (a JSON array, scalar,
  or malformed text) is a protocol fault — see §2.

## 2. Envelope

Two frame types cross the wire.

A **request** (server → bridge):

- `id` (int, required) — correlation id chosen by the server; the matching
  response echoes it.
- `cmd` (string, required) — the command name (§5). An unknown name is **not** a
  framing fault: the bridge replies with an error response and the session
  continues.
- `params` (object, optional) — command parameters; defaults to `{}`.

A **response** (bridge → server):

- `id` (int, required) — the request's id.
- Exactly **one** of:
  - `result` — the command's result payload (shape per §5), or
  - `error` — an object `{ "message": string }`.

Fault handling, all of which keep the session alive once established (§3):

- Unknown `cmd` → error response.
- A malformed line, a non-object line, or params that fail validation → error
  response (the reference implementation raises `ValidationError`, reported as an
  error message).
- Extra, unrecognized object fields are **ignored**, so a newer peer may add
  fields without breaking an older one.

## 3. Handshake and session lifecycle

1. The server sends `hello` **first**. It is the only command accepted before the
   handshake completes; any other command pre-handshake ends the connection.
2. `hello` params carry the server's `protocolVersion` and the requested capture
   `mode` (§4). The bridge requires `protocolVersion` to **equal** its own; a
   mismatch fails the handshake with an error response and the session ends.
3. On success the bridge replies with `HelloResult`:
   - `protocolVersion` (int) — the bridge's version.
   - `reader` (object `{ name, version }`) — **which** screen reader answered
     (§6). The NVDA bridge sends `name = "nvda"`.
   - `capabilities` (array of strings) — what this bridge supports (§4).
   - `mode` — the capture mode now in effect.
   - `synth` — the name of the reader's current speech synthesizer.
   - `logPath` — absolute path to this session's human-readable transcript.
4. After a successful handshake the session is **tolerant**: a failing command
   yields an error response and the session keeps running. Only the conditions in
   §6 (teardown) end it.

## 4. Capture modes and capabilities

**Capture mode** is chosen once, at `hello`, and fixes how speech is captured for
the whole session:

- `silent` — a bundled spy synthesizer replaces the reader's real synth for the
  session; speech is captured deterministically and the user hears nothing. The
  bridge **must** restore the real synth on every teardown path (§6).
- `live` — the real synth keeps speaking; speech is captured by observation.
  Ordering/timing is best-effort rather than exact.

**Capabilities** announce which command groups this bridge can serve. Each value
names one group:

| Capability | Commands it covers |
|---|---|
| `speech` | `getSpeech`, `getLastSpeech`, `getNextSpeechIndex`, `waitForSpeech`, `waitForSpeechToFinish` |
| `braille` | `getBraille` |
| `gestures` | `pressGesture` |
| `focus` | `getFocusInfo` |
| `state` | `getState` |
| `config` | `getConfig`, `setConfig` |

Rules:

- A consumer **must ignore an unknown capability string**, so the set can grow
  without breaking older peers. (This is the one forward-compatibility carve-out
  beyond "ignore unknown fields".)
- A command whose group is **not** in the announced set may be rejected with a
  normal error response. The NVDA bridge announces all six.
- `hello`, `ping`, `echo`, and `bye` are lifecycle/diagnostic commands and belong
  to no capability group; they are always available once the session permits them
  (§3).

## 5. Commands

Every command's `params` and `result` shapes are defined in
[`schema.json`](schema.json) under `commands.<name>`. A `null` `params` there
means the command takes no parameters. Summary:

- `hello` — handshake (§3).
- `ping` → `{ ok: true }` — liveness only; see §6.
- `echo` `{ payload }` → `{ payload }` — returns the payload unchanged, for any
  JSON value; a whole-stack round-trip check.
- `pressGesture` `{ gestures: [string] }` → `{ ok: true }` — press the given
  reader gesture ids in order, blocking until each is processed. Gesture id
  syntax is **reader-specific** and passes through opaquely (NVDA example:
  `"kb:NVDA+f7"`).
- `getSpeech` `{ sinceIndex }` → `{ text, fromIndex, toIndex }` — captured speech
  since an index (§7).
- `getLastSpeech` → `{ text, index }`.
- `getNextSpeechIndex` → `{ index }` — the index the next captured speech will
  occupy.
- `waitForSpeech` `{ text, afterIndex?, timeout? }` → `{ found, index, text }`.
- `waitForSpeechToFinish` `{ timeout? }` → `{ finished }`.
- `getBraille` `{ sinceIndex }` → `{ text, fromIndex, toIndex }`.
- `getFocusInfo` → `{ name, role, states, value, appModule }` — the focus
  object. `role`/`states` strings are reader-specific and pass through opaquely.
- `getState` → `{ browseMode, speechMode, sleepMode, inputHelp }` — queryable
  state that a reader may signal by sound rather than words; diff two snapshots
  across a gesture to assert a toggle. Values are reader-specific.
- `getConfig` `{ keyPath: [string] }` → `{ value }` — read a reader config value;
  `keyPath` is an opaque path into the reader's config tree.
- `setConfig` `{ keyPath: [string], value }` → `{ value }` — write one.
- `bye` → `{ ok: true }` — the server asks to end the session (§6).

Reader-specific vocabulary — gesture ids, roles, states, config key paths, state
values — is **opaque payload**: the server routes it without interpreting it, and
only the agent (which knows the reader) and the bridge understand it.

## 6. Liveness and teardown

The bridge runs two independent watchdogs while a session is established:

- **Heartbeat** — proves the server process is alive. Any message resets it,
  including `ping`.
- **Command inactivity** — proves the agent is still working. Only a real command
  resets it; `ping` deliberately does **not**, so a keepalive cannot mask an
  abandoned session.

A session ends on any of: `bye`, the peer closing the connection (EOF), either
watchdog firing, or an out-of-order pre-handshake command (§3).

On **every** teardown path the bridge must run its restoration: in `silent` mode
that means putting the user's real synthesizer back. A crashed or disconnected
server must never leave the reader mute — this is the contract's single most
important invariant.

## 7. Index semantics

Captured speech and braille each form an append-only log with **monotonically
increasing integer indices**.

- Ranges are **half-open**: `getSpeech`/`getBraille` return
  `[fromIndex, toIndex)`, i.e. `fromIndex` inclusive, `toIndex` exclusive, so
  `toIndex` is exactly the `sinceIndex` to pass next with no overlap or gap.
- `getNextSpeechIndex` returns the index the next captured item will take, so a
  test can note "now", act, then read only what its action produced.
- `waitForSpeech` blocks until a matching item appears or `timeout` seconds
  elapse; `found` says which. `afterIndex` restricts the match to items at or
  after that index.
- `waitForSpeechToFinish` blocks until speech settles or `timeout` elapses.
- All timeouts are in **seconds** (number; defaults live in `schema.json`).

## 8. Versioning policy

- Compatibility is decided by **exact `protocolVersion` equality** at `hello`
  (§3). There is no negotiation yet.
- Two forward-compatibility rules soften that: unknown **object fields** are
  ignored (§2), and unknown **capability strings** are ignored (§4).
- `protocolVersion` 1 is pre-release: it may be amended in place until an external
  (non-Python) bridge depends on it. After that, an incompatible change bumps the
  version and ships a new `specs/wire/vN/` directory.
