# NVDA MCP Bridge 0.1.0

An NVDA add-on that lets an AI agent **drive NVDA**: send keyboard gestures, read back what NVDA speaks and brailles, make NVDA announce something, and follow along with its log.

The first use case is **functional testing of NVDA add-ons** — replacing the manual "install it, press the keys, listen to what it says" loop — but the same primitives support a wider range of agent-driven NVDA workflows.

* speech capture, in a silent or a live variant
* braille capture
* keyboard gesture injection
* announcements through NVDA's own speech
* per-session NVDA log capture at a requested verbosity
* named pipe or loopback TCP, chosen from a dialog in NVDA's Tools menu
* a panic gesture that stops everything and gives you your speech back

- Minimum NVDA version: 2026.1.0
- Last tested NVDA version: 2026.1.0
- Source and issues: https://github.com/marlon-sousa/screen-readers-mcp

## Download

Download the [NVDA MCP Bridge 0.1.0 addon](https://github.com/marlon-sousa/screen-readers-mcp/releases/download/nvda-bridge-v0.1.0/nvdaMcpBridge-0.1.0.nvda-addon)

## This add-on is only half of the system

The add-on does not talk to your AI agent directly. It listens on a local endpoint and speaks a small JSON-lines protocol. The other half — the **nvda-mcp server** — is a separate program that your agent's MCP client launches. The server connects to this add-on and re-exposes NVDA to the agent as MCP tools.

The chain, top to bottom — each link talks only to the next:

1. Your AI agent speaks MCP over stdio to the server.
2. The `nvda-mcp` server speaks JSON lines over a local endpoint to this add-on.
3. This add-on drives NVDA itself.

The two halves share one versioned wire contract. What has to match is the **protocol version**, not the version numbers of the two programs: the `hello` handshake compares protocol versions and rejects a mismatch with a clear error rather than misbehaving. So any server build that speaks the same protocol version as this add-on will work with it, whatever its own version number happens to be. Each release states the protocol version it speaks.

The split exists for a reason: the server must survive NVDA restarts, since restarting NVDA is itself a thing a test may want to do.

### How it works?

1. Install this add-on (you have already done this if you are reading this from the Add-on Store).
2. Open **NVDA menu → Tools → NVDA MCP Bridge…** and press **Start**. Nothing listens until you do this — see [Starting and stopping the bridge](#starting-and-stopping-the-bridge).
3. Register the `screenreader-mcp` server with your MCP client. From a source checkout, build it once and register the binary; for Claude Code, this is:

   ```
   go -C <checkout>\server build -o screenreader-mcp.exe .\cmd\screenreader-mcp
   claude mcp add --scope user screenreader -- <checkout>\server\screenreader-mcp.exe
   ```

   The server takes no arguments: it ships knowing where this add-on listens. Ask the agent to list readers, then to connect to one.

From that point the agent has NVDA available as a set of tools.

## Note about secure mode

This is a development tool: it injects keystrokes and reads back what NVDA says. It is not designed for, and should not be relied on in, secure screens. Where NVDA's GUI is not available, the Tools menu item is simply not added and the dialog cannot be opened.

## Note about safety

Two properties matter more than any feature here, because the failure they prevent is a screen reader that has gone silent on a blind user:

* **The add-on is inert until you start it.** Auto-start is off by default, and even when it is listening it installs nothing with a side effect until a session actually connects. It is safe to leave permanently installed.
* **Your real synthesizer is never swapped.** Silent mode does not replace your synth with a spy driver — the synth you configured stays loaded and valid the whole time (see [Speech capture](#speech-capture)). Ending a session restores speech instantly, with no synth reload that could itself fail.

On top of that, speech is restored on **every** teardown path — `bye`, disconnect, error, timeout, NVDA shutdown, add-on unload — and by the panic gesture. And because NVDA holds speech filters by weak reference, even an add-on that dies outright lifts its own suppression.

## Features

### Starting and stopping the bridge

The bridge is controlled from **NVDA menu → Tools → NVDA MCP Bridge…**.

The dialog shows what the bridge is doing right now, and it stays live: if a client connects while the dialog is open, the status updates and is announced without you touching anything.

#### How it works?

The dialog has four things in it:

* **Connection mode** — a combo box, `Named pipe` or `TCP`. It is enabled only while the bridge is stopped; once it is listening, the mode is locked. To change it: Stop, choose, Start.
* **Start bridge automatically when NVDA loads** — a checkbox. Off by default. Saved as soon as you toggle it.
* **Start** and **Stop** buttons. Exactly one of the two is enabled at a time, depending on whether the bridge is running.
* A status bar, which NVDA reads with NVDA+End. It shows `Stopped`, `Listening on <endpoint>`, or `Client connected`.

State changes are announced as they happen — "Bridge started", "Bridge stopped", "Client connected", "Client disconnected" — no matter what caused them, and focus moves to whatever control is useful next (to **Stop** once it is listening, back to the mode combo once it is stopped).

**Close** closes the dialog and nothing else. It does not stop the bridge.

### Connection modes

Two transports are offered, and both are local only.

* **Named pipe** (the default): `\\.\pipe\nvdaMcpBridge`.
* **TCP**: `127.0.0.1:8765`. Loopback only — the bridge never binds a routable address.

One session at a time, in either mode. A second client waits.

#### How it works?

Choose the mode in the dialog and press Start; the choice is remembered for next time. The status bar shows the endpoint the bridge is actually listening on, which is also what you would put in the server's configuration if it needs to be told explicitly.

### Speech capture

The agent can read back what NVDA said, either as a running indexed stream or as "just the last thing". It can also wait for speech to appear, or wait for NVDA to finish speaking, which is what makes reliable test steps possible.

Capture happens in one of two modes, chosen by the agent when the session opens:

* **Silent** — NVDA's speech is captured and suppressed. Deterministic, and fast, because no audio is produced. This is the mode a test run wants.
* **Live** — NVDA's speech is captured and also spoken normally. This is the mode you want when you are sitting there listening to the agent work.

#### How it works?

In both modes the real synthesizer stays loaded and active. NVDA, and every other add-on, keep seeing the synth you configured, so nothing downstream notices a bridge session is in progress.

Silent mode registers a filter that NVDA applies to every speech sequence before it reaches the synth: the bridge copies the sequence into its buffer and then hands back an empty one, so nothing is synthesized. Stopping the session unregisters the filter and speech resumes immediately. If the bridge's own filter ever raises, NVDA keeps the original sequence — a bug in this add-on fails toward speech, not toward silence.

Live mode hooks the point where speech is queued instead, and leaves the sequence untouched on its way to the synth.

### Braille capture

The agent can read back the current braille display content, so a test can assert on what a braille user would be reading — not just on what is spoken.

#### How it works?

Nothing to configure. The braille buffer is available for the whole session and is read on demand.

### Gesture injection

The agent can press keys as if you had pressed them: `NVDA+control+f`, `alt+tab`, `downArrow`, and so on, in NVDA's own gesture syntax.

#### How it works?

Gestures are executed on NVDA's main thread, exactly as a real keypress would be, so the code under test cannot tell the difference. Combined with speech capture and the wait commands, this is the whole functional-testing loop: press something, wait for speech to settle, read back what was said.

### Announcements

The agent can make NVDA say something of its own — progress reports, "starting step 3", the result of a check.

#### How it works?

The message is spoken through NVDA's normal announcement path. In a silent-mode session it is still spoken, which is what you want: the point of an announcement is that a human hears it.

### Log capture and session transcripts

Every session records what happened, and the agent can ask NVDA to raise its logging verbosity for the duration of the session — `debug`, `io`, `debugwarning` or `info`.

#### How it works?

Both kinds of file land in `nvdaMcpBridge`, inside your NVDA user configuration directory:

* `session-*.log` — the bridge's own transcript of the session.
* `nvda-log-*.log` — NVDA's log, captured for that session.

A requested verbosity raises NVDA's real logging level, not just what is written to the private capture, and it is restored when the session ends. Each family of files is pruned independently, so neither can grow without bound.

### The panic gesture

**NVDA+control+shift+b** stops the bridge immediately: any active session is torn down, speech is restored, and NVDA confirms with "NVDA MCP bridge stopped".

#### How it works?

Press it. It works whether or not the dialog is open, and it does not depend on the agent, the server, or the connection being healthy — that is the entire point of it.

The gesture can be reassigned in NVDA's Input Gestures dialog, under the **NVDA MCP Bridge** category.

## Settings storage

Both preferences — connection mode and auto-start — live in `nvdaMcpBridge\config\config.ini` inside your NVDA user configuration directory, under a `[nvdaMcpBridge]` section.

They are deliberately **not** NVDA configuration profile settings. Whether the bridge is listening is a property of the machine you are testing on, not of the application you happen to be focused on.

## What is not here yet

The wire protocol defines command groups this version does not implement: focus information, general state introspection, and reading or writing NVDA configuration. The add-on does not advertise those capabilities, so a well-behaved server will not offer them as tools; if one is called anyway, it answers with a clean error rather than failing strangely.

Remote (non-loopback) TCP is defined in the protocol but is deliberately not reachable from the interface, pending its security design.

## Contributing and translating

If you want to contribute or translate this add-on, please access the [project repository](https://github.com/marlon-sousa/screen-readers-mcp) and follow the instructions there.

## License

GNU General Public License version 2 or later. See COPYING.txt.
